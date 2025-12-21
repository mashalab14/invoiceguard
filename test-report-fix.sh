#!/bin/bash
# Test script to verify the report file detection fix
set -euo pipefail

echo "================================================"
echo "Testing Report File Detection Fix"
echo "================================================"

CONTAINER_NAME="invoiceguard-test-fix"
IMAGE_NAME="invoiceguard:test-fix"

# Cleanup function
cleanup() {
    echo "Cleaning up..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
}
trap cleanup EXIT

# Build and test
echo "Building test image..."
docker build -t "$IMAGE_NAME" . > /dev/null

echo "Starting container..."
docker run -d -p 8081:8080 --name "$CONTAINER_NAME" "$IMAGE_NAME"

# Wait for startup
echo "Waiting for service..."
for i in {1..20}; do
    if curl -s http://localhost:8081/health > /dev/null 2>&1; then
        echo "✅ Service ready"
        break
    fi
    sleep 1
    if [ $i -eq 20 ]; then
        echo "❌ Service failed to start"
        docker logs "$CONTAINER_NAME"
        exit 1
    fi
done

# Test validation and check logs for report file detection
echo "Testing validation..."
RESPONSE=$(docker exec "$CONTAINER_NAME" curl -s -X POST http://localhost:8080/validate -F "file=@/app/test_ubl.xml")

echo "Checking logs for report file detection..."
LOGS=$(docker logs "$CONTAINER_NAME" 2>&1)

if echo "$LOGS" | grep -q "Found KoSIT report file: input-report.xml"; then
    echo "✅ SUCCESS: Code correctly detected 'input-report.xml'"
elif echo "$LOGS" | grep -q "Found.*report file:"; then
    echo "✅ PARTIAL: Code found a report file"
    echo "$LOGS" | grep "Found.*report file:"
else
    echo "❌ FAILED: No report file detection found in logs"
    echo "Recent logs:"
    echo "$LOGS" | tail -20
fi

# Check validation result
if echo "$RESPONSE" | grep -q '"status":"PASSED"'; then
    echo "✅ SUCCESS: Validation returned PASSED"
elif echo "$RESPONSE" | grep -q '"status":"REJECTED"'; then
    echo "✅ WORKING: Validation returned REJECTED (file processed)"
elif echo "$RESPONSE" | grep -q '"status":"ERROR"'; then
    echo "❌ FAILED: Validation returned ERROR"
    echo "Response: $RESPONSE"
else
    echo "❌ FAILED: Unexpected response"
    echo "Response: $RESPONSE"
fi

echo ""
echo "Test completed!"
