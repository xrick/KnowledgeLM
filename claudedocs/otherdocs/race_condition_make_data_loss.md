# Race Condition 導致資料遺失：深度分析

> **日期**: 2025-12-05
> **檔案**: `template/skill_main.html`
> **症狀**: 切換頁面後，聊天記錄消失
> **根因**: sessionStorage 的 Race Condition

---

## 1. 問題現象

用戶在 `/skill` 頁面進行對話後，切換到 `/skill/config`，再返回 `/skill`，發現聊天記錄消失。

```
用戶操作流程：
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   /skill        │───►│  /skill/config  │───►│    /skill       │
│ (有聊天記錄)    │    │   (設定頁面)    │    │ (記錄消失！)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 2. 為什麼會發生 Race Condition？

### 2.1 非同步程式設計的陷阱

這個問題的根本原因是**混合使用非同步操作與計時器，且缺乏明確的協調機制**。

```javascript
// DOMContentLoaded 事件處理
document.addEventListener('DOMContentLoaded', async () => {
    // 操作 A：非同步函數（等待 API 回應）
    loadSkills();                           // ← async，何時完成不確定

    // 操作 B：計時器（固定 300ms 後執行）
    setTimeout(() => {
        restoreChatState();                 // ← 假設 300ms 後 loadSkills 已完成
    }, 300);
});
```

**問題**：開發者假設「300ms 足夠讓 API 回應」，但：
- 網路快時：API < 100ms 回應
- 網路慢時：API > 500ms 回應
- 這導致執行順序不可預測

### 2.2 共享狀態的危險

```javascript
let chatHistory = [];      // 共享變數 1
let selectedSkills = [];   // 共享變數 2
let checkedItems = new Set(); // 共享變數 3

// 問題函數：一次保存所有狀態
function saveChatState() {
    sessionStorage.setItem('CHAT_HISTORY', JSON.stringify(chatHistory));
    sessionStorage.setItem('SELECTED_SKILLS', JSON.stringify(selectedSkills));
    sessionStorage.setItem('CHECKED_ITEMS', JSON.stringify([...checkedItems]));
}
```

**設計缺陷**：`saveChatState()` 違反單一職責原則
- 本意：保存聊天記錄
- 實際：同時保存選取狀態
- 後果：更新選取狀態時，會「順便」覆蓋聊天記錄

---

## 3. 問題流程圖

### 3.1 正常情況（API 回應 > 300ms）

```
時間軸 →
═══════════════════════════════════════════════════════════════════════════════

DOMContentLoaded
    │
    ├──► loadSkills() 開始           setTimeout(300ms) 設定
    │         │                              │
    │         │ (等待 API...)                │
    │         │                              ▼ (300ms 到)
    │         │                      restoreChatState() 執行
    │         │                              │
    │         │                      chatHistory = [從 sessionStorage 恢復]
    │         │                              │
    │         ▼ (API 回應，假設 400ms)       ✓ 恢復成功
    │   initializeAllSelected()
    │         │
    │         ▼
    │   updateSelectedFromCheckboxes()
    │         │
    │         ▼
    │   saveChatState()
    │         │
    │         └──► 保存 chatHistory（此時已有資料）✓ OK
    ▼
結束

結果：聊天記錄正常保留 ✓
```

### 3.2 問題情況（API 回應 < 300ms）⚠️

```
時間軸 →
═══════════════════════════════════════════════════════════════════════════════

DOMContentLoaded
    │
    ├──► loadSkills() 開始           setTimeout(300ms) 設定
    │         │                              │
    │         │ (等待 API...)                │
    │         ▼ (API 回應，假設 150ms)       │ (尚未到 300ms)
    │   initializeAllSelected()              │
    │         │                              │
    │         ▼                              │
    │   updateSelectedFromCheckboxes()       │
    │         │                              │
    │         ▼                              │
    │   saveChatState() ◄────────────────────┼─── ⚠️ 問題發生點！
    │         │                              │
    │         └──► 保存 chatHistory          │
    │              (此時 chatHistory = [])   │
    │              ⚠️ 空陣列覆蓋 sessionStorage！
    │                                        │
    │                                        ▼ (300ms 到)
    │                                restoreChatState() 執行
    │                                        │
    │                                chatHistory = JSON.parse(sessionStorage)
    │                                        │
    │                                sessionStorage 已經是 []
    │                                        │
    │                                        ⚠️ 恢復到空資料！
    ▼
結束

結果：聊天記錄遺失 ✗
```

### 3.3 時序競爭示意圖

```
                    loadSkills()                    restoreChatState()
                        │                                  │
    API 快速回應        │                                  │
    (< 300ms)          ▼                                  │
              ┌─────────────────┐                         │
              │ initializeAll() │                         │
              │       ↓         │                         │
              │ saveChatState() │ ◄── 寫入空 chatHistory   │
              └─────────────────┘                         │
                                                          ▼ (300ms)
                                              ┌─────────────────────┐
                                              │ 讀取 sessionStorage │
                                              │    (已被覆蓋為空)   │
                                              └─────────────────────┘
                                                          │
                                                          ▼
                                                    資料遺失！


    API 較慢回應        │                                  │
    (> 300ms)          │                                  ▼ (300ms)
                       │                      ┌─────────────────────┐
                       │                      │ 讀取 sessionStorage │
                       │                      │   (正確恢復資料)    │
                       │                      └─────────────────────┘
                       ▼                                  │
              ┌─────────────────┐                         │
              │ initializeAll() │                         │
              │       ↓         │                         │
              │ saveChatState() │ ◄── 寫入已恢復的 chatHistory ✓
              └─────────────────┘
                       │
                       ▼
                  資料保留 ✓
```

---

## 4. 核心問題分析

### 4.1 違反的設計原則

| 原則 | 違反情況 |
|------|----------|
| **單一職責原則 (SRP)** | `saveChatState()` 同時負責保存聊天記錄和選取狀態 |
| **明確依賴原則** | `restoreChatState()` 依賴 `loadSkills()` 完成，但沒有明確等待 |
| **不可變性原則** | 共享變數 `chatHistory` 可被多處修改 |

### 4.2 時序問題的數學分析

```
設：
  T_api = API 回應時間（不確定，0 ~ ∞ ms）
  T_timer = 計時器延遲（固定 300ms）

問題發生條件：
  T_api < T_timer

  即：API 回應時間 < 300ms 時，saveChatState() 會在 restoreChatState() 之前執行

發生機率：
  P(問題) = P(T_api < 300ms)

  - 本地開發環境：P ≈ 0.9（API 通常 < 100ms）
  - 生產環境：P ≈ 0.5 ~ 0.8（取決於網路狀況）
```

### 4.3 問題的隱蔽性

這個 bug 特別難發現，因為：

1. **不是每次都發生**：取決於網路速度
2. **開發環境更容易發生**：本地 API 更快
3. **症狀不明顯**：只有切換頁面後才會發現
4. **難以重現**：需要特定的時序條件

---

## 5. 解決方案

### 5.1 根本修復：分離保存函數

```javascript
// ===== 修復後的程式碼 =====

// 只保存聊天歷史（聊天相關操作使用）
function saveChatHistory() {
    try {
        sessionStorage.setItem(SESSION_KEYS.CHAT_HISTORY, JSON.stringify(chatHistory));
    } catch (e) {
        console.warn('Failed to save chat history:', e);
    }
}

// 只保存選取狀態（選取相關操作使用）
function saveSelectionState() {
    try {
        sessionStorage.setItem(SESSION_KEYS.SELECTED_SKILLS, JSON.stringify(selectedSkills));
        sessionStorage.setItem(SESSION_KEYS.CHECKED_ITEMS, JSON.stringify([...checkedItems]));
    } catch (e) {
        console.warn('Failed to save selection state:', e);
    }
}

// 呼叫點修改
function addMessage(content, role, sources) {
    chatHistory.push({ content, role, sources, timestamp: Date.now() });
    saveChatHistory();  // ← 只保存聊天，不動選取狀態
}

function updateSelectedFromCheckboxes() {
    // ... 更新選取邏輯 ...
    saveSelectionState();  // ← 只保存選取，不動聊天記錄
}
```

### 5.2 修復後的時序

```
時間軸 →（修復後）
═══════════════════════════════════════════════════════════════════════════════

DOMContentLoaded
    │
    ├──► loadSkills() 開始           setTimeout(300ms) 設定
    │         │                              │
    │         ▼ (API 回應，假設 150ms)       │
    │   initializeAllSelected()              │
    │         │                              │
    │         ▼                              │
    │   updateSelectedFromCheckboxes()       │
    │         │                              │
    │         ▼                              │
    │   saveSelectionState() ◄───────────────┼─── ✓ 只保存選取狀態
    │         │                              │       chatHistory 不受影響！
    │         └──► 只保存 selectedSkills     │
    │              和 checkedItems           │
    │              (不動 chatHistory!)       │
    │                                        │
    │                                        ▼ (300ms 到)
    │                                restoreChatState() 執行
    │                                        │
    │                                chatHistory = [正確恢復！]
    │                                        │
    │                                        ✓ 資料完整
    ▼
結束

結果：無論 API 快慢，聊天記錄都能正確保留 ✓
```

---

## 6. 替代方案（供參考）

### 6.1 使用 Promise 協調

```javascript
document.addEventListener('DOMContentLoaded', async () => {
    await loadSkills();          // 等待 loadSkills 完成
    restoreChatState();          // 然後再恢復狀態
});
```

**優點**：明確的執行順序
**缺點**：增加頁面載入時間

### 6.2 使用初始化標記

```javascript
let isRestored = false;

function saveChatState() {
    if (!isRestored) return;  // 尚未恢復完成，不保存
    // ... 保存邏輯 ...
}

function restoreChatState() {
    // ... 恢復邏輯 ...
    isRestored = true;  // 標記恢復完成
}
```

**優點**：簡單直接
**缺點**：增加全域狀態

### 6.3 使用事件驅動

```javascript
document.addEventListener('skillsLoaded', () => {
    restoreChatState();
});

async function loadSkills() {
    // ... 載入邏輯 ...
    document.dispatchEvent(new Event('skillsLoaded'));
}
```

**優點**：解耦，可擴展
**缺點**：增加複雜度

---

## 7. 經驗教訓

### 7.1 設計原則

1. **單一職責**：一個函數只做一件事
2. **明確依賴**：使用 async/await 或事件來協調非同步操作
3. **避免計時器假設**：不要假設「X 毫秒足夠」

### 7.2 防範措施

```javascript
// ❌ 不好的做法
setTimeout(doSomething, 300);  // 假設 300ms 足夠

// ✓ 好的做法
await someAsyncOperation();
doSomething();  // 明確等待完成
```

### 7.3 測試建議

- 使用 Chrome DevTools 的網路節流功能測試不同網速
- 測試快速網路（< 50ms）和慢速網路（> 500ms）場景
- 多次重複測試，確保時序不會造成問題

---

## 8. 結論

> **問題永遠比答案重要。**

這個 Race Condition 的根本原因不是「非同步程式設計」本身，而是：

1. **使用計時器來「猜測」非同步操作完成時間**
2. **共享保存函數同時處理多種不相關的狀態**
3. **缺乏明確的操作順序協調機制**

修復方案的核心思想：**分離關注點**——讓聊天記錄的保存和選取狀態的保存互不干擾，從根本上消除競爭條件。

---

*文檔建立: 2025-12-05*
*修復版本: skill_main.html (Lines 1233-1254, 2340, 2719)*
