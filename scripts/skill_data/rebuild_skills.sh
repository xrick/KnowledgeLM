# scripts/skill_data/rebuild_skills.sh
#!/bin/bash
# ==============================================================================
# rebuild_skills.sh
# ==============================================================================
# 功能：根據 skill_config.json 重建所有 Skills
#
# 使用方式：
#   ./scripts/skill_data/rebuild_skills.sh [options]
#
# 選項：
#   --clean       : 執行前先清除現有資料
#   --config PATH : 指定配置文件路徑 (預設: scripts/skill_data/skill_config.json)
#   --skill NAME  : 只重建指定的 skill
#   --dry-run     : 模擬執行，不實際建立
#   --force       : 跳過確認直接執行
#
# 範例：
#   ./scripts/skill_data/rebuild_skills.sh --clean
#   ./scripts/skill_data/rebuild_skills.sh --skill "LLM"
#   ./scripts/skill_data/rebuild_skills.sh --config custom_config.json
#
# ==============================================================================

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 取得腳本所在目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 預設值
CONFIG_FILE="$SCRIPT_DIR/skill_config.json"
CLEAN_FIRST=false
DRY_RUN=false
FORCE=false
SKILL_FILTER=""

# 解析參數
while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN_FIRST=true
            shift
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --skill)
            SKILL_FILTER="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --clean       Clean existing data before rebuild"
            echo "  --config PATH Specify config file path"
            echo "  --skill NAME  Only rebuild specified skill"
            echo "  --dry-run     Simulate without making changes"
            echo "  --force       Skip confirmation prompts"
            echo "  -h, --help    Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# 函數：顯示橫幅
show_banner() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              DocAI Skill Rebuilder                             ║"
    echo "║                                                                ║"
    echo "║  根據 skill_config.json 重建 Skills                            ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 函數：檢查依賴
check_dependencies() {
    echo -e "${YELLOW}📋 檢查依賴...${NC}"

    # 檢查 Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}錯誤：找不到 python3${NC}"
        exit 1
    fi
    echo "  ✓ Python3: $(python3 --version)"

    # 檢查配置文件
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}錯誤：配置文件不存在 - $CONFIG_FILE${NC}"
        exit 1
    fi
    echo "  ✓ 配置文件: $CONFIG_FILE"

    # 檢查虛擬環境
    if [ -d "$PROJECT_ROOT/docaienv" ]; then
        PYTHON_PATH="$PROJECT_ROOT/docaienv/bin/python"
        echo "  ✓ 虛擬環境: docaienv"
    else
        PYTHON_PATH="python3"
        echo -e "  ${YELLOW}⚠ 未找到 docaienv，使用系統 Python${NC}"
    fi

    echo ""
}

# 函數：顯示配置摘要
show_config_summary() {
    echo -e "${YELLOW}📊 配置摘要：${NC}"
    echo ""

    # 使用 Python 解析 JSON 並顯示
    $PYTHON_PATH << EOF
import json
import sys

try:
    with open("$CONFIG_FILE", 'r', encoding='utf-8') as f:
        config = json.load(f)

    skills = config.get('skills', [])
    settings = config.get('settings', {})
    instant = config.get('instant_attachments', [])

    print(f"  版本: {config.get('version', 'N/A')}")
    print(f"  Skills 數量: {len(skills)}")
    print(f"  Instant Attachments: {len(instant)}")
    print(f"  Chunk Size: {settings.get('chunk_size', 'N/A')}")
    print(f"  Embedding Model: {settings.get('embedding_model', 'N/A')}")
    print("")

    print("  Skills 清單:")
    skill_filter = "$SKILL_FILTER"
    for skill in skills:
        name = skill.get('skill_name', 'Unknown')
        enabled = skill.get('enabled', True)
        sources = skill.get('sources', [])
        enabled_sources = [s for s in sources if s.get('enabled', True)]

        if skill_filter and name != skill_filter:
            continue

        status = "✓" if enabled else "✗"
        print(f"    {status} {name}: {len(enabled_sources)}/{len(sources)} PDF files")

except Exception as e:
    print(f"錯誤：無法解析配置文件 - {e}")
    sys.exit(1)
EOF

    echo ""
}

# 函數：執行清除
do_clean() {
    if [ "$CLEAN_FIRST" = true ]; then
        echo -e "${YELLOW}🧹 執行清除...${NC}"

        if [ "$DRY_RUN" = true ]; then
            echo "  [DRY-RUN] 將會執行: $SCRIPT_DIR/clean_skill_tables.sh --force"
        else
            "$SCRIPT_DIR/clean_skill_tables.sh" --force
        fi

        echo ""
    fi
}

# 函數：執行重建
do_rebuild() {
    echo -e "${CYAN}🔨 開始重建 Skills...${NC}"
    echo ""

    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY-RUN] 將會執行重建流程"
        echo "  配置文件: $CONFIG_FILE"
        [ -n "$SKILL_FILTER" ] && echo "  只重建: $SKILL_FILTER"
        return 0
    fi

    # 切換到專案根目錄
    cd "$PROJECT_ROOT"

    # 設定環境變數
    export SKILL_CONFIG_PATH="$CONFIG_FILE"
    [ -n "$SKILL_FILTER" ] && export SKILL_FILTER="$SKILL_FILTER"

    # 執行 Python 重建腳本
    $PYTHON_PATH scripts/skill_data/rebuild_from_config.py

    echo ""
}

# 函數：驗證結果
verify_results() {
    echo -e "${YELLOW}🔍 驗證結果...${NC}"

    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY-RUN] 跳過驗證"
        return 0
    fi

    local db_path="$PROJECT_ROOT/data/skill_metadata.db"

    if [ -f "$db_path" ]; then
        echo "  Skills in database:"
        sqlite3 "$db_path" "SELECT '    - ' || skill_name || ' (' || total_chunks || ' chunks)' FROM skill_metadata;"
        echo ""

        local skill_count=$(sqlite3 "$db_path" "SELECT COUNT(*) FROM skill_metadata;")
        local chunk_count=$(sqlite3 "$db_path" "SELECT COUNT(*) FROM skill_chunk_metadata;")

        echo -e "${GREEN}  ✓ 總共 $skill_count 個 Skills${NC}"
        echo -e "${GREEN}  ✓ 總共 $chunk_count 個 Chunks${NC}"
    else
        echo -e "${RED}  ✗ 資料庫檔案不存在${NC}"
    fi

    echo ""
}

# 主程式
main() {
    show_banner
    check_dependencies
    show_config_summary

    # 確認執行
    if [ "$FORCE" != true ] && [ "$DRY_RUN" != true ]; then
        echo -e "${RED}⚠️  警告：此操作將重建 Skills 資料！${NC}"
        echo ""
        read -p "確定要繼續嗎？ (輸入 'yes' 確認): " confirm

        if [ "$confirm" != "yes" ]; then
            echo ""
            echo -e "${YELLOW}操作已取消${NC}"
            exit 0
        fi
        echo ""
    fi

    # 執行步驟
    do_clean
    do_rebuild
    verify_results

    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ 重建完成！${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
}

# 執行主程式
main "$@"
