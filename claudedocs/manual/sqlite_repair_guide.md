# DocAI SQLite 資料庫修復與重建指南

> **版本**: 1.0  
> **最後更新**: 2026-01-14  
> **適用範圍**: SQLite 資料庫故障排除

---

## 目錄

1. [概述](#概述)
2. [腳本清單](#腳本清單)
3. [錯誤診斷](#錯誤診斷)
4. [修復流程](#修復流程)
5. [重建資料庫](#重建資料庫)
6. [skill_metadata.db 結構說明](#skill_metadatadb-結構說明)
7. [常見問題](#常見問題)

---

## 概述

DocAI 使用兩個 SQLite 資料庫：

| 資料庫 | 用途 | 位置 |
|--------|------|------|
| `skill_metadata.db` | Skill 系統元數據 | `data/skill_metadata.db` |
| `docai.db` | File 系統元數據 | `data/docai.db` |

本指南說明如何診斷和修復 SQLite 資料庫損壞問題。

---

## 腳本清單

| 腳本 | 用途 | 使用時機 |
|------|------|----------|
| `repair_sqlite.sh` | 自動修復損壞的資料庫 | 出現 "database disk image is malformed" 錯誤時 |
| `create_skill_metadata_db.sh` | 重建全新的 skill_metadata.db | 修復失敗或需要完全重置時 |

---

## 錯誤診斷

### 常見錯誤訊息

#### 錯誤 1: database disk image is malformed

```
2026-01-14 16:17:38,032 - aiosqlite - DEBUG - returning exception database disk image is malformed
```

**原因**:
- 意外關機或斷電
- 磁碟空間不足
- 並發寫入衝突
- 檔案在使用中被複製

**解決**: 使用 `repair_sqlite.sh`

#### 錯誤 2: database is locked

```
sqlite3.OperationalError: database is locked
```

**原因**:
- 多個進程同時訪問資料庫
- 前一個連接未正確關閉

**解決**:
```bash
# 找出佔用資料庫的進程
lsof data/skill_metadata.db

# 重啟 DocAI 服務
pkill -f "python main.py"
python main.py
```

#### 錯誤 3: unable to open database file

```
sqlite3.OperationalError: unable to open database file
```

**原因**:
- 資料庫檔案不存在
- 目錄權限不足

**解決**:
```bash
# 檢查檔案是否存在
ls -la data/

# 檢查權限
chmod 755 data/
chmod 644 data/*.db

# 如果不存在，創建新資料庫
./scripts/create_skill_metadata_db.sh
```

---

## 修復流程

### 自動修復（推薦）

```bash
# 進入專案目錄
cd /path/to/DocAI

# 執行修復腳本
./scripts/repair_sqlite.sh
```

### 修復特定資料庫

```bash
# 只修復 skill_metadata.db
./scripts/repair_sqlite.sh skill_metadata.db

# 只修復 docai.db
./scripts/repair_sqlite.sh docai.db
```

### 修復流程說明

腳本會依序嘗試三種修復方法：

```
┌─────────────────────────────────────────────────────────────────┐
│                    SQLite 修復流程                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 完整性檢查                                                   │
│     └─→ PRAGMA integrity_check                                  │
│         ├─ ok → 資料庫正常，結束                                 │
│         └─ malformed → 繼續修復                                  │
│                                                                 │
│  2. 備份損壞資料庫                                               │
│     └─→ data/backups/YYYYMMDD_HHMMSS/                          │
│                                                                 │
│  3. 方法 1: .recover 命令 (SQLite 3.29+)                        │
│     └─→ sqlite3 db.db ".recover" | sqlite3 db_new.db           │
│         ├─ 成功 → 替換原檔案，結束                               │
│         └─ 失敗 → 嘗試方法 2                                     │
│                                                                 │
│  4. 方法 2: .dump + 重建                                        │
│     └─→ sqlite3 db.db ".dump" > dump.sql                       │
│     └─→ sqlite3 db_new.db < dump.sql                           │
│         ├─ 成功 → 替換原檔案，結束                               │
│         └─ 失敗 → 嘗試方法 3                                     │
│                                                                 │
│  5. 方法 3: 表級別修復                                           │
│     └─→ 逐表提取結構和資料                                       │
│     └─→ 重建到新資料庫                                          │
│         ├─ 部分成功 → 使用部分修復的資料庫                        │
│         └─ 全部失敗 → 建議重建                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 預期輸出

```
═══════════════════════════════════════════════════════════════════
  DocAI SQLite 資料庫修復工具
═══════════════════════════════════════════════════════════════════

✅ sqlite3 已安裝: 3.40.1

ℹ️  專案目錄: /home/user/DocAI
ℹ️  資料目錄: /home/user/DocAI/data

═══════════════════════════════════════════════════════════════════
  修復資料庫: skill_metadata.db
═══════════════════════════════════════════════════════════════════

ℹ️  檢查資料庫完整性: skill_metadata.db
❌ skill_metadata.db 完整性檢查失敗: database disk image is malformed

ℹ️  備份損壞的資料庫到: data/backups/20260114_163000/skill_metadata.db.corrupted
✅ 備份完成

ℹ️  開始修復流程...

ℹ️  嘗試方法 1: 使用 .recover 命令修復
✅ 方法 1 成功: 資料庫已修復

═══════════════════════════════════════════════════════════════════
  修復摘要
═══════════════════════════════════════════════════════════════════

  成功: 1
  失敗: 0

  備份位置: data/backups/20260114_163000/

✅ 所有資料庫修復完成！
```

---

## 重建資料庫

### 何時需要重建

- 修復腳本所有方法都失敗
- 需要完全重置 Skill 系統
- 首次部署系統

### 執行重建

```bash
# 標準模式（會詢問確認）
./scripts/create_skill_metadata_db.sh

# 強制模式（不詢問）
./scripts/create_skill_metadata_db.sh --force
```

### 重建流程

```
1. 檢查 sqlite3 是否安裝
2. 備份現有資料庫（如存在）→ data/backups/
3. 創建新資料庫並執行 Schema
4. 驗證資料庫完整性
5. 顯示使用說明
```

### 預期輸出

```
═══════════════════════════════════════════════════════════════════
  DocAI Skill Metadata 資料庫創建工具
═══════════════════════════════════════════════════════════════════

✅ sqlite3 已安裝: 3.40.1

ℹ️  專案目錄: /home/user/DocAI
⚠️  發現現有資料庫: data/skill_metadata.db

是否備份並替換現有資料庫? (y/N): y

ℹ️  備份現有資料庫到: data/backups/skill_metadata_20260114_163500.db
✅ 備份完成

═══════════════════════════════════════════════════════════════════
  創建 skill_metadata.db
═══════════════════════════════════════════════════════════════════

ℹ️  資料庫路徑: data/skill_metadata.db

✅ 資料庫創建成功

═══════════════════════════════════════════════════════════════════
  驗證資料庫
═══════════════════════════════════════════════════════════════════

✅ 完整性檢查: 通過

ℹ️  已創建的表格:
  📋 skill_heads skill_metadata skill_overviews
  📋 skill_document_mapping skill_chunk_metadata processing_jobs

ℹ️  已創建的索引:
  🔍 idx_skill_category
  🔍 idx_skill_name
  🔍 idx_skill_level
  ...

ℹ️  表格結構摘要:

  📊 skill_heads: 9 個欄位, 1 筆記錄
  📊 skill_metadata: 18 個欄位, 0 筆記錄
  📊 skill_overviews: 4 個欄位, 0 筆記錄
  📊 skill_document_mapping: 5 個欄位, 0 筆記錄
  📊 skill_chunk_metadata: 9 個欄位, 0 筆記錄
  📊 processing_jobs: 21 個欄位, 0 筆記錄

✅ 資料庫驗證完成

✅ skill_metadata.db 創建完成！
```

---

## skill_metadata.db 結構說明

### Table 1: skill_heads（Skill 定義）

```sql
CREATE TABLE skill_heads (
    head_id TEXT PRIMARY KEY,        -- 唯一識別碼
    skill_name TEXT NOT NULL UNIQUE, -- Skill 名稱
    description TEXT,                -- 描述
    category TEXT DEFAULT 'General', -- 分類
    display_order INTEGER DEFAULT 0, -- 顯示順序
    enabled BOOLEAN DEFAULT TRUE,    -- 是否啟用
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**用途**: 定義 Skill 的基本資訊，是整個 Skill 系統的「單一真相來源」

### Table 2: skill_metadata（文件資料）

```sql
CREATE TABLE skill_metadata (
    skill_id TEXT PRIMARY KEY,       -- 文件唯一識別碼
    skill_name TEXT NOT NULL,        -- Skill 名稱
    total_chunks INTEGER DEFAULT 0,  -- Chunk 數量
    head_id TEXT,                    -- 關聯的 skill_head
    parent_skill_id TEXT,            -- 父級 ID（階層結構）
    source_name TEXT,                -- 來源文件名
    processing_status TEXT,          -- 處理狀態
    ...
    FOREIGN KEY (head_id) REFERENCES skill_heads(head_id)
);
```

**用途**: 儲存上傳到 Skill 的每個 PDF 文件資訊

### Table 3: skill_overviews（LLM 摘要）

```sql
CREATE TABLE skill_overviews (
    skill_id TEXT PRIMARY KEY,
    overview TEXT NOT NULL,          -- LLM 生成的摘要
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**用途**: 儲存 LLM 生成的 Skill 概述

### Table 4: skill_document_mapping（關聯表）

```sql
CREATE TABLE skill_document_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    relevance_score REAL DEFAULT 0.0
);
```

**用途**: 建立 Skill 與來源文件的關聯

### Table 5: skill_chunk_metadata（Chunk 資料）

```sql
CREATE TABLE skill_chunk_metadata (
    chunk_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT,
    page_number INTEGER,
    faiss_index INTEGER
);
```

**用途**: 儲存每個 Chunk 的詳細資訊

### Table 6: processing_jobs（任務追蹤）

```sql
CREATE TABLE processing_jobs (
    job_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    pdf_path TEXT NOT NULL,
    total_pages INTEGER,
    last_processed_page INTEGER,     -- 斷點續傳
    status TEXT,                     -- pending|processing|completed|failed
    ...
);
```

**用途**: 追蹤大型 PDF 的處理進度，支援斷點續傳

### 索引清單

| 索引名稱 | 表格 | 欄位 |
|----------|------|------|
| `idx_skill_category` | skill_metadata | skill_category |
| `idx_skill_name` | skill_metadata | skill_name |
| `idx_skill_level` | skill_metadata | skill_level |
| `idx_skill_head_id` | skill_metadata | head_id |
| `idx_skill_parent` | skill_metadata | parent_skill_id |
| `idx_skill_status` | skill_metadata | processing_status |
| `idx_skill_doc_mapping_skill` | skill_document_mapping | skill_id |
| `idx_skill_doc_mapping_file` | skill_document_mapping | file_id |
| `idx_chunk_skill` | skill_chunk_metadata | skill_id |
| `idx_pj_status` | processing_jobs | status |
| `idx_pj_skill` | processing_jobs | skill_id |

---

## 常見問題

### Q1: 修復後資料遺失怎麼辦？

修復過程會自動備份到 `data/backups/` 目錄。如需還原：

```bash
# 查看備份
ls -la data/backups/

# 還原備份
cp data/backups/20260114_163000/skill_metadata.db.corrupted data/skill_metadata.db
```

### Q2: 重建資料庫後，原有 Skills 怎麼辦？

重建資料庫會清空所有 Skill 資料。你需要：

1. 重新上傳 PDF 建立 Skills
2. FAISS 向量索引也需要重建（上傳 PDF 時會自動建立）

### Q3: 如何預防資料庫損壞？

1. **正常關閉服務**: 使用 Ctrl+C 或 `pkill` 而非強制終止
2. **確保磁碟空間**: 保持至少 1GB 可用空間
3. **避免並發寫入**: 不要同時運行多個 DocAI 實例
4. **定期備份**: 設置自動備份任務

```bash
# 手動備份
cp data/skill_metadata.db data/backups/skill_metadata_$(date +%Y%m%d).db
```

### Q4: Windows 環境如何執行這些腳本？

使用 Git Bash 或 WSL：

```bash
# Git Bash
cd /c/Users/username/DocAI
./scripts/repair_sqlite.sh

# PowerShell (需要安裝 sqlite3)
sqlite3 data\skill_metadata.db "PRAGMA integrity_check;"
```

---

## 快速參考

### 修復命令速查

```bash
# 檢查完整性
sqlite3 data/skill_metadata.db "PRAGMA integrity_check;"

# 自動修復
./scripts/repair_sqlite.sh

# 重建資料庫
./scripts/create_skill_metadata_db.sh --force

# 手動備份
cp data/skill_metadata.db data/backups/skill_metadata_backup.db

# 刪除 WAL 文件（解決 locked 問題）
rm -f data/skill_metadata.db-wal data/skill_metadata.db-shm
```

---

*文檔版本: 1.0 | 最後更新: 2026-01-14*
