# Scroll to New Query Fix - 2025-12-16

## Problem Description

### Symptom
When a user submits a new query in the skill chat interface (`skill_main.html`), the old messages (previous query + AI response) should scroll completely out of the visible area, leaving only the new query at the top of the viewport. However, the old messages remained partially visible at the top of the screen.

### Expected Behavior
```
After submitting new query:
┌─────────────────────────────────────────┐
│  [New Query]           ← At top         │
│  [Progress Bar]                         │
│  [AI Response Area]                     │
│                                         │
├─────────────────────────────────────────┤
│  [Input Box]                            │
└─────────────────────────────────────────┘
(Old messages should be completely scrolled above viewport)
```

### Actual Behavior
Old message tails were still visible at the top of the viewport, and the new query appeared in the middle of the screen instead of at the top.

### Reference Screenshots
- `refData/ui_improve/舊訊息仍無法上捲移出畫面4.png`

---

## Root Cause Analysis

### Issue 1: Incorrect Position Calculation

**Original Code:**
```javascript
const chatAreaPadding = parseInt(window.getComputedStyle(chatArea).paddingTop) || 0;
const targetTop = messageElement.offsetTop - chatAreaPadding;
```

**Problem:**
- `offsetTop` returns position relative to the element's `offsetParent`
- In nested layouts, `offsetParent` might not be the scroll container (`chat-area`)
- This leads to incorrect scroll target calculations

**HTML Structure:**
```html
<div class="chat-area" id="chat-area">          <!-- Scrollable container -->
    <div class="welcome-message">...</div>       <!-- Hidden when chatting -->
    <div class="chat-messages" id="chat-messages" style="position: relative;">
        <!-- offsetParent for messages -->
        <div class="message user">Old Query</div>
        <div class="message assistant">Old Response</div>
        <div class="message user">NEW Query</div>  <!-- Target element -->
    </div>
</div>
```

The `offsetTop` of the new query is relative to `chat-messages` (which has `position: relative`), but the scroll happens on `chat-area`. The offset chain wasn't properly accounted for.

### Issue 2: Insufficient Scroll Space

If the total content height (`scrollHeight`) is less than `targetScrollTop + viewportHeight`, the browser cannot scroll far enough to put the new message at the top.

**Example:**
- Viewport height: 600px
- Total content height: 800px
- New message position: 700px from top
- Maximum scrollTop: 800 - 600 = 200px
- Required scrollTop: 700px
- Result: Cannot scroll to position 700px!

### Issue 3: Timing / Async DOM Updates

DOM updates in browsers are asynchronous. When elements are added or modified:
1. JavaScript modifies the DOM
2. Browser schedules a repaint
3. Repaint happens (layout recalculation)
4. Element positions are finalized

A single `requestAnimationFrame` might execute before the layout is fully recalculated, especially when:
- Multiple elements are added (user message + progress bar + response container)
- CSS transitions are involved
- Padding/margin changes affect layout

---

## Solution

### Final Implementation

```javascript
window.scrollMessageToTop = function(messageElement) {
    const chatArea = document.getElementById('chat-area');
    const chatMessages = document.getElementById('chat-messages');

    if (!chatArea || !chatMessages || !messageElement) return;

    // ✅ Step 1: Force large padding to guarantee scroll space
    // Using 100vh ensures there's always enough room to scroll
    chatMessages.style.paddingBottom = '100vh';

    // ✅ Step 2: Wait for padding change to take effect
    // CSS changes need time to be applied to layout
    setTimeout(() => {
        // ✅ Step 3: Double RAF ensures DOM is fully painted
        // First RAF: scheduled after current frame
        // Second RAF: scheduled after next frame (layout complete)
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                // ✅ Step 4: Use getBoundingClientRect for accurate position
                // This method returns position relative to viewport
                // It's the most reliable way to get element position
                const chatAreaRect = chatArea.getBoundingClientRect();
                const messageRect = messageElement.getBoundingClientRect();

                // Calculate how far the message is from chatArea's visible top
                const currentScrollTop = chatArea.scrollTop;
                const messageTopRelativeToViewport = messageRect.top - chatAreaRect.top;
                const targetTop = currentScrollTop + messageTopRelativeToViewport;

                // ✅ Step 5: Execute scroll using direct assignment
                // More predictable than scrollTo() method
                chatArea.scrollTop = targetTop;

                // Reset manual scroll flag
                window.userHasScrolled = false;

                console.log('🚀 Scrolled to new query:', {
                    currentScrollTop,
                    messageTopRelativeToViewport,
                    targetTop,
                    finalScrollTop: chatArea.scrollTop
                });
            });
        });
    }, 50);  // 50ms delay for CSS to take effect
};
```

### Key Techniques Explained

#### 1. Force Padding (`paddingBottom: 100vh`)

```javascript
chatMessages.style.paddingBottom = '100vh';
```

**Why:** Guarantees there's always enough scroll space. 100vh = 100% of viewport height, ensuring we can always scroll far enough to put any message at the top.

**Trade-off:** Adds extra empty space at bottom, but this is acceptable for chat UX.

#### 2. setTimeout Delay (50ms)

```javascript
setTimeout(() => { ... }, 50);
```

**Why:** CSS property changes (like `paddingBottom`) need time to trigger layout recalculation. Without this delay, `getBoundingClientRect()` might return stale values.

**Why 50ms:** A balance between responsiveness and reliability. Too short (10ms) might not be enough; too long (200ms) causes noticeable delay.

#### 3. Double requestAnimationFrame

```javascript
requestAnimationFrame(() => {
    requestAnimationFrame(() => {
        // Measure and scroll here
    });
});
```

**Why:**
- First RAF: Schedules callback for next frame
- Second RAF: Schedules callback for the frame after that

This ensures:
1. Any pending DOM modifications are committed
2. Layout/reflow is complete
3. Paint is complete
4. Element positions are accurate

#### 4. getBoundingClientRect()

```javascript
const chatAreaRect = chatArea.getBoundingClientRect();
const messageRect = messageElement.getBoundingClientRect();
```

**Why:** Returns element position relative to the **viewport**, not relative to any parent element. This eliminates the `offsetParent` chain problem entirely.

**Returns:**
```javascript
{
    top: 150,      // Distance from viewport top
    left: 20,      // Distance from viewport left
    bottom: 200,   // Distance from viewport top to element bottom
    right: 500,    // Distance from viewport left to element right
    width: 480,    // Element width
    height: 50     // Element height
}
```

#### 5. Scroll Position Formula

```javascript
const targetTop = currentScrollTop + messageTopRelativeToViewport;
```

**Derivation:**
- `messageRect.top` = message's distance from viewport top
- `chatAreaRect.top` = chatArea's distance from viewport top
- `messageTopRelativeToViewport` = message's distance from chatArea's visible top
- Adding `currentScrollTop` converts viewport-relative to scroll-absolute position

**Visual:**
```
                          ┌─ Viewport Top (0)
                          │
                          │  ← chatAreaRect.top (e.g., 100px)
┌─────────────────────────┤
│ chat-area (visible)     │
│                         │  ← messageRect.top (e.g., 350px)
│    ★ Message ★         │
│                         │
└─────────────────────────┘

messageTopRelativeToViewport = 350 - 100 = 250px
targetScrollTop = currentScrollTop + 250
```

#### 6. Direct scrollTop Assignment

```javascript
chatArea.scrollTop = targetTop;
```

**Why not `scrollTo()`:**
- `scrollTo({ behavior: 'smooth' })` can be interrupted
- `scrollTo({ behavior: 'instant' })` sometimes has browser quirks
- Direct assignment is the most reliable method

---

## Constraints

Per CLAUDE.md requirements:

1. **No auto-scroll during streaming** - Causes screen jitter, poor UX
2. **Scroll only once** - When new query is submitted
3. **Must calculate old message height** - To determine scroll distance

This solution satisfies all constraints by:
- Only scrolling in `scrollMessageToTop()`, called once per query
- Not scrolling during response streaming
- Using viewport-relative positions for accurate calculations

---

## Files Modified

| File | Changes |
|------|---------|
| `template/skill_main.html` | `scrollMessageToTop()` function (lines ~2500-2540) |

---

## Testing

1. Open skill chat interface
2. Select a skill
3. Submit first query, wait for response
4. Submit second query
5. **Verify:** Old messages scroll completely out of view
6. **Verify:** New query appears at top of visible area
7. **Verify:** No screen jitter during response streaming

---

## Previous Attempted Fixes (Failed)

| Approach | Result |
|----------|--------|
| `scrollTop = scrollHeight` | Scrolls to bottom, not to new query |
| `scrollIntoView({ block: 'start' })` | Unreliable in nested scroll containers |
| `offsetTop` calculation | Incorrect due to offsetParent chain |
| Single `requestAnimationFrame` | Timing issues, DOM not fully updated |

---

## Lessons Learned

1. **Prefer `getBoundingClientRect()` over `offsetTop`** - More reliable for position calculations
2. **Ensure scroll space exists** - Force padding before calculating scroll position
3. **Account for async DOM updates** - Use setTimeout + double RAF for timing
4. **Test with real content** - Single message vs. long conversation behave differently
5. **Check browser DevTools** - Console logs help debug scroll calculations

---

*Document created: 2025-12-16*
*Author: Claude (SuperClaude)*
*Related Issue: 聊天介面捲動問題 (CLAUDE.md Known Issues)*
