# 多文件摘要問題與解決方案

**文檔建立日期**: 2025-11-24
**問題類型**: RAG 檢索策略
**狀態**: 暴力解法已實作，Map-Reduce 解法待實作

---

## 問題描述

### 現象

當用戶勾選 2 份以上文件並詢問「請各別說明二份來源文件的內容」時，系統只回傳第一份文件的詳細內容，第二份文件顯示「並未出現其他完整的文件內容」。

### 截圖證據

參考: `refData/errors/images/個別說明二篇文件_只有其中一篇出現.png`

### 根因分析

1. **意圖檢測不完整**
   - 用戶查詢「請各別說明二份來源文件的內容」不包含 `SUMMARY_KEYWORDS`（摘要、總結、概述等）
   - 導致 `is_summary = False`

2. **Fair Distribution 未啟用**
   - 因為 `is_summary = False`，所以 `enable_fair_dist = False`
   - 系統使用標準檢索模式

3. **標準模式的問題**
   - 標準模式從所有文件取 top_k 後按相關性排序
   - 語義相似度高的單一文件會主導結果

### 資料流追蹤

```
用戶查詢: "請各別說明二份來源文件的內容"
    ↓
detect_summary_intent() → SUMMARY_KEYWORDS 不匹配 → is_summary = False
    ↓
enable_fair_dist = False (因為 is_summary = False)
    ↓
retrieve_context(fair_distribution=False) → 標準模式
    ↓
從 2 個文件各取 top_k=5 chunks → 合併後排序取前 5 個
    ↓
結果: 可能全部來自單一文件 ❌
```

---

## 解決方案一：暴力解法 (已實作)

### 設計理念

當用戶要求摘要/說明多個文件時，跳過 FAISS 向量檢索，直接從 SQLite 取出文件的 overview，組成 prompt 餵給 LLM。

**優點**:
- 速度極快（跳過 FAISS）
- 100% 保證每個文件都有內容
- Demo 時效果非常好

**缺點**:
- 只能使用 overview，無法回答細節問題
- 依賴 overview 的品質

### 實作細節

#### 1. 意圖檢測 (`app/Services/iterative_query_expansion_service.py`)

```python
# 新增多文件關鍵字
MULTI_FILE_KEYWORDS = [
    "各別", "分別", "每份", "每一份", "所有文件", "這些文件",
    "二份", "兩份", "多份", "各自", "各個", "不同文件",
    "說明", "介紹", "比較", "對比", "差異", "異同"
]

def detect_multi_file_intent(self, query: str) -> bool:
    """檢測是否要求對多個文件進行個別處理"""
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in self.MULTI_FILE_KEYWORDS)

def detect_multi_file_summary_intent(self, query: str, file_count: int) -> bool:
    """檢測是否應使用 overview shortcut"""
    if file_count < 2:
        return False
    is_summary = self.detect_summary_intent(query)
    is_multi_file = self.detect_multi_file_intent(query)
    return is_summary or is_multi_file
```

#### 2. Controller 分支 (`app/api/v1/endpoints/chat.py`)

```python
# 在 Phase 2: Parallel Retrieval 中

if is_multi_file_summary and overviews:
    # ⚡ SHORTCUT: 跳過 FAISS，直接用 overview
    logger.info(f"[SHORTCUT] Multi-file summary detected, using overview shortcut")

    for file_id, overview in overviews.items():
        context_chunks.append({
            "content": overview,
            "metadata": {"file_id": file_id, "source": "overview_shortcut"}
        })
else:
    # 標準 FAISS 檢索路徑
    retrieval_tasks = [...]
```

#### 3. 專用 Prompt 模板 (`app/Services/prompt_service.py`)

```python
MULTI_FILE_SUMMARY_TEMPLATE = """你是一位專業的文檔分析師。

**任務類型**: 多文件個別說明

用戶勾選了 {file_count} 份文件，請你為每份文件提供完整的說明。

---
【各文件概述】
{context}
---

**回答格式要求**:

請為每份文件建立獨立的說明區塊，格式如下：

### 所提供文件 1：[檔名]
• **檔名**：[實際檔案名稱]
• **主要研究方向**：[簡述研究目的或主題]
• **關鍵內容**：
  1. [重點 1]
  2. [重點 2]
  3. [重點 3]

### 所提供文件 2：[檔名]
...（以此類推）

**重要規則**:
1. 確保每份文件都有完整說明，不要遺漏任何一份
2. 使用上下文中提供的實際檔案名稱

**用戶問題**: {query}
"""
```

### 測試結果

```
=== 意圖檢測測試 ===
⚡ SHORTCUT | "請各別說明二份來源文件的內容" (files=2) ✅
⚡ SHORTCUT | "請摘要這兩份文件" (files=2) ✅
⚡ SHORTCUT | "比較這些文件的差異" (files=3) ✅
  standard | "什麼是機器學習" (files=2) ✅
  standard | "解釋這份文件的第三章" (files=1) ✅
```

---

## 解決方案二：Map-Reduce 模式 (待實作)

### 設計理念

參考 `refData/Codes/process_more_than_two_files.py` 的設計，實作真正的多文件檢索策略。

**Phase 1 (Map)**: 為每個文件分別檢索
**Phase 2 (Rerank)**: 可選的重排序
**Phase 3 (Reduce)**: 合併結果並組裝 Prompt

### 與 Milvus 版本的差異

| 項目 | Milvus (範例) | FAISS (我們的系統) |
|------|---------------|-------------------|
| 儲存結構 | 單一 Collection + filter | 每個文件獨立的 FAISS Index |
| 查詢方式 | `expr=f'file_name == "{file}"'` | `store_id=file_id` 直接指定 |
| 索引管理 | `_milvus_client` | `_stores[file_id]` Dict |

**關鍵差異**: 我們的 FAISS 架構**天生就是 per-file 的**！

### 建議實作 (`app/Services/retrieval_service.py`)

```python
async def retrieve_context_per_file(
    self,
    query: str,
    file_ids: List[str],
    chunks_per_file: int = 3,
    include_scores: bool = True
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Map-Reduce 模式: 為每個文件分別檢索上下文

    Args:
        query: 用戶查詢
        file_ids: 要查詢的文件 ID 列表
        chunks_per_file: 每個文件取幾個 chunk
        include_scores: 是否包含相似度分數

    Returns:
        Dict[file_id, List[chunks]] - 按文件分組的檢索結果
    """
    results_by_file = {}

    # Phase 1: Map - 每個文件獨立檢索
    for file_id in file_ids:
        try:
            if include_scores:
                chunks = self.vector_store_provider.similarity_search_with_score(
                    store_id=file_id,
                    query=query,
                    k=chunks_per_file
                )
            else:
                chunks = self.vector_store_provider.similarity_search(
                    store_id=file_id,
                    query=query,
                    k=chunks_per_file
                )

            logger.info(f"[Per-File] Retrieved {len(chunks)} chunks from {file_id}")
            results_by_file[file_id] = chunks

        except ValueError as e:
            logger.warning(f"Store not found for file_id '{file_id}': {e}")
            results_by_file[file_id] = []
        except Exception as e:
            logger.error(f"Error searching in store '{file_id}': {e}")
            results_by_file[file_id] = []

    # Phase 2: 驗證每個文件都有結果
    empty_files = [f for f, chunks in results_by_file.items() if not chunks]
    if empty_files:
        logger.warning(f"[Per-File] No chunks found for files: {empty_files}")

    return results_by_file
```

### 執行流程圖解

```
用戶查詢: "請各別說明二份來源文件的內容"
file_ids: ["file_A_uuid", "file_B_uuid"]

┌─────────────────────────────────────────────────────────────┐
│                    Phase 1: Map                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌──────────────────┐      ┌──────────────────┐           │
│   │   FAISS Index    │      │   FAISS Index    │           │
│   │   (file_A_uuid)  │      │   (file_B_uuid)  │           │
│   └────────┬─────────┘      └────────┬─────────┘           │
│            │                         │                      │
│            ▼                         ▼                      │
│   similarity_search()        similarity_search()            │
│   k=3                        k=3                            │
│            │                         │                      │
│            ▼                         ▼                      │
│   ┌──────────────────┐      ┌──────────────────┐           │
│   │ Chunk A1 (0.85)  │      │ Chunk B1 (0.82)  │           │
│   │ Chunk A2 (0.78)  │      │ Chunk B2 (0.75)  │           │
│   │ Chunk A3 (0.72)  │      │ Chunk B3 (0.71)  │           │
│   └──────────────────┘      └──────────────────┘           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Return Value                             │
├─────────────────────────────────────────────────────────────┤
│   {                                                          │
│     "file_A_uuid": [ChunkA1, ChunkA2, ChunkA3],   # 3 chunks │
│     "file_B_uuid": [ChunkB1, ChunkB2, ChunkB3]    # 3 chunks │
│   }                                                          │
│                                                              │
│   ✅ 每個文件保證有 chunks                                    │
└─────────────────────────────────────────────────────────────┘
```

### 與現有 `retrieve_context()` 的對比

```python
# 現有方法 (fair_distribution=True 模式)
async def retrieve_context(self, query, file_ids, top_k=5, fair_distribution=True):
    """
    問題: 先分配 chunks_per_file，再合併，最後只取 top_k

    例: 2 files, top_k=5
        → chunks_per_file = 5 // 2 = 2 (每檔只取2個!)
        → 合併後再取 top 5
        → 結果: 可能某個文件只有 2 個 chunk 被使用
    """
    chunks_per_file = max(1, top_k // len(file_ids))  # 可能太少!
    ...
    final_results = all_results[:top_k]  # 最後又被截斷!


# 新方法 (per-file 模式)
async def retrieve_context_per_file(self, query, file_ids, chunks_per_file=3):
    """
    優點:
    1. 每個文件獨立保證 chunks_per_file 個結果
    2. 不會被截斷
    3. 返回結構化的 Dict，便於後續處理
    """
    return {
        file_id: [chunk1, chunk2, chunk3]
        for file_id in file_ids
    }
```

---

## 兩種解法比較

| 指標 | 暴力解法 | Map-Reduce |
|------|----------|------------|
| **實作狀態** | ✅ 已完成 | ⏳ 待實作 |
| **速度** | ⚡ 極快 (跳過 FAISS) | 🔄 正常 |
| **回答細節問題** | ❌ 無法 (只有 overview) | ✅ 可以 |
| **覆蓋率** | 100% (每個文件) | 100% (每個文件) |
| **適用場景** | Demo、摘要請求 | 生產環境、細節問答 |
| **工作量** | ~1.5 小時 | ~4-6 小時 |

---

## 關鍵程式碼位置

| 功能 | 檔案 | 行號/方法 |
|------|------|----------|
| 多文件關鍵字 | `app/Services/iterative_query_expansion_service.py` | `MULTI_FILE_KEYWORDS` |
| 意圖檢測 | `app/Services/iterative_query_expansion_service.py` | `detect_multi_file_summary_intent()` |
| Shortcut 分支 | `app/api/v1/endpoints/chat.py` | Phase 2 註解區塊 |
| 多文件 Prompt | `app/Services/prompt_service.py` | `MULTI_FILE_SUMMARY_TEMPLATE` |
| 現有 fair_distribution | `app/Services/retrieval_service.py` | `retrieve_context()` |

---

## 測試方法

1. 重新啟動伺服器
2. 勾選 2+ 份文件
3. 輸入測試查詢：
   - "請各別說明二份來源文件的內容"
   - "請摘要這兩份文件"
   - "比較這些文件的差異"
4. 查看 log 確認 `[SHORTCUT]` 是否出現

---

## 相關參考

- 範例程式碼: `refData/Codes/process_more_than_two_files.py`
- 錯誤截圖: `refData/errors/images/個別說明二篇文件_只有其中一篇出現.png`
- RAG 資料流分析: `claudedocs/RAG_Dataflow_Analysis_Report.md`

---

## 資料不一致問題調查 (2025-11-24)

### 發現的問題

在測試多文件摘要時，發現資料庫存在不一致狀態：

| 資料來源 | 狀態 |
|----------|------|
| file_metadata.chunk_count | 有值 (e.g., 266) |
| chunks_metadata 記錄數 | 0 ❌ |
| document_overviews.overview | 部分為空 ❌ |
| FAISS index | 存在 ✅ |

### 根本原因

**1. chunks_metadata 為空的原因：**

`FileMetadataProvider.add_chunks()` 方法已定義，但**從未在 upload.py 中被呼叫**！

```
upload.py 處理流程：
├─ Step 4: add_document_chunks() → 建立 FAISS ✅
├─ Step 5: update_embedding_status() → 更新狀態 ✅
├─ ❌ 缺少: add_chunks() → chunks_metadata 未保存
└─ Step 6: generate/store_overview() → 存入 overview
```

**2. overview 為空的原因：**

如果 `generate_overview()` 拋出異常（例如 LLM 服務問題），外層 try-catch 會捕獲錯誤，導致 `store_overview()` 不執行：

```python
# upload.py Line 172-187
try:
    overview = await overview_service.generate_overview(...)  # 如果這裡失敗
    await overview_service.store_overview(...)  # 這裡不會執行
except Exception as overview_error:
    logger.warning(...)  # 只記錄警告，overview 保持空
```

### 已實作的暫時修復

#### ❌ 第一次修復（有邏輯錯誤）

```python
# 分離有效 overview 的文件和沒有的文件
for file_id, overview in overviews.items():  # ← 問題：只迭代 dict 裡的 file_id
    if overview and overview.strip():  # 有效 overview
        files_with_overview.append(file_id)
    else:
        files_without_overview.append(file_id)  # 需要 FAISS fallback
```

**邏輯錯誤**：
- `get_multiple_overviews()` 只返回**有 overview 的文件**，空 overview 的文件**不在 dict 裡**
- 所以 `overviews.items()` 只會迭代有 overview 的文件
- `else` 分支**永遠不會執行**，因為 dict 裡的 overview 一定非空
- 結果：完全沒有 overview 的文件**根本不會被偵測到**！

```
┌─────────────────────────────────────────────────────────────────┐
│  get_multiple_overviews() 返回:                                  │
│  {file_1: "摘要...", file_2: "摘要..."}  ← file_3 不在 dict 裡！ │
├─────────────────────────────────────────────────────────────────┤
│  for file_id, overview in overviews.items():  ← 只迭代 2 個     │
│      if overview.strip(): → True              ← 永遠 True       │
│      else: → 永遠不執行！                                        │
│                                                                 │
│  結果: file_3 被完全忽略！                                       │
└─────────────────────────────────────────────────────────────────┘
```

#### ✅ 第二次修復（正確邏輯）

```python
# 1. 處理 dict 裡的文件
for file_id, overview in overviews.items():
    if overview and overview.strip():
        files_with_overview.append(file_id)
        context_chunks.append({...})
    else:
        files_without_overview.append(file_id)

# 2. ★關鍵★ 比較 request.file_ids 和 overviews.keys() 找出缺失的文件
overviews_keys = set(overviews.keys())
for file_id in request.file_ids:
    if file_id not in overviews_keys:
        files_without_overview.append(file_id)
        logger.warning(f"[SHORTCUT] File {file_id} has no overview record at all")

# 對沒有 overview 的文件使用 FAISS 檢索
if files_without_overview:
    fallback_results = await retrieval_service.retrieve_context(...)
```

**修復重點**：不是檢查 overview 內容是否為空，而是檢查**哪些 file_id 根本沒有出現在 overviews dict 裡**。

### 建議的永久修復

**修復 1: 在 upload.py 中添加 `add_chunks` 呼叫**

位置: `app/api/v1/endpoints/upload.py` Step 4 之後

```python
# Step 4.5: Save chunk metadata to SQLite
chunk_metadata_records = [
    {
        "chunk_id": f"chunk_{i}",
        "chunk_index": i,
        "chunk_text": text[:500],  # 只保存前 500 字元
        "milvus_id": None
    }
    for i, text in enumerate(chunk_texts)
]
await file_metadata_provider.add_chunks(file_id, chunk_metadata_records)
```

**修復 2: 確保 overview 生成失敗時也存入 fallback**

修改 upload.py 的 overview 處理：

```python
try:
    overview = await overview_service.generate_overview(...)
except Exception as e:
    logger.warning(f"Overview generation failed: {e}")
    overview = f"文檔: {filename}\n\n[概述生成失敗，請查看原文檔]"

# 無論成功或失敗都存入
await overview_service.store_overview(file_metadata_provider, file_id, overview)
