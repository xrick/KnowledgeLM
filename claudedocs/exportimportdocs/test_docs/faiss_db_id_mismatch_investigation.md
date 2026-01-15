# FAISS/DB ID Mismatch Investigation Report

**調查日期**: 2026-01-08
**調查人員**: Claude Code Assistant
**問題描述**: 資料庫中的 skill_id 與實際 FAISS 目錄名稱不一致

---

## 1. 問題發現

### 1.1 現象

在進行 TEST-02 備份時發現：

| 來源 | skill_id | 時間戳 |
|------|----------|--------|
| **Database** | `skill_20251216_123603_2a43e5ac_9ed582` | 12:36:03 |
| **FAISS Directory** | `skill_20251216_043501_2a43e5ac_9ed582` | 04:35:01 |

### 1.2 關鍵觀察

- Hash 後綴相同: `2a43e5ac_9ed582`（證明是同一個 skill_name 和 PDF）
- 時間戳差異: 約 **8 小時**
- 這是 UTC vs 本地時間 (UTC+8) 的典型差異

---

## 2. 根本原因分析

### 2.1 時區不一致問題

經過程式碼審查，發現以下位置使用不同的時區設定：

| 檔案位置 | 函數 | 時區 |
|----------|------|------|
| `skills.py:3170` | `create_skill_head()` | `datetime.now()` **本地時間** |
| `skills.py:1444` | `process_pdf_for_skill_streaming()` | `datetime.now(timezone.utc)` **UTC** |
| `skills.py:955` | `process_pdf_for_skill()` | `datetime.now(timezone.utc)` **UTC** |
| `skills.py:4179` | `import_skill()` | `datetime.now(timezone.utc)` **UTC** |

### 2.2 問題程式碼

```python
# skills.py:3170 - 使用本地時間（問題程式碼）
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# skills.py:1444 - 使用 UTC（正確做法）
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
```

### 2.3 可能的觸發場景

1. **場景 A**: 先呼叫 `create_skill_head()` 建立 head（使用本地時間）
2. **場景 B**: 再呼叫 `process_pdf_for_skill_streaming()` 上傳 PDF（使用 UTC）
3. **結果**: 產生不同的 timestamp，導致 FAISS 目錄名稱與資料庫紀錄不一致

---

## 3. 影響範圍

### 3.1 受影響的 Skill

```sql
-- 查詢資料庫中的 skill_id
SELECT skill_id FROM skill_metadata WHERE head_id = 'skill_20251203_071733_2a43e5ac';
-- 結果: skill_20251216_123603_2a43e5ac_9ed582

-- 實際存在的 FAISS 目錄
ls data/faiss_indices/skills/
-- 結果: skill_20251216_043501_2a43e5ac_9ed582
```

### 3.2 功能影響

- **Export**: 會查詢資料庫取得 skill_id，但該目錄可能不存在
- **Query**: 會嘗試載入不存在的 FAISS 索引
- **Delete**: 會刪除不存在的目錄（無法清理）

---

## 4. 修復建議

### 4.1 立即修復（資料庫校正）

手動更新資料庫，使其指向正確的 FAISS 目錄：

```sql
-- 更新 skill_chunk_metadata
UPDATE skill_chunk_metadata
SET skill_id = 'skill_20251216_043501_2a43e5ac_9ed582'
WHERE skill_id = 'skill_20251216_123603_2a43e5ac_9ed582';

-- 更新 skill_metadata
UPDATE skill_metadata
SET skill_id = 'skill_20251216_043501_2a43e5ac_9ed582'
WHERE skill_id = 'skill_20251216_123603_2a43e5ac_9ed582';

-- 更新 skill_document_mapping
UPDATE skill_document_mapping
SET skill_id = 'skill_20251216_043501_2a43e5ac_9ed582'
WHERE skill_id = 'skill_20251216_123603_2a43e5ac_9ed582';

-- 更新 skill_overviews
UPDATE skill_overviews
SET skill_id = 'skill_20251216_043501_2a43e5ac_9ed582'
WHERE skill_id = 'skill_20251216_123603_2a43e5ac_9ed582';

-- 更新 chunk_id（包含 skill_id 前綴）
UPDATE skill_chunk_metadata
SET chunk_id = REPLACE(chunk_id, 'skill_20251216_123603_2a43e5ac_9ed582', 'skill_20251216_043501_2a43e5ac_9ed582')
WHERE chunk_id LIKE 'skill_20251216_123603_2a43e5ac_9ed582%';
```

### 4.2 程式碼修復（防止未來問題）

統一所有 timestamp 生成使用 UTC：

```python
# skills.py:3170 - 修正
# 原本：
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
# 修改為：
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
```

### 4.3 驗證腳本

```python
# 驗證 FAISS 目錄與資料庫一致性
import sqlite3
from pathlib import Path

db_path = "data/skill_metadata.db"
faiss_base = Path("data/faiss_indices/skills")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT DISTINCT skill_id FROM skill_metadata")
db_skill_ids = {row[0] for row in cursor.fetchall()}
conn.close()

faiss_skill_ids = {d.name for d in faiss_base.iterdir() if d.is_dir()}

# 檢查不一致
db_only = db_skill_ids - faiss_skill_ids
faiss_only = faiss_skill_ids - db_skill_ids

if db_only:
    print(f"❌ 資料庫有但 FAISS 沒有: {db_only}")
if faiss_only:
    print(f"⚠️ FAISS 有但資料庫沒有: {faiss_only}")
if not db_only and not faiss_only:
    print("✅ 資料庫與 FAISS 完全一致")
```

---

## 5. 結論

### 5.1 根本原因
`create_skill_head()` 函數使用本地時間生成 timestamp，而其他函數使用 UTC，導致在 UTC+8 時區環境下產生 8 小時的時間差異。

### 5.2 建議行動
1. **優先**: 更新資料庫記錄，指向正確的 FAISS 目錄
2. **次要**: 修正程式碼，統一使用 UTC
3. **測試**: 繼續進行 TEST-02，驗證修復後的 Export/Import 功能

---

**報告產生時間**: 2026-01-08 11:45
**下一步**: 執行資料庫校正後，繼續 TEST-02 測試
