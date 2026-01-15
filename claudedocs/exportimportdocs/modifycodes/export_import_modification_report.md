# Export/Import 功能修改報告

**日期**: 2026-01-08
**修改檔案**: `app/api/v1/endpoints/skills.py`
**版本變更**: v1.0 → v2.0

---

## 1. 問題分析

### 1.1 原始問題

用戶指出：匯入時生成新的 `skill_id` 是無意義的，因為：

1. `skill_chunk_metadata` 表中的資料 `skill_id = skill_20251126_104421_4fdb3e9b`
2. 這些資料屬於原「大語言模型大全」skill
3. 新建 skill_id 會導致 SQLite 資料與 FAISS 索引不匹配

### 1.2 用戶要求的解決方案

1. **不生成新 skill_id** - 保留原始 ID
2. **Metadata 放入 manifest.json** - 不使用多個 CSV 檔
3. **只保留 skill_chunk_metadata.csv** - 因資料量大
4. **匯入時先讀 manifest.json**
5. **只在 ID 衝突時才生成新 ID**

---

## 2. FAISS ↔ SQLite 關係分析

### 2.1 查詢流程

```
FAISS 查詢：
┌─────────────────┐
│ index.search()  │ ──→ 返回 indices (整數陣列: [24, 15, 67, ...])
└─────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ get_chunk_metadata(skill_id, ..., faiss_index)  │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ SELECT * FROM skill_chunk_metadata              │
│ WHERE skill_id = ? AND chunk_index = ?          │  ← 使用整數索引
└─────────────────────────────────────────────────┘
```

### 2.2 關鍵發現

| 欄位 | 查詢中使用 | 說明 |
|------|-----------|------|
| skill_id | ✅ 是 | SQL WHERE 條件 |
| chunk_index | ✅ 是 | SQL WHERE 條件（整數） |
| chunk_id | ❌ 否 | 只是 PRIMARY KEY |

**結論**: 系統使用 `skill_id` + `chunk_index`（整數）查詢，不依賴 `chunk_id` 字串。

### 2.3 ID 衝突處理策略

當目標機器已有相同 ID 時：

| 資料 | 處理方式 | 原因 |
|------|---------|------|
| skill_id | 生成新 ID | SQL 查詢條件 |
| chunk_index | **不變** | 整數順序與 FAISS 一致 |
| chunk_id | 更新前綴 | 保持一致性（非必要） |
| FAISS 目錄 | 重命名 | 路徑需匹配新 skill_id |

---

## 3. 程式碼修改

### 3.1 export_skill 函數修改

**位置**: `app/api/v1/endpoints/skills.py` Lines 3886-4025

**變更**: 將 metadata 嵌入 manifest.json，不再使用多個 CSV

#### 修改前 (v1.0)

```python
# 匯出多個 CSV 檔案
csv_files = {
    "skill_heads.csv": skill_heads_data,
    "skill_metadata.csv": skill_metadata_data,
    "skill_document_mapping.csv": doc_mapping_data,
    "skill_chunk_metadata.csv": chunk_metadata_data,
    "skill_overviews.csv": overviews_data,
}

manifest = {
    "export_version": "1.0",
    "csv_files": list(csv_files.keys()),
    # ...
}
```

#### 修改後 (v2.0)

```python
# 只匯出 skill_chunk_metadata.csv（資料量大）
csv_files = {
    "skill_chunk_metadata.csv": chunk_metadata_data,
}

# 其他 metadata 嵌入 manifest.json
manifest = {
    "export_version": "2.0",
    "export_date": datetime.now(timezone.utc).isoformat(),
    "head_id": head_id,
    "skill_ids": skill_ids_with_faiss,
    "skill_name": skill_name,
    # ===== 內嵌 metadata =====
    "skill_heads": skill_heads_data,           # List[Dict]
    "skill_metadata": skill_metadata_data,     # List[Dict]
    "skill_document_mapping": doc_mapping_data, # List[Dict]
    "skill_overviews": overviews_data,         # List[Dict]
    "csv_files": ["skill_chunk_metadata.csv"],
    "faiss_folders": skill_ids_with_faiss,
}
```

### 3.2 import_skill 函數修改

**位置**: `app/api/v1/endpoints/skills.py` Lines 4096-4555

**變更**: 完全重寫，加入 ID 衝突檢測

#### 核心邏輯：ID 衝突檢測 (Lines 4229-4272)

```python
# 1. 檢查 head_id 是否衝突
cursor.execute(
    "SELECT COUNT(*) FROM skill_heads WHERE head_id = ?",
    (original_head_id,)
)
head_id_conflict = cursor.fetchone()[0] > 0

# 2. 檢查每個 skill_id 是否衝突
skill_id_conflicts = []
for sid in original_skill_ids:
    cursor.execute(
        "SELECT COUNT(*) FROM skill_metadata WHERE skill_id = ?",
        (sid,)
    )
    if cursor.fetchone()[0] > 0:
        skill_id_conflicts.append(sid)

# 3. 根據衝突情況決定策略
if head_id_conflict or skill_id_conflicts:
    # 有衝突 → 生成新 ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_suffix = uuid.uuid4().hex[:8]
    final_head_id = f"head_{timestamp}_{unique_suffix}"

    id_mapping = {}
    for old_sid in original_skill_ids:
        new_suffix = uuid.uuid4().hex[:6]
        new_sid = f"skill_{timestamp}_{unique_suffix}_{new_suffix}"
        id_mapping[old_sid] = new_sid

    ids_were_changed = True
else:
    # 無衝突 → 保留原始 ID ✅ (v2.0 核心變更)
    final_head_id = original_head_id
    id_mapping = {sid: sid for sid in original_skill_ids}
    ids_were_changed = False
```

---

## 4. 如何更新前綴（chunk_id 處理）

### 4.1 程式碼位置

**檔案**: `app/api/v1/endpoints/skills.py`
**位置**: Lines 4368-4379

### 4.2 完整程式碼

```python
# 12. 讀取 skill_chunk_metadata.csv（所有版本都用 CSV）
chunk_csv_path = skill_folder / "skill_chunk_metadata.csv"
chunk_data = []

if chunk_csv_path.exists():
    with open(chunk_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        chunk_headers = reader.fieldnames
        for row in reader:
            # 更新 skill_id（如果有衝突）
            if row.get('skill_id') in id_mapping:
                old_skill_id = row['skill_id']
                new_skill_id = id_mapping[old_skill_id]
                row['skill_id'] = new_skill_id

                # 只有在 ID 變更時才更新 chunk_id
                if ids_were_changed and row.get('chunk_id', '').startswith(old_skill_id):
                    row['chunk_id'] = row['chunk_id'].replace(old_skill_id, new_skill_id, 1)

            chunk_data.append(row)
```

### 4.3 前綴更新邏輯說明

#### 原始 chunk_id 格式

```
chunk_id = "skill_20251126_104421_4fdb3e9b_doc_871d2f9d_p25"
            ├─────────────────────────────┤ ├─────────────────┤
                     skill_id 前綴              後綴部分
```

#### 更新條件

```python
if ids_were_changed and row.get('chunk_id', '').startswith(old_skill_id):
```

| 條件 | 說明 |
|------|------|
| `ids_were_changed` | 只有在 ID 確實變更時才處理 |
| `.startswith(old_skill_id)` | 確認 chunk_id 以舊 skill_id 為前綴 |

#### 更新方式

```python
row['chunk_id'] = row['chunk_id'].replace(old_skill_id, new_skill_id, 1)
```

- **`.replace(old, new, 1)`**: 只替換第一次出現的前綴
- 這確保只更新前綴，不會影響後綴中可能出現的相似字串

#### 範例

```
情境：skill_id 從 "skill_20251126_104421_4fdb3e9b"
      變更為 "skill_20260108_153022_abc12345"

原始 chunk_id:
  "skill_20251126_104421_4fdb3e9b_doc_871d2f9d_p25"

更新後 chunk_id:
  "skill_20260108_153022_abc12345_doc_871d2f9d_p25"
   ├───────────────────────────────┤
           新的 skill_id 前綴
```

### 4.4 為何 chunk_index 不需要更新

```python
# chunk_index 是整數，不包含 skill_id
# 它是 FAISS 向量索引的位置，從 0 開始連續編號
# FAISS 查詢返回整數索引，SQLite 使用相同整數查詢

chunk_index = 25  # 整數，不受 skill_id 變更影響
```

### 4.5 完整的 ID 對映表

當發生衝突時，系統建立以下對映：

```python
# id_mapping 結構
id_mapping = {
    "skill_20251126_104421_4fdb3e9b": "skill_20260108_153022_abc12345",
    "skill_20251126_104421_4fdb3e9b_src_00": "skill_20260108_153022_abc12345_def678",
    # ... 其他 skill_id
}

# final_head_id
original_head_id = "head_20251126_104421_4fdb3e9b"
final_head_id = "head_20260108_153022_abc12345"
```

### 4.6 需要更新的所有欄位

| 表 | 欄位 | 更新方式 |
|---|------|---------|
| skill_heads | head_id | 直接替換 |
| skill_metadata | skill_id | 直接替換 |
| skill_metadata | head_id | 直接替換 |
| skill_document_mapping | skill_id | 直接替換 |
| skill_document_mapping | head_id | 直接替換 |
| skill_chunk_metadata | skill_id | 直接替換 |
| skill_chunk_metadata | chunk_id | **前綴替換** |
| skill_chunk_metadata | chunk_index | **不更新** |
| skill_overviews | skill_id | 直接替換 |
| FAISS 目錄 | 目錄名 | 重命名 |

---

## 5. 格式相容性

### 5.1 v2.0 格式（新）

```
skill_export_xxx.zip
├── manifest.json          # 包含所有 metadata
├── skill_chunk_metadata.csv  # 大量 chunk 資料
└── faiss_indices/
    └── skill_xxx/
        └── index.faiss
```

### 5.2 v1.0 格式（舊）

```
skill_export_xxx.zip
├── manifest.json          # 只有基本資訊
├── skill_heads.csv
├── skill_metadata.csv
├── skill_document_mapping.csv
├── skill_chunk_metadata.csv
├── skill_overviews.csv
└── faiss_indices/
    └── skill_xxx/
        └── index.faiss
```

### 5.3 向後相容

匯入函數同時支援 v1.0 和 v2.0 格式：

```python
if manifest.get("export_version") == "2.0":
    # 從 manifest.json 讀取嵌入的 metadata
    skill_heads_data = manifest.get("skill_heads", [])
    skill_metadata_data = manifest.get("skill_metadata", [])
    # ...
else:
    # v1.0: 從 CSV 檔案讀取
    skill_heads_data = read_csv("skill_heads.csv")
    # ...
```

---

## 6. 測試驗證

### 6.1 語法檢查

```bash
python3 -m py_compile app/api/v1/endpoints/skills.py
# ✅ 通過，無語法錯誤
```

### 6.2 建議測試案例

| 案例 | 預期結果 |
|------|---------|
| 匯出→匯入（同機器，無衝突） | 保留原始 ID |
| 匯出→匯入（已有相同 ID） | 生成新 ID，資料正確對映 |
| v1.0 格式匯入 | 向後相容，正常匯入 |
| 匯入後查詢 | FAISS 結果正確對應 SQLite 資料 |

---

## 7. 變更摘要

| 項目 | v1.0 | v2.0 |
|------|------|------|
| Metadata 儲存 | 多個 CSV 檔 | manifest.json 嵌入 |
| skill_id 處理 | 一律生成新 ID | 優先保留原 ID |
| 衝突檢測 | 無 | 有（head_id + skill_id） |
| chunk_id 更新 | 無 | 前綴替換（僅衝突時） |
| chunk_index | 不處理 | 保持不變（與 FAISS 對應） |
| 向後相容 | - | 支援 v1.0 匯入 |

---

## 8. 結論

本次修改解決了以下問題：

1. ✅ **不必要的 ID 生成** - 無衝突時保留原 ID
2. ✅ **FAISS-SQLite 對映** - 使用 `chunk_index` 整數對映，不受 `chunk_id` 影響
3. ✅ **chunk_id 前綴更新** - 僅在 ID 衝突時執行前綴替換
4. ✅ **格式簡化** - Metadata 集中於 manifest.json
5. ✅ **向後相容** - 支援 v1.0 格式匯入
6. ✅ **衝突處理** - 只在必要時生成新 ID，並正確更新所有相關資料
