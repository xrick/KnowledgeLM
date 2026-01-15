<!-- claudedocs/specs/docai_database_api_20251216.md -->
<!-- claudedocs/docai_database_api_20251216.md -->
# DocAI Database & API Reference - 資料庫與 API 文件

## 概述

本文檔詳細描述 DocAI 系統使用的兩種資料庫（SQLite、FAISS）的結構、欄位定義，以及操作這些資料庫的函式。

---

## 資料庫總覽

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DocAI Data Storage                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────┐    ┌─────────────────────────────┐    │
│  │        SQLite               │    │          FAISS              │    │
│  │   (Relational Metadata)     │    │   (Vector Indices)          │    │
│  │                             │    │                             │    │
│  │  skill_metadata.db          │    │  data/faiss_indices/        │    │
│  │  ├── skill_heads           │    │  ├── skills/                │    │
│  │  ├── skill_metadata        │    │  │   ├── skill_xxx/         │    │
│  │  ├── skill_document_mapping│    │  │   │   ├── index.faiss   │    │
│  │  ├── skill_chunk_metadata  │    │  │   │   └── index.pkl     │    │
│  │  ├── skill_overviews       │    │  │   └── skill_yyy/         │    │
│  │  └── processing_jobs       │    │  └── files/ (legacy)        │    │
│  └─────────────────────────────┘    └─────────────────────────────┘    │
│                                                                         │
│  用途：關聯式元資料管理               用途：向量相似度搜尋               │
│  技術：aiosqlite (async)              技術：FAISS + LangChain           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: SQLite Database

### 資料庫位置
```
./data/skill_metadata.db
```

### 連線配置
```python
# skill_metadata_provider/client.py Line 70-88
conn = await aiosqlite.connect(
    str(self.db_path),
    timeout=30.0,              # 等待鎖定最多 30 秒
    check_same_thread=False    # 允許跨執行緒存取
)

# 效能優化設定
await conn.execute("PRAGMA journal_mode=WAL")      # Write-Ahead Logging
await conn.execute("PRAGMA synchronous=NORMAL")   # 較快寫入
await conn.execute("PRAGMA cache_size=10000")     # 10MB 快取
await conn.execute("PRAGMA temp_store=MEMORY")    # 記憶體暫存表
```

---

### Table 1: `skill_heads`

**用途**：技能群組定義（Single Source of Truth）

**Schema**:
```sql
CREATE TABLE skill_heads (
    head_id TEXT PRIMARY KEY,          -- 主鍵，格式: head_yyyymmdd_hhmmss_xxxxxxxx
    skill_name TEXT NOT NULL UNIQUE,   -- 技能名稱（唯一）
    description TEXT,                  -- 描述
    category TEXT DEFAULT 'General',   -- 分類
    display_order INTEGER DEFAULT 0,   -- 顯示順序
    enabled BOOLEAN DEFAULT TRUE,      -- 是否啟用
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**範例資料**:
| head_id | skill_name | category | display_order | enabled |
|---------|------------|----------|---------------|---------|
| head_20251126_xxx | 大語言模型大全 | AI | 0 | TRUE |
| head_20251127_yyy | 六法全書-民法 | Legal | 1 | TRUE |

---

### Table 2: `skill_metadata`

**用途**：技能詳細資訊與文檔關聯

**Schema**:
```sql
CREATE TABLE skill_metadata (
    skill_id TEXT PRIMARY KEY,           -- 主鍵，格式: skill_yyyymmdd_hhmmss_xxxxxxxx
    skill_name TEXT NOT NULL,            -- 技能名稱
    skill_description TEXT,              -- 描述
    skill_category TEXT,                 -- 分類
    skill_level TEXT DEFAULT 'intermediate',  -- 難度等級
    tags TEXT,                           -- JSON 標籤陣列
    related_skills TEXT,                 -- JSON 相關技能陣列
    total_chunks INTEGER DEFAULT 0,      -- 總 chunks 數
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    metadata TEXT,                       -- JSON 額外元資料
    head_id TEXT REFERENCES skill_heads(head_id),  -- 關聯 skill_heads
    parent_skill_id TEXT DEFAULT 'root', -- 父技能（用於階層結構）
    source_name TEXT                     -- 來源檔案名稱
);

-- 索引
CREATE INDEX idx_skill_category ON skill_metadata(skill_category);
CREATE INDEX idx_skill_name ON skill_metadata(skill_name);
CREATE INDEX idx_skill_head_id ON skill_metadata(head_id);
```

**`metadata` 欄位 JSON 結構**:
```json
{
    "source_file": "/uploadfiles/pdf/LLM_Handbook.pdf",
    "file_size": 2456789,
    "total_pages": 385,
    "processing_time": 45.2,
    "embedding_model": "BAAI/bge-m3",
    "embedding_dimension": 1024
}
```

---

### Table 3: `skill_document_mapping`

**用途**：技能與文檔的多對多映射

**Schema**:
```sql
CREATE TABLE skill_document_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,              -- 技能 ID
    file_id TEXT NOT NULL,               -- 文檔 ID
    document_name TEXT,                  -- 文檔名稱
    document_path TEXT,                  -- 文檔路徑
    total_pages INTEGER,                 -- 總頁數
    relevance_score REAL DEFAULT 0.0,    -- 相關度分數
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX idx_skill_doc_mapping_skill ON skill_document_mapping(skill_id);
CREATE INDEX idx_skill_doc_mapping_file ON skill_document_mapping(file_id);
```

---

### Table 4: `skill_chunk_metadata`

**用途**：儲存每個文本分塊的詳細資訊

**Schema**:
```sql
CREATE TABLE skill_chunk_metadata (
    chunk_id TEXT PRIMARY KEY,           -- 分塊 ID
    skill_id TEXT NOT NULL,              -- 所屬技能 ID
    document_id TEXT,                    -- 文檔 ID
    document_name TEXT,                  -- 文檔名稱
    page_number INTEGER,                 -- 頁碼
    chunk_index INTEGER,                 -- 分塊索引
    chunk_text TEXT,                     -- 分塊文本（前 2000 字）
    embedding_model TEXT,                -- 嵌入模型
    embedding_dimension INTEGER,         -- 向量維度
    metadata TEXT,                       -- JSON 額外元資料
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id)
);
```

---

### Table 5: `processing_jobs`

**用途**：追蹤大型 PDF 處理任務（支援斷點續傳）

**Schema**:
```sql
CREATE TABLE processing_jobs (
    job_id TEXT PRIMARY KEY,             -- 任務 ID
    skill_id TEXT NOT NULL,              -- 技能 ID
    head_id TEXT,                        -- 技能群組 ID
    pdf_path TEXT NOT NULL,              -- PDF 檔案路徑
    pdf_filename TEXT,                   -- 檔案名稱
    pdf_size_bytes INTEGER,              -- 檔案大小
    total_pages INTEGER DEFAULT 0,       -- 總頁數
    last_processed_page INTEGER DEFAULT 0,  -- 最後處理頁碼
    total_chunks INTEGER DEFAULT 0,      -- 總分塊數
    processed_chunks INTEGER DEFAULT 0,  -- 已處理分塊數
    batch_size INTEGER DEFAULT 12,       -- 批次大小
    status TEXT DEFAULT 'pending',       -- 狀態: pending/processing/completed/failed
    dirty_batches TEXT,                  -- JSON 髒批次清單
    retry_count INTEGER DEFAULT 0,       -- 重試次數
    error_message TEXT,                  -- 錯誤訊息
    error_stack TEXT,                    -- 錯誤堆疊
    created_at TEXT,
    updated_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    processing_time_seconds REAL,        -- 處理時間（秒）
    avg_page_time_ms REAL,               -- 平均每頁處理時間
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id),
    FOREIGN KEY (head_id) REFERENCES skill_heads(head_id)
);

-- 索引
CREATE INDEX idx_pj_status ON processing_jobs(status);
CREATE INDEX idx_pj_skill ON processing_jobs(skill_id);
CREATE INDEX idx_pj_created ON processing_jobs(created_at);
```

---

## Part 2: FAISS Vector Store

### 目錄結構
```
data/faiss_indices/
├── skills/                          # 技能向量索引
│   ├── skill_20251126_105138_b8cc08c1/
│   │   ├── index.faiss             # FAISS 二進位索引
│   │   └── index.pkl               # 元資料（pickle）
│   ├── skill_20251127_xxx/
│   │   ├── index.faiss
│   │   └── index.pkl
│   └── ...
│
└── files/                           # Legacy 檔案索引
    └── (保留相容性)
```

### 索引結構

**index.faiss**:
- 格式：FAISS IndexFlatL2（L2 距離）
- 向量維度：1024（BGE-M3）
- 儲存：二進位格式

**index.pkl**:
- 格式：Python pickle
- 內容：LangChain DocStore（文本 + 元資料映射）

### 元資料結構（index.pkl 內）
```python
{
    "docstore": {
        "doc_uuid_001": {
            "page_content": "這是第一個文本分塊的內容...",
            "metadata": {
                "skill_id": "skill_20251126_xxx",
                "chunk_index": 0,
                "page_number": 1,
                "document_name": "LLM_Handbook",
                "content_id": "skill_20251126_xxx"
            }
        },
        "doc_uuid_002": {
            "page_content": "這是第二個文本分塊...",
            "metadata": {...}
        }
    },
    "index_to_docstore_id": {
        0: "doc_uuid_001",
        1: "doc_uuid_002",
        ...
    }
}
```

---

## Part 3: 資料庫操作函式

### SQLite 操作函式

#### SkillMetadataProvider (`skill_metadata_provider/client.py`)

| 函式 | 行號 | 操作類型 | 說明 |
|------|------|----------|------|
| `initialize_database()` | 108 | CREATE | 建立所有資料表 |
| `create_skill()` | 272 | INSERT | 建立技能記錄 |
| `get_skill()` | 334 | SELECT | 獲取單一技能 |
| `list_skills()` | 391 | SELECT | 列出所有技能 |
| `update_skill()` | 472 | UPDATE | 更新技能資訊 |
| `delete_skill()` | 517 | DELETE | 刪除技能 |
| `create_skill_head()` | 955 | INSERT | 建立技能群組 |
| `get_skill_head()` | 992 | SELECT | 獲取技能群組 |
| `list_skill_heads()` | 1057 | SELECT | 列出所有群組 |
| `update_skill_head()` | 1101 | UPDATE | 更新群組資訊 |
| `delete_skill_head()` | 1136 | DELETE | 刪除群組 |
| `get_skill_tree()` | 1201 | SELECT | 獲取完整樹結構 |
| `get_documents_for_skill()` | 858 | SELECT | 獲取技能的文檔 |
| `update_processing_status()` | 1422 | UPDATE | 更新處理狀態 |
| `get_processing_job()` | 1462 | SELECT | 獲取處理任務 |

#### skills.py 直接 SQLite 操作

| 位置 | 操作 | 說明 |
|------|------|------|
| Line 1134 | INSERT | 存儲文檔映射 + chunk 元資料 |
| Line 1690 | INSERT/REPLACE | SSE 上傳時存儲元資料 |
| Line 2037 | SELECT | 刪除時查詢 skill_ids |
| Line 2075 | DELETE | 刪除 skill_chunk_metadata |
| Line 2816 | UPDATE | 重命名技能 |
| Line 2951 | DELETE | 完整刪除技能相關記錄 |

---

### FAISS 操作函式

#### VectorStoreProvider (`vector_store_provider/client.py`)

| 函式 | 行號 | 操作類型 | 說明 |
|------|------|----------|------|
| `_save_faiss_store()` | 74 | WRITE | 儲存 FAISS 索引到磁碟 |
| `_load_faiss_store()` | 106 | READ | 從磁碟載入 FAISS 索引 |
| `_load_all_faiss_stores()` | 147 | READ | 啟動時載入所有索引 |
| `create_store_from_texts()` | - | CREATE | 從文本建立新索引 |
| `similarity_search()` | - | SEARCH | 相似度搜尋（無分數）|
| `similarity_search_with_score()` | - | SEARCH | 相似度搜尋（含分數）|
| `delete_store()` | - | DELETE | 刪除索引 |

#### SkillRetrievalService (`skill_retrieval_service.py`)

| 函式 | 行號 | 操作類型 | 說明 |
|------|------|----------|------|
| `add_content()` | 39 | CREATE | 新增技能向量到 FAISS |
| `retrieve_context()` | 81 | SEARCH | 檢索相關上下文 |
| `delete_content()` | 135 | DELETE | 刪除技能向量索引 |

---

## Part 4: 為何需要這些資料庫操作

### SQLite 操作需求

| 操作 | 為何需要 |
|------|----------|
| **CREATE skill** | 當使用者上傳 PDF 時，需要記錄技能的基本資訊（名稱、分類、chunks 數）以便在 UI 顯示和管理 |
| **READ skill_tree** | 前端技能樹需要完整的階層結構（Head → Documents → Chunks）來渲染 sidebar |
| **UPDATE processing_status** | 長時間 PDF 處理需要追蹤進度，支援斷點續傳和錯誤恢復 |
| **DELETE cascade** | 刪除技能時需要連帶刪除所有相關的文檔映射和 chunk 元資料，保持資料一致性 |
| **INSERT chunk_metadata** | 儲存每個分塊的頁碼和文本，用於查詢結果中顯示引用來源（citation）|

### FAISS 操作需求

| 操作 | 為何需要 |
|------|----------|
| **CREATE store** | 將 PDF 文本轉換為向量並建立索引，這是 RAG 檢索的核心 |
| **SEARCH similarity** | 根據使用者查詢找到最相關的文本分塊，實現語意搜尋 |
| **LOAD on startup** | 伺服器啟動時預載所有索引到記憶體，加速查詢回應 |
| **SAVE persistence** | 將記憶體中的索引持久化到磁碟，避免重啟後需要重新處理 PDF |
| **DELETE store** | 刪除技能時需要清理對應的向量索引，釋放儲存空間 |

---

## Part 5: API Endpoints Reference

### Skills API (`/api/v1/skills/`)

#### 查詢端點

| Method | Endpoint | 說明 | 資料庫操作 |
|--------|----------|------|------------|
| POST | `/demo/query` | 傳統 JSON 查詢 | SQLite: READ skill_metadata<br>FAISS: similarity_search |
| POST | `/{skill_id}/progressive-stream` | SSE 串流查詢 | SQLite: READ<br>FAISS: search |

#### 技能管理端點

| Method | Endpoint | 說明 | 資料庫操作 |
|--------|----------|------|------------|
| GET | `/demo` | 列出所有技能 | SQLite: list_skills() |
| GET | `/tree` | 獲取技能樹 | SQLite: get_skill_tree() |
| GET | `/heads` | 列出技能群組 | SQLite: list_skill_heads() |
| POST | `/heads` | 建立技能群組 | SQLite: create_skill_head() |
| PUT | `/heads/{head_id}` | 更新群組 | SQLite: update_skill_head() |
| DELETE | `/heads/{head_id}` | 刪除群組 | SQLite: DELETE + FAISS: DELETE |
| DELETE | `/{skill_id}` | 刪除技能 | SQLite: DELETE + FAISS: DELETE |

#### 上傳端點

| Method | Endpoint | 說明 | 資料庫操作 |
|--------|----------|------|------------|
| POST | `/upload-source-streaming` | SSE 進度上傳 | SQLite: INSERT skill_metadata, chunk_metadata<br>FAISS: CREATE store |

---

## Part 6: 資料流圖示

### 上傳流程資料操作

```
┌─────────────────┐
│   PDF Upload    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────────────────────┐
│  Create Skill   │────>│ SQLite: INSERT skill_metadata   │
│  Head (if new)  │     │         INSERT skill_heads      │
└────────┬────────┘     └─────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Extract Text   │
│  (PyPDF2)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────────────────────┐
│  Generate       │────>│ BGE-M3: embed_documents()       │
│  Embeddings     │     │ (1024-dim vectors)              │
└────────┬────────┘     └─────────────────────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────────────────────┐
│  Store Vectors  │────>│ FAISS: create_store_from_texts()│
│                 │     │        save_local()             │
└────────┬────────┘     └─────────────────────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────────────────────┐
│  Store Metadata │────>│ SQLite: INSERT skill_document_mapping │
│                 │     │         INSERT skill_chunk_metadata   │
└─────────────────┘     └─────────────────────────────────┘
```

### 查詢流程資料操作

```
┌─────────────────┐
│   User Query    │
│   + Skill IDs   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────────────────────┐
│  Validate Skills│────>│ SQLite: get_documents_for_skill()│
│                 │     │         get_skill()              │
└────────┬────────┘     └─────────────────────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────────────────────┐
│  Embed Query    │────>│ BGE-M3: embed_query()           │
│                 │     │ (1024-dim vector)               │
└────────┬────────┘     └─────────────────────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────────────────────┐
│  Vector Search  │────>│ FAISS: similarity_search_with_score() │
│  (per skill)    │     │        (parallel for multi-skill)     │
└────────┬────────┘     └─────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Merge & Sort   │
│  Results        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────────────────────┐
│  Build Context  │────>│ Use chunk_metadata for citations│
│  + Citations    │     │                                 │
└────────┬────────┘     └─────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  LLM Generate   │
│  (Ollama)       │
└─────────────────┘
```

---

## Part 7: 常見查詢模式

### 獲取技能樹（前端 sidebar）

```sql
-- Step 1: Get all skill heads
SELECT * FROM skill_heads WHERE enabled = TRUE ORDER BY display_order;

-- Step 2: For each head, get documents
SELECT
    sm.skill_id, sm.skill_name, sm.total_chunks, sm.source_name,
    sm.parent_skill_id, sm.head_id
FROM skill_metadata sm
WHERE sm.head_id = ?
ORDER BY sm.created_at;
```

### 刪除技能（級聯刪除）

```sql
-- Step 1: Delete chunk metadata
DELETE FROM skill_chunk_metadata WHERE skill_id = ?;

-- Step 2: Delete document mapping
DELETE FROM skill_document_mapping WHERE skill_id = ?;

-- Step 3: Delete skill metadata
DELETE FROM skill_metadata WHERE skill_id = ?;

-- Step 4: Delete FAISS index (Python)
-- shutil.rmtree(f"data/faiss_indices/skills/{skill_id}")
```

### 查詢處理進度

```sql
SELECT
    job_id, status, total_pages, last_processed_page,
    (last_processed_page * 100.0 / total_pages) as progress_percent,
    error_message
FROM processing_jobs
WHERE skill_id = ?
ORDER BY created_at DESC
LIMIT 1;
```

---

*文件版本：2025-12-16*
*作者：Claude (SuperClaude)*
