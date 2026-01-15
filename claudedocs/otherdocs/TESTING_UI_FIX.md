# UI 渲染修復測試指南

**狀態**: ✅ 修復已應用，系統已重啟（PID: 513306）

---

## 🔴 測試前必須執行的步驟

### 1. 硬刷新瀏覽器（非常重要！）

JavaScript 文件可能被瀏覽器緩存，**必須**清除緩存：

**方法 1: 硬刷新**
- Windows/Linux: `Ctrl + F5` 或 `Ctrl + Shift + R`
- Mac: `Cmd + Shift + R`

**方法 2: 開發者工具強制刷新**
1. 按 `F12` 開啟開發者工具
2. 右鍵點擊瀏覽器的刷新按鈕
3. 選擇「清空快取並強制重新整理」

**方法 3: 清除網站資料（最徹底）**
1. 按 `F12` → `Application` tab (Chrome) 或 `Storage` tab (Firefox)
2. 點擊左側 `Storage` → `Clear site data`
3. 刷新頁面

---

## 📝 測試步驟

### Step 1: 開啟瀏覽器 Console

1. 開啟 `http://localhost:8000`
2. 按 `F12` 開啟開發者工具
3. 切換到 `Console` tab
4. 確保可以看到 console 訊息

### Step 2: 上傳 PDF 文件

1. 點擊「新增來源」按鈕
2. 選擇任意 PDF 文件
3. 確認上傳成功（側邊欄顯示文件名，有 checkbox ✅）

### Step 3: 發送測試問題

在聊天輸入框輸入：
```
請總結這份文件
```

點擊發送按鈕 ✈️

---

## ✅ 預期行為（修復後）

### 階段 1: 初始化（1-2秒）
```
╔══════════════════════════════╗
║ Waiting for LLM response...  ║  ← 顯示等待訊息
║ (may take 30-60s on first    ║
║  request)                     ║
╚══════════════════════════════╝
```

**Console 輸出**:
```
[DocAI] Starting SSE stream...
[DocAI] Response received: 200 OK
```

### 階段 2: 第一個 Token 到達（~3-5秒）
```
╔══════════════════════════════╗
║ 網                           ║  ← ✅ 立即開始顯示
╚══════════════════════════════╝
```

**Console 輸出**（關鍵！）:
```
[DocAI] Handling event: markdown_token {token: "網"}
[DocAI] Removed waiting indicator on first token  ← 🎯 必須看到這行！
```

### 階段 3: Progressive Rendering（持續 10-30秒）
```
╔══════════════════════════════╗
║ 網絡中的預測編碼理論，旨在   ║  ← ✅ 逐字顯示
║ 模擬生物神經元如何從未見過...║
║                              ║
║ **主要觀點**:                ║
║ 1. CPC (van den Oord...)     ║
╚══════════════════════════════╝
```

**Console 輸出**:
```
[DocAI] Handling event: markdown_token {token: "絡"}
[DocAI] Handling event: markdown_token {token: "中的"}
[DocAI] Handling event: markdown_token {token: "預"}
...（持續接收）
```

### 階段 4: 完成
```
╔══════════════════════════════════════════════════╗
║ (完整的多行 markdown 內容)                        ║
║                                                  ║
║ 根據您指定的範圍，以下是這些元數據中關於自監督學習  ║
║ 技術的一般概述：                                  ║
║                                                  ║
║ 1. **CPC (van den Oord et al., 2018)**: ...     ║
║ 2. **CMC (Bardes et al., 2021)**: ...           ║
║ 3. **BYOL**: ...                                ║
║ ...                                              ║
╚══════════════════════════════════════════════════╝
```

**Console 輸出**:
```
[DocAI] Chat completed successfully
```

---

## ❌ 錯誤行為（修復前）

如果看到以下情況，表示修復**未生效**：

### 錯誤 1: "Waiting..." 永遠不消失
```
╔══════════════════════════════╗
║ Waiting for LLM response...  ║  ← ❌ 一直顯示
║ (may take 30-60s on first    ║
║  request)                     ║
╚══════════════════════════════╝
```

**Console 正常**:
```
[DocAI] Handling event: markdown_token {token: "網"}
[DocAI] Handling event: markdown_token {token: "絡"}
...（200+ 事件）
```

**原因**: JavaScript 文件被瀏覽器緩存
**解決**: 硬刷新瀏覽器（`Ctrl+F5`）

### 錯誤 2: Console 沒有 "Removed waiting indicator" 日誌
```
[DocAI] Handling event: markdown_token {token: "網"}
```

**缺少**:
```
[DocAI] Removed waiting indicator on first token  ← ❌ 沒有這行
```

**原因**: 舊版 JavaScript
**解決**:
1. 硬刷新瀏覽器
2. 確認系統已重啟（PID 應該是新的）
3. 清除瀏覽器緩存

---

## 🔍 故障排除

### 問題 1: 仍然看到 "Waiting..." 不消失

**檢查清單**:
- [ ] 已執行硬刷新（`Ctrl+F5`）
- [ ] Console 顯示 "[DocAI] Removed waiting indicator on first token"
- [ ] 系統已重啟（檢查 PID）
- [ ] JavaScript 文件時間戳已更新

**驗證 JavaScript 更新**:
```bash
# 檢查文件修改時間
ls -l static/js/docai-client.js

# 應該顯示最新時間（2025-11-05 15:xx）
```

**強制清除緩存**:
1. F12 → Application → Storage → Clear site data
2. 關閉所有 `localhost:8000` 標籤頁
3. 重新開啟 `http://localhost:8000`

### 問題 2: Console 沒有任何 markdown_token 事件

**可能原因**:
1. LLM 服務未運行
2. Backend 錯誤

**檢查**:
```bash
# 檢查 Ollama
curl http://localhost:11434/api/tags

# 檢查 Backend 日誌
tail -50 logs/server.log
```

### 問題 3: Console 有 markdown_token 但頁面空白

**可能原因**:
1. CSS 樣式問題
2. marked.js 未載入

**檢查 Console 錯誤**:
```
# 應該沒有這類錯誤
[DocAI] marked library not loaded!
```

**驗證 marked.js**:
```javascript
// 在 Console 執行
typeof marked
// 應該返回: "object" 或 "function"
```

---

## 📊 完整的成功測試日誌範例

```
[DocAI] Starting SSE stream...
[DocAI] Response received: 200 OK
[DocAI SSE] Handling event: progress {"phase":1,"phase_name":"Query Understanding",...}
[DocAI SSE] Handling event: progress {"phase":1,"phase_name":"Query Understanding","progress":100,...}
[DocAI SSE] Handling event: progress {"phase":2,"phase_name":"Parallel Retrieval",...}
[DocAI SSE] Handling event: progress {"phase":2,"phase_name":"Parallel Retrieval","progress":100,...}
[DocAI SSE] Handling event: progress {"phase":3,"phase_name":"Context Assembly",...}
[DocAI SSE] Handling event: progress {"phase":3,"phase_name":"Context Assembly","progress":100,...}
[DocAI SSE] Handling event: progress {"phase":4,"phase_name":"Response Generation",...}
[DocAI SSE] Handling event: markdown_token {"token":"網"}
[DocAI] Removed waiting indicator on first token  ← 🎯 關鍵日誌
[DocAI SSE] Handling event: markdown_token {"token":"絡"}
[DocAI SSE] Handling event: markdown_token {"token":"中的"}
... (200+ markdown_token 事件)
[DocAI SSE] Handling event: progress {"phase":4,"progress":100,"message":"Answer generation complete"}
[DocAI SSE] Handling event: progress {"phase":5,"phase_name":"Post Processing",...}
[DocAI SSE] Handling event: complete {"session_id":"...","query":"請總結這份文件","answer":"..."}
[DocAI] Chat completed successfully
```

---

## 🎯 修復摘要

**修改文件**: [static/js/docai-client.js:505-509](../static/js/docai-client.js#L505-L509)

**修改內容**: 在第一個 `markdown_token` 到達時移除 `progressIndicator`

**修改前**:
```javascript
case 'markdown_token':
    const token = eventData.token || '';
    if (!token) break;

    this.tokenBuffer += token;  // 直接累積

    if (!this.rafScheduled) {
        this.rafScheduled = true;
        requestAnimationFrame(() => {
            this.rafScheduled = false;
            this.flushTokenBuffer(aiBubble);
        });
    }
    break;
```

**修改後**:
```javascript
case 'markdown_token':
    const token = eventData.token || '';
    if (!token) break;

    // FIX: Remove "Waiting..." indicator on first token
    if (this.tokenBuffer === '' && progressIndicator && progressIndicator.parentNode) {
        progressIndicator.remove();
        console.log('[DocAI] Removed waiting indicator on first token');
    }

    this.tokenBuffer += token;

    if (!this.rafScheduled) {
        this.rafScheduled = true;
        requestAnimationFrame(() => {
            this.rafScheduled = false;
            this.flushTokenBuffer(aiBubble);
        });
    }
    break;
```

---

## ✅ 測試完成確認

測試成功標準：
- [ ] 硬刷新瀏覽器完成
- [ ] Console 顯示 "[DocAI] Removed waiting indicator on first token"
- [ ] "Waiting..." 訊息在第一個 token 後消失
- [ ] Markdown 內容逐字即時顯示
- [ ] 完整內容正確渲染（多行文字、粗體、列表等）
- [ ] 無 JavaScript 錯誤

**完成日期**: _______________
**測試人員**: _______________
