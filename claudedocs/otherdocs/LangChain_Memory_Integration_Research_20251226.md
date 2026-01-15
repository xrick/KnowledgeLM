# LangChain Memory 組件整合研究

**研究日期**: 2025-12-26
**狀態**: 研究完成，暫不實作
**請求者**: 用戶 `/sc:design --type component`

---

## 研究目標

評估是否應整合 LangChain 的 Memory 組件來增強現有的 `ChatHistoryProvider`：
- ConversationBufferMemory
- ConversationBufferWindowMemory
- ConversationSummaryMemory
- VectorStoreRetrieverMemory

---

## 現有實作分析

### ChatHistoryProvider (MongoDB)

**位置**: `app/Providers/chat_history_provider/client.py`

**已實現功能**:

| 功能 | 方法 | 說明 |
|------|------|------|
| 完整訊息儲存 | `add_message()` | 儲存 role, content, timestamp, metadata |
| 窗口式讀取 | `get_chat_history(limit=N)` | 只返回最近 N 條訊息 |
| Session 隔離 | `session_id` | 格式: `skill_{user_id}_{skill_id}` |
| LangChain 格式 | `get_chat_history()` | 返回 `[{"role": "user", "content": "..."}]` |
| 用戶查詢 | `list_user_sessions()` | 列出用戶所有 sessions |
| 統計資訊 | `get_session_stats()` | 訊息計數、時間戳記 |

**結論**: 現有實作 **已等同於 ConversationBufferWindowMemory**

---

## LangChain Memory 組件分析

### 1. ConversationBufferMemory

```python
# LangChain 原生
memory = ConversationBufferMemory()
memory.save_context({"input": "hi"}, {"output": "hello"})
memory.load_memory_variables({})  # 返回所有對話
```

**與現有實作比較**:
| 特性 | LangChain | 現有 ChatHistoryProvider |
|------|-----------|-------------------------|
| 儲存方式 | In-Memory dict | MongoDB (持久化) ✅ |
| 格式 | messages list | messages list ✅ |
| Session 支援 | 需額外實作 | 內建 ✅ |
| 生產就緒 | ❌ (記憶體) | ✅ (資料庫) |

**結論**: ❌ **不需要整合** - 現有實作更優

---

### 2. ConversationBufferWindowMemory

```python
# LangChain 原生
memory = ConversationBufferWindowMemory(k=10)  # 只保留最近 10 輪
```

**與現有實作比較**:
```python
# 現有 ChatHistoryProvider
chat_history = await provider.get_chat_history(session_id, limit=10)
```

**結論**: ❌ **不需要整合** - 現有 `limit` 參數已實現相同功能

---

### 3. ConversationSummaryMemory ⭐

```python
# LangChain 實作概念 (from Context7)
def summarize_conversation(state):
    summary = state.get("summary", "")

    if summary:
        summary_message = f"Summary so far: {summary}\nExtend the summary:"
    else:
        summary_message = "Create a summary of the conversation above:"

    messages = state["messages"] + [HumanMessage(content=summary_message)]
    response = model.invoke(messages)

    # 刪除舊訊息，只保留最近 2 條
    delete_messages = [RemoveMessage(id=m.id) for m in state["messages"][:-2]]
    return {"summary": response.content, "messages": delete_messages}
```

**優點**:
- 🎯 減少 Token 使用量（長對話壓縮為摘要）
- 🎯 保留對話精華，忘記細節
- 🎯 適合超長對話 (>20 輪)

**與現有實作比較**:
| 特性 | ConversationSummaryMemory | 現有實作 |
|------|---------------------------|----------|
| Token 效率 | 高（壓縮摘要）| 低（完整歷史）|
| 精確度 | 可能遺失細節 | 完整保留 |
| LLM 調用 | 每次對話需額外調用 | 無 |
| 複雜度 | 高 | 低 |

**整合建議**: ⚠️ **可選整合** - 僅對超長對話有價值

---

### 4. VectorStoreRetrieverMemory ⭐⭐

```python
# LangChain 實作概念 (from Context7)
from langgraph.store.memory import InMemoryStore

def embed(texts: list[str]) -> list[list[float]]:
    return embedding_model.encode(texts)

store = InMemoryStore(index={"embed": embed, "dims": 768})

# 儲存記憶
store.put(namespace, "memory-id", {
    "rules": ["User likes short answers"],
    "preferences": {"language": "zh"}
})

# 語意搜尋相關記憶
items = store.search(namespace, query="language preferences")
```

**優點**:
- 🎯 **語意搜尋過去對話** - 根據當前問題找相關歷史
- 🎯 **長期記憶** - 跨 Session 記住用戶偏好
- 🎯 **Personalization** - 學習用戶行為模式

**與現有實作比較**:
| 特性 | VectorStoreRetrieverMemory | 現有實作 |
|------|---------------------------|----------|
| 搜尋方式 | 語意相似度 | 時間順序 |
| 跨 Session | ✅ | ❌ |
| 用戶偏好 | ✅ 可學習 | ❌ |
| 複雜度 | 高（需 Embedding）| 低 |
| FAISS 整合 | 可用現有基礎設施 | N/A |

**整合建議**: ⭐ **推薦整合** - 可利用現有 FAISS 和 BGE-M3 基礎設施

---

## 整合方案設計

### 方案 A: 最小變更（推薦用於 Demo）

**維持現狀** - 現有 `ChatHistoryProvider` 已足夠：
- ✅ ConversationBufferWindowMemory 功能已具備
- ✅ MongoDB 持久化優於 LangChain In-Memory
- ✅ 無需額外依賴

**適用場景**: Demo、短對話 (<20 輪)

---

### 方案 B: 增強型整合（Post-Demo）

#### B1. ConversationSummaryMemory 整合

**新增檔案**: `app/Services/memory_service.py`

```python
class MemoryService:
    """Memory Service with summarization support"""

    def __init__(
        self,
        chat_history_provider: ChatHistoryProvider,
        llm_client: LLMProviderClient,
        summary_threshold: int = 20  # 超過 20 條訊息開始摘要
    ):
        self.chat_history = chat_history_provider
        self.llm = llm_client
        self.summary_threshold = summary_threshold

    async def get_optimized_history(
        self,
        session_id: str,
        max_messages: int = 10
    ) -> List[Dict[str, str]]:
        """
        獲取優化後的對話歷史
        - 短對話：返回完整歷史
        - 長對話：返回摘要 + 最近 N 條
        """
        session = await self.chat_history.get_session(session_id)
        messages = session.get('messages', [])

        if len(messages) <= self.summary_threshold:
            # 短對話：直接返回最近 N 條
            return await self.chat_history.get_chat_history(
                session_id, limit=max_messages
            )

        # 長對話：生成摘要
        summary = await self._generate_summary(messages[:-max_messages])
        recent = messages[-max_messages:]

        return [
            {"role": "system", "content": f"對話摘要: {summary}"},
            *[{"role": m["role"], "content": m["content"]} for m in recent]
        ]

    async def _generate_summary(self, messages: List[Dict]) -> str:
        """使用 LLM 生成對話摘要"""
        prompt = [
            {"role": "system", "content": "請將以下對話摘要為 2-3 句話："},
            *[{"role": m["role"], "content": m["content"]} for m in messages]
        ]
        response = await self.llm.get_chat_completion(prompt, max_tokens=200)
        return response["choices"][0]["message"]["content"]
```

**修改影響**:
| 檔案 | 變更 |
|------|------|
| `app/Services/memory_service.py` | 新增 (約 80 行) |
| `app/api/v1/endpoints/skills.py` | 使用 MemoryService 替代直接 ChatHistoryProvider |

---

#### B2. VectorStoreRetrieverMemory 整合

**新增檔案**: `app/Services/semantic_memory_service.py`

```python
class SemanticMemoryService:
    """Semantic memory using FAISS for relevant history retrieval"""

    def __init__(
        self,
        embedding_provider,  # 現有 BGE-M3 provider
        faiss_index_path: str = "data/faiss_indices/memory"
    ):
        self.embeddings = embedding_provider
        self.index_path = faiss_index_path
        self._index = None
        self._id_to_memory = {}

    async def store_memory(
        self,
        user_id: str,
        memory_type: str,  # "preference", "fact", "interaction"
        content: str,
        metadata: Dict = None
    ):
        """儲存用戶記憶到向量庫"""
        embedding = await self.embeddings.embed_text(content)
        memory_id = f"{user_id}_{memory_type}_{uuid4().hex[:8]}"

        # 加入 FAISS 索引
        self._add_to_index(memory_id, embedding)
        self._id_to_memory[memory_id] = {
            "content": content,
            "type": memory_type,
            "metadata": metadata,
            "created_at": datetime.now()
        }

    async def retrieve_relevant_memories(
        self,
        user_id: str,
        query: str,
        top_k: int = 3
    ) -> List[Dict]:
        """根據當前問題檢索相關記憶"""
        query_embedding = await self.embeddings.embed_text(query)

        # FAISS 相似度搜尋
        distances, indices = self._index.search(query_embedding, top_k)

        return [
            self._id_to_memory[self._index_to_id[i]]
            for i in indices[0]
            if self._index_to_id[i].startswith(user_id)
        ]
```

**使用場景**:
```python
# 在查詢前，檢索相關用戶記憶
relevant_memories = await semantic_memory.retrieve_relevant_memories(
    user_id=user_id,
    query="什麼是機器學習？"
)

# 將記憶加入 context
context_with_memory = [
    *relevant_memories,  # 用戶歷史偏好/知識
    *rag_context         # 文檔檢索結果
]
```

**修改影響**:
| 檔案 | 變更 |
|------|------|
| `app/Services/semantic_memory_service.py` | 新增 (約 150 行) |
| `app/api/v1/endpoints/skills.py` | 可選整合 |
| `data/faiss_indices/memory/` | 新增目錄 |

---

## 整合建議總結

| Memory 類型 | 整合建議 | 優先級 | 原因 |
|-------------|----------|--------|------|
| ConversationBufferMemory | ❌ 不需要 | - | 現有實作更優 |
| ConversationBufferWindowMemory | ❌ 不需要 | - | 現有 `limit` 已實現 |
| ConversationSummaryMemory | ⚠️ 可選 | P2 | 僅對超長對話有價值 |
| VectorStoreRetrieverMemory | ✅ 推薦 | P1 | 可利用現有 FAISS，增加個性化 |

---

## 推薦實作路徑

### Phase 1: Demo (現狀維持)
- ✅ 使用現有 `ChatHistoryProvider` (已完成)
- ✅ `limit=10` 作為 Window Memory
- ✅ 無需 LangChain 依賴

### Phase 2: Post-Demo 增強
1. **VectorStoreRetrieverMemory** - 利用現有 FAISS + BGE-M3
   - 跨 Session 用戶偏好學習
   - 語意相關歷史對話檢索

2. **ConversationSummaryMemory** - 僅對超長對話
   - 當 messages > 20 時自動觸發
   - 使用現有 LLM Provider

### Phase 3: 企業級 (Optional)
- LangGraph 整合 (狀態機、checkpointing)
- Zep Memory Service (專用記憶服務)
- LangSmith 追蹤與監控

---

## 依賴分析

### 現有可重用組件

| 組件 | 位置 | 用途 |
|------|------|------|
| FAISS VectorStore | `data/faiss_indices/` | VectorStoreRetrieverMemory |
| BGE-M3 Embeddings | `app/Providers/embedding_provider/` | 記憶向量化 |
| LLMProviderClient | `app/Providers/llm_provider/client.py` | 摘要生成 |
| MongoDB | `ChatHistoryProvider` | 持久化儲存 |

### 需要新增

| 組件 | 說明 | 行數估計 |
|------|------|----------|
| MemoryService | 摘要記憶管理 | ~80 行 |
| SemanticMemoryService | 向量記憶檢索 | ~150 行 |

---

## 結論

**研究結論**:

1. **現有實作已足夠 Demo 使用** - `ChatHistoryProvider` 等同於 ConversationBufferWindowMemory

2. **LangChain 直接整合不推薦** - 因為：
   - 現有 MongoDB 實作比 In-Memory 更穩定
   - 會增加不必要的依賴
   - 需要適配現有 async 架構

3. **推薦借鑑 LangChain 概念自行實作**:
   - VectorStoreRetrieverMemory 概念 → 使用現有 FAISS
   - ConversationSummaryMemory 概念 → 使用現有 LLMProviderClient

---

## 相關檔案

- `app/Providers/chat_history_provider/client.py` - 現有 MongoDB 對話儲存
- `app/Services/prompt_service.py` - RAG Prompt 建構（含 chat_history 參數）
- `app/Providers/llm_provider/client.py` - LLM 客戶端
- `app/Providers/embedding_provider/` - BGE-M3 嵌入

---

*研究完成，暫不實作*
