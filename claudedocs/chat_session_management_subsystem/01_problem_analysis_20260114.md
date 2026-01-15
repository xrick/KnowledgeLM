# Chat Session Management - 問題分析報告

**文件日期**: 2026-01-14  
**版本**: 1.0  
**狀態**: 分析完成

---

## 1. 問題背景

### 1.1 發現的異常現象

用戶在 Skill Chat 頁面操作時發現以下問題：

1. 選擇 A Skill（例如：MSI Product）
2. 輸入提示：「請總結所有文件內容」
3. 系統正常回覆所有文件的總結
4. 切換到 B Skill（例如：投資理財）
5. 輸入相同提示：「請總結所有文件內容」
6. **異常回覆**：「目前對話中只有關於投資目的的資訊，已在前面回答。若您有其他文件或資料需要總結，請將其內容貼上，我將為您整理。」

### 1.2 關鍵異常點

LLM 回覆中出現「**已在前面回答**」這句話，表明：
- LLM 看到了不應該存在的「前面對話」
- 切換 Skill 後，舊的對話歷史被帶入新的對話上下文

---

## 2. 根本原因分析

### 2.1 Session ID 生成機制

**當前 Session ID 格式**：
```
skill_{user_id}_{skill_id}
```

**程式碼位置**：`app/api/v1/endpoints/skills.py`

```python
# Line 517-518
effective_session_id = (
    session_id or f"skill_{effective_user_id}_{primary_skill_id}"
)
```

### 2.2 問題流程圖

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: 用戶選擇 A Skill (MSI Product)                          │
│  → 問「請總結所有文件內容」                                       │
│  → 系統回答 (正常)                                               │
│  → chatHistory 保存到 localStorage                               │
│  → 對話保存到 MongoDB                                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: 用戶切換到 B Skill (投資理財)                            │
│  → updateSelectionUI() 被調用                                    │
│  → 保存舊 chatHistory → 載入新 skill 的 chatHistory              │
│  → MongoDB 載入該 Skill 的歷史對話                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: 用戶問「請總結所有文件內容」                             │
│  → API 帶著 include_history: true 發送請求                       │
│  → MongoDB 載入 chat_history (包含之前的「投資目的」對話)         │
│  → LLM 看到舊內容 → 回覆「已在前面回答」                         │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 核心問題：MongoDB Session 持久化

**問題所在**：MongoDB 中的 chat_history 是**跨 session 持久化**的。

當用戶**之前**在「投資理財」Skill 下問過關於「投資目的」的問題，該對話會被保存。當用戶**再次**選擇同一個 Skill 時：

```python
# skills.py line 3809-3811
chat_history = await chat_history_provider.get_chat_history(
    session_id=effective_session_id, limit=request.history_limit
)
```

這會載入之前的對話歷史，包括「投資目的」的問答，導致 LLM 認為「已經回答過了」。

### 2.4 為什麼 A Skill 正常，B Skill 異常？

| Skill | 是否有 MongoDB 歷史 | 結果 |
|-------|---------------------|------|
| MSI Product | 否（新 session 或無歷史） | ✅ 正常回答 |
| 投資理財 | **是**（之前問過「投資目的」）| ❌ 說「已在前面回答」|

---

## 3. 各層級狀態分析

| 層級 | 狀態 | 說明 |
|------|------|------|
| **MongoDB Session** | ⚠️ 問題所在 | Session 持久化保存了之前的對話，切換 Skill 後被載入 |
| **前端 localStorage** | ✅ 正確隔離 | `updateSelectionUI` 已實現按 Skill 保存/載入 |
| **API Request** | ✅ 正確 | `include_history: true` 按設計運作 |
| **LLM Prompt** | ✅ 正確 | 按設計將歷史傳給 LLM |

---

## 4. 衍生問題：不同用戶是否會互相干擾？

### 4.1 驗證結果

**當前 Session ID 格式**：
```
skill_{user_id}_{skill_id}
```

**範例**：
| 用戶 | Skill | Session ID |
|------|-------|------------|
| Alice (uuid-aaa) | 投資理財 (skill_invest_xxx) | `skill_uuid-aaa_skill_invest_xxx` |
| Bob (uuid-bbb) | 投資理財 (skill_invest_xxx) | `skill_uuid-bbb_skill_invest_xxx` |

### 4.2 結論

因為 `user_id` 是 Session ID 的一部分，不同用戶即使在同一個 Skill 也會有不同的 session，**不會互相干擾**。

---

## 5. 解決方案建議

### 方案 A：切換 Skill 時清空 MongoDB Session（立即生效）

在前端切換 Skill 時，調用清除 API：

```javascript
async function onSkillChange(newSkillId) {
    await clearMongoDBSession(newSkillId);
    // 其他切換邏輯...
}
```

### 方案 B：新增「清除對話」按鈕（用戶主動）

在 UI 上提供明顯的「清除此 Skill 的對話歷史」按鈕。

### 方案 C：每次切換 Skill 自動清除歷史（最乾淨）

```javascript
async function handleSkillGroupClick(groupId, headId, name, totalChunks, category, element) {
    // ... existing code ...
    
    const newSkillId = selectedSkills[0]?.id;
    if (newSkillId) {
        await clearMongoDBSession(newSkillId);
        console.log(`🗑️ Cleared MongoDB session for skill: ${newSkillId}`);
    }
}
```

### 方案 D：提供用戶選擇（推薦）

切換 Skill 時詢問用戶：
- 「繼續之前的對話」→ 載入歷史
- 「開始新對話」→ 清空歷史

---

## 6. 相關程式碼位置

| 檔案 | 行數 | 說明 |
|------|------|------|
| `app/api/v1/endpoints/skills.py` | 517-518 | Session ID 生成邏輯 |
| `app/api/v1/endpoints/skills.py` | 3809-3811 | 載入 chat_history |
| `template/skill_main.html` | 3960-4010 | `updateSelectionUI` 切換邏輯 |
| `template/skill_main.html` | 4815-4834 | `clearMongoDBSession` 函數 |

---

## 7. 附錄：MongoDB Sessions 資料範例

```javascript
{
  session_id: 'skill_5a19a0da-7485-4656-8641-41402fef4049_skill_20260113_061734_4209c143_8388d1',
  user_id: '5a19a0da-7485-4656-8641-41402fef4049',
  file_ids: [ 'skill_20260113_061734_4209c143_8388d1' ],
  created_at: ISODate('2026-01-13T06:26:35.356Z'),
  updated_at: ISODate('2026-01-13T09:02:17.673Z'),
  messages: [
    { role: 'user', content: '請說明這份文件的內容', ... },
    { role: 'assistant', content: '這份文件是...', ... }
  ],
  metadata: {
    type: 'skill_progressive_chat',
    skill_id: 'skill_20260113_061734_4209c143_8388d1'
  }
}
```

---

*文件結束*
