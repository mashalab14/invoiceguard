#!/bin/bash
# Quick Start Script for InvoiceGuard
# Builds, runs, and tests the validator

set -euo pipefail

echo "================================================"
echo "InvoiceGuard - Quick Start"
echo "================================================"
echo ""

# Configuration
IMAGE_NAME="invoiceguard:latest"
CONTAINER_NAME="invoiceguard"
PORT=8080

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker and try again."
    exit 1
fi

# Clean up existing container
echo "🧹 Cleaning up existing containers..."
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

# Build image
echo ""
echo "🔨 Building Docker image..."
echo "This will take 5-10 minutes depending on your internet connection."
echo ""
if ! docker build -t "$IMAGE_NAME" .; then
    echo "❌ Build failed!"
    exit 1
fi

echo ""
echo "✅ Build complete!"
echo ""

# Run container
echo "🚀 Starting InvoiceGuard..."
docker run -d -p $PORT:8080 --name "$CONTAINER_NAME" "$IMAGE_NAME"

# Wait for startup
echo "⏳ Waiting for service to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:$PORT/health > /dev/null 2>&1; then
        echo "✅ InvoiceGuard is ready!"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "❌ Service failed to start"
        echo "Logs:"
        docker logs "$CONTAINER_NAME"
        exit 1
    fi
done

# Test with built-in files
echo ""
echo "🧪 Running quick tests..."
echo ""

echo "Testing UBL invoice..."
UBL_RESPONSE=$(docker exec "$CONTAINER_NAME" curl -s -X POST http://localhost:8080/validate -F "file=@/app/test_ubl.xml")
if echo "$UBL_RESPONSE" | grep -q '"status":"PASSED"' || echo "$UBL_RESPONSE" | grep -q '"status": "PASSED"'; then
    echo "✅ UBL validation: PASSED"
else
    echo "❌ UBL validation: FAILED"
    echo "$UBL_RESPONSE"
fi

echo ""
echo "Testing CII invoice..."
CII_RESPONSE=$(docker exec "$CONTAINER_NAME" curl -s -X POST http://localhost:8080/validate -F "file=@/app/test_cii.xml")
if echo "$CII_RESPONSE" | grep -q '"status":"PASSED"' || echo "$CII_RESPONSE" | grep -q '"status": "PASSED"'; then
    echo "✅ CII validation: PASSED"
else
    echo "❌ CII validation: FAILED"
    echo "$CII_RESPONSE"
fi

# Display info
echo ""
echo "================================================"
echo "🎉 InvoiceGuard is running!"
echo "================================================"
echo ""
echo "API Endpoint:    http://localhost:$PORT"
echo "Health Check:    http://localhost:$PORT/health"
echo "Container Name:  $CONTAINER_NAME"
echo ""
echo "Usage Examples:"
echo "  # Validate an invoice"
echo "  curl -X POST http://localhost:$PORT/validate -F \"file=@invoice.xml\""
echo ""
echo "  # Check health"
echo "  curl http://localhost:$PORT/health"
echo ""
echo "  # View logs"
echo "  docker logs $CONTAINER_NAME"
echo ""
echo "  # Stop service"
echo "  docker stop $CONTAINER_NAME"
echo ""
echo "  # Run full test suite"
echo "  ./test.sh"
echo ""
echo "📚 Documentation: See README.md and IMPLEMENTATION.md"
echo "🔗 Repository: https://github.com/mashalab14/invoiceguard"
echo ""
