# Milvus 向量資料庫遷移指南

**日期**: 2025-11-07
**狀態**: ✅ 已完成配置
**影響**: 向量資料現在持久化儲存，服務器重啟後不會丟失

---

## 變更摘要

### 從 FAISS 切換到 Milvus

**之前 (FAISS)**:
```bash
VECTOR_STORE_TYPE=faiss
# 向量儲存在記憶體中
# 服務器重啟 → 所有向量消失
```

**現在 (Milvus)**:
```bash
VECTOR_STORE_TYPE=milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION_NAME=docai_embeddings
```

---

## 配置變更

### 1. `.env` 文件修改

**位置**: `/home/mapleleaf/LCJRepos/gitprjs/DocAI/.env`

**變更內容**:
```diff
# Vector Database
- VECTOR_STORE_TYPE=faiss
- # MILVUS_HOST=localhost
- # MILVUS_PORT=19530
- # MILVUS_COLLECTION_NAME=docai_embeddings
+ VECTOR_STORE_TYPE=milvus
+ MILVUS_HOST=localhost
+ MILVUS_PORT=19530
+ MILVUS_COLLECTION_NAME=docai_embeddings
```

### 2. 代碼修復

**位置**: `app/Providers/vector_store_provider/client.py`

**問題**: 調用了不存在的方法 `search_similar_vectors`
**修復**: 改為正確的 `search` 方法

```diff
- search_results = self._milvus_client.search_similar_vectors(
-     file_id=store_id,
+ search_results = self._milvus_client.search(
+     file_ids=[store_id],
      query_embedding=query_embedding,
      top_k=k
  )
```

---

## Milvus 服務驗證

### 檢查 Milvus 運行狀態

```bash
# 方法 1: Docker 檢查
docker ps | grep milvus

# 預期輸出:
# ae0809cb1d7b   milvusdb/milvus:v2.5.8   ...   Up 2 hours (healthy)
# 0.0.0.0:19530->19530/tcp   milvus-standalone
```

**當前狀態**: ✅ Milvus 運行中
- 容器 ID: ae0809cb1d7b
- 版本: v2.5.8
- 健康狀態: healthy
- 端口: 19530 (已綁定)

### 測試連接

```bash
# 使用 netcat 測試端口
nc -zv localhost 19530

# 或使用 Python
python -c "from pymilvus import connections; connections.connect('default', host='localhost', port='19530'); print('Connected!')"
```

---

## 架構對比

### FAISS (之前)

```
PDF 上傳
    ↓
文本提取 + 分塊
    ↓
向量化 (sentence-transformers)
    ↓
┌─────────────────────────────────────┐
│ 記憶體 (VectorStoreProvider)        │
├─────────────────────────────────────┤
│ self._stores = {                    │
│   "file_xxx": FAISS VectorStore     │
│ }                                   │
└─────────────────────────────────────┘
    ↓ 服務器重啟
    ↓
✗ 所有向量消失
✗ 需要重新上傳所有文件
```

### Milvus (現在)

```
PDF 上傳
    ↓
文本提取 + 分塊
    ↓
向量化 (sentence-transformers)
    ↓
┌─────────────────────────────────────┐
│ Milvus (持久化向量資料庫)            │
├─────────────────────────────────────┤
│ Collection: docai_embeddings        │
│ ├─ Partition: file_xxx              │
│ │  ├─ Vector 1 (384 dim)            │
│ │  ├─ Vector 2 (384 dim)            │
│ │  └─ ...                           │
│ ├─ Partition: file_yyy              │
│ └─ ...                              │
└─────────────────────────────────────┘
    ↓ 服務器重啟
    ↓
✓ 向量資料保留
✓ 無需重新上傳
```

---

## 資料儲存位置

### 之前 (FAISS)

| 資料類型 | 儲存位置 | 持久化 |
|---------|---------|--------|
| 向量 | 記憶體 `VectorStoreProvider._stores` | ❌ |
| 文件元數據 | SQLite `data/docai.db` (file_metadata) | ✅ |
| Chunks 文本 | 無 | ❌ |

**問題**：
- 向量在記憶體中，重啟後消失
- Chunks 文本沒有儲存，無法恢復

### 現在 (Milvus)

| 資料類型 | 儲存位置 | 持久化 |
|---------|---------|--------|
| 向量 | Milvus Docker Volume | ✅ |
| 文件元數據 | SQLite `data/docai.db` (file_metadata) | ✅ |
| Chunks 文本 | Milvus Collection (content 欄位) | ✅ |

**優勢**：
- 所有資料持久化
- 服務器重啟後自動恢復
- 支持分佈式部署（未來）

---

## Milvus 資料結構

### Collection Schema

**Collection 名稱**: `docai_embeddings`

**欄位定義**:
```python
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=64),
    FieldSchema(name="chunk_index", dtype=DataType.INT32),
    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=384),
    FieldSchema(name="timestamp", dtype=DataType.INT64)
]
```

### Partition 結構

**設計**: 每個文件一個 Partition

```
Collection: docai_embeddings
├─ Partition: file_1762481517_c62acbd5_f03fc729  (DeepSeek_R1.pdf)
│  ├─ id=1, chunk_index=0, content="...", embedding=[...]
│  ├─ id=2, chunk_index=1, content="...", embedding=[...]
│  └─ ... (247 chunks)
│
├─ Partition: file_1762335574_da8d0bda_4db4a6e8  (另一個 PDF)
│  └─ ... (105 chunks)
│
└─ ...
```

**優勢**:
- 快速刪除文件（直接刪除 Partition）
- 高效檢索（只搜尋特定文件的 Partition）
- 清晰的資料組織

---

## 索引配置

### 當前設置

**索引類型**: `IVF_FLAT`
- **說明**: Inverted File with Flat (exhaustive search within clusters)
- **優勢**: 平衡速度和精度
- **適用**: 中小規模向量集（< 1M vectors）

**相似度指標**: `L2` (歐幾里得距離)
- **說明**: 計算向量間的 L2 距離
- **替代**: `IP` (內積), `COSINE` (余弦相似度)

**配置參數**:
```python
MILVUS_INDEX_TYPE = "IVF_FLAT"
MILVUS_METRIC_TYPE = "L2"
MILVUS_NLIST = 1024  # 聚類數量
```

### 檢索參數

```python
search_params = {
    "metric_type": "L2",
    "params": {"nprobe": 16}  # 搜尋的聚類數量
}
```

**nprobe 調優**:
- 更高 = 更精確，更慢
- 更低 = 更快，可能遺漏結果
- 推薦: `nprobe = min(16, nlist)`

---

## 使用方式變更

### 上傳文件（無變更）

```python
# 前端上傳 PDF
# 後端處理流程相同:
# 1. 提取文本
# 2. 分塊
# 3. 向量化
# 4. 儲存 → 現在自動儲存到 Milvus
```

### 查詢文件（無變更）

```python
# 用戶查詢
# 檢索流程相同:
# 1. 查詢向量化
# 2. 相似度搜尋 → 現在從 Milvus 檢索
# 3. 返回 top-k chunks
```

**對用戶透明**：用戶體驗完全相同，只是底層儲存變更。

---

## 遷移步驟

### 已完成的步驟 ✅

1. ✅ 修改 `.env` 配置為 `VECTOR_STORE_TYPE=milvus`
2. ✅ 修復 `client.py` 中的方法調用錯誤
3. ✅ 驗證 Milvus 服務運行中

### 下一步操作

#### 1. 重啟服務器以應用變更

```bash
# 停止當前服務器
./stop_system.sh

# 啟動服務器（會自動連接 Milvus）
./start_system.sh
```

#### 2. 重新上傳測試文件

**重要**：FAISS 中的向量不會自動遷移到 Milvus

```bash
# 舊的 FAISS 向量（記憶體中）已經消失
# 需要重新上傳 PDF 文件到 Milvus
```

**步驟**:
1. 打開 Web UI: http://localhost:8000
2. 上傳測試文件（如 DeepSeek_R1.pdf）
3. 驗證向量已儲存到 Milvus

#### 3. 驗證 Milvus 資料

```bash
# 使用 Python 腳本檢查
python -c "
from pymilvus import connections, Collection
connections.connect('default', host='localhost', port='19530')
collection = Collection('docai_embeddings')
print(f'Total entities: {collection.num_entities}')
print(f'Partitions: {[p.name for p in collection.partitions]}')
"
```

**預期輸出**:
```
Total entities: 247  # DeepSeek_R1.pdf 的 chunks
Partitions: ['_default', 'file_1762481517_c62acbd5_f03fc729']
```

---

## 故障排除

### 問題 1: Milvus 連接失敗

**症狀**:
```
ERROR: Failed to connect to Milvus: ...
```

**解決方案**:
```bash
# 檢查 Milvus 是否運行
docker ps | grep milvus

# 如果未運行，啟動 Milvus
docker start milvus-standalone

# 或使用 docker-compose
docker-compose up -d milvus-standalone
```

### 問題 2: Collection 不存在

**症狀**:
```
ERROR: Collection 'docai_embeddings' does not exist
```

**解決方案**:
系統會自動創建 Collection，但可以手動創建：

```python
from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType
connections.connect('default', host='localhost', port='19530')

# Collection 會在首次上傳文件時自動創建
# 或檢查是否已存在
from pymilvus import utility
if utility.has_collection('docai_embeddings'):
    print("Collection exists")
else:
    print("Collection will be created on first upload")
```

### 問題 3: 向量搜尋無結果

**症狀**:
```
Retrieved 0 context chunks
```

**診斷**:
```python
# 檢查 Partition 是否有資料
from pymilvus import connections, Collection
connections.connect('default', host='localhost', port='19530')
collection = Collection('docai_embeddings')

for partition in collection.partitions:
    print(f"{partition.name}: {partition.num_entities} entities")
```

**解決方案**:
- 確認文件已上傳
- 檢查 Partition 名稱是否匹配
- 驗證 embedding dimension (應為 384)

### 問題 4: 重複上傳文件

**症狀**:
同一個文件上傳兩次，創建兩個 Partition

**解決方案**:
```python
# 系統應該檢查文件 hash 避免重複
# 如果發生重複，手動刪除舊 Partition:

from pymilvus import connections, Collection
connections.connect('default', host='localhost', port='19530')
collection = Collection('docai_embeddings')

# 刪除重複的 Partition
collection.drop_partition('file_duplicate_xxx')
```

---

## 性能比較

### FAISS vs Milvus

| 指標 | FAISS (記憶體) | Milvus (持久化) |
|------|---------------|----------------|
| **檢索速度** | 極快 (~1ms) | 快 (~5-10ms) |
| **插入速度** | 極快 | 中等 (需寫磁碟) |
| **記憶體使用** | 高 (所有向量) | 低 (索引 + 快取) |
| **持久化** | ❌ | ✅ |
| **擴展性** | 單機 | 分佈式 |
| **資料恢復** | ❌ | ✅ |
| **適用規模** | < 100K vectors | > 1M vectors |

### 當前場景評估

**文件數量**: ~10 個 PDF
**總向量數**: ~1000 vectors
**記憶體使用**:
- FAISS: ~1.5 MB (1000 × 384 × 4 bytes)
- Milvus: ~3 MB (索引 + 元數據)

**結論**: 當前規模下，Milvus 的主要優勢是**持久化**，性能差異可忽略。

---

## 未來優化建議

### 1. 索引優化（大規模時）

當向量數 > 100K 時，考慮升級索引：

```python
# 當前: IVF_FLAT
MILVUS_INDEX_TYPE = "IVF_FLAT"

# 大規模推薦: HNSW (更快，但記憶體更高)
MILVUS_INDEX_TYPE = "HNSW"
MILVUS_HNSW_M = 16
MILVUS_HNSW_EF_CONSTRUCTION = 200
```

### 2. 相似度指標調整

```python
# 當前: L2 距離
MILVUS_METRIC_TYPE = "L2"

# 如果使用 normalized embeddings，改用 IP 或 COSINE
MILVUS_METRIC_TYPE = "IP"  # Inner Product
# 或
MILVUS_METRIC_TYPE = "COSINE"  # Cosine Similarity
```

### 3. 分佈式部署（未來）

當需要高可用性時：

```bash
# 當前: Standalone Milvus
docker run -d milvus-standalone

# 未來: Milvus Cluster
docker-compose -f docker-compose-cluster.yml up -d
# 包含: Query Nodes, Data Nodes, Index Nodes, Coordinator
```

### 4. 監控與日誌

```python
# 添加 Milvus 監控
from pymilvus import connections
import logging

# 啟用詳細日誌
logging.getLogger("pymilvus").setLevel(logging.DEBUG)

# 監控指標
collection.get_stats()
# → {"row_count": 247, "index_status": "built", ...}
```

---

## 總結

### 完成的變更 ✅

1. ✅ `.env` 配置切換到 Milvus
2. ✅ 修復代碼中的方法調用錯誤
3. ✅ 驗證 Milvus 服務運行中
4. ✅ 文檔完整記錄遷移過程

### 主要優勢

| 優勢 | 說明 |
|------|------|
| **持久化** | 服務器重啟後資料不丟失 |
| **可擴展** | 支持未來分佈式部署 |
| **企業級** | Milvus 是生產級向量資料庫 |
| **完整性** | Chunks 文本也儲存在 Milvus |

### 下一步行動

1. **重啟服務器**: `./stop_system.sh && ./start_system.sh`
2. **重新上傳文件**: 通過 Web UI 上傳測試 PDF
3. **驗證功能**: 測試查詢和檢索功能
4. **監控日誌**: 檢查是否有連接或儲存錯誤

---

**文檔版本**: 1.0.0
**最後更新**: 2025-11-07
**維護者**: Claude Code Agent
**狀態**: ✅ 配置完成，待重啟驗證
