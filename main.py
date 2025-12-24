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

from fastapi import FastAPI, File, UploadFile, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

# Tier 0 imports - raw KoSIT only
from diagnostics.models import ValidationError, ErrorAction, DebugContext, OutputMode, KoSITReport

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
    status: str  # PASSED, REJECTED, ERROR
    meta: ValidationMeta
    errors: List[ValidationError]
    debug_log: Optional[str] = None
    kosit: Optional[KoSITReport] = None  # Raw KoSIT report


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
        "message": "InvoiceGuard API - Tier 0 (Raw KoSIT Only)",
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
    
    Tier 0 Mode: Returns raw KoSIT findings with no enrichment.
    
    Args:
        file: Invoice XML file to validate
        mode: Output mode (only TIER0 supported)
    
    Returns:
        JSONResponse with raw KoSIT validation results and report
    """
    if mode != OutputMode.TIER0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only TIER0 mode is supported. Enrichment has been removed."
        )
    
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
            result = await validate_file(session_id, input_path)
            return JSONResponse(content=jsonable_encoder(result.dict()))
    
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
            debug_log=str(e)
        )
        return JSONResponse(content=jsonable_encoder(error_response.dict()))
    finally:
        if os.path.exists(session_dir):
            try:
                shutil.rmtree(session_dir)
                logger.debug(f"Session {session_id}: Cleaned up temp directory")
            except Exception as e:
                logger.error(f"Session {session_id}: Failed to cleanup: {e}")


async def validate_file(session_id: str, input_path: str) -> ValidationResponse:
    """
    Execute validation logic for a single file (Tier 0 only).
    
    Args:
        session_id: Unique session identifier
        input_path: Path to input XML file
        
    Returns:
        ValidationResponse with raw KoSIT results
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
                debug_log=None
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
            debug_log=None
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
            debug_log=f"STDOUT: {stdout_text}\nSTDERR: {stderr_text}"
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
            debug_log=f"STDOUT: {stdout_text}\nSTDERR: {stderr_text}"
        )
    
    # Parse report XML
    try:
        tree = ET.parse(report_path)
        root = tree.getroot()
    except ET.ParseError as e:
        logger.error(f"Session {session_id}: KoSIT output malformed: {e}")
        kosit_report = read_report_files(output_dir, session_id)
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
    
    # Parse raw KoSIT findings (Tier 0 only)
    errors = parse_kosit_report_tier0(root, session_id)
    
    # Read raw report files
    kosit_report = read_report_files(output_dir, session_id)
    
    # Determine status
    if errors:
        validation_status = "REJECTED"
        logger.info(f"Session {session_id}: Validation REJECTED ({len(errors)} finding(s))")
    elif process.returncode != 0:
        validation_status = "ERROR"
        logger.error(f"Session {session_id}: Validator exited with error but no findings parsed")
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
    Parse KoSIT report - raw findings only, no enrichment.
    
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
        
        if tag_name == 'message':
            error_code = elem.get('code')
            if error_code:
                failed_items.append({'type': 'kosit', 'elem': elem})
        elif tag_name == 'failed-assert':
            failed_items.append({'type': 'svrl', 'elem': elem})
    
    logger.debug(f"Session {session_id}: Found {len(failed_items)} raw findings")
    
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
        
        # Tier 0: Raw KoSIT data only
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
            )
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
