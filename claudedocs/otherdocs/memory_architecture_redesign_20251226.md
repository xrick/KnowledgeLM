# Memory Architecture Redesign - 雙軌隔離架構

**日期**: 2025-12-26
**狀態**: 設計中
**優先級**: P0

## 問題診斷

### 當前問題
1. **Intent Classification 失效**: 翻譯請求被識別為 `is_conversational: false`
2. **Chat History 未儲存**: 第一輪查詢後 "Loaded 0 messages from history"
3. **RAG Context 污染**: 對話歷史包含 RAG 檢索片段，導致翻譯時輸出文檔內容

### 根本原因分析

```
問題鏈：
1. curl | head -20 → 過早斷開連接 → save_message 未執行
2. has_chat_history=false → 意圖檢測跳過 → 翻譯請求走 RAG 路徑
3. 即使有歷史，Memory 包含完整 RAG 上下文 → 翻譯時輸出錯誤內容
```

## 雙軌隔離架構設計 (Dual-Track Isolation)

### 架構圖

```
                    ┌─────────────────────────────────────────────────────┐
                    │                   用戶輸入                           │
                    └─────────────────────────────────────────────────────┘
                                            │
                                            ▼
                    ┌─────────────────────────────────────────────────────┐
                    │              Phase 1: Intent Classifier              │
                    │  ┌─────────────────────────────────────────────┐    │
                    │  │  輸出:                                       │    │
                    │  │  - is_conversational: bool                   │    │
                    │  │  - requires_retrieval: bool (NEW)            │    │
                    │  │  - action: translation|follow_up|rag_query   │    │
                    │  │  - target_history_index: int (-1=last)       │    │
                    │  └─────────────────────────────────────────────┘    │
                    └─────────────────────────────────────────────────────┘
                                            │
                           ┌────────────────┼────────────────┐
                           │                │                │
                           ▼                │                ▼
         ┌─────────────────────────┐        │  ┌─────────────────────────┐
         │   Operation Branch      │        │  │   Knowledge Branch       │
         │   (requires_retrieval   │        │  │   (requires_retrieval    │
         │    = false)             │        │  │    = true)               │
         │                         │        │  │                          │
         │  • Translation          │        │  │  • Phase 2: Retrieval    │
         │  • Summarize Previous   │        │  │  • Phase 3: Context      │
         │  • Clarify              │        │  │  • Phase 4: Generation   │
         │  • Follow-up            │        │  │                          │
         └─────────────────────────┘        │  └─────────────────────────┘
                    │                       │                │
                    ▼                       │                ▼
         ┌─────────────────────────┐        │  ┌─────────────────────────┐
         │  Minimal Prompt         │        │  │  RAG System Prompt      │
         │  ┌───────────────────┐  │        │  │  ┌───────────────────┐  │
         │  │ System: 翻譯員    │  │        │  │  │ System: RAG 助手  │  │
         │  │ History: [clean]  │  │        │  │  │ Context: [chunks] │  │
         │  │ User: 翻譯請求    │  │        │  │  │ User: 查詢        │  │
         │  └───────────────────┘  │        │  │  └───────────────────┘  │
         └─────────────────────────┘        │  └─────────────────────────┘
                    │                       │                │
                    └───────────────────────┼────────────────┘
                                            │
                                            ▼
                    ┌─────────────────────────────────────────────────────┐
                    │              Enhanced Memory Storage                 │
                    │  ┌─────────────────────────────────────────────┐    │
                    │  │  message: {                                  │    │
                    │  │    role: "assistant",                        │    │
                    │  │    content: "純淨回覆（無 RAG 片段）",       │    │
                    │  │    metadata: {                               │    │
                    │  │      query_type: "rag" | "conversational",   │    │
                    │  │      document_ids: [...],  // 如果是 RAG     │    │
                    │  │      action: "translation" | "query" | ...   │    │
                    │  │    }                                         │    │
                    │  │  }                                           │    │
                    │  └─────────────────────────────────────────────┘    │
                    └─────────────────────────────────────────────────────┘
```

## 實作計畫

### P0: 修復儲存時機問題

**問題**: `curl | head -20` 導致連接斷開，save_message 未執行

**解決方案**: 儲存邏輯移到 StreamingResponse 的 finally block

```python
async def event_generator():
    full_response = ""
    saved = False
    try:
        async for update in progressive_service.chat_stream_progressive(...):
            # ... accumulate full_response ...
            yield update

        # 正常完成：儲存
        if full_response.strip():
            await save_conversation(...)
            saved = True
    except asyncio.CancelledError:
        # 客戶端斷開：仍然儲存已累積的回覆
        if full_response.strip() and not saved:
            await save_conversation(...)
    finally:
        # 確保清理
        pass
```

### P1: 增強 Intent Classifier

**新增欄位**: `requires_retrieval`

```python
ENHANCED_INTENT_PROMPT = """Analyze this query:

User Query: {user_query}
Has Chat History: {has_history}

Respond with JSON:
{
  "is_conversational": true/false,
  "requires_retrieval": true/false,  // NEW: 是否需要檢索文檔
  "action": "translation|follow_up|summarize|clarify|rag_query",
  "target_history_index": -1,  // -1 表示最後一個回覆
  "confidence": 0.0-1.0
}

Rules:
- Translation requests: requires_retrieval=false
- "上一個回覆" references: requires_retrieval=false
- New topic questions: requires_retrieval=true
- If has_history=false but seems conversational: requires_retrieval=true (fallback to RAG)
"""
```

### P2: Memory 結構優化

**新結構**:

```python
message = {
    "role": "assistant",
    "content": clean_response,  # 純淨回覆，不含 RAG 片段
    "timestamp": datetime.now(),
    "metadata": {
        "query_type": "rag" | "conversational",
        "action": "translation" | "query" | "follow_up",
        "skill_id": skill_id,
        "document_ids": [...],  # 僅 RAG 查詢時填入
        "original_query": user_query,
        "response_length": len(clean_response)
    }
}
```

### P3: 動態 System Prompt

**Operation Branch Prompt** (翻譯/後續):

```python
OPERATION_SYSTEM_PROMPT = """你是一位專業的助手。

用戶正在進行後續對話，請根據對話歷史回應。

**規則**：
1. 直接回應用戶請求
2. 如果是翻譯請求，完整翻譯前一個回答
3. 不要提及文檔或檢索
4. 保持專業語氣
"""
```

**Knowledge Branch Prompt** (RAG):

```python
RAG_SYSTEM_PROMPT = """你是一位專業的文檔問答助手。

[文檔內容]
{context}

**回答策略**：
1. 優先引用文檔內容
2. 明確標註引用來源
...
"""
```

## 測試驗證

### Test Case 1: 正常 RAG 查詢
```
Query: "What is Strix Halo?"
Expected: requires_retrieval=true, RAG 路徑
```

### Test Case 2: 翻譯請求
```
Query: "請把上一個回覆翻譯成英文"
Expected: requires_retrieval=false, Operation 路徑
```

### Test Case 3: 無歷史的翻譯請求
```
Query: "請翻譯這個" (無歷史)
Expected: requires_retrieval=true (fallback), 告知需要先查詢
```

## 修改清單

| 檔案 | 修改內容 |
|------|----------|
| `app/api/v1/endpoints/skills.py` | 儲存時機修復、增強 metadata |
| `phase1_skill_query_understanding.py` | 增加 requires_retrieval 欄位 |
| `progressive_streaming.py` | 根據 requires_retrieval 分流 |
| `phase4_response_generation.py` | 動態選擇 System Prompt |
| `chat_history_provider/client.py` | 增強 message 結構 |

## 時程

- **P0 (立即)**: 修復儲存時機
- **P1 (今天)**: 增強 Intent Classifier
- **P2 (今天)**: Memory 結構優化
- **P3 (今天)**: 動態 System Prompt
- **測試**: 完整驗證雙軌隔離
