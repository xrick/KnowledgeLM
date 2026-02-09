#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# DocAI Skill Metadata Database Creation Script (Windows/Python)
# =============================================================================
# 此腳本用於創建全新的 skill_metadata.db 資料庫及所有表格
#
# 使用方式:
#   python scripts/create_skill_metadata_db.py           # 創建新資料庫（如已存在會備份）
#   python scripts/create_skill_metadata_db.py --force    # 強制重建（不詢問確認）
# =============================================================================

import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime
import shutil

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# =============================================================================
# 配置
# =============================================================================
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "skill_metadata.db"
BACKUP_DIR = DATA_DIR / "backups"

FORCE_MODE = "--force" in sys.argv or "-f" in sys.argv

# =============================================================================
# 輔助函數
# =============================================================================
def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")

def print_success(text):
    print(f"✅ {text}")

def print_warning(text):
    print(f"⚠️  {text}")

def print_error(text):
    print(f"❌ {text}")

def print_info(text):
    print(f"ℹ️  {text}")

# =============================================================================
# 備份現有資料庫
# =============================================================================
def backup_existing():
    if DB_PATH.exists():
        print_warning(f"發現現有資料庫: {DB_PATH}")

        if not FORCE_MODE:
            response = input("是否備份並替換現有資料庫? (y/N): ")
            if response.lower() != 'y':
                print_info("操作已取消")
                sys.exit(0)

        # 創建備份目錄
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        backup_name = f"skill_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = BACKUP_DIR / backup_name

        print_info(f"備份現有資料庫到: {backup_path}")
        shutil.move(str(DB_PATH), str(backup_path))

        # 移除 WAL/SHM 文件
        wal_path = Path(str(DB_PATH) + "-wal")
        shm_path = Path(str(DB_PATH) + "-shm")
        if wal_path.exists():
            wal_path.unlink()
        if shm_path.exists():
            shm_path.unlink()

        print_success("備份完成")

# =============================================================================
# 創建資料庫和表格
# =============================================================================
def create_database():
    print_header("創建 skill_metadata.db")

    # 確保資料目錄存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print_info(f"資料庫路徑: {DB_PATH}")
    print()

    # 連接資料庫
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 執行 SQL 語句
    sql_script = """
-- =============================================================================
-- DocAI Skill Metadata Database Schema
-- =============================================================================
-- Version: 1.0
-- Created: 2026-01-14
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
CREATE TABLE IF NOT EXISTS skill_heads (
    head_id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL UNIQUE,
    description TEXT,
    category TEXT DEFAULT 'General',
    display_order INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Table 2: skill_metadata - Skill 文件/來源資料
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_metadata (
    skill_id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    skill_description TEXT,
    skill_category TEXT,
    skill_level TEXT DEFAULT 'intermediate',
    tags TEXT,
    related_skills TEXT,
    total_chunks INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,
    parent_skill_id TEXT DEFAULT 'root',
    source_name TEXT,
    head_id TEXT,
    processing_status TEXT DEFAULT 'pending',
    indexed_chunks INTEGER DEFAULT 0,
    last_error TEXT,
    processing_started_at TIMESTAMP,
    processing_completed_at TIMESTAMP,
    FOREIGN KEY (head_id) REFERENCES skill_heads(head_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 3: skill_overviews - LLM 生成的摘要
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_overviews (
    skill_id TEXT PRIMARY KEY,
    overview TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 4: skill_document_mapping - Skill 與文件的關聯
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_document_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    document_name TEXT,
    document_path TEXT,
    total_pages INTEGER DEFAULT 0,
    relevance_score REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 5: skill_chunk_metadata - Chunk 級別元數據
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_chunk_metadata (
    chunk_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    document_id TEXT,
    document_name TEXT,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT,
    page_number INTEGER,
    faiss_index INTEGER,
    embedding_model TEXT,
    embedding_dimension INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 6: processing_jobs - PDF 處理任務追蹤
-- =============================================================================
CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    head_id TEXT,
    pdf_path TEXT NOT NULL,
    pdf_filename TEXT,
    pdf_size_bytes INTEGER,
    total_pages INTEGER DEFAULT 0,
    last_processed_page INTEGER DEFAULT 0,
    total_chunks INTEGER DEFAULT 0,
    processed_chunks INTEGER DEFAULT 0,
    batch_size INTEGER DEFAULT 12,
    status TEXT DEFAULT 'pending',
    dirty_batches TEXT,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    error_stack TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    completed_at TEXT,
    processing_time_seconds REAL,
    avg_page_time_ms REAL,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id),
    FOREIGN KEY (head_id) REFERENCES skill_heads(head_id)
);

-- =============================================================================
-- 索引 - 提升查詢效能
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_skill_category ON skill_metadata(skill_category);
CREATE INDEX IF NOT EXISTS idx_skill_name ON skill_metadata(skill_name);
CREATE INDEX IF NOT EXISTS idx_skill_level ON skill_metadata(skill_level);
CREATE INDEX IF NOT EXISTS idx_skill_head_id ON skill_metadata(head_id);
CREATE INDEX IF NOT EXISTS idx_skill_parent ON skill_metadata(parent_skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_status ON skill_metadata(processing_status);

CREATE INDEX IF NOT EXISTS idx_skill_doc_mapping_skill ON skill_document_mapping(skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_doc_mapping_file ON skill_document_mapping(file_id);

CREATE INDEX IF NOT EXISTS idx_chunk_skill ON skill_chunk_metadata(skill_id);
CREATE INDEX IF NOT EXISTS idx_chunk_index ON skill_chunk_metadata(skill_id, chunk_index);

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
    0
);
"""

    # 執行 SQL 腳本
    cursor.executescript(sql_script)
    conn.commit()
    conn.close()

    print_success("資料庫創建成功")

# =============================================================================
# 驗證資料庫
# =============================================================================
def verify_database():
    print_header("驗證資料庫")

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 完整性檢查
    cursor.execute("PRAGMA integrity_check;")
    integrity = cursor.fetchone()[0]
    if integrity == "ok":
        print_success("完整性檢查: 通過")
    else:
        print_error(f"完整性檢查: 失敗 - {integrity}")
        conn.close()
        return False

    # 列出所有表格
    print()
    print_info("已創建的表格:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    for row in cursor.fetchall():
        print(f"  📋 {row[0]}")

    # 列出所有索引
    print()
    print_info("已創建的索引:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    for row in cursor.fetchall():
        print(f"  🔍 {row[0]}")

    # 顯示表格結構摘要
    print()
    print_info("表格結構摘要:")
    print()

    tables = ['skill_heads', 'skill_metadata', 'skill_overviews', 
              'skill_document_mapping', 'skill_chunk_metadata', 'processing_jobs']
    
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            cursor.execute(f"PRAGMA table_info({table});")
            columns = len(cursor.fetchall())
            print(f"  📊 {table}: {columns} 個欄位, {count} 筆記錄")
        except Exception as e:
            print(f"  ⚠️  {table}: 無法讀取 - {e}")

    conn.close()
    print_success("資料庫驗證完成")
    return True

# =============================================================================
# 顯示使用說明
# =============================================================================
def show_usage_info():
    print_header("使用說明")

    print(f"""
資料庫已成功創建！以下是相關資訊:

📁 資料庫位置:
   {DB_PATH}

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
   {BACKUP_DIR}/
""")

# =============================================================================
# 主函數
# =============================================================================
def main():
    print_header("DocAI Skill Metadata 資料庫創建工具")

    # 切換到專案目錄
    os.chdir(PROJECT_ROOT)
    print_info(f"專案目錄: {PROJECT_ROOT}")

    # 備份現有資料庫
    backup_existing()

    # 創建資料庫
    create_database()

    # 驗證資料庫
    if verify_database():
        # 顯示使用說明
        show_usage_info()
        print_success("skill_metadata.db 創建完成！")
    else:
        print_error("資料庫驗證失敗，請檢查錯誤訊息")
        sys.exit(1)

if __name__ == "__main__":
    main()
