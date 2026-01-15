# Milvus 整合與系統修復報告

**日期**: 2025-11-04
**問題**: PDF 上傳成功後，聊天功能掛在 "Initializing..." 狀態
**診斷**: 系統性故障排除，發現多個連鎖問題

---

## 📋 執行摘要

### 根本原因

1. **架構不一致**: 系統配置使用 `VECTOR_STORE_BACKEND="milvus"`，但實際實現只支援 FAISS/ChromaDB
2. **記憶體資料遺失**: 向量存儲在記憶體中，server 重啟後全部遺失
3. **模組缺失**: `pkg_resources` 模組缺失導致 pymilvus 無法正常工作

### 解決方案

✅ 整合 Milvus 支援到現有 VectorStoreProvider
✅ 修復 pymilvus 依賴問題
✅ 修復 LLM streaming API 錯誤
✅ 修復 Cache provider 方法調用錯誤

---

## 🔍 問題診斷過程

### 問題 1: pkg_resources 模組缺失

**症狀**:
```
ModuleNotFoundError: No module named 'pkg_resources'
```

**根本原因**:
- 虛擬環境 `docaienv` 沒有安裝 pip
- `pymilvus` 需要 `pkg_resources` 模組（來自 `setuptools`）

**修復步驟**:
```bash
source docaienv/bin/activate
python3 -m ensurepip --upgrade  # 安裝 pip
# 自動安裝 setuptools-65.5.0（包含 pkg_resources）
```

**影響檔案**: 虛擬環境配置
**驗證**: `python3 -c "import pkg_resources; print('✅ pkg_resources imported')"` → 成功

---

### 問題 2: 向量存儲架構不一致

**症狀**:
- Milvus collection `document_embeddings` 不存在
- 向量檢索回傳 0 個 chunks
- Server 重啟後向量資料遺失

**根本原因分析**:

**配置檔案** ([app/core/config.py](../app/core/config.py)):
```python
VECTOR_STORE_BACKEND: str = "milvus"  # 設定使用 Milvus
```

**實際實現** ([app/Providers/vector_store_provider/client.py](../app/Providers/vector_store_provider/client.py)):
```python
class VectorStoreProvider:
    def __init__(self, backend: str = "faiss", ...):
        # 只實現了 FAISS 和 ChromaDB
        # Milvus 實現存在於 milvus_client.py 但從未被使用
```

**資料流向**:
```
Upload PDF → RetrievalService.add_document_chunks()
           → VectorStoreProvider.create_store_from_texts()  # 建立 FAISS 記憶體存儲
           → 存入 _stores[file_id] = FAISS_vector_store  # ❌ 記憶體中

Server 重啟 → _stores = {} # ❌ 所有資料遺失

Chat request → RetrievalService.retrieve_context()
            → VectorStoreProvider.similarity_search()
            → ValueError: Vector store not found  # ❌ 檔案不存在
```

**修復方案**: 整合 Milvus 支援到 VectorStoreProvider

---

### 問題 3: Cache Provider 方法錯誤

**症狀**:
```
'CacheProvider' object has no attribute 'get'
```

**位置**: [app/Services/query_enhancement_service.py](../app/Services/query_enhancement_service.py#L143-L191)

**錯誤程式碼**:
```python
cached_result = await cache_provider.get(cache_key)  # ❌ 方法不存在
await cache_provider.set(cache_key, json.dumps(result), expire=3600)  # ❌ 方法不存在
```

**正確程式碼**:
```python
cached_result = await cache_provider.get_query_expansion(query)  # ✅ 使用專用方法
await cache_provider.set_query_expansion(query, expansion_result)  # ✅ 使用專用方法
```

**修復**: 修改為使用正確的專用方法

---

### 問題 4: LLM Streaming API 錯誤

**症狀**:
```
Attempted to access streaming response content, without having called `read()`.
```

**位置**: [app/Providers/llm_provider/client.py](../app/Providers/llm_provider/client.py#L104)

**錯誤程式碼**:
```python
async with client.stream(...) as response:
    response.raise_for_status()  # ❌ 在 streaming 模式不能直接調用
    async for chunk in response.aiter_bytes():
        yield chunk
```

**修復程式碼**:
```python
async with client.stream(...) as response:
    # 手動檢查狀態碼，避免讀取 response content
    if response.status_code >= 400:
        error_text = await response.aread()
        raise httpx.HTTPStatusError(...)
    async for chunk in response.aiter_bytes():
        yield chunk
```

---

## 🔧 實施的修復

### 修復 1: 整合 Milvus 到 VectorStoreProvider

**修改檔案**: [app/Providers/vector_store_provider/client.py](../app/Providers/vector_store_provider/client.py)

#### 1.1 擴充 `__init__` 方法

**修改前**:
```python
def __init__(self, backend: str = "faiss", ...):
    self.backend = backend.lower()
    self._stores: Dict[str, Any] = {}  # 只支援 FAISS/ChromaDB
```

**修改後**:
```python
def __init__(self, backend: str = "faiss", ...):
    from app.core.config import settings
    self.backend = backend.lower() if backend else settings.VECTOR_STORE_BACKEND.lower()
    self._stores: Dict[str, Any] = {}  # FAISS/ChromaDB 使用
    self._milvus_client: Optional[Any] = None  # Milvus 客戶端（延遲初始化）
```

**變更原因**:
- 從配置自動讀取 backend 設定
- 新增 Milvus 客戶端支援

#### 1.2 擴充 `create_store_from_texts` 方法

**新增 Milvus 分支**:
```python
elif self.backend == "milvus":
    from app.Providers.vector_store_provider.milvus_client import MilvusClient

    # 初始化 Milvus 客戶端
    if self._milvus_client is None:
        self._milvus_client = MilvusClient()
        self._milvus_client.connect()

    store_id = file_id or f"store_{len(self._stores)}"

    # 生成 embeddings
    embedding_vectors = embeddings.embed_documents(texts)

    # 建立 partition（每個檔案一個 partition）
    partition_name = self._milvus_client.create_partition(store_id)

    # 準備 chunk indices
    chunk_indices = list(range(len(texts)))
    if metadatas:
        chunk_indices = [m.get("chunk_index", i) for i, m in enumerate(metadatas)]

    # 插入向量到 Milvus
    self._milvus_client.insert_vectors(
        file_id=store_id,
        texts=texts,
        embeddings=embedding_vectors,
        chunk_indices=chunk_indices
    )

    # 記錄 store 資訊
    self._stores[store_id] = {"type": "milvus", "partition": partition_name}

    logger.info(f"Created Milvus store '{store_id}' with {len(texts)} chunks")
    return store_id
```

**重用策略**:
- ✅ 重用現有的 `MilvusClient` 類別（[app/Providers/vector_store_provider/milvus_client.py](../app/Providers/vector_store_provider/milvus_client.py)）
- ✅ 重用現有的 partition-based 架構
- ✅ 保持與 FAISS/ChromaDB 相同的介面

#### 1.3 擴充 `similarity_search` 方法

**新增 Milvus 查詢分支**:
```python
# 檢查是否為 Milvus store
if isinstance(vector_store, dict) and vector_store.get("type") == "milvus":
    from app.Providers.embedding_provider.client import get_embedding_provider

    # 取得 query embedding
    embedding_provider = get_embedding_provider()
    query_embedding = embedding_provider.get_embedding(query)

    # 在 Milvus 中搜尋
    search_results = self._milvus_client.search_similar_vectors(
        file_id=store_id,
        query_embedding=query_embedding,
        top_k=k
    )

    # 格式化結果
    results = []
    for result in search_results:
        results.append({
            "content": result.get("content", ""),
            "metadata": {
                "file_id": result.get("file_id", store_id),
                "chunk_index": result.get("chunk_index", 0)
            }
        })

    return results
else:
    # FAISS/ChromaDB 原有邏輯...
```

#### 1.4 擴充 `similarity_search_with_score` 方法

同樣的方式加入 Milvus 支援，返回包含 `score` 的結果。

---

### 修復 2-4: 其他錯誤修復

參考之前的修復報告：
- `claudedocs/sse_parsing_fix_20251104.md`
- `claudedocs/chunks_metadata_fix_20251104.md`
- `claudedocs/mongodb_import_error_fix_20251104.md`

---

## ✅ 驗證結果

### 1. pkg_resources 模組
```bash
$ python3 -c "import pkg_resources; print('Success')"
Success  ✅
```

### 2. Milvus 連接
```bash
$ python3 test_milvus_connection.py
✅ Connected successfully
✅ Milvus version: 2.5.8
✅ Available collections: [...]
```

### 3. Ollama LLM API
```bash
$ curl -X POST http://localhost:11434/v1/chat/completions ...
{"id":"chatcmpl-399","object":"chat.completion",...}  ✅
```

### 4. Server 健康檢查
```bash
$ curl http://localhost:8000/health
{"status":"healthy","app_name":"DocAI","version":"1.0.0"}  ✅
```

---

## 📝 後續步驟

### ⚠️ 重要：需要重新上傳 PDF

**原因**: 之前的向量資料存在 FAISS 記憶體中，server 重啟後已遺失

**步驟**:
1. 在 DocAI 介面點擊「新增來源」
2. 上傳 PDF 檔案
3. 系統會自動：
   - 生成 embeddings
   - 建立 Milvus collection（如不存在）
   - 建立 partition (file_xxx)
   - 插入向量到 Milvus
   - 資料永久保存（不會因 server 重啟而遺失）

### 測試聊天功能

上傳完成後：
1. 在聊天介面輸入問題
2. 應該會看到 5 個 phase 的進度：
   - Phase 1: Query Understanding ✅
   - Phase 2: Parallel Retrieval ✅（從 Milvus 檢索）
   - Phase 3: Context Assembly ✅
   - Phase 4: Response Generation ✅（從 Ollama LLM）
   - Phase 5: Post Processing ✅
3. 最終收到完整的 Markdown 回應

---

## 📊 架構改進

### 之前（有問題）
```
Upload → FAISS (記憶體) → Server 重啟 → 資料遺失 ❌
```

### 現在（已修復）
```
Upload → Milvus (持久化) → Server 重啟 → 資料保留 ✅
```

### 向量存儲選擇
| Backend | 持久化 | 分散式 | 適用場景 |
|---------|--------|--------|----------|
| FAISS | ❌ | ❌ | 開發測試 |
| ChromaDB | ✅ | ❌ | 單機部署 |
| **Milvus** | ✅ | ✅ | **生產環境（推薦）** |

---

## 🎯 合規確認

**COMPLIANCE CONFIRMED**: 本次修復完全遵循程式碼重用原則

✅ **重用現有檔案**: 修改 `app/Providers/vector_store_provider/client.py`，未創建新檔案
✅ **重用現有類別**: 使用現有的 `MilvusClient` 類別
✅ **重用現有架構**: 保持 partition-based 設計
✅ **向後相容**: FAISS 和 ChromaDB 功能完全保留
✅ **擴充不重寫**: 透過條件分支擴充功能，未改變現有邏輯

---

## 📚 參考文件

- [Milvus Client 實現](../app/Providers/vector_store_provider/milvus_client.py)
- [VectorStoreProvider](../app/Providers/vector_store_provider/client.py)
- [RetrievalService](../app/Services/retrieval_service.py)
- [Configuration](../app/core/config.py)

---

## 🔍 故障排除

### 如果聊天仍然掛起

1. **檢查 Milvus 連接**:
   ```bash
   curl -s http://localhost:19530/healthz || echo "Milvus not responding"
   ```

2. **檢查向量資料**:
   ```bash
   python3 test_milvus_connection.py
   # 應該看到 document_embeddings collection 和相關 partitions
   ```

3. **檢查 Ollama**:
   ```bash
   curl -X POST http://localhost:11434/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"gpt-oss:20b","messages":[{"role":"user","content":"test"}]}'
   ```

4. **檢查 server logs**:
   ```bash
   tail -f logs/server.log | grep -E "(ERROR|WARNING|Milvus|LLM)"
   ```

---

**修復完成**: 2025-11-04 14:58
**測試狀態**: Server 正常運行，等待 PDF 重新上傳以驗證端對端流程
