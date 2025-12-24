"""
InvoiceGuard - Peppol BIS 3.0 Pre-flight Validator
Deterministic, fail-safe API wrapping KoSIT Validator v1.5.0
"""

import asyncio
import logging
import os
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

# Enhanced imports
from diagnostics.pipeline import DiagnosticsPipeline
from diagnostics.models import ValidationError, ErrorAction, ErrorEvidence, DebugContext, OutputMode, KoSITReport
from diagnostics.presentation import apply_mode_filter

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG for better troubleshooting
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Global configuration with environment variable support
VALIDATOR_JAR = os.environ.get("VALIDATOR_JAR", "/app/validator.jar")
VERSION_INFO_FILE = os.environ.get("VERSION_INFO_FILE", "/app/version_info.txt")
RULES_DIR_FILE = os.environ.get("RULES_DIR_FILE", "/app/rules_dir.txt")
TEMP_DIR = os.environ.get("TEMP_DIR", "/app/temp")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
VALIDATION_TIMEOUT = 30  # seconds

# Concurrency control
validation_semaphore = asyncio.Semaphore(1)

# Application
app = FastAPI(title="InvoiceGuard", version="1.0.0")


class ValidationMeta(BaseModel):
    engine: str
    rules_tag: str
    commit: str


class ValidationResponse(BaseModel):
    status: str  # PASSED, REJECTED, ERROR
    meta: ValidationMeta
    errors: List[ValidationError]
    debug_log: Optional[str] = None
    kosit: Optional[KoSITReport] = None  # Raw KoSIT report (included in TIER0 mode)


# Read configuration at startup
def load_config():
    """Load validator configuration and rules directory."""
    try:
        # Read commit hash
        with open(VERSION_INFO_FILE, 'r') as f:
            commit_hash = f.read().strip()
        
        # Read rules directory
        with open(RULES_DIR_FILE, 'r') as f:
            rules_dir = f.read().strip()
        
        # In development mode, skip file existence checks
        if not os.environ.get("DEV_MODE"):
            # Verify files exist (only in production)
            if not os.path.exists(VALIDATOR_JAR):
                raise FileNotFoundError(f"Validator JAR not found: {VALIDATOR_JAR}")
            
            scenarios_file = os.path.join(rules_dir, "scenarios.xml")
            if not os.path.exists(scenarios_file):
                raise FileNotFoundError(f"Scenarios file not found: {scenarios_file}")
        
        logger.info(f"Validator Ready. Rules Commit: {commit_hash}")
        logger.info(f"Rules Directory: {rules_dir}")
        
        return {
            "commit_hash": commit_hash,
            "rules_dir": rules_dir
        }
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise


# Load config on startup
config = load_config()

# Initialize humanization pipeline
diagnostics_pipeline = DiagnosticsPipeline()
logger.info("Humanization layer initialized")

# Ensure temp directory exists
os.makedirs(TEMP_DIR, exist_ok=True)


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("InvoiceGuard API starting up...")
    logger.info(f"KoSIT Validator: {VALIDATOR_JAR}")
    logger.info(f"Rules: {config['rules_dir']}")
    logger.info(f"Commit: {config['commit_hash']}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {
        "message": "InvoiceGuard API is running",
        "docs": "/docs",
        "health": "/health"
    }


@app.post("/validate")
async def validate_invoice(
    file: UploadFile = File(...),
    mode: OutputMode = OutputMode.TIER0
):
    """
    Validate a Peppol BIS 3.0 invoice against KoSIT rules.
    
    Args:
        file: Invoice XML file to validate
        mode: Output filtering mode
              - TIER0: Raw KoSIT findings only, no enrichment, includes raw report [default]
              - SHORT: Only id, summary, fix (for Suppliers)
              - BALANCED: Add evidence, 3 sample locations (for Developers)
              - DETAILED: Everything including all locations and raw logs (for Auditors)
    
    Returns:
        JSONResponse with validation results filtered by mode
    """
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(TEMP_DIR, session_id)
    input_path = None
    
    try:
        # Create session directory
        os.makedirs(session_dir, exist_ok=True)
        input_path = os.path.join(session_dir, "input.xml")
        
        # Read file with chunked streaming and size limit
        file_size = 0
        with open(input_path, 'wb') as f:
            while True:
                chunk = await file.read(1024)
                if not chunk:
                    break
                file_size += len(chunk)
                
                # Check size limit
                if file_size > MAX_FILE_SIZE:
                    logger.warning(f"File size exceeded limit: {file_size} bytes")
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File size exceeds 10MB limit"
                    )
                
                f.write(chunk)
        
        logger.info(f"Session {session_id}: Received file ({file_size} bytes)")
        
        # Acquire semaphore for validation
        async with validation_semaphore:
            result = await validate_file(session_id, input_path, mode)
            # Apply presentation filtering and ensure JSON-safe serialization
            try:
                filtered_result = apply_mode_filter(mode, result)
                json_safe_result = jsonable_encoder(filtered_result)
                return JSONResponse(content=json_safe_result)
            except ValueError as e:
                # Invalid mode
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e)
                )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session {session_id}: Unexpected error: {e}")
        
        # Create INTERNAL_ERROR with tiered structure
        internal_error = {
            "id": "INTERNAL_ERROR",
            "message": f"Unexpected error: {str(e)}",
            "location": "",
            "severity": "fatal",
            "humanized_message": "System Error: An unexpected error occurred during validation.",
            "suppressed": False
        }
        
        error_response = ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[convert_flat_to_tiered(internal_error, session_id)],
            debug_log=None
        )
        try:
            filtered_error = apply_mode_filter(mode, error_response)
            return JSONResponse(content=jsonable_encoder(filtered_error))
        except ValueError:
            # If mode is invalid, default to balanced
            filtered_error = apply_mode_filter(OutputMode.BALANCED, error_response)
            return JSONResponse(content=jsonable_encoder(filtered_error))
    finally:
        # Always cleanup temp directory
        if os.path.exists(session_dir):
            try:
                shutil.rmtree(session_dir)
                logger.debug(f"Session {session_id}: Cleaned up temp directory")
            except Exception as e:
                logger.error(f"Session {session_id}: Failed to cleanup: {e}")


def clean_xpath(xpath: str) -> str:
    """
    Clean XPath by removing namespace prefixes and making it human-readable.
    
    Examples:
        /*:Invoice[namespace-uri()='...'] → /Invoice[1]
        /cbc:TaxExclusiveAmount[1] → /TaxExclusiveAmount[1]
    
    Args:
        xpath: Raw XPath with namespaces
        
    Returns:
        Clean XPath without namespace prefixes
    """
    if not xpath:
        return xpath
    
    import re
    
    # Remove namespace-uri() predicates
    cleaned = re.sub(r'\[namespace-uri\(\)=[^\]]+\]', '', xpath)
    
    # Remove *: namespace prefixes
    cleaned = re.sub(r'/\*:', '/', cleaned)
    
    # Remove cbc:, cac:, and other namespace prefixes
    cleaned = re.sub(r'/(cbc|cac|ubl|qdt|ccts):', '/', cleaned)
    
    return cleaned


def parse_kosit_report_tier0(root: ET.Element, session_id: str) -> List[ValidationError]:
    """
    Parse KoSIT report in TIER0 mode - raw findings only, no enrichment.
    
    Args:
        root: XML root element of KoSIT report
        session_id: Session ID for logging
        
    Returns:
        List of ValidationError objects with raw KoSIT data only
    """
    errors = []
    failed_items = []
    
    # Parse both KoSIT VARL and Standard SVRL formats
    for elem in root.iter():
        tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        # KoSIT VARL Format: <rep:message code="BR-CO-15" level="error">Text</rep:message>
        if tag_name == 'message':
            error_code = elem.get('code')
            if error_code:
                failed_items.append({'type': 'kosit', 'elem': elem})
        
        # Standard SVRL Format: <svrl:failed-assert id="BR-CO-15"><svrl:text>Text</svrl:text>
        elif tag_name == 'failed-assert':
            failed_items.append({'type': 'svrl', 'elem': elem})
    
    logger.debug(f"Session {session_id}: Found {len(failed_items)} raw findings in TIER0 mode")
    
    for item in failed_items:
        elem = item['elem']
        
        if item['type'] == 'kosit':
            error_code = elem.get('code', 'UNKNOWN')
            severity = elem.get('level', 'error')
            raw_location = elem.get('xpathLocation', '')
            raw_message = elem.text.strip() if elem.text else "Validation failed"
        else:
            error_code = elem.get('id') or elem.get('location') or "UNKNOWN"
            severity = "error"
            raw_location = elem.get('location', '')
            raw_message = "Validation failed"
            for child in elem:
                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if child_tag == 'text' and child.text:
                    raw_message = child.text.strip()
                    break
        
        # TIER0: Create ValidationError with raw data only
        # - action.summary = raw KoSIT message (verbatim)
        # - action.fix = generic constant string
        # - locations = raw locations from KoSIT
        # - no evidence (TIER0 doesn't compute this)
        # - technical_details preserved verbatim
        error = ValidationError(
            id=error_code,
            severity=severity,
            action=ErrorAction(
                summary=raw_message,  # Verbatim KoSIT message
                fix="See rule description and correct the invoice data accordingly.",  # Generic constant
                locations=[raw_location] if raw_location else []
            ),
            evidence=None,  # No enrichment in TIER0
            technical_details=DebugContext(
                raw_message=raw_message,
                raw_locations=[raw_location] if raw_location else []
            ),
            suppressed=False  # No suppression in TIER0
        )
        errors.append(error)
    
    return errors


def read_report_files(output_dir: str, session_id: str) -> KoSITReport:
    """
    Read KoSIT report files (XML and optionally HTML).
    
    Args:
        output_dir: Directory containing report files
        session_id: Session ID for logging
        
    Returns:
        KoSITReport object with report content
    """
    report_xml_content = None
    report_html_content = None
    
    if os.path.exists(output_dir):
        output_files = os.listdir(output_dir)
        
        # Read XML report
        for filename in output_files:
            if filename.endswith('-report.xml') or filename == 'input-report.xml':
                xml_path = os.path.join(output_dir, filename)
                try:
                    with open(xml_path, 'r', encoding='utf-8') as f:
                        report_xml_content = f.read()
                    logger.debug(f"Session {session_id}: Read XML report ({len(report_xml_content)} bytes)")
                except Exception as e:
                    logger.error(f"Session {session_id}: Failed to read XML report: {e}")
                break
        
        # Read HTML report if available
        for filename in output_files:
            if filename.endswith('-report.html') or filename == 'input-report.html':
                html_path = os.path.join(output_dir, filename)
                try:
                    with open(html_path, 'r', encoding='utf-8') as f:
                        report_html_content = f.read()
                    logger.debug(f"Session {session_id}: Read HTML report ({len(report_html_content)} bytes)")
                except Exception as e:
                    logger.debug(f"Session {session_id}: HTML report not available or failed to read: {e}")
                break
    
    if not report_xml_content:
        logger.warning(f"Session {session_id}: No XML report content available")
        report_xml_content = "Report XML not available"
    
    return KoSITReport(
        report_xml=report_xml_content,
        report_html=report_html_content
    )


def convert_flat_to_tiered(flat_error: dict, session_id: str) -> ValidationError:
    """
    Convert flat error structure (from humanization pipeline) to tiered structure.
    
    Args:
        flat_error: Flat error dict with keys: id, message, location, severity, humanized_message, suppressed
        session_id: Session ID for logging
        
    Returns:
        ValidationError with tiered structure
    """
    error_id = flat_error.get("id", "UNKNOWN")
    raw_message = flat_error.get("message", "")
    raw_location = flat_error.get("location", "")
    severity = flat_error.get("severity", "error")
    humanized = flat_error.get("humanized_message", raw_message)
    suppressed = flat_error.get("suppressed", False)
    
    # Extract structured data if available (from R051 explainer)
    structured_data = flat_error.get("structured_data", {})
    bt5_value = structured_data.get("bt5_value")
    found_currency = structured_data.get("found_currency")
    
    # Build evidence if we have structured data
    evidence = None
    if bt5_value or found_currency:
        currency_ids = {}
        if found_currency:
            currency_ids[found_currency] = 1  # Will be aggregated in deduplication
        
        evidence = ErrorEvidence(
            bt5_value=bt5_value,
            currency_ids_found=currency_ids if currency_ids else None,
            occurrence_count=1
        )
    
    # Build action with default fix message
    fix_message = "Please review and correct this error according to the Peppol BIS 3.0 specification."
    
    # Special fix messages for known error types
    if error_id == "PEPPOL-EN16931-R051":
        fix_message = "Make BT-5 (DocumentCurrencyCode) and all currencyID attributes consistent. Either change BT-5 to match the amounts, or convert amounts and update currencyID to match BT-5."
    elif error_id == "BR-CO-15":
        fix_message = "Verify that Tax Inclusive Amount (BT-112) = Tax Exclusive Amount (BT-109) + Tax Amount (BT-110)."
    
    # Create tiered error
    return ValidationError(
        id=error_id,
        severity=severity,
        action=ErrorAction(
            summary=humanized or raw_message,
            fix=fix_message,
            locations=[clean_xpath(raw_location)] if raw_location else []
        ),
        evidence=evidence,
        technical_details=DebugContext(
            raw_message=raw_message,
            raw_locations=[raw_location] if raw_location else []
        ),
        suppressed=suppressed
    )


def _deduplicate_errors(errors: List[ValidationError], session_id: str) -> List[ValidationError]:
    """
    Deduplicate errors by grouping repeated error IDs and aggregating evidence.
    
    For errors with the same ID:
    - Aggregate all locations (cleaned and raw)
    - Aggregate currency evidence (count occurrences)
    - Update summary with repeat count
    - Merge into single error
    
    Args:
        errors: List of tiered validation errors
        session_id: Session ID for logging
        
    Returns:
        Deduplicated list of errors with aggregated evidence
    """
    if not errors:
        return errors
    
    # Group errors by ID
    error_groups = {}
    for error in errors:
        error_id = error.id
        if error_id not in error_groups:
            error_groups[error_id] = []
        error_groups[error_id].append(error)
    
    # Build deduplicated list with aggregated evidence
    deduplicated = []
    total_before = len(errors)
    
    for error_id, group in error_groups.items():
        occurrence_count = len(group)
        first_error = group[0]
        
        # Collect all unique locations (cleaned and raw)
        cleaned_locations = []
        raw_locations = []
        
        for err in group:
            # Collect cleaned locations from action
            for loc in err.action.locations:
                if loc and loc not in cleaned_locations:
                    cleaned_locations.append(loc)
            
            # Collect raw locations from technical_details
            for raw_loc in err.technical_details.raw_locations:
                if raw_loc and raw_loc not in raw_locations:
                    raw_locations.append(raw_loc)
        
        # Aggregate evidence (especially for R051 currency counts)
        aggregated_evidence = None
        if first_error.evidence:
            currency_counts = {}
            bt5_value = first_error.evidence.bt5_value
            
            # Aggregate currency_ids_found from all instances
            for err in group:
                if err.evidence and err.evidence.currency_ids_found:
                    for currency, count in err.evidence.currency_ids_found.items():
                        currency_counts[currency] = currency_counts.get(currency, 0) + count
            
            aggregated_evidence = ErrorEvidence(
                bt5_value=bt5_value,
                currency_ids_found=currency_counts if currency_counts else first_error.evidence.currency_ids_found,
                occurrence_count=occurrence_count
            )
        
        # Update summary with repeat count if multiple occurrences
        summary = first_error.action.summary
        if occurrence_count > 1:
            summary = f"{summary} (Repeated {occurrence_count} times)"
        
        # Create deduplicated error
        deduplicated_error = ValidationError(
            id=error_id,
            severity=first_error.severity,
            action=ErrorAction(
                summary=summary,
                fix=first_error.action.fix,
                locations=cleaned_locations
            ),
            evidence=aggregated_evidence,
            technical_details=DebugContext(
                raw_message=first_error.technical_details.raw_message,
                raw_locations=raw_locations
            ),
            suppressed=first_error.suppressed
        )
        
        deduplicated.append(deduplicated_error)
        
        if occurrence_count > 1:
            logger.debug(f"Session {session_id}: Deduplicated {occurrence_count} instances of {error_id}")
    
    total_after = len(deduplicated)
    if total_before != total_after:
        logger.info(f"Session {session_id}: Deduplication reduced errors from {total_before} to {total_after}")
    
    return deduplicated


def _apply_cross_error_suppression(errors: List[ValidationError], session_id: str) -> List[ValidationError]:
    """
    Apply cross-error suppression logic.
    
    If PEPPOL-EN16931-R051 (Currency Mismatch) is present, BR-CO-15 (Math Error) 
    is almost certainly a side effect. Suppress BR-CO-15 so the user focuses on 
    the root cause (currency mismatch).
    
    Args:
        errors: List of validation errors
        session_id: Session ID for logging
        
    Returns:
        List of errors with suppression applied
    """
    if not errors:
        return errors
    
    # Check if R051 (currency mismatch) is present
    has_r051 = any(e.id == "PEPPOL-EN16931-R051" for e in errors)
    
    if not has_r051:
        return errors
    
    # Suppress BR-CO-15 errors if R051 is present
    suppressed_count = 0
    for error in errors:
        if error.id == "BR-CO-15" and not error.suppressed:
            error.suppressed = True
            # Update action summary with clean suppression message
            error.action.summary = "Math Error (Suppressed: Likely caused by Currency Mismatch R051)"
            suppressed_count += 1
    
    if suppressed_count > 0:
        logger.info(f"Session {session_id}: Cross-error suppression - suppressed {suppressed_count} BR-CO-15 error(s) due to R051 currency mismatch")
    
    return errors


async def validate_file(session_id: str, input_path: str, mode: OutputMode = OutputMode.BALANCED) -> ValidationResponse:
    """
    Execute validation logic for a single file.
    
    Args:
        session_id: Unique session identifier
        input_path: Path to input XML file
        mode: Output filtering mode (SHORT, BALANCED, DETAILED)
        
    Returns:
        ValidationResponse with results filtered by mode
    """
    session_dir = os.path.dirname(input_path)
    output_dir = os.path.join(session_dir, "output")
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    logger.debug(f"Session {session_id}: Created output directory: {output_dir}")
    
    # Pre-flight check: Validate input XML
    try:
        ET.parse(input_path)
        logger.info(f"Session {session_id}: Input XML is well-formed")
    except ET.ParseError as e:
        logger.warning(f"Session {session_id}: Input is not valid XML: {e}")
        
        # Create INVALID_XML error with tiered structure
        invalid_xml_error = {
            "id": "INVALID_XML",
            "message": "Input file is not valid XML",
            "location": "",
            "severity": "fatal",
            "humanized_message": "Input file is not valid XML. Please provide a well-formed XML document.",
            "suppressed": False
        }
        
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[convert_flat_to_tiered(invalid_xml_error, session_id)],
            debug_log=str(e)
        )
    
    # Build Java command
    scenarios_file = os.path.join(config["rules_dir"], "scenarios.xml")
    cmd = [
        "java",
        "-jar", VALIDATOR_JAR,
        "-s", scenarios_file,
        "-r", config["rules_dir"],
        "-o", output_dir,
        input_path
    ]
    
    logger.info(f"Session {session_id}: Executing KoSIT validator...")
    logger.debug(f"Session {session_id}: Command: {' '.join(cmd)}")
    logger.debug(f"Session {session_id}: Working directory: /app")
    logger.debug(f"Session {session_id}: Output directory: {output_dir}")
    
    # Execute Java validator
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/app"  # Set working directory to /app so JAR can find lib folder
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=VALIDATION_TIMEOUT
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.error(f"Session {session_id}: Validation timed out")
            
            # Create TIMEOUT error with tiered structure
            timeout_error = {
                "id": "TIMEOUT",
                "message": "Validation timed out",
                "location": "",
                "severity": "fatal",
                "humanized_message": "Validation timed out. The file may be too complex or contain issues.",
                "suppressed": False
            }
            
            return ValidationResponse(
                status="ERROR",
                meta=ValidationMeta(
                    engine="KoSIT 1.5.0",
                    rules_tag="release-3.0.18",
                    commit=config["commit_hash"]
                ),
                errors=[convert_flat_to_tiered(timeout_error, session_id)],
                debug_log=None
            )
        
        # 1. First, check if a report file was generated
        report_path = None
        if os.path.exists(output_dir):
            for filename in os.listdir(output_dir):
                if filename == "input-report.xml" or filename.endswith("-report.xml"):
                    report_path = os.path.join(output_dir, filename)
                    break
        
        # 2. If NO report exists AND exit code is bad, THEN it's a crash
        if not report_path and process.returncode != 0:
            stderr_text = stderr.decode('utf-8', errors='replace')
            stdout_text = stdout.decode('utf-8', errors='replace')
            combined_log = f"--- STDOUT ---\n{stdout_text}\n\n--- STDERR ---\n{stderr_text}"
            logger.error(f"Session {session_id}: Validator crashed (exit code {process.returncode})")
            
            # Create VALIDATOR_CRASH error with tiered structure
            crash_error = {
                "id": "VALIDATOR_CRASH",
                "message": "Internal validator crash",
                "location": "",
                "severity": "fatal",
                "humanized_message": "System Error: The validator encountered an internal error.",
                "suppressed": False
            }
            
            return ValidationResponse(
                status="ERROR",
                meta=ValidationMeta(
                    engine="KoSIT 1.5.0",
                    rules_tag="release-3.0.18",
                    commit=config["commit_hash"]
                ),
                errors=[convert_flat_to_tiered(crash_error, session_id)],
                debug_log=combined_log[-4000:]
            )
        # 3. If we are here, we either have a report OR returncode was 0.
        # Proceed to parse the report (even if returncode was 1).
        
        logger.info(f"Session {session_id}: Validator completed successfully")
    
    except Exception as e:
        logger.error(f"Session {session_id}: Failed to execute validator: {e}")
        
        # Create EXECUTION_ERROR with tiered structure
        execution_error = {
            "id": "EXECUTION_ERROR",
            "message": f"Failed to execute validator: {str(e)}",
            "location": "",
            "severity": "fatal",
            "humanized_message": "System Error: Failed to execute the validation engine.",
            "suppressed": False
        }
        
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[convert_flat_to_tiered(execution_error, session_id)],
            debug_log=None
        )
    
    # Parse validation report - find the actual report file
    # The KoSIT validator generates input-report.xml (not input.xml-report.xml)
    report_path = None
    
    if os.path.exists(output_dir):
        output_files = os.listdir(output_dir)
        logger.debug(f"Session {session_id}: Files in output directory: {output_files}")
        
        # Look for the report file - prioritize the exact filename KoSIT generates
        for filename in output_files:
            # First check for the exact filename KoSIT validator generates
            if filename == "input-report.xml":
                report_path = os.path.join(output_dir, filename)
                logger.debug(f"Session {session_id}: Found KoSIT report file: {filename}")
                break
            # Fallback to other possible names
            elif filename in ["input.xml-report.xml"] or filename.endswith("-report.xml"):
                report_path = os.path.join(output_dir, filename)
                logger.debug(f"Session {session_id}: Found alternative report file: {filename}")
                break
    
    if not report_path or not os.path.exists(report_path):
        # List files in output directory for debugging
        if os.path.exists(output_dir):
            output_files = os.listdir(output_dir)
            logger.error(f"Session {session_id}: No valid report file found. Files: {output_files}")
        else:
            logger.error(f"Session {session_id}: Output directory does not exist: {output_dir}")
        
        stderr_text = stderr.decode('utf-8', errors='replace')
        stdout_text = stdout.decode('utf-8', errors='replace')
        logger.error(f"Session {session_id}: Report file missing")
        logger.debug(f"Session {session_id}: STDOUT: {stdout_text}")
        logger.debug(f"Session {session_id}: STDERR: {stderr_text}")
        
        # Create REPORT_MISSING error with tiered structure
        report_missing_error = {
            "id": "REPORT_MISSING",
            "message": "Report missing",
            "location": "",
            "severity": "fatal",
            "humanized_message": "System Error: The validation report could not be generated.",
            "suppressed": False
        }
        
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[convert_flat_to_tiered(report_missing_error, session_id)],
            debug_log=f"STDOUT: {stdout_text}\nSTDERR: {stderr_text}"
        )
    
    # Parse report XML
    logger.debug(f"Session {session_id}: Parsing report file: {report_path}")
    try:
        tree = ET.parse(report_path)
        root = tree.getroot()
    except ET.ParseError as e:
        logger.error(f"Session {session_id}: KoSIT output malformed: {e}")
        
        # Create MALFORMED_REPORT error with tiered structure
        malformed_error = {
            "id": "MALFORMED_REPORT",
            "message": "KoSIT output malformed",
            "location": "",
            "severity": "fatal",
            "humanized_message": "System Error: The validation report could not be parsed.",
            "suppressed": False
        }
        
        # For TIER0, try to include raw report even if parsing failed
        kosit_report = None
        if mode == OutputMode.TIER0:
            kosit_report = read_report_files(output_dir, session_id)
        
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[convert_flat_to_tiered(malformed_error, session_id)],
            debug_log=str(e),
            kosit=kosit_report
        )
    
    # ---------------------------------------------------------
    # TIER0 MODE: Raw KoSIT findings only, no enrichment
    # ---------------------------------------------------------
    if mode == OutputMode.TIER0:
        logger.info(f"Session {session_id}: Using TIER0 mode - raw KoSIT findings only")
        errors = parse_kosit_report_tier0(root, session_id)
        
        # Read raw report files
        kosit_report = read_report_files(output_dir, session_id)
        
        # Determine status
        if errors:
            validation_status = "REJECTED"
            logger.info(f"Session {session_id}: Validation REJECTED ({len(errors)} finding(s))")
        elif process.returncode != 0:
            validation_status = "ERROR"
            logger.error(f"Session {session_id}: Validator exited with error code {process.returncode} but no findings were parsed")
            
            # Create PARSING_MISMATCH error
            parsing_error = ValidationError(
                id="PARSER_ERROR",
                severity="error",
                action=ErrorAction(
                    summary="The validator rejected the file, but the report could not be parsed.",
                    fix="See rule description and correct the invoice data accordingly.",
                    locations=[]
                ),
                evidence=None,
                technical_details=DebugContext(
                    raw_message="Validator exited with non-zero code but no findings parsed",
                    raw_locations=[]
                ),
                suppressed=False
            )
            errors.append(parsing_error)
        else:
            validation_status = "PASSED"
            logger.info(f"Session {session_id}: Validation PASSED")
        
        return ValidationResponse(
            status=validation_status,
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=errors,
            debug_log=None,
            kosit=kosit_report
        )
    
    # ---------------------------------------------------------
    # ENRICHED MODES: Parse and apply humanization
    # ---------------------------------------------------------
    errors = []
    
    # We iterate every node. We strip namespaces.
    # We look for BOTH 'message' (KoSIT format) and 'failed-assert' (Standard format)
    
    failed_items = []
    
    for elem in root.iter():
        tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        # Mode 1: KoSIT VARL Format (What is in your logs)
        # Structure: <rep:message code="BR-CO-15" level="error">Text</rep:message>
        if tag_name == 'message':
            error_code = elem.get('code')
            if error_code: # Only treat as error if it has a code
                failed_items.append({
                    'type': 'kosit',
                    'elem': elem
                })

        # Mode 2: Standard SVRL Format (Fallback)
        # Structure: <svrl:failed-assert id="BR-CO-15"><svrl:text>Text</svrl:text>...
        elif tag_name == 'failed-assert':
             failed_items.append({
                'type': 'svrl',
                'elem': elem
             })

    logger.debug(f"Session {session_id}: Found {len(failed_items)} raw error items")

    for item in failed_items:
        elem = item['elem']
        
        if item['type'] == 'kosit':
            # --- PARSING KOSIT VARL ---
            error_code = elem.get('code', 'UNKNOWN')
            severity = elem.get('level', 'error')
            location = elem.get('xpathLocation', '')
            message = elem.text.strip() if elem.text else "Validation failed"
            
        else:
            # --- PARSING STANDARD SVRL ---
            error_code = elem.get('id') or elem.get('location') or "UNKNOWN"
            severity = "error" # SVRL failed-assert is always an error
            location = elem.get('location', '')
            
            # Find message text in children
            message = "Validation failed"
            for child in elem:
                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if child_tag == 'text' and child.text:
                    message = child.text.strip()
                    break

        # Add to final list - using flat structure, will be converted after humanization
        errors.append({
            "id": error_code,
            "message": message,
            "location": location,
            "severity": severity,
            "humanized_message": None,
            "suppressed": False
        })
            
    # ---------------------------------------------------------
    # END NEW PARSER
    # ---------------------------------------------------------
    
    # Apply humanization layer to enhance error messages
    if errors:
        try:
            logger.debug(f"Session {session_id}: Applying humanization layer to {len(errors)} errors")
            
            # Read the original input file for context
            with open(input_path, 'rb') as f:
                invoice_xml = f.read()
            
            # Convert errors to the format expected by humanization pipeline
            kosit_errors = []
            for error in errors:
                kosit_errors.append({
                    "id": error["id"],
                    "message": error["message"],
                    "location": error.get("location", ""),
                    "severity": error.get("severity", "error")
                })
            
            # Run humanization pipeline
            humanization_result = diagnostics_pipeline.run(kosit_errors, invoice_xml)
            
            # Convert humanized errors to tiered structure
            enhanced_errors = []
            for processed_error in humanization_result.processed_errors:
                tiered_error = convert_flat_to_tiered(processed_error, session_id)
                enhanced_errors.append(tiered_error)
            
            # Replace original errors with enhanced errors
            errors = enhanced_errors
            
            # Log humanization statistics
            enriched_count = sum(1 for e in errors if e.humanized_message)
            suppressed_count = sum(1 for e in errors if e.suppressed)
            logger.info(f"Session {session_id}: Humanization completed - {enriched_count} enriched, {suppressed_count} suppressed")
            
            # Deduplicate errors - group repeated errors by ID
            errors = _deduplicate_errors(errors, session_id)
            
            # Apply cross-error suppression logic
            errors = _apply_cross_error_suppression(errors, session_id)
            
        except Exception as e:
            logger.error(f"Session {session_id}: Humanization failed: {e}")
            # Continue with original errors if humanization fails
    
    # Determine status
    if errors:
        validation_status = "REJECTED"
        logger.info(f"Session {session_id}: Validation REJECTED ({len(errors)} error(s))")
    
    # --- SAFETY CATCH START ---
    elif process.returncode != 0:
        # The Java tool crashed or rejected the file, but our XML parser found 0 errors.
        # This prevents "False Positives" (Passing a bad file).
        validation_status = "ERROR"
        logger.error(f"Session {session_id}: Validator exited with error code {process.returncode} but no SVRL errors were parsed.")
        
        # DEBUG TRAP: Read the XML report content to see what's inside
        report_dump = ""
        if report_path and os.path.exists(report_path):
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    report_dump = f.read()
                logger.debug(f"Session {session_id}: Successfully read report file ({len(report_dump)} bytes)")
            except Exception as e:
                report_dump = f"[ERROR: Could not read report file: {e}]"
                logger.error(f"Session {session_id}: Failed to read report file: {e}")
        else:
            report_dump = f"[ERROR: Report file not found at path: {report_path}]"
            logger.error(f"Session {session_id}: Report file not found at {report_path}")
        
        # Capture the stderr to show what went wrong
        stderr_text = stderr.decode('utf-8', errors='replace')
        stdout_text = stdout.decode('utf-8', errors='replace')
        
        # Create PARSING_MISMATCH error with tiered structure
        parsing_error = {
            "id": "PARSING_MISMATCH",
            "message": "The validator rejected the file, but the report could not be parsed. Check the debug log.",
            "location": "",
            "severity": "fatal",
            "humanized_message": "System Error: The validator rejected this file, but we could not read the error report.",
            "suppressed": False
        }
        errors.append(convert_flat_to_tiered(parsing_error, session_id))
        
        # Attach the raw log AND XML report dump so you can debug WHY the parsing failed
        debug_output = f"""--- XML REPORT DUMP ---
{report_dump}

--- STDOUT ---
{stdout_text}

--- STDERR ---
{stderr_text}
"""
        
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=errors,
            debug_log=debug_output
        )
    # --- SAFETY CATCH END ---

    else:
        validation_status = "PASSED"
        logger.info(f"Session {session_id}: Validation PASSED")
    
    # Sort errors: active errors first, suppressed errors last
    if errors:
        active_errors = [e for e in errors if not e.suppressed]
        suppressed_errors = [e for e in errors if e.suppressed]
        errors = active_errors + suppressed_errors
        
        if suppressed_errors:
            logger.debug(f"Session {session_id}: Sorted {len(active_errors)} active errors before {len(suppressed_errors)} suppressed errors")
    
    return ValidationResponse(
        status=validation_status,
        meta=ValidationMeta(
            engine="KoSIT 1.5.0",
            rules_tag="release-3.0.18",
            commit=config["commit_hash"]
        ),
        errors=errors,
        debug_log=None
    )


def parse_kosit_report_tier0(root: ET.Element, session_id: str) -> List[ValidationError]:
    """
    Parse KoSIT report in TIER0 mode - raw findings only, no enrichment.
    
    Args:
        root: XML root element of KoSIT report
        session_id: Session ID for logging
        
    Returns:
        List of ValidationError objects with raw KoSIT data only
    """
    errors = []
    failed_items = []
    
    # Parse both KoSIT VARL and Standard SVRL formats
    for elem in root.iter():
        tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        # KoSIT VARL Format: <rep:message code="BR-CO-15" level="error">Text</rep:message>
        if tag_name == 'message':
            error_code = elem.get('code')
            if error_code:
                failed_items.append({'type': 'kosit', 'elem': elem})
        
        # Standard SVRL Format: <svrl:failed-assert id="BR-CO-15"><svrl:text>Text</svrl:text>
        elif tag_name == 'failed-assert':
            failed_items.append({'type': 'svrl', 'elem': elem})
    
    logger.debug(f"Session {session_id}: Found {len(failed_items)} raw findings in TIER0 mode")
    
    for item in failed_items:
        elem = item['elem']
        
        if item['type'] == 'kosit':
            error_code = elem.get('code', 'UNKNOWN')
            severity = elem.get('level', 'error')
            raw_location = elem.get('xpathLocation', '')
            raw_message = elem.text.strip() if elem.text else "Validation failed"
        else:
            error_code = elem.get('id') or elem.get('location') or "UNKNOWN"
            severity = "error"
            raw_location = elem.get('location', '')
            raw_message = "Validation failed"
            for child in elem:
                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if child_tag == 'text' and child.text:
                    raw_message = child.text.strip()
                    break
        
        # TIER0: Create ValidationError with raw data only
        # - action.summary = raw KoSIT message (verbatim)
        # - action.fix = generic constant string
        # - locations = raw locations from KoSIT
        # - no evidence (TIER0 doesn't compute this)
        # - technical_details preserved verbatim
        error = ValidationError(
            id=error_code,
            severity=severity,
            action=ErrorAction(
                summary=raw_message,  # Verbatim KoSIT message
                fix="See rule description and correct the invoice data accordingly.",  # Generic constant
                locations=[raw_location] if raw_location else []
            ),
            evidence=None,  # No enrichment in TIER0
            technical_details=DebugContext(
                raw_message=raw_message,
                raw_locations=[raw_location] if raw_location else []
            ),
            suppressed=False  # No suppression in TIER0
        )
        errors.append(error)
    
    return errors


def read_report_files(output_dir: str, session_id: str) -> KoSITReport:
    """
    Read KoSIT report files (XML and optionally HTML).
    
    Args:
        output_dir: Directory containing report files
        session_id: Session ID for logging
        
    Returns:
        KoSITReport object with report content
    """
    report_xml_content = None
    report_html_content = None
    
    if os.path.exists(output_dir):
        output_files = os.listdir(output_dir)
        
        # Read XML report
        for filename in output_files:
            if filename.endswith('-report.xml') or filename == 'input-report.xml':
                xml_path = os.path.join(output_dir, filename)
                try:
                    with open(xml_path, 'r', encoding='utf-8') as f:
                        report_xml_content = f.read()
                    logger.debug(f"Session {session_id}: Read XML report ({len(report_xml_content)} bytes)")
                except Exception as e:
                    logger.error(f"Session {session_id}: Failed to read XML report: {e}")
                break
        
        # Read HTML report if available
        for filename in output_files:
            if filename.endswith('-report.html') or filename == 'input-report.html':
                html_path = os.path.join(output_dir, filename)
                try:
                    with open(html_path, 'r', encoding='utf-8') as f:
                        report_html_content = f.read()
                    logger.debug(f"Session {session_id}: Read HTML report ({len(report_html_content)} bytes)")
                except Exception as e:
                    logger.debug(f"Session {session_id}: HTML report not available or failed to read: {e}")
                break
    
    if not report_xml_content:
        logger.warning(f"Session {session_id}: No XML report content available")
        report_xml_content = "Report XML not available"
    
    return KoSITReport(
        report_xml=report_xml_content,
        report_html=report_html_content
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
