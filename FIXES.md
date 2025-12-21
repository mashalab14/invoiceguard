# 🔧 KoSIT Validator Fixes Applied

## Problem Identified
The runtime validation was failing with "Report missing" error due to subprocess execution issues in `main.py`.

## Root Cause Analysis
1. **Missing Working Directory**: The subprocess didn't specify `cwd="/app"`, so the Java process couldn't find the validator JAR's `lib` folder
2. **Output Directory Not Created**: The KoSIT validator expects the output directory to exist before execution
3. **Insufficient Debugging**: Limited logging made it hard to diagnose path issues

## Fixes Applied ✅

### 1. Fixed Subprocess Working Directory
```python
# BEFORE
process = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE
)

# AFTER
process = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd="/app"  # Set working directory so JAR can find lib folder
)
```

### 2. Explicit Output Directory Creation
```python
# BEFORE
session_dir = os.path.dirname(input_path)
output_dir = os.path.join(session_dir, "output")

# AFTER
session_dir = os.path.dirname(input_path)
output_dir = os.path.join(session_dir, "output")

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)
logger.debug(f"Session {session_id}: Created output directory: {output_dir}")
```

### 3. Enhanced Debug Logging
- Changed log level from `INFO` to `DEBUG`
- Added command execution details
- Added file listing when report is missing
- Capture both stdout and stderr in error responses

### 4. Better Error Diagnostics
```python
# Enhanced error reporting with stdout/stderr
if not os.path.exists(report_path):
    # List files in output directory for debugging
    if os.path.exists(output_dir):
        output_files = os.listdir(output_dir)
        logger.error(f"Session {session_id}: Output directory exists but report missing. Files: {output_files}")
    else:
        logger.error(f"Session {session_id}: Output directory does not exist: {output_dir}")
    
    stderr_text = stderr.decode('utf-8', errors='replace')
    stdout_text = stdout.decode('utf-8', errors='replace')
    # ... return with detailed debug_log
```

## Testing the Fixes 🧪

### Quick Test (Recommended)
```bash
# Build with fixes
docker build -t invoiceguard:fixed .

# Run container
docker run -d -p 8080:8080 --name invoiceguard-test invoiceguard:fixed

# Watch logs for debugging
docker logs -f invoiceguard-test

# Test validation (in another terminal)
docker exec invoiceguard-test curl -X POST http://localhost:8080/validate -F "file=@/app/test_ubl.xml"
```

### Full Test Suite
```bash
# Run comprehensive tests
./test.sh
```

### Debug Logs to Watch For ✅
- `[DEBUG] Session XXX: Command: java -jar /app/validator.jar ...`
- `[DEBUG] Session XXX: Working directory: /app`
- `[DEBUG] Session XXX: Created output directory: ...`
- `[DEBUG] Session XXX: Looking for report at: ...`

### Success Indicators ✅
- No "Report missing" errors
- Validation returns `PASSED` for test files
- Clean subprocess execution

## Expected Resolution
These fixes should resolve the "Report missing" error by ensuring:

1. ✅ **Correct Working Directory**: Java process runs in `/app` and finds the validator's `lib` folder
2. ✅ **Output Directory Exists**: Directory is created before validation starts
3. ✅ **Proper Path Resolution**: All file paths are correctly resolved relative to `/app`
4. ✅ **Better Debugging**: Detailed logs help identify any remaining issues

## Fallback Troubleshooting
If issues persist after these fixes, check the debug logs for:
- `[ERROR] Output directory exists but report missing. Files: [...]` - Shows what files were actually created
- `[DEBUG] STDOUT: ...` - KoSIT validator output
- `[DEBUG] STDERR: ...` - Any Java errors

## Commit Status ✅
- **Committed**: `4aa2d34` - Fix KoSIT validator subprocess execution and report path issues
- **Pushed**: GitHub repository updated
- **Ready**: For testing and validation

---

**Next Steps**: Build and test the Docker container to verify the fixes resolve the validation issues.
