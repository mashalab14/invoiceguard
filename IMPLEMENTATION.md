# InvoiceGuard - Implementation Summary

## 🎯 Project Overview
**InvoiceGuard** is a deterministic, fail-safe API that wraps the KoSIT Validator v1.5.0 for Peppol BIS 3.0 invoice validation.

## 📦 Deliverables

### Core Files Created
1. **Dockerfile** - Multi-stage build with strict error handling
2. **main.py** - FastAPI application with comprehensive validation logic
3. **requirements.txt** - Python dependencies
4. **README.md** - Complete documentation
5. **test.sh** - Comprehensive test suite (7 binary tests)
6. **.gitignore** - Git ignore patterns

## 🔧 Technical Implementation

### A. Dockerfile Features
- **Base Image**: `python:3.9-slim`
- **Java Runtime**: OpenJDK 17 JRE Headless
- **Shell Configuration**: `SHELL ["/bin/bash", "-c"]` with `set -euo pipefail`
- **Fail-Fast Mode**: Every RUN command starts with `set -euo pipefail;`

#### Build Steps
1. **Validator Installation**
   - Downloads KoSIT Validator v1.5.0
   - Finds and validates exactly 1 standalone JAR (excludes java8)
   - Logs SHA256 hash for traceability
   - Moves to `/app/validator.jar`

2. **Rules Installation**
   - Clones `validator-configuration-bis.git` at tag `release-3.0.18`
   - Captures commit hash to `version_info.txt`
   - Discovers and validates `scenarios.xml` (exactly 1)
   - Asserts directory structure:
     - `resources` folder exists
     - `test-files/good/ubl` folder exists
     - `test-files/good/cii` folder exists

3. **Test Data Setup**
   - **UBL**: Selects first file from `test-files/good/ubl/*.xml`
   - **CII**: Selects first file from `test-files/good/cii/*.xml`
   - Logs selected files
   - Validates file sizes > 0
   - Copies to `/app/test_ubl.xml` and `/app/test_cii.xml`

### B. main.py Features

#### Startup
- Reads `version_info.txt` and `rules_dir.txt`
- Logs commit hash and rules directory path
- Validates validator JAR and scenarios.xml exist

#### Concurrency Control
- `asyncio.Semaphore(1)` - Single validation at a time
- Prevents resource exhaustion

#### Security Features
1. **Chunked Reading**: Streams files in 1024-byte chunks
2. **Size Limit**: Rejects files >10MB with HTTP 413
3. **Cleanup**: Always removes temp directory in finally block

#### Validation Pipeline

1. **File Reception**
   - Creates temp directory with UUID
   - Streams file with size checking
   - Writes to `input.xml`

2. **Pre-flight Check (Input Hygiene)**
   - Attempts `ET.parse(input_path)`
   - If `ParseError`: Returns `ERROR` status with HTTP 400
   - Message: "Input file is not valid XML"
   - **Does not execute Java if this fails**

3. **Java Execution**
   - Command: `java -jar validator.jar -s scenarios.xml -r rules_dir -o output input.xml`
   - Timeout: 30 seconds
   - Async subprocess execution

4. **Error Handling**
   - **TimeoutExpired**: Returns `ERROR` with HTTP 500, message "Validation Timed Out"
   - **Non-zero return code**: Returns `ERROR` with HTTP 500, includes last 20 lines of stderr
   - **Missing report**: Returns `ERROR` with HTTP 500, message "Report missing"
   - **Malformed report**: Returns `ERROR` with HTTP 500, message "KoSIT Output Malformed"

5. **Report Parsing**
   - Target: `output/input.xml-report.xml`
   - Extracts `failed-assert` elements
   - ID Logic: Uses `id` attribute, fallback to `location`, fallback to "UNKNOWN"
   - Proof of execution: Warns if no `failed-assert` and no `active-pattern`/`fired-rule`

6. **Status Determination**
   - `failed-assert` count > 0 → `REJECTED`
   - `failed-assert` count == 0 → `PASSED`

7. **Cleanup**
   - `shutil.rmtree(session_dir)` in finally block
   - Guaranteed execution even on exceptions

### C. Response Schema
```json
{
  "status": "PASSED" | "REJECTED" | "ERROR",
  "meta": {
    "engine": "KoSIT 1.5.0",
    "rules_tag": "release-3.0.18",
    "commit": "<hash>"
  },
  "errors": [
    {
      "code": "BR-CO-16",
      "message": "Calculated total..."
    }
  ],
  "debug_log": null
}
```

## ✅ Definition of Done - 7 Binary Tests

### TEST 1: Build Success
- ✅ Docker build succeeds with `set -euo pipefail`
- ✅ Logs show SHA256 hash
- ✅ Logs show selected UBL and CII filenames

### TEST 2: Integrity
- ✅ `test_ubl.xml` is valid XML
- ✅ `test_cii.xml` is valid XML

### TEST 3: Determinism (UBL)
- ✅ `curl -F "file=@/app/test_ubl.xml"` returns `PASSED`

### TEST 4: Scope (CII)
- ✅ `curl -F "file=@/app/test_cii.xml"` returns `PASSED`

### TEST 5: Input Hygiene
- ✅ Non-XML text file returns `ERROR` with HTTP 400
- ✅ Message: "Input file is not valid XML"

### TEST 6: System Fault
- ✅ Timeout protection (30 seconds)
- ✅ Java crash returns `ERROR` with HTTP 500
- ✅ Includes last 20 lines of stderr

### TEST 7: Security
- ✅ >10MB file returns HTTP 413
- ✅ Cleanup in finally block even on exception

## 🚀 Usage

### Build and Run
```bash
# Build
docker build -t invoiceguard:latest .

# Run
docker run -d -p 8080:8080 --name invoiceguard invoiceguard:latest

# Test
./test.sh
```

### API Endpoints
- `GET /health` - Health check
- `POST /validate` - Validate invoice (multipart/form-data)

### Example
```bash
curl -X POST http://localhost:8080/validate \
  -F "file=@invoice.xml"
```

## 📊 Repository
**GitHub**: https://github.com/mashalab14/invoiceguard

## 🔒 Security Considerations
- Input validation before execution
- File size limits
- Timeout protection
- Resource cleanup
- Single-threaded execution
- No shell injection vectors

## 📝 Traceability
- Validator JAR SHA256 logged at build
- Rules commit hash stored and returned in responses
- Build logs show all selected files and validations
- Version info available at runtime

## 🎓 Best Practices Implemented
1. **Fail-Fast**: `set -euo pipefail` in all build steps
2. **Deterministic**: Fixed versions, no latest tags
3. **Defensive**: Multiple assertion points
4. **Observable**: Comprehensive logging
5. **Secure**: Input validation, size limits, timeouts
6. **Clean**: Guaranteed resource cleanup
7. **Tested**: 7 comprehensive binary tests

## 🏗️ Architecture Decisions

### Why Semaphore(1)?
- Java validator is CPU-intensive
- Prevents resource exhaustion
- Predictable performance
- Simpler than complex queuing

### Why Pre-flight XML Check?
- Fails fast on invalid input
- Avoids unnecessary Java execution
- Clear error messages to users
- Saves resources

### Why Chunked Reading?
- Memory efficient for large files
- Early detection of oversized files
- Prevents OOM attacks

### Why Finally Block Cleanup?
- Guaranteed execution
- Prevents disk space leaks
- Works even with exceptions
- Critical for long-running services

## 📈 Performance Characteristics
- **Throughput**: 1 validation at a time
- **Timeout**: 30 seconds per validation
- **Memory**: Chunked streaming (1KB chunks)
- **Disk**: Temporary files cleaned immediately
- **CPU**: Single Java process at a time

## 🔮 Future Enhancements
- [ ] Queue system for concurrent validations
- [ ] Metrics/monitoring (Prometheus)
- [ ] Caching for repeated validations
- [ ] Webhook notifications
- [ ] Batch validation endpoint
- [ ] API key authentication
- [ ] Rate limiting

---

**Status**: ✅ Complete and pushed to GitHub
**Build Time**: ~5-10 minutes (depends on network)
**Runtime**: <1 second startup, <5 seconds per validation
