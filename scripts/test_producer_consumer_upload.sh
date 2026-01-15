#!/bin/bash
# Test script for Producer-Consumer PDF upload
# Tests real-time SSE progress streaming

set -e

PROJECT_ROOT="/Users/xrickliao/WorkSpaces/Work/Projects/DocAI"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "Producer-Consumer Upload Test"
echo "=========================================="
echo ""

# Check if server is running
echo "1. Checking if server is running..."
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo "❌ Server not running. Start with:"
    echo "   ./start_system.sh"
    exit 1
fi
echo "✅ Server is running"
echo ""

# Prepare test PDF
TEST_PDF="data/test_uploads/test_small.pdf"
if [ ! -f "$TEST_PDF" ]; then
    echo "❌ Test PDF not found: $TEST_PDF"
    echo "   Create a test PDF or use your own"
    exit 1
fi

FILESIZE=$(du -h "$TEST_PDF" | cut -f1)
echo "2. Test PDF: $TEST_PDF ($FILESIZE)"
echo ""

# Test upload with SSE streaming
echo "3. Testing SSE upload streaming..."
echo "   Endpoint: POST /api/v1/skills/upload-source-stream"
echo ""

# Monitor SSE events in real-time
curl -X POST "http://localhost:8000/api/v1/skills/upload-source-stream" \
  -H "accept: text/event-stream" \
  -F "file=@$TEST_PDF" \
  -F "skill_name=Test Producer Consumer" \
  -F "skill_description=Testing real-time progress" \
  -F "skill_category=Test" \
  -F "head_id=head_test_20251212" \
  --no-buffer | while IFS= read -r line; do
    # Parse SSE events
    if [[ "$line" =~ ^event:\ (.+)$ ]]; then
        EVENT_TYPE="${BASH_REMATCH[1]}"
        echo "📡 Event: $EVENT_TYPE"
    elif [[ "$line" =~ ^data:\ (.+)$ ]]; then
        DATA="${BASH_REMATCH[1]}"
        # Pretty print JSON (if jq available)
        if command -v jq &> /dev/null; then
            echo "$DATA" | jq -C '.'
        else
            echo "   $DATA"
        fi
        echo ""
    fi
done

echo ""
echo "=========================================="
echo "✅ Test completed!"
echo "=========================================="
echo ""
echo "Expected behavior:"
echo "  - start event (immediately)"
echo "  - phase_start event (pipeline activated)"
echo "  - Multiple checkpoint events (batch_start, batch_complete)"
echo "  - Multiple progress events (embedding)"
echo "  - Heartbeat events (if queue empty)"
echo "  - complete event (final)"
echo ""
echo "Check for:"
echo "  ✅ Progress updates every 2-5 seconds"
echo "  ✅ Batch numbers incrementing (1, 2, 3, ...)"
echo "  ✅ Total chunks accumulating"
echo "  ✅ No long freezes (>10 seconds)"
echo ""
