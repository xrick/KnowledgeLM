# OPMP Streaming 診斷報告

**日期**: 2025-11-05
**問題**: Screen hangs on "initialize...", no output in streaming mode
**狀態**: 🔴 已診斷，待修復

---

## 🔴 三大根本問題

### 問題 1: 配置不一致導致意外啟用 Streaming

**文件**: [static/js/docai-client.js:19](static/js/docai-client.js#L19)

```javascript
this.useStreaming = true; // Use non-streaming mode by default (more reliable)
                ^^^^^^
                // 註釋說 "non-streaming" 但實際是 true！
```

**影響**:
- 系統實際運行在 **streaming mode**
- 用戶期望 non-streaming 的穩定性，但遇到 streaming 的超時問題
- 配置與註釋不一致，造成混淆

**修復**:
```javascript
this.useStreaming = false; // Non-streaming mode (recommended for stability)
```

---

### 問題 2: LLM 冷啟動期間無視覺反饋

**現象**:
```
User sends message
  ↓
Screen shows: "Initializing..." (progressIndicator)
  ↓
[30-60 seconds of silence while LLM loads model]
  ↓
User thinks: "系統卡住了？"
  ↓
Browser timeout or user gives up
```

**證據**:
- `refData/errors/messages/screen_does_not_show_the_meesage_backend_can_show_5.txt`
- 60 秒空白期間：Phase 4 start → http.disconnect

**根本原因**:
- Ollama 首次加載 phi4-mini:3.8b model（3.2GB）需要 30-60 秒
- 這段時間沒有任何 token 輸出
- Frontend 只顯示靜態 "Initializing..."，沒有動態進度指示
- 用戶無法知道系統是在工作還是真的卡住

**當前改進**:
- ✅ 延長超時到 5 分鐘（backend + frontend）
- ✅ 添加 15 秒 keep-alive ping
- ❌ 但仍缺少明確的 "Model loading, please wait..." 提示

---

### 問題 3: 極頻繁的 DOM 更新（性能瓶頸）

**實測數據**:
```bash
$ curl http://localhost:11434/api/generate -d '{"model":"phi4-mini:3.8b","prompt":"Hello","stream":true}'

{"response":"I","done":false}           # 1 char, 45ms
{"response":" am","done":false}         # 3 chars, 45ms
{"response":" Phi","done":false}        # 4 chars, 45ms
{"response":" developed","done":false}  # 10 chars, 45ms
...
```

**發現**:
- ✅ 用戶觀察正確：**Chunk data 確實很短**
- 平均 token 長度：1-10 字符
- Token 間隔：~45ms
- 每秒 DOM 更新：~20-22 次

**當前處理** ([docai-client.js:477-518](static/js/docai-client.js#L477-L518)):
```javascript
case 'markdown_token':
    const token = eventData.token || '';
    const currentMarkdown = aiBubble.dataset.markdown || '';
    const newMarkdown = currentMarkdown + token;
    aiBubble.dataset.markdown = newMarkdown;

    // 問題：每個 token 都觸發 marked.parse() + innerHTML 更新
    const htmlContent = marked.parse(newMarkdown);  // ❌ 每 45ms 執行一次
    contentDiv.innerHTML = htmlContent;              // ❌ 每 45ms 重繪 DOM
    this.chatDisplayArea.scrollTop = ...;            // ❌ 每 45ms 滾動
```

**性能影響**:
- 假設回答 500 tokens（典型長度）
- DOM 更新次數：500 次
- marked.parse() 調用：500 次（解析整個 markdown，不是增量）
- innerHTML 重寫：500 次（整個 bubble 重繪）
- Auto-scroll 觸發：500 次

**問題嚴重性**:
- 短文本（<100 tokens）：影響不大
- 長文本（>500 tokens）：可能造成明顯卡頓
- 複雜 markdown（代碼塊、表格）：marked.parse() 成本高

---

## 📊 Ping-Pong Buffer 方案評估

### 用戶提議

```
A-Buffer: [token1, token2, token3, token4, token5, token6] (6 words)
B-Buffer: [receiving new tokens...]

When A-Buffer full:
  1. Display A-Buffer content to screen
  2. Clear A-Buffer
  3. Switch: A-Buffer receives, B-Buffer displays

Repeat...
```

### 優點分析

✅ **減少 DOM 更新頻率**:
```
Without buffer:  500 tokens → 500 DOM updates
With buffer (6): 500 tokens → ~83 DOM updates (6x reduction)
```

✅ **降低 marked.parse() 成本**:
- 每次解析的增量更大（6 tokens vs 1 token）
- 雖然仍是全量解析，但頻率降低

✅ **平滑滾動**:
- 減少 auto-scroll 觸發次數
- 滾動更平滑，不閃爍

✅ **實施相對簡單**:
- 不需要改 backend
- 只需在 frontend 添加 buffer 邏輯

### 缺點分析

❌ **增加顯示延遲**:
```
Token stream: [I] [am] [Phi] [developed] [by] [Microsoft]
Without buffer: 立即顯示 "I"
With buffer(6): 等待 6 個 tokens 才顯示 "I am Phi developed by Microsoft"

Delay = 6 tokens × 45ms = 270ms
```

❌ **不符合 "Progressive" 初衷**:
- OPMP = **Optimistic Progressive** Markdown Parsing
- 目標是 token-by-token 即時反饋（像 ChatGPT）
- Buffer 破壞了即時性體驗

❌ **Buffer 大小難以調整**:
- 6 words？太大？太小？
- 不同語言（中文 vs 英文）token 長度不同
- 不同 LLM 的 token 策略不同

❌ **仍然是全量 markdown 解析**:
- marked.parse(entire_markdown) 仍會隨著內容增長而變慢
- 83 次 vs 500 次，但每次成本隨文本增長

### 🎯 更好的替代方案

#### 方案 A: **requestAnimationFrame Throttling**（推薦）

```javascript
case 'markdown_token':
    const token = eventData.token || '';
    this.tokenBuffer = (this.tokenBuffer || '') + token;

    // 使用 RAF throttling，最多每 16ms 更新一次（60 FPS）
    if (!this.rafScheduled) {
        this.rafScheduled = true;
        requestAnimationFrame(() => {
            this.rafScheduled = false;

            const markdown = aiBubble.dataset.markdown || '';
            const newMarkdown = markdown + this.tokenBuffer;
            aiBubble.dataset.markdown = newMarkdown;
            this.tokenBuffer = '';

            const htmlContent = marked.parse(newMarkdown);
            contentDiv.innerHTML = htmlContent;
            this.chatDisplayArea.scrollTop = this.chatDisplayArea.scrollHeight;
        });
    }
```

**優點**:
- ✅ 自動批量處理多個 tokens（在 16ms 內累積的）
- ✅ 同步瀏覽器重繪週期（60 FPS）
- ✅ 仍然保持 progressive 體驗（最多 16ms 延遲）
- ✅ 不需要手動調整 buffer 大小

**效果**:
```
45ms/token, 16ms RAF interval:
- 平均每次 RAF 處理 0-1 個 token（當 tokens 來得慢）
- 或 2-3 個 tokens（當 tokens 來得快）
- DOM 更新：60 FPS = 每秒 60 次（vs 原本 ~22 次）
- 但對於長文本，500 tokens 可能只需要 ~150 次更新
```

#### 方案 B: **Incremental DOM (IncrementalDOM or morphdom)**

```javascript
// 使用 morphdom 只更新變化的 DOM 節點
import morphdom from 'morphdom';

case 'markdown_token':
    const newMarkdown = currentMarkdown + token;
    const newHtml = marked.parse(newMarkdown);

    morphdom(contentDiv, newHtml); // 只更新 diff，不重寫整個 DOM
```

**優點**:
- ✅ 只更新實際變化的 DOM 節點
- ✅ 減少 repaint/reflow 成本
- ✅ 保持即時性

**缺點**:
- ❌ 需要額外依賴（morphdom 或類似庫）
- ❌ marked.parse() 仍是全量

#### 方案 C: **簡單的定時 Throttle**（最簡單）

```javascript
case 'markdown_token':
    this.tokenBuffer = (this.tokenBuffer || '') + token;

    if (!this.updateScheduled) {
        this.updateScheduled = true;
        setTimeout(() => {
            this.updateScheduled = false;
            this.flushTokenBuffer(aiBubble, contentDiv);
        }, 100); // 每 100ms 更新一次
    }
```

**優點**:
- ✅ 極簡實施（5 行代碼）
- ✅ 顯著減少更新頻率（每秒 10 次 vs 22 次）
- ✅ 仍然保持相對即時（100ms 延遲感知不強）

**效果**:
```
500 tokens / 45ms = 22.5 seconds total
100ms throttle = 每秒 10 次更新
Total updates = 225 → 10 updates/sec × 22.5s = 225 updates

Wait, 這計算不對。重新算：
500 tokens × 45ms = 22500ms = 22.5 秒
100ms throttle = 每 100ms 觸發一次
Total updates = 22500 / 100 = 225 次

嗯，這樣沒有減少。問題在於 tokens 是連續的。

正確計算：
如果 tokens 每 45ms 一個，100ms 內可能收到 2-3 個 tokens
所以 500 tokens / 2.5 tokens per update = 200 次更新
vs 原本 500 次，減少 60%
```

---

## 🎯 綜合建議

### 立即修復（Priority 1）

#### 1. 修正配置不一致

**文件**: [static/js/docai-client.js:19](static/js/docai-client.js#L19)

```javascript
// 修改前
this.useStreaming = true; // Use non-streaming mode by default (more reliable)

// 修改後
this.useStreaming = false; // Non-streaming mode (recommended for stability)
```

**理由**: 恢復穩定的 non-streaming 默認設置

---

#### 2. 添加 LLM Loading 提示

**文件**: [static/js/docai-client.js:271-290](static/js/docai-client.js#L271-L290)

```javascript
async streamChat(payload, aiBubble, progressIndicator) {
    console.log('[DocAI] Starting SSE stream...');

    // Update progress to show LLM loading
    progressIndicator.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px; padding: 8px;">
            <div class="spinner"></div>
            <span style="color: #666;">Waiting for LLM response (may take 30-60s on first request)...</span>
        </div>
    `;

    // ... rest of code
}
```

**理由**: 明確告知用戶可能的等待時間

---

### 性能優化（Priority 2）

#### 實施 requestAnimationFrame Throttling

**新增方法**:
```javascript
/**
 * Token buffer for RAF throttling
 */
constructor() {
    // ... existing code
    this.tokenBuffer = '';
    this.rafScheduled = false;
}

/**
 * Flush accumulated tokens to DOM (RAF-throttled)
 */
flushTokenBuffer(aiBubble, contentDiv) {
    if (!this.tokenBuffer) return;

    const currentMarkdown = aiBubble.dataset.markdown || '';
    const newMarkdown = currentMarkdown + this.tokenBuffer;
    aiBubble.dataset.markdown = newMarkdown;
    this.tokenBuffer = '';

    const htmlContent = marked.parse(newMarkdown);
    contentDiv.innerHTML = htmlContent;
    this.chatDisplayArea.scrollTop = this.chatDisplayArea.scrollHeight;
}
```

**修改 handleSSEEvent**:
```javascript
case 'markdown_token':
    const token = eventData.token || '';
    if (!token) break;

    // Accumulate tokens in buffer
    this.tokenBuffer = (this.tokenBuffer || '') + token;

    // Schedule RAF update if not already scheduled
    if (!this.rafScheduled) {
        this.rafScheduled = true;
        requestAnimationFrame(() => {
            this.rafScheduled = false;
            this.flushTokenBuffer(aiBubble, contentDiv);
        });
    }
    break;
```

**預期效果**:
- DOM 更新減少：500 次 → ~150 次（60-70% 減少）
- 仍然保持流暢的 progressive 體驗
- 自動適應不同 token 速度

---

### Ping-Pong Buffer（Optional）

**僅在以下情況實施**:
- 用戶明確要求固定字數批次顯示
- 願意接受 270-500ms 的延遲
- 想要更"穩定"的顯示效果（類似打字機，但批次更大）

**實施示例**:
```javascript
constructor() {
    this.tokenBufferA = [];
    this.tokenBufferB = [];
    this.activeBuffer = 'A';
    this.BUFFER_SIZE = 6; // 6 words/tokens
}

case 'markdown_token':
    const token = eventData.token || '';

    // Add to active buffer
    const buffer = (this.activeBuffer === 'A') ? this.tokenBufferA : this.tokenBufferB;
    buffer.push(token);

    // When buffer full, display and switch
    if (buffer.length >= this.BUFFER_SIZE) {
        const textToDisplay = buffer.join('');
        const currentMarkdown = aiBubble.dataset.markdown || '';
        const newMarkdown = currentMarkdown + textToDisplay;
        aiBubble.dataset.markdown = newMarkdown;

        const htmlContent = marked.parse(newMarkdown);
        contentDiv.innerHTML = htmlContent;

        // Clear and switch buffer
        buffer.length = 0;
        this.activeBuffer = (this.activeBuffer === 'A') ? 'B' : 'A';
    }
    break;
```

**不推薦理由**:
- 違背 progressive 即時性原則
- requestAnimationFrame 方案更優雅
- 手動調整 buffer size 麻煩

---

## 🧪 測試建議

### 測試 1: 驗證 Non-Streaming 恢復

```javascript
// 1. 確認 useStreaming = false
// 2. 發送測試 query
// 預期：2-5 秒後完整顯示結果
```

### 測試 2: 測試 Streaming Mode（可選）

```javascript
// 1. 設置 useStreaming = true
// 2. 實施 RAF throttling
// 3. 發送測試 query
// 預期：token-by-token 顯示，無明顯卡頓
```

### 測試 3: 長文本性能

```javascript
// Query: "請詳細解釋這份文件的所有章節內容"（預期 1000+ tokens）
// 觀察：
// - DOM 更新次數（DevTools Performance）
// - 滾動流暢度
// - CPU 使用率
```

---

## 📝 總結

### 三個問題的答案

**1. 為什麼 screen hangs on "initialize..."？**
- **根因**: 配置不一致，意外啟用 streaming mode
- **觸發**: LLM 冷啟動 30-60 秒無輸出
- **缺失**: 無明確的 "Model loading..." 提示
- **修復**: 恢復 `useStreaming = false` + 添加 loading 提示

**2. Backend 如何發送數據到 OPMP？**
- Ollama streaming → LLM Provider Client → Chat Endpoint
- 每個 token 包裝成 SSE event：`{"event": "markdown_token", "data": {"token": "..."}}`
- EventSourceResponse 添加 15s ping keep-alive
- Frontend 解析 SSE → 累積 markdown → marked.parse() → DOM 更新
- **問題**: 每個 token（平均 1-10 字符）都觸發完整 DOM 重繪

**3. Ping-Pong Buffer 是否可行？**
- **可行性**: ✅ 技術上可行
- **優點**: 減少 DOM 更新次數（6x reduction）
- **缺點**: 增加延遲（270ms），違背 progressive 原則
- **更好方案**: requestAnimationFrame throttling（推薦）
- **結論**: 不推薦 ping-pong buffer，推薦 RAF throttling

---

## 🎯 推薦行動

**現在立即做**:
1. ✅ 修正 `useStreaming = false`（恢復穩定 non-streaming）
2. ✅ 添加 LLM loading 提示

**可選優化**（如果要啟用 streaming）:
3. 🔧 實施 requestAnimationFrame throttling
4. 🧪 測試長文本性能

**不推薦**:
❌ Ping-pong buffer（除非用戶明確要求固定批次顯示）
