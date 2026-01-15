<!-- claudedocs/chunks_metadata_Table_資料遺失修復報告.md -->
<!-- claudedocs/chunks_metadata_fix_20251104.md -->
# chunks_metadata Table 資料遺失修復報告

**日期**: 2025-11-04
**問題**: `chunks_metadata` table 沒有任何資料
**修復類型**: Missing Feature Implementation - Database Write Operation
**嚴重程度**: 🟡 Important - 影響資料完整性和查詢功能

---

## 🎯 問題描述

### 用戶報告
用戶發現 `chunks_metadata` table 中沒有任何資料，儘管：
- 檔案上傳成功（9 筆檔案在 `file_metadata`）
- 每個檔案都有 `chunk_count`（3-460 chunks）
- Embeddings 已儲存到 Milvus vector store

### 問題影響
1. **資料完整性**: 無法追蹤每個 chunk 的詳細資訊
2. **查詢功能受限**: 無法透過 SQL 查詢特定 chunk 內容
3. **Debug 困難**: 無法驗證 chunking 結果和 Milvus 的對應關係

---

## 🔍 診斷過程

### Step 1: 確認問題範圍

**操作**:
```bash
# 檢查 table 存在性
sqlite3 data/docai.db ".tables"
# 結果: chunks_metadata  file_metadata  users

# 檢查 table schema
sqlite3 data/docai.db ".schema chunks_metadata"
# 結果: ✅ Schema 正確

# 檢查資料筆數
sqlite3 data/docai.db "SELECT COUNT(*) FROM chunks_metadata;"
# 結果: 0 ← 問題確認！

# 檢查 file_metadata
sqlite3 data/docai.db "SELECT COUNT(*) FROM file_metadata;"
# 結果: 9 筆檔案存在
```

**發現**:
- ✅ Table 存在且 schema 正確
- ❌ Table 完全沒有資料（0 筆）
- ✅ 相關的 `file_metadata` 有資料

---

### Step 2: 追蹤資料寫入流程

**檔案上傳流程分析** ([app/api/v1/endpoints/upload.py](app/api/v1/endpoints/upload.py)):

```
1. process_file()          → 產生 chunks ✅
2. add_file()             → 寫入 file_metadata ✅
3. add_document_chunks()  → 寫入 Milvus vector store ✅
4. update_embedding_status() → 更新狀態 ✅
5. add_chunks()           → 寫入 chunks_metadata ❌ 缺少！
```

**關鍵發現**:
- `FileMetadataProvider.add_chunks()` 方法存在（[client.py:360-392](app/Providers/file_metadata_provider/client.py#L360-L392)）
- 但 **upload.py 中沒有呼叫此方法**

---

### Step 3: 程式碼分析

#### FileMetadataProvider.add_chunks() 方法
**位置**: `app/Providers/file_metadata_provider/client.py:360-392`

**功能**: 批次寫入 chunks metadata 到 SQLite

**需要的參數格式**:
```python
chunks = [
    {
        "chunk_id": "file_xxx_chunk_0",
        "chunk_index": 0,
        "chunk_text": "chunk content...",
        "milvus_id": 12345  # Optional
    },
    ...
]
await provider.add_chunks(file_id, chunks)
```

#### 現有的 chunks 格式
**來源**: `InputDataHandleService.process_file()`

**實際格式**:
```python
chunks = [
    {
        "content": "chunk text...",
        "metadata": {
            "chunk_index": 0,
            "file_id": "file_xxx",
            "filename": "doc.pdf",
            ...
        }
    },
    ...
]
```

**格式差異**:
- 實際: `content` + `metadata` (nested dict)
- 需要: flat dict with `chunk_text` + `chunk_index` + etc.

---

## ✅ 修復方案

### 修改的檔案
**COMPLIANCE CONFIRMED**: 修改現有檔案，不創建新檔案

- ✅ [app/api/v1/endpoints/upload.py](app/api/v1/endpoints/upload.py) (Lines 156-170，新增 14 行)

### 實現細節

#### 修改前（Lines 147-157）
```python
# Step 4: Add chunks to vector store (with embeddings)
store_id = await retrieval_service.add_document_chunks(
    file_id=file_id,
    chunks=chunk_texts,
    metadata=chunk_metadata
)

logger.info(f"Embeddings generated and stored: {store_id}")

# Step 5: Update embedding status
await file_metadata_provider.update_embedding_status(file_id, "completed")
```

#### 修改後（Lines 147-173）
```python
# Step 4: Add chunks to vector store (with embeddings)
store_id = await retrieval_service.add_document_chunks(
    file_id=file_id,
    chunks=chunk_texts,
    metadata=chunk_metadata
)

logger.info(f"Embeddings generated and stored: {store_id}")

# Step 4.5: Store chunk metadata in SQLite chunks_metadata table
# Prepare chunk records for database storage
chunk_records = []
for idx, chunk in enumerate(chunks):
    chunk_record = {
        "chunk_id": f"{file_id}_chunk_{idx}",
        "chunk_index": chunk["metadata"].get("chunk_index", idx),
        "chunk_text": chunk["content"],
        "milvus_id": None  # Milvus doesn't return individual IDs in current implementation
    }
    chunk_records.append(chunk_record)

# Store chunks metadata
await file_metadata_provider.add_chunks(file_id, chunk_records)
logger.info(f"Stored {len(chunk_records)} chunk metadata records for file {file_id}")

# Step 5: Update embedding status
await file_metadata_provider.update_embedding_status(file_id, "completed")
```

### 關鍵改進

1. **格式轉換**:
   - 從 `chunks` (nested dict) 轉換為 `chunk_records` (flat dict)
   - 提取 `content` → `chunk_text`
   - 提取 `metadata.chunk_index` → `chunk_index`

2. **Chunk ID 生成**:
   - 格式: `{file_id}_chunk_{index}`
   - 例如: `file_1762230742_e9d32b6d_chunk_0`
   - 確保唯一性

3. **Milvus ID 處理**:
   - 目前設為 `None`（因為 `add_document_chunks` 不返回個別 IDs）
   - 未來可以修改 `retrieval_service` 來返回 IDs

4. **錯誤處理**:
   - 維持現有的 try-except 結構
   - 如果寫入失敗會自動 rollback

---

## 🧪 驗證步驟

### 1. 語法驗證
```bash
python3 -m py_compile app/api/v1/endpoints/upload.py
# ✅ 通過（無輸出表示成功）
```

### 2. 功能測試

#### 測試場景 1: 上傳新檔案
```bash
# 上傳一個測試 PDF
curl -X POST "http://localhost:8000/api/v1/upload" \
  -H "X-User-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -F "file=@test.pdf"

# 預期結果:
{
  "file_id": "file_xxx...",
  "filename": "test.pdf",
  "chunk_count": 100,
  "embedding_status": "completed",
  "message": "File uploaded and indexed successfully..."
}
```

#### 測試場景 2: 驗證 chunks_metadata 資料
```bash
# 檢查總筆數
sqlite3 data/docai.db "SELECT COUNT(*) FROM chunks_metadata;"
# 預期: 100 (或檔案的 chunk_count)

# 檢查資料內容
sqlite3 data/docai.db "SELECT chunk_id, chunk_index, LENGTH(chunk_text) FROM chunks_metadata WHERE file_id='file_xxx' LIMIT 5;"
# 預期: 顯示 5 筆 chunk 資料

# 檢查特定檔案的 chunks
sqlite3 data/docai.db "SELECT COUNT(*) FROM chunks_metadata WHERE file_id='file_xxx';"
# 預期: 與 file_metadata.chunk_count 一致
```

#### 測試場景 3: 驗證資料一致性
```sql
-- 檢查每個檔案的 chunk 數量是否一致
SELECT
    fm.file_id,
    fm.filename,
    fm.chunk_count as expected_chunks,
    COUNT(cm.chunk_id) as actual_chunks,
    (fm.chunk_count = COUNT(cm.chunk_id)) as is_consistent
FROM file_metadata fm
LEFT JOIN chunks_metadata cm ON fm.file_id = cm.file_id
GROUP BY fm.file_id;

-- 預期: is_consistent = 1 for all files
```

---

## 📊 修改影響分析

### 正面影響
1. ✅ **資料完整性恢復**: chunks_metadata table 將開始接收資料
2. ✅ **功能增強**: 可以透過 SQL 查詢 chunk 詳細資訊
3. ✅ **Debug 改善**: 可以驗證 chunking 結果
4. ✅ **未來擴展**: 為 chunk-level 分析和最佳化奠定基礎

### 保持的特性
1. ✅ **向後兼容**: 不影響現有的檔案上傳和檢索流程
2. ✅ **錯誤處理**: 維持原有的 exception handling
3. ✅ **效能**: 批次寫入，無額外 API 呼叫

### 潛在考量
1. ⚠️ **儲存空間**: 每個 chunk 的完整文本會被儲存兩次：
   - Milvus (for vector search)
   - SQLite (for metadata query)
2. ⚠️ **寫入效能**: 多一次資料庫寫入操作
   - 緩解: 使用批次寫入（已實現）
3. ⚠️ **Milvus ID 缺失**: 目前無法追蹤 Milvus 的具體 ID
   - 未來改進: 修改 `retrieval_service.add_document_chunks()` 返回 IDs

---

## 🔄 建議後續改進

### 短期 (立即可做)
1. **測試現有檔案**: 為已上傳的 9 個檔案補齊 chunks_metadata
   ```python
   # 創建 migration script
   # 從 Milvus 讀取 chunks → 寫入 chunks_metadata
   ```

2. **監控日誌**: 確認新上傳的檔案都正確寫入
   ```bash
   grep "Stored.*chunk metadata records" logs/server.log
   ```

### 中期 (1-2 weeks)
1. **返回 Milvus IDs**: 修改 `RetrievalService.add_document_chunks()`
   ```python
   # 返回 List[int] 而不是 str
   milvus_ids = await retrieval_service.add_document_chunks(...)
   # 然後在 chunk_records 中填入實際的 milvus_id
   ```

2. **添加索引**: 優化查詢效能
   ```sql
   CREATE INDEX idx_chunk_text_fts
   ON chunks_metadata(chunk_text);
   ```

### 長期 (future releases)
1. **Full-text Search**: 在 SQLite 中啟用 FTS5
2. **Chunk Analytics**: 統計 chunk size distribution, 常見 chunks 等
3. **Deduplication**: 檢測和移除重複的 chunks

---

## 📋 總結

### 問題根本原因
上傳流程中缺少呼叫 `FileMetadataProvider.add_chunks()`，導致 chunks_metadata table 沒有資料。

### 修復方式
在 [app/api/v1/endpoints/upload.py](app/api/v1/endpoints/upload.py#L156-L170) 的 `process_and_embed_file` 函數中：
- 新增 Step 4.5: 格式轉換 + 呼叫 `add_chunks()`
- 不影響現有流程，向後兼容

### 驗證結果
- ✅ Python 語法驗證通過
- ⏳ 功能測試待執行（需要上傳新檔案）

### COMPLIANCE CONFIRMATION
✅ **遵守規則確認**:
- ✅ 修改現有檔案 (`upload.py`)，沒有創建新檔案
- ✅ 擴展現有服務 (`FileMetadataProvider.add_chunks`)
- ✅ 引用具體檔案路徑
- ✅ 提供驗證步驟和測試策略

---

## 🔗 相關檔案

### 修改的檔案
- `app/api/v1/endpoints/upload.py` (Lines 156-170, +14 lines)

### 相關程式碼
- `app/Providers/file_metadata_provider/client.py` (Lines 360-392, `add_chunks` method)
- `app/Services/input_data_handle_service.py` (Lines 443-478, `enrich_chunk_metadata`)
- `app/Services/chunking_strategies.py` (Chunk format definition)

### 相關文件
- `claudedocs/sse_parsing_fix_20251104.md` (今天稍早的 SSE 修復)
- `claudedocs/mongodb_import_error_fix_20251104.md` (MongoDB 修復)

---

**修復人員**: Claude (SuperClaude Framework + /sc:troubleshoot)
**審核狀態**: ✅ Syntax Validated | ⏳ Functional Testing Required
**版本**: v1.0 → v1.1 (chunks_metadata Population Enabled)
