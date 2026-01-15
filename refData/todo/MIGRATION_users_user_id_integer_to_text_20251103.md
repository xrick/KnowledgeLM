# MIGRATION: users.user_id INTEGER → TEXT (UUID Format)

## 概述 (Overview)

**日期**: 2025-11-03
**目的**: 將 `users` 表格的 `user_id` 欄位從 `INTEGER` 轉換為 `TEXT`，以與 `file_metadata.user_id` 保持一致，實現真正的多用戶系統。

## 問題陳述 (Problem Statement)

### 不一致性 (Inconsistency)

**Before Migration**:
- `users.user_id`: **INTEGER** (auto-increment primary key)
- `file_metadata.user_id`: **TEXT** (UUID v4 format)

**問題**:
1. ❌ 資料型別不匹配，無法建立外鍵關係
2. ❌ 前端生成的 UUID (TEXT) 無法與 users 表的 INTEGER ID 對應
3. ❌ 多用戶檔案管理系統無法正確關聯用戶與檔案

### 目標 (Goal)

**After Migration**:
- `users.user_id`: **TEXT** (UUID v4 format) ✅
- `file_metadata.user_id`: **TEXT** (UUID v4 format) ✅

**好處**:
1. ✅ 兩個表格使用相同的資料型別
2. ✅ 支援前端生成的 UUID v4 用戶識別符
3. ✅ 可以建立外鍵關係確保資料完整性
4. ✅ 多用戶系統完整運作

---

## 遷移過程 (Migration Process)

### 遷移腳本 (Migration Script)

**檔案**: [scripts/migrate_users_table_user_id_to_text.py](scripts/migrate_users_table_user_id_to_text.py)

### 執行命令 (Execution Command)

```bash
python scripts/migrate_users_table_user_id_to_text.py
```

### 遷移步驟 (Migration Steps)

```
1. 📦 備份資料庫 (Backup database)
   → data/docai_backup_20251103_203324.db

2. 📊 檢查現有資料 (Check existing data)
   → Found 0 existing users

3. 🔨 建立新表格結構 (Create new table structure)
   → CREATE TABLE users_new (user_id TEXT PRIMARY KEY, ...)

4. 📦 遷移現有資料 (Migrate existing data)
   → CAST(user_id AS TEXT) for existing rows
   → 0 rows migrated

5. 🗑️  刪除舊表格 (Drop old table)
   → DROP TABLE users

6. 🔄 重新命名新表格 (Rename new table)
   → ALTER TABLE users_new RENAME TO users

7. 📇 重建索引 (Recreate indexes)
   → CREATE INDEX idx_users_username ON users(username)
   → CREATE INDEX idx_users_email ON users(email)

8. ✅ 驗證遷移 (Verify migration)
   → user_id column type: TEXT ✅
   → Data integrity verified: All users migrated ✅
```

### 執行結果 (Execution Result)

```
======================================================================
✅ Migration completed successfully!
======================================================================

Next steps:
  1. Test user authentication with UUID user_id
  2. Update any application code that assumes INTEGER user_id
  3. Verify file_metadata.user_id matches users.user_id format
```

---

## 資料庫架構變更 (Schema Changes)

### Before Migration (舊架構)

```sql
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ❌ INTEGER (auto-increment)
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email TEXT UNIQUE,
    full_name TEXT,
    role TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**特性**:
- `user_id` 自動遞增（1, 2, 3, ...）
- 資料庫生成 ID
- 與 `file_metadata.user_id` 型別不匹配

### After Migration (新架構)

```sql
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,                   -- ✅ TEXT (UUID v4 format)
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email TEXT UNIQUE,
    full_name TEXT,
    role TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
```

**特性**:
- `user_id` 使用 UUID v4 格式（例：`550e8400-e29b-41d4-a716-446655440000`）
- 應用程式生成 ID（前端或後端）
- 與 `file_metadata.user_id` 型別匹配 ✅

---

## 一致性驗證 (Consistency Verification)

### 資料庫架構對比 (Schema Comparison)

#### users 表格
```sql
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,  -- ✅ TEXT
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email TEXT UNIQUE,
    full_name TEXT,
    role TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### file_metadata 表格
```sql
CREATE TABLE file_metadata (
    file_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER,
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT,              -- ✅ TEXT (matches users.user_id)
    chunk_count INTEGER,
    embedding_status TEXT,
    milvus_partition TEXT,
    metadata_json TEXT
);
```

### 型別一致性 (Type Consistency)

| 表格 | 欄位 | 型別 | 格式 | 狀態 |
|------|------|------|------|------|
| `users` | `user_id` | **TEXT** | UUID v4 | ✅ 匹配 |
| `file_metadata` | `user_id` | **TEXT** | UUID v4 | ✅ 匹配 |

**結論**: 兩個表格的 `user_id` 欄位現在完全一致 ✅

---

## 外鍵關係 (Foreign Key Relationship)

### 可選的外鍵約束 (Optional Foreign Key Constraint)

遷移完成後，可以選擇性地新增外鍵約束來確保資料完整性：

```sql
-- 未來可選：新增外鍵約束
-- 注意：SQLite 的外鍵約束需要在建表時定義，或需要重建表格

-- 選項 1: 在新的 file_metadata 表格建立時定義
CREATE TABLE file_metadata_with_fk (
    file_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER,
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT NOT NULL,
    chunk_count INTEGER,
    embedding_status TEXT,
    milvus_partition TEXT,
    metadata_json TEXT,

    FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

-- 選項 2: 使用觸發器模擬外鍵約束
CREATE TRIGGER fk_file_metadata_user_id_insert
BEFORE INSERT ON file_metadata
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Foreign key violation: user_id does not exist')
    WHERE NEW.user_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM users WHERE user_id = NEW.user_id);
END;
```

**建議**:
- 在原型階段可以不使用外鍵約束
- 在生產環境建議啟用以確保資料完整性

---

## 應用程式碼影響 (Application Code Impact)

### 前端 (Frontend)

**無需變更** ✅

前端程式碼已經在使用 UUID v4 格式：
- `static/js/docai-client.js:82` - `crypto.randomUUID()` 生成 UUID
- 透過 `X-User-ID` 標頭傳遞 UUID 字串

### 後端 (Backend)

**無需變更** ✅

後端程式碼已經在使用 TEXT 型別處理 `user_id`：
- `app/api/v1/endpoints/upload.py:217` - `user_id: str = Header(...)`
- `app/Providers/file_metadata_provider/client.py:163` - `_user_id = str(user_id)`

### 資料庫操作 (Database Operations)

**已完成** ✅

`file_metadata_provider` 的 `add_file()` 方法已經正確處理 TEXT 型別的 `user_id`：

```python
async def add_file(
    self,
    file_id: str,
    filename: str,
    file_type: str,
    file_size: int,
    user_id: int,  # 接受字串或整數
    # ...
):
    _user_id = str(user_id)  # 轉換為字串

    await conn.execute("""
        INSERT INTO file_metadata (
            file_id, filename, file_type, file_size,
            upload_time, user_id, chunk_count,
            embedding_status, milvus_partition, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        file_id, filename, file_type, file_size,
        datetime.now(timezone.utc).isoformat(),
        _user_id,  # TEXT 型別的 UUID
        chunk_count,
        'pending', milvus_partition, metadata_json
    ))
```

---

## 測試驗證 (Testing and Verification)

### 1. 驗證資料庫架構 (Verify Schema)

```bash
sqlite3 data/docai.db ".schema users"
```

**預期輸出**:
```sql
CREATE TABLE "users" (
    user_id TEXT PRIMARY KEY,  -- ✅ TEXT (not INTEGER)
    username TEXT NOT NULL UNIQUE,
    ...
);
```

### 2. 驗證資料型別一致性 (Verify Type Consistency)

```bash
sqlite3 data/docai.db "SELECT sql FROM sqlite_master WHERE type='table' AND name IN ('users', 'file_metadata')"
```

**確認**:
- `users.user_id`: TEXT ✅
- `file_metadata.user_id`: TEXT ✅

### 3. 測試用戶建立 (Test User Creation)

```bash
sqlite3 data/docai.db "INSERT INTO users (user_id, username, password_hash) VALUES ('550e8400-e29b-41d4-a716-446655440000', 'testuser', 'hash123')"
```

**確認**: 應該成功插入 UUID 格式的 `user_id`

### 4. 測試檔案上傳關聯 (Test File Upload Association)

```bash
# 上傳檔案並確認 user_id 正確儲存
curl -X POST "http://localhost:8000/api/v1/upload" \
  -H "X-User-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -F "file=@test.pdf"

# 查詢資料庫確認
sqlite3 data/docai.db "SELECT file_id, filename, user_id FROM file_metadata ORDER BY upload_time DESC LIMIT 1"
```

**預期**: `user_id` 欄位應該顯示完整的 UUID

### 5. 測試查詢功能 (Test Query Functionality)

```bash
# 查詢特定用戶的所有檔案
sqlite3 data/docai.db "SELECT * FROM file_metadata WHERE user_id = '550e8400-e29b-41d4-a716-446655440000'"

# 測試 JOIN 查詢（如果實作了用戶認證）
sqlite3 data/docai.db "
SELECT f.file_id, f.filename, u.username
FROM file_metadata f
JOIN users u ON f.user_id = u.user_id
WHERE f.user_id = '550e8400-e29b-41d4-a716-446655440000'
"
```

---

## 回滾計畫 (Rollback Plan)

### 如果遷移失敗 (If Migration Fails)

**備份檔案已自動建立**:
```
data/docai_backup_20251103_203324.db
```

### 回滾步驟 (Rollback Steps)

1. **停止應用程式** (Stop application)
   ```bash
   pkill -f "python main.py"
   ```

2. **還原資料庫** (Restore database)
   ```bash
   cp data/docai_backup_20251103_203324.db data/docai.db
   ```

3. **驗證還原** (Verify restoration)
   ```bash
   sqlite3 data/docai.db ".schema users"
   ```

4. **重新啟動應用程式** (Restart application)
   ```bash
   python main.py
   ```

---

## 未來改進建議 (Future Improvements)

### 1. 新增外鍵約束 (Add Foreign Key Constraints)

確保 `file_metadata.user_id` 必須存在於 `users.user_id` 中：

```sql
-- 需要重建 file_metadata 表格
ALTER TABLE file_metadata ADD CONSTRAINT fk_user_id
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    ON DELETE CASCADE
    ON UPDATE CASCADE;
```

### 2. 實作用戶認證系統 (Implement User Authentication)

目前的 UUID 系統只是識別，不是真正的認證。建議：
- 整合 JWT (JSON Web Tokens)
- 實作登入/登出功能
- 新增密碼驗證和加密
- 實作會話管理

### 3. 新增資料驗證 (Add Data Validation)

確保所有 `user_id` 都符合 UUID v4 格式：

```python
import re

UUID_V4_PATTERN = r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'

def validate_user_id(user_id: str) -> bool:
    return re.match(UUID_V4_PATTERN, user_id, re.IGNORECASE) is not None
```

### 4. 新增索引優化 (Add Index Optimization)

針對常見查詢模式新增複合索引：

```sql
-- 針對「用戶最近上傳的檔案」查詢優化
CREATE INDEX idx_file_user_upload_time
    ON file_metadata(user_id, upload_time DESC);
```

---

## 相關文件 (Related Documentation)

### 技術文件
- [claudedocs/USER_ID_GENERATION_FLOW.md](claudedocs/USER_ID_GENERATION_FLOW.md) - 完整的 user_id 生成與儲存流程
- [refData/todo/FIXED_upload_user_id_missing_20251031.md](refData/todo/FIXED_upload_user_id_missing_20251031.md) - 上傳錯誤修復（user_id 標頭缺失）
- [refData/todo/COMPLETE_multiuser_phase3_20251031.md](refData/todo/COMPLETE_multiuser_phase3_20251031.md) - 多用戶系統實作

### 遷移腳本
- [scripts/migrate_users_table_user_id_to_text.py](scripts/migrate_users_table_user_id_to_text.py) - 遷移腳本原始碼

### 資料庫架構
- `data/docai.db` - 主要資料庫（已遷移）
- `data/docai_backup_20251103_203324.db` - 遷移前備份

---

## 檢查清單 (Checklist)

### 遷移完成確認 (Migration Completion Checklist)

- [x] 資料庫備份已建立
- [x] users 表格 user_id 欄位已轉換為 TEXT
- [x] 索引已重建
- [x] 資料完整性已驗證
- [x] users.user_id 與 file_metadata.user_id 型別一致
- [x] 遷移文件已建立
- [ ] 用戶認證系統測試（待實作）
- [ ] 外鍵約束新增（可選）
- [ ] 生產環境部署測試（待執行）

---

## 結論 (Conclusion)

✅ **遷移成功完成**

**核心變更**:
- `users.user_id`: INTEGER → **TEXT** (UUID v4 format)
- 與 `file_metadata.user_id` 完全一致

**好處**:
1. ✅ 多用戶系統資料型別一致性
2. ✅ 支援前端生成的 UUID 識別符
3. ✅ 可建立外鍵關係確保資料完整性
4. ✅ 為未來的用戶認證系統奠定基礎

**無需額外動作**: 前端和後端程式碼已經正確處理 TEXT 型別的 `user_id`，無需修改應用程式邏輯。

**備份位置**: `data/docai_backup_20251103_203324.db`

---

*遷移執行時間: 2025-11-03 20:33:24*
*遷移腳本版本: 1.0*
*資料庫版本: SQLite*
