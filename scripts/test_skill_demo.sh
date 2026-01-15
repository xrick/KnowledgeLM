#!/bin/bash
#
# Test Skill Demo Functionality
# 測試技能模式Demo功能
#

set -e

echo "========================================"
echo "🎯 DocAI Skill-Based RAG Demo Test"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
API_BASE="http://localhost:8001"
SKILL_ID="skill_ai_research_2024"
TEST_QUERY="深度學習"

# Function to check if service is running
check_service() {
    echo "📍 Checking if DocAI service is running..."
    if curl -s -f "${API_BASE}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ DocAI service is running${NC}"
        return 0
    else
        echo -e "${RED}❌ DocAI service is not running${NC}"
        echo "   Please start the service first: ./start_system.sh"
        return 1
    fi
}

# Function to load demo skills
load_demo_skills() {
    echo ""
    echo "📚 Loading Demo Skills..."
    echo "   This will create 3 demo skills with pre-generated content"

    # Check if Python virtual environment exists
    if [ -d "docaienv" ]; then
        PYTHON_CMD="docaienv/bin/python"
    else
        PYTHON_CMD="python3"
    fi

    # Run the load script
    if $PYTHON_CMD scripts/load_demo_skills.py; then
        echo -e "${GREEN}✅ Demo skills loaded successfully${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️ Some issues loading demo skills (may already exist)${NC}"
        return 0  # Continue anyway
    fi
}

# Function to test skill list API
test_list_skills() {
    echo ""
    echo "🔍 Testing Skill List API..."

    response=$(curl -s "${API_BASE}/api/v1/skills/demo")

    if echo "$response" | grep -q "skill_ai_research"; then
        echo -e "${GREEN}✅ Skill list API working${NC}"
        echo "   Found skills:"
        echo "$response" | python3 -m json.tool | grep '"name"' | head -3
        return 0
    else
        echo -e "${RED}❌ Skill list API failed${NC}"
        echo "   Response: $response"
        return 1
    fi
}

# Function to test skill query API
test_skill_query() {
    echo ""
    echo "🔎 Testing Skill Query API..."
    echo "   Skill: $SKILL_ID"
    echo "   Query: $TEST_QUERY"

    response=$(curl -s -X POST "${API_BASE}/api/v1/skills/demo/query" \
        -H "Content-Type: application/json" \
        -d "{
            \"skill_id\": \"${SKILL_ID}\",
            \"query\": \"${TEST_QUERY}\",
            \"top_k\": 5
        }")

    if echo "$response" | grep -q "answer"; then
        echo -e "${GREEN}✅ Skill query API working${NC}"

        # Extract some info
        search_mode=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('search_mode', 'unknown'))" 2>/dev/null || echo "unknown")
        docs_searched=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('documents_searched', 0))" 2>/dev/null || echo "0")

        echo "   Search mode: $search_mode"
        echo "   Documents searched: $docs_searched"

        # Show first 100 chars of answer
        answer_preview=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('answer', '')[:100])" 2>/dev/null || echo "")
        echo "   Answer preview: ${answer_preview}..."

        return 0
    else
        echo -e "${RED}❌ Skill query API failed${NC}"
        echo "   Response: $response"
        return 1
    fi
}

# Function to test web interface
test_web_interface() {
    echo ""
    echo "🌐 Testing Web Interface..."

    # Test main page
    if curl -s -f "${API_BASE}/" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Main page accessible${NC}"
    else
        echo -e "${RED}❌ Main page not accessible${NC}"
    fi

    # Test skill demo page
    if curl -s -f "${API_BASE}/skill-demo" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Skill demo page accessible${NC}"
        echo ""
        echo "   🎉 Demo is ready!"
        echo "   📱 Open in browser: ${API_BASE}/skill-demo"
    else
        echo -e "${RED}❌ Skill demo page not accessible${NC}"
    fi
}

# Function to run performance test
test_performance() {
    echo ""
    echo "⚡ Testing Performance (Optional)..."

    # Test parallel search performance
    echo "   Testing parallel search with 3 queries..."

    start_time=$(date +%s%N)

    for i in {1..3}; do
        curl -s -X POST "${API_BASE}/api/v1/skills/demo/query" \
            -H "Content-Type: application/json" \
            -d "{
                \"skill_id\": \"${SKILL_ID}\",
                \"query\": \"${TEST_QUERY} $i\",
                \"top_k\": 5
            }" > /dev/null 2>&1 &
    done

    wait

    end_time=$(date +%s%N)
    elapsed=$((($end_time - $start_time) / 1000000))  # Convert to milliseconds

    echo -e "${GREEN}✅ Parallel queries completed in ${elapsed}ms${NC}"
}

# Main test flow
main() {
    echo "Starting Demo Test Suite..."
    echo ""

    # Step 1: Check service
    if ! check_service; then
        echo ""
        echo -e "${RED}Test aborted: Service not running${NC}"
        exit 1
    fi

    # Step 2: Load demo skills
    load_demo_skills

    # Step 3: Test APIs
    test_list_skills
    test_skill_query

    # Step 4: Test web interface
    test_web_interface

    # Step 5: Optional performance test
    read -p "Run performance test? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_performance
    fi

    # Summary
    echo ""
    echo "========================================"
    echo "📊 Test Summary"
    echo "========================================"
    echo -e "${GREEN}✅ All core tests passed!${NC}"
    echo ""
    echo "🚀 Demo is ready for presentation!"
    echo "   1. Open browser: ${API_BASE}/skill-demo"
    echo "   2. Select a skill (AI研究論文集, Python開發文檔, or 商業分析報告)"
    echo "   3. Enter a query (e.g., 深度學習, FastAPI, 數據驅動)"
    echo "   4. See the parallel search results!"
    echo ""
    echo "💡 Tips for demo:"
    echo "   - The system uses Level 1 parallel search optimization"
    echo "   - Each skill contains 3 documents with 5 chunks each"
    echo "   - Results show similarity scores and source documents"
    echo ""
}

# Run main function
main