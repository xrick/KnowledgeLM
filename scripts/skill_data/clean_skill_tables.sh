#!/bin/bash
# ==============================================================================
# clean_skill_tables.sh
# ==============================================================================
# 功能：清除 skill_metadata.db 中的所有 skill 相關表格
# 保留：embedding_models 表格（不修改）
#
# 被清除的表格：
#   - skill_chunk_metadata   (Skill 的 chunk 資料)
#   - skill_document_mapping (Skill 與文檔的對應關係)
#   - skill_metadata         (Skill 的基本資訊)
#   - skill_overviews        (Skill 的概述)
#
# 使用方式：
#   ./scripts/skill_data/clean_skill_tables.sh [--force]
#
# 參數：
#   --force : 跳過確認直接執行
#
# ==============================================================================

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 取得腳本所在目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DB_PATH="$PROJECT_ROOT/data/skill_metadata.db"
FAISS_SKILLS_DIR="$PROJECT_ROOT/data/faiss_indices/skills"

# 函數：顯示橫幅
show_banner() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║             DocAI Skill Tables Cleaner                         ║"
    echo "║                                                                ║"
    echo "║  清除 skill_metadata.db 中的 skill 相關表格                    ║"
    echo "║  保留 embedding_models 表格                                    ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 函數：顯示當前狀態
show_current_status() {
    echo -e "${YELLOW}📊 當前資料庫狀態：${NC}"
    echo ""

    if [ -f "$DB_PATH" ]; then
        # 顯示各表格的記錄數
        echo "表格記錄數："
        echo "  - skill_metadata:         $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM skill_metadata;" 2>/dev/null || echo "N/A")"
        echo "  - skill_overviews:        $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM skill_overviews;" 2>/dev/null || echo "N/A")"
        echo "  - skill_document_mapping: $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM skill_document_mapping;" 2>/dev/null || echo "N/A")"
        echo "  - skill_chunk_metadata:   $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM skill_chunk_metadata;" 2>/dev/null || echo "N/A")"
        echo -e "  - embedding_models:       $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM embedding_models;" 2>/dev/null || echo "N/A") ${GREEN}(保留)${NC}"
        echo ""

        # 顯示現有 skills
        echo "現有 Skills："
        sqlite3 "$DB_PATH" "SELECT '  - ' || skill_name || ' (' || total_chunks || ' chunks)' FROM skill_metadata;" 2>/dev/null || echo "  (無)"
        echo ""
    else
        echo -e "${RED}  資料庫檔案不存在！${NC}"
        echo ""
    fi

    # 顯示 FAISS 索引目錄
    echo "FAISS Skills 索引目錄："
    if [ -d "$FAISS_SKILLS_DIR" ]; then
        local count=$(find "$FAISS_SKILLS_DIR" -name "*.faiss" 2>/dev/null | wc -l)
        echo "  路徑: $FAISS_SKILLS_DIR"
        echo "  索引檔案數: $count"
    else
        echo "  目錄不存在"
    fi
    echo ""
}

# 函數：清除表格
clean_tables() {
    echo -e "${YELLOW}🧹 開始清除 skill 表格...${NC}"
    echo ""

    # 檢查資料庫是否存在
    if [ ! -f "$DB_PATH" ]; then
        echo -e "${RED}錯誤：資料庫檔案不存在 - $DB_PATH${NC}"
        exit 1
    fi

    # 備份資料庫
    local backup_path="${DB_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "📦 備份資料庫到: $backup_path"
    cp "$DB_PATH" "$backup_path"
    echo -e "${GREEN}  ✓ 備份完成${NC}"
    echo ""

    # 清除表格（按照外鍵依賴順序）
    echo "清除表格資料..."

    # 1. 清除 skill_chunk_metadata
    echo -n "  1. 清除 skill_chunk_metadata... "
    sqlite3 "$DB_PATH" "DELETE FROM skill_chunk_metadata;"
    echo -e "${GREEN}✓${NC}"

    # 2. 清除 skill_document_mapping
    echo -n "  2. 清除 skill_document_mapping... "
    sqlite3 "$DB_PATH" "DELETE FROM skill_document_mapping;"
    echo -e "${GREEN}✓${NC}"

    # 3. 清除 skill_overviews
    echo -n "  3. 清除 skill_overviews... "
    sqlite3 "$DB_PATH" "DELETE FROM skill_overviews;"
    echo -e "${GREEN}✓${NC}"

    # 4. 清除 skill_metadata
    echo -n "  4. 清除 skill_metadata... "
    sqlite3 "$DB_PATH" "DELETE FROM skill_metadata;"
    echo -e "${GREEN}✓${NC}"

    # 5. 重置 sqlite_sequence
    echo -n "  5. 重置自動遞增序列... "
    sqlite3 "$DB_PATH" "DELETE FROM sqlite_sequence WHERE name LIKE 'skill%';" 2>/dev/null || true
    echo -e "${GREEN}✓${NC}"

    echo ""

    # 清除 FAISS 索引
    echo "清除 FAISS Skills 索引..."
    if [ -d "$FAISS_SKILLS_DIR" ]; then
        local faiss_files=$(find "$FAISS_SKILLS_DIR" -type f \( -name "*.faiss" -o -name "*.pkl" \) 2>/dev/null | wc -l)
        if [ "$faiss_files" -gt 0 ]; then
            echo -n "  刪除 $faiss_files 個索引檔案... "
            find "$FAISS_SKILLS_DIR" -type f \( -name "*.faiss" -o -name "*.pkl" \) -delete 2>/dev/null
            echo -e "${GREEN}✓${NC}"
        else
            echo "  (無索引檔案需要刪除)"
        fi
    else
        echo "  (目錄不存在，跳過)"
    fi

    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ 清除完成！${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""

    # 顯示清除後狀態
    echo "清除後狀態："
    echo "  - skill_metadata:         $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM skill_metadata;")"
    echo "  - skill_chunk_metadata:   $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM skill_chunk_metadata;")"
    echo -e "  - embedding_models:       $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM embedding_models;") ${GREEN}(未修改)${NC}"
    echo ""
    echo "備份檔案位置: $backup_path"
}

# 主程式
main() {
    show_banner
    show_current_status

    # 檢查 --force 參數
    if [ "$1" = "--force" ]; then
        echo -e "${YELLOW}⚠️  使用 --force 模式，跳過確認${NC}"
        echo ""
        clean_tables
    else
        echo -e "${RED}⚠️  警告：此操作將刪除所有 skill 相關資料！${NC}"
        echo ""
        read -p "確定要繼續嗎？ (輸入 'yes' 確認): " confirm

        if [ "$confirm" = "yes" ]; then
            echo ""
            clean_tables
        else
            echo ""
            echo -e "${YELLOW}操作已取消${NC}"
            exit 0
        fi
    fi
}

# 執行主程式
main "$@"
