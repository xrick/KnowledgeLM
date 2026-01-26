# ISSUE-001: Skill 選擇後查詢失敗 - selectedSkills 為空

**優先級**: 🔴 **最高 (P0)**  
**狀態**: ✅ 已修復  
**發現日期**: 2026-01-23  
**影響範圍**: 所有 Skill Chat 查詢功能

---

## 問題描述

### 現象
用戶在 Skill Chat 頁面選擇任何 Skill 後進行查詢，系統總是回答：
> 「抱歉，我無法回答此問題，因為缺少相關文檔內容。」

### 實際行為
- 前端 `selectedSkills` 陣列為空
- 查詢請求未正確發送或發送了空的 `skill_id`
- API 返回 404: "No documents found for specified skills"

### 預期行為
- 選擇 Skill 後，`selectedSkills` 應包含正確的 skill_id
- 查詢應正常發送並返回相關內容

---

## 根本原因分析

### 1. 資料架構不一致

系統存在兩種 Skill 架構：

| 架構類型 | 特徵 | 範例 |
|----------|------|------|
| **舊架構** | `skill.documents = []`，FAISS 索引直接關聯到 head_id | 六法全書-刑法、投資理財（原版） |
| **新架構** | `skill.documents` 包含子文檔，每個子文檔有獨立 skill_id | 大語言模型大全、投資理財（新版） |

### 2. 前端選擇邏輯缺陷

**問題代碼位置**: `template/skill_main.html`

```javascript
// handleSkillGroupClick 函數 (Line ~3718)
if (skill.documents && skill.documents.length > 0) {
    skill.documents.forEach(doc => {
        selectedSkills.push({ id: doc.skill_id, ... });
    });
}
// ❌ 缺少 else 分支！當 documents 為空時，selectedSkills 保持為空
```

### 3. 問題流程圖

```
用戶選擇「六法全書-刑法」(舊架構)
    ↓
handleSkillGroupClick() 被調用
    ↓
skill.documents = [] (空陣列)
    ↓
if 條件不滿足，不執行任何操作
    ↓
selectedSkills = [] (空陣列)
    ↓
sendQuery() 檢查: if (selectedSkills.length === 0) return;
    ↓
查詢未發送！或發送空 skill_id
    ↓
API 返回錯誤 或 LLM 因無 context 回答「找不到」
```

---

## 解決方案

### 修復代碼

在 `handleSkillGroupClick` 和 `selectSkillGroupFromTree` 函數中增加 `else` 分支：

```javascript
if (skill.documents && skill.documents.length > 0) {
    // 新架構：選擇所有子文檔
    skill.documents.forEach(doc => {
        selectedSkills.push({
            id: doc.skill_id,
            name: doc.source_name || 'Document',
            chunks: doc.total_chunks || 0,
            category: category,
            isAttachment: true
        });
    });
} else {
    // ✅ 修復：舊架構 fallback
    // 直接使用 head_id 作為 skill_id 進行查詢
    selectedSkills.push({
        id: headId,
        name: name,
        chunks: totalChunks,
        category: category,
        isHead: true,
        isMain: true
    });
    checkedItems.add(headId);
    console.log(`[handleSkillGroupClick] Legacy skill with no documents, using headId: ${headId}`);
}
```

### 修改檔案清單

| 檔案 | 行數 | 修改內容 |
|------|------|----------|
| `template/skill_main.html` | ~3740 | `handleSkillGroupClick` 增加 else 分支 |
| `template/skill_main.html` | ~4010 | `selectSkillGroupFromTree` 增加 else 分支 |

---

## 偵測方法

### 1. 自動化測試 (建議實施)

```javascript
// test/skill_selection.test.js
describe('Skill Selection', () => {
    test('Legacy skill (no documents) should set selectedSkills', () => {
        const legacySkill = { head_id: 'skill_xxx', documents: [] };
        handleSkillGroupClick('group-1', legacySkill.head_id, 'Test', 100, 'Legal', mockElement);
        expect(selectedSkills.length).toBeGreaterThan(0);
        expect(selectedSkills[0].id).toBe('skill_xxx');
    });
    
    test('New skill (with documents) should set selectedSkills from documents', () => {
        const newSkill = { head_id: 'skill_yyy', documents: [{ skill_id: 'doc_1' }] };
        handleSkillGroupClick('group-2', newSkill.head_id, 'Test', 100, 'Tech', mockElement);
        expect(selectedSkills.length).toBe(1);
        expect(selectedSkills[0].id).toBe('doc_1');
    });
});
```

### 2. Console 日誌監控

在選擇 Skill 後檢查 Console：
```
✅ 正確: [handleSkillGroupClick] Selected skill "xxx" with 1 documents
❌ 錯誤: [handleSkillGroupClick] Selected skill "xxx" with 0 documents
```

### 3. 運行時檢查

```javascript
// 在 sendQuery() 開頭加入診斷
async function sendQuery() {
    console.log('[sendQuery] selectedSkills:', selectedSkills);
    if (selectedSkills.length === 0) {
        console.error('[sendQuery] ERROR: No skills selected!');
        // 可選：顯示用戶友好的錯誤訊息
        return;
    }
    // ...
}
```

---

## 預防措施

### 1. 架構統一 (長期方案)

**目標**: 消除舊/新架構差異

```sql
-- 為所有舊架構 skill 創建對應的 document 記錄
INSERT INTO skill_metadata (skill_id, head_id, source_name, ...)
SELECT skill_id || '_main', skill_id, skill_name, ...
FROM skill_metadata
WHERE documents_count = 0 AND parent_skill_id = 'root';
```

### 2. API 層防護

```python
# app/api/v1/endpoints/skills.py
@router.post("/demo/query")
async def query_demo_skill(...):
    # 增加 head_id fallback 邏輯
    if not valid_skill_ids and target_skill_ids:
        # 嘗試直接使用傳入的 ID（可能是舊架構的 head_id）
        for sid in target_skill_ids:
            if await check_faiss_index_exists(sid):
                valid_skill_ids.append(sid)
                logger.info(f"Fallback: Using head_id directly: {sid}")
```

### 3. 前端防禦性編程

```javascript
// 統一的 skill 選擇函數
function selectSkill(skill, element) {
    clearAllSelections();
    element.classList.add('selected');
    
    selectedSkills = [];
    
    // 優先使用 documents
    if (skill.documents?.length > 0) {
        skill.documents.forEach(doc => {
            selectedSkills.push({ id: doc.skill_id, ... });
        });
    }
    
    // Fallback: 使用 head_id
    if (selectedSkills.length === 0 && skill.head_id) {
        selectedSkills.push({ id: skill.head_id, isHead: true, ... });
    }
    
    // 最終檢查
    if (selectedSkills.length === 0) {
        console.error('Failed to select skill:', skill);
        showUserError('無法選擇此技能，請聯繫管理員');
        return false;
    }
    
    return true;
}
```

### 4. TypeScript 類型保護 (如遷移到 TS)

```typescript
interface SelectedSkill {
    id: string;  // 必填
    name: string;
    chunks: number;
    category: string;
    isHead?: boolean;
    isAttachment?: boolean;
}

// 編譯時確保 id 不為空
function addSelectedSkill(skill: SelectedSkill): void {
    if (!skill.id) {
        throw new Error('Skill id is required');
    }
    selectedSkills.push(skill);
}
```

---

## 驗證清單

修復後請執行以下驗證：

- [ ] 選擇「六法全書-刑法」→ 查詢「什麼是刑法」→ 應返回正確答案
- [ ] 選擇「大語言模型大全」→ 查詢「什麼是 LLM」→ 應返回正確答案
- [ ] 選擇「投資理財」→ 查詢「投資原則」→ 應返回正確答案
- [ ] Console 無 "0 documents" 或 "No skills selected" 錯誤
- [ ] 強制刷新瀏覽器 (Cmd+Shift+R) 確保載入最新 JavaScript

---

## 相關文件

- `template/skill_main.html` - 前端 Skill 選擇邏輯
- `app/api/v1/endpoints/skills.py` - 後端查詢 API
- `app/Providers/skill_metadata_provider/client.py` - Skill 元數據查詢

---

*文檔建立: 2026-01-23*  
*最後更新: 2026-01-23*
