# Skill FAISS 儲存位置與命名規則分析 - 2025-12-25

## 問題

用戶問題：「請找出匯入一個文件到某個技能時，faiss檔案是儲存到哪？如何命名包含faiss及pkl檔的資料夾名稱」

---

## FAISS 儲存架構

### 儲存位置階層

```
data/faiss_indices/
├── files/                    # File-Based 系統的向量索引
│   └── file_{timestamp}_{hash}/
│       ├── index.faiss
│       └── index.pkl
│
└── skills/                   # Skill-Based 系統的向量索引 ✅ 這裡
    └── skill_{timestamp}_{name_hash}_{file_hash}/
        ├── index.faiss       # FAISS 向量索引檔案
        └── index.pkl         # Python pickle 元資料檔案
```

**關鍵路徑**：
- **基礎目錄**：`data/faiss_indices/` (定義於 `FAISS_PERSIST_DIR` 常數)
- **Skill 子目錄**：`data/faiss_indices/skills/`
- **完整路徑**：`data/faiss_indices/skills/{skill_id}/`

---

## 資料夾命名規則

### Skill ID 格式

```python
skill_id = f"skill_{timestamp}_{name_hash}_{file_hash}"
```

### 命名元件拆解

| 元件 | 格式 | 範例 | 說明 |
|------|------|------|------|
| **Prefix** | `skill_` | `skill_` | 固定前綴，識別為 Skill 系統 |
| **Timestamp** | `YYYYMMDD_HHMMSS` | `20251216_124010` | 上傳時間 (UTC) |
| **Name Hash** | MD5[:8] | `b45c5a1f` | Skill 名稱的 MD5 前 8 位 |
| **File Hash** | MD5[:6] | `d81758` | PDF 檔名的 MD5 前 6 位 |

### 範例資料夾名稱

```
skill_20251216_124010_b45c5a1f_d81758
│      │         │        │        └─ File Hash (6 chars)
│      │         │        └────────── Name Hash (8 chars)
│      │         └─────────────────── Timestamp (UTC)
│      └───────────────────────────── Prefix
```

**實際案例**：
```
skill_20251216_124010_b45c5a1f_d81758/
├── index.faiss   # 847,917 bytes (FAISS 向量索引)
└── index.pkl     #  37,974 bytes (Metadata pickle)
```

---

## 程式碼流程分析

### 1. Skill ID 生成 (app/api/v1/endpoints/skills.py)

**位置**：Lines 945-953

```python
# Generate unique skill_id with timestamp, skill name hash, and filename hash
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
name_hash = hashlib.md5(skill_name.encode('utf-8')).hexdigest()[:8]
file_hash = hashlib.md5(pdf_path.name.encode('utf-8')).hexdigest()[:6]

skill_id = f"skill_{timestamp}_{name_hash}_{file_hash}"
```

**範例**：
- **Skill Name**: "民法" → MD5 → `b45c5a1f` (前 8 位)
- **PDF File**: "民法.pdf" → MD5 → `d81758` (前 6 位)
- **Timestamp**: 2025-12-16 12:40:10 UTC → `20251216_124010`
- **Result**: `skill_20251216_124010_b45c5a1f_d81758`

---

### 2. FAISS 儲存路徑設定 (app/Providers/vector_store_provider/client.py)

**初始化** (Lines 59-66):

```python
# FAISS persistence directory with store_type isolation
self._faiss_persist_dir = Path(FAISS_PERSIST_DIR)  # "data/faiss_indices"
self._faiss_file_dir = self._faiss_persist_dir / "files"
self._faiss_skill_dir = self._faiss_persist_dir / "skills"

# Create directories for both store types
self._faiss_file_dir.mkdir(parents=True, exist_ok=True)
self._faiss_skill_dir.mkdir(parents=True, exist_ok=True)
```

**儲存方法** (Lines 74-104):

```python
def _save_faiss_store(self, store_id: str, vector_store: Any, store_type: str = "file") -> bool:
    try:
        # Determine base directory by store type
        if store_type == "skill":
            base_dir = self._faiss_skill_dir  # data/faiss_indices/skills/
        else:
            base_dir = self._faiss_file_dir   # data/faiss_indices/files/

        store_path = base_dir / store_id
        store_path.mkdir(parents=True, exist_ok=True)

        # Save FAISS index (creates index.faiss and index.pkl)
        vector_store.save_local(str(store_path))

        logger.info(f"Saved FAISS store '{store_id}' ({store_type}) to {store_path}")
        return True
```

**關鍵邏輯**：
1. `store_type='skill'` → 使用 `self._faiss_skill_dir` (`data/faiss_indices/skills/`)
2. 建立資料夾：`{base_dir}/{skill_id}/`
3. LangChain 的 `vector_store.save_local()` 生成兩個檔案：
   - `index.faiss` - FAISS 向量索引（二進位格式）
   - `index.pkl` - Python pickle 格式的元資料

---

### 3. 上傳與處理流程 (app/api/v1/endpoints/skills.py)

**API 調用流程**：

```python
# Lines 883-922: upload_source_to_skill endpoint
@router.post("/{skill_name}/upload-source")
async def upload_source_to_skill(skill_name: str, file: UploadFile):
    # 1. Save PDF to uploadfiles/pdf/
    pdf_path = upload_dir / file.filename

    # 2. Process PDF → FAISS
    await process_pdf_for_skill(skill_name, pdf_path, ...)

# Lines 914-1189: process_pdf_for_skill function
async def process_pdf_for_skill(skill_name: str, pdf_path: Path, ...):
    # 1. Generate skill_id
    skill_id = f"skill_{timestamp}_{name_hash}_{file_hash}"

    # 2. Extract text from PDF (PyPDF2)
    # 3. Generate embeddings (BGE-M3, 1024 dim)
    # 4. Create FAISS store
    vector_provider = VectorStoreProvider(persist_directory="./data/faiss_indices")

    store_id = vector_provider.create_store_from_texts(
        texts=texts,
        embeddings=EmbeddingWrapper(embedding_provider),
        metadatas=metadata_list,
        file_id=skill_id,
        store_type='skill',  # ✅ Key parameter for path routing
        precomputed_embeddings=all_embeddings
    )

    # 5. Save to SQLite metadata
    await metadata_provider.create_skill(skill_id=skill_id, ...)
```

---

## 檔案系統實證

### 實際儲存範例

**命令**：
```bash
ls -la data/faiss_indices/skills/skill_20251216_124010_b45c5a1f_d81758/
```

**輸出**：
```
total 1744
drwxr-xr-x   4 xrickliao  staff     128 Dec 16 20:40 .
drwxr-xr-x@ 19 xrickliao  staff     608 Dec 16 20:40 ..
-rw-r--r--   1 xrickliao  staff  847917 Dec 16 20:40 index.faiss
-rw-r--r--   1 xrickliao  staff   37974 Dec 16 20:40 index.pkl
```

**檔案說明**：

| 檔案 | 大小 | 格式 | 內容 |
|------|------|------|------|
| `index.faiss` | 847,917 bytes | Binary | FAISS 向量索引（1024 dim embeddings） |
| `index.pkl` | 37,974 bytes | Pickle | Metadata (skill_id, chunk_index, source_file, etc.) |

---

## 完整資料夾結構

### 當前系統狀態

```bash
data/faiss_indices/skills/
├── skill_20251126_104421_4fdb3e9b/
├── skill_20251126_104649_f333015b/
├── skill_20251128_074913_b7380bf3/
├── skill_20251202_064106_f333015b/
├── skill_20251211_174437_48af4341_feb60e/
├── skill_20251214_091738_2a43e5ac_9ed582/
├── skill_20251214_091909_48af4341_feb60e/
├── skill_20251214_120435_b45c5a1f_d81758/
├── skill_20251214_120609_b45c5a1f_4d7aea/
├── skill_20251214_122224_2a43e5ac_2f3182/
├── skill_20251214_122333_2a43e5ac_5e9d9a/
├── skill_20251214_122409_2a43e5ac_d03a77/
├── skill_20251214_123701_2a43e5ac_a56893/
├── skill_20251214_124019_d01fd9b0_53c4c0/
├── skill_20251216_123603_2a43e5ac_9ed582/
├── skill_20251216_123910_48af4341_feb60e/
└── skill_20251216_124010_b45c5a1f_d81758/   # ✅ 最新上傳
    ├── index.faiss
    └── index.pkl
```

**統計**：
- 總 Skills：17 個
- 每個資料夾包含：2 個檔案 (index.faiss + index.pkl)

---

## 關鍵設計決策

### 1. 路徑隔離設計

**目的**：完全分離 File-Based 和 Skill-Based 系統

```python
# File-Based: data/faiss_indices/files/{file_id}/
# Skill-Based: data/faiss_indices/skills/{skill_id}/
```

**優點**：
- ✅ 避免 ID 衝突
- ✅ 獨立管理與清理
- ✅ 不同 embedding 維度 (384 vs 1024)

---

### 2. 命名唯一性保證

**方法**：Timestamp + Name Hash + File Hash

**範例情境**：
```
同一個 Skill "民法" 上傳兩個不同 PDF：

1. 民法-總則.pdf (12:40:10)
   → skill_20251216_124010_b45c5a1f_d81758

2. 民法-債編.pdf (12:45:22)
   → skill_20251216_124522_b45c5a1f_3a9f2b

相同 Name Hash (b45c5a1f)，但不同 File Hash 和 Timestamp
```

**保證**：
- Timestamp：秒級精度，避免時間碰撞
- Name Hash：相同 skill 保持一致性
- File Hash：不同檔案必然不同

---

### 3. LangChain 儲存格式

**使用**：`vector_store.save_local(str(store_path))`

**生成檔案**：

1. **index.faiss** - FAISS 向量索引
   - Format: Binary (FAISS native format)
   - Content: Vector embeddings (1024 dimensions for BGE-M3)
   - Size: ~850 KB for typical PDFs

2. **index.pkl** - Metadata pickle
   - Format: Python pickle
   - Content:
     ```python
     {
         'docstore': {...},           # Document content
         'index_to_docstore_id': {...},  # Index mapping
         'metadatas': [               # Chunk metadata
             {
                 'skill_id': 'skill_...',
                 'chunk_index': 0,
                 'source_file': 'example.pdf',
                 'page_number': 1,
                 ...
             },
             ...
         ]
     }
     ```
   - Size: ~38 KB for typical PDFs

---

## 載入機制

### 啟動時自動載入 (Lines 147-184)

```python
def _load_all_faiss_stores(self):
    """Load all persisted FAISS stores on startup"""
    from app.Providers.embedding_provider.client import get_embedding_provider
    from langchain_community.vectorstores import FAISS

    # Load File-Based stores (384 dim)
    if self._faiss_file_dir.exists():
        for store_dir in self._faiss_file_dir.iterdir():
            if store_dir.is_dir():
                embedding_provider = get_embedding_provider()
                vector_store = FAISS.load_local(
                    str(store_dir),
                    embedding_provider,
                    allow_dangerous_deserialization=True
                )
                self._stores[store_dir.name] = vector_store

    # Load Skill-Based stores (1024 dim, BGE-M3)
    if self._faiss_skill_dir.exists():
        for store_dir in self._faiss_skill_dir.iterdir():
            if store_dir.is_dir():
                from app.Providers.embedding_provider.bge_m3_provider import BGEM3EmbeddingProvider
                embedding_provider = BGEM3EmbeddingProvider()
                vector_store = FAISS.load_local(
                    str(store_dir),
                    embedding_provider,
                    allow_dangerous_deserialization=True
                )
                self._stores[store_dir.name] = vector_store
```

**重點**：
- File stores：使用 384-dim embedding provider
- Skill stores：使用 1024-dim BGE-M3 provider
- `allow_dangerous_deserialization=True`：信任自己的 FAISS 索引

---

## 查詢流程

### Lazy Loading 機制 (Lines 217-260)

```python
def _try_lazy_load_store(self, store_id: str) -> Optional[Any]:
    """Try loading from disk if not in memory"""
    # Try skill directory first
    skill_path = self._faiss_skill_dir / store_id
    if skill_path.exists():
        from app.Providers.embedding_provider.bge_m3_provider import BGEM3EmbeddingProvider
        embedding_provider = BGEM3EmbeddingProvider()
        return self._load_faiss_store(store_id, embedding_provider, store_type="skill")

    # Fall back to file directory
    file_path = self._faiss_file_dir / store_id
    if file_path.exists():
        from app.Providers.embedding_provider.client import get_embedding_provider
        embedding_provider = get_embedding_provider()
        return self._load_faiss_store(store_id, embedding_provider, store_type="file")

    return None
```

**優勢**：
- 不需提前載入所有索引
- 節省記憶體
- 支援動態新增索引

---

## 相關檔案

| 檔案 | Lines | 功能 |
|------|-------|------|
| `app/api/v1/endpoints/skills.py` | 945-953 | Skill ID 生成邏輯 |
| `app/api/v1/endpoints/skills.py` | 914-1189 | PDF 處理與 FAISS 儲存流程 |
| `app/Providers/vector_store_provider/client.py` | 19 | `FAISS_PERSIST_DIR` 常數定義 |
| `app/Providers/vector_store_provider/client.py` | 59-66 | 路徑初始化與目錄建立 |
| `app/Providers/vector_store_provider/client.py` | 74-104 | `_save_faiss_store()` 儲存方法 |
| `app/Providers/vector_store_provider/client.py` | 106-145 | `_load_faiss_store()` 載入方法 |
| `app/Providers/vector_store_provider/client.py` | 147-184 | `_load_all_faiss_stores()` 啟動載入 |
| `app/Providers/vector_store_provider/client.py` | 217-260 | `_try_lazy_load_store()` 延遲載入 |

---

## 總結

### 問題回答

**Q: 匯入一個文件到某個技能時，faiss 檔案是儲存到哪？**

**A**: `data/faiss_indices/skills/{skill_id}/`

範例：
```
data/faiss_indices/skills/skill_20251216_124010_b45c5a1f_d81758/
├── index.faiss   # FAISS 向量索引
└── index.pkl     # Metadata pickle
```

---

**Q: 如何命名包含 faiss 及 pkl 檔的資料夾名稱？**

**A**: `skill_{timestamp}_{name_hash}_{file_hash}`

範例拆解：
```
skill_20251216_124010_b45c5a1f_d81758
      │         │        │        └─ PDF 檔名 MD5 前 6 位
      │         │        └────────── Skill 名稱 MD5 前 8 位
      │         └─────────────────── UTC 時間戳 (YYYYMMDD_HHMMSS)
      └───────────────────────────── 固定前綴
```

---

### 架構優勢

1. **完全隔離**：Skill 與 File 系統互不干擾
2. **唯一性保證**：Timestamp + Hash 組合避免碰撞
3. **自動載入**：啟動時自動載入所有索引
4. **Lazy Loading**：支援動態載入未在記憶體的索引
5. **維度適配**：Skill (1024) vs File (384) 自動選擇 embedding provider

---

**分析完成時間**：2025-12-25
**狀態**：✅ Complete
