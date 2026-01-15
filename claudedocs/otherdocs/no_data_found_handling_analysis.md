# 「找不到資料」處理機制分析報告

## 概述

本文檔分析 DocAI 系統在「真的找不到相關資料」時的多層處理機制，以及如何區分「有資料但回答錯誤」vs「真的沒有資料」。

---

## 多層處理機制

### 🔍 Level 1: Vector 檢索層（FAISS）

**位置**: `app/SkillServices/skill_retrieval_service.py`

**職責**: 向量相似度搜尋

```python
context_results = await retrieval_service.retrieve_context(
    query=query,
    content_ids=[skill_id],
    top_k=10,
    include_scores=True
)
```

**可能結果**:
1. ✅ **找到結果**: `context_results` 包含相關的 chunks（可能 1-10 筆）
2. ❌ **找不到結果**: `context_results = []`（空列表）
3. ⚠️ **低相關度結果**: `context_results` 有資料但 scores 很差（例如 > 0.8）

---

### 📝 Level 2: Context 組裝層（PromptService）

**位置**: `app/Services/prompt_service.py:286-303`

**職責**: 檢查 chunks 是否為空，並組裝成 LLM 可用的 context

```python
def _assemble_context(self, context_chunks: List[str]) -> str:
    if not context_chunks:
        return "[無可用上下文]" if self.language == "zh" else "[No context available]"

    # Join chunks with clear separators
    context_str = "\n\n".join(context_chunks)
    return context_str
```

**處理邏輯**:
- **情境 1**: `context_chunks` 為空 → 返回 `[無可用上下文]`
- **情境 2**: `context_chunks` 有內容 → 組裝成完整 context 字串

**傳給 LLM 的內容**:
```
---
[用戶勾選的文檔內容]
[無可用上下文]
---
```
或
```
---
[用戶勾選的文檔內容]
Chunk 1 內容...

Chunk 2 內容...
---
```

---

### 🤖 Level 3: LLM 判斷層（System Prompt）

**位置**: `app/Services/prompt_service.py:42-55`

**職責**: 引導 LLM 正確判斷和回答

**系統提示詞**:
```
回答策略：
1. **直接使用上方文檔**：上方文檔內容已經存在，請直接引用和分析，不要質疑文檔是否存在
2. **優先引用文檔**：回答時應優先使用上方上下文中的信息，並明確標註引用來源
3. **智能補充說明**：當需要補充背景知識或專業解釋時，可以使用你的知識，但要明確區分：
   - 文檔內容：「根據您的文檔...」、「文檔中提到...」
   - 補充說明：「補充說明...」、「相關背景...」
4. **準確性優先**：不要編造文檔中不存在的內容
5. **重要：不要開頭就說「找不到」**：
   - ❌ 錯誤示範：「在您的文檔中，我沒有找到...（但實際內容如下）」
   - ✅ 正確做法：如果上方文檔有相關內容，直接回答問題並引用來源
   - 只有在上方文檔真的完全沒有任何相關資訊時，才說明找不到
```

**LLM 判斷邏輯**:

#### 情境 A: Context = `[無可用上下文]`
LLM 看到：
```
[用戶勾選的文檔內容]
[無可用上下文]
---

用戶問題：請說明 XXX
```

**預期回答**:
```
抱歉，在您選擇的知識庫中，我沒有找到關於「XXX」的相關資訊。

建議：
1. 請確認是否選擇了正確的知識庫
2. 嘗試調整問題的表達方式
3. 如果這是新的主題，可能需要上傳相關文檔
```

#### 情境 B: Context 有內容但不相關
LLM 看到：
```
[用戶勾選的文檔內容]
Chunk 1: 民法第一條規定...
Chunk 2: 刑法總則說明...
---

用戶問題：請說明 LLM 訓練階段
```

**預期回答**:
```
在您選擇的知識庫中，我沒有找到關於 LLM 訓練階段的相關資訊。

目前提供的文檔主要涉及法律相關內容（民法、刑法），而不包含大型語言模型訓練的技術說明。

建議選擇包含 AI/機器學習相關內容的知識庫。
```

#### 情境 C: Context 有相關內容
LLM 看到：
```
[用戶勾選的文檔內容]
Chunk 1: LLM 訓練分為三個階段：預訓練、監督微調、強化學習...
Chunk 2: 預訓練階段使用大規模無標註語料...
---

用戶問題：請說明 LLM 訓練階段
```

**預期回答**:
```
根據您的文檔，LLM 訓練分為三個主要階段：

1. **預訓練階段（Pre-training）**
   使用大規模無標註語料進行訓練...

2. **監督微調階段（Supervised Fine-tuning）**
   ...

3. **強化學習階段（RLHF）**
   ...

（來源：LLM 訓練文檔）
```

---

### 🎯 Level 4: API 錯誤處理層

**位置**: `app/api/v1/endpoints/skills.py:212-328`

**職責**: API 級別的異常處理

**檢查點 1**: Skill 是否存在
```python
mappings = await metadata_provider.get_documents_for_skill(skill_id)

if not mappings:
    raise HTTPException(status_code=404, detail=f"No documents found for skill {skill_id}")
```

**檢查點 2**: 向量檢索異常處理
```python
try:
    context_results = await retrieval_service.retrieve_context(...)
except Exception as e:
    logger.error(f"Error in demo skill query: {str(e)}")
    raise HTTPException(status_code=500, detail=str(e))
```

**前端錯誤處理**（`template/skill_main.html:926-928`）:
```javascript
if (response.ok) {
    addMessage(result.answer || '找到相關內容', 'assistant', result.results);
} else {
    console.error('Query error:', result.detail);
    addMessage('😔 目前找不到相關資料，請稍後再試或聯繫工程師協助處理。', 'assistant');
}
```

---

## 完整流程圖

```
用戶提問: "請說明 XXX"
    ↓
┌─────────────────────────────────────────┐
│ Level 1: Vector Retrieval (FAISS)      │
│ retrieval_service.retrieve_context()   │
└─────────────────────────────────────────┘
    ↓
    ├─→ [情境 1] context_results = []
    │   ↓
    │   Level 2: PromptService
    │   返回: "[無可用上下文]"
    │   ↓
    │   Level 3: LLM 判斷
    │   回答: "在您選擇的知識庫中，我沒有找到..."
    │
    ├─→ [情境 2] context_results 有內容但不相關
    │   ↓
    │   Level 2: PromptService
    │   組裝: 不相關的 chunks
    │   ↓
    │   Level 3: LLM 判斷
    │   分析: chunks 內容與問題不匹配
    │   回答: "在您選擇的知識庫中，我沒有找到相關資訊"
    │
    └─→ [情境 3] context_results 有相關內容
        ↓
        Level 2: PromptService
        組裝: 相關的 chunks
        ↓
        Level 3: LLM 判斷
        分析: chunks 包含答案
        回答: "根據您的文檔，XXX..."（直接回答，不說「找不到」）
```

---

## 關鍵設計原則

### 1. **分層責任**
- **Vector 層**: 純技術檢索，不做語義判斷
- **Context 層**: 檢查空值，組裝格式
- **LLM 層**: 語義理解和判斷相關性
- **API 層**: 異常捕獲和用戶友好錯誤訊息

### 2. **信任 Vector 檢索結果**
系統假設 FAISS 返回的結果已經是「最相關」的，即使相關度不高。LLM 負責最終判斷是否真的相關。

### 3. **明確區分來源**
- 文檔內容: `「根據您的文檔...」`
- 補充說明: `「補充說明...」`
- 找不到: `「在您選擇的知識庫中，我沒有找到...」`

### 4. **避免誤判**
修改後的 prompt（2025-11-26）明確要求：
- ❌ 不要在有內容時說「找不到」
- ✅ 只有真的沒有相關資訊時才說「找不到」

---

## 實際範例分析

### 範例 1: 完全沒有相關文檔

**用戶操作**: 選擇「民法」知識庫
**用戶問題**: 「請說明 Python asyncio 的工作原理」

**系統處理**:
1. FAISS 檢索: 在民法文檔中搜尋 "Python asyncio"
2. 結果: 相關度極低的 chunks（可能包含「原理」等通用詞）
3. LLM 分析: chunks 都是民法條文，與 Python 完全無關
4. 回答:
```
在您選擇的知識庫（民法）中，我沒有找到關於 Python asyncio 的相關資訊。

目前的文檔主要涵蓋民法相關內容，如果您需要了解 Python 程式設計，
建議選擇包含程式設計或技術文檔的知識庫。
```

### 範例 2: 部分相關但不足以回答

**用戶操作**: 選擇「LLM 基礎」知識庫
**用戶問題**: 「請說明 GPT-4 的具體參數量和訓練成本」

**系統處理**:
1. FAISS 檢索: 找到關於 LLM 參數和訓練的一般性說明
2. 結果: 有 chunks 提到「參數量」「訓練成本」但沒有 GPT-4 的具體數據
3. LLM 分析: 文檔有相關概念但缺少具體信息
4. 回答:
```
根據您的文檔，我找到了關於 LLM 參數量和訓練成本的一般性說明：

【文檔內容】
- 大型語言模型通常有數十億到數千億參數
- 訓練成本與參數量成正比，通常需要...

【補充說明】
關於 GPT-4 的具體參數量，OpenAI 官方並未公開詳細數據。
您的文檔中沒有提供 GPT-4 的具體訓練成本資訊。
```

### 範例 3: 有充分相關內容

**用戶操作**: 選擇「LLM 訓練」知識庫
**用戶問題**: 「請說明 LLM 訓練分成哪幾個階段」

**系統處理**:
1. FAISS 檢索: 找到多個高相關度 chunks
2. 結果: chunks 詳細描述了訓練階段
3. LLM 分析: 文檔內容充分，可直接回答
4. 回答:
```
根據您的文檔，LLM 訓練主要分為以下三個階段：

1. **預訓練階段（Pre-training）**
   使用大規模無標註語料進行自監督學習...

2. **監督微調階段（Supervised Fine-tuning, SFT）**
   使用人工標註的高質量問答對進行訓練...

3. **強化學習人類反饋階段（RLHF）**
   通過人類反饋優化模型行為...

（來源：LLM 訓練文檔-第 3-5 頁）
```

---

## 改進建議（Post-Demo）

### 1. **向量相似度閾值過濾**
```python
# 在 retrieval_service 中增加分數過濾
RELEVANCE_THRESHOLD = 0.7  # 相似度低於此值視為不相關

filtered_results = [
    r for r in context_results
    if r.get('score', 1.0) < RELEVANCE_THRESHOLD
]

if not filtered_results:
    # 觸發「找不到相關資料」流程
    context_chunks = []
```

### 2. **前端相關度指示器**
在前端顯示檢索結果的相關度：
```javascript
// 在 addMessage 函數中
if (sources && sources.length > 0) {
    sources.forEach(s => {
        const relevance = (1 - s.score) * 100;
        const relevanceClass = relevance > 70 ? 'high' : relevance > 50 ? 'medium' : 'low';

        html += `
            <div class="source-item ${relevanceClass}">
                <span class="relevance-badge">${relevance.toFixed(0)}% 相關</span>
                <strong>${filename}</strong>
            </div>
        `;
    });
}
```

### 3. **智能建議系統**
當找不到資料時，提供智能建議：
```python
def suggest_alternatives(query: str, available_skills: List[str]) -> List[str]:
    """根據問題內容，推薦可能相關的知識庫"""
    # 使用簡單的關鍵字匹配或 embedding 相似度
    suggestions = []

    keywords_map = {
        "LLM|AI|機器學習": ["LLM基礎", "深度學習"],
        "民法|刑法|法律": ["六法全書"],
        "Python|程式": ["程式設計指南"]
    }

    for pattern, skills in keywords_map.items():
        if re.search(pattern, query):
            suggestions.extend(skills)

    return suggestions
```

---

## 總結

### 當前機制 ✅

1. **多層防護**: Vector → Context → LLM → API 四層處理
2. **明確提示**: 修改後的 prompt 明確要求 LLM 區分情境
3. **用戶友好**: API 錯誤時返回友好訊息而非技術細節

### 預期行為 🎯

- **有資料**: 直接回答，引用來源，不說「找不到」
- **無資料**: 明確說明找不到，提供建議，不編造內容
- **部分資料**: 回答已有內容，明確標示缺少的部分

### 改進方向 🚀

- 增加相似度閾值過濾（Post-Demo）
- 前端相關度可視化（Post-Demo）
- 智能知識庫推薦（Post-Demo）

---

*分析完成時間: 2025-11-26*
*相關修復: prompt_response_fix_20251126.md*
