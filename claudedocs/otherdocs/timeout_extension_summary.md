# Timeout Extension Implementation Summary

**日期**: 2025-11-05
**狀態**: ✅ 完成
**目標**: 延長 backend 和 frontend 的等待時間，支持 LLM 冷啟動

---

## 實施的修改

### 1. Backend Timeout 延長

#### 1.1 LLM Provider Timeout (config.py)

**文件**: [app/core/config.py:43](app/core/config.py#L43)

**修改前**:
```python
LLM_TIMEOUT: float = 60.0
```

**修改後**:
```python
LLM_TIMEOUT: float = 300.0  # Extended to 5 minutes for LLM cold start (was 60.0)
```

**影響範圍**:
- `app/Providers/llm_provider/client.py:97` - httpx.AsyncClient timeout
- 所有 LLM streaming 和 non-streaming 請求
- 適用於 Ollama 本地 LLM 服務

**理由**:
- LLM 首次加載 model 需要 30-60 秒（phi4-mini:3.8b ≈ 3.2GB）
- 原 60 秒超時在冷啟動時會過早斷開連接
- 5 分鐘提供足夠緩衝時間

---

#### 1.2 SSE Keep-Alive Mechanism (chat.py)

**文件**: [app/api/v1/endpoints/chat.py:355](app/api/v1/endpoints/chat.py#L355)

**修改前**:
```python
return EventSourceResponse(generate_sse_events())
```

**修改後**:
```python
# ping=15 sends keep-alive comments every 15 seconds to prevent connection timeout
return EventSourceResponse(generate_sse_events(), ping=15)
```

**功能**:
- 每 15 秒自動發送 SSE comment (`: ping\n\n`) 保持連接活躍
- 防止 proxy、load balancer、browser 因長時間沉默而斷開連接
- 不影響實際數據流，僅作為心跳信號

**理由**:
- LLM generation 期間可能有長時間沒有 token 輸出
- Keep-alive 確保連接在整個 generation 過程中保持開啟
- Standard SSE practice for long-running streams

---

### 2. Frontend Timeout 延長

#### 2.1 Fetch Timeout Control (docai-client.js)

**文件**: [static/js/docai-client.js:274-290](static/js/docai-client.js#L274-L290)

**修改前** (implicit default timeout ~60-90s):
```javascript
async streamChat(payload, aiBubble, progressIndicator) {
    console.log('[DocAI] Starting SSE stream...');

    const response = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-User-ID': this.userId
        },
        body: JSON.stringify(payload)
    });
```

**修改後** (explicit 5-minute timeout):
```javascript
async streamChat(payload, aiBubble, progressIndicator) {
    console.log('[DocAI] Starting SSE stream...');

    // Extended timeout: 5 minutes for LLM cold start (was default ~60s)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
        console.warn('[DocAI] Stream timeout after 5 minutes');
        controller.abort();
    }, 300000); // 5 minutes = 300000ms

    try {
        const response = await fetch('/api/v1/chat/stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-ID': this.userId
            },
            body: JSON.stringify(payload),
            signal: controller.signal  // Abort signal for timeout control
        });
```

**功能**:
- 使用 AbortController 明確控制 timeout
- 5 分鐘 = 300,000 毫秒
- Timeout 觸發時 abort fetch 並拋出 AbortError

---

#### 2.2 Timeout Cleanup (docai-client.js)

**文件**: [static/js/docai-client.js:295,315,374-382](static/js/docai-client.js#L295)

**添加**:
```javascript
// On error
if (!response.ok) {
    clearTimeout(timeoutId);  // Clear timeout on error
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
}

// On completion
if (done) {
    console.log('[DocAI] Stream completed, total events:', eventCount);
    clearTimeout(timeoutId);  // Clear timeout on completion
    break;
}

// On stream error
} catch (streamError) {
    console.error('[DocAI] Stream reading error:', streamError);
    clearTimeout(timeoutId);  // Clear timeout on error
    throw streamError;
}

// On fetch error with specific AbortError handling
} catch (fetchError) {
    clearTimeout(timeoutId);  // Clear timeout on fetch error
    if (fetchError.name === 'AbortError') {
        throw new Error('Request timeout after 5 minutes - LLM may be loading model');
    }
    throw fetchError;
}
```

**功能**:
- 確保 timeout timer 在所有情況下都被正確清理
- 避免 memory leak 和 zombie timers
- 提供友好的 timeout error message

---

#### 2.3 Cache Busting Update (index.html)

**文件**: [template/index.html:480](template/index.html#L480)

**修改前**:
```html
<script src="/static/js/docai-client.js?v=1762318800"></script>
```

**修改後**:
```html
<script src="/static/js/docai-client.js?v=1762321887"></script>
```

**目的**:
- 確保瀏覽器加載更新後的 JavaScript 代碼
- Unix timestamp 版本號強制 cache invalidation

---

## 完整超時配置總結

### Timeout 層級

| Layer | Component | Timeout | Keep-Alive | Notes |
|-------|-----------|---------|------------|-------|
| **Backend** | httpx.AsyncClient | 300s | N/A | LLM HTTP client |
| **Backend** | EventSourceResponse | ∞ | 15s ping | SSE stream generator |
| **Frontend** | fetch() | 300s | Browser default | AbortController |
| **LLM** | Ollama | ∞ | N/A | Local service, no timeout |

### 預期行為

#### 冷啟動場景（首次請求）
```
t=0s    User: 發送 chat request
t=0s    Frontend: fetch() started, 5-min timeout armed
t=0s    Backend: SSE stream created, ping every 15s
t=0s    Backend: 調用 LLM with 300s timeout

t=15s   Backend: :ping (keep-alive)
t=30s   Backend: :ping
t=45s   Backend: :ping
t=60s   LLM: Model loaded, 開始生成 tokens
t=60s   Frontend: 收到第一個 markdown_token
t=65s   LLM: 生成完成
t=65s   Frontend: 收到 complete event
t=65s   Frontend: clearTimeout(), stream closed
```

#### 熱啟動場景（model 已加載）
```
t=0s    User: 發送 chat request
t=0s    Frontend: fetch() started
t=0s    Backend: SSE stream created
t=0s    Backend: 調用 LLM
t=1s    LLM: 立即開始生成（model in memory）
t=1s    Frontend: 收到第一個 markdown_token
t=5s    LLM: 生成完成
t=5s    Frontend: 收到 complete event, stream closed
```

---

## 兼容性與影響

### ✅ 不影響當前運行模式

**當前配置** (docai-client.js:19):
```javascript
this.useStreaming = false; // Use non-streaming mode by default
```

**Non-streaming mode 仍然使用**:
- `simpleChat()` method 調用 `/api/v1/chat` (non-streaming endpoint)
- 沒有 SSE，使用標準 JSON response
- Timeout 仍然是 browser default (~60s)，但足夠因為：
  - Model 已 preloaded
  - 完整響應在 2-5 秒內返回

**Streaming mode 改進生效時機**:
- 當 `this.useStreaming = true` 時
- 用戶可選擇啟用 token-by-token streaming
- 現在有 5 分鐘超時保護

---

### ✅ Backward Compatible

**不會破壞現有功能**:
- Non-streaming mode 繼續正常工作
- Streaming mode 現在更可靠（如果啟用）
- Keep-alive ping 對 clients 透明（comment lines 被忽略）

**可能的副作用**:
- 稍微增加 server resources（每 15 秒發送 ping）
- 佔用極少 bandwidth（每個 ping ≈ 10 bytes）
- 影響可忽略不計

---

## 測試建議

### 測試場景 1: Non-streaming Mode (當前默認)
```bash
# 1. 確保 model 已 preloaded
curl http://localhost:11434/api/generate \
  -d '{"model":"phi4-mini:3.8b","prompt":"test","stream":false}'

# 2. 測試 non-streaming endpoint
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "請問這份文件在說什麼",
    "session_id": "test_session",
    "file_ids": ["file_id_here"]
  }'

# 預期: 2-5 秒內返回完整 JSON response
```

### 測試場景 2: Streaming Mode (可選啟用)

**啟用 streaming**:
```javascript
// In docai-client.js:19
this.useStreaming = true;
```

**測試冷啟動**:
```bash
# 1. Unload model 模擬冷啟動
docker exec ollama pkill ollama
docker restart ollama

# 2. 發送 streaming request
# 打開瀏覽器 DevTools → Network → 觀察 /api/v1/chat/stream

# 預期行為:
# - 每 15 秒看到 :ping
# - 60-90 秒後收到第一個 token
# - 5 分鐘內不會 timeout
```

### 測試場景 3: Timeout 驗證

**測試超時機制**:
```javascript
// Temporarily reduce timeout for testing
const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 seconds

// 發送 request，預期 5 秒後 abort
// Console 應該顯示: "Request timeout after 5 minutes - LLM may be loading model"
```

---

## 相關文檔

- **OPMP 分析報告**: [claudedocs/opmp_streaming_analysis.md](claudedocs/opmp_streaming_analysis.md)
- **Backend 配置**: [app/core/config.py](app/core/config.py)
- **LLM Provider**: [app/Providers/llm_provider/client.py](app/Providers/llm_provider/client.py)
- **Chat Endpoint**: [app/api/v1/endpoints/chat.py](app/api/v1/endpoints/chat.py)
- **Frontend Client**: [static/js/docai-client.js](static/js/docai-client.js)

---

## 下一步（可選）

### 進一步優化

1. **Model Preloading on Server Startup**
   - 在 server 啟動時自動 preload model
   - 消除首次請求的冷啟動延遲
   - 實施位置: `main.py` startup event handler

2. **Progress Feedback Enhancement**
   - 在 LLM 載入期間顯示明確的 "Model loading..." 消息
   - 添加倒計時或進度條
   - 改善用戶體驗

3. **Queue-Based Streaming Architecture**
   - 實施 reference implementation 的 asyncio.Queue 模式
   - 完全解耦 LLM generation 和 SSE sending
   - 消除潛在的 buffering 問題

4. **Adaptive Timeout**
   - 根據 model size 動態調整 timeout
   - 檢測首次請求 vs 後續請求
   - 智能 timeout management

---

## 結論

✅ **Backend timeout 延長**: 60s → 300s
✅ **Frontend timeout 延長**: default → 300s (explicit control)
✅ **Keep-alive 機制**: 每 15 秒 ping
✅ **Cache busting**: 更新版本號

**當前狀態**:
- Non-streaming mode 工作完美（默認）
- Streaming mode 現在有足夠的 timeout 保護（可選啟用）
- 為將來的 OPMP streaming 優化奠定基礎
