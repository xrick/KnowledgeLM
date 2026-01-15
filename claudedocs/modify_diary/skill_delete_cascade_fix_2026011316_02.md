# 修改日記: Skill 刪除邏輯完整修復（Cascade Deletion）

**日期時間**: 2026-01-13 16:02
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟡 中

## 修改摘要
修復三個 skill 刪除 endpoint，確保刪除時會清理所有相關 tables 的資料，避免產生孤兒資料（orphan data）。

## 問題背景

### 發現的問題
1. **孤兒資料**: 發現 2,592 筆孤兒 chunks 在 `skill_chunk_metadata` 中（已刪除的 skill 資料未清理）
2. **不完整刪除**: 三個刪除 endpoint 未統一刪除所有相關 tables

### 刪除邏輯分析（修復前）

| Endpoint | skill_metadata | skill_chunk_metadata | skill_document_mapping | skill_overviews | skill_heads |
|----------|---------------|---------------------|----------------------|-----------------|-------------|
| `DELETE /{skill_id}` | ✅ | ✅ | ✅ | ❌ 遺漏 | ❌ |
| `DELETE /config/skills/{skill_name}` | ✅ | ✅ | ✅ | ❌ 遺漏 | ✅ |
| `DELETE /heads/{head_id}` | ✅ | ❌ 遺漏 | ❌ 遺漏 | ❌ 遺漏 | ✅ |

## 修改檔案

| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| `app/Providers/skill_metadata_provider/client.py` | 修改 | 重寫 `delete_skill_head()` 方法，加入完整 cascade deletion |
| `app/api/v1/endpoints/skills.py` | 修改 | 兩處加入 `skill_overviews` 刪除邏輯 |

## 修改詳情

### 1. `delete_skill_head()` 方法 (client.py Lines 1192-1261)

**修改前**: 只刪除 `skill_metadata` 和 `skill_heads`

**修改後**: 完整 6 步驟 cascade deletion
```python
# Step 1: 取得所有關聯的 skill_ids（關鍵！確保只刪除相關資料）
# Step 2: DELETE FROM skill_chunk_metadata WHERE skill_id IN (...)
# Step 3: DELETE FROM skill_document_mapping WHERE skill_id IN (...)
# Step 4: DELETE FROM skill_overviews WHERE skill_id IN (...)
# Step 5: DELETE FROM skill_metadata WHERE head_id = ?
# Step 6: DELETE FROM skill_heads WHERE head_id = ?
```

### 2. `DELETE /{skill_id}` endpoint (skills.py Lines 3370-3378)

**新增**: `skill_overviews` 刪除
```python
# Delete from skill_overviews (overview/summary data)
cursor.execute(
    "DELETE FROM skill_overviews WHERE skill_id = ?", (skill_id,)
)
overviews_deleted = cursor.rowcount
```

### 3. `DELETE /config/skills/{skill_name}` endpoint (skills.py Lines 2393-2399)

**新增**: `skill_overviews` 刪除（在 for loop 中）
```python
# Delete from skill_overviews (overview/summary data)
cursor.execute(
    "DELETE FROM skill_overviews WHERE skill_id = ?", (skill_id,)
)
total_overviews += cursor.rowcount
```

## 修復後刪除邏輯

| Endpoint | skill_metadata | skill_chunk_metadata | skill_document_mapping | skill_overviews | skill_heads |
|----------|---------------|---------------------|----------------------|-----------------|-------------|
| `DELETE /{skill_id}` | ✅ | ✅ | ✅ | ✅ | ❌ (不適用) |
| `DELETE /config/skills/{skill_name}` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `DELETE /heads/{head_id}` | ✅ | ✅ | ✅ | ✅ | ✅ |

## 安全防護

**關鍵設計**: 所有刪除操作都使用 `WHERE skill_id = ?` 或 `WHERE skill_id IN (...)` 條件，確保：
- ✅ 只刪除與指定 skill_id 相關的資料
- ✅ 絕不影響其他 skill 的資料
- ✅ 先查詢關聯 IDs，再執行刪除（防止誤刪）

## 影響分析
- 影響範圍: 所有 skill 刪除操作
- 向後相容: 是（API 介面不變，只是內部邏輯更完整）
- 需要測試: 
  1. 刪除單一 skill (`DELETE /{skill_id}`)
  2. 刪除整個 skill group (`DELETE /config/skills/{skill_name}`)
  3. 刪除 skill head (`DELETE /heads/{head_id}`)
  4. 驗證其他 skill 資料不受影響

## 回滾方案
```bash
# 使用 git 回滾
git checkout HEAD~1 -- app/Providers/skill_metadata_provider/client.py
git checkout HEAD~1 -- app/api/v1/endpoints/skills.py
```

## 驗證結果
- [x] 程式碼邏輯審查通過
- [ ] 單元測試通過
- [ ] 整合測試通過
- [ ] 手動驗證通過

## 建議測試步驟
```bash
# 1. 重啟服務
./stop_system.sh && ./start_system.sh

# 2. 測試刪除 skill（觀察 log 確認所有 tables 都有刪除）
curl -X DELETE "http://localhost:8082/api/v1/skills/{test_skill_id}"

# 3. 檢查孤兒資料
sqlite3 data/skill_metadata.db "
SELECT COUNT(*) as orphan_chunks 
FROM skill_chunk_metadata 
WHERE skill_id NOT IN (SELECT skill_id FROM skill_metadata);
"
# 期望結果: 0
```
