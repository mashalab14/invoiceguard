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
from pydantic import BaseModel

# Enhanced imports
from diagnostics.pipeline import DiagnosticsPipeline

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


class ValidationError(BaseModel):
    id: str  # Renamed from 'code' to match pipeline expectations
    message: str
    location: Optional[str] = None
    locations: Optional[List[str]] = None  # For storing multiple XPath locations when deduplicated
    severity: Optional[str] = None
    humanized_message: Optional[str] = None
    suppressed: Optional[bool] = None


class ValidationMeta(BaseModel):
    engine: str
    rules_tag: str
    commit: str


class ValidationResponse(BaseModel):
    status: str  # PASSED, REJECTED, ERROR
    meta: ValidationMeta
    errors: List[ValidationError]
    debug_log: Optional[str] = None


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


@app.post("/validate", response_model=ValidationResponse)
async def validate_invoice(file: UploadFile = File(...)):
    """
    Validate a Peppol BIS 3.0 invoice against KoSIT rules.
    
    Returns:
        ValidationResponse with status PASSED, REJECTED, or ERROR
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
            result = await validate_file(session_id, input_path)
            return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session {session_id}: Unexpected error: {e}")
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[ValidationError(
                id="INTERNAL_ERROR",
                message=f"Unexpected error: {str(e)}"
            )],
            debug_log=None
        )
    finally:
        # Always cleanup temp directory
        if os.path.exists(session_dir):
            try:
                shutil.rmtree(session_dir)
                logger.debug(f"Session {session_id}: Cleaned up temp directory")
            except Exception as e:
                logger.error(f"Session {session_id}: Failed to cleanup: {e}")


def _deduplicate_errors(errors: List[ValidationError], session_id: str) -> List[ValidationError]:
    """
    Deduplicate errors by grouping repeated error IDs.
    
    For errors with the same ID, keep the first instance and:
    - Append "(Repeated X times)" to the message
    - Store all XPath locations in the locations field
    
    Args:
        errors: List of validation errors
        session_id: Session ID for logging
        
    Returns:
        Deduplicated list of errors
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
    
    # Build deduplicated list
    deduplicated = []
    total_before = len(errors)
    
    for error_id, group in error_groups.items():
        if len(group) == 1:
            # Single occurrence, no deduplication needed
            deduplicated.append(group[0])
        else:
            # Multiple occurrences, deduplicate
            first_error = group[0]
            
            # Collect all unique locations
            all_locations = []
            for err in group:
                if err.location and err.location not in all_locations:
                    all_locations.append(err.location)
            
            # Update the first error with repeat count and locations
            repeat_count = len(group)
            updated_message = f"{first_error.message} (Repeated {repeat_count} times)"
            
            deduplicated.append(ValidationError(
                id=first_error.id,
                message=updated_message,
                location=first_error.location,  # Keep first location for compatibility
                locations=all_locations,  # Store all locations
                severity=first_error.severity,
                humanized_message=first_error.humanized_message,
                suppressed=first_error.suppressed
            ))
            
            logger.debug(f"Session {session_id}: Deduplicated {repeat_count} instances of {error_id}")
    
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
            # Replace humanized_message with clean, short suppression note
            error.humanized_message = "Suppressed: Cascade error from Currency Mismatch (R051)."
            # Also update the main message
            suppression_note = " (Suppressed: Root cause is likely the Currency Mismatch R051)."
            error.message = error.message + suppression_note
            suppressed_count += 1
    
    if suppressed_count > 0:
        logger.info(f"Session {session_id}: Cross-error suppression - suppressed {suppressed_count} BR-CO-15 error(s) due to R051 currency mismatch")
    
    return errors


async def validate_file(session_id: str, input_path: str) -> ValidationResponse:
    """
    Execute validation logic for a single file.
    
    Args:
        session_id: Unique session identifier
        input_path: Path to input XML file
        
    Returns:
        ValidationResponse with results
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
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[ValidationError(
                id="INVALID_XML",
                message="Input file is not valid XML"
            )],
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
            return ValidationResponse(
                status="ERROR",
                meta=ValidationMeta(
                    engine="KoSIT 1.5.0",
                    rules_tag="release-3.0.18",
                    commit=config["commit_hash"]
                ),
                errors=[ValidationError(
                    id="TIMEOUT",
                    message="Validation timed out"
                )],
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
            return ValidationResponse(
                status="ERROR",
                meta=ValidationMeta(
                    engine="KoSIT 1.5.0",
                    rules_tag="release-3.0.18",
                    commit=config["commit_hash"]
                ),
                errors=[ValidationError(id="VALIDATOR_CRASH", message="Internal validator crash")],
                debug_log=combined_log[-4000:]
            )
        # 3. If we are here, we either have a report OR returncode was 0.
        # Proceed to parse the report (even if returncode was 1).
        
        logger.info(f"Session {session_id}: Validator completed successfully")
    
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
                message=f"Failed to execute validator: {str(e)}"
            )],
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
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[ValidationError(
                id="REPORT_MISSING",
                message="Report missing"
            )],
            debug_log=f"STDOUT: {stdout_text}\nSTDERR: {stderr_text}"
        )
    
    # Parse report XML
    logger.debug(f"Session {session_id}: Parsing report file: {report_path}")
    try:
        tree = ET.parse(report_path)
        root = tree.getroot()
    except ET.ParseError as e:
        logger.error(f"Session {session_id}: KoSIT output malformed: {e}")
        return ValidationResponse(
            status="ERROR",
            meta=ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=config["commit_hash"]
            ),
            errors=[ValidationError(
                id="MALFORMED_REPORT",
                message="KoSIT output malformed"
            )],
            debug_log=str(e)
        )
    
    # ---------------------------------------------------------
    # NEW: Dual-Mode Parser (KoSIT VARL + Standard SVRL)
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

        # Add to final list
        errors.append(ValidationError(
            id=error_code,
            message=message,
            location=location,
            severity=severity,
            humanized_message=None,
            suppressed=False
        ))
            
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
                    "id": error.id,
                    "message": error.message,
                    "location": error.location or "",
                    "severity": error.severity or "error"
                })
            
            # Run humanization pipeline
            humanization_result = diagnostics_pipeline.run(kosit_errors, invoice_xml)
            
            # Update errors with humanization results
            enhanced_errors = []
            for processed_error in humanization_result.processed_errors:
                enhanced_errors.append(ValidationError(
                    id=processed_error["id"],
                    message=processed_error["message"],
                    location=processed_error.get("location", ""),
                    severity=processed_error.get("severity", "error"),
                    humanized_message=processed_error.get("humanized_message"),
                    suppressed=processed_error.get("suppressed", False)
                ))
            
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
        
        errors.append(ValidationError(
            id="PARSING_MISMATCH",
            message="The validator rejected the file, but the report could not be parsed. Check the debug log.",
            severity="fatal",
            humanized_message="System Error: The validator rejected this file, but we could not read the error report."
        ))
        
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
