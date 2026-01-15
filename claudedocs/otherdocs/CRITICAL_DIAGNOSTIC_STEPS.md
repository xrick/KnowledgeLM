# 🔴 關鍵診斷步驟 - Streaming 顯示問題

**問題**: Backend streaming 正常，但前端頁面不顯示內容

---

## ⚠️ 重要提醒

您截圖中右側是 **Terminal（服務器日誌）**，不是**瀏覽器 Console**！

我們需要檢查的是**瀏覽器的開發者工具 Console**，不是 Terminal。

---

## 📋 診斷步驟 1: 打開診斷頁面

### 1.1 訪問診斷工具

在瀏覽器訪問：
```
http://localhost:8000/static/diagnostic.html
```

這個頁面會自動檢測：
- ✅ JavaScript 是否正常運行
- ✅ marked.js 是否載入
- ✅ DocAI Client 是否載入
- ✅ Streaming 模式是否啟用

### 1.2 執行 SSE 測試

1. 點擊頁面上的「測試 SSE Streaming」按鈕
2. 觀察是否有 markdown tokens 顯示
3. 查看是否有渲染的 markdown 內容

**預期結果**:
- 應該看到 "Token #1: ...", "Token #2: ..." 等
- 最後應該有渲染的 markdown 內容顯示

---

## 📋 診斷步驟 2: 檢查瀏覽器 Console

### 2.1 打開瀏覽器開發者工具

**Chrome / Edge**:
- 按 `F12`
- 或右鍵點擊頁面 → 「檢查」

**Firefox**:
- 按 `F12`
- 或右鍵點擊頁面 → 「檢查元素」

**Safari**:
- 先啟用開發選單：Preferences → Advanced → Show Develop menu
- 按 `Cmd + Option + I`

### 2.2 切換到 Console Tab

在開發者工具中找到 「**Console**」 tab（不是 Elements, Network 等）

### 2.3 清除 Console 並重新測試

1. 在 Console 中點擊 🚫 圖示清除所有訊息
2. 回到主頁：`http://localhost:8000`
3. 硬刷新頁面：`Ctrl + F5` (Windows/Linux) 或 `Cmd + Shift + R` (Mac)
4. 上傳 PDF 並發送問題

### 2.4 查找關鍵日誌

在 Console 中應該看到：

**正常情況**:
```
[DocAI] Starting SSE stream...
[DocAI] Response received: 200 OK
[DocAI SSE] Handling event: progress ...
[DocAI SSE] Handling event: markdown_token {token: "網"}
[DocAI] Removed waiting indicator on first token  ← 🎯 關鍵！
[DocAI SSE] Handling event: markdown_token {token: "絡"}
...
[DocAI] Chat completed successfully
```

**異常情況 1 - 沒有任何 Console 輸出**:
- 可能是 JavaScript 錯誤阻止執行
- 檢查 Console 是否有紅色錯誤訊息

**異常情況 2 - 有錯誤訊息**:
```
Uncaught ReferenceError: marked is not defined
```
或
```
Uncaught TypeError: Cannot read property 'parse' of undefined
```
- 表示 marked.js 沒有正確載入

**異常情況 3 - 沒有 "Removed waiting indicator" 訊息**:
- JavaScript 文件被瀏覽器緩存
- 需要強制刷新

---

## 📋 診斷步驟 3: 檢查網絡請求

### 3.1 切換到 Network Tab

在開發者工具中找到 「**Network**」 tab

### 3.2 重新載入頁面

按 `Ctrl + R` 或點擊刷新按鈕

### 3.3 檢查 JavaScript 文件

在 Network tab 中搜尋：
- `docai-client.js`
- `marked.min.js`

點擊文件查看：
- **Status**: 應該是 200
- **Size**:
  - `docai-client.js` 約 26 KB
  - `marked.min.js` 約 35 KB
- **Time**: 應該有載入時間

**如果看到 304 Not Modified**:
- 表示使用了緩存版本
- 需要硬刷新：`Ctrl + F5`

**如果看到 404 Not Found**:
- 文件路徑錯誤或文件不存在
- 回報這個問題

---

## 📋 診斷步驟 4: 檢查 DOM 元素

### 4.1 切換到 Elements Tab

在開發者工具中找到 「**Elements**」 tab

### 4.2 發送測試問題

在主頁面上傳 PDF 並發送問題

### 4.3 檢查 AI bubble 元素

1. 在 Elements tab 中，找到 `.chat-display-area`
2. 展開查看是否有 `.chat-bubble.ai` 元素
3. 展開 AI bubble 查看內部結構

**預期結構**（修復後）:
```html
<div class="chat-bubble ai">
  <div class="markdown-content">
    <p>網絡中的預測編碼理論...</p>
    <p><strong>主要觀點</strong>:</p>
    ...
  </div>
</div>
```

**異常結構 1**（修復前）:
```html
<div class="chat-bubble ai">
  <div class="progress-indicator">
    ...Waiting for LLM response...
  </div>
  <div class="markdown-content">  ← 被上面覆蓋
    ...
  </div>
</div>
```

**異常結構 2**（沒有內容）:
```html
<div class="chat-bubble ai">
  <div class="progress-indicator">
    ...Waiting for LLM response...
  </div>
  <!-- 沒有 markdown-content -->
</div>
```

---

## 📋 診斷步驟 5: JavaScript 環境測試

### 5.1 在 Console 執行測試命令

在瀏覽器 Console 中輸入以下命令（一行一行執行）：

```javascript
// Test 1: Check marked.js
typeof marked
// 預期輸出: "object" 或 "function"

// Test 2: Check marked.parse
typeof marked.parse
// 預期輸出: "function"

// Test 3: Test markdown parsing
marked.parse('**粗體** 和 *斜體*')
// 預期輸出: "<p><strong>粗體</strong> 和 <em>斜體</em></p>\n"

// Test 4: Check DocAI Client
typeof window.docaiClient
// 預期輸出: "object"

// Test 5: Check streaming mode
window.docaiClient.useStreaming
// 預期輸出: true

// Test 6: Check DOM elements
document.querySelector('.chat-display-area')
// 預期輸出: <div class="chat-display-area">...</div>
```

**記錄所有輸出**並提供給我。

---

## 📋 診斷步驟 6: 強制清除所有緩存

### 6.1 清除網站資料（最徹底）

**Chrome / Edge**:
1. 按 `F12` 打開開發者工具
2. 右鍵點擊瀏覽器地址欄左側的刷新按鈕
3. 選擇「清空快取並強制重新整理」

**或者**:
1. `F12` → `Application` tab
2. 左側找到 `Storage`
3. 點擊 `Clear site data`
4. 勾選所有選項
5. 點擊 `Clear site data` 按鈕
6. 關閉所有 `localhost:8000` 標籤頁
7. 重新開啟 `http://localhost:8000`

### 6.2 停用緩存（開發模式）

在開發者工具中：
1. `F12` → `Network` tab
2. 勾選 「**Disable cache**」
3. 保持開發者工具開啟
4. 刷新頁面

---

## 🎯 診斷檢查清單

請執行以下檢查並記錄結果：

- [ ] **步驟 1**: 訪問 `http://localhost:8000/static/diagnostic.html`
  - 結果: _______________

- [ ] **步驟 2**: 打開瀏覽器 Console (F12 → Console tab)
  - 是否看到 Console 訊息? _______________
  - 是否有錯誤訊息? _______________

- [ ] **步驟 3**: 檢查 Network tab
  - `docai-client.js` Status: _______________
  - `marked.min.js` Status: _______________

- [ ] **步驟 4**: 檢查 Elements tab
  - AI bubble 是否有 `.markdown-content`? _______________
  - AI bubble 是否有 `.progress-indicator`? _______________

- [ ] **步驟 5**: JavaScript 環境測試
  - `typeof marked`: _______________
  - `window.docaiClient.useStreaming`: _______________

- [ ] **步驟 6**: 強制清除緩存完成
  - 已清除? _______________

---

## 📸 需要的截圖

請提供以下截圖：

1. **診斷頁面** (`http://localhost:8000/static/diagnostic.html`)
   - 整個頁面的截圖

2. **瀏覽器 Console**
   - F12 → Console tab
   - 顯示所有 `[DocAI]` 開頭的訊息

3. **Network tab**
   - 顯示 `docai-client.js` 和 `marked.min.js` 的狀態

4. **Elements tab**
   - 展開 `.chat-bubble.ai` 的 DOM 結構

---

## 🔧 常見問題解答

### Q1: 我看不到瀏覽器 Console
**A**: 按 `F12` → 點擊 「Console」 tab（不是 Terminal）

### Q2: Console 說 "marked is not defined"
**A**:
1. 檢查 Network tab 中 `marked.min.js` 是否 200 OK
2. 強制刷新：`Ctrl + F5`
3. 清除緩存並重試

### Q3: Console 完全沒有 [DocAI] 訊息
**A**:
1. 檢查是否有 JavaScript 錯誤（紅色訊息）
2. 確認 `docai-client.js` 是否載入（Network tab）
3. 檢查是否在正確的頁面（`http://localhost:8000`）

### Q4: 看到 "Removed waiting indicator" 但頁面還是沒顯示
**A**:
1. 檢查 Elements tab 中 `.markdown-content` 是否存在
2. 檢查 CSS 是否隱藏了元素
3. 執行 Console 測試確認 `marked.parse()` 正常

---

## 🚀 下一步

完成所有診斷步驟後，請提供：

1. ✅ 診斷檢查清單的結果
2. ✅ 所需的 4 張截圖
3. ✅ JavaScript 環境測試的輸出
4. ✅ 任何錯誤訊息

這樣我才能準確定位問題並提供正確的解決方案。
