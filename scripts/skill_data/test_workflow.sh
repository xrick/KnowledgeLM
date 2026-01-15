# scripts/skill_data/test_workflow.sh
#!/bin/bash
# ==============================================================================
# test_workflow.sh
# ==============================================================================
# 功能：測試 Skill Data Management System 完整工作流程
#
# 測試項目：
#   1. 配置文件讀取
#   2. 清除腳本執行
#   3. API endpoints 可用性
#   4. 重建流程
#
# ==============================================================================

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 取得腳本目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           Skill Data Management System Test                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 計數器
PASSED=0
FAILED=0

# 測試函數
test_case() {
    local name="$1"
    local cmd="$2"

    echo -n "  Testing: $name... "
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASSED${NC}"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}✗ FAILED${NC}"
        FAILED=$((FAILED + 1))
    fi
}

# 1. 檔案存在性測試
echo -e "\n${YELLOW}1. File Existence Tests${NC}"
echo "────────────────────────────────────────"

test_case "clean_skill_tables.sh exists" "[ -f '$SCRIPT_DIR/clean_skill_tables.sh' ]"
test_case "rebuild_skills.sh exists" "[ -f '$SCRIPT_DIR/rebuild_skills.sh' ]"
test_case "rebuild_from_config.py exists" "[ -f '$SCRIPT_DIR/rebuild_from_config.py' ]"
test_case "skill_config.json exists" "[ -f '$SCRIPT_DIR/skill_config.json' ]"

# 2. 配置文件測試
echo -e "\n${YELLOW}2. Configuration Tests${NC}"
echo "────────────────────────────────────────"

test_case "skill_config.json is valid JSON" "python3 -c \"import json; json.load(open('$SCRIPT_DIR/skill_config.json'))\""
test_case "Config has skills array" "python3 -c \"import json; c=json.load(open('$SCRIPT_DIR/skill_config.json')); assert 'skills' in c\""
test_case "Config has settings" "python3 -c \"import json; c=json.load(open('$SCRIPT_DIR/skill_config.json')); assert 'settings' in c\""

# 3. 腳本語法測試
echo -e "\n${YELLOW}3. Script Syntax Tests${NC}"
echo "────────────────────────────────────────"

test_case "clean_skill_tables.sh syntax" "bash -n '$SCRIPT_DIR/clean_skill_tables.sh'"
test_case "rebuild_skills.sh syntax" "bash -n '$SCRIPT_DIR/rebuild_skills.sh'"
test_case "rebuild_from_config.py syntax" "python3 -m py_compile '$SCRIPT_DIR/rebuild_from_config.py'"

# 4. 資料庫測試
echo -e "\n${YELLOW}4. Database Tests${NC}"
echo "────────────────────────────────────────"

DB_PATH="$PROJECT_ROOT/data/skill_metadata.db"
test_case "skill_metadata.db exists" "[ -f '$DB_PATH' ]"
test_case "skill_metadata table exists" "sqlite3 '$DB_PATH' '.tables' | grep -q 'skill_metadata'"
test_case "embedding_models table exists" "sqlite3 '$DB_PATH' '.tables' | grep -q 'embedding_models'"

# 5. API 測試 (需要服務器運行)
echo -e "\n${YELLOW}5. API Tests (requires server running)${NC}"
echo "────────────────────────────────────────"

if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    test_case "Server is healthy" "curl -s http://localhost:8000/health | grep -q 'healthy'"
    test_case "Skills API responds" "curl -s http://localhost:8000/api/v1/skills/ | grep -q 'skill_id'"
    test_case "Demo skills API responds" "curl -s http://localhost:8000/api/v1/skills/demo | grep -q 'id'"
else
    echo -e "  ${YELLOW}⚠ Server not running, skipping API tests${NC}"
fi

# 6. Template 測試
echo -e "\n${YELLOW}6. Template Tests${NC}"
echo "────────────────────────────────────────"

test_case "skill_main.html exists" "[ -f '$PROJECT_ROOT/template/skill_main.html' ]"
test_case "skill_config.html exists" "[ -f '$PROJECT_ROOT/template/skill_config.html' ]"
test_case "skill_main.html has config link" "grep -q 'skill/config' '$PROJECT_ROOT/template/skill_main.html'"

# 結果摘要
echo ""
echo "════════════════════════════════════════════════════════════════"
echo -e "  Total: $((PASSED + FAILED)) tests"
echo -e "  ${GREEN}Passed: $PASSED${NC}"
echo -e "  ${RED}Failed: $FAILED${NC}"
echo "════════════════════════════════════════════════════════════════"

if [ $FAILED -eq 0 ]; then
    echo -e "\n${GREEN}✅ All tests passed!${NC}"
    exit 0
else
    echo -e "\n${RED}❌ Some tests failed. Please check the output above.${NC}"
    exit 1
fi
