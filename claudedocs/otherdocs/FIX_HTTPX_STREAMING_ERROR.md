# Fix: httpx Streaming Response Error

## 問題描述

### 錯誤訊息
```
event: error
data: {"error": "Attempted to access streaming response content, without having called `read()`."}
```

### 瀏覽器錯誤
```
POST http://localhost:8000/api/v1/chat/stream net::ERR_INCOMPLETE_CHUNKED_ENCODING 200 (OK)
[DocAI] Stream reading error: TypeError: network error
```

### 根本原因

在 `app/Providers/llm_provider/client.py` 中，exception handler 嘗試訪問 streaming response 的 `.text` 屬性，導致 httpx 錯誤。

**錯誤流程**：

1. **Line 104-109**: 使用 `client.stream()` 建立 streaming request
   ```python
   async with client.stream("POST", endpoint, ...) as response:
   ```

2. **Line 111-118**: 檢查 HTTP status code，如果 >= 400：
   ```python
   if response.status_code >= 400:
       error_text = await response.aread()  # ✅ 正確讀取 streaming response
       logger.error(f"HTTP {response.status_code} from LLM provider: {error_text.decode()}")
       raise httpx.HTTPStatusError(...)
   ```

3. **Line 124-126**: Exception handler 捕獲錯誤：
   ```python
   except httpx.HTTPStatusError as e:
       logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")  # ❌ 錯誤！
   ```

**問題**：
- Line 112 已使用 `aread()` 消耗 streaming response body
- Line 125 再次嘗試訪問 `e.response.text`
- httpx 偵測到這是 streaming response 且 body 已被讀取
- 拋出錯誤：`"Attempted to access streaming response content, without having called read()"`

## 修復方案

### Fix #1: Streaming Function Error Handler

**檔案**: `app/Providers/llm_provider/client.py`
**位置**: Lines 124-128

**修復前**:
```python
except httpx.HTTPStatusError as e:
    logger.error(f"HTTP error from LLM provider: {e.response.status_code} - {e.response.text}")
    raise
```

**修復後**:
```python
except httpx.HTTPStatusError as e:
    # FIX: Don't access e.response.text for streaming responses
    # Error details already logged in line 113 before raising
    logger.error(f"HTTP error from LLM provider: {e.response.status_code}")
    raise
```

**說明**：
- 移除對 `e.response.text` 的訪問
- 錯誤詳情已在 line 113 記錄（在 raise 之前）
- 避免重複訪問 streaming response body

### Fix #2: Non-Streaming Function Error Handler (防禦性編程)

**檔案**: `app/Providers/llm_provider/client.py`
**位置**: Lines 188-195

**修復前**:
```python
except httpx.HTTPStatusError as e:
    logger.error(f"HTTP error from LLM provider: {e.response.status_code} - {e.response.text}")
    raise
```

**修復後**:
```python
except httpx.HTTPStatusError as e:
    # FIX: Safe error logging - attempt to read response text, fallback to status code only
    try:
        error_detail = e.response.text
        logger.error(f"HTTP error from LLM provider: {e.response.status_code} - {error_detail}")
    except Exception:
        logger.error(f"HTTP error from LLM provider: {e.response.status_code}")
    raise
```

**說明**：
- 雖然 non-streaming response 通常可以安全訪問 `.text`
- 但為了防禦性編程，增加 try-except 處理
- 如果讀取失敗，fallback 到只記錄 status code

## 驗證方法

### 測試場景

1. **正常 Streaming (應該成功)**:
   - LLM 正常回應
   - Token streaming 正常
   - 無錯誤訊息

2. **HTTP 錯誤 Streaming (應該優雅處理)**:
   - LLM 返回 404/500 錯誤
   - 錯誤訊息正確記錄（status code only）
   - 不出現 "Attempted to access streaming response content" 錯誤

### 瀏覽器測試

訪問 `http://localhost:8000`，上傳文件並提問：
- ✅ 應看到 progress events
- ✅ 應看到 markdown tokens streaming
- ✅ 不應看到 "Attempted to access streaming response content" 錯誤
- ✅ Console 不應有 `net::ERR_INCOMPLETE_CHUNKED_ENCODING` 錯誤

### Logs 檢查

```bash
tail -100 logs/server.log | grep -E "(HTTP error|Attempted)"
```

**期望結果**：
- ✅ 如有 HTTP 錯誤，只顯示 status code
- ❌ 不應出現 "Attempted to access streaming response content"

## 相關修復

這個修復與之前的 SSE 修復相關：

1. **SSE Line Ending Fix** (已完成)
   - `docai-client.js:370` - `line.trim() === ''`
   - 修復 `\r\n` line ending 解析問題

2. **LLM URL Auto-Correction** (已完成)
   - `client.py:41-44` - Auto-add `/v1` suffix
   - 修復 Ollama API 404 錯誤

3. **httpx Streaming Error Fix** (本次修復)
   - `client.py:124-128` & `188-195`
   - 修復 streaming response error handling

## 技術細節

### httpx Streaming Response 限制

當使用 `client.stream()` 時：
- ✅ 可以使用: `response.status_code`, `response.headers`
- ✅ 可以使用: `response.aiter_bytes()`, `response.aread()`
- ❌ 不能使用: `response.text`, `response.content`, `response.json()` (在未呼叫 read() 前)

### 正確的 Streaming Error Handling

```python
# ✅ 正確方式 1: 在 streaming context 內讀取錯誤
async with client.stream("POST", url) as response:
    if response.status_code >= 400:
        error_text = await response.aread()  # 在 context 內讀取
        logger.error(f"Error: {error_text.decode()}")
        raise HTTPStatusError(...)

# ✅ 正確方式 2: Exception handler 不訪問 response body
except HTTPStatusError as e:
    logger.error(f"Error: {e.response.status_code}")  # 只記錄 status code
    raise

# ❌ 錯誤方式: Exception handler 訪問 streaming response text
except HTTPStatusError as e:
    logger.error(f"Error: {e.response.text}")  # ❌ 會失敗！
    raise
```

## 影響範圍

### 受影響的功能
- `/api/v1/chat/stream` - Native RAG streaming
- 所有使用 `LLMProviderClient.get_chat_completion_stream()` 的功能

### 不受影響的功能
- `/api/v1/chat/stream-langchain` - LangChain streaming (使用不同的 client)
- Non-streaming endpoints
- File upload 功能

## 部署檢查清單

- [x] 修改 `client.py` streaming error handler
- [x] 修改 `client.py` non-streaming error handler (防禦性)
- [x] 重啟系統載入修復
- [ ] 瀏覽器測試確認無錯誤
- [ ] 檢查 logs 確認錯誤處理正常
- [ ] 提交 git commit

## Git Commit Message

```
fix: httpx streaming response error handling

Problem:
- Exception handler accessed e.response.text on streaming response
- Caused "Attempted to access streaming response content" error
- Resulted in ERR_INCOMPLETE_CHUNKED_ENCODING in browser

Solution:
- Remove e.response.text access in streaming error handler
- Error details already logged before raising exception
- Add defensive try-except for non-streaming handler

Files:
- app/Providers/llm_provider/client.py (lines 124-128, 188-195)

Related:
- SSE line ending fix (docai-client.js:370)
- LLM URL auto-correction (client.py:41-44)
```

---

**文件版本**: 1.0
**建立日期**: 2025-11-05
**狀態**: 已修復，待測試
