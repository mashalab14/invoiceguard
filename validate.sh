#!/bin/bash
# Advanced testing and troubleshooting script
set -euo pipefail

echo "================================================"
echo "InvoiceGuard - Advanced Testing & Troubleshooting"
echo "================================================"

CONTAINER_NAME="invoiceguard"
PORT=8080
VERBOSE=${1:-false}

# Helper functions
log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

test_endpoint() {
    local name="$1"
    local cmd="$2"
    local expected="$3"
    
    echo ""
    log "Testing: $name"
    
    if [ "$VERBOSE" = "-v" ]; then
        echo "Command: $cmd"
    fi
    
    result=$(eval "$cmd" 2>/dev/null || echo "COMMAND_FAILED")
    
    if echo "$result" | grep -q "$expected"; then
        echo "✅ PASS: $name"
        return 0
    else
        echo "❌ FAIL: $name"
        if [ "$VERBOSE" = "-v" ]; then
            echo "Expected: $expected"
            echo "Got: $result"
        fi
        return 1
    fi
}

check_container() {
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        echo "❌ Container '$CONTAINER_NAME' is not running"
        echo ""
        echo "Available containers:"
        docker ps -a
        echo ""
        echo "To start: ./start.sh"
        exit 1
    fi
    echo "✅ Container is running"
}

# Main tests
echo "Container: $CONTAINER_NAME"
echo "Port: $PORT"
echo "Verbose: $VERBOSE"
echo ""

check_container

# Test 1: Health check
test_endpoint "Health Check" \
    "curl -s http://localhost:$PORT/health" \
    "healthy"

# Test 2: UBL validation 
test_endpoint "UBL Invoice Validation" \
    "docker exec $CONTAINER_NAME curl -s -X POST http://localhost:8080/validate -F 'file=@/app/test_ubl.xml'" \
    '"status":"PASSED"'

# Test 3: Invalid XML handling
test_endpoint "Invalid XML Error Handling" \
    "echo 'not xml' | curl -s -X POST http://localhost:$PORT/validate -F 'file=@-'" \
    '"status":"ERROR"'

# Test 4: File size limit
log "Testing file size limit (this may take a moment)..."
dd if=/dev/zero of=/tmp/large_test.xml bs=1M count=11 2>/dev/null
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:$PORT/validate -F "file=@/tmp/large_test.xml")
rm -f /tmp/large_test.xml

if [ "$HTTP_CODE" = "413" ]; then
    echo "✅ PASS: File size limit (HTTP 413)"
else
    echo "❌ FAIL: File size limit (got HTTP $HTTP_CODE, expected 413)"
fi

# Test 5: API response structure
log "Testing API response structure..."
RESPONSE=$(docker exec $CONTAINER_NAME curl -s -X POST http://localhost:8080/validate -F 'file=@/app/test_ubl.xml')

# Check required fields
for field in "status" "meta" "errors"; do
    if echo "$RESPONSE" | grep -q "\"$field\""; then
        echo "✅ Response contains '$field' field"
    else
        echo "❌ Response missing '$field' field"
    fi
done

# Test 6: Concurrent requests (stress test)
log "Testing concurrent requests..."
for i in {1..5}; do
    docker exec $CONTAINER_NAME curl -s -X POST http://localhost:8080/validate -F 'file=@/app/test_ubl.xml' > /tmp/concurrent_$i.json &
done
wait

SUCCESS_COUNT=0
for i in {1..5}; do
    if grep -q '"status":"PASSED"' /tmp/concurrent_$i.json 2>/dev/null; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    fi
    rm -f /tmp/concurrent_$i.json
done

if [ "$SUCCESS_COUNT" -eq 5 ]; then
    echo "✅ PASS: Concurrent requests (5/5 successful)"
else
    echo "❌ FAIL: Concurrent requests ($SUCCESS_COUNT/5 successful)"
fi

# Performance test
log "Testing validation performance..."
START_TIME=$(date +%s%N)
docker exec $CONTAINER_NAME curl -s -X POST http://localhost:8080/validate -F 'file=@/app/test_ubl.xml' > /dev/null
END_TIME=$(date +%s%N)
DURATION_MS=$(( (END_TIME - START_TIME) / 1000000 ))

echo "⏱️  Validation time: ${DURATION_MS}ms"
if [ "$DURATION_MS" -lt 5000 ]; then
    echo "✅ PASS: Performance (<5s)"
else
    echo "⚠️  SLOW: Performance (>${DURATION_MS}ms)"
fi

# Container health
echo ""
log "Container diagnostics:"
echo "Memory usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" $CONTAINER_NAME

echo ""
echo "Recent logs (last 10 lines):"
docker logs --tail=10 $CONTAINER_NAME

if [ "$VERBOSE" = "-v" ]; then
    echo ""
    echo "Container inspection:"
    docker inspect $CONTAINER_NAME --format='
Image: {{.Config.Image}}
Status: {{.State.Status}}
Health: {{.State.Health.Status}}
Started: {{.State.StartedAt}}
Ports: {{range $p, $conf := .NetworkSettings.Ports}}{{$p}} -> {{(index $conf 0).HostPort}} {{end}}
'
fi

echo ""
echo "================================================"
echo "🏁 Testing Complete"
echo "================================================"
