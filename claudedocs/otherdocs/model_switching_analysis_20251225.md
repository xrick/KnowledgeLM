# 模型切換功能完整性分析報告

**日期**: 2025-12-25
**分析範圍**: 前端 UI → 後端 API → LLM Provider
**驗證方法**: 程式碼審查 + 流程分析

---

## 執行摘要

✅ **模型切換功能已完整實現**，包含：
1. 前端 UI 選擇介面
2. 後端 API endpoint (`/api/v1/llm/switch`)
3. LLMManager 模型切換邏輯
4. LLMProviderClient 模型參數傳遞

**關鍵發現**: 程式碼邏輯正確，會真正切換到新選擇的模型。

---

## 1. 前端模型切換實現

### 1.1 UI 介面
**檔案**: `template/skill_main.html` (Lines 2128-2152)

**可用模型**:
```html
1. gpt-oss:20b     (預設，20B 參數)
2. deepseek-r1:7b  (7B 參數)
3. phi4-mini:3.8b  (3.8B 參數)
```

**HTML 結構**:
```html
<div class="model-selector" id="model-selector-btn" onclick="toggleModelDropdown(event)">
    <span id="current-model-name">gpt-oss</span>
</div>
<div class="model-dropdown-menu">
    <div class="model-dropdown-item active" data-model="gpt-oss:20b"
         onclick="selectModel('gpt-oss:20b')">
        <span class="model-name">gpt-oss</span>
        <span class="model-size">20B</span>
    </div>
    <!-- 其他模型... -->
</div>
```

### 1.2 JavaScript 切換邏輯
**檔案**: `template/skill_main.html` (Lines 4399-4478)

**關鍵變數**:
```javascript
let currentModel = 'gpt-oss:20b';  // 追蹤當前模型
```

**selectModel() 函數流程**:
```javascript
async function selectModel(modelName) {
    // 1. 檢查是否為相同模型
    if (modelName === currentModel) {
        closeModelDropdown();
        return;  // ✅ 避免重複切換
    }

    // 2. 顯示切換中狀態
    modelNameSpan.textContent = '切換中...';

    // 3. 呼叫後端 API
    const response = await fetch('/api/v1/llm/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: modelName })  // ✅ 完整模型名稱
    });

    // 4. 處理回應
    if (response.ok) {
        const data = await response.json();
        currentModel = data.new_model;  // ✅ 更新前端狀態
        updateModelDisplay(currentModel);
        showModelToast(`已切換至 ${displayName}`, 'success');
        console.log(`[Model Switch] ${data.old_model} → ${data.new_model}`);
    } else {
        // 錯誤處理...
    }
}
```

**✅ 驗證點**:
- 傳送完整模型名稱（例如 `gpt-oss:20b`，不是只有 `gpt-oss`）
- 更新前端狀態 `currentModel`
- 顯示成功/失敗提示

---

## 2. 後端 API Endpoint

### 2.1 API 定義
**檔案**: `app/api/v1/endpoints/llm.py` (Lines 131-166)

```python
@router.post(
    "/switch",
    response_model=SwitchModelResponse,
    summary="Switch LLM Model",
    description="Switches to a different LLM model. Releases current model resources first."
)
async def switch_model(
    request: SwitchModelRequest,
    manager: LLMManager = Depends(get_llm_manager)
) -> SwitchModelResponse:
    """
    Switch to a different LLM model.

    This will:
    1. Release resources of the current model
    2. Initialize the new model
    3. Return success/failure status
    """
    logger.info(f"Request to switch LLM model to: {request.model_name}")

    result = await manager.switch_model(request.model_name)  # ✅ 調用管理器切換

    if not result["success"]:
        logger.error(f"Failed to switch model: {result.get('error')}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to switch model: {result.get('error')}"
        )

    return SwitchModelResponse(**result)
```

**Request Schema**:
```python
class SwitchModelRequest(BaseModel):
    model_name: str  # 例如: "deepseek-r1:7b"
```

**Response Schema**:
```python
class SwitchModelResponse(BaseModel):
    success: bool
    old_model: str
    new_model: str
    message: str
```

**✅ 驗證點**:
- 接收完整模型名稱
- 調用 LLMManager 進行切換
- 返回舊模型和新模型名稱

---

## 3. LLMManager 模型切換邏輯

### 3.1 switch_model() 實現
**檔案**: `app/Providers/llm_provider/manager.py` (Lines 90-153)

```python
async def switch_model(self, new_model: str) -> Dict[str, Any]:
    """
    Switch to a different LLM model

    Releases the current client resources and creates a new one
    with the specified model.
    """
    async with self._client_lock:  # ✅ 執行緒安全
        old_model = self._current_model

        # 1. 檢查是否已經使用該模型
        if old_model == new_model:
            logger.info(f"Already using model: {new_model}")
            return {
                "success": True,
                "old_model": old_model,
                "new_model": new_model,
                "message": "Already using this model"
            }

        try:
            # 2. 釋放當前 client 資源
            if self._client is not None:
                logger.info(f"Releasing current LLM client (model: {old_model})")
                await self._client.release()  # ✅ 清理舊連接
                self._client = None

            # 3. 更新當前模型
            self._current_model = new_model  # ✅ 關鍵：更新模型狀態

            # 4. 創建新 client
            from app.Providers.llm_provider.client import LLMProviderClient

            self._client = LLMProviderClient(
                base_url=self._base_url,
                api_key=self._api_key,
                model_name=new_model  # ✅ 傳遞新模型名稱
            )

            logger.info(f"Switched LLM model: {old_model} -> {new_model}")

            return {
                "success": True,
                "old_model": old_model,
                "new_model": new_model,
                "message": f"Successfully switched from {old_model} to {new_model}"
            }

        except Exception as e:
            logger.error(f"Failed to switch model: {e}")
            # 失敗時恢復舊模型
            self._current_model = old_model  # ✅ 錯誤恢復
            return {
                "success": False,
                "old_model": old_model,
                "new_model": new_model,
                "error": str(e)
            }
```

**✅ 驗證點**:
- 執行緒安全（使用 async lock）
- 釋放舊 client 資源
- **更新 `self._current_model` 狀態變數**
- 創建新 LLMProviderClient 並傳遞新模型名稱
- 錯誤恢復機制

---

## 4. LLMProviderClient 模型使用

### 4.1 初始化
**檔案**: `app/Providers/llm_provider/client.py` (Lines 27-60)

```python
class LLMProviderClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        model_name: Optional[str] = None  # ✅ 接收模型名稱
    ):
        self.base_url = base_url or settings.LLM_PROVIDER_BASE_URL
        self.api_key = api_key or settings.LLM_PROVIDER_API_KEY or "ollama"
        self.timeout = timeout or settings.LLM_TIMEOUT
        self.model_name = model_name or settings.DEFAULT_LLM_MODEL  # ✅ 儲存模型名稱

        logger.info(
            f"LLM Provider initialized: model={self.model_name}, "
            f"base_url={self.base_url}, timeout={self.timeout}s"
        )
```

### 4.2 Chat Completion 使用
**檔案**: `app/Providers/llm_provider/client.py` (Lines 85-158)

```python
async def get_chat_completion_stream(
    self,
    messages: list[dict],
    model: Optional[str] = None,  # 可選覆蓋
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    **kwargs
) -> AsyncGenerator[bytes, None]:
    """Get streaming chat completion from LLM"""

    # ✅ 關鍵：使用實例的 model_name 作為預設值
    model = model or self.model_name

    request_body = {
        "model": model,  # ✅ 傳遞給 Ollama API
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }

    # ... 發送請求到 Ollama API ...
    endpoint = f"{self.base_url}/chat/completions"
    async with httpx.AsyncClient(timeout=self.timeout) as client:
        async with client.stream(
            "POST",
            endpoint,
            json=request_body,  # ✅ 包含正確的模型名稱
            headers=headers
        ) as response:
            async for chunk in response.aiter_bytes():
                yield chunk
```

**✅ 驗證點**:
- `model_name` 儲存在實例變數中
- 每次 chat completion 請求都使用 `self.model_name`
- 請求體中的 `"model"` 欄位會傳遞給 Ollama API

---

## 5. 完整流程圖

```
使用者點擊模型選項
    ↓
selectModel('deepseek-r1:7b')  [前端]
    ↓
POST /api/v1/llm/switch
    body: { "model_name": "deepseek-r1:7b" }
    ↓
switch_model() endpoint  [API]
    ↓
manager.switch_model('deepseek-r1:7b')  [LLMManager]
    ├─ Release old client
    ├─ self._current_model = 'deepseek-r1:7b'  ✅ 更新狀態
    └─ Create new LLMProviderClient(model_name='deepseek-r1:7b')
        ↓
    LLMProviderClient.__init__()  [Client]
        └─ self.model_name = 'deepseek-r1:7b'  ✅ 儲存模型
    ↓
Response: {
    "success": true,
    "old_model": "gpt-oss:20b",
    "new_model": "deepseek-r1:7b"
}
    ↓
updateModelDisplay()  [前端]
    └─ currentModel = 'deepseek-r1:7b'  ✅ 前端狀態同步
    └─ 顯示: "已切換至 deepseek-r1"

---

下次查詢時：
    ↓
get_chat_completion_stream(messages)
    └─ model = self.model_name  ✅ 使用 'deepseek-r1:7b'
    └─ request_body = { "model": "deepseek-r1:7b", ... }
    └─ POST http://localhost:11434/v1/chat/completions
        ↓
    Ollama API 載入並執行 deepseek-r1:7b 模型  ✅
```

---

## 6. 驗證結果

### 6.1 程式碼層面驗證

| 檢查項目 | 狀態 | 說明 |
|---------|------|------|
| **前端傳遞完整模型名稱** | ✅ | `selectModel('deepseek-r1:7b')` |
| **API 接收模型名稱** | ✅ | `request.model_name` |
| **Manager 更新狀態** | ✅ | `self._current_model = new_model` |
| **Client 儲存模型** | ✅ | `self.model_name = model_name` |
| **Request 使用模型** | ✅ | `request_body["model"] = model` |
| **錯誤處理** | ✅ | 失敗時恢復舊模型 |
| **執行緒安全** | ✅ | 使用 async lock |
| **資源清理** | ✅ | `await client.release()` |

### 6.2 Ollama 模型可用性

**已下載模型** (使用 `ollama list` 驗證):
```
✅ gpt-oss:20b          (13 GB)
✅ deepseek-r1:7b       (4.7 GB)
✅ phi4-mini:3.8b       (2.5 GB)
```

**結論**: 所有選單中的模型都已下載，可以切換。

### 6.3 運行時驗證建議

由於服務器目前未運行，無法進行實時 `ollama ps` 驗證。建議執行以下測試：

#### 測試步驟：

1. **啟動 DocAI 服務器**:
   ```bash
   cd /Users/xrickliao/WorkSpaces/Work/Projects/DocAI
   ./start_system.sh
   ```

2. **開啟瀏覽器前往 Skill Chat 頁面**:
   ```
   http://localhost:10087/skill
   ```

3. **初始狀態檢查**:
   ```bash
   # 終端機 1: 監控 Ollama 運行的模型
   watch -n 1 'ollama ps'
   ```

4. **執行切換測試**:
   - 初始模型應該是 **gpt-oss:20b** (預設)
   - 點擊模型選擇器，選擇 **deepseek-r1:7b**
   - 觀察 `ollama ps` 輸出

5. **預期結果**:
   ```bash
   # 切換前 (gpt-oss:20b)
   NAME          ID            SIZE    PROCESSOR    CONTEXT    UNTIL
   gpt-oss:20b   aa4295ac10c3  13 GB   100% GPU     2048/2048  4 minutes from now

   # 切換後 (deepseek-r1:7b)
   NAME              ID            SIZE    PROCESSOR    CONTEXT    UNTIL
   deepseek-r1:7b    755ced02ce7b  4.7 GB  100% GPU     2048/2048  4 minutes from now
   ```

6. **發送查詢驗證**:
   - 輸入問題：「你是什麼模型？」
   - 模型應該回答 **DeepSeek-R1** 相關資訊

7. **切換到第三個模型**:
   - 選擇 **phi4-mini:3.8b**
   - 再次檢查 `ollama ps`
   - 應該看到 **phi4-mini:3.8b** 載入

#### API 直接測試（可選）:

```bash
# 測試切換到 deepseek-r1:7b
curl -X POST http://localhost:10087/api/v1/llm/switch \
  -H "Content-Type: application/json" \
  -d '{"model_name": "deepseek-r1:7b"}' | jq

# 預期輸出:
# {
#   "success": true,
#   "old_model": "gpt-oss:20b",
#   "new_model": "deepseek-r1:7b",
#   "message": "Successfully switched from gpt-oss:20b to deepseek-r1:7b"
# }

# 立即檢查 Ollama
ollama ps

# 測試切換到 phi4-mini:3.8b
curl -X POST http://localhost:10087/api/v1/llm/switch \
  -H "Content-Type: application/json" \
  -d '{"model_name": "phi4-mini:3.8b"}' | jq
```

---

## 7. 結論

### ✅ 模型切換功能完整性確認

**程式碼審查結論**:
1. **前端邏輯**: ✅ 正確傳遞完整模型名稱
2. **API Endpoint**: ✅ 正確接收並調用管理器
3. **LLMManager**: ✅ 正確更新 `_current_model` 狀態並創建新 client
4. **LLMProviderClient**: ✅ 正確儲存並使用 `model_name`
5. **Ollama API**: ✅ 請求中包含正確的模型名稱

**關鍵證據**:
- `manager.py` Line 124: `self._current_model = new_model` ✅
- `client.py` Line 52: `self.model_name = model_name` ✅
- `client.py` Line 115: `model = model or self.model_name` ✅
- `client.py` Line 118: `"model": model` ✅

**答案**:
> **是的，切換模型的程式碼會真的切換到新選擇的大語言模型。**

每次切換時：
1. 舊 LLMProviderClient 被釋放
2. 新 LLMProviderClient 創建並儲存新模型名稱
3. 下次 chat completion 請求會使用新模型名稱
4. Ollama API 會載入並執行新模型

### 驗證方法

**程式碼層面**: ✅ 已完成
**運行時層面**: ⏳ 需要啟動服務器後使用 `ollama ps` 驗證

建議按照上述「運行時驗證建議」進行實際測試。

---

**報告結束**
