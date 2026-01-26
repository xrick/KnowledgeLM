# Skill Metadata Database Tables 說明文檔

**建立日期**: 2026-01-26  
**適用版本**: DocAI Skill-Based Architecture  
**資料庫**: `data/skill_metadata.db` (SQLite)

---

## 目錄

1. [資料庫架構總覽](#資料庫架構總覽)
2. [Tables 詳細說明](#tables-詳細說明)
3. [新增技能完整流程](#新增技能完整流程)
4. [資料關聯查詢](#資料關聯查詢)
5. [操作對照表](#操作對照表)

---

## 資料庫架構總覽

```
skill_metadata.db
├── skill_heads              ← 1️⃣ 技能定義層 (父層)
├── skill_metadata           ← 2️⃣ 文檔層 (子層)
├── skill_document_mapping   ← 3️⃣ 文檔映射 (可選)
├── skill_chunk_metadata     ← 4️⃣ 文本區塊層
├── processing_jobs          ← 5️⃣ 處理任務追蹤
├── skill_overviews          ← 6️⃣ 技能摘要 (可選)
├── embedding_models         ← 7️⃣ 嵌入模型設定
└── users                    ← 8️⃣ 用戶資訊
```

### 核心關聯圖

```
┌─────────────────┐
│   skill_heads   │  ← 技能定義 (Single Source of Truth)
│    (head_id)    │
└────────┬────────┘
         │ 1:N
         ▼
┌─────────────────┐
│ skill_metadata  │  ← 文檔記錄 (每個 PDF 一筆)
│   (skill_id)    │
│   (head_id FK)  │
└────────┬────────┘
         │ 1:N
         ▼
┌─────────────────────┐
│ skill_chunk_metadata│  ← 文本區塊 (每個 chunk 一筆)
│    (chunk_id)       │
│    (skill_id FK)    │
└─────────────────────┘
```

---

## Tables 詳細說明

### 1️⃣ `skill_heads` - 技能頭部定義

**用途**: 定義技能的「身份」，是 Single Source of Truth

**寫入時機**: 用戶點擊「新增技能」按鈕時

#### Schema

```sql
CREATE TABLE skill_heads (
    head_id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL UNIQUE,
    description TEXT,
    category TEXT DEFAULT 'General',
    display_order INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 欄位說明

| 欄位 | 類型 | 說明 | 範例 |
|------|------|------|------|
| `head_id` | TEXT | 唯一識別碼 (PK) | `head_20260126_143022_abc123` |
| `skill_name` | TEXT | 技能名稱 (唯一) | `大語言模型大全` |
| `description` | TEXT | 技能描述 | `關於 LLM 的技術文檔` |
| `category` | TEXT | 分類 | `AI/ML`, `Legal`, `Finance` |
| `display_order` | INTEGER | UI 排序順序 | `0`, `1`, `2` |
| `enabled` | BOOLEAN | 是否啟用 | `TRUE` |

#### 相關 Provider 方法

```python
# app/Providers/skill_metadata_provider/client.py
await provider.create_skill_head(head_id, skill_name, description, category, display_order, enabled)
await provider.get_skill_head(head_id)
await provider.get_skill_head_by_name(skill_name)
await provider.list_skill_heads()
await provider.update_skill_head(head_id, **updates)
await provider.delete_skill_head(head_id)
```

---

### 2️⃣ `skill_metadata` - 文檔元資料

**用途**: 記錄每個上傳的 PDF 文檔

**寫入時機**: 用戶上傳 PDF 到技能時

#### Schema

```sql
CREATE TABLE skill_metadata (
    skill_id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    skill_description TEXT,
    skill_category TEXT,
    skill_level TEXT DEFAULT 'intermediate',
    tags TEXT,                              -- JSON array
    related_skills TEXT,                    -- JSON array
    total_chunks INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,                          -- JSON object
    embedding_model TEXT DEFAULT 'text-embedding-ada-002',
    embedding_dimension INTEGER DEFAULT 1536,
    parent_skill_id TEXT DEFAULT 'root',
    source_name TEXT DEFAULT NULL,          -- PDF 檔名
    head_id TEXT REFERENCES skill_heads(head_id),
    processing_status TEXT DEFAULT 'completed',
    indexed_chunks INTEGER DEFAULT 0,
    last_error TEXT DEFAULT NULL,
    processing_started_at TEXT DEFAULT NULL,
    processing_completed_at TEXT DEFAULT NULL
);

-- Indexes
CREATE INDEX idx_skill_category ON skill_metadata(skill_category);
CREATE INDEX idx_skill_name ON skill_metadata(skill_name);
CREATE INDEX idx_skill_level ON skill_metadata(skill_level);
CREATE INDEX idx_parent_skill_id ON skill_metadata(parent_skill_id);
CREATE INDEX idx_skill_head_id ON skill_metadata(head_id);
CREATE INDEX idx_processing_status ON skill_metadata(processing_status);
```

#### 欄位說明

| 欄位 | 類型 | 說明 | 範例 |
|------|------|------|------|
| `skill_id` | TEXT | 文檔唯一 ID (PK) | `skill_20260126_143022_abc123_src_00` |
| `skill_name` | TEXT | 技能名稱 | `大語言模型大全` |
| `head_id` | TEXT | 關聯到 skill_heads (FK) | `head_20260126_143022_abc123` |
| `source_name` | TEXT | PDF 檔名 | `民法總則.pdf` |
| `total_chunks` | INTEGER | 區塊數量 | `385` |
| `processing_status` | TEXT | 處理狀態 | `pending`, `processing`, `completed`, `failed` |
| `parent_skill_id` | TEXT | 父技能 ID | `root` 或父 skill_id |

#### 相關 Provider 方法

```python
await provider.create_skill(skill_id, skill_name, ..., head_id=head_id, source_name=source_name)
await provider.get_skill(skill_id)
await provider.list_skills(category=None, level=None)
await provider.update_skill(skill_id, **updates)
await provider.delete_skill(skill_id)
await provider.update_processing_status(skill_id, status, error=None)
```

---

### 3️⃣ `skill_document_mapping` - 文檔映射

**用途**: 記錄 skill 與 file 的關聯（可選使用）

**寫入時機**: 當需要追蹤文件相關性分數時

#### Schema

```sql
CREATE TABLE skill_document_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    relevance_score REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    document_name TEXT,
    document_path TEXT,
    total_pages INTEGER DEFAULT 0,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_skill_doc_mapping_skill ON skill_document_mapping(skill_id);
CREATE INDEX idx_skill_doc_mapping_file ON skill_document_mapping(file_id);
```

#### 相關 Provider 方法

```python
await provider.link_skill_to_document(skill_id, file_id, relevance_score)
await provider.get_documents_for_skill(skill_id)
await provider.get_skills_for_document(file_id)
```

---

### 4️⃣ `skill_chunk_metadata` - 文本區塊

**用途**: 儲存 PDF 分割後的每個文本區塊

**寫入時機**: PDF 處理完成後，批次插入

#### Schema

```sql
CREATE TABLE skill_chunk_metadata (
    chunk_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    document_name TEXT NOT NULL,
    page_number INTEGER,
    chunk_index INTEGER,
    chunk_text TEXT,
    embedding_model TEXT DEFAULT 'text-embedding-ada-002',
    embedding_dimension INTEGER DEFAULT 1536,
    metadata TEXT,                          -- JSON object
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_chunk_skill_page ON skill_chunk_metadata(skill_id, document_name, page_number);
```

#### 欄位說明

| 欄位 | 類型 | 說明 | 範例 |
|------|------|------|------|
| `chunk_id` | TEXT | 區塊唯一 ID (PK) | `chunk_0001_page_5` |
| `skill_id` | TEXT | 關聯到 skill_metadata (FK) | `skill_xxx_src_00` |
| `document_id` | TEXT | 文檔 ID | `doc_abc123` |
| `document_name` | TEXT | 文檔名稱 | `民法總則.pdf` |
| `page_number` | INTEGER | 頁碼 | `5` |
| `chunk_index` | INTEGER | 區塊索引 | `0`, `1`, `2` |
| `chunk_text` | TEXT | 實際文本內容 | `第一條 民法總則...` |

#### 插入範例 (from `pdf_skill_ingestion_service.py`)

```python
cursor.execute("""
    INSERT INTO skill_chunk_metadata
    (chunk_id, skill_id, document_id, document_name, page_number,
     chunk_index, chunk_text, embedding_model, embedding_dimension, metadata)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    metadata['chunk_id'],
    skill_id,
    metadata['document_id'],
    metadata['document_name'],
    metadata['page_number'],
    metadata['chunk_index'],
    chunk['text'],
    'BAAI/bge-m3',
    1024,
    json.dumps(metadata)
))
```

---

### 5️⃣ `processing_jobs` - 處理任務追蹤

**用途**: 追蹤大型 PDF 的處理進度（支援斷點續傳）

**寫入時機**: 開始處理 PDF 時

#### Schema

```sql
CREATE TABLE processing_jobs (
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
    dirty_batches TEXT,                     -- JSON array
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

-- Indexes
CREATE INDEX idx_pj_status ON processing_jobs(status);
CREATE INDEX idx_pj_skill ON processing_jobs(skill_id);
CREATE INDEX idx_pj_created ON processing_jobs(created_at);
```

#### 欄位說明

| 欄位 | 類型 | 說明 | 範例 |
|------|------|------|------|
| `job_id` | TEXT | 任務 UUID (PK) | `job_abc123` |
| `skill_id` | TEXT | 關聯 skill (FK) | `skill_xxx` |
| `head_id` | TEXT | 關聯 skill_head (FK) | `head_xxx` |
| `total_pages` | INTEGER | PDF 總頁數 | `100` |
| `last_processed_page` | INTEGER | 已處理頁數 | `50` |
| `status` | TEXT | 狀態 | `pending`, `processing`, `completed`, `failed` |
| `dirty_batches` | TEXT | 需重試的批次 (JSON) | `[1, 5, 8]` |

#### 相關 Provider 方法

```python
await provider.create_processing_job(job_id, skill_id, pdf_path, total_pages, head_id, ...)
await provider.get_processing_job(job_id)
await provider.update_processing_job(job_id, **updates)
await provider.get_interrupted_jobs()
await provider.mark_job_dirty(job_id, batch_index)
await provider.delete_processing_job(job_id)
```

---

### 6️⃣ `skill_overviews` - 技能摘要

**用途**: 儲存技能的 AI 生成摘要（可選）

#### Schema

```sql
CREATE TABLE skill_overviews (
    skill_id TEXT PRIMARY KEY,
    overview TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);
```

#### 相關 Provider 方法

```python
await provider.store_overview(skill_id, overview_text)
await provider.get_overview(skill_id)
await provider.get_multiple_overviews(skill_ids)
```

---

### 7️⃣ `embedding_models` - 嵌入模型設定

**用途**: 記錄可用的嵌入模型配置

#### Schema

```sql
CREATE TABLE embedding_models (
    model_name TEXT PRIMARY KEY,
    model_type TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    max_sequence_length INTEGER,
    language_support TEXT,
    configuration TEXT,                     -- JSON object
    is_active BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 新增技能完整流程

### 流程圖

```
用戶操作                          資料庫 Tables
─────────                        ─────────────
   │
   ▼
[1. 新增技能]
   │
   ├─────────────────────────► skill_heads (INSERT)
   │                           ↓ head_id
   ▼
[2. 上傳 PDF]
   │
   ├─────────────────────────► processing_jobs (INSERT)
   │                           ↓ job_id
   │
   ├─────────────────────────► skill_metadata (INSERT)
   │                           ↓ skill_id
   ▼
[3. PDF 處理中...]
   │
   ├─────────────────────────► skill_chunk_metadata (BATCH INSERT)
   │                           (每個 chunk 一筆)
   │
   ├─────────────────────────► processing_jobs (UPDATE status)
   │
   ▼
[4. 處理完成]
   │
   ├─────────────────────────► skill_metadata (UPDATE total_chunks)
   │
   └─────────────────────────► processing_jobs (UPDATE completed_at)
```

### 詳細步驟

#### Step 1: 創建 Skill Head

```python
# API: POST /api/v1/skills/heads
await metadata_provider.create_skill_head(
    head_id="head_20260126_143022_abc123",
    skill_name="大語言模型大全",
    description="LLM 技術文檔集合",
    category="AI/ML",
    display_order=0,
    enabled=True
)
```

#### Step 2: 上傳 PDF 並創建 Processing Job

```python
# API: POST /api/v1/skills/{head_id}/upload-source
job = await metadata_provider.create_processing_job(
    job_id="job_xxx",
    skill_id="skill_20260126_143022_abc123_src_00",
    pdf_path="/path/to/file.pdf",
    total_pages=100,
    head_id="head_20260126_143022_abc123"
)
```

#### Step 3: 創建 Skill Metadata

```python
await metadata_provider.create_skill(
    skill_id="skill_20260126_143022_abc123_src_00",
    skill_name="大語言模型大全",
    skill_category="AI/ML",
    head_id="head_20260126_143022_abc123",
    source_name="LLM_Handbook.pdf",
    processing_status="processing"
)
```

#### Step 4: 批次插入 Chunks

```python
# 在 pdf_skill_ingestion_service.py 中
for chunk in chunks:
    cursor.execute("""
        INSERT INTO skill_chunk_metadata
        (chunk_id, skill_id, document_id, document_name, ...)
        VALUES (?, ?, ?, ?, ...)
    """, (...))

conn.commit()
```

#### Step 5: 更新完成狀態

```python
await metadata_provider.update_skill(
    skill_id="skill_xxx",
    total_chunks=385,
    processing_status="completed"
)

await metadata_provider.update_processing_job(
    job_id="job_xxx",
    status="completed",
    completed_at=datetime.now().isoformat()
)
```

---

## 資料關聯查詢

### 取得完整技能樹 (UI 左側面板)

```sql
SELECT 
    h.head_id,
    h.skill_name,
    h.description,
    h.category,
    h.display_order,
    m.skill_id,
    m.source_name,
    m.total_chunks,
    m.processing_status
FROM skill_heads h
LEFT JOIN skill_metadata m ON h.head_id = m.head_id
WHERE h.enabled = TRUE
ORDER BY h.display_order, h.skill_name, m.source_name
```

### Provider 方法

```python
# 取得技能樹
tree = await metadata_provider.get_skill_tree()

# 返回結構:
# [
#     {
#         "head_id": "head_xxx",
#         "skill_name": "大語言模型大全",
#         "category": "AI/ML",
#         "documents": [
#             {"skill_id": "skill_xxx_src_00", "source_name": "LLM_Handbook.pdf", "total_chunks": 385},
#             {"skill_id": "skill_xxx_src_01", "source_name": "GPT_Guide.pdf", "total_chunks": 200}
#         ]
#     }
# ]
```

---

## 操作對照表

| 操作 | skill_heads | skill_metadata | skill_chunk_metadata | processing_jobs |
|------|:-----------:|:--------------:|:--------------------:|:---------------:|
| **新增技能** | ✅ INSERT | - | - | - |
| **上傳 PDF** | - | ✅ INSERT | ✅ BATCH INSERT | ✅ INSERT/UPDATE |
| **查詢技能樹** | ✅ READ | ✅ READ | - | - |
| **執行查詢** | - | ✅ READ | ✅ READ (via FAISS) | - |
| **刪除技能** | ✅ DELETE | ✅ CASCADE DELETE | ✅ CASCADE DELETE | - |
| **刪除文檔** | - | ✅ DELETE | ✅ CASCADE DELETE | - |
| **重建索引** | - | ✅ UPDATE | ✅ DELETE + INSERT | ✅ INSERT |

---

## 相關檔案

| 檔案 | 說明 |
|------|------|
| `app/Providers/skill_metadata_provider/client.py` | SkillMetadataProvider 類別 (~1970 行) |
| `app/SkillServices/pdf_skill_ingestion_service.py` | PDF 處理服務 |
| `app/api/v1/endpoints/skills.py` | Skills API endpoints |
| `data/skill_metadata.db` | SQLite 資料庫檔案 |

---

*文檔建立: 2026-01-26*  
*最後更新: 2026-01-26*
