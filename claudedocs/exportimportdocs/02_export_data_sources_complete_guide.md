# Skill Export 資料來源完整指南

**文檔版本**: 1.0
**建立日期**: 2025-12-25
**文檔類型**: 技術規格 - 資料來源與匯出/匯入方法
**狀態**: 完整技術文檔

---

## 📋 目錄

1. [資料來源總覽](#資料來源總覽)
2. [SQLite 資料庫匯出](#sqlite-資料庫匯出)
3. [FAISS 向量索引匯出](#faiss-向量索引匯出)
4. [Manifest 元資料生成](#manifest-元資料生成)
5. [匯出後的驗證方法](#匯出後的驗證方法)
6. [匯入流程與資料重建](#匯入流程與資料重建)
7. [完整測試方案](#完整測試方案)

---

## 資料來源總覽

當匯出一個 Skill 時，系統會從以下 **三大來源** 收集資料：

```
┌─────────────────────────────────────────────────────────────┐
│                   Skill Export 資料來源                      │
└─────────────────────────────────────────────────────────────┘

📦 資料來源 1: SQLite Database (skill_metadata.db)
   ├─ skill_heads table          (1 record)
   ├─ skill_metadata table        (N records)
   ├─ skill_chunk_metadata table  (M records)
   ├─ skill_document_mapping table (K records)
   └─ skill_overviews table       (1 record)

🧠 資料來源 2: FAISS Vector Index
   ├─ index.faiss                 (FAISS binary index)
   └─ index.pkl                   (Metadata pickle)

📝 資料來源 3: Manifest Metadata (Generated)
   └─ manifest.json               (Export metadata + checksums)
```

### 為什麼需要這三大來源？

| 來源 | 作用 | 缺少後果 |
|------|------|----------|
| **SQLite Database** | 儲存文字內容、結構化元資料、文件映射 | 無法重建 skill 的文字內容與結構 |
| **FAISS Index** | 儲存向量嵌入，用於語義搜尋 | 無法進行向量檢索，失去 RAG 核心功能 |
| **Manifest** | 驗證資料完整性、提供匯入指引 | 無法驗證資料是否損壞，匯入失敗率高 |

---

## SQLite 資料庫匯出

### 1. skill_heads 表

#### 表結構
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

#### 匯出方法

```python
import csv
import sqlite3
from typing import List, Dict, Any

async def export_skill_heads(
    db_path: str,
    head_id: str,
    output_csv: str
) -> int:
    """
    匯出 skill_heads 表資料到 CSV

    Args:
        db_path: SQLite 資料庫路徑 (e.g., "./data/skill_metadata.db")
        head_id: Skill Head ID (e.g., "head_20251225_ml_001")
        output_csv: 輸出 CSV 檔案路徑 (e.g., "/tmp/export_xxx/skill_heads.csv")

    Returns:
        匯出的記錄數 (通常為 1)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 啟用字典式存取

    try:
        cursor = conn.execute("""
            SELECT head_id, skill_name, description, category,
                   display_order, enabled, created_at, updated_at
            FROM skill_heads
            WHERE head_id = ?
        """, (head_id,))

        rows = cursor.fetchall()

        if not rows:
            raise ValueError(f"Skill head not found: {head_id}")

        # 寫入 CSV
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['head_id', 'skill_name', 'description', 'category',
                         'display_order', 'enabled', 'created_at', 'updated_at']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

        return len(rows)

    finally:
        conn.close()
```

#### 為什麼要匯出此表？

**必要性**: 🔴 **Critical**

| 欄位 | 用途 | 缺少後果 |
|------|------|----------|
| `head_id` | Skill 的唯一識別符 | 無法建立 skill 結構 |
| `skill_name` | Skill 顯示名稱 | UI 無法顯示 skill 名稱 |
| `description` | Skill 描述 | 遺失 skill 描述資訊 |
| `category` | Skill 分類 | 無法分類管理 |
| `display_order` | UI 顯示順序 | 排序混亂 |
| `enabled` | 啟用狀態 | 無法控制 skill 啟用/停用 |
| `created_at` / `updated_at` | 時間戳記 | 遺失歷史記錄 |

**實際範例資料**:
```csv
head_id,skill_name,description,category,display_order,enabled,created_at,updated_at
head_20251225_ml_001,ML知識庫,Machine Learning documents,AI/ML,0,TRUE,2025-12-01 10:00:00,2025-12-25 14:00:00
```

---

### 2. skill_metadata 表

#### 表結構
```sql
CREATE TABLE skill_metadata (
    skill_id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    skill_description TEXT,
    skill_category TEXT,
    skill_level TEXT DEFAULT 'intermediate',
    tags TEXT,  -- JSON array
    related_skills TEXT,  -- JSON array
    total_chunks INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,  -- JSON object
    parent_skill_id TEXT DEFAULT 'root',
    source_name TEXT,  -- Document filename
    head_id TEXT REFERENCES skill_heads(head_id)
);
```

#### 匯出方法

```python
async def export_skill_metadata(
    db_path: str,
    head_id: str,
    output_csv: str
) -> int:
    """
    匯出 skill_metadata 表資料到 CSV

    此表包含：
    - Main skill document (parent_skill_id='root' 且有 source_name)
    - Instant attachments (parent_skill_id=skill_id 的子文件)

    Args:
        db_path: SQLite 資料庫路徑
        head_id: Skill Head ID
        output_csv: 輸出 CSV 檔案路徑

    Returns:
        匯出的文件數 (包含 main + attachments)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # 匯出所有屬於此 head_id 的文件
        cursor = conn.execute("""
            SELECT skill_id, skill_name, skill_description, skill_category,
                   skill_level, tags, related_skills, total_chunks,
                   created_at, updated_at, metadata, parent_skill_id,
                   source_name, head_id
            FROM skill_metadata
            WHERE head_id = ?
            ORDER BY created_at ASC
        """, (head_id,))

        rows = cursor.fetchall()

        if not rows:
            raise ValueError(f"No documents found for head_id: {head_id}")

        # 寫入 CSV
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'skill_id', 'skill_name', 'skill_description', 'skill_category',
                'skill_level', 'tags', 'related_skills', 'total_chunks',
                'created_at', 'updated_at', 'metadata', 'parent_skill_id',
                'source_name', 'head_id'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

        return len(rows)

    finally:
        conn.close()
```

#### 為什麼要匯出此表？

**必要性**: 🔴 **Critical**

| 欄位 | 用途 | 缺少後果 |
|------|------|----------|
| `skill_id` | Document 唯一識別符 | 無法重建文件結構 |
| `skill_name` | Document 名稱 | UI 無法顯示文件名稱 |
| `total_chunks` | Chunk 總數 | 無法驗證資料完整性 |
| `source_name` | 原始 PDF 檔名 | 無法追蹤來源文件 |
| `head_id` | 所屬 Skill Head | 無法建立層級關係 |
| `parent_skill_id` | 父子關係 (用於 attachments) | 無法重建 3-level 樹狀結構 |
| `metadata` | 額外元資料 (JSON) | 遺失 PDF 路徑等資訊 |
| `tags` / `related_skills` | 標籤與關聯 | 遺失分類與關聯資訊 |

**實際範例資料**:
```csv
skill_id,skill_name,source_name,total_chunks,head_id,parent_skill_id,metadata
skill_001,ML知識庫,Build_LLM,462,head_20251225_ml_001,root,"{""source_file"": ""uploadfiles/pdf/build_llm.pdf"", ""file_size"": 11534567}"
skill_002,ML知識庫,LLM_Handbook,421,head_20251225_ml_001,root,"{""source_file"": ""uploadfiles/pdf/llm_handbook.pdf"", ""file_size"": 9845231}"
```

---

### 3. skill_chunk_metadata 表

#### 表結構
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
    metadata TEXT,  -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);
```

#### 匯出方法

```python
async def export_skill_chunk_metadata(
    db_path: str,
    head_id: str,
    output_csv: str,
    batch_size: int = 1000
) -> int:
    """
    匯出 skill_chunk_metadata 表資料到 CSV (分批處理)

    此表包含所有 chunk 的文字內容與元資料。
    對於大型 skill (>5000 chunks)，使用批次處理避免記憶體溢出。

    Args:
        db_path: SQLite 資料庫路徑
        head_id: Skill Head ID
        output_csv: 輸出 CSV 檔案路徑
        batch_size: 每批處理的 chunk 數 (預設 1000)

    Returns:
        匯出的 chunk 總數
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # 首先取得屬於此 head 的所有 skill_ids
        cursor = conn.execute("""
            SELECT skill_id FROM skill_metadata WHERE head_id = ?
        """, (head_id,))
        skill_ids = [row['skill_id'] for row in cursor.fetchall()]

        if not skill_ids:
            raise ValueError(f"No documents found for head_id: {head_id}")

        total_chunks = 0

        # 寫入 CSV (批次模式)
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'chunk_id', 'skill_id', 'document_id', 'document_name',
                'page_number', 'chunk_index', 'chunk_text',
                'embedding_model', 'embedding_dimension', 'metadata', 'created_at'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            # 對每個 skill_id 進行批次查詢
            for skill_id in skill_ids:
                offset = 0

                while True:
                    cursor = conn.execute("""
                        SELECT chunk_id, skill_id, document_id, document_name,
                               page_number, chunk_index, chunk_text,
                               embedding_model, embedding_dimension, metadata, created_at
                        FROM skill_chunk_metadata
                        WHERE skill_id = ?
                        ORDER BY chunk_index ASC
                        LIMIT ? OFFSET ?
                    """, (skill_id, batch_size, offset))

                    batch = cursor.fetchall()

                    if not batch:
                        break

                    # 寫入批次
                    for row in batch:
                        writer.writerow(dict(row))
                        total_chunks += 1

                    offset += batch_size

        return total_chunks

    finally:
        conn.close()
```

#### 為什麼要匯出此表？

**必要性**: 🔴 **Critical** (RAG 核心資料)

| 欄位 | 用途 | 缺少後果 |
|------|------|----------|
| `chunk_id` | Chunk 唯一識別符 | 無法追蹤 chunk |
| `skill_id` | 所屬 Skill | 無法建立關聯 |
| `chunk_text` | **Chunk 文字內容** | **完全失去 RAG 文字內容** |
| `chunk_index` | Chunk 順序索引 | 無法對應 FAISS 向量索引 |
| `page_number` | 來源頁碼 | 無法顯示引用來源 |
| `document_name` | 來源文件名 | 無法顯示來源文件 |
| `embedding_model` | 嵌入模型名稱 | 無法驗證向量相容性 |
| `embedding_dimension` | 嵌入維度 | 無法驗證 FAISS 索引相容性 |

**關鍵重點**:
- 此表儲存了 **所有 chunk 的文字內容**，是 RAG 系統的核心資料
- `chunk_index` 與 FAISS index 的位置 **一一對應**
- 匯出時必須保持 `chunk_index` 的順序，否則 FAISS 向量與文字會錯位

**實際範例資料**:
```csv
chunk_id,skill_id,chunk_index,chunk_text,page_number,document_name,embedding_model,embedding_dimension
chunk_001,skill_001,0,"Large Language Models (LLMs) are...",1,Build_LLM,BAAI/bge-m3,1024
chunk_002,skill_001,1,"Pre-training involves unsupervised learning...",1,Build_LLM,BAAI/bge-m3,1024
chunk_003,skill_001,2,"Fine-tuning adapts the pre-trained model...",2,Build_LLM,BAAI/bge-m3,1024
```

**檔案大小估算**:
- 每個 chunk 平均 1000 chars 文字 + 200 chars 元資料 ≈ **1.2 KB/row**
- 1532 chunks ≈ **1.8 MB CSV 檔案**
- 5000 chunks ≈ **6 MB CSV 檔案**

---

### 4. skill_document_mapping 表

#### 表結構
```sql
CREATE TABLE skill_document_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    file_id TEXT NOT NULL,  -- From FileMetadataProvider (可能為空)
    relevance_score REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);
```

#### 匯出方法

```python
async def export_skill_document_mapping(
    db_path: str,
    head_id: str,
    output_csv: str
) -> int:
    """
    匯出 skill_document_mapping 表資料到 CSV

    此表用於 Skill-Based 與 File-Based 系統的映射。
    注意：對於純 Skill-Based 建立的 skill，此表可能為空。

    Args:
        db_path: SQLite 資料庫路徑
        head_id: Skill Head ID
        output_csv: 輸出 CSV 檔案路徑

    Returns:
        匯出的映射記錄數 (可能為 0)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # 取得屬於此 head 的所有 skill_ids
        cursor = conn.execute("""
            SELECT skill_id FROM skill_metadata WHERE head_id = ?
        """, (head_id,))
        skill_ids = [row['skill_id'] for row in cursor.fetchall()]

        if not skill_ids:
            # 建立空 CSV
            with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['mapping_id', 'skill_id', 'file_id', 'relevance_score', 'created_at']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
            return 0

        # 查詢映射記錄
        placeholders = ','.join('?' * len(skill_ids))
        cursor = conn.execute(f"""
            SELECT mapping_id, skill_id, file_id, relevance_score, created_at
            FROM skill_document_mapping
            WHERE skill_id IN ({placeholders})
            ORDER BY created_at ASC
        """, skill_ids)

        rows = cursor.fetchall()

        # 寫入 CSV
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['mapping_id', 'skill_id', 'file_id', 'relevance_score', 'created_at']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

        return len(rows)

    finally:
        conn.close()
```

#### 為什麼要匯出此表？

**必要性**: 🟡 **Optional** (取決於系統架構)

| 情境 | 是否必要 | 原因 |
|------|----------|------|
| 純 Skill-Based 系統 | ❌ 非必要 | 此表可能為空，無影響 |
| Skill + File 混合系統 | ✅ 必要 | 需要保留跨系統映射關係 |
| 需要追蹤來源檔案 | ✅ 建議匯出 | 保留完整的資料來源追蹤 |

**欄位說明**:
| 欄位 | 用途 | 缺少後果 |
|------|------|----------|
| `mapping_id` | 映射記錄 ID | 無法重建映射 |
| `skill_id` | Skill 識別符 | 無法建立關聯 |
| `file_id` | File 系統的檔案 ID | 遺失跨系統映射 |
| `relevance_score` | 相關性分數 | 遺失相關性資訊 |

**實際範例資料**:
```csv
mapping_id,skill_id,file_id,relevance_score,created_at
1,skill_001,file_abc123,0.95,2025-12-01 10:40:00
2,skill_002,file_xyz789,0.88,2025-12-01 11:05:00
```

---

### 5. skill_overviews 表

#### 表結構
```sql
CREATE TABLE skill_overviews (
    skill_id TEXT PRIMARY KEY,
    overview TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);
```

#### 匯出方法

```python
async def export_skill_overviews(
    db_path: str,
    head_id: str,
    output_csv: str
) -> int:
    """
    匯出 skill_overviews 表資料到 CSV

    此表儲存 LLM 生成的 Skill 概要摘要。
    注意：每個 skill_id 對應一個 overview (非 head_id)。

    Args:
        db_path: SQLite 資料庫路徑
        head_id: Skill Head ID
        output_csv: 輸出 CSV 檔案路徑

    Returns:
        匯出的 overview 記錄數
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # 取得屬於此 head 的所有 skill_ids
        cursor = conn.execute("""
            SELECT skill_id FROM skill_metadata WHERE head_id = ?
        """, (head_id,))
        skill_ids = [row['skill_id'] for row in cursor.fetchall()]

        if not skill_ids:
            # 建立空 CSV
            with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['skill_id', 'overview', 'created_at', 'updated_at']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
            return 0

        # 查詢 overviews
        placeholders = ','.join('?' * len(skill_ids))
        cursor = conn.execute(f"""
            SELECT skill_id, overview, created_at, updated_at
            FROM skill_overviews
            WHERE skill_id IN ({placeholders})
            ORDER BY created_at ASC
        """, skill_ids)

        rows = cursor.fetchall()

        # 寫入 CSV
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['skill_id', 'overview', 'created_at', 'updated_at']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

        return len(rows)

    finally:
        conn.close()
```

#### 為什麼要匯出此表？

**必要性**: 🟢 **Recommended** (增強功能)

| 欄位 | 用途 | 缺少後果 |
|------|------|----------|
| `skill_id` | 對應的 Skill | 無法建立關聯 |
| `overview` | LLM 生成的 Skill 摘要 | 遺失 Skill 概要資訊 |
| `created_at` / `updated_at` | 時間戳記 | 遺失歷史記錄 |

**功能說明**:
- **用途**: 顯示 Skill 的整體概要，幫助使用者快速理解 Skill 內容
- **生成**: 由 LLM 自動生成，非人工撰寫
- **影響**: 若缺少，Skill 仍可正常運作，但缺少概要說明

**實際範例資料**:
```csv
skill_id,overview,created_at,updated_at
skill_001,"This skill covers the fundamentals of building Large Language Models, including pre-training, fine-tuning, and deployment strategies.",2025-12-01 10:50:00,2025-12-25 14:10:00
```

---

## FAISS 向量索引匯出

### FAISS 檔案結構

每個 Skill 的 FAISS 索引儲存在獨立目錄：

```
data/faiss_indices/skills/{skill_id}/
├── index.faiss      # FAISS 向量索引 (二進位檔案)
└── index.pkl        # 元資料 (Pickle 序列化)
```

### 1. index.faiss 檔案

#### 檔案說明
- **格式**: FAISS 二進位格式
- **內容**: 所有 chunks 的向量嵌入 (embeddings)
- **維度**: 1024 (BGE-M3 model)
- **索引類型**: `IndexFlatIP` (Inner Product - 內積相似度)

#### 匯出方法

```python
import faiss
import shutil
from pathlib import Path

async def export_faiss_index(
    skill_id: str,
    faiss_base_dir: str,
    output_dir: str
) -> Dict[str, int]:
    """
    匯出 FAISS 索引檔案

    Args:
        skill_id: Skill ID (e.g., "skill_20251216_124010_b45c5a1f_d81758")
        faiss_base_dir: FAISS 基礎目錄 (e.g., "./data/faiss_indices/skills")
        output_dir: 輸出目錄 (e.g., "/tmp/export_xxx/")

    Returns:
        Dict with file sizes:
        {
            "index_faiss_size": 828416,  # bytes
            "index_pkl_size": 37824,     # bytes
            "total_size": 866240         # bytes
        }
    """
    source_dir = Path(faiss_base_dir) / skill_id

    # 驗證來源目錄存在
    if not source_dir.exists():
        raise FileNotFoundError(f"FAISS index directory not found: {source_dir}")

    index_faiss_path = source_dir / "index.faiss"
    index_pkl_path = source_dir / "index.pkl"

    # 驗證檔案存在
    if not index_faiss_path.exists():
        raise FileNotFoundError(f"index.faiss not found: {index_faiss_path}")
    if not index_pkl_path.exists():
        raise FileNotFoundError(f"index.pkl not found: {index_pkl_path}")

    # 複製檔案到輸出目錄
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    shutil.copy2(index_faiss_path, output_path / "index.faiss")
    shutil.copy2(index_pkl_path, output_path / "index.pkl")

    # 計算檔案大小
    index_faiss_size = index_faiss_path.stat().st_size
    index_pkl_size = index_pkl_path.stat().st_size

    return {
        "index_faiss_size": index_faiss_size,
        "index_pkl_size": index_pkl_size,
        "total_size": index_faiss_size + index_pkl_size
    }
```

#### 為什麼要匯出此檔案？

**必要性**: 🔴 **Critical** (RAG 核心功能)

| 用途 | 說明 | 缺少後果 |
|------|------|----------|
| **向量檢索** | 儲存所有 chunks 的向量嵌入 | **完全失去語義搜尋功能** |
| **RAG Pipeline** | Query embedding → FAISS search → 相似 chunks | RAG 系統無法運作 |
| **效能優化** | FAISS 提供高效向量搜尋 (毫秒級) | 無法進行大規模向量檢索 |

**檔案大小估算**:
- **計算公式**: `file_size ≈ num_vectors × dimension × 4 bytes`
- **範例**:
  - 1532 chunks × 1024 dim × 4 bytes ≈ **6.3 MB**
  - 實際大小 828 KB (壓縮後) ≈ **13% of theoretical size**

**FAISS 索引驗證**:
```python
import faiss

# 讀取 FAISS 索引
index = faiss.read_index("index.faiss")

# 驗證索引資訊
print(f"Total vectors: {index.ntotal}")          # e.g., 1532
print(f"Dimension: {index.d}")                   # e.g., 1024
print(f"Index type: {type(index).__name__}")    # e.g., IndexFlatIP
```

---

### 2. index.pkl 檔案

#### 檔案說明
- **格式**: Python Pickle 序列化
- **內容**: FAISS 索引的元資料與映射資訊
- **用途**: 將 FAISS index 位置對應到 chunk_id

#### 檔案結構

```python
{
    "dimension": 1024,
    "index_type": "IndexFlatIP",
    "total_vectors": 1532,
    "chunk_id_mapping": {
        0: "chunk_001",
        1: "chunk_002",
        2: "chunk_003",
        # ... up to 1531
    },
    "metadata": {
        "created_at": "2025-12-16T20:40:00",
        "embedding_model": "BAAI/bge-m3",
        "skill_id": "skill_20251216_124010_b45c5a1f_d81758"
    }
}
```

#### 匯出方法

已包含在上述 `export_faiss_index()` 函數中。

#### 為什麼要匯出此檔案？

**必要性**: 🔴 **Critical** (FAISS 索引映射)

| 用途 | 說明 | 缺少後果 |
|------|------|----------|
| **Index → Chunk 映射** | FAISS 位置 (0-1531) → chunk_id | 無法取得 chunk 文字內容 |
| **索引驗證** | 驗證向量數量與維度 | 無法驗證索引完整性 |
| **模型追蹤** | 記錄使用的嵌入模型 | 無法驗證模型相容性 |

**映射邏輯**:
```python
# 查詢流程
query_vector = [0.123, 0.456, ...]  # 1024-dim

# FAISS 搜尋
D, I = index.search(query_vector, k=5)
# I = [234, 567, 89, 12, 901]  # FAISS indices

# 使用 index.pkl 映射到 chunk_ids
chunk_ids = [chunk_id_mapping[i] for i in I]
# chunk_ids = ["chunk_235", "chunk_568", "chunk_90", "chunk_13", "chunk_902"]

# 使用 chunk_ids 從 skill_chunk_metadata 查詢文字
chunks = query_chunks_by_ids(chunk_ids)
```

---

## Manifest 元資料生成

### manifest.json 結構

```json
{
  "version": "1.0",
  "export_timestamp": "2025-12-25T14:30:22.123456",
  "export_tool": "DocAI-SkillExport",

  "skill_info": {
    "head_id": "head_20251225_ml_001",
    "skill_name": "ML知識庫",
    "description": "Machine Learning 相關文件",
    "created_at": "2025-12-01T10:00:00",
    "updated_at": "2025-12-25T14:00:00"
  },

  "statistics": {
    "total_documents": 5,
    "total_chunks": 1532,
    "faiss_index_size_bytes": 828416,
    "embedding_model": "BAAI/bge-m3",
    "embedding_dimension": 1024
  },

  "file_list": {
    "tables": [
      "skill_heads.csv",
      "skill_metadata.csv",
      "skill_chunk_metadata.csv",
      "skill_document_mapping.csv",
      "skill_overviews.csv"
    ],
    "faiss_files": [
      "index.faiss",
      "index.pkl"
    ],
    "pdf_files": []
  },

  "checksums": {
    "skill_heads.csv": "sha256:a3c5e8d9f2b4c6e1a7d9f3b5c7e9a1d3f5b7c9e1a3d5f7b9c1e3a5d7f9b1c3e5",
    "skill_metadata.csv": "sha256:b4d6f9e0c3a5d7f1b8e0c2a4d6f8b0d2f4b6c8e0a2d4f6b8c0e2a4d6f8b0d2f4",
    "skill_chunk_metadata.csv": "sha256:c5e7g0f1d4b6e8g2c9f1d3b5e7g9c1e3f5b7d9c1e3f5b7d9c1e3f5b7d9c1e3f5",
    "skill_document_mapping.csv": "sha256:d6f8h1e2c5a7f9h3d0e2c4a6f8h0d2f4b6c8e0a2d4f6b8c0e2a4d6f8b0d2f4b6",
    "skill_overviews.csv": "sha256:e7g9i2f3d6b8g0i4e1f3d5b7g9i1e3f5b7d9c1e3f5b7d9c1e3f5b7d9c1e3f5b7",
    "index.faiss": "sha256:f8h0j3g4e7c9h1j5f2g4e6c8h0j2f4b6d8c0e2a4f6b8d0e2a4f6b8d0e2a4f6b8",
    "index.pkl": "sha256:g9i1k4h5f8d0i2k6g3h5f7d9i1k3g5b7d9c1e3f5b7d9c1e3f5b7d9c1e3f5b7d9"
  }
}
```

### 生成方法

```python
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

def calculate_file_checksum(file_path: str) -> str:
    """計算檔案 SHA-256 checksum"""
    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)

    return f"sha256:{sha256_hash.hexdigest()}"

async def generate_manifest(
    head_id: str,
    skill_name: str,
    export_dir: Path,
    skill_info: Dict[str, Any],
    statistics: Dict[str, int]
) -> Dict[str, Any]:
    """
    生成 manifest.json

    Args:
        head_id: Skill Head ID
        skill_name: Skill 名稱
        export_dir: 匯出目錄 (包含所有 CSV 和 FAISS 檔案)
        skill_info: Skill 基本資訊
        statistics: 統計資訊

    Returns:
        Manifest dict
    """
    # 定義檔案列表
    table_files = [
        "skill_heads.csv",
        "skill_metadata.csv",
        "skill_chunk_metadata.csv",
        "skill_document_mapping.csv",
        "skill_overviews.csv"
    ]

    faiss_files = [
        "index.faiss",
        "index.pkl"
    ]

    # 計算所有檔案的 checksums
    checksums = {}
    for filename in table_files + faiss_files:
        file_path = export_dir / filename
        if file_path.exists():
            checksums[filename] = calculate_file_checksum(str(file_path))
        else:
            raise FileNotFoundError(f"Expected file not found: {filename}")

    # 建立 manifest
    manifest = {
        "version": "1.0",
        "export_timestamp": datetime.utcnow().isoformat(),
        "export_tool": "DocAI-SkillExport",

        "skill_info": {
            "head_id": head_id,
            "skill_name": skill_name,
            "description": skill_info.get("description", ""),
            "created_at": skill_info.get("created_at", ""),
            "updated_at": skill_info.get("updated_at", "")
        },

        "statistics": {
            "total_documents": statistics.get("total_documents", 0),
            "total_chunks": statistics.get("total_chunks", 0),
            "faiss_index_size_bytes": statistics.get("faiss_index_size_bytes", 0),
            "embedding_model": statistics.get("embedding_model", "BAAI/bge-m3"),
            "embedding_dimension": statistics.get("embedding_dimension", 1024)
        },

        "file_list": {
            "tables": table_files,
            "faiss_files": faiss_files,
            "pdf_files": []  # Phase 1: No PDF
        },

        "checksums": checksums
    }

    # 寫入 manifest.json
    manifest_path = export_dir / "manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return manifest
```

### 為什麼要生成 manifest.json？

**必要性**: 🔴 **Critical** (資料完整性驗證)

| 用途 | 說明 | 缺少後果 |
|------|------|----------|
| **完整性驗證** | 透過 SHA-256 checksums 驗證檔案未損壞 | 無法檢測資料損壞 |
| **版本控制** | 記錄 export tool 版本與格式版本 | 相容性問題 |
| **匯入指引** | 提供匯入所需的所有資訊 | 匯入失敗率高 |
| **統計資訊** | 快速了解 Skill 規模 | 無法預估匯入時間 |
| **模型驗證** | 確認嵌入模型與維度 | 向量不相容 |

---

## 匯出後的驗證方法

### 1. 檔案完整性驗證

```python
async def verify_export_integrity(
    export_zip: str,
    manifest: Dict[str, Any]
) -> Dict[str, Any]:
    """
    驗證匯出檔案的完整性

    Args:
        export_zip: 匯出的 ZIP 檔案路徑
        manifest: Manifest dict

    Returns:
        驗證結果 dict
    """
    import zipfile
    import tempfile
    import shutil

    results = {
        "status": "success",
        "verified_files": 0,
        "failed_files": [],
        "missing_files": [],
        "checksum_mismatches": []
    }

    # 解壓縮到臨時目錄
    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(export_zip, 'r') as zf:
            zf.extractall(temp_dir)

        temp_path = Path(temp_dir)

        # 驗證所有檔案存在且 checksum 正確
        expected_files = (
            manifest["file_list"]["tables"] +
            manifest["file_list"]["faiss_files"] +
            ["manifest.json"]
        )

        for filename in expected_files:
            file_path = temp_path / filename

            # 檢查檔案存在
            if not file_path.exists():
                results["missing_files"].append(filename)
                results["status"] = "failed"
                continue

            # 驗證 checksum (除了 manifest.json 本身)
            if filename != "manifest.json":
                expected_checksum = manifest["checksums"][filename]
                actual_checksum = calculate_file_checksum(str(file_path))

                if expected_checksum != actual_checksum:
                    results["checksum_mismatches"].append({
                        "file": filename,
                        "expected": expected_checksum,
                        "actual": actual_checksum
                    })
                    results["status"] = "failed"
                else:
                    results["verified_files"] += 1

    return results
```

### 2. 資料一致性驗證

```python
async def verify_export_consistency(
    export_dir: Path,
    manifest: Dict[str, Any]
) -> Dict[str, Any]:
    """
    驗證匯出資料的一致性

    檢查項目:
    1. SQLite 表之間的關聯完整性
    2. FAISS 向量數量 = skill_chunk_metadata 記錄數
    3. total_chunks 統計正確

    Args:
        export_dir: 匯出目錄
        manifest: Manifest dict

    Returns:
        驗證結果 dict
    """
    import csv
    import faiss
    import pickle

    results = {
        "status": "success",
        "checks": []
    }

    # Check 1: 讀取 skill_heads.csv
    with open(export_dir / "skill_heads.csv", 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        heads = list(reader)

    if len(heads) != 1:
        results["checks"].append({
            "check": "skill_heads_count",
            "status": "failed",
            "expected": 1,
            "actual": len(heads)
        })
        results["status"] = "failed"
    else:
        results["checks"].append({
            "check": "skill_heads_count",
            "status": "passed"
        })

    # Check 2: 讀取 skill_metadata.csv 並統計 documents
    with open(export_dir / "skill_metadata.csv", 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        documents = list(reader)

    expected_docs = manifest["statistics"]["total_documents"]
    if len(documents) != expected_docs:
        results["checks"].append({
            "check": "document_count",
            "status": "failed",
            "expected": expected_docs,
            "actual": len(documents)
        })
        results["status"] = "failed"
    else:
        results["checks"].append({
            "check": "document_count",
            "status": "passed"
        })

    # Check 3: 讀取 skill_chunk_metadata.csv 並統計 chunks
    with open(export_dir / "skill_chunk_metadata.csv", 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        chunks = list(reader)

    expected_chunks = manifest["statistics"]["total_chunks"]
    if len(chunks) != expected_chunks:
        results["checks"].append({
            "check": "chunk_count",
            "status": "failed",
            "expected": expected_chunks,
            "actual": len(chunks)
        })
        results["status"] = "failed"
    else:
        results["checks"].append({
            "check": "chunk_count",
            "status": "passed"
        })

    # Check 4: 驗證 FAISS 向量數量
    index = faiss.read_index(str(export_dir / "index.faiss"))
    faiss_vector_count = index.ntotal

    if faiss_vector_count != expected_chunks:
        results["checks"].append({
            "check": "faiss_vector_count",
            "status": "failed",
            "expected": expected_chunks,
            "actual": faiss_vector_count
        })
        results["status"] = "failed"
    else:
        results["checks"].append({
            "check": "faiss_vector_count",
            "status": "passed"
        })

    # Check 5: 驗證 FAISS 維度
    expected_dim = manifest["statistics"]["embedding_dimension"]
    if index.d != expected_dim:
        results["checks"].append({
            "check": "faiss_dimension",
            "status": "failed",
            "expected": expected_dim,
            "actual": index.d
        })
        results["status"] = "failed"
    else:
        results["checks"].append({
            "check": "faiss_dimension",
            "status": "passed"
        })

    # Check 6: 驗證 index.pkl 映射完整性
    with open(export_dir / "index.pkl", 'rb') as f:
        pkl_data = pickle.load(f)

    mapping_count = len(pkl_data.get("chunk_id_mapping", {}))
    if mapping_count != expected_chunks:
        results["checks"].append({
            "check": "pkl_mapping_count",
            "status": "failed",
            "expected": expected_chunks,
            "actual": mapping_count
        })
        results["status"] = "failed"
    else:
        results["checks"].append({
            "check": "pkl_mapping_count",
            "status": "passed"
        })

    return results
```

---

## 匯入流程與資料重建

### 匯入流程概述

```
┌─────────────────────────────────────────────────────────────┐
│                      Import Process                          │
└─────────────────────────────────────────────────────────────┘

1. Upload & Validation
   ├─ Validate ZIP format
   ├─ Extract to temp directory
   ├─ Parse manifest.json
   └─ Verify checksums

2. ID Regeneration
   ├─ Generate new head_id
   ├─ Generate new skill_ids
   ├─ Generate new chunk_ids
   └─ Build ID mapping dict

3. Database Import (Transaction)
   ├─ BEGIN TRANSACTION
   ├─ Import skill_heads.csv
   ├─ Import skill_metadata.csv (remap IDs)
   ├─ Import skill_chunk_metadata.csv (remap IDs)
   ├─ Import skill_document_mapping.csv (remap IDs)
   ├─ Import skill_overviews.csv (remap IDs)
   └─ COMMIT (or ROLLBACK on error)

4. FAISS Setup
   ├─ Create directory data/faiss_indices/skills/{new_head_id}/
   ├─ Copy index.faiss
   ├─ Update index.pkl (remap chunk IDs)
   └─ Verify index integrity

5. Cleanup & Validation
   ├─ Delete temp files
   ├─ Verify import consistency
   └─ Return success response
```

### ID 重新映射

#### 為什麼需要重新生成 ID？

**原因**: 避免與目標系統現有資料衝突

| ID 類型 | 重新生成原因 | 映射方式 |
|---------|--------------|----------|
| `head_id` | 目標系統可能已有相同 head_id | 生成新 UUID |
| `skill_id` | 避免與現有 documents 衝突 | 基於新 head_id 生成 |
| `chunk_id` | 維持與 skill_id 的關聯 | 基於新 skill_id 生成 |

#### ID 映射實作

```python
from typing import Dict, List
import uuid
from datetime import datetime

def generate_id_mapping(
    manifest: Dict,
    csv_data: Dict[str, List[Dict]]
) -> Dict[str, Dict[str, str]]:
    """
    生成 ID 映射表

    Args:
        manifest: Manifest dict
        csv_data: 所有 CSV 資料的 dict

    Returns:
        ID 映射表:
        {
            "head_id": "head_xxx_new",
            "skill_ids": {"skill_001_old": "skill_001_new", ...},
            "chunk_ids": {"chunk_001_old": "chunk_001_new", ...}
        }
    """
    # 生成新 head_id
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_head_id = f"head_{timestamp}_{uuid.uuid4().hex[:8]}"

    # 讀取舊的 skill_ids
    old_skill_ids = [row["skill_id"] for row in csv_data["skill_metadata"]]

    # 生成新 skill_ids
    skill_id_mapping = {}
    for i, old_skill_id in enumerate(old_skill_ids):
        new_skill_id = f"skill_{timestamp}_{uuid.uuid4().hex[:8]}_{i:03d}"
        skill_id_mapping[old_skill_id] = new_skill_id

    # 讀取舊的 chunk_ids
    old_chunk_ids = [row["chunk_id"] for row in csv_data["skill_chunk_metadata"]]

    # 生成新 chunk_ids
    chunk_id_mapping = {}
    for i, old_chunk_id in enumerate(old_chunk_ids):
        new_chunk_id = f"chunk_{timestamp}_{uuid.uuid4().hex[:8]}_{i:06d}"
        chunk_id_mapping[old_chunk_id] = new_chunk_id

    return {
        "head_id": new_head_id,
        "skill_ids": skill_id_mapping,
        "chunk_ids": chunk_id_mapping
    }
```

### SQLite 匯入方法

```python
import csv
import sqlite3
from typing import Dict, List

async def import_with_transaction(
    db_path: str,
    csv_data: Dict[str, List[Dict]],
    id_mapping: Dict[str, Dict[str, str]]
) -> bool:
    """
    使用 transaction 匯入所有資料

    Args:
        db_path: SQLite 資料庫路徑
        csv_data: 所有 CSV 資料
        id_mapping: ID 映射表

    Returns:
        True if successful, raises exception on failure
    """
    conn = sqlite3.connect(db_path)

    try:
        # BEGIN TRANSACTION
        conn.execute("BEGIN TRANSACTION")

        # 1. Import skill_heads
        for row in csv_data["skill_heads"]:
            conn.execute("""
                INSERT INTO skill_heads (
                    head_id, skill_name, description, category,
                    display_order, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                id_mapping["head_id"],  # 使用新 head_id
                row["skill_name"],
                row["description"],
                row["category"],
                row["display_order"],
                row["enabled"],
                row["created_at"],
                row["updated_at"]
            ))

        # 2. Import skill_metadata
        for row in csv_data["skill_metadata"]:
            old_skill_id = row["skill_id"]
            new_skill_id = id_mapping["skill_ids"][old_skill_id]

            # Remap parent_skill_id if needed
            old_parent_id = row["parent_skill_id"]
            new_parent_id = (
                id_mapping["skill_ids"].get(old_parent_id, "root")
                if old_parent_id != "root"
                else "root"
            )

            conn.execute("""
                INSERT INTO skill_metadata (
                    skill_id, skill_name, skill_description, skill_category,
                    skill_level, tags, related_skills, total_chunks,
                    created_at, updated_at, metadata, parent_skill_id,
                    source_name, head_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                new_skill_id,
                row["skill_name"],
                row["skill_description"],
                row["skill_category"],
                row["skill_level"],
                row["tags"],
                row["related_skills"],
                row["total_chunks"],
                row["created_at"],
                row["updated_at"],
                row["metadata"],
                new_parent_id,
                row["source_name"],
                id_mapping["head_id"]  # 使用新 head_id
            ))

        # 3. Import skill_chunk_metadata
        for row in csv_data["skill_chunk_metadata"]:
            old_chunk_id = row["chunk_id"]
            old_skill_id = row["skill_id"]

            new_chunk_id = id_mapping["chunk_ids"][old_chunk_id]
            new_skill_id = id_mapping["skill_ids"][old_skill_id]

            conn.execute("""
                INSERT INTO skill_chunk_metadata (
                    chunk_id, skill_id, document_id, document_name,
                    page_number, chunk_index, chunk_text,
                    embedding_model, embedding_dimension, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                new_chunk_id,
                new_skill_id,
                row["document_id"],
                row["document_name"],
                row["page_number"],
                row["chunk_index"],
                row["chunk_text"],
                row["embedding_model"],
                row["embedding_dimension"],
                row["metadata"],
                row["created_at"]
            ))

        # 4. Import skill_document_mapping
        for row in csv_data["skill_document_mapping"]:
            old_skill_id = row["skill_id"]
            new_skill_id = id_mapping["skill_ids"][old_skill_id]

            conn.execute("""
                INSERT INTO skill_document_mapping (
                    skill_id, file_id, relevance_score, created_at
                ) VALUES (?, ?, ?, ?)
            """, (
                new_skill_id,
                row["file_id"],
                row["relevance_score"],
                row["created_at"]
            ))

        # 5. Import skill_overviews
        for row in csv_data["skill_overviews"]:
            old_skill_id = row["skill_id"]
            new_skill_id = id_mapping["skill_ids"][old_skill_id]

            conn.execute("""
                INSERT INTO skill_overviews (
                    skill_id, overview, created_at, updated_at
                ) VALUES (?, ?, ?, ?)
            """, (
                new_skill_id,
                row["overview"],
                row["created_at"],
                row["updated_at"]
            ))

        # COMMIT TRANSACTION
        conn.commit()
        return True

    except Exception as e:
        # ROLLBACK on any error
        conn.rollback()
        raise ImportError(f"Database import failed: {e}") from e

    finally:
        conn.close()
```

### FAISS 匯入方法

```python
import faiss
import pickle
import shutil
from pathlib import Path

async def import_faiss_index(
    source_dir: Path,
    target_base_dir: Path,
    new_head_id: str,
    chunk_id_mapping: Dict[str, str]
) -> bool:
    """
    匯入並更新 FAISS 索引

    Args:
        source_dir: 解壓縮的臨時目錄 (包含 index.faiss, index.pkl)
        target_base_dir: FAISS 基礎目錄 (e.g., "data/faiss_indices/skills")
        new_head_id: 新的 head_id
        chunk_id_mapping: Chunk ID 映射表

    Returns:
        True if successful
    """
    # 建立目標目錄
    target_dir = target_base_dir / new_head_id
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. 複製 index.faiss (FAISS 索引不需要修改)
        shutil.copy2(
            source_dir / "index.faiss",
            target_dir / "index.faiss"
        )

        # 2. 讀取並更新 index.pkl
        with open(source_dir / "index.pkl", 'rb') as f:
            pkl_data = pickle.load(f)

        # 更新 chunk_id_mapping
        old_mapping = pkl_data["chunk_id_mapping"]
        new_mapping = {}

        for faiss_idx, old_chunk_id in old_mapping.items():
            new_chunk_id = chunk_id_mapping[old_chunk_id]
            new_mapping[faiss_idx] = new_chunk_id

        pkl_data["chunk_id_mapping"] = new_mapping

        # 更新 metadata 中的 skill_id
        if "metadata" in pkl_data:
            pkl_data["metadata"]["skill_id"] = new_head_id

        # 寫入更新後的 index.pkl
        with open(target_dir / "index.pkl", 'wb') as f:
            pickle.dump(pkl_data, f)

        # 3. 驗證 FAISS 索引可讀取
        index = faiss.read_index(str(target_dir / "index.faiss"))

        # 驗證向量數量
        expected_vectors = len(chunk_id_mapping)
        if index.ntotal != expected_vectors:
            raise ValueError(
                f"FAISS index vector count mismatch: "
                f"expected {expected_vectors}, got {index.ntotal}"
            )

        return True

    except Exception as e:
        # 清理失敗的目錄
        if target_dir.exists():
            shutil.rmtree(target_dir)
        raise ImportError(f"FAISS import failed: {e}") from e
```

---

## 完整測試方案

### 測試環境準備

```python
import tempfile
import shutil
from pathlib import Path

async def prepare_test_environment() -> Dict[str, Path]:
    """
    準備測試環境

    Returns:
        Dict with paths:
        {
            "source_db": Path,  # 原始資料庫 (備份)
            "target_db": Path,  # 目標資料庫 (匯入測試)
            "export_dir": Path,  # 匯出目錄
            "import_dir": Path   # 匯入目錄
        }
    """
    test_root = Path(tempfile.mkdtemp(prefix="skill_export_import_test_"))

    # 複製原始資料庫到測試環境
    source_db = Path("./data/skill_metadata.db")
    test_source_db = test_root / "source" / "skill_metadata.db"
    test_source_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_db, test_source_db)

    # 建立空白目標資料庫
    test_target_db = test_root / "target" / "skill_metadata.db"
    test_target_db.parent.mkdir(parents=True, exist_ok=True)

    # 初始化目標資料庫結構
    from app.Providers.skill_metadata_provider.client import SkillMetadataProvider
    provider = SkillMetadataProvider(db_path=str(test_target_db))
    await provider.initialize_database()

    # 建立匯出/匯入目錄
    export_dir = test_root / "export"
    import_dir = test_root / "import"
    export_dir.mkdir(parents=True, exist_ok=True)
    import_dir.mkdir(parents=True, exist_ok=True)

    return {
        "source_db": test_source_db,
        "target_db": test_target_db,
        "export_dir": export_dir,
        "import_dir": import_dir,
        "test_root": test_root
    }
```

### 測試案例 1: 匯出驗證

```python
async def test_export_verification():
    """
    測試匯出資料的完整性與一致性
    """
    # 準備測試環境
    env = await prepare_test_environment()

    # 選擇測試 skill (使用實際 head_id)
    test_head_id = "head_20251225_ml_001"

    # 執行匯出
    export_result = await export_skill_complete(
        db_path=str(env["source_db"]),
        head_id=test_head_id,
        output_dir=env["export_dir"]
    )

    # 驗證檔案完整性
    integrity_result = await verify_export_integrity(
        export_zip=export_result["zip_file"],
        manifest=export_result["manifest"]
    )

    assert integrity_result["status"] == "success", \
        f"Integrity check failed: {integrity_result}"

    # 驗證資料一致性
    consistency_result = await verify_export_consistency(
        export_dir=env["export_dir"],
        manifest=export_result["manifest"]
    )

    assert consistency_result["status"] == "success", \
        f"Consistency check failed: {consistency_result}"

    print("✅ Export verification passed")
```

### 測試案例 2: 匯入驗證

```python
async def test_import_verification():
    """
    測試匯入後資料的完整性與一致性
    """
    # 準備測試環境
    env = await prepare_test_environment()

    # 執行匯出
    test_head_id = "head_20251225_ml_001"
    export_result = await export_skill_complete(
        db_path=str(env["source_db"]),
        head_id=test_head_id,
        output_dir=env["export_dir"]
    )

    # 執行匯入到目標資料庫
    import_result = await import_skill_complete(
        zip_file=export_result["zip_file"],
        target_db=str(env["target_db"]),
        target_faiss_dir=env["test_root"] / "target_faiss"
    )

    # 驗證匯入結果
    assert import_result["status"] == "success", \
        f"Import failed: {import_result}"

    # 比對資料一致性
    comparison_result = await compare_source_and_target(
        source_db=str(env["source_db"]),
        source_head_id=test_head_id,
        target_db=str(env["target_db"]),
        target_head_id=import_result["new_head_id"]
    )

    assert comparison_result["match_percentage"] > 99.9, \
        f"Data mismatch: {comparison_result}"

    print("✅ Import verification passed")
```

### 測試案例 3: 資料比對

```python
async def compare_source_and_target(
    source_db: str,
    source_head_id: str,
    target_db: str,
    target_head_id: str
) -> Dict[str, Any]:
    """
    比對匯出前後資料的一致性

    Returns:
        比對結果:
        {
            "match_percentage": 99.95,
            "mismatches": [],
            "statistics": {...}
        }
    """
    source_conn = sqlite3.connect(source_db)
    target_conn = sqlite3.connect(target_db)

    try:
        # 比對 skill_metadata 數量
        source_docs = source_conn.execute("""
            SELECT COUNT(*) FROM skill_metadata WHERE head_id = ?
        """, (source_head_id,)).fetchone()[0]

        target_docs = target_conn.execute("""
            SELECT COUNT(*) FROM skill_metadata WHERE head_id = ?
        """, (target_head_id,)).fetchone()[0]

        assert source_docs == target_docs, \
            f"Document count mismatch: source={source_docs}, target={target_docs}"

        # 比對 skill_chunk_metadata 數量
        source_chunks = source_conn.execute("""
            SELECT COUNT(*) FROM skill_chunk_metadata
            WHERE skill_id IN (SELECT skill_id FROM skill_metadata WHERE head_id = ?)
        """, (source_head_id,)).fetchone()[0]

        target_chunks = target_conn.execute("""
            SELECT COUNT(*) FROM skill_chunk_metadata
            WHERE skill_id IN (SELECT skill_id FROM skill_metadata WHERE head_id = ?)
        """, (target_head_id,)).fetchone()[0]

        assert source_chunks == target_chunks, \
            f"Chunk count mismatch: source={source_chunks}, target={target_chunks}"

        # 比對 chunk_text 內容 (抽樣)
        source_texts = source_conn.execute("""
            SELECT chunk_text FROM skill_chunk_metadata
            WHERE skill_id IN (SELECT skill_id FROM skill_metadata WHERE head_id = ?)
            ORDER BY chunk_index
            LIMIT 100
        """, (source_head_id,)).fetchall()

        target_texts = target_conn.execute("""
            SELECT chunk_text FROM skill_chunk_metadata
            WHERE skill_id IN (SELECT skill_id FROM skill_metadata WHERE head_id = ?)
            ORDER BY chunk_index
            LIMIT 100
        """, (target_head_id,)).fetchall()

        matching_texts = sum(1 for s, t in zip(source_texts, target_texts) if s[0] == t[0])
        match_percentage = (matching_texts / len(source_texts)) * 100

        return {
            "match_percentage": match_percentage,
            "mismatches": [],
            "statistics": {
                "source_documents": source_docs,
                "target_documents": target_docs,
                "source_chunks": source_chunks,
                "target_chunks": target_chunks,
                "sampled_texts": len(source_texts),
                "matching_texts": matching_texts
            }
        }

    finally:
        source_conn.close()
        target_conn.close()
```

---

## 總結

### 資料來源清單

| # | 資料來源 | 必要性 | 檔案格式 | 用途 |
|---|----------|--------|----------|------|
| 1 | skill_heads | 🔴 Critical | CSV | Skill 定義 |
| 2 | skill_metadata | 🔴 Critical | CSV | 文件元資料 |
| 3 | skill_chunk_metadata | 🔴 Critical | CSV | Chunk 文字內容 |
| 4 | skill_document_mapping | 🟡 Optional | CSV | 跨系統映射 |
| 5 | skill_overviews | 🟢 Recommended | CSV | LLM 生成摘要 |
| 6 | index.faiss | 🔴 Critical | Binary | 向量索引 |
| 7 | index.pkl | 🔴 Critical | Pickle | 索引元資料 |
| 8 | manifest.json | 🔴 Critical | JSON | 完整性驗證 |

### 關鍵技術要點

1. **ID 重新生成**: 避免衝突，維持資料完整性
2. **Transaction 管理**: 使用 BEGIN/COMMIT/ROLLBACK 確保原子性
3. **Checksum 驗證**: SHA-256 確保資料未損壞
4. **Batch Processing**: 大量資料使用批次處理避免記憶體溢出
5. **FAISS 映射更新**: index.pkl 的 chunk_id_mapping 必須更新

---

**文檔版本**: 1.0
**建立日期**: 2025-12-25
**最後更新**: 2025-12-25
**狀態**: 完整技術文檔
**下一步**: 等待用戶確認後開始實施
