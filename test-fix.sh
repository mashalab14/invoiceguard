#!/bin/bash
# Quick test script to verify the report filename fix
set -euo pipefail

CONTAINER_NAME="invoiceguard"

echo "🧪 Testing Report File Detection Fix"
echo "=================================="

# Check if container is running
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "❌ Container '$CONTAINER_NAME' not running"
    echo "Start with: ./start.sh"
    exit 1
fi

echo "✅ Container is running"

# Test validation and capture detailed output
echo ""
echo "🔍 Testing validation with debug output..."
echo ""

# Get the response with validation
RESPONSE=$(docker exec "$CONTAINER_NAME" curl -s -X POST http://localhost:8080/validate -F "file=@/app/test_ubl.xml" 2>/dev/null)

echo "Response:"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"

echo ""
echo "📋 Recent container logs (last 20 lines):"
echo "=========================================="
docker logs --tail=20 "$CONTAINER_NAME" | grep -E "\[DEBUG\]|\[ERROR\]|\[INFO\].*Session" || echo "No relevant logs found"

echo ""
if echo "$RESPONSE" | grep -q '"status":"PASSED"' || echo "$RESPONSE" | grep -q '"status": "PASSED"'; then
    echo "✅ SUCCESS: Validation completed with PASSED status"
    echo "🎉 Report file detection fix appears to be working!"
elif echo "$RESPONSE" | grep -q '"status":"ERROR"' || echo "$RESPONSE" | grep -q '"status": "ERROR"'; then
    echo "❌ ERROR: Validation failed"
    echo ""
    echo "Check logs for specific error details:"
    echo "  ./logs.sh errors"
    echo ""
    echo "Look for these patterns in logs:"
    echo "  - 'Files in output directory: [...]' - Shows what files were created"
    echo "  - 'Found report file: ...' - Shows which file was detected"
    echo "  - 'No valid report file found' - Indicates the fix didn't work"
else
    echo "⚠️  UNEXPECTED: Response format not recognized"
    echo "Raw response: $RESPONSE"
fi

echo ""
echo "💡 To debug further:"
echo "   ./logs.sh debug    # Show debug messages"
echo "   ./logs.sh follow   # Watch real-time logs"
