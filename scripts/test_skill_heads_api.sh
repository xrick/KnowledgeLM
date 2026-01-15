#!/bin/bash
# Test script for skill_heads API endpoints

BASE_URL="http://127.0.0.1:8000/api/v1/skills"

echo "=============================================="
echo "Testing Skill Heads API Endpoints"
echo "=============================================="

# Test 1: Get skill tree
echo ""
echo "[1] GET /tree - Get complete skill tree"
curl -s "$BASE_URL/tree" | python3 -m json.tool 2>/dev/null || echo "❌ Failed"

# Test 2: List skill heads
echo ""
echo "[2] GET /heads - List all skill heads"
curl -s "$BASE_URL/heads" | python3 -m json.tool 2>/dev/null || echo "❌ Failed"

# Test 3: Create skill head (commented out to avoid creating test data)
# echo ""
# echo "[3] POST /heads - Create new skill head"
# curl -s -X POST "$BASE_URL/heads" \
#     -H "Content-Type: application/json" \
#     -d '{"skill_name":"Test Skill","description":"Test description","category":"Test"}' \
#     | python3 -m json.tool

# Test 4: Run migration (safe to run multiple times)
echo ""
echo "[3] POST /migrate - Run migration"
curl -s -X POST "$BASE_URL/migrate" | python3 -m json.tool 2>/dev/null || echo "❌ Failed"

echo ""
echo "=============================================="
echo "Tests complete!"
echo "=============================================="
