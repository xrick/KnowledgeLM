# 修改日記: 資料庫 Schema 低風險修復 (4 項)

**日期時間**: 2026-01-27 14:51
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟢 低

## 修改摘要
針對 skill_metadata.db 資料庫的 4 項低風險高價值問題進行修復：補齊缺失的 CREATE TABLE、修正查錯表的 SQL、清理孤兒記錄、統一 head_id 前綴。

## 修改項目

### 1. 補齊 skill_chunk_metadata 的 CREATE TABLE

**問題**: `initialize_database()` 中缺少 `skill_chunk_metadata` 表的 CREATE TABLE，新環境部署時會因表不存在導致 INSERT 失敗。

**修正**: 在 `client.py` 的 `initialize_database()` 方法中，於 `processing_jobs` 表之前新增 CREATE TABLE 及兩個索引。

**Schema 定義**:
```sql
CREATE TABLE IF NOT EXISTS skill_chunk_metadata (
    chunk_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    document_name TEXT NOT NULL,
    page_number INTEGER,
    chunk_index INTEGER,
    chunk_text TEXT,
    embedding_model TEXT DEFAULT 'BAAI/bge-m3',
    embedding_dimension INTEGER DEFAULT 1024,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
)
```

### 2. 修正 skills.py 刪除函數查錯表的問題

**問題**: `delete_skill_by_name` 函數中 Step 2 使用 `SELECT skill_id FROM skill_metadata WHERE skill_name = ?` 查找要刪除的記錄。但 `skill_name` 在 `skill_metadata` 中不是唯一的（可能有多份同名文件），應優先使用 `head_id` 查找。

**修正**:
- 在函數開頭初始化 `skill_head = None` 和 `head_id = None`
- Step 2 優先使用 `head_id` 查找：`SELECT skill_id FROM skill_metadata WHERE head_id = ?`
- 保留 `skill_name` 作為 fallback（當 Step 1 未找到 head 時）

### 3. 清理孤兒記錄

**問題**:
- `skill_document_mapping` 有 9 筆 `skill_id` 指向不存在的 `skill_metadata` 記錄
- `skill_metadata` 有 1 筆 `parent_skill_id` 指向不存在的記錄

**修正**:
- 刪除 9 筆 `skill_document_mapping` 孤兒記錄 (mapping_id: 1, 2, 8, 9, 10, 11, 12, 15, 77)
- 將 1 筆孤兒的 `parent_skill_id` 從 `skill_20251203_071733_2a43e5ac` 修正為 `'root'`
  - 受影響記錄: `skill_20260108_035814_2a43e5ac_8f1f01` (大語言模型大全 / Build_a_Large_Language_Model)

### 4. 統一 head_id 前綴

**問題**: 六法全書-民法的 `head_id` 使用 `skill_` 前綴 (`skill_20251203_054249_f333015b`)，其他 5 個 skill_heads 都使用 `head_` 前綴。

**修正**: 使用 Transaction 將 `skill_20251203_054249_f333015b` → `head_20251203_054249_f333015b`
- `skill_heads.head_id`: 1 筆更新 (PK)
- `skill_metadata.head_id`: 5 筆更新 (FK)
- `skill_metadata.parent_skill_id`: 5 筆更新 (引用舊 head_id)
- `processing_jobs.head_id`: 0 筆 (無影響)
- FAISS 目錄: 無影響 (使用 skill_id 非 head_id)

## 修改檔案

| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| `app/Providers/skill_metadata_provider/client.py` | 修改 | `initialize_database()` 新增 skill_chunk_metadata CREATE TABLE + 2 索引 |
| `app/api/v1/endpoints/skills.py` | 修改 | `delete_skill_by_name` 初始化變數 + 優先用 head_id 查找 |
| `data/skill_metadata.db` | 修改 | 清理孤兒 + 統一 head_id 前綴 |

## 影響分析

- 影響範圍: 資料庫初始化、Skill 刪除功能、資料完整性
- 向後相容: 是 (CREATE TABLE IF NOT EXISTS 不影響已有表；SQL 查詢邏輯有 fallback)
- FAISS 索引: 不受影響
- 前端: 不受影響

## 回滾方案

1. **程式碼**: `git checkout -- app/Providers/skill_metadata_provider/client.py app/api/v1/endpoints/skills.py`
2. **資料庫**: `cp data/skill_metadata.db.backup_20260127_fix data/skill_metadata.db`

## 驗證結果

- [x] Python 語法檢查通過 (client.py, skills.py)
- [x] 所有 head_id 統一使用 head_ 前綴 (6/6)
- [x] skill_document_mapping 無孤兒記錄 (0)
- [x] parent_skill_id 無孤兒 (0)
- [x] skill_chunk_metadata 表存在且有資料 (1603 筆)
- [ ] 重啟伺服器驗證（需要用戶執行）
