# FIXED: Upload Error - Column Count Mismatch in Database Insert

## 問題描述 (Problem Description)

**症狀 (Symptom)**:
- 文件上傳失敗，返回 HTTP 500 錯誤 (File upload fails with HTTP 500 error)
- 前端顯示錯誤：「Failed to process file: 11 values for 10 columns」

**錯誤訊息 (Error Messages)**:

**前端 (Frontend)**:
```
POST http://localhost:8000/api/v1/upload 500 (Internal Server Error)
Upload error: Error: Failed to process file: 11 values for 10 columns
```

**後端日誌 (Backend Logs)**:
```
Failed to add file metadata: 11 values for 10 columns
File processing failed: 11 values for 10 columns
Upload endpoint error: 11 values for 10 columns
INFO:     127.0.0.1:57123 - "POST /api/v1/upload HTTP/1.1" 500 Internal Server Error
```

**截圖 (Screenshot)**: [refData/errors/images/upload_error_7.png](refData/errors/images/upload_error_7.png)

## 根本原因 (Root Cause)

### 問題分析 (Problem Analysis)

**位置**: [app/Providers/file_metadata_provider/client.py:164-175](app/Providers/file_metadata_provider/client.py#L164-L175)

**SQL 語句錯誤 (SQL Statement Error)**:
- INSERT 語句指定了 **10 個欄位名稱** (10 column names)
- VALUES 子句卻有 **11 個佔位符** (11 placeholders: `?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?`)
- 提供的值只有 **10 個** (10 values)

### 資料庫架構 (Database Schema)

**file_metadata 表格** (10 個欄位):
```sql
CREATE TABLE file_metadata (
    file_id TEXT PRIMARY KEY,          -- 1
    filename TEXT NOT NULL,            -- 2
    file_type TEXT NOT NULL,           -- 3
    file_size INTEGER,                 -- 4
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 5
    user_id TEXT,                      -- 6
    chunk_count INTEGER,               -- 7
    embedding_status TEXT,             -- 8
    milvus_partition TEXT,             -- 9
    metadata_json TEXT                 -- 10
);
```

### 錯誤程式碼 (Problematic Code)

**修改前 (Before)**:
```python
await conn.execute("""
    INSERT INTO file_metadata (
        file_id, filename, file_type, file_size,          # 4 columns
        upload_time, user_id, chunk_count,                # 3 columns
        embedding_status, milvus_partition, metadata_json # 3 columns
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)  # ❌ 11 placeholders (1 extra!)
""", (
    file_id, filename, file_type, file_size,              # 4 values
    datetime.now(timezone.utc).isoformat(),               # 1 value
    _user_id, chunk_count,                                # 2 values
    'pending', milvus_partition, metadata_json            # 3 values
))                                                        # ✅ 10 values total
```

**問題**:
- 欄位數：10 個
- 佔位符：11 個 ❌
- 實際值：10 個 ✅
- **佔位符數量與欄位/值數量不符**

## 解決方案 (Solution)

### 修復內容 (Fix Applied)

**檔案**: [app/Providers/file_metadata_provider/client.py:169](app/Providers/file_metadata_provider/client.py#L169)

**修改**: 移除多餘的佔位符 (Remove extra placeholder)

**修改後 (After)**:
```python
await conn.execute("""
    INSERT INTO file_metadata (
        file_id, filename, file_type, file_size,
        upload_time, user_id, chunk_count,
        embedding_status, milvus_partition, metadata_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)  # ✅ 10 placeholders (matching!)
""", (
    file_id, filename, file_type, file_size,
    datetime.now(timezone.utc).isoformat(),
    _user_id, chunk_count,
    'pending', milvus_partition, metadata_json
))
```

**變更**:
- 從 11 個佔位符減少到 10 個佔位符
- 現在佔位符數量與欄位數量及值數量完全匹配

### 驗證 (Validation)

**語法檢查 (Syntax Check)**:
```bash
✅ Syntax validation passed
```

**伺服器啟動 (Server Startup)**:
```
INFO:     Started server process [26471]
INFO:     Waiting for application startup.
INFO:     Application startup complete.  # ✅ 成功啟動
```

**預期結果 (Expected Outcome)**:
- ✅ 文件上傳應該成功
- ✅ 檔案元數據正確寫入 `docai.db`
- ✅ 前端顯示上傳成功訊息

## 測試建議 (Testing Recommendations)

### 手動測試 (Manual Testing)

1. **上傳測試文件**:
   - 訪問 http://localhost:8000
   - 選擇一個 PDF 文件
   - 點擊「上傳」按鈕
   - 確認上傳成功且無錯誤訊息

2. **驗證資料庫記錄**:
   ```bash
   sqlite3 data/docai.db "SELECT * FROM file_metadata ORDER BY upload_time DESC LIMIT 1;"
   ```
   應該看到新插入的記錄，包含所有 10 個欄位的值

3. **檢查日誌**:
   ```bash
   tail -f logs/server.log
   ```
   應該看到「Added file metadata: [file_id]」而非錯誤訊息

### 自動化測試建議 (Automated Testing Suggestions)

建議在 `tests/` 目錄新增單元測試：

```python
async def test_add_file_metadata():
    """Test file metadata insertion with correct column count"""
    provider = FileMetadataProvider()
    await provider.initialize_database()

    await provider.add_file(
        file_id="test_file_123",
        filename="test.pdf",
        file_type="pdf",
        file_size=1024,
        user_id="user_abc",
        chunk_count=5
    )

    # Verify insertion
    file = await provider.get_file("test_file_123")
    assert file is not None
    assert file['filename'] == "test.pdf"
    assert file['chunk_count'] == 5
```

## 預防策略 (Prevention Strategy)

### 最佳實踐 (Best Practices)

1. **使用命名參數 (Use Named Parameters)**:
   ```python
   # ✅ BETTER: Named parameters prevent count mismatches
   await conn.execute("""
       INSERT INTO file_metadata (
           file_id, filename, file_type, file_size,
           upload_time, user_id, chunk_count,
           embedding_status, milvus_partition, metadata_json
       ) VALUES (
           :file_id, :filename, :file_type, :file_size,
           :upload_time, :user_id, :chunk_count,
           :embedding_status, :milvus_partition, :metadata_json
       )
   """, {
       "file_id": file_id,
       "filename": filename,
       "file_type": file_type,
       "file_size": file_size,
       "upload_time": datetime.now(timezone.utc).isoformat(),
       "user_id": _user_id,
       "chunk_count": chunk_count,
       "embedding_status": 'pending',
       "milvus_partition": milvus_partition,
       "metadata_json": metadata_json
   })
   ```

2. **單元測試覆蓋 (Unit Test Coverage)**:
   - 為所有資料庫操作編寫單元測試
   - 測試應驗證插入、更新、刪除操作的正確性
   - 包含邊界條件測試（NULL 值、空字串等）

3. **程式碼審查檢查清單 (Code Review Checklist)**:
   - [ ] 佔位符數量是否與欄位數量匹配？
   - [ ] VALUES 提供的值數量是否與佔位符數量匹配？
   - [ ] 欄位順序是否與值的順序對應？
   - [ ] 是否有單元測試覆蓋此操作？

4. **使用 ORM 框架 (Consider ORM)**:
   ```python
   # 使用 SQLAlchemy 或 tortoise-orm 等 ORM 框架
   # 可以避免手動編寫 SQL 語句的錯誤
   from sqlalchemy import Column, String, Integer, Text
   from sqlalchemy.ext.asyncio import AsyncSession

   class FileMetadata(Base):
       __tablename__ = "file_metadata"
       file_id = Column(String, primary_key=True)
       filename = Column(String, nullable=False)
       # ... 其他欄位
   ```

## 影響範圍 (Impact Scope)

**修改檔案 (Files Modified)**:
- `app/Providers/file_metadata_provider/client.py` (1 line changed)

**影響功能 (Affected Functionality)**:
- ✅ 文件上傳功能 (File upload functionality)
- ✅ 檔案元數據儲存 (File metadata storage)
- ✅ 多用戶文件管理 (Multi-user file management)

**向後相容性 (Backward Compatibility)**:
- ✅ 完全相容 (Fully compatible)
- ✅ 無 API 變更 (No API changes)
- ✅ 無資料庫架構變更 (No schema changes)
- ✅ 現有資料不受影響 (Existing data unaffected)

## 相關問題 (Related Issues)

此問題可能在以下情況下被引入：
1. 在資料庫架構中新增欄位時，未同步更新 INSERT 語句
2. 複製貼上程式碼時不小心多加了一個佔位符
3. 缺少單元測試來捕捉此類錯誤

**建議**: 實施自動化測試和使用 ORM 框架可以有效預防此類錯誤。

## 結論 (Conclusion)

這是一個典型的 SQL 語句錯誤，由於佔位符數量與欄位/值數量不匹配導致。修復方法很簡單：移除多餘的佔位符。但這提醒我們：

1. **手動編寫 SQL 容易出錯** - 考慮使用 ORM 或命名參數
2. **單元測試至關重要** - 應該有測試覆蓋所有資料庫操作
3. **程式碼審查很重要** - 此類錯誤在審查時很容易發現

**重要提醒**: 建議盡快為 `FileMetadataProvider` 編寫完整的單元測試套件，以預防類似問題。
