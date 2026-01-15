# Skill 隔離與 Memory 功能實作文件

**建立日期**: 2025-12-24
**狀態**: 已完成
**相關計畫檔**: `/home/mapleleaf/.claude/plans/moonlit-spinning-rocket.md`

---

## 問題摘要

### Bug: 跨 Skill 數據洩漏

**症狀**: 在 "AMD" skill 查詢後，切換到 "大語言模型大全" skill，回應中仍顯示 AMD 內容

**根因**: 前端 `preservedMessagesHtml` 邏輯在切換 skill 時重新添加**所有**舊訊息（不只是 think indicator，還包括檢索結果）

### 需求: Memory 功能

**目標**: 實作 Multi-Turn 對話記憶，讓 LLM 能理解上下文

**方案**: 整合現有 MongoDB `ChatHistoryProvider` + localStorage 前端儲存

---

## 核心原則

> **「在不同的 skill，只能出現被選擇的 skill 的文件資料的內容」**

---

## 實作步驟詳解

### Step 0: 建立 Users Table (SQLite)

**目的**: 提供共用的 `user_id` 給 Memory 功能使用

**檔案**: `data/skill_metadata.db`

**SQL 執行**:
```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,
    username TEXT DEFAULT 'default_user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_default BOOLEAN DEFAULT 0
);

INSERT OR IGNORE INTO users (user_id, username, is_default)
VALUES ('5a19a0da-7485-4656-8641-41402fef4049', 'default_user', 1);
```

**驗證**:
```sql
SELECT * FROM users;
-- 結果: 1|5a19a0da-7485-4656-8641-41402fef4049|default_user|2025-12-24 ...|1
```

---

### Step 1: 前端 Bug 修復 (Critical)

**檔案**: `template/skill_main.html`
**位置**: Lines 3341-3353

**問題代碼** (已移除):
```javascript
// 保留 think indicators 的邏輯會導致跨 skill 污染
const messagesWithThinkIndicators = ...
const preservedMessagesHtml = messagesWithThinkIndicators.map(msg => msg.outerHTML).join('');
// ... 清空 DOM ...
// 又把舊訊息加回去 ← BUG!
if (preservedMessagesHtml) {
    Array.from(tempDiv.children).forEach(msg => {
        chatMessages.appendChild(msg);  // 舊 skill 的訊息被加到新 skill!
    });
}
```

**修復後代碼**:
```javascript
// 4. 切換 skill 時完全清空 DOM（不保留任何舊訊息，確保 skill 隔離）
chatMessages.innerHTML = '';
chatMessages.style.paddingBottom = '50vh';

// 如果有載入的對話歷史，渲染它們
if (chatHistory.length > 0) {
    renderChatHistory();
    console.log(`📜 渲染完成: ${chatHistory.length} 條訊息`);
} else {
    console.log(`🆕 此 skill 無歷史對話`);
}

console.log('=== 切換完成 ===\n');
```

---

### Step 2: 後端整合 Memory

**檔案**: `app/api/v1/endpoints/skills.py`

#### 2.1 新增 Import (Lines 37-38)
```python
from app.Providers.chat_history_provider.client import ChatHistoryProvider, get_chat_history_provider
from app.core.config import settings
```

#### 2.2 修改 Endpoint 參數 (Lines 369-386)
```python
@router.post("/demo/query")
async def query_demo_skill(
    # 現有參數
    skill_id: str = Body(None, embed=False),
    skill_ids: List[str] = Body(None, embed=False),
    query: str = Body(..., embed=False),
    top_k: int = Body(10, embed=False),
    # 新增 Memory 參數
    user_id: Optional[str] = Body(None, embed=False),
    session_id: Optional[str] = Body(None, embed=False),
    include_history: bool = Body(True, embed=False),
    history_limit: int = Body(10, embed=False),
    # Dependencies
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
    retrieval_service: SkillRetrievalService = Depends(get_skill_retrieval_service),
    llm_client: LLMProviderClient = Depends(get_llm_provider),
    prompt_service: PromptService = Depends(get_prompt_service),
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider)
):
```

#### 2.3 Session 管理邏輯 (Lines 441-466)
```python
# Session ID 格式: skill_{user_id}_{primary_skill_id}
effective_user_id = user_id or settings.DEFAULT_USER_ID
primary_skill_id = skill_id or (valid_skill_ids[0] if valid_skill_ids else None)
effective_session_id = session_id or f"skill_{effective_user_id}_{primary_skill_id}"

# 確保 Session 存在
if not await chat_history_provider.session_exists(effective_session_id):
    await chat_history_provider.create_session(
        session_id=effective_session_id,
        user_id=effective_user_id,
        file_ids=[primary_skill_id] if primary_skill_id else [],
        metadata={"type": "skill_chat", "skill_id": primary_skill_id}
    )

# 獲取對話歷史
chat_history = []
if include_history:
    chat_history = await chat_history_provider.get_chat_history(
        session_id=effective_session_id,
        limit=history_limit
    )
```

#### 2.4 修改 Prompt 建構 (Line ~480)
```python
messages = prompt_service.build_rag_prompt(
    query=query,
    context_chunks=context_texts,
    chat_history=chat_history,  # 傳入對話歷史
    language="zh"
)
```

#### 2.5 保存對話 (返回前, Lines ~520-530)
```python
# 保存對話到 MongoDB
await chat_history_provider.add_message(
    session_id=effective_session_id,
    role="user",
    content=query,
    metadata={"skill_id": primary_skill_id}
)
await chat_history_provider.add_message(
    session_id=effective_session_id,
    role="assistant",
    content=answer,
    metadata={"sources_count": len(context_results)}
)
```

#### 2.6 返回值包含 session_id
```python
return {
    # 現有欄位...
    "session_id": effective_session_id  # 新增
}
```

---

### Step 3: 前端整合 Memory

**檔案**: `template/skill_main.html`

#### 3.1 新增 getCurrentUserId() (Lines 3861-3864)
```javascript
function getCurrentUserId() {
    return localStorage.getItem('docai_user_id') || '5a19a0da-7485-4656-8641-41402fef4049';
}
```

#### 3.2 修改 requestBody (Lines 3921-3932)
```javascript
const requestBody = {
    skill_id: skillIds.length === 1 ? skillIds[0] : null,
    skill_ids: skillIds.length > 1 ? skillIds : null,
    query: query,
    top_k: 10,
    // Memory parameters
    user_id: getCurrentUserId(),
    include_history: true,
    history_limit: 10
};
```

---

### Step 4: 100 組對話限制

**檔案**: `template/skill_main.html`
**位置**: Lines 2131-2150

**設計決策**:
- 1 組對話 = 1 user message + 1 assistant message = 2 條訊息
- 最多保留 100 組 = 200 條訊息
- 超過時自動裁剪最舊的對話
- 不需要 UI 顯示計數

**實作代碼**:
```javascript
// ===== 簡化版 Per-Skill Chat History (localStorage) =====
// 限制：最多保留 100 組對話（1 組 = user + assistant = 2 條訊息）
const MAX_CONVERSATION_PAIRS = 100;
const MAX_MESSAGES = MAX_CONVERSATION_PAIRS * 2;  // 200 條訊息

// 保存對話到 localStorage（使用 skill ID 作為 key）
function saveSkillChat(skillId, history) {
    if (!skillId || !history || history.length === 0) return;

    // 限制最新 100 組對話（保留最後 200 條訊息）
    let trimmedHistory = history;
    if (history.length > MAX_MESSAGES) {
        trimmedHistory = history.slice(-MAX_MESSAGES);
        console.log(`🧹 Trimmed: ${history.length} → ${trimmedHistory.length} messages (kept newest ${MAX_CONVERSATION_PAIRS} pairs)`);
    }

    const key = SKILL_CHAT_PREFIX + skillId;
    localStorage.setItem(key, JSON.stringify(trimmedHistory));
    console.log(`💾 Saved ${trimmedHistory.length} messages (${Math.floor(trimmedHistory.length/2)} pairs) to ${key}`);
}
```

---

## 修改檔案清單

| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| `data/skill_metadata.db` | 新增 | users table |
| `template/skill_main.html` | 修改 | 移除 preservedMessagesHtml 邏輯 |
| `template/skill_main.html` | 新增 | getCurrentUserId() 函數 |
| `template/skill_main.html` | 修改 | requestBody 加入 memory 參數 |
| `template/skill_main.html` | 修改 | saveSkillChat() 加入 100 組限制 |
| `app/api/v1/endpoints/skills.py` | 新增 | ChatHistoryProvider import |
| `app/api/v1/endpoints/skills.py` | 修改 | endpoint 參數 + session 管理 |
| `app/api/v1/endpoints/skills.py` | 新增 | 對話保存邏輯 |

---

## 隔離保證機制

| 層級 | 機制 | Key/ID 格式 |
|------|------|-------------|
| 前端 DOM | 切換時 `innerHTML = ''` | N/A |
| 前端 localStorage | Per-skill 儲存 | `docai_skill_chat_{skill_id}` |
| 後端 MongoDB | Session 隔離 | `skill_{user_id}_{skill_id}` |
| 後端 FAISS | skill_id 過濾 | 向量索引路徑包含 skill_id |

---

## 資料流程圖

```
┌─────────────────────────────────────────────────────────────────┐
│                        用戶發送查詢                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (skill_main.html)                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. 從 localStorage 載入當前 skill 的對話歷史            │   │
│  │ 2. 組裝 requestBody (含 user_id, include_history)       │   │
│  │ 3. POST /api/v1/skills/demo/query                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend (skills.py)                                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. 產生 effective_session_id                            │   │
│  │ 2. 從 MongoDB 載入最近 10 條對話 (chat_history)         │   │
│  │ 3. FAISS 向量檢索 (skill_id 過濾)                       │   │
│  │ 4. build_rag_prompt(query, context, chat_history)       │   │
│  │ 5. LLM 生成回答                                         │   │
│  │ 6. 保存 user + assistant 訊息到 MongoDB                 │   │
│  │ 7. 返回 answer + session_id                             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (skill_main.html)                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. 顯示回答                                              │   │
│  │ 2. 更新 chatHistory array                                │   │
│  │ 3. saveSkillChat() → localStorage (含 100 組限制)        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## localStorage vs Cookie 比較

| 特性 | localStorage | Cookie |
|------|-------------|--------|
| 容量 | 5-10 MB | 4 KB |
| 有效期 | 永久（除非手動清除） | 可設定過期時間 |
| HTTP 傳輸 | 不會自動發送 | 每次請求自動附帶 |
| 存取方式 | JavaScript 純前端 | 前端 + 後端都可存取 |
| 適用場景 | 大量前端資料暫存 | Session 管理、認證 Token |

**本次選擇 localStorage 原因**:
- 對話歷史可能很大（100 組 × 平均每條 500 字 ≈ 100KB）
- 不需要每次 HTTP 請求都傳送
- 純前端快速存取

---

## 測試驗證

### 測試 1: Skill 隔離
```
1. 選擇 "AMD" skill，查詢 "AMD 是什麼公司？"
2. 切換到 "大語言模型大全" skill
3. 確認：聊天區域清空，無 AMD 相關內容
4. 查詢 "什麼是 LLM？"
5. 確認：回答僅來自 LLM 相關文件
```

### 測試 2: Multi-Turn Memory
```
1. 選擇 "刑法" skill
2. 查詢 "什麼是刑法第一條？"
3. 查詢 "有什麼處罰？" （不指明主題）
4. 確認：LLM 理解上下文，回答刑法相關處罰
```

### 測試 3: 100 組限制
```
1. 在某 skill 累積超過 100 組對話
2. 檢查 localStorage 大小
3. 確認：只保留最新 200 條訊息
4. Console 顯示：🧹 Trimmed: 210 → 200 messages
```

---

## 後續優化建議

1. **MongoDB 同步機制**: 目前前端 localStorage 與後端 MongoDB 獨立運作，可考慮啟動時從 MongoDB 載入
2. **對話匯出功能**: 允許用戶匯出對話記錄
3. **對話搜尋功能**: 在歷史對話中搜尋關鍵字
4. **壓縮儲存**: 對 localStorage 資料進行壓縮以節省空間

---

## 相關檔案參考

- `app/Providers/chat_history_provider/client.py` - MongoDB 對話儲存 Provider
- `app/Services/prompt_service.py` - RAG Prompt 建構（含 chat_history 參數）
- `app/core/config.py` - DEFAULT_USER_ID 設定

---

*文件結束*
