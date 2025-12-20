# InvoiceGuard - Peppol BIS 3.0 Pre-flight Validator

A deterministic, fail-safe API wrapping the KoSIT Validator v1.5.0 for Peppol BIS 3.0 invoice validation.

## Features

- **Deterministic Validation**: Uses KoSIT Validator 1.5.0 with Peppol rules release-3.0.18
- **Fail-Safe Design**: Strict error handling with `set -euo pipefail` in all build steps
- **Security**: 10MB file size limit, chunked streaming, input XML validation
- **Concurrency Control**: Single validation at a time using asyncio.Semaphore
- **Comprehensive Error Handling**: Pre-flight checks, timeout protection, malformed output detection

## Architecture

```
InvoiceGuard
├── Dockerfile          # Multi-stage build with strict assertions
├── main.py            # FastAPI application with validation logic
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

## Build & Run

### Build Docker Image

```bash
docker build -t invoiceguard:latest .
```

### Run Container

```bash
docker run -d -p 8080:8080 --name invoiceguard invoiceguard:latest
```

### Health Check

```bash
curl http://localhost:8080/health
```

## API Usage

### Validate Invoice

**Endpoint**: `POST /validate`

**Request**:
```bash
curl -X POST http://localhost:8080/validate \
  -F "file=@invoice.xml"
```

**Response**:
```json
{
  "status": "PASSED",
  "meta": {
    "engine": "KoSIT 1.5.0",
    "rules_tag": "release-3.0.18",
    "commit": "abc123..."
  },
  "errors": [],
  "debug_log": null
}
```

### Status Codes

- `PASSED`: Invoice is valid
- `REJECTED`: Invoice has validation errors
- `ERROR`: System error (invalid XML, timeout, crash)

### HTTP Status Codes

- `200`: Validation completed (check `status` field)
- `400`: Invalid XML input
- `413`: File too large (>10MB)
- `500`: Internal validator error

## Testing

### Test with Built-in Files

```bash
# Test UBL invoice
docker exec invoiceguard curl -X POST http://localhost:8080/validate \
  -F "file=@/app/test_ubl.xml"

# Test CII invoice
docker exec invoiceguard curl -X POST http://localhost:8080/validate \
  -F "file=@/app/test_cii.xml"
```

### Test Error Handling

```bash
# Test invalid XML (HTTP 400)
echo "not xml" > invalid.txt
curl -X POST http://localhost:8080/validate -F "file=@invalid.txt"

# Test file size limit (HTTP 413)
dd if=/dev/zero of=large.xml bs=1M count=11
curl -X POST http://localhost:8080/validate -F "file=@large.xml"
```

## Configuration

### Validator Version
- **KoSIT Validator**: v1.5.0
- **Source**: https://github.com/itplr-kosit/validator/releases/tag/v1.5.0

### Peppol Rules
- **Repository**: https://projekte.kosit.org/peppol/validator-configuration-bis.git
- **Tag**: release-3.0.18 (November 2024)

### Test Data
- **UBL**: First file from `test-files/good/ubl/*.xml`
- **CII**: First file from `test-files/good/cii/*.xml`

## Build Traceability

The Docker build includes:
- SHA256 hash of validator JAR
- Git commit hash of rules repository
- Selected test file paths
- Directory structure validation

All artifacts are logged during build and available at runtime.

## Security

- **Input Validation**: XML parsing before Java execution
- **Size Limit**: 10MB maximum file size
- **Timeout**: 30-second validation timeout
- **Resource Cleanup**: Temporary files cleaned up in finally block
- **Concurrency**: Single validation at a time

## Development

### Local Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (requires Java 17 and rules setup)
uvicorn main:app --reload --port 8080
```

## License

Internal project - All rights reserved
