# 修改日記: Skill 刪除邏輯與匯入功能修復

**日期時間**: 2026-01-13
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟡 中

---

## 📋 本次處理的問題總覽

| # | 問題 | 狀態 | 影響範圍 |
|---|------|------|----------|
| 1 | Skill 刪除時未清理所有相關 tables（孤兒資料問題） | ✅ 已修復 | 資料庫完整性 |
| 2 | Skill 匯入功能問題排查 | ✅ 已確認正常 | 匯入/匯出功能 |
| 3 | 匯入完成後無法關閉 Preview Modal | ✅ 已修復 | 前端 UI |

---

## 🔴 問題一：Skill 刪除邏輯不完整（Cascade Deletion）

### 問題描述

刪除 Skill 時，系統未清理所有相關 tables 的資料，導致產生**孤兒資料（Orphan Data）**。

### 問題發現過程

1. 用戶在匯入 Skill 時遇到錯誤：`UNIQUE constraint failed: skill_chunk_metadata.chunk_id`
2. 分析後發現 `skill_chunk_metadata` 中存在 **2,592 筆孤兒 chunks**
3. 這些 chunks 的 `skill_id` 在 `skill_metadata` 中已不存在（skill 被刪除但 chunks 未清理）

### 根本原因分析

系統有三個刪除 Skill 的 endpoint，但刪除邏輯不一致：

| Endpoint | 用途 | 問題 |
|----------|------|------|
| `DELETE /{skill_id}` | 刪除單一 source | 缺少 `skill_overviews` 刪除 |
| `DELETE /config/skills/{skill_name}` | 刪除整個 Skill Group | 缺少 `skill_overviews` 刪除 |
| `DELETE /heads/{head_id}` | 刪除 Skill Head | **最嚴重**：只刪除 `skill_metadata` 和 `skill_heads`，遺漏 `skill_chunk_metadata`、`skill_document_mapping`、`skill_overviews` |

### 修復前的刪除覆蓋表

| Table | DELETE /{skill_id} | DELETE /config/skills/{skill_name} | DELETE /heads/{head_id} |
|-------|:------------------:|:----------------------------------:|:-----------------------:|
| skill_metadata | ✅ | ✅ | ✅ |
| skill_chunk_metadata | ✅ | ✅ | ❌ 遺漏 |
| skill_document_mapping | ✅ | ✅ | ❌ 遺漏 |
| skill_overviews | ❌ 遺漏 | ❌ 遺漏 | ❌ 遺漏 |
| skill_heads | - | ✅ | ✅ |

### 修復方案

#### 修改 1: `delete_skill_head()` 方法重寫

**檔案**: `app/Providers/skill_metadata_provider/client.py`  
**位置**: Lines 1192-1261

**修改前**:
```python
async def delete_skill_head(self, head_id: str) -> bool:
    # 只刪除 skill_metadata 和 skill_heads
    await conn.execute("DELETE FROM skill_metadata WHERE head_id = ?", (head_id,))
    await conn.execute("DELETE FROM skill_heads WHERE head_id = ?", (head_id,))
```

**修改後**:
```python
async def delete_skill_head(self, head_id: str) -> bool:
    # Step 1: 取得所有關聯的 skill_ids（關鍵！確保只刪除相關資料）
    cursor = await conn.execute(
        "SELECT skill_id FROM skill_metadata WHERE head_id = ?", (head_id,)
    )
    rows = await cursor.fetchall()
    skill_ids = [row[0] for row in rows]
    
    if skill_ids:
        placeholders = ", ".join(["?" for _ in skill_ids])
        
        # Step 2: DELETE FROM skill_chunk_metadata
        await conn.execute(f"DELETE FROM skill_chunk_metadata WHERE skill_id IN ({placeholders})", skill_ids)
        
        # Step 3: DELETE FROM skill_document_mapping
        await conn.execute(f"DELETE FROM skill_document_mapping WHERE skill_id IN ({placeholders})", skill_ids)
        
        # Step 4: DELETE FROM skill_overviews
        await conn.execute(f"DELETE FROM skill_overviews WHERE skill_id IN ({placeholders})", skill_ids)
    
    # Step 5: DELETE FROM skill_metadata
    await conn.execute("DELETE FROM skill_metadata WHERE head_id = ?", (head_id,))
    
    # Step 6: DELETE FROM skill_heads
    await conn.execute("DELETE FROM skill_heads WHERE head_id = ?", (head_id,))
```

#### 修改 2: `DELETE /{skill_id}` endpoint 加入 skill_overviews

**檔案**: `app/api/v1/endpoints/skills.py`  
**位置**: Lines 3370-3378

**新增程式碼**:
```python
# Delete from skill_overviews (overview/summary data)
cursor.execute(
    "DELETE FROM skill_overviews WHERE skill_id = ?", (skill_id,)
)
overviews_deleted = cursor.rowcount
logger.info(f"Deleted {overviews_deleted} overview records")
```

#### 修改 3: `DELETE /config/skills/{skill_name}` endpoint 加入 skill_overviews

**檔案**: `app/api/v1/endpoints/skills.py`  
**位置**: Lines 2393-2399

**新增程式碼**:
```python
# Delete from skill_overviews (overview/summary data)
cursor.execute(
    "DELETE FROM skill_overviews WHERE skill_id = ?", (skill_id,)
)
total_overviews += cursor.rowcount
```

### 修復後的刪除覆蓋表

| Table | DELETE /{skill_id} | DELETE /config/skills/{skill_name} | DELETE /heads/{head_id} |
|-------|:------------------:|:----------------------------------:|:-----------------------:|
| skill_metadata | ✅ | ✅ | ✅ |
| skill_chunk_metadata | ✅ | ✅ | ✅ |
| skill_document_mapping | ✅ | ✅ | ✅ |
| skill_overviews | ✅ | ✅ | ✅ |
| skill_heads | - | ✅ | ✅ |

### 安全防護設計

**關鍵原則**: 所有刪除操作都必須使用 `WHERE skill_id = ?` 條件，確保：

1. ✅ 只刪除與指定 skill_id 相關的資料
2. ✅ 絕不影響其他 skill 的資料
3. ✅ 先查詢關聯 IDs，再執行刪除（防止誤刪）

### 孤兒資料清理

在修復程式碼前，先清理了現有的孤兒資料：

```sql
-- 清理 skill_chunk_metadata 中的孤兒資料
DELETE FROM skill_chunk_metadata 
WHERE skill_id NOT IN (SELECT skill_id FROM skill_metadata);
-- 結果：刪除 2,592 筆孤兒 chunks
```

---

## 🟡 問題二：Skill 匯入功能排查

### 問題描述

用戶反映：
1. 匯入功能曾出現 `UNIQUE constraint failed: skill_chunk_metadata.chunk_id` 錯誤
2. 匯出的 ZIP 檔解壓後有一層 skill 名稱的資料夾，懷疑是否影響匯入

### ZIP 結構分析

實際 ZIP 結構：
```
skill_export_ML.zip
└── 機器學習/              ← Skill 名稱資料夾（第一層）
    ├── manifest.json      ← 匯出設定與 metadata
    ├── skill_chunk_metadata.csv  ← chunks 資料（資料量大用 CSV）
    └── faiss_indices/     ← FAISS 向量索引
        └── skill_20260113_061734_4209c143_8388d1/
            ├── index.faiss
            └── index.pkl
```

### 程式碼處理方式

**檔案**: `app/api/v1/endpoints/skills.py`  
**位置**: Lines 4531-4538

```python
# 6. 找到 skill 資料夾（ZIP 內第一層）
skill_folders = [d for d in extract_dir.iterdir() if d.is_dir()]

if not skill_folders:
    raise HTTPException(
        status_code=400, detail="Invalid ZIP structure: no skill folder found"
    )

skill_folder = skill_folders[0]  # 使用第一個資料夾（例如「機器學習」）
```

**結論**: ZIP 內的 skill 名稱資料夾是**正常設計**，程式碼已正確處理。

### 匯入錯誤的真正原因

`UNIQUE constraint failed` 錯誤是由**孤兒資料**造成的：

1. 之前刪除 skill 時沒有清理 `skill_chunk_metadata`
2. 匯入時嘗試插入相同 `chunk_id` 的記錄
3. 觸發 UNIQUE constraint 違規

### 已實施的修復（之前會話）

1. **INSERT OR REPLACE**: 匯入時使用 `INSERT OR REPLACE` 避免 UNIQUE 衝突
   ```python
   # Line 4970
   sql = f"INSERT OR REPLACE INTO skill_chunk_metadata ({', '.join(columns)}) VALUES ({placeholders})"
   ```

2. **Preview API 修正**: 
   - 修正 `manifest.get("metadata")` → `manifest.get("skill_metadata")`
   - 修正 export_date 讀取順序

### 測試驗證

重啟伺服器後進行完整測試：

#### Preview API 測試
```bash
curl -X POST "http://localhost:8082/api/v1/skills/config/skills/preview" \
  -F "file=@refData/test/skill_export_ML.zip"
```

**結果**:
```json
{
    "skill_name": "機器學習",
    "document_count": 1,
    "total_chunks": 475,
    "export_date": "2026-01-13T06:28:34.482972+00:00",
    "export_version": "2.0",
    "documents": [
        {"name": "Machine_Learning_Production_Systems_oreilly_2024", "chunks": 475}
    ],
    "has_name_conflict": false,
    "has_id_conflict": false
}
```

#### Import API 測試
```bash
curl -X POST "http://localhost:8082/api/v1/skills/config/skills/import" \
  -F "file=@refData/test/skill_export_ML.zip"
```

**結果**:
```json
{
    "success": true,
    "message": "Skill '機器學習' imported successfully",
    "head_id": "head_20260113_141642_4209c143",
    "skill_ids": ["skill_20260113_061734_4209c143_8388d1"],
    "document_count": 1,
    "total_chunks": 475
}
```

#### 資料庫驗證
```sql
-- skill_heads
SELECT head_id, skill_name FROM skill_heads WHERE skill_name = '機器學習';
-- 結果: head_20260113_141642_4209c143 | 機器學習

-- skill_metadata  
SELECT skill_id, total_chunks, source_name FROM skill_metadata WHERE skill_name = '機器學習';
-- 結果: skill_20260113_061734_4209c143_8388d1 | 475 | Machine_Learning_Production_Systems_oreilly_2024

-- skill_chunk_metadata
SELECT COUNT(*) FROM skill_chunk_metadata WHERE skill_id = 'skill_20260113_061734_4209c143_8388d1';
-- 結果: 475
```

---

## 📁 修改的檔案清單

| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| `app/Providers/skill_metadata_provider/client.py` | 修改 | 重寫 `delete_skill_head()` 方法，實現完整 cascade deletion |
| `app/api/v1/endpoints/skills.py` | 修改 | 兩處加入 `skill_overviews` 刪除邏輯（Lines 2393-2399, 3370-3378） |

---

## 🔄 回滾方案

如需回滾，執行：
```bash
git checkout HEAD~1 -- app/Providers/skill_metadata_provider/client.py
git checkout HEAD~1 -- app/api/v1/endpoints/skills.py
```

---

## ✅ 驗證清單

- [x] `delete_skill_head()` 方法重寫完成
- [x] `DELETE /{skill_id}` endpoint 加入 skill_overviews 刪除
- [x] `DELETE /config/skills/{skill_name}` endpoint 加入 skill_overviews 刪除
- [x] 孤兒資料已清理（2,592 筆）
- [x] Preview API 測試通過
- [x] Import API 測試通過
- [x] 資料庫記錄驗證通過
- [x] 伺服器重啟並套用新程式碼

---

## 🟢 問題三：匯入完成後無法關閉 Preview Modal

### 問題描述

匯入 Skill 完成後，點擊關閉按鈕或匯入成功後，Preview Modal 視窗無法關閉。

### 根本原因

Modal 的顯示與隱藏使用了不一致的方式：

| 操作 | 程式碼 | 問題 |
|------|--------|------|
| **顯示** | `modal.style.display = "flex"` + `classList.add("active")` | 使用兩種方式 |
| **關閉** | `classList.remove("active")` | ❌ 只移除 class，沒有設定 `display: none` |

動態建立的 modal 使用 inline style `display: flex`，但 `closeModal()` 函數只移除 CSS class，導致 modal 仍然可見。

### 修復方案

#### 修改 1: 通用 `closeModal()` 函數

**檔案**: `template/skill_config.html`  
**位置**: Lines 2704-2712

**修改前**:
```javascript
function closeModal(id) {
    document.getElementById(id).classList.remove("active");
}
```

**修改後**:
```javascript
function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.remove("active");
        // 處理動態建立的 modal（使用 inline style display: flex）
        if (modal.style.display === "flex") {
            modal.style.display = "none";
        }
    }
}
```

#### 修改 2: 加強 `closeImportPreview()` 函數

**檔案**: `template/skill_config.html`  
**位置**: Lines 4135-4145

**修改前**:
```javascript
function closeImportPreview() {
    closeModal("import-preview-modal");
    document.getElementById("import-file-input").value = "";
    pendingImportFile = null;
}
```

**修改後**:
```javascript
function closeImportPreview() {
    const modal = document.getElementById("import-preview-modal");
    if (modal) {
        modal.style.display = "none";
        modal.classList.remove("active");
    }
    const fileInput = document.getElementById("import-file-input");
    if (fileInput) {
        fileInput.value = "";
    }
    pendingImportFile = null;
}
```

#### 修改 3: 匯入成功後使用正確的關閉函數

**檔案**: `template/skill_config.html`  
**位置**: Line 4179

**修改前**:
```javascript
closeModal("import-preview-modal");
```

**修改後**:
```javascript
// 使用完整的關閉邏輯（包含 display:none）
closeImportPreview();
```

### 影響範圍

- ✅ 匯入 Preview Modal 可正確關閉
- ✅ Loading Modal 可正確關閉
- ✅ 其他靜態 modal 不受影響

---

## 📝 後續建議

1. **定期檢查孤兒資料**:
   ```sql
   SELECT COUNT(*) as orphan_count 
   FROM skill_chunk_metadata 
   WHERE skill_id NOT IN (SELECT skill_id FROM skill_metadata);
   ```
   期望結果應為 0。

2. **考慮加入資料庫外鍵約束**:
   SQLite 支援 FOREIGN KEY，可考慮在未來版本加入以自動維護資料完整性。

3. **匯入前備份**:
   在進行大量匯入前，建議先備份 `skill_metadata.db`。

---

*文件產生時間: 2026-01-13 16:14*
*SuperClaude Framework v2.0.1*
