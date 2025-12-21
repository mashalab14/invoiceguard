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

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG for better troubleshooting
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Global configuration
VALIDATOR_JAR = "/app/validator.jar"
VERSION_INFO_FILE = "/app/version_info.txt"
RULES_DIR_FILE = "/app/rules_dir.txt"
TEMP_DIR = "/app/temp"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
VALIDATION_TIMEOUT = 30  # seconds

# Concurrency control
validation_semaphore = asyncio.Semaphore(1)

# Application
app = FastAPI(title="InvoiceGuard", version="1.0.0")


class ValidationError(BaseModel):
    code: str
    message: str


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
        
        # Verify files exist
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
                code="INTERNAL_ERROR",
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
                code="INVALID_XML",
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
                    code="TIMEOUT",
                    message="Validation timed out"
                )],
                debug_log=None
            )
        
        # Check return code
        if process.returncode != 0:
            stderr_text = stderr.decode('utf-8', errors='replace')
            stderr_lines = stderr_text.strip().split('\n')
            last_20_lines = '\n'.join(stderr_lines[-20:])
            
            logger.error(f"Session {session_id}: Validator crashed (exit code {process.returncode})")
            return ValidationResponse(
                status="ERROR",
                meta=ValidationMeta(
                    engine="KoSIT 1.5.0",
                    rules_tag="release-3.0.18",
                    commit=config["commit_hash"]
                ),
                errors=[ValidationError(
                    code="VALIDATOR_CRASH",
                    message="Internal validator crash"
                )],
                debug_log=last_20_lines
            )
        
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
                code="EXECUTION_ERROR",
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
                code="REPORT_MISSING",
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
                code="MALFORMED_REPORT",
                message="KoSIT output malformed"
            )],
            debug_log=str(e)
        )
    
    # Extract validation errors
    errors = []
    
    # Define namespace (Schematron typically uses svrl namespace)
    namespaces = {
        'svrl': 'http://purl.oclc.org/dsdl/svrl',
        'xsl': 'http://www.w3.org/1999/XSL/Transform'
    }
    
    # Find all failed-assert elements
    failed_asserts = root.findall('.//svrl:failed-assert', namespaces)
    
    # Also try without namespace if not found
    if not failed_asserts:
        failed_asserts = root.findall('.//failed-assert')
    
    for failed_assert in failed_asserts:
        # Extract error code (id attribute or location attribute or UNKNOWN)
        error_code = failed_assert.get('id')
        if not error_code:
            error_code = failed_assert.get('location')
        if not error_code:
            error_code = "UNKNOWN"
        
        # Extract message (text element)
        text_elem = failed_assert.find('svrl:text', namespaces)
        if text_elem is None:
            text_elem = failed_assert.find('text')
        
        message = text_elem.text if text_elem is not None and text_elem.text else "Validation failed"
        
        errors.append(ValidationError(
            code=error_code,
            message=message.strip()
        ))
    
    # Proof of execution check
    if len(failed_asserts) == 0:
        # Check for active-pattern or fired-rule elements as proof of execution
        active_patterns = root.findall('.//svrl:active-pattern', namespaces)
        fired_rules = root.findall('.//svrl:fired-rule', namespaces)
        
        if not active_patterns:
            active_patterns = root.findall('.//active-pattern')
        if not fired_rules:
            fired_rules = root.findall('.//fired-rule')
        
        if not active_patterns and not fired_rules:
            logger.warning(f"Session {session_id}: No failed-assert and no execution proof found")
    
    # Determine status
    if errors:
        validation_status = "REJECTED"
        logger.info(f"Session {session_id}: Validation REJECTED ({len(errors)} error(s))")
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
        debug_log=None
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
