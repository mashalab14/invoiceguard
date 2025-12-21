#!/bin/bash
# Debug script for testing KoSIT validator fixes

echo "=== InvoiceGuard Debug Info ==="
echo ""

echo "Key fixes applied to main.py:"
echo "1. Added cwd='/app' to subprocess call"
echo "2. Added explicit output directory creation"
echo "3. Enhanced debug logging"
echo "4. Added stdout/stderr capture in error messages"
echo ""

echo "Expected behavior after fixes:"
echo "- Java process runs in /app directory"
echo "- Can find validator JAR lib folder"
echo "- Output directory is created before validation"
echo "- Detailed logging shows command execution"
echo ""

echo "To test the fixes:"
echo "1. docker build -t invoiceguard:debug ."
echo "2. docker run -d -p 8080:8080 --name invoiceguard-debug invoiceguard:debug"
echo "3. docker logs -f invoiceguard-debug  # Watch logs"
echo "4. Test validation:"
echo "   docker exec invoiceguard-debug curl -X POST http://localhost:8080/validate -F \"file=@/app/test_ubl.xml\""
echo ""

echo "Debug log lines to look for:"
echo "- [DEBUG] Session XXX: Command: java -jar /app/validator.jar ..."
echo "- [DEBUG] Session XXX: Working directory: /app"
echo "- [DEBUG] Session XXX: Output directory: /app/temp/XXX/output"
echo "- [DEBUG] Session XXX: Created output directory: ..."
echo "- [DEBUG] Session XXX: Looking for report at: ..."
echo ""

echo "If report is still missing, check:"
echo "- [ERROR] Output directory exists but report missing. Files: [...]"
echo "- [DEBUG] STDOUT: ... (validator output)"
echo "- [DEBUG] STDERR: ... (validator errors)"
