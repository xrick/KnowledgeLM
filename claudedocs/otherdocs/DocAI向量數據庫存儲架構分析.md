<!-- claudedocs/DocAI向量數據庫存儲架構分析.md -->
<!-- claudedocs/vector_database_storage_architecture_analysis.md -->
# DocAI 向量數據庫存儲架構分析

**日期**: 2025-11-03
**主題**: 原始文字內容 (page_content) 的存儲位置與檢索流程分析
**系統版本**: DocAI v1.0

---

## 📋 目錄

1. [核心問題](#核心問題)
2. [答案總結](#答案總結)
3. [支援的向量數據庫後端](#支援的向量數據庫後端)
4. [完整數據存儲架構](#完整數據存儲架構)
5. [檢索流程詳解](#檢索流程詳解)
6. [架構對比與選擇](#架構對比與選擇)
7. [代碼證據](#代碼證據)

---

## 核心問題

**Q: 原始文字內容 (page_content) 存儲在何種資料庫？**

**背景**：
- 常見的 RAG 架構有兩種模式：
  - **分離存儲**：Vector DB 存 embeddings + ID，RDBMS 存文字內容
  - **嵌入式存儲**：Vector DB 同時存 embeddings + 文字內容

**疑問**：DocAI 系統採用哪種架構？文字內容到底存在哪裡？

---

## 答案總結

### ✅ 結論

**原始文字內容直接存儲在向量數據庫中，不是單獨的 RDBMS！**

| 配置後端 | 數據庫類型 | 存儲欄位/方式 | 物理位置 |
|---------|-----------|-------------|---------|
| **Milvus** (預設) | 向量資料庫 | `content: VARCHAR(4096)` | Milvus server (localhost:19530) |
| **FAISS** | In-memory 向量庫 | Python object (pickle) | `./data/vector_store/` |
| **ChromaDB** | 嵌入式向量庫 | SQLite + Parquet | `VECTOR_STORE_PATH` 目錄 |

### 關鍵特點

- ✅ 採用**嵌入式存儲架構**
- ✅ 向量和文字內容存在同一個數據庫
- ✅ 檢索時**一次查詢**即可返回完整內容
- ✅ SQLite 只存文件元數據，**不參與內容檢索**

---

## 支援的向量數據庫後端

### 1️⃣ Milvus (預設配置)

**配置文件**: `app/core/config.py:151`
```python
VECTOR_STORE_BACKEND: str = "milvus"  # 預設值
```

#### Collection Schema

**文件**: `app/Providers/vector_store_provider/milvus_client.py:110-127`

```python
# Collection Schema:
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=64),
    FieldSchema(name="chunk_index", dtype=DataType.INT32),
    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),  # ← 原始文字！
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=384),
    FieldSchema(name="timestamp", dtype=DataType.INT64)
]
```

#### 特點

- **數據庫類型**：專業分散式向量數據庫
- **存儲方式**：Columnar storage，針對向量搜索優化
- **文字欄位**：VARCHAR(4096)，最大 4096 字符
- **索引類型**：IVF_FLAT (預設)
- **距離度量**：L2 (歐式距離)
- **物理位置**：Milvus 服務器 (localhost:19530)

#### 優點
- ✅ 高性能分散式架構
- ✅ 支援大規模數據 (億級)
- ✅ 完善的索引和查詢優化
- ✅ 企業級功能 (高可用、備份)

#### 缺點
- ❌ 需要單獨部署 Milvus 服務
- ❌ 資源消耗較高
- ❌ 配置和維護相對複雜

---

### 2️⃣ FAISS (備用方案)

**配置文件**: `app/core/config.py:152`
```python
VECTOR_STORE_PATH: str = "./data/vector_store"  # FAISS 存儲路徑
```

#### 實現方式

**文件**: `app/Providers/vector_store_provider/client.py:76-89`

```python
from langchain_community.vectorstores import FAISS

vector_store = FAISS.from_texts(
    texts=texts,           # ← 原始文字存在這裡
    embedding=embeddings,
    metadatas=metadatas
)

# Store in memory with file_id as key
self._stores[store_id] = vector_store
```

#### 特點

- **數據庫類型**：In-memory 向量索引庫
- **存儲方式**：Python pickle 格式
- **文字位置**：與向量打包在同一個對象中
- **持久化**：可選保存到磁碟
- **物理位置**：`./data/vector_store/` 目錄

#### 數據結構

```
FAISS VectorStore 對象
├─ index: faiss.IndexFlatL2         # 向量索引
├─ docstore: dict                   # 文檔存儲
│   └─ {
│       doc_id_1: Document(page_content="...", metadata={...}),
│       doc_id_2: Document(page_content="...", metadata={...})
│   }
└─ index_to_docstore_id: dict      # 索引映射
```

#### 優點
- ✅ 無需額外服務，開箱即用
- ✅ 速度極快 (in-memory)
- ✅ 適合開發和小型部署
- ✅ 配置簡單

#### 缺點
- ❌ 受限於單機記憶體
- ❌ 不支援分散式
- ❌ 數據量上限 (通常 < 1M vectors)

---

### 3️⃣ ChromaDB (第三選項)

**實現**: `app/Providers/vector_store_provider/client.py:91-113`

```python
from langchain_community.vectorstores import Chroma

vector_store = Chroma.from_texts(
    texts=texts,           # ← 原始文字
    embedding=embeddings,
    metadatas=metadatas,
    collection_name=self.collection_name,
    persist_directory=str(persist_path)
)
```

#### 特點

- **數據庫類型**：嵌入式向量數據庫
- **存儲方式**：混合存儲
  - SQLite：存元數據和映射
  - Parquet files：存向量數據
  - Documents：存原始文字
- **持久化**：自動持久化到磁碟
- **物理位置**：`VECTOR_STORE_PATH` 配置的目錄

#### 優點
- ✅ 平衡性能和易用性
- ✅ 自動持久化，無需手動管理
- ✅ 支援中等規模數據
- ✅ 豐富的查詢功能

#### 缺點
- ❌ 單機限制
- ❌ 性能不如 Milvus
- ❌ 需要安裝 chromadb 套件

---

## 完整數據存儲架構

```
DocAI 系統數據存儲架構
═══════════════════════════════════════════════════════════

1️⃣ 向量數據庫 (預設: Milvus @ localhost:19530)
   ┌─────────────────────────────────────────────────────┐
   │  Collection: document_embeddings                     │
   │  ├─ Partition: file_abc123                          │
   │  │  ├─ Record 1:                                    │
   │  │  │  ├─ id: 1                                     │
   │  │  │  ├─ file_id: "abc123"                         │
   │  │  │  ├─ chunk_index: 0                            │
   │  │  │  ├─ content: "RAG 是檢索增強生成..."  ✅      │
   │  │  │  ├─ embedding: [0.123, 0.456, ..., 0.789]    │
   │  │  │  └─ timestamp: 1699000000                     │
   │  │  └─ Record 2, 3, 4...                            │
   │  └─ Partition: file_xyz456                          │
   └─────────────────────────────────────────────────────┘
   用途:
   - ✅ 語意相似性搜索 (向量檢索)
   - ✅ 直接返回原始文字內容
   - ✅ 核心檢索引擎

2️⃣ SQLite (./data/docai.db)
   ┌─────────────────────────────────────────────────────┐
   │  Table: file_metadata                                │
   │  ├─ file_id: "abc123"                               │
   │  ├─ filename: "document.pdf"                         │
   │  ├─ file_type: "pdf"                                │
   │  ├─ file_size: 1024000                              │
   │  ├─ upload_time: "2025-11-03 10:00:00"              │
   │  ├─ chunk_count: 50                                 │
   │  ├─ embedding_status: "completed"                    │
   │  └─ metadata_json: "{...}"                          │
   │                                                      │
   │  Table: chunks_metadata (可選)                       │
   │  ├─ chunk_id: "chunk_001"                           │
   │  ├─ file_id: "abc123"                               │
   │  ├─ chunk_index: 0                                  │
   │  ├─ chunk_text: NULL  ❌ 不存實際文字               │
   │  └─ milvus_id: 12345                                │
   └─────────────────────────────────────────────────────┘
   用途:
   - ✅ 文件管理和追蹤
   - ✅ Sidebar 文件列表顯示
   - ✅ 上傳狀態追蹤
   - ❌ 不參與內容檢索

3️⃣ Redis (localhost:6379)
   ┌─────────────────────────────────────────────────────┐
   │  Cache Keys:                                         │
   │  ├─ query_expansion:{hash}                          │
   │  ├─ search_results:{hash}                           │
   │  └─ embeddings:{hash}                               │
   └─────────────────────────────────────────────────────┘
   用途:
   - ✅ 檢索結果快取 (TTL: 30分鐘)
   - ✅ Query expansion 快取 (TTL: 1小時)
   - ✅ Embeddings 快取 (TTL: 24小時)

4️⃣ MongoDB (localhost:27017/docai)
   ┌─────────────────────────────────────────────────────┐
   │  Collection: chat_sessions                           │
   │  └─ Document:                                        │
   │     ├─ session_id: "session_xyz"                    │
   │     ├─ messages: [                                  │
   │     │   {role: "user", content: "...", metadata},  │
   │     │   {role: "assistant", content: "..."}        │
   │     │ ]                                             │
   │     └─ created_at: "2025-11-03T10:00:00Z"          │
   └─────────────────────────────────────────────────────┘
   用途:
   - ✅ 對話歷史記錄
   - ✅ Session 管理
   - ✅ Chat history 上下文

5️⃣ 文件系統 (./uploadfiles/)
   ┌─────────────────────────────────────────────────────┐
   │  ./uploadfiles/pdf/                                  │
   │  ├─ abc123_document.pdf                             │
   │  └─ xyz456_report.pdf                               │
   └─────────────────────────────────────────────────────┘
   用途:
   - ✅ 原始文件備份
   - ✅ 可選的文件下載功能
```

---

## 檢索流程詳解

### 完整的 RAG 檢索流程

```python
# ═══════════════════════════════════════════════════════════
# Phase 1: 用戶提交查詢
# ═══════════════════════════════════════════════════════════

POST /api/v1/chat/stream
{
    "query": "什麼是 RAG？",
    "file_ids": ["abc123", "xyz456"],  # 用戶在 sidebar 勾選的文檔
    "session_id": "session_001",
    "top_k": 5
}

# ═══════════════════════════════════════════════════════════
# Phase 2: Query Enhancement (可選)
# ═══════════════════════════════════════════════════════════

# 文件: app/Services/query_enhancement_service.py
expanded_questions = [
    "什麼是 RAG？",
    "RAG 的工作原理是什麼？",
    "RAG 有哪些應用場景？"
]

# ═══════════════════════════════════════════════════════════
# Phase 3: 向量檢索 (核心流程)
# ═══════════════════════════════════════════════════════════

# 文件: app/Services/retrieval_service.py
async def retrieve_context(query: str, file_ids: List[str], top_k: int):

    # 步驟 3.1: 生成查詢向量
    query_embedding = embedding_provider.embed_query(query)
    # → [0.123, 0.456, ..., 0.789]  (384維向量)

    # 步驟 3.2: 在 Milvus 中搜索
    for file_id in file_ids:
        results = vector_store_provider.similarity_search(
            store_id=file_id,
            query=query,
            k=top_k
        )

    return results


# ═══════════════════════════════════════════════════════════
# Milvus 內部處理 (底層實現)
# ═══════════════════════════════════════════════════════════

# 文件: app/Providers/vector_store_provider/client.py
def similarity_search(store_id: str, query: str, k: int):

    # 步驟 3.3: 向量相似性搜索
    vector_store = self._stores[store_id]  # 獲取 FAISS/Milvus store

    docs = vector_store.similarity_search(query, k=k)
    # Milvus 執行:
    # 1. 將 query 轉成 embedding
    # 2. 計算與所有向量的距離 (L2 或 cosine)
    # 3. 返回 top_k 最相似的記錄

    # 步驟 3.4: 格式化結果 (關鍵步驟！)
    results = []
    for doc in docs:
        results.append({
            "content": doc.page_content,    # ← 從 Milvus 的 content 欄位直接取得！
            "metadata": doc.metadata        # ← 包含 file_id, chunk_index
        })

    return results


# ═══════════════════════════════════════════════════════════
# Phase 4: 實際返回的數據
# ═══════════════════════════════════════════════════════════

results = [
    {
        "content": "RAG（Retrieval-Augmented Generation）是檢索增強生成技術...",
        "metadata": {
            "file_id": "abc123",
            "chunk_index": 5
        },
        "score": 0.15  # 距離越小越相似
    },
    {
        "content": "RAG 結合了檢索系統和生成模型的優勢，通過檢索相關文檔...",
        "metadata": {
            "file_id": "xyz456",
            "chunk_index": 2
        },
        "score": 0.23
    },
    # ... 更多結果
]


# ═══════════════════════════════════════════════════════════
# Phase 5: 構建 Prompt
# ═══════════════════════════════════════════════════════════

# 文件: app/Services/prompt_service.py
def build_rag_prompt(query: str, context_chunks: List[str]):

    # 組裝上下文
    context_str = "\n\n".join([
        f"[文檔片段 {i+1}]\n{chunk}"
        for i, chunk in enumerate(context_chunks)
    ])

    # 填充 system prompt
    system_prompt = f"""你是一位專業的文檔問答助手。

**核心原則：下方的「上下文」來自用戶在側邊欄中勾選的文檔...**

---
[用戶勾選的文檔內容]
{context_str}
---

請根據以上用戶勾選的文檔內容回答問題..."""

    # 構建 messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]

    return messages


# ═══════════════════════════════════════════════════════════
# Phase 6: LLM 生成回答
# ═══════════════════════════════════════════════════════════

response = await llm_client.get_chat_completion_stream(
    messages=messages,
    temperature=0.7
)

# LLM 收到的 messages:
# [
#   {
#     "role": "system",
#     "content": "你是助手...\n\n[文檔片段 1]\nRAG 是檢索增強生成...\n\n[文檔片段 2]\n..."
#   },
#   {
#     "role": "user",
#     "content": "什麼是 RAG？"
#   }
# ]

# LLM 基於文檔內容生成回答...
```

### 關鍵觀察

#### ✅ 一次查詢完成

```python
# 一個 similarity_search 調用就能獲得:
results = vector_store.similarity_search(query, k=5)

# 返回內容包括:
# 1. 文字內容 (page_content)  ← 從 Milvus 的 content 欄位
# 2. 元數據 (metadata)         ← file_id, chunk_index
# 3. 相似度分數 (score)        ← 距離度量

# ❌ 不需要額外查詢 SQLite
# ❌ 不需要額外查詢其他數據庫
# ✅ 所有數據都在向量數據庫中！
```

#### ❌ SQLite 不參與檢索

```python
# SQLite 只在以下場景使用:

# 1. 文件上傳時 - 保存元數據
await file_metadata_provider.add_file_metadata(
    file_id=file_id,
    filename=filename,
    chunk_count=len(chunks)
)

# 2. 文件列表顯示 - 查詢文件信息
files = await file_metadata_provider.get_all_files()

# 3. 刪除文件時 - 清理元數據
await file_metadata_provider.delete_file_metadata(file_id)

# ❌ 檢索時完全不使用 SQLite！
```

---

## 架構對比與選擇

### 兩種常見 RAG 架構

#### 架構 A：分離存儲

```
用戶查詢
  ↓
【Vector DB】: 語意搜索，返回 document IDs
  ↓
【RDBMS】: 根據 IDs 查詢文字內容
  ↓
返回結果
```

**優點**：
- ✅ Vector DB 存儲空間小（只存向量 + ID）
- ✅ 更新文字內容不需重新生成 embeddings
- ✅ 可進行複雜的 SQL 查詢和關聯

**缺點**：
- ❌ 需要兩次查詢（增加延遲）
- ❌ 架構複雜，需維護兩個系統
- ❌ 可能出現數據不一致問題
- ❌ 需要處理連接失敗等異常情況

---

#### 架構 B：嵌入式存儲 (DocAI 採用)

```
用戶查詢
  ↓
【Vector DB】: 語意搜索 + 直接返回文字內容
  ↓
返回結果
```

**優點**：
- ✅ 只需一次查詢，延遲最低
- ✅ 架構簡單，易於維護
- ✅ 原子性保證（向量和文字永遠一致）
- ✅ 無需管理複雜的數據同步

**缺點**：
- ❌ Vector DB 存儲空間較大
- ❌ 更新內容需重新生成 embeddings
- ❌ 無法進行複雜的關聯查詢
- ❌ 文字長度受限（Milvus: VARCHAR(4096)）

---

### 為什麼 DocAI 選擇架構 B？

#### 適用場景分析

**DocAI 的使用場景**：
- 📄 文檔問答系統
- 👥 中小型用戶群
- 📊 數據規模：< 100萬 chunks
- 🔄 更新頻率：低到中等
- ⚡ 性能要求：查詢延遲 < 100ms

**架構 B 的優勢**：
1. **性能最佳化**
   - 單次查詢，延遲最低
   - Milvus 針對此場景優化
   - 適合實時問答

2. **開發效率**
   - 代碼簡單，易於理解
   - 減少 bug 機率
   - 降低運維複雜度

3. **數據一致性**
   - 向量和文字原子性更新
   - 無同步延遲問題
   - 無數據不一致風險

4. **成本效益**
   - 存儲成本可接受（文字壓縮後不大）
   - 減少服務器數量（不需單獨 RDBMS）
   - 運維成本低

---

### 何時考慮架構 A？

如果遇到以下情況，可能需要改為分離存儲：

#### 場景 1: 大規模數據
```
數據規模: > 10M chunks
文字內容: 每個 chunk > 1000 字
存儲成本: Vector DB 容量不足
→ 建議: 分離存儲，Vector DB 只存 ID
```

#### 場景 2: 頻繁更新
```
更新頻率: 每天更新大量文檔
更新模式: 只修改文字，語意不變
重建成本: Embeddings 生成耗時
→ 建議: 文字存 RDBMS，快速更新
```

#### 場景 3: 複雜查詢需求
```
查詢需求: 需要 JOIN 多個表
分析需求: 需要聚合統計、報表
權限控制: 複雜的行級權限
→ 建議: 利用 RDBMS 的 SQL 能力
```

#### 場景 4: 多模態檢索
```
數據類型: 文字 + 圖片 + 表格
存儲需求: 不同類型存不同系統
查詢模式: 多階段檢索和融合
→ 建議: Vector DB + 專門的存儲系統
```

---

## 代碼證據

### 證據 1: Milvus Schema 定義

**文件**: `app/Providers/vector_store_provider/milvus_client.py:121-128`

```python
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=64),
    FieldSchema(name="chunk_index", dtype=DataType.INT32),
    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),  # ← 證據！
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.dimension),
    FieldSchema(name="timestamp", dtype=DataType.INT64)
]
```

**分析**：
- `content` 欄位明確定義為 `VARCHAR(4096)`
- 與 `embedding` 欄位在同一個 schema 中
- 證明文字內容直接存在 Milvus

---

### 證據 2: FAISS 存儲實現

**文件**: `app/Providers/vector_store_provider/client.py:78-82`

```python
vector_store = FAISS.from_texts(
    texts=texts,           # ← 原始文字在這裡
    embedding=embeddings,
    metadatas=metadatas
)
```

**分析**：
- `FAISS.from_texts()` 接收 `texts` 參數
- LangChain 的 FAISS 實現會將文字打包到 Document 對象
- Document 與向量一起存儲在 FAISS 索引中

---

### 證據 3: 檢索時直接返回文字

**文件**: `app/Providers/vector_store_provider/client.py:162-170`

```python
def similarity_search(store_id: str, query: str, k: int):
    vector_store = self._stores[store_id]

    # 執行相似性搜索
    docs = vector_store.similarity_search(query, k=k)

    # 格式化結果
    results = []
    for doc in docs:
        results.append({
            "content": doc.page_content,  # ← 直接從 doc 對象取得文字！
            "metadata": doc.metadata
        })

    return results
```

**分析**：
- `doc.page_content` 直接可用，無需額外查詢
- 證明文字內容已經在 `doc` 對象中
- 沒有任何對 SQLite 或其他數據庫的查詢調用

---

### 證據 4: SQLite 只存元數據

**文件**: `app/Providers/file_metadata_provider/client.py:73-86`

```python
await conn.execute("""
    CREATE TABLE IF NOT EXISTS file_metadata (
        file_id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        file_type TEXT NOT NULL,
        file_size INTEGER,
        upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_id TEXT,
        chunk_count INTEGER,
        embedding_status TEXT,
        milvus_partition TEXT,
        metadata_json TEXT
    )
""")
```

**分析**：
- 表結構中**沒有** `content` 或 `text` 欄位
- 只有文件級別的元數據
- 證明 SQLite 不存儲實際文字內容

---

### 證據 5: 檢索流程不查詢 SQLite

**文件**: `app/api/v1/endpoints/chat.py:172-199`

```python
# Phase 2: Parallel Retrieval
retrieval_tasks = [
    retrieval_service.retrieve_context(
        query=question,
        file_ids=request.file_ids,  # ← 直接使用 file_ids
        top_k=request.top_k
    )
    for question in expanded_questions
]

retrieval_results = await asyncio.gather(*retrieval_tasks)

# Merge and deduplicate context chunks
seen_contents = set()
for results in retrieval_results:
    for result in results:
        content = result.get("content", "")  # ← 內容已經在這裡
        if content and content not in seen_contents:
            context_chunks.append(result)
            seen_contents.add(content)
```

**分析**：
- 整個檢索流程中沒有對 `file_metadata_provider` 的調用
- `content` 直接從 `result` 中獲取
- 證明檢索不依賴 SQLite

---

## 總結

### 核心結論

1. **存儲位置**：原始文字內容存儲在**向量數據庫**（Milvus/FAISS/ChromaDB），不是 RDBMS

2. **架構模式**：採用**嵌入式存儲架構**，向量和文字在同一系統

3. **檢索效率**：**一次查詢**即可獲得語意搜索結果 + 完整文字內容

4. **SQLite 角色**：僅用於文件元數據管理，完全不參與內容檢索

5. **設計優勢**：
   - ✅ 查詢延遲最低（單次查詢）
   - ✅ 架構簡單（易於維護）
   - ✅ 數據一致性（原子性保證）
   - ✅ 開發效率高（代碼簡潔）

### 數據流動總覽

```
文檔上傳
  ↓
[解析 + 分塊] → chunks
  ↓
[生成 embeddings] → vectors
  ↓
[Milvus] 存儲: vectors + chunks + metadata  ✅
[SQLite] 存儲: file_id, filename, chunk_count  ✅
  ↓
═══════════════════════════════════════════════
  ↓
用戶查詢
  ↓
[Milvus] 語意搜索 → 直接返回 vectors + chunks  ✅
[SQLite] ❌ 不參與
  ↓
[構建 Prompt] → context + query
  ↓
[LLM 生成] → answer
```

### 適用場景

DocAI 的嵌入式存儲架構最適合：
- 📊 數據規模：< 1M chunks
- 🔄 更新頻率：低到中等
- ⚡ 性能要求：查詢延遲 < 100ms
- 👥 用戶規模：中小型應用
- 💰 成本考量：簡化運維，降低成本

---

**文檔版本**: v1.0
**最後更新**: 2025-11-03
**作者**: Claude (SuperClaude Framework)
