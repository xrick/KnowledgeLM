<!-- claudedocs/specs/docai_workflow_20251216.md -->
# DocAI Query Workflow (2025-12-16)

## 概述

本文檔描述 DocAI Skill-Based RAG 系統的查詢工作流程，從使用者在瀏覽器輸入 query 到顯示結果的完整流程。

---

## 工作流程總覽

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DocAI Query Workflow                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [1. 前端輸入]     [2. API 路由]     [3. 向量檢索]     [4. LLM 生成]         │
│       │                 │                 │                 │               │
│       ▼                 ▼                 ▼                 ▼               │
│  ┌─────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐         │
│  │ Browser │ ───> │ FastAPI  │ ───> │  FAISS   │ ───> │  Ollama  │         │
│  │ (HTML)  │      │ Endpoint │      │ Retrieval│      │   LLM    │         │
│  └─────────┘      └──────────┘      └──────────┘      └──────────┘         │
│       │                 │                 │                 │               │
│       │                 │                 │                 │               │
│       ▼                 ▼                 ▼                 ▼               │
│  [5. 結果顯示]  <───────────────────────────────────────────┘               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 階段 1：前端輸入 (Frontend Input)

### 檔案位置
- `template/skill_main.html`

### 處理流程

```javascript
// Line 2461: sendQuery() 函數
async function sendQuery() {
    const query = document.getElementById('query-input').value.trim();
    const selectedSkills = [...];  // 使用者勾選的技能/文檔

    // 根據模式選擇查詢方式
    if (isProgressiveMode) {
        await sendProgressiveQuery(query);  // SSE 串流模式
    } else {
        await sendTraditionalQuery(query);  // 傳統 JSON 模式
    }
}
```

### 比喻說明

> **圖書館的讀者服務台** 📚
>
> 前端就像圖書館的讀者服務台。使用者（讀者）走到櫃台，說出他想找什麼（query），
> 並告訴館員要在哪些書架區域找（selectedSkills）。服務台會把這個需求記錄下來，
> 傳送到後方的書庫管理系統。

### 傳遞的資料

```json
{
    "skill_ids": ["skill_20251126_xxx", "skill_20251127_yyy"],
    "query": "什麼是大語言模型的訓練過程？",
    "top_k": 10
}
```

---

## 階段 2：API 路由與驗證 (API Routing & Validation)

### 檔案位置
- `app/api/v1/endpoints/skills.py` (Lines 367-600)

### 處理流程

```python
# Line 367: query_demo_skill endpoint
@router.post("/demo/query")
async def query_demo_skill(
    skill_ids: List[str],
    query: str,
    top_k: int = 10,
    metadata_provider: SkillMetadataProvider,
    retrieval_service: SkillRetrievalService,
    llm_client: LLMProviderClient,
    prompt_service: PromptService
):
    # 1. 解析 skill_ids（支援 head_id 和 skill_id）
    valid_skill_ids = []
    for sid in target_skill_ids:
        if sid.startswith('head_'):
            # 展開 head_id 到所有子文檔
            matching_skills = await metadata_provider.list_skills()
            ...
        else:
            # 直接使用 skill_id
            mappings = await metadata_provider.get_documents_for_skill(sid)
            valid_skill_ids.append(sid)
```

### 比喻說明

> **圖書館的索引系統** 🗂️
>
> API 層就像圖書館的索引系統。當讀者的需求送到這裡，系統會：
> 1. **驗證書架代碼**：確認讀者指定的書架區域（skill_ids）確實存在
> 2. **展開分類目錄**：如果讀者說「法律區」（head_id），系統會展開成「民法架」「刑法架」等
> 3. **建立搜尋清單**：把所有要搜尋的具體書架編號列出來

### 關鍵操作

| 操作 | 函數 | 說明 |
|------|------|------|
| 展開 Head ID | `metadata_provider.list_skills()` | 將技能群組展開為具體文檔 |
| 驗證文檔存在 | `metadata_provider.get_documents_for_skill()` | 確認 FAISS 索引存在 |
| 獲取技能名稱 | `metadata_provider.get_skill()` | 用於引用標註 |

---

## 階段 3：向量檢索 (Vector Retrieval)

### 檔案位置
- `app/SkillServices/skill_retrieval_service.py` (Lines 81-133)
- `app/Providers/vector_store_provider/client.py`

### 處理流程

```python
# skill_retrieval_service.py Line 81
async def retrieve_context(
    self,
    query: str,
    content_ids: List[str],  # skill_ids
    top_k: int = 5
) -> List[Dict[str, Any]]:

    # 1. 對每個技能的 FAISS 索引執行搜尋
    for skill_id in content_ids:
        results = self.vector_store_provider.similarity_search_with_score(
            store_id=skill_id,
            query=query,
            k=top_k
        )
        all_results.extend(results)

    # 2. 按相似度分數排序（FAISS 使用 L2 距離，越小越相似）
    all_results.sort(key=lambda x: x.get('score', float('inf')))

    # 3. 返回 top_k 最相關的結果
    return all_results[:top_k]
```

### 向量搜尋內部流程

```
┌──────────────────────────────────────────────────────────────────┐
│                    Vector Retrieval Process                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Query: "什麼是 LLM 訓練？"                                      │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────────────┐                                        │
│  │  Embedding Provider │  ← BGE-M3 模型                          │
│  │  (1024 維向量)      │                                        │
│  └─────────────────────┘                                        │
│         │                                                        │
│         │ [0.12, -0.34, 0.78, ...]                               │
│         ▼                                                        │
│  ┌─────────────────────┐     ┌─────────────────────┐            │
│  │   FAISS Index #1    │     │   FAISS Index #2    │            │
│  │   (skill_xxx)       │     │   (skill_yyy)       │            │
│  └─────────────────────┘     └─────────────────────┘            │
│         │                           │                            │
│         └───────┬───────────────────┘                            │
│                 ▼                                                │
│         ┌─────────────┐                                          │
│         │ Merge & Sort│  ← L2 距離排序                           │
│         └─────────────┘                                          │
│                 │                                                │
│                 ▼                                                │
│         Top-K Chunks with Scores                                 │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 比喻說明

> **智慧書架機器人** 🤖
>
> 向量檢索就像一群智慧機器人在書架間搜尋。
>
> 1. **理解問題**：機器人首先把讀者的問題「翻譯」成一種特殊的數字密碼（1024 維向量），
>    這個密碼代表問題的「語意指紋」。
>
> 2. **比對書頁**：機器人走到每個指定的書架（FAISS Index），把書架上每頁的「指紋」
>    與問題指紋進行比對。越相似的指紋，距離越近。
>
> 3. **收集結果**：所有機器人把找到的相關頁面帶回來，按照「相似程度」排隊。
>    最像的排最前面。

### FAISS 索引結構

```
data/faiss_indices/skills/
├── skill_20251126_xxx/
│   ├── index.faiss          ← 向量索引（二進位）
│   └── index.pkl            ← 元資料（文檔名、頁碼等）
├── skill_20251127_yyy/
│   ├── index.faiss
│   └── index.pkl
└── ...
```

---

## 階段 4：上下文組裝與 LLM 生成 (Context Assembly & LLM Generation)

### 檔案位置
- `app/Services/prompt_service.py` (Lines 30-56)
- `app/Providers/llm_provider/client.py`

### 處理流程

```python
# skills.py Line 517-561
# 1. 組裝上下文
context_texts = []
citations = []

for item in context_results:
    content = item.get("content", "")
    doc_name = metadata.get("document_name")
    page_num = metadata.get("page_number", 0)

    citation = f"[{doc_name}-第{page_num}頁]"
    citations.append(citation)
    context_texts.append(f"{content}\n{citation}")

# 2. 建構 RAG Prompt
messages = prompt_service.build_rag_prompt(
    query=query,
    context_chunks=context_texts,
    language="zh"
)

# 3. 呼叫 LLM 生成回答
response = await llm_client.get_chat_completion(
    messages=messages,
    temperature=0.7
)

answer = response['choices'][0]['message']['content']
```

### Prompt 結構

```
┌────────────────────────────────────────────────────────────────┐
│                      RAG Prompt Structure                       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  [System Prompt]                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ 你是一位專業的文檔問答助手。                              │ │
│  │                                                          │ │
│  │ **核心原則：下方的「上下文」來自用戶勾選的文檔**          │ │
│  │                                                          │ │
│  │ ---                                                      │ │
│  │ [用戶勾選的文檔內容]                                     │ │
│  │ {context}  ← 檢索到的文檔片段                            │ │
│  │ ---                                                      │ │
│  │                                                          │ │
│  │ 回答策略：                                               │ │
│  │ 1. 直接使用上方文檔                                      │ │
│  │ 2. 優先引用文檔                                          │ │
│  │ 3. 智能補充說明                                          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  [User Message]                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ 什麼是大語言模型的訓練過程？                             │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 比喻說明

> **專業顧問的工作室** 👨‍��
>
> LLM 生成就像一位專業顧問在工作室裡整理答案。
>
> 1. **收到資料包**：機器人送來的相關頁面（context_results）被整理成一份「參考資料包」
>
> 2. **標註來源**：每份資料都被標上出處（例如「民法-第42頁」），
>    就像學術論文的引用標註
>
> 3. **撰寫報告**：顧問（LLM）閱讀所有資料，用自然語言撰寫一份
>    有條理的回答，並在適當位置標明資料來源
>
> 4. **品質把關**：顧問遵循一套嚴格的規則：
>    - 不編造資料中沒有的內容
>    - 明確區分「文檔內容」和「補充說明」
>    - 不會開頭就說「找不到」

---

## 階段 5：結果回傳與前端渲染 (Response & Rendering)

### 檔案位置
- `app/api/v1/endpoints/skills.py` (Lines 586-600)
- `template/skill_main.html` (Lines 2591-2720)

### API 回應格式

```json
{
    "skill_id": "skill_20251126_xxx",
    "skill_ids": ["skill_20251126_xxx", "skill_20251127_yyy"],
    "answer": "大語言模型的訓練過程分為三個主要階段...\n\n參考來源：\n[LLM_Handbook-第42頁]\n[ML_Guide-第18頁]",
    "query": "什麼是大語言模型的訓練過程？",
    "documents_searched": 2,
    "results": [
        {
            "content": "Pre-training 是 LLM 訓練的第一階段...",
            "score": 0.234,
            "metadata": {
                "document_name": "LLM_Handbook",
                "page_number": 42
            },
            "citation": "[LLM_Handbook-第42頁]",
            "source_name": "LLM_Handbook"
        }
    ]
}
```

### 前端渲染流程

```javascript
// skill_main.html Line 2630-2700
async function sendTraditionalQuery(query) {
    // 1. 發送 API 請求
    const response = await fetch('/api/v1/skills/demo/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            skill_ids: selectedSkills.map(s => s.id),
            query: query,
            top_k: 10
        })
    });

    const data = await response.json();

    // 2. 顯示使用者問題
    addMessage(query, 'user');

    // 3. 渲染 AI 回答（Markdown 格式）
    addMessage(data.answer, 'ai');

    // 4. 顯示搜尋統計
    updateFooter(`📚 搜尋了 ${data.documents_searched} 個知識庫`);
}
```

### 比喻說明

> **讀者服務台的回覆** 📬
>
> 最終階段就像服務台把整理好的答案交給讀者。
>
> 1. **包裝答案**：後端把顧問的報告、參考來源、搜尋統計打包成 JSON
>
> 2. **送達前台**：瀏覽器收到這個「答案包裹」
>
> 3. **展示結果**：
>    - 使用者的問題顯示在對話框上方
>    - AI 的回答以 Markdown 格式呈現（支援粗體、列表、程式碼區塊）
>    - 底部顯示「搜尋了 N 個知識庫」

---

## 完整流程時序圖

```
┌─────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐      ┌─────────┐
│ Browser │      │ FastAPI  │      │ Metadata │      │  FAISS   │      │  LLM    │
│         │      │ Endpoint │      │ Provider │      │ Provider │      │ Client  │
└────┬────┘      └────┬─────┘      └────┬─────┘      └────┬─────┘      └────┬────┘
     │                │                 │                 │                 │
     │ POST /demo/query                 │                 │                 │
     │ {skill_ids, query}               │                 │                 │
     │ ──────────────>│                 │                 │                 │
     │                │                 │                 │                 │
     │                │ list_skills()   │                 │                 │
     │                │ ───────────────>│                 │                 │
     │                │                 │                 │                 │
     │                │ <───────────────│                 │                 │
     │                │ valid_skill_ids │                 │                 │
     │                │                 │                 │                 │
     │                │ similarity_search(query, skill_ids)                 │
     │                │ ──────────────────────────────────>│                 │
     │                │                 │                 │                 │
     │                │ <──────────────────────────────────│                 │
     │                │ context_results (chunks + scores)  │                 │
     │                │                 │                 │                 │
     │                │ build_rag_prompt(query, context)   │                 │
     │                │ ────────────────────────────────────────────────────>│
     │                │                 │                 │                 │
     │                │ <────────────────────────────────────────────────────│
     │                │                 │                 │         answer  │
     │                │                 │                 │                 │
     │ <──────────────│                 │                 │                 │
     │ {answer, results, citations}     │                 │                 │
     │                │                 │                 │                 │
     ▼                ▼                 ▼                 ▼                 ▼
```

---

## Progressive Streaming 模式（OPMP）

除了傳統 JSON 模式，系統還支援 Progressive Streaming（漸進式串流）模式，提供更好的使用者體驗。

### 5 階段架構

```
┌─────────────────────────────────────────────────────────────────┐
│              Progressive Skill Streaming (OPMP)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Phase 1: Query Understanding      (5%)   ← 問題理解與擴展      │
│         │                                                       │
│         ▼                                                       │
│  Phase 2: Parallel Retrieval      (25%)   ← 並行向量檢索        │
│         │                                                       │
│         ▼                                                       │
│  Phase 3: Context Assembly        (10%)   ← 上下文組裝          │
│         │                                                       │
│         ▼                                                       │
│  Phase 4: Response Generation     (55%)   ← Token-by-Token 串流 │
│         │                                                       │
│         ▼                                                       │
│  Phase 5: Post Processing          (5%)   ← 後處理與記錄        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 檔案位置

| Phase | 檔案 |
|-------|------|
| Phase 1 | `app/SkillServices/progressive_skill_streaming/phase1_skill_query_understanding.py` |
| Phase 2 | `app/SkillServices/progressive_skill_streaming/phase2_skill_retrieval.py` |
| Phase 3 | `app/SkillServices/progressive_skill_streaming/phase3_context_assembly.py` |
| Phase 4 | `app/SkillServices/progressive_skill_streaming/phase4_response_generation.py` |
| Phase 5 | `app/SkillServices/progressive_skill_streaming/phase5_postprocessing.py` |
| 協調器 | `app/SkillServices/progressive_skill_streaming/progressive_streaming.py` |

### SSE 事件格式

```
event: phase_start
data: {"phase": 1, "name": "Query Understanding", "progress": 0}

event: token
data: {"content": "大", "phase": 4}

event: token
data: {"content": "語言", "phase": 4}

event: complete
data: {"phase": 5, "total_time": 3.45}
```

---

## 關鍵函數索引

| 階段 | 函數 | 檔案:行號 |
|------|------|-----------|
| 前端入口 | `sendQuery()` | `skill_main.html:2461` |
| API 端點 | `query_demo_skill()` | `skills.py:367` |
| 向量檢索 | `retrieve_context()` | `skill_retrieval_service.py:81` |
| Prompt 組裝 | `build_rag_prompt()` | `prompt_service.py:90` |
| LLM 呼叫 | `get_chat_completion()` | `llm_provider/client.py` |
| 前端渲染 | `addMessage()` | `skill_main.html:2680` |

---

## 效能考量

### 並行搜尋優化

```python
# skills.py Line 436-459
if len(content_ids) > 1:
    # 並行檢索多個文檔
    tasks = []
    for doc_id in content_ids[:10]:
        task = retrieval_service.retrieve_context(
            query=query,
            content_ids=[doc_id],
            top_k=3  # 每文檔取 3 個
        )
        tasks.append(task)

    # 並行執行
    all_results = await asyncio.gather(*tasks)
```

### 快取策略

- **Embedding 快取**：相同查詢的向量嵌入可被 Redis 快取
- **FAISS 索引**：啟動時自動載入到記憶體
- **SQLite WAL**：啟用 Write-Ahead Logging 提升並發性能

---

*文件版本：2025-12-16*
*作者：Claude (SuperClaude)*
