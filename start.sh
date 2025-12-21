#!/bin/bash
# Enhanced QuickStart Script for InvoiceGuard with Debug Support
set -euo pipefail

echo "================================================"
echo "InvoiceGuard - Enhanced Quick Start with Debugging"
echo "================================================"

# Configuration
IMAGE_NAME="invoiceguard:latest"
CONTAINER_NAME="invoiceguard"
PORT=8080
DEBUG_MODE=${1:-false}

# Check Docker availability
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker Desktop and ensure it's in your PATH."
    echo "   Download from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker daemon not running. Please start Docker Desktop."
    exit 1
fi

echo "✅ Docker is available and running"

# Cleanup function
cleanup() {
    echo "🧹 Cleaning up..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
}
trap cleanup EXIT

# Clean up existing container
cleanup

# Build image
echo ""
echo "🔨 Building Docker image..."
if [ "$DEBUG_MODE" = "debug" ]; then
    echo "   (Debug mode - will show verbose build output)"
    docker build -t "$IMAGE_NAME" . | tee build.log
else
    echo "   (Building... this may take 5-10 minutes)"
    docker build -t "$IMAGE_NAME" . > build.log 2>&1
fi

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "❌ Build failed! Check build.log for details:"
    tail -20 build.log
    exit 1
fi

echo "✅ Build completed successfully"

# Check for required build outputs
echo ""
echo "🔍 Verifying build artifacts..."
if grep -q "SHA256" build.log && grep -q "Selected UBL:" build.log; then
    echo "✅ Build artifacts verified"
else
    echo "⚠️  Warning: Some build artifacts may be missing"
fi

# Start container
echo ""
echo "🚀 Starting InvoiceGuard container..."
if [ "$DEBUG_MODE" = "debug" ]; then
    echo "   (Debug mode - container logs will be shown)"
    docker run -d -p $PORT:8080 --name "$CONTAINER_NAME" "$IMAGE_NAME"
    echo "   Logs will be shown below..."
    docker logs -f "$CONTAINER_NAME" &
    LOG_PID=$!
    sleep 3
    kill $LOG_PID 2>/dev/null || true
else
    docker run -d -p $PORT:8080 --name "$CONTAINER_NAME" "$IMAGE_NAME"
fi

# Wait for service
echo ""
echo "⏳ Waiting for service to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:$PORT/health > /dev/null 2>&1; then
        echo "✅ InvoiceGuard is ready!"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "❌ Service failed to start within 30 seconds"
        echo "Container logs:"
        docker logs "$CONTAINER_NAME"
        exit 1
    fi
    if [ $((i % 5)) -eq 0 ]; then
        echo "   Still waiting... ($i/30)"
    fi
done

# Quick validation test
echo ""
echo "🧪 Running validation tests..."

# Test UBL
echo "Testing UBL invoice validation..."
UBL_RESULT=$(docker exec "$CONTAINER_NAME" curl -s -X POST http://localhost:8080/validate -F "file=@/app/test_ubl.xml" 2>/dev/null || echo "ERROR")
if echo "$UBL_RESULT" | grep -q '"status":"PASSED"' || echo "$UBL_RESULT" | grep -q '"status": "PASSED"'; then
    echo "✅ UBL validation: PASSED"
    UBL_SUCCESS=true
else
    echo "❌ UBL validation: FAILED"
    if [ "$DEBUG_MODE" = "debug" ]; then
        echo "   Response: $UBL_RESULT"
    fi
    UBL_SUCCESS=false
fi

# Test error handling
echo "Testing error handling with invalid XML..."
ERROR_RESULT=$(echo "invalid xml" | curl -s -X POST http://localhost:$PORT/validate -F "file=@-" 2>/dev/null || echo "ERROR")
if echo "$ERROR_RESULT" | grep -q '"status":"ERROR"' || echo "$ERROR_RESULT" | grep -q '"status": "ERROR"'; then
    echo "✅ Error handling: WORKING"
    ERROR_SUCCESS=true
else
    echo "❌ Error handling: FAILED"
    ERROR_SUCCESS=false
fi

# Summary
echo ""
echo "================================================"
echo "🎉 InvoiceGuard Setup Complete!"
echo "================================================"

if [ "$UBL_SUCCESS" = true ] && [ "$ERROR_SUCCESS" = true ]; then
    echo "✅ All quick tests PASSED"
    STATUS="HEALTHY"
else
    echo "⚠️  Some tests FAILED - check logs for details"
    STATUS="DEGRADED"
fi

echo ""
echo "Service Status: $STATUS"
echo "API Endpoint:   http://localhost:$PORT"
echo "Health Check:   http://localhost:$PORT/health"
echo ""
echo "Quick Commands:"
echo "  # Test with your own invoice"
echo "  curl -X POST http://localhost:$PORT/validate -F \"file=@your_invoice.xml\""
echo ""
echo "  # View real-time logs"
echo "  docker logs -f $CONTAINER_NAME"
echo ""
echo "  # Run comprehensive tests"
echo "  ./test.sh"
echo ""
echo "  # Stop service"
echo "  docker stop $CONTAINER_NAME"
echo ""

if [ "$DEBUG_MODE" = "debug" ]; then
    echo "Debug mode - showing recent logs:"
    echo "=================================="
    docker logs --tail=20 "$CONTAINER_NAME"
fi

# Keep container running (remove trap)
trap - EXIT
echo "Container is running in background. Use 'docker stop $CONTAINER_NAME' to stop."
