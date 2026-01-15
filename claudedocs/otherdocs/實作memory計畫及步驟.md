<!-- claudedocs/實作memory計畫及步驟.md -->
# Skill-Based Multi-Turn Chat Memory 實作計畫

**建立日期**: 2025-12-22
**狀態**: 待實作
**預計時間**: 約 2 小時

---

## 1. 需求確認

| 項目 | 決定 |
|------|------|
| **目標系統** | Skill-Based (主系統，File-Based 已棄用) |
| **記憶範圍** | 最近 10 條訊息，滑動窗口 |
| **儲存後端** | MongoDB (重用現有 ChatHistoryProvider) |
| **對話隔離** | 用戶 + Skill (`user_id` + `skill_id`) |
| **實作策略** | 重用 MongoDB ChatHistoryProvider (複雜度低) |

---

## 2. 現狀分析

### 2.1 現有架構

| 系統 | 對話記憶 | 儲存 | Multi-Turn |
|------|---------|------|------------|
| **File-Based (OPMP)** | ✅ 完整支援 | MongoDB | ✅ 最近 10 條訊息傳遞給 LLM |
| **Skill-Based (當前)** | ❌ 僅前端 | localStorage | ❌ 每次查詢獨立，無上下文 |

### 2.2 現有 ChatHistoryProvider 功能

**位置**: `app/Providers/chat_history_provider/client.py` (513 lines)

**主要方法**:
- `create_session(session_id, user_id, file_ids, metadata)` - 建立對話 session
- `session_exists(session_id)` - 檢查 session 是否存在
- `add_message(session_id, role, content, metadata)` - 新增訊息
- `get_chat_history(session_id, limit)` - 獲取對話歷史 (滑動窗口)
- `delete_session(session_id)` - 刪除 session

**MongoDB Schema**:
```javascript
{
    "_id": ObjectId,
    "session_id": str,           // 唯一索引
    "user_id": str,              // 用戶 ID
    "file_ids": List[str],       // 關聯的檔案/技能
    "created_at": datetime,
    "updated_at": datetime,
    "messages": [
        {
            "role": "user" | "assistant" | "system",
            "content": str,
            "timestamp": datetime,
            "metadata": dict
        }
    ],
    "metadata": dict
}
```

---

## 3. Session ID 設計

### 3.1 命名規則

```
session_id = f"skill_{user_id}_{skill_id}"
```

**範例**:
```
skill_user123_skill_20251203_094135_d01fd9b0
```

### 3.2 設計理由

- **唯一性**: 每個用戶對每個 Skill 有獨立的對話記憶
- **可追蹤**: 從 session_id 可直接識別用戶和 Skill
- **相容性**: 與現有 MongoDB schema 相容

---

## 4. 修改計畫

### Step 1: 修改 Skill Query Request Model

**檔案**: `app/api/v1/endpoints/skills.py`

**變更內容**: 新增參數到 Request Model

```python
class SkillQueryRequest(BaseModel):
    """Skill 查詢請求 - 支援 Multi-Turn 對話"""

    # 現有參數
    skill_id: Optional[str] = None
    skill_ids: Optional[List[str]] = None
    query: str
    top_k: int = 10

    # 新增參數 - Multi-Turn 支援
    user_id: Optional[str] = Field(
        default=None,
        description="用戶 ID，用於對話隔離"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID，可選。若未提供則自動生成"
    )
    include_history: bool = Field(
        default=True,
        description="是否包含對話歷史"
    )
    history_limit: int = Field(
        default=10,
        description="滑動窗口大小，預設 10 條訊息"
    )
```

---

### Step 2: 修改 Demo Query Endpoint

**檔案**: `app/api/v1/endpoints/skills.py`

**變更內容**: 整合 ChatHistoryProvider

```python
from app.Providers.chat_history_provider import get_chat_history_provider, ChatHistoryProvider

@router.post("/demo/query")
async def query_skill_demo(
    request: SkillQueryRequest,
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider)
):
    """
    Skill 查詢 - 支援 Multi-Turn 對話記憶
    """

    # ========================================
    # 1. 決定 skill_id 和 user_id
    # ========================================
    skill_id = request.skill_id or (request.skill_ids[0] if request.skill_ids else None)
    user_id = request.user_id or settings.DEFAULT_USER_ID

    # ========================================
    # 2. 生成或使用 session_id
    # ========================================
    session_id = request.session_id or f"skill_{user_id}_{skill_id}"

    # ========================================
    # 3. 確保 session 存在 (首次對話時建立)
    # ========================================
    if not await chat_history_provider.session_exists(session_id):
        await chat_history_provider.create_session(
            session_id=session_id,
            user_id=user_id,
            file_ids=[skill_id],  # 使用 skill_id 作為關聯
            metadata={
                "type": "skill_chat",
                "skill_id": skill_id,
                "skill_ids": request.skill_ids or [skill_id]
            }
        )
        logger.info(f"Created new chat session: {session_id}")

    # ========================================
    # 4. 獲取對話歷史 (滑動窗口)
    # ========================================
    chat_history = []
    if request.include_history:
        chat_history = await chat_history_provider.get_chat_history(
            session_id=session_id,
            limit=request.history_limit  # 預設 10 條
        )
        logger.info(f"Retrieved {len(chat_history)} messages from history")

    # ========================================
    # 5. Vector Retrieval (現有邏輯)
    # ========================================
    # ... 現有的 FAISS 檢索邏輯 ...
    context_chunks = [...]  # 檢索結果

    # ========================================
    # 6. 建立帶歷史的 Prompt
    # ========================================
    from app.Services.prompt_service import build_rag_prompt

    messages = build_rag_prompt(
        query=request.query,
        context_chunks=context_chunks,
        chat_history=chat_history,  # 傳入對話歷史
        language="zh"
    )

    # ========================================
    # 7. 調用 LLM (使用 Singleton Manager)
    # ========================================
    from app.Providers.llm_provider.manager import get_llm_manager

    llm_manager = get_llm_manager()
    llm_client = await llm_manager.get_client()

    response = await llm_client.get_chat_completion(
        messages=messages,
        temperature=0.3
    )

    answer = response["choices"][0]["message"]["content"]

    # ========================================
    # 8. 保存對話到 MongoDB
    # ========================================
    # 保存用戶訊息
    await chat_history_provider.add_message(
        session_id=session_id,
        role="user",
        content=request.query,
        metadata={
            "skill_id": skill_id,
            "top_k": request.top_k
        }
    )

    # 保存助手回應
    await chat_history_provider.add_message(
        session_id=session_id,
        role="assistant",
        content=answer,
        metadata={
            "sources_count": len(context_chunks),
            "model": llm_manager.current_model
        }
    )

    logger.info(f"Saved conversation to session: {session_id}")

    # ========================================
    # 9. 返回結果 (包含 session_id)
    # ========================================
    return {
        "answer": answer,
        "session_id": session_id,  # 返回 session_id 供前端使用
        "results": [...],  # citations
        "search_mode": "single" if request.skill_id else "multi",
        "documents_searched": len(context_chunks)
    }
```

---

### Step 3: 確認 Prompt Service

**檔案**: `app/Services/prompt_service.py`

**確認內容**: 確保 `build_rag_prompt()` 正確處理 `chat_history` 參數

```python
def build_rag_prompt(
    query: str,
    context_chunks: List[str],
    chat_history: Optional[List[Dict[str, str]]] = None,
    language: str = "zh",
    is_summary: bool = False
) -> List[Dict[str, str]]:
    """
    建立 RAG Prompt

    訊息順序：
    1. System prompt (包含 RAG context)
    2. Chat history (滑動窗口，最近 N 條)
    3. Current user query
    """

    messages = []

    # 1. System prompt
    system_content = f"""你是一個專業的文件問答助手...

    以下是相關文件內容：
    {format_context(context_chunks)}
    """
    messages.append({"role": "system", "content": system_content})

    # 2. Chat history (如果有)
    if chat_history:
        messages.extend(chat_history)

    # 3. Current user query
    messages.append({"role": "user", "content": query})

    return messages
```

---

### Step 4: 新增 Session 管理 API (可選)

**檔案**: `app/api/v1/endpoints/skills.py`

**新增 Endpoints**:

```python
# ========================================
# Session 管理 API
# ========================================

@router.get("/sessions")
async def list_user_sessions(
    user_id: str,
    limit: int = 20,
    skip: int = 0,
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider)
):
    """
    獲取用戶的所有 Skill 對話列表
    """
    sessions = await chat_history_provider.list_user_sessions(
        user_id=user_id,
        limit=limit,
        skip=skip
    )
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    limit: Optional[int] = None,
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider)
):
    """
    獲取特定對話的歷史訊息
    """
    messages = await chat_history_provider.get_messages(
        session_id=session_id,
        limit=limit
    )
    return {"session_id": session_id, "messages": messages}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider)
):
    """
    清除特定對話歷史
    """
    success = await chat_history_provider.delete_session(session_id)
    return {"success": success, "session_id": session_id}


@router.delete("/sessions/user/{user_id}")
async def delete_user_sessions(
    user_id: str,
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider)
):
    """
    清除用戶的所有對話歷史
    """
    deleted_count = await chat_history_provider.delete_user_sessions(user_id)
    return {"success": True, "deleted_count": deleted_count}
```

---

## 5. 預計修改的檔案清單

| 檔案 | 變更類型 | 說明 | 預計行數 |
|------|---------|------|---------|
| `app/api/v1/endpoints/skills.py` | 修改 | 整合 ChatHistoryProvider，新增 Session API | +80-100 lines |
| `app/Services/prompt_service.py` | 確認/微調 | 確認 chat_history 處理邏輯 | +5-10 lines |

---

## 6. 對話流程圖

```
┌─────────────────────────────────────────────────────────────┐
│                     User Query                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Session 管理                                        │
│  ├─ 生成 session_id: skill_{user_id}_{skill_id}             │
│  ├─ 檢查 session 是否存在                                    │
│  └─ 若不存在則建立新 session (MongoDB)                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 2: 獲取對話歷史                                        │
│  ├─ 從 MongoDB 獲取最近 10 條訊息                            │
│  └─ 滑動窗口機制                                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 3: Vector Retrieval                                    │
│  ├─ FAISS 向量檢索                                          │
│  └─ 獲取相關 context chunks                                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 4: 建立 Prompt                                         │
│  ├─ [System Prompt + RAG Context]                           │
│  ├─ [Chat History - 10 messages]  ← 滑動窗口                 │
│  └─ [Current User Query]                                    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 5: LLM Generation                                      │
│  ├─ 使用 LLM Manager Singleton                              │
│  └─ 生成帶上下文的回應                                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 6: 保存對話                                            │
│  ├─ 保存 user message 到 MongoDB                            │
│  └─ 保存 assistant response 到 MongoDB                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Response: {answer, session_id, results, ...}                │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. 測試計畫

### 7.1 curl 測試命令

```bash
# ========================================
# 測試 1: 第一輪對話 (建立 session)
# ========================================
curl -X POST http://localhost:8082/api/v1/skills/demo/query \
  -H "Content-Type: application/json" \
  -d '{
    "skill_id": "skill_20251203_094135_d01fd9b0",
    "query": "什麼是機器學習？",
    "user_id": "user123",
    "include_history": true
  }'

# 預期回應包含 session_id


# ========================================
# 測試 2: 第二輪對話 (LLM 應記住上一輪)
# ========================================
curl -X POST http://localhost:8082/api/v1/skills/demo/query \
  -H "Content-Type: application/json" \
  -d '{
    "skill_id": "skill_20251203_094135_d01fd9b0",
    "query": "請給我一個具體的例子",
    "user_id": "user123"
  }'

# 預期: LLM 知道是在問機器學習的例子


# ========================================
# 測試 3: 第三輪對話 (持續上下文)
# ========================================
curl -X POST http://localhost:8082/api/v1/skills/demo/query \
  -H "Content-Type: application/json" \
  -d '{
    "skill_id": "skill_20251203_094135_d01fd9b0",
    "query": "這個例子可以應用在哪些領域？",
    "user_id": "user123"
  }'

# 預期: LLM 記住之前討論的機器學習例子


# ========================================
# 測試 4: 查看對話歷史
# ========================================
curl "http://localhost:8082/api/v1/skills/sessions/skill_user123_skill_20251203_094135_d01fd9b0/messages"


# ========================================
# 測試 5: 列出用戶所有對話
# ========================================
curl "http://localhost:8082/api/v1/skills/sessions?user_id=user123"


# ========================================
# 測試 6: 清除對話歷史
# ========================================
curl -X DELETE "http://localhost:8082/api/v1/skills/sessions/skill_user123_skill_20251203_094135_d01fd9b0"
```

### 7.2 驗證要點

| 測試項目 | 驗證方法 |
|---------|---------|
| Session 建立 | 檢查 MongoDB 是否有新 document |
| 對話記憶 | 第二輪問「請給我例子」時，LLM 知道是問什麼的例子 |
| 滑動窗口 | 超過 10 條後，舊訊息不影響新對話 |
| 用戶隔離 | 不同 user_id 有獨立對話 |
| Skill 隔離 | 同一用戶不同 Skill 有獨立對話 |

---

## 8. 時間估計

| 步驟 | 預計時間 |
|------|---------|
| Step 1: 修改 Request Model | 15 分鐘 |
| Step 2: 修改 Demo Query Endpoint | 45-60 分鐘 |
| Step 3: 確認 Prompt Service | 15 分鐘 |
| Step 4: 新增 Session 管理 API | 30 分鐘 |
| 測試與調試 | 30 分鐘 |
| **總計** | **約 2-2.5 小時** |

---

## 9. 注意事項

### 9.1 MongoDB 連線

確保 MongoDB 服務運行中：
```bash
# 檢查 MongoDB 狀態
systemctl status mongod

# 或使用 Docker
docker ps | grep mongo
```

### 9.2 向後相容

- 新增參數都有預設值，現有 API 調用不受影響
- `user_id` 預設使用 `settings.DEFAULT_USER_ID`
- `include_history` 預設為 `True`

### 9.3 Token 限制考量

- 滑動窗口設為 10 條，避免超出 LLM token 限制
- 每條訊息平均 100-200 tokens，10 條約 1000-2000 tokens
- 加上 RAG context 和 system prompt，總計約 3000-5000 tokens

---

## 10. 後續優化方向 (Post-Implementation)

| 優化項目 | 說明 | 優先級 |
|---------|------|-------|
| 摘要式記憶 | 壓縮舊對話成摘要，支援更長歷史 | P2 |
| 對話匯出 | 支援匯出為 Markdown/JSON | P3 |
| 對話搜尋 | 搜尋歷史對話內容 | P3 |
| 分析統計 | 對話使用統計和分析 | P4 |

---

*文件建立: 2025-12-22*
*最後更新: 2025-12-22*
*狀態: 待用戶確認後實作*
