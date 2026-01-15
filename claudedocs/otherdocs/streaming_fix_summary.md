# OPMP Streaming 修復總結

**日期**: 2025-11-05
**狀態**: 🔴 診斷完成，等待最終修復

---

## ✅ 核心發現

### 1. Streaming **完全正常工作**！

**證據來自用戶提供的瀏覽器調試**：
```
test_sse.html - Event Log:
  Chunk #1 received (129 bytes) ✅
  Chunk #2 received (293 bytes) ✅
  Chunk #3 received (268 bytes) ✅
  Total: 5 chunks, 8 events successfully parsed
```

**結論**：
- ✅ Backend SSE streaming 正常
- ✅ Frontend 能接收 chunks
- ✅ SSE parsing 邏輯正確
- ✅ Event handling 正確
- ❌ **唯一問題**：LLM Provider 返回 HTTP 404

---

## 🔴 根本原因：LLM Provider URL 錯誤

### 問題診斷

**Server log 顯示**：
```
HTTP Request: POST http://localhost:11434/chat/completions "HTTP/1.1 404 Not Found"
                                          ^^^^^^^^^^^^^^
                                          缺少 /v1 前綴
```

**正確的 URL 應該是**：
```
POST http://localhost:11434/v1/chat/completions
                              ^^^ 需要 /v1
```

### 配置檢查

**1. .env 文件**（✅ 正確）：
```bash
LLM_PROVIDER_BASE_URL=http://localhost:11434/v1
```

**2. config.py**（✅ 正確）：
```python
LLM_PROVIDER_BASE_URL: str = "http://localhost:11434/v1"
```

**3. 實際運行時**（❌ 錯誤）：
```python
settings.LLM_PROVIDER_BASE_URL: http://localhost:11434  # 缺少 /v1
```

### 根本原因

**環境變量覆蓋**：
```bash
$ env | grep LLM_PROVIDER_BASE_URL
LLM_PROVIDER_BASE_URL=http://localhost:11434  # 系統環境變量
```

**Pydantic-settings 優先級**：
1. 環境變量（最高優先級）← 問題在這裡！
2. .env 文件
3. 類定義的默認值

即使 .env 有 `/v1`，系統環境變量會覆蓋它。

---

## 🔧 修復方案

### 方案 A: 清除環境變量（推薦）

**步驟**：
1. 找到設置環境變量的地方（~/.bashrc, ~/.profile, /etc/environment）
2. 刪除 `LLM_PROVIDER_BASE_URL=http://localhost:11434` 這一行
3. 重新載入配置：`source ~/.bashrc`
4. 重啟 server

**如果找不到**，使用臨時解決方案：
```bash
# 在啟動 server 前強制設置正確值
export LLM_PROVIDER_BASE_URL="http://localhost:11434/v1"
docaienv/bin/python main.py
```

### 方案 B: 修改代碼強制使用 .env（不推薦）

修改 `app/core/config.py`:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix=""  # 可以添加 prefix 避免衝突
    )

    # 在 __init__ 中強制讀取 .env
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Force reload from .env if environment variable doesn't have /v1
        if not self.LLM_PROVIDER_BASE_URL.endswith('/v1'):
            from dotenv import dotenv_values
            env_vals = dotenv_values(".env")
            if 'LLM_PROVIDER_BASE_URL' in env_vals:
                self.LLM_PROVIDER_BASE_URL = env_vals['LLM_PROVIDER_BASE_URL']
```

### 方案 C: 直接在代碼中硬編碼（臨時）

修改 `app/Providers/llm_provider/client.py`:
```python
def __init__(self, base_url: Optional[str] = None, ...):
    # Force correct URL if missing /v1
    if base_url and not base_url.endswith('/v1'):
        base_url = f"{base_url}/v1"

    self.base_url = base_url or settings.LLM_PROVIDER_BASE_URL
    if not self.base_url.endswith('/v1'):
        self.base_url = f"{self.base_url}/v1"
```

---

## 📝 Double-Buffer 方案討論

### 用戶原始問題理解修正

用戶提到 "double-buffer" 是因為認為：
- Backend 發送數據
- Frontend 收不到
- 可能是 buffering 問題

**但實際診斷證明**：
- ✅ Frontend **能夠**接收數據
- ✅ Chunks 正常傳輸
- ✅ Events 正確解析
- ❌ 問題在 LLM Provider 404 錯誤，導致沒有 markdown tokens

### Double-Buffer 不適用

**原因**：
1. 問題不是 buffering，是 URL 錯誤導致 404
2. Backend → Frontend 傳輸正常（證據：8 個 progress events 都收到）
3. 缺少的是 LLM 的 markdown_token events（因為 LLM 請求失敗）

---

## 🧪 修復後的測試步驟

### 1. 修復 URL

選擇上述方案 A/B/C 之一修復

### 2. 驗證配置

```bash
docaienv/bin/python << 'EOF'
from app.core.config import settings
from app.Providers.llm_provider.client import get_llm_provider

client = get_llm_provider()
endpoint = f"{client.base_url}/chat/completions"

print(f"Base URL: {client.base_url}")
print(f"Full endpoint: {endpoint}")

if "/v1/" in endpoint:
    print("✅ Configuration CORRECT")
else:
    print("❌ Configuration WRONG - still missing /v1/")
EOF
```

### 3. 測試 LLM Provider

```bash
curl -X POST http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ollama" \
  -d '{
    "model": "phi4-mini:3.8b",
    "messages": [{"role": "user", "content": "test"}],
    "stream": true
  }' | head -5
```

預期：應該看到 LLM streaming tokens，而不是 404

### 4. 測試完整 Streaming

打開瀏覽器：
- 訪問 http://localhost:8000/static/test_sse.html
- 點擊 "Test SSE Streaming"
- 觀察：應該看到 markdown_token events，而不是 error event

### 5. 測試實際應用

- 上傳 PDF 文件
- 發送聊天問題
- 觀察：應該看到 token-by-token streaming 顯示

---

## 📊 完整數據流驗證

**修復前**（❌ 404 錯誤）：
```
Phase 1-3: progress events ✅ 正常
↓
Phase 4: LLM generation
  → POST http://localhost:11434/chat/completions
  ← HTTP 404 Not Found ❌
↓
error event: {"error": "HTTP 404"} ❌
↓
Stream 結束，無 markdown tokens
```

**修復後**（✅ 正常）：
```
Phase 1-3: progress events ✅
↓
Phase 4: LLM generation
  → POST http://localhost:11434/v1/chat/completions ✅
  ← HTTP 200 OK, streaming tokens...
  ← data: {"choices":[{"delta":{"content":"根據"}}]}
  ← data: {"choices":[{"delta":{"content":"您"}}]}
  ← data: {"choices":[{"delta":{"content":"挑選"}}]}
  ...
↓
markdown_token events ✅
↓
complete event ✅
↓
Frontend displays token-by-token ✅
```

---

## 🎯 關鍵結論

### 問題**不在**：
- ❌ Frontend SSE parsing
- ❌ Backend SSE formatting
- ❌ Browser buffering
- ❌ EventSourceResponse configuration
- ❌ Network transmission
- ❌ OPMP architecture

### 問題**在於**：
- ✅ 環境變量覆蓋配置
- ✅ LLM Provider URL 缺少 /v1
- ✅ 導致 404 錯誤
- ✅ 沒有 LLM tokens 生成

### 修復**只需要**：
- ✅ 清除錯誤的環境變量
- ✅ 或強制使用正確的 URL
- ✅ 重啟 server
- ✅ 驗證 endpoint 包含 /v1/

---

## 📋 下一步行動

**立即**：
1. 找出並清除系統環境變量 `LLM_PROVIDER_BASE_URL`
2. 或使用方案 C 在代碼中強制添加 /v1
3. 重啟 server
4. 執行測試步驟 1-5

**確認修復**：
- 瀏覽器應該看到 markdown_token events
- Frontend 應該 token-by-token 顯示 LLM 回應
- 無 404 錯誤

**文檔**：
- 記錄環境變量問題以防再次發生
- 更新部署文檔說明正確的環境配置
