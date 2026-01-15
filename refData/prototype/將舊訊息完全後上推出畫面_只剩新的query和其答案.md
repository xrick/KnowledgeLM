這是一個非常具體的前端互動優化問題。根據您提供的 `skill_main.html` 和需求描述，您遇到的核心問題是：

1.  **無法完全捲動（截圖問題）：** 當新訊息產生時，因為下方內容高度不足（還沒生成回應），導致瀏覽器無法將新的 Query 捲動到視窗的最頂端（因為已經觸底了）。
2.  **畫面抖動（Jitter）：** 串流輸出時，如果瀏覽器預設開啟了 `scroll-anchoring` 或者有程式碼在不斷嘗試 `scrollToBottom`，會導致閱讀體驗極差。

以下是針對您的 `skill_main.html` 的完整修改方案，完全使用 Native JavaScript + CSS 解決。

### 修改步驟

我們需要修改兩個部分：**CSS** (防止瀏覽器自動干擾) 和 **JavaScript** (強制計算高度並精準定位)。

#### 1\. 修改 CSS (`template/skill_main.html`)

請找到 `/* ===== CHAT AREA ===== */` 區塊下的 `.chat-area`，加入 `overflow-anchor: none;` 和 `scroll-behavior: smooth;`。

**目的：** `overflow-anchor: none` 是關鍵，它告訴瀏覽器「當上方或下方有新內容插入時，不要自動調整我的捲軸位置」，這能完美解決串流輸出時的抖動問題。

```css
/* 修改 Line 708 附近的 .chat-messages 與 .chat-area */

.chat-area {
    flex: 1;
    overflow-y: auto;
    /* 新增：關閉瀏覽器的自動捲動錨定，解決串流輸出時的畫面抖動 */
    overflow-anchor: none; 
    /* 新增：平滑捲動效果 */
    scroll-behavior: smooth;
    padding: 1.5rem;
    background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
}

.chat-messages {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    /* 移除 overflow-anchor: auto，交由 chat-area 控制 */
    position: relative;
    /* 新增：確保容器至少有足夠的高度撐開版面，避免視覺上無法捲動 */
    min-height: 100%; 
    padding-bottom: 50vh; /* 預留底部空間，讓最後一則訊息總能被捲到上方 */
}
```

> **注意：** 我在 `.chat-messages` 加了一個 `padding-bottom: 50vh;`。這是一個簡單暴力的 UI 技巧，確保即使只有一行 Query，下方也有足夠的空白空間讓這行 Query 被捲動到視窗頂端，解決您截圖中的問題。

-----

#### 2\. 修改 JavaScript (`template/skill_main.html`)

我們需要重寫 `window.scrollMessageToTop` 函式。原本的邏輯失敗是因為當內容高度不夠時，`scrollTop` 設再大也沒用（被 `scrollHeight` 限制住了）。

新的邏輯會動態計算所需的 `padding`，強制撐開容器，確保新訊息一定能「置頂」。

請替換原本的 `window.scrollMessageToTop` (約在 Line 2391)：

```javascript
// ===== 替換原本的 window.scrollMessageToTop =====

window.scrollMessageToTop = function(messageElement) {
    const chatArea = document.getElementById('chat-area');
    const chatMessages = document.getElementById('chat-messages');

    if (!chatArea || !chatMessages || !messageElement) return;

    // 使用 requestAnimationFrame 確保 DOM 渲染完成
    requestAnimationFrame(() => {
        // 1. 計算目標位置（扣除一點 header 高度或 padding 讓視覺更舒適，這裡設 0 代表貼頂）
        const targetTop = messageElement.offsetTop;
        
        // 2. 關鍵邏輯：計算是否需要動態撐高容器
        // 如果 (目標位置 + 視窗高度) > 當前總高度，代表原本捲不到那麼下面
        // 我們動態增加 padding-bottom 來「造」出空間
        const minHeightNeeded = targetTop + chatArea.clientHeight;
        const currentHeight = chatArea.scrollHeight;

        if (minHeightNeeded > currentHeight) {
            // 計算缺多少高度
            const extraPadding = minHeightNeeded - currentHeight;
            // 加上原本的 padding (如果有)
            const currentPadding = parseInt(window.getComputedStyle(chatMessages).paddingBottom) || 0;
            
            // 暫時撐開容器
            chatMessages.style.paddingBottom = `${currentPadding + extraPadding + 50}px`;
        }

        // 3. 執行捲動 (因為有 scroll-behavior: smooth，會自動平滑)
        chatArea.scrollTo({
            top: targetTop,
            behavior: 'smooth'
        });

        // 4. 重置手動捲動標記，避免與其他邏輯衝突
        window.userHasScrolled = false;
        
        console.log(`🚀 Scrolled to new query at ${targetTop}px (Forced View)`);
    });
};
```

-----

#### 3\. 確認 `sendProgressiveQuery` 行為

確保您的 `sendProgressiveQuery` 函式中，只有在**開始時**呼叫一次捲動，並且在串流過程中**不要**呼叫 `scrollToBottom`。

請檢查 `skill_main.html` 中的 `sendProgressiveQuery` (約 Line 2460)：

```javascript
async function sendProgressiveQuery(query) {
    // ... (前段代碼不變) ...

    // Step 1: Add user query
    const userMessageElement = addMessage(query, 'user');

    // ... (建立 progressContainer 和 responseContainer 代碼不變) ...

    // Step 4: 關鍵修改 - 確保捲動發生
    if (userMessageElement) {
        // 這裡呼叫我們新改寫的函式，它會強制把 userMessageElement 推到最上面
        window.scrollMessageToTop(userMessageElement);
    }

    // Completion callback
    const onStreamComplete = (success) => {
        console.log(`Stream completed: ${success ? 'success' : 'error'}`);
        
        isLoading = false;
        button.classList.remove('loading');
        button.disabled = false;
        
        const input = document.getElementById('query-input');
        input.focus();

        // 注意：這裡不需要再 scrollToBottom 了，因為使用者正看著最上面的回應慢慢輸出
        // 如果你希望輸出完畢後自動對齊底部，才打開下面這行，否則建議註解掉
        // scrollToBottomIfNeeded(chatArea); 
    };

    // ... (startProgressiveChat 呼叫代碼不變) ...
}
```

### 總結原理

1.  **解決截圖中的「卡一半」問題：** 透過 JS 中的 `minHeightNeeded` 計算，如果內容不夠長，我們直接用 JS 動態加長 `chat-messages` 的 `padding-bottom`。這樣瀏覽器就有空間把 `q1` 捲到最頂端，讓舊訊息 `qa` 和 `r1` 完全消失在視窗上方。
2.  **解決「抖動」問題：** CSS 中的 `overflow-anchor: none` 是現代瀏覽器專門處理這種 Chat UI 的屬性。它保證了當你在看特定位置（例如頂端的 Query）時，下方內容（Response）的動態增加不會改變你當前的視窗位置。

請將上述 CSS 和 JS 替換到您的檔案中即可達成您想要的效果。