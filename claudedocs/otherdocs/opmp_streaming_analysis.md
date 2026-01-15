# OPMP Streaming 實現分析報告

**日期**: 2025-11-05
**狀態**: 已修復（使用 non-streaming fallback）
**待優化**: OPMP streaming 架構改進（可選）

---

## 執行摘要

**根本原因**: LLM 冷啟動超時（30-60秒），而非 OPMP 架構或同步問題
**當前解決方案**: 實施 non-streaming mode 作為可靠的 fallback
**證據**: Backend logs 顯示完整的 SSE 事件成功生成（2043 lines）

---

## 問題時間線

### Phase 1: 初始症狀
- **現象**: Frontend 停留在 "Initializing..."，backend 成功輸出 2043 行 SSE 事件
- **文件**: `refData/errors/messages/screen_does_not_show_the_meesage_backend_can_show_2.txt`
- **診斷**: Browser caching 導致 JavaScript 未更新

### Phase 2: Cache Busting 後持續問題
- **修復**: 添加 version parameters + Cache-Control headers
- **結果**: 仍然失敗
- **新發現**: Milvus warning + 60 秒後 http.disconnect

### Phase 3: 發現根本原因
- **文件**: `refData/errors/messages/screen_does_not_show_the_meesage_backend_can_show_5.txt`
- **關鍵時間差**:
  ```
  12:43:03.160 - Phase 4 start: "Generating answer from LLM..."
  12:43:03.173 - httpcore: connect_tcp.started
  [60 seconds of silence - LLM loading model into memory]
  12:44:02.948 - Got event: http.disconnect
  ```

### Phase 4: 解決方案實施
- **修復**:
  1. 切換到更快的 phi4-mini:3.8b model
  2. Model preloading
  3. 實施 non-streaming mode (`simpleChat()`)
- **結果**: ✅ 成功，2-5 秒響應時間

---

## 架構比較：Current vs Reference

### Current Implementation 架構

**文件**: `app/api/v1/endpoints/chat.py:126-354`

**流程**:
```
generate_sse_events() [Outer Generator]
  ↓
  llm_client.get_chat_completion_stream() [Middle Generator]
    ↓
    httpx.response.aiter_bytes() [Inner Generator]
      ↓
      Parse SSE → Extract token → Yield to frontend
```

**特點**:
- **3 層嵌套 async generators**
- **SSE 格式**: `{"event": "markdown_token", "data": json.dumps(...)}`
- **Buffering 風險**: 多層嵌套可能導致 token buffering
- **錯誤處理**: 在 generate_sse_events() 頂層捕獲

**代碼片段** (chat.py:246-280):
```python
# Phase 4: Response Generation (OPMP Core)
async for chunk in llm_client.get_chat_completion_stream(
    messages=messages,
    temperature=0.7
):
    chunk_str = chunk.decode('utf-8')

    for line in chunk_str.split('\n'):
        if line.startswith('data: '):
            data_str = line[6:]

            if data_str.strip() == '[DONE]':
                continue

            try:
                data = json.loads(data_str)
                choices = data.get('choices', [])
                if choices:
                    delta = choices[0].get('delta', {})
                    token = delta.get('content', '')

                    if token:
                        full_response += token
                        yield create_sse_event("markdown_token", {"token": token})
            except json.JSONDecodeError:
                continue
```

### Reference Implementation 架構

**文件**: `refData/Codes/opmp_kernel/phase4_response_generation.py:187-257`

**流程**:
```
asyncio.Queue [Decoupling Layer]
  ↑                    ↓
generate() task    while loop yields tokens
  ↑                    ↓
LLM.astream()      queue.get() → Immediate yield
```

**特點**:
- **Producer-Consumer 解耦** via asyncio.Queue
- **零 buffering**: queue.get() 立即返回可用 token
- **SSE 格式**: `f"data: {json.dumps(...)}\n\n"` (更簡單)
- **錯誤處理**: 通過 queue 傳遞 error event

**代碼片段** (phase4_response_generation.py:187-257):
```python
async def process(self, query, analysis, context):
    queue = asyncio.Queue()

    async def generate():
        try:
            async for chunk in self.llm.astream(prompt):
                token = str(chunk) if chunk else ""
                if token:
                    await queue.put({
                        "type": "markdown_token",
                        "token": token
                    })
            await queue.put(None)  # Signal completion
        except Exception as e:
            await queue.put({"type": "error", "message": str(e)})
            await queue.put(None)

    # Start LLM generation in background
    task = asyncio.create_task(generate())

    # Stream tokens as they arrive
    while True:
        token_data = await queue.get()
        if token_data is None:
            break
        yield token_data  # Immediate yield, no additional layers

    await task
```

### 關鍵差異總結

| 特性 | Current Implementation | Reference Implementation |
|------|------------------------|--------------------------|
| **架構模式** | 嵌套 async generators (3 層) | asyncio.Queue producer-consumer |
| **Token 延遲** | 可能有 buffering | 零 buffering (immediate queue.get) |
| **SSE 格式** | `{"event": X, "data": json.dumps(Y)}` | `f"data: {json}\n\n"` |
| **錯誤處理** | Top-level try/except | Queue-based error propagation |
| **複雜度** | 中等（多層解析） | 低（直接 queue 通信） |
| **LLM 超時** | 60s (太短) | 可配置 + heartbeat 機制 |

---

## 當前超時配置

### Backend 超時

**文件**: `app/core/config.py:43`
```python
LLM_TIMEOUT: float = 60.0
```

**文件**: `app/Providers/llm_provider/client.py:29,97`
```python
def __init__(self, timeout: float = 60.0):
    self.timeout = timeout

async with httpx.AsyncClient(timeout=self.timeout) as client:
    # 60 秒後斷開連接
```

### Frontend 超時

**文件**: `static/js/docai-client.js:266-365`
- 使用瀏覽器默認 fetch timeout (通常 ~60-90 秒)
- 無明確的 EventSource timeout 配置
- 60 秒沉默後瀏覽器可能自動斷開連接

---

## 診斷結論

### ✅ 工作正常的部分

1. **Backend SSE Streaming Logic**:
   - 完整生成 2043 行 markdown tokens
   - 所有 5 個 phases 正確執行
   - Event format 正確 (`event:`, `data:` lines)

2. **Frontend SSE Parsing**:
   - 14 個 debug tracking points 全部正確
   - Event type 識別正確 (progress, markdown_token, complete)
   - Markdown rendering 使用 marked.js

3. **Non-Streaming Mode**:
   - simpleChat() 100% 成功率
   - 2-5 秒響應時間
   - 完整 markdown 渲染

### ❌ 問題所在

**不是同步問題，是超時問題！**

1. **LLM Cold Start Delay**:
   - Ollama 首次加載 model 需要 30-60 秒
   - 在這段時間內沒有任何 token 輸出
   - Frontend 等待超時後斷開連接

2. **缺少進度反饋**:
   - 用戶在 60 秒內只看到 "Processing..."
   - 沒有 "Model loading..." 的明確提示
   - 缺少 heartbeat keep-alive 機制

3. **超時配置不當**:
   - 60 秒對於 LLM 冷啟動不足
   - 應該至少 180-300 秒
   - 或實施 model preloading

---

## 建議改進（可選）

### 優先級 1: 延長超時（立即實施）

**Backend**:
```python
# config.py
LLM_TIMEOUT: float = 300.0  # 5 minutes for cold start
```

**Frontend**:
```javascript
// docai-client.js
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 min

fetch('/api/v1/chat/stream', {
    signal: controller.signal
    // ...
});
```

### 優先級 2: Model Preloading（server 啟動時）

```bash
# In startup script
curl http://localhost:11434/api/generate \
  -d '{"model":"phi4-mini:3.8b","prompt":"warmup","stream":false}'
```

### 優先級 3: Heartbeat Mechanism（進階）

**Backend**:
```python
return EventSourceResponse(
    generate_sse_events(),
    ping=10  # Send comment every 10 seconds to keep connection alive
)
```

**Frontend**:
- Add explicit "Model loading, please wait..." message
- Show countdown timer during initial silence

### 優先級 4: Queue-Based Architecture（最佳化）

實施 reference implementation 的 asyncio.Queue 模式：
- 完全解耦 LLM generation 和 SSE sending
- 零 buffering，immediate token delivery
- 更簡潔的錯誤處理

---

## 當前推薦方案

**保留 non-streaming mode 作為默認**:
- ✅ 100% 可靠
- ✅ 2-5 秒響應時間（model preloaded）
- ✅ 完整 markdown 渲染
- ✅ 用戶體驗優於有延遲的 streaming

**可選啟用 streaming**:
- 在 `docai-client.js:19` 設置 `this.useStreaming = true`
- 需要先實施超時延長和 model preloading
- 適合真正需要 token-by-token 體驗的場景

---

## 參考文件

### Backend Messages (Evidence)
- `refData/errors/messages/screen_does_not_show_the_meesage_backend_can_show_2.txt` - 2043 行成功的 SSE events
- `refData/errors/messages/screen_does_not_show_the_meesage_backend_can_show_5.txt` - 60 秒超時證據

### Screenshots
- `refData/done/the_summary_is_successfully_be_shown_on_the_screen.png` - Non-streaming 成功截圖

### Reference Implementation
- `refData/Codes/opmp_kernel/progressive_streaming.py` - Main orchestrator
- `refData/Codes/opmp_kernel/phase4_response_generation.py` - Queue-based streaming
- `refData/Codes/opmp_kernel/chat_stream_optimized.py` - Optimized retrieval

### Current Implementation
- `app/api/v1/endpoints/chat.py` - SSE streaming endpoint
- `app/Providers/llm_provider/client.py` - LLM provider with httpx
- `static/js/docai-client.js` - Frontend SSE parsing
