# User ID Generation and Storage Flow

## 概述 (Overview)

DocAI 使用 **UUID v4** 作為用戶識別符，實現多用戶檔案管理系統。`user_id` 在**前端生成**，通過 HTTP 標頭傳遞到後端，最終儲存在 `docai.db` 的 `file_metadata` 表格中。

## 完整工作流程 (Complete Workflow)

```
[Browser] → [Generate UUID] → [localStorage] → [HTTP Header] → [Backend API] → [SQLite Database]
```

### 時間線 (Timeline)

1. **T+0ms**: 用戶首次訪問頁面
2. **T+10ms**: 前端檢查 localStorage 中是否存在 `user_id`
3. **T+15ms**: 若不存在，生成新的 UUID v4 並儲存
4. **T+100ms**: 用戶選擇檔案並點擊上傳
5. **T+110ms**: 前端發送 POST 請求，包含 `X-User-ID` 標頭
6. **T+150ms**: 後端驗證 UUID 格式
7. **T+200ms**: 後端處理檔案並將 `user_id` 寫入資料庫
8. **T+250ms**: 上傳完成，`user_id` 永久儲存在 `docai.db`

---

## 階段 1: 前端生成 (Frontend Generation)

### 位置 (Location)
**檔案**: [static/js/docai-client.js:75-100](static/js/docai-client.js#L75-L100)

### 方法: `getUserId()`

#### 程式碼 (Code)
```javascript
getUserId() {
    // 檢查 localStorage 中是否已存在 UUID
    let userId = localStorage.getItem('docai_user_id');

    if (!userId) {
        // 使用 crypto.randomUUID() 生成 UUID v4 (現代瀏覽器)
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            userId = crypto.randomUUID();
        } else {
            // 舊版瀏覽器的備用方案：手動生成 UUID v4
            userId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                const r = Math.random() * 16 | 0;
                const v = c === 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        }

        // 儲存到 localStorage 實現持久化
        localStorage.setItem('docai_user_id', userId);
        console.log('[DocAI] Generated new user_id:', userId);
    } else {
        console.log('[DocAI] Using existing user_id:', userId);
    }

    return userId;
}
```

#### 生成邏輯 (Generation Logic)

1. **檢查現有 ID (Check Existing)**:
   - 從瀏覽器 `localStorage` 讀取 `docai_user_id`
   - 若存在，直接返回（持久化跨會話）

2. **生成新 UUID (Generate New UUID)**:
   - **優先方法**: 使用 `crypto.randomUUID()` (Web Crypto API)
     - 標準 UUID v4 格式
     - 加密安全的隨機數生成
     - 支援現代瀏覽器 (Chrome 92+, Firefox 95+, Safari 15.4+)

   - **備用方法**: 手動生成 UUID v4
     - 使用 `Math.random()` 生成偽隨機數
     - 符合 RFC 4122 規範
     - 確保版本位 (4) 和變體位 (8, 9, a, b) 正確

3. **持久化儲存 (Persistent Storage)**:
   - 儲存到 `localStorage.setItem('docai_user_id', userId)`
   - 跨瀏覽器標籤頁共享
   - 跨會話持久化（除非用戶清除瀏覽器資料）

#### UUID v4 格式 (Format)

```
xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
│      │ │  │ │  │ │  │ │          │
│      │ │  │ │  │ │  │ └─ 12 hex digits (random)
│      │ │  │ │  │ └──────  4 hex digits (random, 8/9/a/b prefix for variant)
│      │ │  │ └──────────── 3 hex digits (random)
│      │ │  └────────────── Version: 4 (UUID v4)
│      │ └───────────────── 4 hex digits (random)
└──────────────────────────  8 hex digits (random)
```

**範例 (Example)**:
```
550e8400-e29b-41d4-a716-446655440000
```

---

## 階段 2: HTTP 傳輸 (HTTP Transmission)

### 位置 (Location)
**檔案**: [static/js/docai-client.js:112-118](static/js/docai-client.js#L112-L118)

### 方法: `uploadFile()`

#### 程式碼 (Code)
```javascript
async uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/v1/upload', {
            method: 'POST',
            headers: {
                'X-User-ID': this.userId  // 多用戶支援：發送用戶 UUID
            },
            body: formData
        });
        // ... 處理回應
    }
}
```

#### 傳輸機制 (Transmission Mechanism)

1. **HTTP 標頭 (HTTP Header)**:
   - 標頭名稱：`X-User-ID`
   - 標頭值：UUID v4 字串（從 `this.userId` 取得）
   - 傳輸方式：HTTP POST 請求標頭

2. **為什麼使用標頭而非請求體？ (Why Header vs Body?)**
   - ✅ **與 multipart/form-data 相容**：檔案上傳使用 FormData
   - ✅ **清晰的關注點分離**：認證/識別 vs 業務資料
   - ✅ **FastAPI 依賴注入友善**：使用 `Header()` 依賴
   - ✅ **RESTful 最佳實踐**：元資訊屬於標頭

3. **請求範例 (Request Example)**:
   ```http
   POST /api/v1/upload HTTP/1.1
   Host: localhost:8000
   X-User-ID: 550e8400-e29b-41d4-a716-446655440000
   Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

   ------WebKitFormBoundary
   Content-Disposition: form-data; name="file"; filename="document.pdf"
   Content-Type: application/pdf

   [Binary PDF content]
   ------WebKitFormBoundary--
   ```

---

## 階段 3: 後端接收與驗證 (Backend Reception and Validation)

### 位置 (Location)
**檔案**: [app/api/v1/endpoints/upload.py:215-260](app/api/v1/endpoints/upload.py#L215-L260)

### 端點: `POST /api/v1/upload`

#### 程式碼 (Code)
```python
@router.post("")
async def upload_pdf(
    file: UploadFile = File(..., description="PDF file to upload"),
    user_id: str = Header(..., alias="X-User-ID", description="User UUID (required)"),
    # ... 其他依賴
):
    """
    上傳 PDF 檔案進行處理和索引（多用戶支援）

    Args:
        file: 上傳的 PDF 檔案
        user_id: 用戶識別符（UUID v4 格式，通過 X-User-ID 標頭必填）
    """

    # 驗證 user_id 格式（UUID v4）
    import re
    UUID_PATTERN = r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    if not re.match(UUID_PATTERN, user_id, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "ValidationError",
                "message": "Invalid user_id format. Must be UUID v4.",
                "details": {
                    "user_id": user_id,
                    "expected_format": "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
                }
            }
        )
```

#### 驗證步驟 (Validation Steps)

1. **FastAPI 依賴注入 (Dependency Injection)**:
   ```python
   user_id: str = Header(..., alias="X-User-ID", description="User UUID (required)")
   ```
   - `Header(...)`: 從 HTTP 標頭中提取
   - `alias="X-User-ID"`: 標頭名稱映射
   - Required (`...`): 必填，缺少會返回 422 錯誤

2. **UUID v4 格式驗證 (Format Validation)**:
   - 正則表達式：`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`
   - 檢查項目：
     - 8-4-4-4-12 分段結構
     - 版本位：第 3 段首位必須是 `4`
     - 變體位：第 4 段首位必須是 `8`, `9`, `a`, 或 `b`
   - 失敗時返回 HTTP 400 錯誤

3. **錯誤處理 (Error Handling)**:
   - **缺少標頭**: HTTP 422 (FastAPI 自動處理)
   - **格式錯誤**: HTTP 400 with 詳細錯誤訊息

---

## 階段 4: 資料處理與傳遞 (Data Processing and Propagation)

### 位置 (Location)
**檔案**: [app/api/v1/endpoints/upload.py:289-297](app/api/v1/endpoints/upload.py#L289-L297)

#### 程式碼 (Code)
```python
# 處理檔案並生成嵌入（附帶用戶所有權）
result = await process_and_embed_file(
    file_content=file_content,
    filename=file.filename,
    user_id=user_id,  # NEW: 傳遞 user_id 進行所有權追蹤
    input_service=input_service,
    retrieval_service=retrieval_service,
    file_metadata_provider=file_metadata_provider,
    embedding_provider=embedding_provider
)
```

### 位置 (Location)
**檔案**: [app/api/v1/endpoints/upload.py:129-141](app/api/v1/endpoints/upload.py#L129-L141)

#### 程式碼 (Code)
```python
async def process_and_embed_file(..., user_id: str, ...):
    # ... 檔案處理邏輯 ...

    # Step 2: 儲存檔案元數據到 SQLite（附帶用戶所有權）
    await file_metadata_provider.add_file(
        file_id=file_id,
        filename=filename,
        file_type="pdf",
        file_size=process_result["file_size"],
        user_id=user_id,  # NEW: 將檔案與用戶關聯
        chunk_count=chunk_count,
        milvus_partition=f"file_{file_id}",
        metadata={...}
    )
```

#### 資料流 (Data Flow)

```
HTTP Request
    ↓ [FastAPI Header extraction]
user_id (str)
    ↓ [Validation]
user_id (validated UUID v4)
    ↓ [Pass to process_and_embed_file()]
user_id (parameter)
    ↓ [Pass to add_file()]
user_id (parameter)
    ↓ [Insert into database]
user_id (stored in docai.db)
```

---

## 階段 5: 資料庫儲存 (Database Storage)

### 位置 (Location)
**檔案**: [app/Providers/file_metadata_provider/client.py:127-175](app/Providers/file_metadata_provider/client.py#L127-L175)

### 方法: `add_file()`

#### 程式碼 (Code)
```python
async def add_file(
    self,
    file_id: str,
    filename: str,
    file_type: str,
    file_size: int,
    user_id: int,  # 用戶識別符（UUID 字串）
    chunk_count: Optional[int] = None,
    milvus_partition: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    新增檔案元資料記錄

    Args:
        user_id: 選用的用戶識別符（UUID 格式）
    """
    conn = await self._get_connection()
    try:
        metadata_json = json.dumps(metadata) if metadata else None
        _user_id = str(user_id)  # 確保為字串型別

        await conn.execute("""
            INSERT INTO file_metadata (
                file_id, filename, file_type, file_size,
                upload_time, user_id, chunk_count,
                embedding_status, milvus_partition, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id, filename, file_type, file_size,
            datetime.now(timezone.utc).isoformat(),
            _user_id,  # UUID 字串儲存在此
            chunk_count,
            'pending', milvus_partition, metadata_json
        ))

        await conn.commit()
        logger.info(f"Added file metadata: {file_id}")
    except Exception as e:
        logger.error(f"Failed to add file metadata: {str(e)}")
        raise
```

### 資料庫架構 (Database Schema)

**表格**: `file_metadata` (SQLite)

```sql
CREATE TABLE file_metadata (
    file_id TEXT PRIMARY KEY,              -- 檔案唯一識別符
    filename TEXT NOT NULL,                -- 原始檔案名稱
    file_type TEXT NOT NULL,               -- 檔案類型（pdf, docx, txt）
    file_size INTEGER,                     -- 檔案大小（位元組）
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 上傳時間戳
    user_id TEXT,                          -- 用戶 UUID（多用戶支援）
    chunk_count INTEGER,                   -- 分塊數量
    embedding_status TEXT,                 -- 嵌入狀態（pending, completed, failed）
    milvus_partition TEXT,                 -- Milvus 分區名稱
    metadata_json TEXT                     -- 額外元資料（JSON 格式）
);

-- 索引：依用戶 ID 快速查詢
CREATE INDEX idx_file_user ON file_metadata(user_id);

-- 索引：依上傳時間排序
CREATE INDEX idx_file_upload_time ON file_metadata(upload_time);
```

### 儲存範例 (Storage Example)

**插入的記錄**:
```
file_id: "file_20251103_abc123"
filename: "document.pdf"
file_type: "pdf"
file_size: 1024000
upload_time: "2025-11-03T20:30:45.123456+00:00"
user_id: "550e8400-e29b-41d4-a716-446655440000"  ← 從前端生成的 UUID
chunk_count: 150
embedding_status: "completed"
milvus_partition: "file_file_20251103_abc123"
metadata_json: '{"chunking_strategy": "hierarchical", "chunk_sizes": [2000, 1000, 500]}'
```

### 查詢範例 (Query Examples)

**列出特定用戶的所有檔案**:
```sql
SELECT * FROM file_metadata
WHERE user_id = '550e8400-e29b-41d4-a716-446655440000'
ORDER BY upload_time DESC;
```

**檢查檔案所有權**:
```sql
SELECT user_id FROM file_metadata
WHERE file_id = 'file_20251103_abc123';
```

---

## 安全性考量 (Security Considerations)

### ✅ 優點 (Strengths)

1. **UUID v4 隨機性 (Randomness)**:
   - 128 位元隨機數（約 3.4 × 10³⁸ 種可能）
   - 實際上不可能碰撞或猜測
   - 加密安全（使用 `crypto.randomUUID()`）

2. **無個人資訊 (No PII)**:
   - UUID 不包含個人可識別資訊
   - 不洩露 IP、時間戳或裝置資訊
   - 符合隱私保護要求

3. **客戶端生成 (Client-Side Generation)**:
   - 減少伺服器負擔
   - 離線時也可生成
   - 跨裝置一致性（通過 localStorage）

4. **格式驗證 (Format Validation)**:
   - 後端嚴格驗證 UUID v4 格式
   - 防止注入攻擊和格式錯誤

### ⚠️ 限制與考量 (Limitations and Considerations)

1. **無真實認證 (No Real Authentication)**:
   - ❌ 任何人都可以生成有效的 UUID
   - ❌ 無密碼或身份驗證機制
   - ❌ 用戶可以假裝成其他用戶（如果知道其 UUID）
   - **適用場景**: 原型、內部工具、非敏感數據

2. **瀏覽器依賴 (Browser Dependency)**:
   - UUID 儲存在 localStorage
   - 清除瀏覽器資料會遺失身份
   - 跨裝置不同步
   - 無跨瀏覽器識別

3. **無會話管理 (No Session Management)**:
   - 無 JWT、OAuth 或 session token
   - 無過期機制
   - 無撤銷或登出功能

### 🔐 生產環境建議 (Production Recommendations)

**若要部署到生產環境，應升級為真實的認證系統**:

1. **整合認證提供者 (Authentication Provider)**:
   - Auth0, Firebase Auth, Supabase Auth
   - OAuth 2.0 (Google, GitHub, Microsoft)
   - SAML 2.0 (企業 SSO)

2. **實施 JWT (JSON Web Tokens)**:
   ```python
   from fastapi.security import HTTPBearer

   security = HTTPBearer()

   async def get_current_user(token: str = Depends(security)):
       payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
       user_id = payload.get("sub")
       return user_id
   ```

3. **新增用戶資料表 (User Table)**:
   ```sql
   CREATE TABLE users (
       user_id TEXT PRIMARY KEY,
       email TEXT UNIQUE NOT NULL,
       password_hash TEXT NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

4. **實施授權檢查 (Authorization Checks)**:
   ```python
   async def verify_file_ownership(file_id: str, user_id: str):
       file = await file_metadata_provider.get_file(file_id)
       if file['user_id'] != user_id:
           raise HTTPException(status_code=403, detail="Forbidden")
   ```

---

## 多用戶功能使用方式 (Multi-User Functionality Usage)

### API 呼叫範例 (API Call Examples)

#### 上傳檔案 (Upload File)
```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
  -H "X-User-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -F "file=@document.pdf"
```

#### 列出用戶檔案 (List User Files)
```bash
curl -X GET "http://localhost:8000/api/v1/files" \
  -H "X-User-ID: 550e8400-e29b-41d4-a716-446655440000"
```

#### 刪除檔案 (Delete File)
```bash
curl -X DELETE "http://localhost:8000/api/v1/files/file_20251103_abc123" \
  -H "X-User-ID: 550e8400-e29b-41d4-a716-446655440000"
```

### JavaScript 整合範例 (JavaScript Integration Example)

```javascript
// 初始化 DocAI 客戶端（自動生成或取得 user_id）
const client = new DocAIClient('http://localhost:8000');

// 上傳檔案（自動附帶 X-User-ID 標頭）
const file = document.getElementById('fileInput').files[0];
const result = await client.uploadFile(file);
console.log('Uploaded file_id:', result.file_id);

// 列出當前用戶的檔案
const files = await client.listFiles();
console.log('User files:', files);

// 刪除檔案
await client.deleteFile('file_20251103_abc123');
```

---

## 相關檔案 (Related Files)

### 前端 (Frontend)
- [static/js/docai-client.js](static/js/docai-client.js) - 完整的 DocAI 客戶端類別
  - `getUserId()`: UUID 生成邏輯
  - `uploadFile()`: 上傳檔案（含 X-User-ID 標頭）
  - `listFiles()`: 列出用戶檔案
  - `deleteFile()`: 刪除用戶檔案

### 後端 API (Backend API)
- [app/api/v1/endpoints/upload.py](app/api/v1/endpoints/upload.py) - 上傳端點
  - `upload_pdf()`: 接收並驗證 user_id
  - `process_and_embed_file()`: 處理檔案並儲存 user_id
- [app/api/v1/endpoints/files.py](app/api/v1/endpoints/files.py) - 檔案管理端點
  - `list_user_files()`: 列出特定用戶的檔案
  - `delete_user_file()`: 刪除用戶檔案（附帶所有權驗證）

### 資料層 (Data Layer)
- [app/Providers/file_metadata_provider/client.py](app/Providers/file_metadata_provider/client.py) - 檔案元資料提供者
  - `add_file()`: 儲存檔案元資料（含 user_id）
  - `list_files_by_user()`: 依用戶 ID 查詢檔案
  - `delete_file()`: 刪除檔案元資料

### 文件 (Documentation)
- [refData/todo/FIXED_upload_user_id_missing_20251031.md](refData/todo/FIXED_upload_user_id_missing_20251031.md) - 上傳錯誤修復（user_id 標頭缺失）
- [refData/todo/COMPLETE_multiuser_phase3_20251031.md](refData/todo/COMPLETE_multiuser_phase3_20251031.md) - 多用戶系統實作（第 3 階段）

---

## 總結 (Summary)

### 核心機制 (Core Mechanism)

**user_id** 是一個 **UUID v4** 字串：
1. **生成位置**: 前端（瀏覽器）
2. **生成方法**: `crypto.randomUUID()` 或手動生成
3. **儲存方式**: `localStorage.setItem('docai_user_id', uuid)`
4. **傳輸方式**: HTTP 標頭 `X-User-ID`
5. **驗證方式**: 後端正則表達式檢查 UUID v4 格式
6. **儲存位置**: `data/docai.db` → `file_metadata.user_id` 欄位

### 資料流簡圖 (Data Flow Diagram)

```
┌─────────────┐
│   Browser   │
│             │
│ [Generate]  │ ──► crypto.randomUUID()
│     ↓       │     → "550e8400-e29b-41d4-..."
│ localStorage│
└──────┬──────┘
       │
       │ X-User-ID: 550e8400-...
       ↓
┌─────────────┐
│  FastAPI    │
│   Upload    │ ──► Validate UUID v4 format
│   Endpoint  │     ✓ Regex match
└──────┬──────┘
       │
       │ user_id parameter
       ↓
┌─────────────┐
│   SQLite    │
│   INSERT    │ ──► file_metadata.user_id
│  docai.db   │     = "550e8400-e29b-..."
└─────────────┘
```

### 關鍵檔案位置摘要 (Key File Locations Summary)

| 階段 | 檔案 | 行號 | 功能 |
|------|------|------|------|
| 生成 | `static/js/docai-client.js` | 75-100 | `getUserId()` - UUID 生成與持久化 |
| 傳輸 | `static/js/docai-client.js` | 115 | `X-User-ID` 標頭設定 |
| 接收 | `app/api/v1/endpoints/upload.py` | 217 | `Header(..., alias="X-User-ID")` 依賴注入 |
| 驗證 | `app/api/v1/endpoints/upload.py` | 249-260 | UUID v4 格式正則驗證 |
| 傳遞 | `app/api/v1/endpoints/upload.py` | 292 | `user_id` 參數傳遞 |
| 儲存 | `app/Providers/file_metadata_provider/client.py` | 164-175 | SQL INSERT 語句 |

---

**完整的 user_id 生成與儲存流程已記錄完畢！** 📝
