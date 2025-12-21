#!/bin/bash
# Log monitoring and analysis tool
set -euo pipefail

CONTAINER_NAME="invoiceguard"
MODE=${1:-"follow"}

if [ "$#" -gt 1 ]; then
    echo "Usage: $0 [follow|tail|errors|debug]"
    echo ""
    echo "Modes:"
    echo "  follow  - Follow logs in real-time (default)"
    echo "  tail    - Show last 50 lines"
    echo "  errors  - Show only ERROR and WARNING lines"
    echo "  debug   - Show only DEBUG lines"
    echo "  stats   - Show log statistics"
    exit 1
fi

# Check container exists
if ! docker ps -a | grep -q "$CONTAINER_NAME"; then
    echo "❌ Container '$CONTAINER_NAME' not found"
    echo "Available containers:"
    docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    exit 1
fi

# Check if running
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "⚠️  Container '$CONTAINER_NAME' is not running"
    echo "Status: $(docker ps -a --filter name=$CONTAINER_NAME --format '{{.Status}}')"
    echo ""
    read -p "Show logs from stopped container? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi

echo "================================================"
echo "InvoiceGuard - Log Monitor"
echo "================================================"
echo "Container: $CONTAINER_NAME"
echo "Mode: $MODE"
echo ""

case $MODE in
    "follow")
        echo "Following logs (Ctrl+C to stop)..."
        echo "================================================"
        docker logs -f "$CONTAINER_NAME"
        ;;
    
    "tail")
        echo "Last 50 log lines:"
        echo "================================================"
        docker logs --tail=50 "$CONTAINER_NAME"
        ;;
    
    "errors")
        echo "Error and warning messages:"
        echo "================================================"
        docker logs "$CONTAINER_NAME" 2>&1 | grep -E "\[ERROR\]|\[WARNING\]|\[CRITICAL\]" || echo "No errors found"
        ;;
    
    "debug")
        echo "Debug messages:"
        echo "================================================"
        docker logs "$CONTAINER_NAME" 2>&1 | grep "\[DEBUG\]" || echo "No debug messages found"
        ;;
    
    "stats")
        echo "Log Statistics:"
        echo "================================================"
        TOTAL_LINES=$(docker logs "$CONTAINER_NAME" 2>&1 | wc -l)
        ERROR_COUNT=$(docker logs "$CONTAINER_NAME" 2>&1 | grep -c "\[ERROR\]" || echo "0")
        WARNING_COUNT=$(docker logs "$CONTAINER_NAME" 2>&1 | grep -c "\[WARNING\]" || echo "0")
        INFO_COUNT=$(docker logs "$CONTAINER_NAME" 2>&1 | grep -c "\[INFO\]" || echo "0")
        DEBUG_COUNT=$(docker logs "$CONTAINER_NAME" 2>&1 | grep -c "\[DEBUG\]" || echo "0")
        
        echo "Total log lines: $TOTAL_LINES"
        echo "ERROR messages:  $ERROR_COUNT"
        echo "WARNING messages: $WARNING_COUNT"
        echo "INFO messages:   $INFO_COUNT"
        echo "DEBUG messages:  $DEBUG_COUNT"
        
        echo ""
        echo "Recent activity (last 10 lines):"
        echo "================================"
        docker logs --tail=10 "$CONTAINER_NAME"
        ;;
    
    *)
        echo "❌ Unknown mode: $MODE"
        exit 1
        ;;
esac
