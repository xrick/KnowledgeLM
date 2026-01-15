# Skill-Based Architecture 優化策略
**Date**: 2025-11-25
**Author**: Claude (SuperClaude Framework)
**Purpose**: 記錄100文件Skill的高效搜尋優化策略

---

## 挑戰分析

當一個Skill包含100個文件的embeddings時，主要挑戰：
- **記憶體使用**: 100個獨立FAISS索引 = ~400MB記憶體
- **搜尋延遲**: 串行搜尋100個索引需要2-3秒
- **I/O瓶頸**: 從磁碟載入100個索引檔案
- **結果排序**: 需合併和排序10,000個候選結果

---

## 優化策略層級

### 🚀 Level 1: 並行搜尋 (立即可實現 - Demo用)
**實現難度**: ⭐⭐ (簡單)
**性能提升**: 3-5倍
**適合場景**: Demo展示，快速驗證

```python
async def parallel_skill_search(skill_id: str, query: str, top_k: int = 10):
    """並行搜尋所有文件索引"""
    tasks = []
    for file_id in skill_files:
        task = asyncio.create_task(
            vector_store.similarity_search(file_id, query, top_k)
        )
        tasks.append(task)

    # 並行執行所有搜尋
    all_results = await asyncio.gather(*tasks)

    # 合併並排序結果
    merged = [item for sublist in all_results for item in sublist]
    merged.sort(key=lambda x: x['score'])
    return merged[:top_k]
```

**優點**:
- 實現簡單，改動最小
- 充分利用多核CPU
- 不需要額外儲存空間

**缺點**:
- 記憶體使用仍然較高
- I/O密集時效果有限

---

### 🎯 Level 2: 虛擬合併索引 (建議方案)
**實現難度**: ⭐⭐⭐ (中等)
**性能提升**: 10-100倍
**適合場景**: 生產環境，最佳平衡

```python
def create_skill_master_index(skill_id: str):
    """創建Skill的主索引"""
    # 1. 載入所有文件索引
    indices = []
    id_maps = []

    for file_id in get_skill_files(skill_id):
        index = faiss.read_index(f"indices/{file_id}.index")
        indices.append(index)
        # 保存file_id映射
        id_maps.extend([file_id] * index.ntotal)

    # 2. 合併為單一索引
    master_index = faiss.IndexFlatL2(dimension)
    for idx in indices:
        vectors = idx.reconstruct_n(0, idx.ntotal)
        master_index.add(vectors)

    # 3. 保存主索引和映射
    faiss.write_index(master_index, f"skills/{skill_id}/master.index")
    save_json(f"skills/{skill_id}/id_map.json", id_maps)

    return master_index
```

```python
def search_skill_master_index(skill_id: str, query: str, top_k: int = 10):
    """使用主索引搜尋"""
    # 1. 載入主索引（已緩存）
    master_index = get_cached_index(skill_id)
    id_map = load_json(f"skills/{skill_id}/id_map.json")

    # 2. 單次搜尋
    query_vector = embed(query)
    scores, indices = master_index.search(query_vector, top_k)

    # 3. 映射回原始文件
    results = []
    for score, idx in zip(scores[0], indices[0]):
        file_id = id_map[idx]
        chunk_metadata = get_chunk_metadata(file_id, idx)
        results.append({
            'file_id': file_id,
            'chunk': chunk_metadata,
            'score': float(score)
        })

    return results
```

**優點**:
- **搜尋速度快**: 單次向量搜尋 < 10ms
- **記憶體高效**: 只需載入一個索引
- **易於實現**: 使用FAISS原生功能

**缺點**:
- 需要預處理建立主索引
- 更新文件時需重建索引

---

### 🔥 Level 3: 熱插拔記憶體管理
**實現難度**: ⭐⭐⭐⭐ (較難)
**性能提升**: 優化記憶體使用50-70%
**適合場景**: 多Skill切換場景

```python
from functools import lru_cache
import psutil

class SkillIndexManager:
    def __init__(self, max_memory_gb: float = 2.0):
        self.max_memory = max_memory_gb * 1024 * 1024 * 1024
        self.loaded_indices = {}
        self.access_times = {}

    @lru_cache(maxsize=5)
    def get_skill_index(self, skill_id: str):
        """LRU緩存管理Skill索引"""
        # 檢查記憶體使用
        if self._memory_pressure():
            self._evict_oldest()

        # 載入或返回緩存
        if skill_id not in self.loaded_indices:
            index = faiss.read_index(f"skills/{skill_id}/master.index")
            self.loaded_indices[skill_id] = index

        self.access_times[skill_id] = time.time()
        return self.loaded_indices[skill_id]

    def _memory_pressure(self) -> bool:
        """檢查記憶體壓力"""
        return psutil.virtual_memory().percent > 75

    def _evict_oldest(self):
        """淘汰最久未使用的索引"""
        if not self.loaded_indices:
            return

        oldest = min(self.access_times, key=self.access_times.get)
        del self.loaded_indices[oldest]
        del self.access_times[oldest]
        self.get_skill_index.cache_clear()
```

**優點**:
- 自動記憶體管理
- 支援多Skill並發
- 熱門Skill常駐記憶體

---

### 💡 Level 4: Skill Cover生成
**實現難度**: ⭐⭐⭐⭐⭐ (困難)
**性能提升**: 首次查詢加速90%
**適合場景**: 大型知識庫

```python
def generate_skill_cover(skill_id: str, coverage: float = 0.95):
    """生成Skill的代表性摘要"""
    master_index = load_skill_index(skill_id)

    # 1. K-means聚類找代表性向量
    n_clusters = int(master_index.ntotal * 0.1)  # 10%採樣
    kmeans = faiss.Kmeans(d=dimension, k=n_clusters)
    kmeans.train(master_index.reconstruct_n(0, master_index.ntotal))

    # 2. 為每個聚類生成摘要
    cluster_summaries = []
    for centroid in kmeans.centroids:
        # 找最近的實際chunks
        _, nearest = master_index.search(centroid.reshape(1, -1), k=3)
        chunks = [get_chunk_text(idx) for idx in nearest[0]]

        # 生成摘要
        summary = generate_summary(chunks)
        cluster_summaries.append({
            'centroid': centroid.tolist(),
            'summary': summary
        })

    # 3. 保存Skill Cover
    save_json(f"skills/{skill_id}/cover.json", {
        'clusters': cluster_summaries,
        'coverage': coverage,
        'total_chunks': master_index.ntotal
    })

    return cluster_summaries
```

```python
def skill_cover_search(skill_id: str, query: str):
    """兩階段搜尋：先Cover後Detail"""
    cover = load_json(f"skills/{skill_id}/cover.json")

    # 階段1: Cover搜尋（快速）
    query_vec = embed(query)
    relevant_clusters = []

    for cluster in cover['clusters']:
        similarity = cosine_similarity(query_vec, cluster['centroid'])
        if similarity > 0.7:
            relevant_clusters.append(cluster)

    # 階段2: 僅在相關cluster中詳細搜尋
    if relevant_clusters:
        # 縮小搜尋範圍
        return focused_search(skill_id, query, relevant_clusters)
    else:
        # 全域搜尋
        return full_search(skill_id, query)
```

**優點**:
- 快速預覽Skill內容
- 智能搜尋路由
- 減少不必要的計算

---

## 實施優先級建議

### 🎯 Demo階段 (下周一、二)
1. **立即實現**: Level 1 並行搜尋
   - 改動最小，風險最低
   - 3-5倍性能提升足夠Demo
   - 實現時間：2-3小時

2. **Demo亮點**: 展示Level 2概念
   - 準備架構圖和性能對比
   - 說明未來優化方向
   - 不需要完整實現

### 🏗️ Post-Demo重構
1. **第一週**: 實現Level 2虛擬合併索引
   - 最大性能提升
   - 實現複雜度適中
   - 預計時間：2-3天

2. **第二週**: 實現Level 3熱插拔管理
   - 優化記憶體使用
   - 支援多用戶場景
   - 預計時間：2-3天

3. **未來規劃**: Level 4 Skill Cover
   - 作為進階功能
   - 需要更多測試和優化
   - 預計時間：1週

---

## 性能基準測試

### 測試環境
- 100個PDF文件，每個50頁
- 總計約50,000個chunks
- 向量維度：1536 (OpenAI embeddings)

### 預期結果

| 優化等級 | 搜尋延遲 | 記憶體使用 | 實現複雜度 |
|---------|---------|-----------|-----------|
| Baseline (串行) | 2-3秒 | 400MB | - |
| Level 1 (並行) | 0.5-1秒 | 400MB | 簡單 |
| Level 2 (主索引) | <50ms | 100MB | 中等 |
| Level 3 (LRU) | <50ms | 50-100MB | 較難 |
| Level 4 (Cover) | <20ms | 150MB | 困難 |

---

## 程式碼範例位置

建議在以下位置實現：

```
app/SkillServices/
├── optimizers/
│   ├── __init__.py
│   ├── parallel_search.py      # Level 1
│   ├── master_index.py         # Level 2
│   ├── memory_manager.py       # Level 3
│   └── skill_cover.py          # Level 4
├── skill_retrieval_service.py  # 整合優化器
└── performance_monitor.py      # 性能監控
```

---

## 風險與緩解

### 風險1: Demo時系統不穩定
**緩解**: 使用Level 1簡單方案，充分測試

### 風險2: 主索引建立時間長
**緩解**: 預先建立Demo用的主索引

### 風險3: 記憶體溢出
**緩解**: 實現記憶體監控和自動降級

### 風險4: 搜尋品質下降
**緩解**: 保留完整搜尋作為fallback

---

## 總結

1. **Demo策略**: 採用Level 1並行搜尋，簡單可靠
2. **長期方案**: Level 2主索引是最佳平衡點
3. **進階優化**: Level 3-4根據實際需求決定
4. **關鍵指標**: 搜尋延遲 < 100ms，記憶體 < 200MB

---

*文檔生成時間: 2025-11-25*
*下次更新: Demo後實際測試結果*