#!/bin/bash
# =============================================================================
# DocAI Skill Metadata Database Creation Script
# =============================================================================
# 此腳本用於創建全新的 skill_metadata.db 資料庫及所有表格
#
# 使用場景:
#   - 資料庫損壞無法修復時
#   - 首次部署系統時
#   - 需要完全重置 Skill 系統時
#
# 使用方式:
#   chmod +x create_skill_metadata_db.sh
#   ./create_skill_metadata_db.sh           # 創建新資料庫（如已存在會備份）
#   ./create_skill_metadata_db.sh --force   # 強制重建（不詢問確認）
#
# 作者: SuperClaude Framework
# 日期: 2026-01-14
# =============================================================================

set -e

# =============================================================================
# 顏色定義
# =============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# 輔助函數
# =============================================================================
print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}\n"
}

print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_info() { echo -e "${CYAN}ℹ️  $1${NC}"; }

# =============================================================================
# 配置
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_ROOT/data"
DB_PATH="$DATA_DIR/skill_metadata.db"
BACKUP_DIR="$DATA_DIR/backups"

FORCE_MODE=false

# 解析參數
for arg in "$@"; do
    case $arg in
        --force|-f)
            FORCE_MODE=true
            shift
            ;;
    esac
done

# =============================================================================
# 檢查 sqlite3 是否安裝
# =============================================================================
check_sqlite() {
    if ! command -v sqlite3 &> /dev/null; then
        print_error "sqlite3 未安裝"
        echo ""
        echo "請先安裝 sqlite3:"
        echo "  Ubuntu/Debian: sudo apt-get install sqlite3"
        echo "  CentOS/RHEL:   sudo yum install sqlite"
        echo "  macOS:         brew install sqlite3"
        exit 1
    fi
    print_success "sqlite3 已安裝: $(sqlite3 --version)"
}

# =============================================================================
# 備份現有資料庫
# =============================================================================
backup_existing() {
    if [ -f "$DB_PATH" ]; then
        print_warning "發現現有資料庫: $DB_PATH"

        if [ "$FORCE_MODE" = false ]; then
            echo ""
            read -p "是否備份並替換現有資料庫? (y/N): " confirm
            if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
                print_info "操作已取消"
                exit 0
            fi
        fi

        # 創建備份目錄
        mkdir -p "$BACKUP_DIR"

        local backup_name="skill_metadata_$(date +%Y%m%d_%H%M%S).db"
        local backup_path="$BACKUP_DIR/$backup_name"

        print_info "備份現有資料庫到: $backup_path"
        mv "$DB_PATH" "$backup_path"

        # 移除 WAL/SHM 文件
        rm -f "${DB_PATH}-wal" "${DB_PATH}-shm"

        print_success "備份完成"
    fi
}

# =============================================================================
# 創建資料庫和表格
# =============================================================================
create_database() {
    print_header "創建 skill_metadata.db"

    # 確保資料目錄存在
    mkdir -p "$DATA_DIR"

    print_info "資料庫路徑: $DB_PATH"
    echo ""

    # 創建資料庫並執行 SQL
    sqlite3 "$DB_PATH" << 'EOF'
-- =============================================================================
-- DocAI Skill Metadata Database Schema
-- =============================================================================
-- Version: 1.0
-- Created: 2026-01-14
--
-- Tables:
--   1. skill_heads          - Skill 定義（單一真相來源）
--   2. skill_metadata       - Skill 文件/來源資料
--   3. skill_overviews      - LLM 生成的摘要
--   4. skill_document_mapping - Skill 與文件的關聯
--   5. skill_chunk_metadata - Chunk 級別元數據
--   6. processing_jobs      - PDF 處理任務追蹤
-- =============================================================================

-- 啟用 WAL 模式（提升並發性能）
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=10000;
PRAGMA temp_store=MEMORY;
PRAGMA busy_timeout=5000;
PRAGMA wal_autocheckpoint=1000;

-- =============================================================================
-- Table 1: skill_heads - Skill 定義（單一真相來源）
-- =============================================================================
-- 這是 Skill 系統的核心表，定義了所有 Skill 的基本資訊。
-- 每個 Skill Head 可以包含多個文件（透過 skill_metadata.head_id 關聯）
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_heads (
    head_id TEXT PRIMARY KEY,                    -- 唯一識別碼 (格式: head_YYYYMMDD_HHMMSS_uuid)
    skill_name TEXT NOT NULL UNIQUE,             -- Skill 名稱（必須唯一）
    description TEXT,                            -- Skill 描述
    category TEXT DEFAULT 'General',             -- 分類（如: 法律, 程式, 投資）
    display_order INTEGER DEFAULT 0,             -- UI 顯示順序
    enabled BOOLEAN DEFAULT TRUE,                -- 是否啟用
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Table 2: skill_metadata - Skill 文件/來源資料
-- =============================================================================
-- 儲存每個上傳到 Skill 的文件資訊。
-- 每個文件都關聯到一個 skill_head（透過 head_id）
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_metadata (
    skill_id TEXT PRIMARY KEY,                   -- 唯一識別碼 (格式: skill_YYYYMMDD_HHMMSS_uuid_src_XX)
    skill_name TEXT NOT NULL,                    -- Skill 名稱（繼承自 skill_head）
    skill_description TEXT,                      -- 描述
    skill_category TEXT,                         -- 分類
    skill_level TEXT DEFAULT 'intermediate',     -- 難度等級 (beginner|intermediate|advanced)
    tags TEXT,                                   -- 標籤 (JSON array)
    related_skills TEXT,                         -- 相關 Skills (JSON array)
    total_chunks INTEGER DEFAULT 0,              -- Chunk 總數
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,                               -- 額外元數據 (JSON)

    -- 階層結構欄位
    parent_skill_id TEXT DEFAULT 'root',         -- 父級 Skill ID（root 表示主 Skill）
    source_name TEXT,                            -- 來源文件名稱（如: 民法.pdf）
    head_id TEXT,                                -- 關聯的 skill_head ID

    -- 處理狀態追蹤欄位
    processing_status TEXT DEFAULT 'pending',    -- pending|processing|completed|failed
    indexed_chunks INTEGER DEFAULT 0,            -- 已索引的 Chunk 數
    last_error TEXT,                             -- 最後錯誤訊息
    processing_started_at TIMESTAMP,             -- 處理開始時間
    processing_completed_at TIMESTAMP,           -- 處理完成時間

    FOREIGN KEY (head_id) REFERENCES skill_heads(head_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 3: skill_overviews - LLM 生成的摘要
-- =============================================================================
-- 儲存由 LLM 生成的 Skill 概述/摘要
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_overviews (
    skill_id TEXT PRIMARY KEY,                   -- 關聯的 skill_id
    overview TEXT NOT NULL,                      -- LLM 生成的摘要內容
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 4: skill_document_mapping - Skill 與文件的關聯
-- =============================================================================
-- 建立 Skill 與來源文件之間的多對多關係
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_document_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,                      -- 關聯的 skill_id
    file_id TEXT NOT NULL,                       -- 關聯的 file_id（來自 docai.db）
    document_name TEXT,                          -- 文件名稱
    document_path TEXT,                          -- 文件路徑
    total_pages INTEGER DEFAULT 0,               -- 總頁數
    relevance_score REAL DEFAULT 0.0,            -- 相關度分數 (0.0-1.0)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 5: skill_chunk_metadata - Chunk 級別元數據
-- =============================================================================
-- 儲存每個 Chunk 的詳細資訊（可選，用於進階功能）
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_chunk_metadata (
    chunk_id TEXT PRIMARY KEY,                   -- Chunk 唯一識別碼
    skill_id TEXT NOT NULL,                      -- 關聯的 skill_id
    document_id TEXT,                            -- 文件 ID
    document_name TEXT,                          -- 文件名稱
    chunk_index INTEGER NOT NULL,                -- Chunk 在文件中的索引
    chunk_text TEXT,                             -- Chunk 文字內容
    page_number INTEGER,                         -- 來源頁碼
    faiss_index INTEGER,                         -- FAISS 向量索引位置
    embedding_model TEXT,                        -- 使用的 Embedding 模型
    embedding_dimension INTEGER,                 -- Embedding 向量維度
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,                               -- 額外元數據 (JSON)
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 6: processing_jobs - PDF 處理任務追蹤
-- =============================================================================
-- 追蹤大型 PDF 的處理進度，支援斷點續傳
-- =============================================================================
CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id TEXT PRIMARY KEY,                     -- 任務唯一識別碼
    skill_id TEXT NOT NULL,                      -- 關聯的 skill_id
    head_id TEXT,                                -- 關聯的 head_id
    pdf_path TEXT NOT NULL,                      -- PDF 檔案路徑
    pdf_filename TEXT,                           -- PDF 檔案名稱
    pdf_size_bytes INTEGER,                      -- PDF 檔案大小
    total_pages INTEGER DEFAULT 0,               -- PDF 總頁數
    last_processed_page INTEGER DEFAULT 0,       -- 最後處理的頁碼（斷點續傳）
    total_chunks INTEGER DEFAULT 0,              -- 預計 Chunk 總數
    processed_chunks INTEGER DEFAULT 0,          -- 已處理 Chunk 數
    batch_size INTEGER DEFAULT 12,               -- 批次大小
    status TEXT DEFAULT 'pending',               -- pending|processing|completed|failed|paused
    dirty_batches TEXT,                          -- 需要重試的批次 (JSON array)
    retry_count INTEGER DEFAULT 0,               -- 重試次數
    error_message TEXT,                          -- 錯誤訊息
    error_stack TEXT,                            -- 錯誤堆疊
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,                             -- 開始處理時間
    completed_at TEXT,                           -- 完成處理時間
    processing_time_seconds REAL,                -- 總處理時間（秒）
    avg_page_time_ms REAL,                       -- 平均每頁處理時間（毫秒）
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id),
    FOREIGN KEY (head_id) REFERENCES skill_heads(head_id)
);

-- =============================================================================
-- 索引 - 提升查詢效能
-- =============================================================================

-- skill_metadata 索引
CREATE INDEX IF NOT EXISTS idx_skill_category ON skill_metadata(skill_category);
CREATE INDEX IF NOT EXISTS idx_skill_name ON skill_metadata(skill_name);
CREATE INDEX IF NOT EXISTS idx_skill_level ON skill_metadata(skill_level);
CREATE INDEX IF NOT EXISTS idx_skill_head_id ON skill_metadata(head_id);
CREATE INDEX IF NOT EXISTS idx_skill_parent ON skill_metadata(parent_skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_status ON skill_metadata(processing_status);

-- skill_document_mapping 索引
CREATE INDEX IF NOT EXISTS idx_skill_doc_mapping_skill ON skill_document_mapping(skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_doc_mapping_file ON skill_document_mapping(file_id);

-- skill_chunk_metadata 索引
CREATE INDEX IF NOT EXISTS idx_chunk_skill ON skill_chunk_metadata(skill_id);
CREATE INDEX IF NOT EXISTS idx_chunk_index ON skill_chunk_metadata(skill_id, chunk_index);

-- processing_jobs 索引
CREATE INDEX IF NOT EXISTS idx_pj_status ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_pj_skill ON processing_jobs(skill_id);
CREATE INDEX IF NOT EXISTS idx_pj_created ON processing_jobs(created_at);

-- =============================================================================
-- 初始化測試記錄
-- =============================================================================
INSERT INTO skill_heads (head_id, skill_name, description, category, display_order, enabled)
VALUES (
    'head_init_test',
    '_system_init_test',
    'Database initialization test record - can be safely deleted',
    'System',
    999,
    FALSE
);

EOF

    print_success "資料庫創建成功"
}

# =============================================================================
# 驗證資料庫
# =============================================================================
verify_database() {
    print_header "驗證資料庫"

    # 完整性檢查
    local integrity=$(sqlite3 "$DB_PATH" "PRAGMA integrity_check;")
    if [ "$integrity" = "ok" ]; then
        print_success "完整性檢查: 通過"
    else
        print_error "完整性檢查: 失敗 - $integrity"
        return 1
    fi

    # 列出所有表格
    echo ""
    print_info "已創建的表格:"
    sqlite3 "$DB_PATH" ".tables" | while read line; do
        echo "  📋 $line"
    done

    # 列出所有索引
    echo ""
    print_info "已創建的索引:"
    sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';" | while read index; do
        echo "  🔍 $index"
    done

    # 顯示表格結構摘要
    echo ""
    print_info "表格結構摘要:"
    echo ""

    for table in skill_heads skill_metadata skill_overviews skill_document_mapping skill_chunk_metadata processing_jobs; do
        local count=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM $table;" 2>/dev/null || echo "0")
        local columns=$(sqlite3 "$DB_PATH" "PRAGMA table_info($table);" 2>/dev/null | wc -l)
        echo "  📊 $table: $columns 個欄位, $count 筆記錄"
    done

    print_success "資料庫驗證完成"
}

# =============================================================================
# 顯示使用說明
# =============================================================================
show_usage_info() {
    print_header "使用說明"

    cat << EOF
資料庫已成功創建！以下是相關資訊:

📁 資料庫位置:
   $DB_PATH

🔧 表格說明:
   • skill_heads          - Skill 定義（主表）
   • skill_metadata       - Skill 文件資料
   • skill_overviews      - LLM 生成摘要
   • skill_document_mapping - Skill-文件關聯
   • skill_chunk_metadata - Chunk 詳細資料
   • processing_jobs      - 處理任務追蹤

📝 下一步:
   1. 重新啟動 DocAI: python main.py
   2. 上傳 PDF 建立新的 Skills
   3. 或從備份還原資料

⚠️  注意事項:
   • 此操作會建立全新空白資料庫
   • 原有的 Skill 資料需要重新建立
   • FAISS 向量索引需要配合重建

📂 備份位置:
   $BACKUP_DIR/

EOF
}

# =============================================================================
# 主函數
# =============================================================================
main() {
    print_header "DocAI Skill Metadata 資料庫創建工具"

    # 檢查 sqlite3
    check_sqlite
    echo ""

    # 切換到專案目錄
    cd "$PROJECT_ROOT"
    print_info "專案目錄: $PROJECT_ROOT"

    # 備份現有資料庫
    backup_existing

    # 創建資料庫
    create_database

    # 驗證資料庫
    verify_database

    # 顯示使用說明
    show_usage_info

    print_success "skill_metadata.db 創建完成！"
}

# 執行主函數
main "$@"
