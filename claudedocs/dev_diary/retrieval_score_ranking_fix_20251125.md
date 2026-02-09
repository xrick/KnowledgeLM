# Multi-File Retrieval Score Ranking 修正記錄

**修正時間**: 2025-11-25 13:00
**問題類型**: Retrieval Quality Issue
**影響範圍**: Multi-file queries with specific questions

---

## 問題描述

### 用戶報告

當選擇多個檔案（如 4 個）並詢問特定問題時，系統無法找到正確資訊：

- **選擇 1 個檔案** + 問「請解釋什麼是bitnet.cpp」 → ✅ 正常回答
- **選擇 4 個檔案** + 問「請解釋什麼是bitnet.cpp」 → ❌ 回覆「找不到相關資訊」

### 錯誤回覆範例

```
在您勾選的文檔中，我沒有找到任何關於 bitnet.cpp 的直接說明。

補充說明：
- bitnet.cpp 不是在目前提供的文件片段中提及的術語或檔案。
- 通常，.cpp 檔案是 C++ 程式碼檔案...
```

但實際上文檔中**確實包含** bitnet.cpp 的詳細資訊。

---

## 問題調查

### 1. 排除 Intent Detection 問題

首先測試 intent detection 系統：

```python
Query: "請解釋什麼是bitnet.cpp"
  → is_summary: False
  → is_multi_file_summary: False
```

✅ **Intent detection 運作正常**，沒有錯誤觸發 overview shortcut。

### 2. 檢查 Retrieval 日誌

從日誌發現：

```
Query intent detected: question (is_summary=False, is_multi_file_summary=False)
Query expansion complete: 1 rounds, 3 final queries
Retrieved 5 chunks from file file_1763978861... (4 個檔案各 5 chunks)
Retrieved 11 unique context chunks from vector search
```

- ✅ FAISS retrieval 執行了
- ✅ Retrieved 11 chunks（不是 0）
- ❌ 但 LLM 仍然說找不到資訊

### 3. 找到根本原因

檢查 `app/Services/retrieval_service.py` 的 `retrieve_context()` 方法：

```python
# Standard mode: retrieve top_k from each file, then rank globally
for file_id in file_ids:
    results = self.vector_store_provider.similarity_search(
        store_id=file_id,
        query=query,
        k=top_k  # ← 從每個檔案取 top_k 個 chunks
    )
    all_results.extend(results)

# Sort by score if available (lower is better for FAISS)
if include_scores and all_results:  # ← 關鍵：只有在 include_scores=True 時才排序！
    all_results.sort(key=lambda x: x.get('score', float('inf')))

# Limit to top_k overall results
final_results = all_results[:top_k]  # ← 沒有排序就直接取前 top_k 個
```

**問題流程**：

1. 從 4 個檔案各取 5 個 chunks → 總共 20 個 chunks
2. **如果 `include_scores=False`，則不會根據相似度排序**
3. 直接取前 5 個 chunks（按檔案順序，不是按相關性）
4. bitnet.cpp 的詳細資訊可能在後面的檔案中，被截斷了
5. LLM 收到的 5 個 chunks 不包含相關資訊

**檢查 chat.py 的調用**：

```python
retrieval_tasks = [
    retrieval_service.retrieve_context(
        query=question,
        file_ids=request.file_ids,
        top_k=request.top_k,
        fair_distribution=enable_fair_dist
        # ← 缺少 include_scores=True
    )
    for question in expanded_questions
]
```

確認了問題：chat.py 調用時**沒有傳遞 `include_scores=True`**！

---

## 修正方案

### 修改檔案

**app/api/v1/endpoints/chat.py**

### 修改位置

1. **Line 335** - Streaming endpoint 的標準 retrieval
2. **Line 305** - Streaming endpoint 的 shortcut fallback
3. **Line 642** - Non-streaming endpoint 的 retrieval

### 修改內容

```python
retrieval_tasks = [
    retrieval_service.retrieve_context(
        query=question,
        file_ids=request.file_ids,
        top_k=request.top_k,
        fair_distribution=enable_fair_dist,
        include_scores=True  # ← 新增：Enable score-based ranking for multi-file retrieval
    )
    for question in expanded_questions
]
```

---

## 修正效果

### Before（問題狀態）

| 檔案數 | 查詢類型 | Retrieval 方式 | 排序 | 結果 |
|-------|---------|--------------|------|------|
| 1 | 特定問題 | FAISS | ❌ 無排序 | ✅ 正常（因為只有 1 個檔案） |
| 4 | 特定問題 | FAISS | ❌ 無排序 | ❌ 找不到資訊（相關 chunks 被截斷） |
| 4 | 整體摘要 | Overview shortcut | N/A | ✅ 正常 |

### After（修正後）

| 檔案數 | 查詢類型 | Retrieval 方式 | 排序 | 結果 |
|-------|---------|--------------|------|------|
| 1 | 特定問題 | FAISS | ✅ 按相似度 | ✅ 正常 |
| 4 | 特定問題 | FAISS | ✅ 按相似度 | ✅ 正常（選擇最相關的 chunks） |
| 4 | 整體摘要 | Overview shortcut | N/A | ✅ 正常 |

---

## 技術細節

### Retrieval Service 邏輯

```python
def retrieve_context(
    query: str,
    file_ids: List[str],
    top_k: int = 5,
    include_scores: bool = False,  # ← 預設為 False
    fair_distribution: bool = False
):
    # Standard mode
    for file_id in file_ids:
        results = similarity_search(store_id=file_id, query=query, k=top_k)
        all_results.extend(results)

    # 只有 include_scores=True 才會排序
    if include_scores and all_results:
        all_results.sort(key=lambda x: x.get('score', float('inf')))

    return all_results[:top_k]
```

### FAISS Distance Metric

- FAISS 使用 **L2 distance**（歐幾里得距離）
- **分數越低 = 相似度越高**
- 排序時使用 ascending order（從小到大）

### Fair Distribution Mode

Fair distribution mode 有自己的邏輯：
- 計算 `chunks_per_file = max(1, top_k // len(file_ids))`
- 確保每個檔案至少貢獻 1 個 chunk
- 但**不影響此次修正**，因為 fair distribution 只在 `is_summary=True` 時啟用

---

## 測試驗證

### 測試案例 1：特定問題 + 單一檔案

```
Query: "請解釋什麼是bitnet.cpp"
Files: 1 個檔案
Expected: 找到詳細資訊 ✅
Result: ✅ 通過（修正前後都正常）
```

### 測試案例 2：特定問題 + 多個檔案

```
Query: "請解釋什麼是bitnet.cpp"
Files: 4 個檔案
Expected: 找到詳細資訊 ✅
Result Before: ❌ 找不到資訊
Result After: ✅ 通過（修正後正常）
```

### 測試案例 3：整體摘要 + 多個檔案

```
Query: "比較三份文件"
Files: 3 個檔案
Expected: 使用 overview shortcut ✅
Result: ✅ 通過（修正前後都正常，不受影響）
```

---

## 影響範圍

### 受影響的功能

✅ **正面影響**：
- 多檔案選擇 + 特定問題查詢（retrieval quality 提升）
- 所有需要精確資訊檢索的場景

❌ **無負面影響**：
- 單一檔案查詢（行為不變）
- Multi-file summary（使用 overview shortcut，不受影響）
- Fair distribution mode（仍然正常運作）

### 性能影響

- **Minimal overhead**：`include_scores=True` 只是讀取已經計算好的 scores
- FAISS 在 `similarity_search_with_score()` 中本來就計算了 scores
- 排序操作：`O(n log n)`，其中 n = file_count × top_k（通常很小）

---

## 相關檔案

### 修改的檔案
- `app/api/v1/endpoints/chat.py` - 新增 `include_scores=True` 參數

### 相關檔案（未修改）
- `app/Services/retrieval_service.py` - Retrieval logic
- `app/Services/iterative_query_expansion_service.py` - Intent detection
- `app/Services/query_intent_detection/` - Pattern detection module

---

## 未來建議

### 短期（1 週內）
1. 監控日誌確認修正效果
2. 收集用戶反饋
3. 驗證性能影響

### 中期（1 個月內）
1. 考慮將 `include_scores=True` 設為預設值
2. 優化 retrieval ranking algorithm
3. 實作更智慧的 chunk selection strategy

### 長期（3-6 個月）
1. 實作 hybrid retrieval（BM25 + Vector）
2. 加入 reranking model
3. 考慮 query-specific retrieval strategies

---

## 總結

✅ **問題修正**：Multi-file retrieval 現在會根據相似度排序，確保最相關的 chunks 被選中
✅ **Intent detection 正常**：新的 regex-based pattern detection 運作良好
✅ **零風險部署**：修正不影響現有功能，純粹提升 retrieval quality
✅ **性能影響極小**：Minimal overhead，不影響系統性能

**下一步**：在生產環境觀察 1-2 天，確認修正效果穩定。

---

**修正者**: Claude (SuperClaude Framework)
**修正方式**: Add score-based ranking to multi-file retrieval
**風險等級**: 低（純粹提升 quality，無破壞性變更）
