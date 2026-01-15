#!/bin/bash
# Fix script for Gorgon Point FAISS index integrity issue
# This script rebuilds the FAISS index for the affected skill

echo "=================================================="
echo "Gorgon Point FAISS Index Repair Script"
echo "=================================================="
echo ""

SKILL_NAME="AMD"
SKILL_ID="skill_20251211_075133_48af4341_5c6743"
API_URL="http://localhost:8765/api/v1/skills"

echo "Target Skill: $SKILL_NAME"
echo "Skill ID: $SKILL_ID"
echo ""

# Check current index status
echo "1. Checking current FAISS index status..."
INDEX_PATH="data/faiss_indices/skills/$SKILL_ID/index.faiss"

if [ -f "$INDEX_PATH" ]; then
    echo "   ✅ Index file exists: $INDEX_PATH"

    # Use Python to check vector count
    VECTOR_COUNT=$(docaienv/bin/python3 << EOF
import faiss
try:
    index = faiss.read_index("$INDEX_PATH")
    print(index.ntotal)
except Exception as e:
    print("ERROR")
EOF
)

    if [ "$VECTOR_COUNT" != "ERROR" ]; then
        echo "   📊 Current vector count: $VECTOR_COUNT"
        if [ "$VECTOR_COUNT" -lt "65" ]; then
            echo "   ❌ ISSUE CONFIRMED: Expected 65 vectors, found $VECTOR_COUNT"
        fi
    fi
else
    echo "   ❌ Index file not found!"
fi

echo ""

# Check database chunk count
echo "2. Checking database chunk count..."
DB_CHUNKS=$(sqlite3 data/skill_metadata.db "SELECT total_chunks FROM skill_metadata WHERE skill_id = '$SKILL_ID';")
echo "   📊 Database chunks: $DB_CHUNKS"
echo ""

# Rebuild index
echo "3. Rebuilding FAISS index via API..."
echo "   Sending rebuild request..."

REBUILD_RESPONSE=$(curl -s -X POST "$API_URL/rebuild" \
  -H "Content-Type: application/json" \
  -d "{\"skill_name\": \"$SKILL_NAME\", \"force_all\": false}")

echo "   Response: $REBUILD_RESPONSE"
echo ""

# Wait for rebuild to complete
echo "4. Waiting for rebuild to complete..."
sleep 5

# Check rebuild status
for i in {1..12}; do
    STATUS_RESPONSE=$(curl -s -X GET "$API_URL/rebuild/status")
    echo "   Status check $i: $STATUS_RESPONSE"

    if echo "$STATUS_RESPONSE" | grep -q '"status":"completed"'; then
        echo "   ✅ Rebuild completed successfully!"
        break
    elif echo "$STATUS_RESPONSE" | grep -q '"status":"failed"'; then
        echo "   ❌ Rebuild failed!"
        break
    fi

    sleep 5
done

echo ""

# Verify fix
echo "5. Verifying index integrity after rebuild..."
NEW_VECTOR_COUNT=$(docaienv/bin/python3 << EOF
import faiss
try:
    index = faiss.read_index("$INDEX_PATH")
    print(index.ntotal)
except Exception as e:
    print("ERROR")
EOF
)

if [ "$NEW_VECTOR_COUNT" != "ERROR" ]; then
    echo "   📊 New vector count: $NEW_VECTOR_COUNT"

    if [ "$NEW_VECTOR_COUNT" -eq "65" ]; then
        echo "   ✅ SUCCESS: Index integrity restored! ($NEW_VECTOR_COUNT/65 vectors)"
    else
        echo "   ⚠️  WARNING: Vector count still incorrect ($NEW_VECTOR_COUNT/65)"
    fi
fi

echo ""

# Test retrieval
echo "6. Testing Thunderbolt 4 content retrieval..."
TEST_QUERY="pathway to Thunderbolt 4 certification"

echo "   Query: $TEST_QUERY"
echo "   Running test script..."

docaienv/bin/python3 scripts/test_gorgon_retrieval.py 2>&1 | grep -A 5 "Chunks containing 'THUNDERBOLT'"

echo ""
echo "=================================================="
echo "Repair script completed!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "1. Check the log output above for any errors"
echo "2. Verify 65/65 vectors in FAISS index"
echo "3. Test query in skill/chat UI to confirm Thunderbolt 4 content is retrievable"
echo ""
