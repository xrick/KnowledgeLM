# Document IDs 展開修復 - 2025-12-06

**日期**: 2025-12-06
**問題**: 前端只傳遞 Head ID，未展開子文件 IDs
**狀態**: ✅ 已修復

---

## 問題

即使設定 `RETRIEVAL_TOP_K=50`，系統仍回覆「找不到相關內容」。

**根本原因**: 前端只傳遞 Head ID (`skill_20251203_071733_2a43e5ac`)，而真正的 FAISS 索引在子文件中 (`_src_00` ~ `_src_08`)。

---

## 修復內容

**檔案**: `template/skill_main.html`

### 變更 1: 展開 document IDs (Lines 2281-2295)

```javascript
// 修復前 ❌
const skillIds = selectedSkills.map(s => s.id);

// 修復後 ✅
const documentIds = [];

for (const skill of selectedSkills) {
    if (skill.children && skill.children.length > 0) {
        documentIds.push(...skill.children.map(child => child.id));
        console.log(`📁 Expanded "${skill.skill_name}": ${skill.children.length} documents`);
    } else {
        documentIds.push(skill.id);
    }
}

console.log(`📄 Total Document IDs: ${documentIds.length} docs`, documentIds);
```

### 變更 2: 使用展開後的 IDs (Line 2347)

```javascript
// 修復前 ❌
skillIds,

// 修復後 ✅
documentIds,  // Use expanded document IDs (not skillIds)
```

---

## 預期效果

### 修復前
```
document_ids = ["skill_20251203_071733_2a43e5ac"]  // 1 個 Head
→ FAISS 索引不存在
→ 返回 0 chunks
→ "找不到相關內容"
```

### 修復後
```
document_ids = [
    "skill_20251203_071733_2a43e5ac_src_00",
    "skill_20251203_071733_2a43e5ac_src_01",
    ...
    "skill_20251203_071733_2a43e5ac_src_08"
]  // 9 個子文件

→ 檢索 9 個 FAISS 索引
→ 返回 ~200+ chunks
→ "大語言模型的預訓練分為以下階段：..."
```

---

## 驗證步驟

1. **清除瀏覽器快取**: Ctrl+Shift+R (硬重新整理)
2. **前往**: http://localhost:8082/skill
3. **選擇**: 「大語言模型大全」
4. **查詢**: "請說明大語言模型的預訓練"
5. **檢查 Console**:
   ```
   📁 Expanded "大語言模型大全": 9 documents
   📄 Total Document IDs: 9 docs [...]
   ```
6. **驗證回答**: 應包含預訓練的詳細說明

---

## 修改的檔案

| 檔案 | 行號 | 變更 |
|------|------|------|
| `template/skill_main.html` | 2281-2295 | 新增子文件展開邏輯 |
| `template/skill_main.html` | 2347 | `skillIds` → `documentIds` |

---

**狀態**: ✅ 完成 - 無需重啟伺服器（純前端修改）
