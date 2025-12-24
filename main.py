"""
InvoiceGuard - Peppol BIS 3.0 Pre-flight Validator (Tier 0 Only)
Returns raw KoSIT findings with no enrichment.
"""

import asyncio
import logging
import os
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, status, Query
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

# Tier 0 imports - raw KoSIT only
from diagnostics.models import (
    ValidationError, ErrorAction, DebugContext, ErrorEvidence,
    OutputMode, OutputType, GroupingMode, KoSITReport
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Global configuration
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
    status: str = Field(..., description="Validation status: PASSED, REJECTED, or ERROR")
    meta: ValidationMeta = Field(..., description="Validation engine metadata")
    errors: List[ValidationError] = Field(..., description="List of validation errors found")
    debug_log: Optional[str] = Field(None, description="Debug log for troubleshooting")
    kosit: Optional[KoSITReport] = Field(None, description="Raw KoSIT report (XML + HTML). Include with include_kosit_report=true")


def load_config():
    """Load validator configuration."""
    try:
        with open(VERSION_INFO_FILE, 'r') as f:
            commit_hash = f.read().strip()
        
        with open(RULES_DIR_FILE, 'r') as f:
            rules_dir = f.read().strip()
        
        if not os.environ.get("DEV_MODE"):
            if not os.path.exists(VALIDATOR_JAR):
                raise FileNotFoundError(f"Validator JAR not found: {VALIDATOR_JAR}")
            
            scenarios_file = os.path.join(rules_dir, "scenarios.xml")
            if not os.path.exists(scenarios_file):
                raise FileNotFoundError(f"Scenarios file not found: {scenarios_file}")
        
        logger.info(f"Validator Ready. Rules Commit: {commit_hash}")
        logger.info(f"Rules Directory: {rules_dir}")
        
        return {"commit_hash": commit_hash, "rules_dir": rules_dir}
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise


config = load_config()
os.makedirs(TEMP_DIR, exist_ok=True)


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("InvoiceGuard API starting up (Tier 0 - Raw KoSIT Only)...")
    logger.info(f"KoSIT Validator: {VALIDATOR_JAR}")
    logger.info(f"Rules: {config['rules_dir']}")
    logger.info(f"Commit: {config['commit_hash']}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "mode": "tier0"}


@app.get("/")
async def root():
    return {
        "message": "InvoiceGuard API - Deterministic Output Selector",
        "docs": "/docs",
        "health": "/health",
        "output_types": ["raw", "t0", "t1"],
        "grouping_modes": ["ungrouped", "grouped"]
    }


@app.post("/validate")
async def validate_invoice(
    file: UploadFile = File(..., description="Invoice XML file to validate (max 10MB)"),
    type: OutputType = Query(
        OutputType.T1,
        description="Output type: 'raw' (KoSIT report only), 't0' (1:1 findings), 't1' (with evidence). Default: t1"
    ),
    grouping: GroupingMode = Query(
        GroupingMode.UNGROUPED,
        description="Grouping mode: 'ungrouped' (one per finding) or 'grouped' (deduplicate by rule+message). "
                    "Only applies to type=t1. Default: ungrouped"
    ),
    mode: Optional[OutputMode] = Query(
        None,
        description="Legacy output mode (deprecated, use 'type' parameter instead)"
    ),
    include_kosit_report: Optional[bool] = Query(
        True,
        description="Include raw KoSIT report (XML + HTML) in response. "
                    "Accepted values: true, false, 1, 0. Default: true"
    )
):
    """
    Validate a Peppol BIS 3.0 invoice against KoSIT rules with deterministic output selection.
    
    **Output Types:**
    - `raw`: Returns only KoSIT report (XML + HTML), no parsed errors
    - `t0`: Returns 1:1 KoSIT findings with verbatim messages, no evidence
    - `t1`: Returns findings with deterministic evidence extraction (default)
    
    **Grouping Modes** (only for type=t1):
    - `ungrouped`: One error per KoSIT finding, preserves ordering (default)
    - `grouped`: Groups by id + severity + message, adds occurrence_count
    
    **Query Parameters:**
    - `type`: Output type selector (default: t1)
    - `grouping`: Grouping mode for t1 output (default: ungrouped)
    - `include_kosit_report`: Include raw KoSIT report in response (default: true)
    
    **Response Structure:**
    - `status`: PASSED, REJECTED, or ERROR
    - `meta`: Validation engine metadata
    - `errors`: List of validation errors (empty for type=raw)
    - `kosit`: Raw KoSIT report (if include_kosit_report=true)
    
    **Examples:**
    
    Default (T1 ungrouped with KoSIT report):
    ```bash
    curl -X POST "http://localhost:8080/validate" \\
         -F "file=@invoice.xml"
    ```
    
    T1 with grouping:
    ```bash
    curl -X POST "http://localhost:8080/validate?type=t1&grouping=grouped" \\
         -F "file=@invoice.xml"
    ```
    
    T0 (1:1 findings, no evidence):
    ```bash
    curl -X POST "http://localhost:8080/validate?type=t0" \\
         -F "file=@invoice.xml"
    ```
    
    Raw KoSIT only:
    ```bash
    curl -X POST "http://localhost:8080/validate?type=raw" \\
         -F "file=@invoice.xml"
    ```
    
    Without KoSIT report (smaller response):
    ```bash
    curl -X POST "http://localhost:8080/validate?type=t1&include_kosit_report=false" \\
         -F "file=@invoice.xml"
    ```
    
    Args:
        file: Invoice XML file to validate
        type: Output type (raw/t0/t1)
        grouping: Grouping mode (ungrouped/grouped, only for t1)
        mode: Legacy parameter (deprecated)
        include_kosit_report: Whether to include raw KoSIT report
    
    Returns:
        JSONResponse with validation results according to selected type
    """
    # Legacy mode handling (backward compatibility)
    if mode is not None:
        logger.warning(f"Legacy 'mode' parameter used: {mode}. Please use 'type' parameter instead.")
        # Map legacy mode to type
        if mode == OutputMode.TIER0:
            type = OutputType.T0
    
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(TEMP_DIR, session_id)
    
    try:
        os.makedirs(session_dir, exist_ok=True)
        input_path = os.path.join(session_dir, "input.xml")
        
        # Read file with size limit
        file_size = 0
        with open(input_path, 'wb') as f:
            while True:
                chunk = await file.read(1024)
                if not chunk:
                    break
                file_size += len(chunk)
                
                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File size exceeds 10MB limit"
                    )
                
                f.write(chunk)
        
        logger.info(f"Session {session_id}: Received file ({file_size} bytes)")
        
        async with validation_semaphore:
            result = await validate_file(session_id, input_path, type, grouping, include_kosit_report)
            # Convert to dict
            response_dict = result.dict()
            # Conditionally remove kosit field based on flag
            if not include_kosit_report and 'kosit' in response_dict:
                del response_dict['kosit']
            # Remove other None fields (but not kosit if we want to keep it)
            response_dict = {k: v for k, v in response_dict.items() if v is not None or (k == 'kosit' and include_kosit_report)}
            return JSONResponse(content=jsonable_encoder(response_dict))
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session {session_id}: Unexpected error: {e}")
        
        error_response = ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[ValidationError(
                id="INTERNAL_ERROR",
                severity="fatal",
                action=ErrorAction(
                    summary=f"Unexpected error: {str(e)}",
                    fix="See rule description and correct the invoice data accordingly.",
                    locations=[]
                ),
                technical_details=DebugContext(
                    raw_message=f"Unexpected error: {str(e)}",
                    raw_locations=[]
                )
            )],
            debug_log=str(e),
            kosit=None  # Error case - no report available
        )
        response_dict = error_response.dict()
        if not include_kosit_report and 'kosit' in response_dict:
            del response_dict['kosit']
        # Remove other None fields
        response_dict = {k: v for k, v in response_dict.items() if v is not None or (k == 'kosit' and include_kosit_report)}
        return JSONResponse(content=jsonable_encoder(response_dict))
    finally:
        if os.path.exists(session_dir):
            try:
                shutil.rmtree(session_dir)
                logger.debug(f"Session {session_id}: Cleaned up temp directory")
            except Exception as e:
                logger.error(f"Session {session_id}: Failed to cleanup: {e}")


async def validate_file(
    session_id: str,
    input_path: str,
    output_type: OutputType = OutputType.T1,
    grouping: GroupingMode = GroupingMode.UNGROUPED,
    include_kosit_report: bool = True
) -> ValidationResponse:
    """
    Execute validation logic for a single file with deterministic output selection.
    
    Args:
        session_id: Unique session identifier
        input_path: Path to input XML file
        output_type: Output type (raw/t0/t1)
        grouping: Grouping mode (ungrouped/grouped, only for t1)
        include_kosit_report: Whether to include raw KoSIT report in response
        
    Returns:
        ValidationResponse with results according to selected output type
    """
    session_dir = os.path.dirname(input_path)
    output_dir = os.path.join(session_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # Pre-flight check: Validate input XML
    try:
        ET.parse(input_path)
        logger.info(f"Session {session_id}: Input XML is well-formed")
    except ET.ParseError as e:
        logger.warning(f"Session {session_id}: Input is not valid XML: {e}")
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[ValidationError(
                id="INVALID_XML",
                severity="fatal",
                action=ErrorAction(
                    summary="Input file is not valid XML. Please provide a well-formed XML document.",
                    fix="See rule description and correct the invoice data accordingly.",
                    locations=[]
                ),
                technical_details=DebugContext(
                    raw_message="Input file is not valid XML",
                    raw_locations=[]
                )
            )],
            debug_log=str(e),
            kosit=None  # Error case - no report available
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
    
    # Execute Java validator
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/app"
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
            return ValidationResponse(
                status="ERROR",
                meta=ValidationMeta(
                    engine="KoSIT 1.5.0",
                    rules_tag="release-3.0.18",
                    commit=config["commit_hash"]
                ),
                errors=[ValidationError(
                    id="TIMEOUT",
                    severity="fatal",
                    action=ErrorAction(
                        summary="Validation timed out. The file may be too complex or contain issues.",
                        fix="See rule description and correct the invoice data accordingly.",
                        locations=[]
                    ),
                    technical_details=DebugContext(
                        raw_message="Validation timed out",
                        raw_locations=[]
                    )
                )],
                debug_log=None,
                kosit=None  # Error case - no report available
            )
        
        logger.info(f"Session {session_id}: Validator completed")
    
    except Exception as e:
        logger.error(f"Session {session_id}: Failed to execute validator: {e}")
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[ValidationError(
                id="EXECUTION_ERROR",
                severity="fatal",
                action=ErrorAction(
                    summary="System Error: Failed to execute the validation engine.",
                    fix="See rule description and correct the invoice data accordingly.",
                    locations=[]
                ),
                technical_details=DebugContext(
                    raw_message=f"Failed to execute validator: {str(e)}",
                    raw_locations=[]
                )
            )],
            debug_log=None,
            kosit=None  # Error case - no report available
        )
    
    # Find report file
    report_path = None
    if os.path.exists(output_dir):
        for filename in os.listdir(output_dir):
            if filename == "input-report.xml" or filename.endswith("-report.xml"):
                report_path = os.path.join(output_dir, filename)
                break
    
    if not report_path and process.returncode != 0:
        stderr_text = stderr.decode('utf-8', errors='replace')
        stdout_text = stdout.decode('utf-8', errors='replace')
        logger.error(f"Session {session_id}: Validator crashed (exit code {process.returncode})")
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[ValidationError(
                id="VALIDATOR_CRASH",
                severity="fatal",
                action=ErrorAction(
                    summary="System Error: The validator encountered an internal error.",
                    fix="See rule description and correct the invoice data accordingly.",
                    locations=[]
                ),
                technical_details=DebugContext(
                    raw_message="Internal validator crash",
                    raw_locations=[]
                )
            )],
            debug_log=f"STDOUT: {stdout_text}\nSTDERR: {stderr_text}",
            kosit=None  # Error case - no report available
        )
    
    if not report_path or not os.path.exists(report_path):
        stderr_text = stderr.decode('utf-8', errors='replace')
        stdout_text = stdout.decode('utf-8', errors='replace')
        logger.error(f"Session {session_id}: Report file missing")
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[ValidationError(
                id="REPORT_MISSING",
                severity="fatal",
                action=ErrorAction(
                    summary="System Error: The validation report could not be generated.",
                    fix="See rule description and correct the invoice data accordingly.",
                    locations=[]
                ),
                technical_details=DebugContext(
                    raw_message="Report missing",
                    raw_locations=[]
                )
            )],
            debug_log=f"STDOUT: {stdout_text}\nSTDERR: {stderr_text}",
            kosit=None  # Error case - no report available
        )
    
    # Parse report XML
    try:
        tree = ET.parse(report_path)
        root = tree.getroot()
    except ET.ParseError as e:
        logger.error(f"Session {session_id}: KoSIT output malformed: {e}")
        kosit_report = read_report_files(output_dir, session_id) if include_kosit_report else None
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[ValidationError(
                id="MALFORMED_REPORT",
                severity="fatal",
                action=ErrorAction(
                    summary="System Error: The validation report could not be parsed.",
                    fix="See rule description and correct the invoice data accordingly.",
                    locations=[]
                ),
                technical_details=DebugContext(
                    raw_message="KoSIT output malformed",
                    raw_locations=[]
                )
            )],
            debug_log=str(e),
            kosit=kosit_report
        )
    
    # Parse findings based on output type
    if output_type == OutputType.RAW:
        # RAW: No parsed errors, just return KoSIT report
        errors = []
        logger.info(f"Session {session_id}: RAW output - returning KoSIT report only")
    elif output_type == OutputType.T0:
        # T0: 1:1 KoSIT findings, verbatim messages, no evidence
        errors = parse_kosit_report_t0(root, session_id)
        logger.info(f"Session {session_id}: T0 output - {len(errors)} findings (1:1 with KoSIT)")
    elif output_type == OutputType.T1:
        # T1: KoSIT findings + deterministic evidence extraction
        errors = parse_kosit_report_t1(root, input_path, session_id)
        logger.info(f"Session {session_id}: T1 output - {len(errors)} findings with evidence")
        
        # Apply grouping if requested
        if grouping == GroupingMode.GROUPED:
            errors = apply_grouping(errors, session_id)
            logger.info(f"Session {session_id}: T1 grouped - reduced to {len(errors)} groups")
    else:
        errors = []
        logger.error(f"Session {session_id}: Unknown output type: {output_type}")
    
    # Read raw report files (only if requested)
    kosit_report = read_report_files(output_dir, session_id) if include_kosit_report else None
    
    # Determine status
    if errors:
        validation_status = "REJECTED"
        logger.info(f"Session {session_id}: Validation REJECTED ({len(errors)} finding(s))")
    elif output_type == OutputType.RAW:
        # For RAW type, check if KoSIT report indicates rejection
        # Look for validation failures in the report
        validation_status = determine_raw_status(root, process.returncode)
        logger.info(f"Session {session_id}: RAW status determined: {validation_status}")
    elif process.returncode != 0:
        validation_status = "ERROR"
        logger.error(f"Session {session_id}: Validator exited with error but no findings parsed")
        if output_type != OutputType.RAW:
            errors.append(ValidationError(
                id="PARSER_ERROR",
                severity="error",
                action=ErrorAction(
                    summary="The validator rejected the file, but the report could not be parsed.",
                    fix="See rule description and correct the invoice data accordingly.",
                    locations=[]
                ),
                technical_details=DebugContext(
                    raw_message="Validator exited with non-zero code but no findings parsed",
                    raw_locations=[]
                )
            ))
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


def parse_kosit_report_tier0(root: ET.Element, session_id: str) -> List[ValidationError]:
    """
    Legacy function name - calls parse_kosit_report_t0 for backward compatibility.
    """
    return parse_kosit_report_t0(root, session_id)


def parse_kosit_report_t0(root: ET.Element, session_id: str) -> List[ValidationError]:
    """
    Parse KoSIT report - T0 output (1:1 findings, verbatim messages, no evidence).
    
    Args:
        root: XML root element of KoSIT report
        session_id: Session ID for logging
        
    Returns:
        List of ValidationError objects with raw KoSIT data only (no evidence)
    """
    errors = []
    failed_items = []
    
    # Parse both KoSIT VARL and Standard SVRL formats
    for elem in root.iter():
        tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        if tag_name == 'message':
            error_code = elem.get('code')
            if error_code:
                failed_items.append({'type': 'kosit', 'elem': elem})
        elif tag_name == 'failed-assert':
            failed_items.append({'type': 'svrl', 'elem': elem})
    
    logger.debug(f"Session {session_id}: Found {len(failed_items)} raw findings (T0)")
    
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
        
        # T0: Raw KoSIT data only, no evidence
        error = ValidationError(
            id=error_code,
            severity=severity,
            action=ErrorAction(
                summary=raw_message,  # Verbatim
                fix="See rule description and correct the invoice data accordingly.",  # Generic
                locations=[raw_location] if raw_location else []
            ),
            technical_details=DebugContext(
                raw_message=raw_message,
                raw_locations=[raw_location] if raw_location else []
            ),
            evidence=None  # T0 has no evidence
        )
        errors.append(error)
    
    return errors


def parse_kosit_report_t1(root: ET.Element, input_path: str, session_id: str) -> List[ValidationError]:
    """
    Parse KoSIT report - T1 output (with deterministic evidence extraction).
    
    Args:
        root: XML root element of KoSIT report
        input_path: Path to input invoice XML for evidence extraction
        session_id: Session ID for logging
        
    Returns:
        List of ValidationError objects with evidence fields
    """
    # Start with T0 parsing
    errors = parse_kosit_report_t0(root, session_id)
    
    # Load invoice XML for evidence extraction
    try:
        invoice_tree = ET.parse(input_path)
        invoice_root = invoice_tree.getroot()
    except Exception as e:
        logger.warning(f"Session {session_id}: Could not parse invoice XML for evidence: {e}")
        return errors  # Return T0 errors without evidence
    
    # Extract evidence for each error deterministically
    for error in errors:
        evidence = extract_evidence_deterministic(error, invoice_root, session_id)
        error.evidence = evidence
    
    logger.debug(f"Session {session_id}: Added evidence to {len(errors)} findings (T1)")
    return errors


def extract_evidence_deterministic(
    error: ValidationError,
    invoice_root: ET.Element,
    session_id: str
) -> ErrorEvidence:
    """
    Extract structured evidence from invoice XML deterministically.
    
    Uses rule-based mappings to extract relevant BT fields and values.
    No LLM calls, no heuristics - purely deterministic based on XPath locations.
    
    Args:
        error: ValidationError with locations
        invoice_root: Root element of invoice XML
        session_id: Session ID for logging
        
    Returns:
        ErrorEvidence with structured fields
    """
    fields = {}
    
    # Extract line numbers from locations
    for i, location in enumerate(error.action.locations):
        if location:
            # Try to find the element and extract context
            try:
                # Remove namespace prefixes for simplified matching
                simple_path = location.split('[')[0]  # Get base path without predicates
                fields[f"location_{i}_xpath"] = location
                
                # Try to extract the element value if possible
                # This is a simplified approach - in production, you'd have more sophisticated XPath evaluation
                fields[f"location_{i}_simplified"] = simple_path
                
            except Exception as e:
                logger.debug(f"Session {session_id}: Could not extract evidence from location {location}: {e}")
    
    # Rule-specific evidence extraction based on error ID
    rule_id = error.id.upper()
    
    # Example: BR-CO-15 (Currency mismatch)
    if 'BR-CO-15' in rule_id or 'BR_CO_15' in rule_id:
        fields['rule_type'] = 'currency_mismatch'
        # Extract BT-5 (Invoice currency code)
        try:
            # Simplified XPath - in production use proper namespace handling
            for elem in invoice_root.iter():
                local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if local_name == 'DocumentCurrencyCode':
                    fields['bt_5_invoice_currency'] = elem.text
                    fields['bt_5_xpath'] = get_element_xpath(elem)
                    break
        except Exception as e:
            logger.debug(f"Session {session_id}: Error extracting BT-5: {e}")
    
    # Example: BR-CO-16 (VAT category code)
    elif 'BR-CO-16' in rule_id or 'BR_CO_16' in rule_id:
        fields['rule_type'] = 'vat_category_mismatch'
        # Extract VAT category codes
        vat_categories = []
        try:
            for elem in invoice_root.iter():
                local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if local_name == 'TaxCategory':
                    cat_code = None
                    for child in elem:
                        child_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                        if child_name == 'ID' and child.text:
                            cat_code = child.text
                            break
                    if cat_code:
                        vat_categories.append(cat_code)
            if vat_categories:
                fields['vat_categories'] = vat_categories
                fields['vat_category_count'] = len(vat_categories)
        except Exception as e:
            logger.debug(f"Session {session_id}: Error extracting VAT categories: {e}")
    
    # Generic: Try to extract values from error locations
    else:
        fields['rule_type'] = 'generic'
        # Extract values from the locations mentioned in the error
        for i, location in enumerate(error.action.locations[:3]):  # Limit to first 3
            if location:
                try:
                    # Very basic value extraction - just get text from nearby elements
                    # In production, you'd use proper XPath evaluation
                    pass
                except Exception:
                    pass
    
    return ErrorEvidence(fields=fields)


def get_element_xpath(element: ET.Element) -> str:
    """
    Get a simplified XPath for an element.
    
    Args:
        element: XML element
        
    Returns:
        Simplified XPath string
    """
    path_parts = []
    current = element
    while current is not None:
        tag = current.tag.split('}')[-1] if '}' in current.tag else current.tag
        path_parts.insert(0, tag)
        current = current.getparent() if hasattr(current, 'getparent') else None
    return '/' + '/'.join(path_parts)


def apply_grouping(errors: List[ValidationError], session_id: str) -> List[ValidationError]:
    """
    Group T1 errors by id + severity + summary message.
    
    Args:
        errors: List of ValidationError objects
        session_id: Session ID for logging
        
    Returns:
        List of grouped ValidationError objects with occurrence_count
    """
    from collections import defaultdict
    
    # Group by (id, severity, summary)
    groups = defaultdict(list)
    for error in errors:
        key = (error.id, error.severity, error.action.summary)
        groups[key].append(error)
    
    logger.debug(f"Session {session_id}: Grouping {len(errors)} errors into {len(groups)} groups")
    
    # Create grouped errors
    grouped_errors = []
    for (error_id, severity, summary), group in groups.items():
        # Merge locations from all occurrences
        all_locations = []
        all_raw_locations = []
        occurrences = []
        
        for err in group:
            all_locations.extend(err.action.locations)
            all_raw_locations.extend(err.technical_details.raw_locations)
            # Store occurrence details
            occurrence = {
                'locations': err.action.locations,
                'evidence': err.evidence.fields if err.evidence else {}
            }
            occurrences.append(occurrence)
        
        # Create grouped error (use first error as template)
        first_error = group[0]
        grouped_error = ValidationError(
            id=error_id,
            severity=severity,
            action=ErrorAction(
                summary=summary,  # Keep verbatim message
                fix=first_error.action.fix,
                locations=list(dict.fromkeys(all_locations))  # Deduplicate while preserving order
            ),
            technical_details=DebugContext(
                raw_message=first_error.technical_details.raw_message,
                raw_locations=list(dict.fromkeys(all_raw_locations))
            ),
            evidence=first_error.evidence,  # Keep first occurrence's evidence as representative
            occurrence_count=len(group),
            occurrences=occurrences
        )
        grouped_errors.append(grouped_error)
    
    return grouped_errors


def determine_raw_status(root: ET.Element, return_code: int) -> str:
    """
    Determine validation status from KoSIT report for RAW output type.
    
    Args:
        root: XML root element of KoSIT report
        return_code: Process return code
        
    Returns:
        Status string: PASSED, REJECTED, or ERROR
    """
    # Look for acceptRecommendation or similar in KoSIT report
    try:
        for elem in root.iter():
            tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag_name == 'acceptRecommendation':
                if elem.text and elem.text.strip().upper() == 'REJECT':
                    return "REJECTED"
                elif elem.text and elem.text.strip().upper() == 'ACCEPT':
                    return "PASSED"
            elif tag_name == 'message':
                # If there are any error messages, it's rejected
                return "REJECTED"
            elif tag_name == 'failed-assert':
                return "REJECTED"
    except Exception:
        pass
    
    # Fall back to return code
    if return_code != 0:
        return "ERROR"
    
    return "PASSED"


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
                    logger.debug(f"Session {session_id}: HTML report not available: {e}")
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
