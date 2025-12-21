#!/bin/bash
# Production deployment script for InvoiceGuard
set -euo pipefail

echo "================================================"
echo "InvoiceGuard - Production Deployment"
echo "================================================"

# Configuration
IMAGE_NAME="invoiceguard"
VERSION=${1:-"latest"}
CONTAINER_NAME="invoiceguard-prod"
PORT=${2:-"8080"}
RESTART_POLICY="unless-stopped"

# Validation
if [ "$#" -gt 2 ]; then
    echo "Usage: $0 [version] [port]"
    echo "Example: $0 v1.0.0 8080"
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found"
    exit 1
fi

if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker daemon not running"
    exit 1
fi

echo "Deploying InvoiceGuard version: $VERSION"
echo "Port: $PORT"
echo "Restart policy: $RESTART_POLICY"
echo ""

# Stop existing container
echo "🛑 Stopping existing container..."
docker stop "$CONTAINER_NAME" 2>/dev/null || echo "   No existing container found"
docker rm "$CONTAINER_NAME" 2>/dev/null || echo "   No existing container to remove"

# Build if version is 'latest' or 'build'
if [ "$VERSION" = "latest" ] || [ "$VERSION" = "build" ]; then
    echo ""
    echo "🔨 Building image..."
    docker build -t "$IMAGE_NAME:$VERSION" .
    if [ $? -ne 0 ]; then
        echo "❌ Build failed"
        exit 1
    fi
    echo "✅ Build completed"
fi

# Deploy
echo ""
echo "🚀 Deploying container..."
docker run -d \
    --name "$CONTAINER_NAME" \
    --restart "$RESTART_POLICY" \
    -p "$PORT:8080" \
    --health-cmd="python -c \"import requests; requests.get('http://localhost:8080/health', timeout=5)\"" \
    --health-interval=30s \
    --health-timeout=10s \
    --health-start-period=10s \
    --health-retries=3 \
    "$IMAGE_NAME:$VERSION"

if [ $? -ne 0 ]; then
    echo "❌ Deployment failed"
    exit 1
fi

# Wait for health check
echo ""
echo "⏳ Waiting for health check..."
for i in {1..60}; do
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    if [ "$HEALTH" = "healthy" ]; then
        echo "✅ Service is healthy!"
        break
    elif [ "$HEALTH" = "unhealthy" ]; then
        echo "❌ Service failed health check"
        echo "Logs:"
        docker logs "$CONTAINER_NAME"
        exit 1
    fi
    sleep 1
    if [ $((i % 10)) -eq 0 ]; then
        echo "   Health status: $HEALTH ($i/60)"
    fi
done

if [ "$HEALTH" != "healthy" ]; then
    echo "⚠️  Health check timeout - service may still be starting"
fi

# Final test
echo ""
echo "🧪 Running deployment verification..."
if curl -s "http://localhost:$PORT/health" | grep -q "healthy"; then
    echo "✅ API responding correctly"
else
    echo "❌ API not responding"
    docker logs "$CONTAINER_NAME"
    exit 1
fi

echo ""
echo "================================================"
echo "🎉 Production Deployment Complete!"
echo "================================================"
echo ""
echo "Service:     $CONTAINER_NAME"
echo "Image:       $IMAGE_NAME:$VERSION"
echo "URL:         http://localhost:$PORT"
echo "Health:      http://localhost:$PORT/health"
echo "Restart:     $RESTART_POLICY"
echo ""
echo "Management Commands:"
echo "  docker logs $CONTAINER_NAME           # View logs"
echo "  docker logs -f $CONTAINER_NAME        # Follow logs"
echo "  docker stop $CONTAINER_NAME           # Stop service"
echo "  docker restart $CONTAINER_NAME        # Restart service"
echo "  docker inspect $CONTAINER_NAME        # Detailed info"
echo ""
echo "Monitoring:"
echo "  curl http://localhost:$PORT/health    # Health check"
echo "  docker stats $CONTAINER_NAME          # Resource usage"
echo ""
