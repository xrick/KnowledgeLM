# Fix: Chat History 污染問題

## 問題描述

**用戶報告**: 上傳兩個 PDF 並提問，LLM 回答說看不到文件，並提到用戶"沒有說過的話"：

```
"你所提到的「使用者點擊了以下文獻」並沒有在我的視野中顯現"
```

**用戶質疑**: "所有 query 都來自於使用者的輸入框，為什麼會有其它的不相關問題？"

## 根本原因分析

### 調查過程

1. **用戶的正確質疑**：
   - 所有 query 確實來自輸入框
   - "使用者點擊了以下文獻" 這個措辭不可能是用戶輸入的
   - 必定來自其他來源

2. **發現 Chat History 機制**：

   **檔案**: `app/api/v1/endpoints/chat.py:212-215`
   ```python
   # Get chat history
   chat_history = await chat_history_provider.get_chat_history(
       session_id=request.session_id,
       limit=10  # Last 10 messages for context
   )
   ```

   **系統會載入最近 10 條歷史訊息！**

3. **Session ID 管理問題**：

   **檔案**: `static/js/docai-client.js:15`
   ```javascript
   constructor() {
       this.sessionId = this.generateSessionId();  // 只在 constructor 執行一次
       ...
   }
   ```

   **Session ID 在頁面載入時只生成一次，之後不變！**

4. **"新增來源" 按鈕問題**：

   **檔案**: `template/index.html:516-523`
   ```javascript
   addSourceBtn.addEventListener('click', () => {
       // 只打開 modal，沒有重置 session
       uploadModal.showModal();
   });
   ```

   **"新增來源" 按鈕不會重置 session_id！**

### 問題流程

```
用戶第一次對話
→ 提到 "使用者點擊了以下文獻" (或 LLM 在回答中使用了這個措辭)
→ 保存到 chat_history (session_id = session_xxx)
→ 用戶點擊 "新增來源"
→ session_id 仍然是 session_xxx (未重置！)
→ 上傳新文件並提問
→ 系統載入最近 10 條 history
→ LLM 看到舊對話的內容
→ LLM 混淆了新舊對話，回答說 "你提到了..."
```

## 修復方案

### Fix #1: 添加 resetSession() 方法

**檔案**: `static/js/docai-client.js:679-693`

```javascript
/**
 * Reset session and clear chat history
 * Call this when user clicks "新增來源" to start fresh conversation
 */
resetSession() {
    // Generate new session ID
    this.sessionId = this.generateSessionId();

    // Clear chat display area
    if (this.chatDisplayArea) {
        this.chatDisplayArea.innerHTML = `
            <div class="chat-bubble ai">
                歡迎使用 DocAI 系統，這裡可以上傳您的文件並進行智慧問答
            </div>
        `;
    }

    console.log('[DocAI] Session reset:', { sessionId: this.sessionId });
}
```

**功能**:
- 生成新的 session_id
- 清除聊天顯示區域
- 記錄 log 用於調試

### Fix #2: 修改 "新增來源" 按鈕

**檔案**: `template/index.html:517-518`

```javascript
addSourceBtn.addEventListener('click', () => {
    // FIX: Reset session to clear chat history and start fresh conversation
    window.docaiClient.resetSession();

    // Reset upload area text when opening modal
    uploadAreaText.textContent = 'Drag & Drop File';
    ...
    uploadModal.showModal();
});
```

**功能**:
- 在打開上傳 modal 之前重置 session
- 清除舊的 chat history
- 開始全新的對話

## 修復效果

### 修復前

```
Session: session_1762330860644_82bcwg1 (固定不變)

對話 1:
User: "問題 A"
LLM: "使用者點擊了以下文獻..." (saved to history)

點擊 "新增來源" → session ID 不變

對話 2:
User: "問題 B" (關於新上傳的文件)
System: 載入 history (包含對話 1)
LLM: "你所提到的「使用者點擊了以下文獻」..." ← 混淆！
```

### 修復後

```
Session: session_1762330860644_82bcwg1

對話 1:
User: "問題 A"
LLM: "使用者點擊了以下文獻..." (saved to history)

點擊 "新增來源" → resetSession() 執行
→ session ID 變成 session_1762335555555_newid (新的!)

對話 2:
User: "問題 B" (關於新上傳的文件)
System: 載入 history (空的，因為是新 session)
LLM: 正確回答問題 B ← 正常！
```

## 驗證方法

### 測試步驟

1. **第一次對話**:
   - 上傳文件 A
   - 提問並獲得回答
   - 觀察 console: `[DocAI] Session initialized: {sessionId: 'session_xxx'}`

2. **點擊 "新增來源"**:
   - 觀察 console: `[DocAI] Session reset: {sessionId: 'session_yyy'}` (新的 ID)
   - 聊天區域已清空

3. **第二次對話**:
   - 上傳文件 B
   - 提問
   - LLM 應該只回答關於文件 B 的問題，不會提到文件 A 的內容

### 檢查 Console Logs

```javascript
// 初始化
[DocAI] Using existing user_id: ...
[DocAI Client initialized] {sessionId: 'session_1762330860644_82bcwg1'}

// 第一次對話...

// 點擊 "新增來源"
[DocAI] Session reset: {sessionId: 'session_1762335555555_newid'}  // ← 新 ID

// 第二次對話只使用新 session 的 history
```

## 相關功能說明

### Chat History 管理

**目的**: 提供上下文記憶，讓對話更連貫

**實現**:
- 每個 session_id 獨立儲存 chat history
- 每次請求載入最近 10 條訊息
- 傳遞給 LLM 作為上下文

**問題**:
- 如果 session_id 不變，history 一直累積
- 跨文件對話時會產生混淆

**解決**:
- "新增來源" 按鈕重置 session
- 每次新對話使用新的 session_id
- 避免跨文件 history 污染

### Session ID 格式

```javascript
generateSessionId() {
    return `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}
```

**範例**: `session_1762330860644_82bcwg1`
- `1762330860644`: Unix timestamp (milliseconds)
- `82bcwg1`: 隨機字符串 (7 字符)

**唯一性**: 時間戳 + 隨機字符串確保全局唯一

## 其他改進建議

### 1. 添加 "清除歷史" 按鈕

除了 "新增來源"，可以額外提供清除 history 的按鈕：

```javascript
clearHistory() {
    // 保留相同 session_id，但清除 UI
    if (this.chatDisplayArea) {
        this.chatDisplayArea.innerHTML = `
            <div class="chat-bubble ai">
                對話歷史已清除
            </div>
        `;
    }
    console.log('[DocAI] Chat history cleared');
}
```

### 2. 限制 History 範圍

可以只載入當前文件選擇後的對話：

```python
# 在 chat_history_provider 中添加 file_ids 過濾
async def get_chat_history(
    self,
    session_id: str,
    file_ids: Optional[List[str]] = None,  # 新增
    limit: int = 10
):
    # 只返回與當前 file_ids 相關的 history
    ...
```

### 3. 視覺化 Session 狀態

在 UI 上顯示當前 session 狀態：

```html
<div class="session-info">
    Session: <span id="sessionId">session_xxx</span>
    <button onclick="window.docaiClient.resetSession()">重置</button>
</div>
```

## 影響範圍

### 受影響的功能
- ✅ "新增來源" 按鈕 - 現在會重置 session
- ✅ Chat history 載入 - 新 session 不會載入舊對話
- ✅ 多文件對話 - 每次新文件使用獨立 session

### 不受影響的功能
- 同一 session 內的對話記憶 (正常)
- User ID 管理 (獨立於 session)
- File upload 功能

## Git Commit Message

```
fix(frontend): reset session on "新增來源" to prevent chat history pollution

Problem:
- Session ID was generated once on page load and never reset
- "新增來源" button didn't reset session_id
- Chat history accumulated across different file uploads
- LLM responses contained content from previous unrelated conversations

Root Cause:
- DocAIClient.sessionId set in constructor, never updated
- Backend loads last 10 messages from chat_history by session_id
- Same session_id meant old conversations were loaded for new files

Solution:
- Add resetSession() method to DocAIClient
- Call resetSession() when user clicks "新增來源"
- Generate new session_id and clear chat display
- Each new file upload starts with fresh conversation context

Impact:
- Users can now have independent conversations for different files
- No more confusion from previous chat history
- Better user experience for multi-file scenarios

Files:
- static/js/docai-client.js (lines 679-693): Add resetSession()
- template/index.html (line 517-518): Call resetSession() on button click

Related Issues:
- Chat history pollution
- Cross-file conversation contamination
- LLM mentioning content user never said
```

---

**文件版本**: 1.0
**建立日期**: 2025-11-05
**修復類型**: Bug Fix
**優先級**: 🔴 CRITICAL (影響對話品質)
