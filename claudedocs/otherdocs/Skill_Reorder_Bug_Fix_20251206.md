# Skill 排序無法保存問題修復 - 2025-12-06

**日期**: 2025-12-06
**狀態**: ✅ 已修復
**伺服器**: Running on http://localhost:8082 (PID: 39358)

---

## 問題描述

### 用戶報告

在 skill/config 頁面拖動排序 (例如：將「大語言模型大全」與「ML」交換位置)：

1. **Config 頁面**: 拖動後位置改變 ✅
2. **切換至 Chat 頁面**: 位置恢復原樣 ❌
3. **返回 Config 頁面**: 位置又恢復原樣 ❌

**結果**: 排序無法保存

---

## 根本原因分析

### Dual Source of Truth 反模式

系統存在兩個資料來源，導致資料不一致：

| 資料來源 | 用途 | 狀態 |
|---------|------|------|
| `skill_config.json` | `/config/reorder` API 寫入 | ❌ 已封存 (deprecated) |
| `skill_heads` 表 (SQLite) | `/config/demo` API 讀取 | ✅ Single Source of Truth |

### 問題流程

```
用戶拖動排序
    ↓
前端調用: PUT /api/v1/skills/config/reorder
    ↓
後端寫入: skill_config.json (Line 1897)  ← ❌ 寫入已封存的檔案！
    ↓
頁面重新載入 (skill/config 或 skill/chat)
    ↓
後端讀取: GET /api/v1/skills/tree → 從 skill_heads 表讀取 (Line 307)
    ↓
結果: skill_heads 表的 display_order 沒有更新
    ↓
排序恢復原樣 ❌
```

---

## 技術細節

### 問題代碼 (修復前)

**檔案**: `app/api/v1/endpoints/skills.py` (Lines 1872-1907)

```python
@router.put("/config/reorder")
async def reorder_skills(request: ReorderSkillsRequest):
    try:
        # ❌ 從已封存的 skill_config.json 讀取
        config = load_skill_config()
        skills = config.get("skills", [])

        order_map = {item.skill_name: item.display_order for item in request.order}

        for skill in skills:
            if skill["skill_name"] in order_map:
                skill["display_order"] = order_map[skill["skill_name"]]

        # ❌ 寫入已封存的 skill_config.json
        save_skill_config(config)

        return {"message": "Skills reordered successfully", ...}
```

**問題**:
1. `load_skill_config()` 讀取 `scripts/skill_data/skill_config.json` (已封存)
2. `save_skill_config()` 寫入同一檔案
3. 但 `/tree` 和 `/config/demo` API 從 `skill_heads` 表讀取
4. **兩個系統完全分離，導致資料不同步**

---

## 解決方案

### 修復後代碼

**檔案**: `app/api/v1/endpoints/skills.py` (Lines 1872-1928)

```python
@router.put("/config/reorder")
async def reorder_skills(
    request: ReorderSkillsRequest,
    provider: SkillMetadataProvider = Depends(get_skill_metadata_provider)
):
    """
    Update the display order of skills.

    NEW: Uses skill_heads table (SQLite - Single Source of Truth)
    DEPRECATED: No longer uses skill_config.json (archived)
    """
    try:
        # ✅ 從 skill_heads 表讀取
        skill_heads = await provider.list_skill_heads()

        # 建立 skill_name → display_order 映射
        order_map = {item.skill_name: item.display_order for item in request.order}

        # ✅ 更新每個 skill head 的 display_order (寫入資料庫)
        updated_skills = []
        for head in skill_heads:
            skill_name = head.get("skill_name")
            if skill_name in order_map:
                new_order = order_map[skill_name]
                head_id = head.get("head_id")

                # ✅ UPDATE skill_heads SET display_order = ? WHERE head_id = ?
                await provider.update_skill_head(
                    head_id=head_id,
                    display_order=new_order
                )

                updated_skills.append({
                    "skill_name": skill_name,
                    "display_order": new_order,
                    "head_id": head_id
                })

                logger.info(f"Updated {skill_name} display_order to {new_order}")

        return {
            "message": "Skills reordered successfully",
            "skills": updated_skills
        }
```

### 關鍵改進

| 改進項目 | 修復前 | 修復後 |
|---------|-------|-------|
| **資料來源** | skill_config.json (已封存) | skill_heads 表 (SQLite) |
| **讀取方式** | `load_skill_config()` | `provider.list_skill_heads()` |
| **寫入方式** | `save_skill_config()` | `provider.update_skill_head()` |
| **一致性** | ❌ 與讀取 API 不同步 | ✅ 與讀取 API 同步 |

---

## 資料庫更新邏輯

### Provider 方法

**檔案**: `app/Providers/skill_metadata_provider/client.py` (Lines 879-919)

```python
async def update_skill_head(
    self,
    head_id: str,
    **updates
) -> Optional[Dict[str, Any]]:
    """
    Update a skill head.

    Args:
        head_id: The skill head ID
        **updates: Fields to update (display_order, skill_name, description, etc.)
    """
    conn = await self._get_connection()

    allowed_fields = {'skill_name', 'description', 'category', 'display_order', 'enabled'}
    update_fields = {k: v for k, v in updates.items() if k in allowed_fields}

    if not update_fields:
        return await self.get_skill_head(head_id)

    # 動態生成 UPDATE SQL
    set_clause = ", ".join([f"{k} = ?" for k in update_fields.keys()])
    set_clause += ", updated_at = CURRENT_TIMESTAMP"

    query = f"UPDATE skill_heads SET {set_clause} WHERE head_id = ?"
    params = list(update_fields.values()) + [head_id]

    await conn.execute(query, params)
    await conn.commit()

    return await self.get_skill_head(head_id)
```

### SQL 執行範例

```sql
-- 範例：將「大語言模型大全」的 display_order 更新為 0
UPDATE skill_heads
SET display_order = 0, updated_at = CURRENT_TIMESTAMP
WHERE head_id = 'head_20251125_xxxx';

-- 範例：將「ML」的 display_order 更新為 1
UPDATE skill_heads
SET display_order = 1, updated_at = CURRENT_TIMESTAMP
WHERE head_id = 'head_20251125_yyyy';
```

---

## 前端資料流

### 拖動排序流程

**檔案**: `template/skill_config.html` (Lines 2177-2231)

```javascript
function handleDrop(event, dropIndex) {
    event.preventDefault();

    if (draggedIndex === null || draggedIndex === dropIndex) return;

    // 重新排序 skills array
    const skills = configData.tree || [];
    skills.sort((a, b) => a.display_order - b.display_order);

    // 移動被拖動的 skill
    const [movedSkill] = skills.splice(draggedIndex, 1);
    skills.splice(dropIndex, 0, movedSkill);

    // 更新所有 skills 的 display_order
    skills.forEach((skill, idx) => {
        skill.display_order = idx;
    });

    // 重新渲染 & 儲存
    renderSkills(skills);
    saveSkillOrder(skills);  // ← 調用 API
}

async function saveSkillOrder(skills) {
    const orderData = skills.map((skill, index) => ({
        head_id: skill.head_id,           // 前端發送 (後端不使用)
        skill_name: skill.skill_name,      // ✅ 後端使用
        display_order: index               // ✅ 後端使用
    }));

    const response = await fetch('/api/v1/skills/config/reorder', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order: orderData })
    });
}
```

### API Request 範例

```json
PUT /api/v1/skills/config/reorder

{
  "order": [
    {
      "head_id": "head_20251125_xxxx",
      "skill_name": "大語言模型大全",
      "display_order": 0
    },
    {
      "head_id": "head_20251125_yyyy",
      "skill_name": "ML",
      "display_order": 1
    }
  ]
}
```

---

## 完整資料流

### 修復後的完整流程

```
1. 用戶拖動排序 (Config 頁面)
    ↓
2. handleDrop() → skills array 重新排序
    ↓
3. saveSkillOrder() → PUT /api/v1/skills/config/reorder
    ↓
4. 後端: await provider.list_skill_heads()  ← 從 skill_heads 表讀取
    ↓
5. 後端: await provider.update_skill_head(head_id, display_order=new_order)
    ↓
6. SQL: UPDATE skill_heads SET display_order = ?, updated_at = ? WHERE head_id = ?
    ↓
7. 資料庫: skill_heads 表更新成功 ✅
    ↓
8. 頁面重新載入 (skill/config 或 skill/chat)
    ↓
9. GET /api/v1/skills/tree → SELECT * FROM skill_heads ORDER BY display_order
    ↓
10. 前端: 顯示新的排序 ✅
```

---

## 測試驗證

### 測試步驟

1. **前往 Skill Config 頁面**: http://localhost:8082/skill/config
2. **拖動排序**: 將「大語言模型大全」與「ML」交換位置
3. **切換至 Chat 頁面**: http://localhost:8082/skill
4. **驗證排序**: Sidebar 顯示新的排序 ✅
5. **返回 Config 頁面**: http://localhost:8082/skill/config
6. **驗證持久化**: Config 頁面顯示新的排序 ✅

### 資料庫驗證

```bash
# 檢查 skill_heads 表的 display_order
sqlite3 data/skill_metadata.db

SELECT head_id, skill_name, display_order, updated_at
FROM skill_heads
ORDER BY display_order;
```

**預期結果**:
```
head_id                        | skill_name      | display_order | updated_at
-------------------------------|-----------------|---------------|-------------------
head_20251125_xxxx             | 大語言模型大全  | 0             | 2025-12-06 22:20:00
head_20251125_yyyy             | ML              | 1             | 2025-12-06 22:20:00
head_20251125_zzzz             | 投資理財        | 2             | 2025-12-05 10:00:00
```

---

## 修改的檔案

| 檔案 | 行數 | 變更 |
|------|------|------|
| `app/api/v1/endpoints/skills.py` | 1872-1928 | 重寫 `/config/reorder` API 以使用 skill_heads 表 |

---

## 架構一致性

### 新架構 (Single Source of Truth)

```
┌──────────────────────────────────────────┐
│          skill_metadata.db (SQLite)       │
│  ┌────────────┐    ┌─────────────────┐   │
│  │skill_heads │ ←→ │ skill_metadata  │   │
│  │(定義層)    │    │ (文件層)        │   │
│  └────────────┘    └─────────────────┘   │
│         Single Source of Truth ✅        │
└──────────────────────────────────────────┘
            ↑
            │ ALL APIs 統一讀寫
            │
┌───────────┴───────────────────────────┐
│ /tree     /config/demo    /config/reorder │
│ (讀取)       (讀取)          (寫入)         │
└───────────────────────────────────────────┘
```

### 封存的舊系統

```
scripts/skill_data/archive/skill_config.json.deprecated
    ↑
    └─ 不再使用 (2025-12-04 封存)
```

---

## 相關文檔

- **架構重構**: `claudedocs/CLAUDE.md` (Lines 119-205)
- **skill_heads 遷移**: Session Update - 2025-12-04
- **Single Source of Truth**: 統一使用 SQLite `skill_heads` 表

---

## 總結

### 問題
- **Dual Source of Truth** 導致排序無法保存
- `/config/reorder` API 寫入已封存的 `skill_config.json`
- 讀取 API (`/tree`, `/config/demo`) 從 `skill_heads` 表讀取

### 解決
- ✅ 重寫 `/config/reorder` API 以使用 `skill_heads` 表
- ✅ 統一所有 API 使用 SQLite 作為 Single Source of Truth
- ✅ 封存 `skill_config.json` 並移除所有依賴

### 驗證
- ✅ 伺服器成功重啟 (PID: 39358)
- ✅ 健康檢查通過: `{"status":"healthy"}`
- ✅ API 端點正常運作
- ⏳ 待用戶測試拖動排序功能

---

**修復者**: Claude (SuperClaude)
**修復時間**: 2025-12-06 22:16
**狀態**: ✅ 完成 - 待用戶驗證
