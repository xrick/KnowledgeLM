<!-- claudedocs/skill_export_import_implementation_plan.md -->
# Skill Export/Import 功能實施計畫

**建立日期**: 2025-12-25
**狀態**: 📋 Planning Phase
**優先級**: High

---

## 📋 執行摘要

本文檔詳細規劃 DocAI 系統的 Skill Export 和 Import 功能，允許用戶匯出完整的 Skill 資料（包含資料庫記錄和 FAISS 向量索引），並在其他環境或同一系統中重新匯入。

**核心目標**：
- ✅ 完整的資料可攜性（Database + FAISS）
- ✅ ID 衝突自動處理
- ✅ 資料完整性保證（交易式操作）
- ✅ 使用者友善的 UI

---

## 🏗️ 系統架構分析

### 當前架構

| 元件 | 技術 | 路徑/位置 |
|------|------|----------|
| **Backend** | FastAPI | `app/api/v1/endpoints/skills.py` |
| **Database** | SQLite | `data/skill_metadata.db` |
| **Vector Store** | FAISS | `data/faiss_indices/skills/{skill_id}/` |
| **Frontend** | Vanilla JS/HTML/CSS | `template/skill_config.html` |
| **Metadata Provider** | Python Class | `app/Providers/skill_metadata_provider/client.py` |

### 資料庫結構 (5 Tables)

```sql
-- 1. skill_heads: Skill 群組層
CREATE TABLE skill_heads (
    head_id TEXT PRIMARY KEY,              -- head_yyyymmdd_hhmmss_xxxxxxxx
    skill_name TEXT NOT NULL UNIQUE,       -- 唯一名稱
    description TEXT,
    category TEXT DEFAULT 'General',
    display_order INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. skill_metadata: Skill 詳細資訊
CREATE TABLE skill_metadata (
    skill_id TEXT PRIMARY KEY,             -- skill_yyyymmdd_hhmmss_xxxxxxxx
    skill_name TEXT NOT NULL,
    skill_description TEXT,
    total_chunks INTEGER DEFAULT 0,
    head_id TEXT REFERENCES skill_heads(head_id),
    parent_skill_id TEXT DEFAULT 'root',
    source_name TEXT,
    metadata TEXT,                         -- JSON
    -- ... 其他欄位
);

-- 3. skill_chunk_metadata: 文本分塊資訊
CREATE TABLE skill_chunk_metadata (
    chunk_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    chunk_text TEXT,
    chunk_index INTEGER,
    metadata TEXT,                         -- JSON
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id)
);

-- 4. skill_document_mapping: 文檔映射
CREATE TABLE skill_document_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    document_name TEXT,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- 5. skill_overviews: Skill 概覽
CREATE TABLE skill_overviews (
    overview_id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    overview_text TEXT,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id)
);
```

### FAISS 儲存結構

```
data/faiss_indices/skills/
└── {skill_id}/
    ├── index.faiss    # 向量索引 (binary, ~800KB)
    └── index.pkl      # Metadata pickle (~40KB)
```

---

## 📦 Export Skill 功能設計

### API Endpoint

```python
@router.get("/config/skills/export/{skill_id}")
async def export_skill(skill_id: str)
```

**URL 設計考量**：
- ✅ 使用 `/config/skills/export/{skill_id}` 符合現有 API 慣例
- ✅ GET 方法適合檔案下載操作
- ✅ Path parameter 清楚標識要匯出的 skill

### 實施流程

#### Phase 1: 資料收集 (Data Collection)

```python
async def export_skill(skill_id: str):
    logger.info(f"[Export] Starting export for skill_id: {skill_id}")

    # 1. 驗證 skill 存在
    skill = await metadata_provider.get_skill_by_id(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    # 2. 查詢 head_id
    head_id = skill.get('head_id')
    if not head_id:
        logger.warning(f"[Export] Skill {skill_id} has no head_id, might be orphaned")

    # 3. 驗證 FAISS 索引存在
    faiss_dir = Path(f"data/faiss_indices/skills/{skill_id}")
    if not faiss_dir.exists():
        raise HTTPException(
            status_code=500,
            detail=f"FAISS index missing for skill: {skill_id}"
        )

    index_faiss = faiss_dir / "index.faiss"
    index_pkl = faiss_dir / "index.pkl"

    if not index_faiss.exists() or not index_pkl.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Incomplete FAISS index (missing files)"
        )
```

#### Phase 2: 資料庫匯出 (Database Export)

```python
# 4. 匯出 5 個資料表到 CSV
conn = sqlite3.connect("data/skill_metadata.db")
cursor = conn.cursor()

export_tables = {
    'skill_heads': f"SELECT * FROM skill_heads WHERE head_id = '{head_id}'",
    'skill_metadata': f"SELECT * FROM skill_metadata WHERE skill_id = '{skill_id}'",
    'skill_chunk_metadata': f"SELECT * FROM skill_chunk_metadata WHERE skill_id = '{skill_id}'",
    'skill_document_mapping': f"SELECT * FROM skill_document_mapping WHERE skill_id = '{skill_id}'",
    'skill_overviews': f"SELECT * FROM skill_overviews WHERE skill_id = '{skill_id}'"
}

csv_files = {}
for table_name, query in export_tables.items():
    # 執行查詢
    cursor.execute(query)
    rows = cursor.fetchall()

    if not rows:
        logger.warning(f"[Export] No data found in {table_name} for skill_id: {skill_id}")
        continue

    # 取得欄位名稱
    columns = [description[0] for description in cursor.description]

    # 寫入 CSV
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(columns)  # Header
    writer.writerows(rows)

    csv_files[f"{table_name}.csv"] = csv_buffer.getvalue()
    logger.info(f"[Export] Exported {len(rows)} rows from {table_name}")

conn.close()
```

#### Phase 3: Manifest 生成 (Manifest Generation)

```python
# 5. 建立 manifest.json
manifest = {
    "export_version": "1.0",
    "export_date": datetime.now(timezone.utc).isoformat(),
    "source_skill_id": skill_id,
    "skill_name": skill.get('skill_name'),
    "skill_description": skill.get('skill_description'),
    "head_id": head_id,
    "total_chunks": skill.get('total_chunks', 0),
    "embedding_model": skill.get('embedding_model', 'BAAI/bge-m3'),
    "embedding_dimension": skill.get('embedding_dimension', 1024),
    "database_tables": list(csv_files.keys()),
    "faiss_files": ["index.faiss", "index.pkl"],
    "export_metadata": {
        "system_version": "DocAI v1.0",
        "export_tool": "skill_export_api"
    }
}

manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
```

#### Phase 4: ZIP 壓縮 (Compression)

```python
# 6. 建立臨時目錄
import tempfile
import zipfile

temp_dir = tempfile.mkdtemp(prefix=f"skill_export_{skill_id}_")
skill_folder = Path(temp_dir) / sanitize_filename(skill.get('skill_name'))
skill_folder.mkdir(parents=True, exist_ok=True)

try:
    # 7. 寫入 manifest.json
    (skill_folder / "manifest.json").write_text(manifest_json, encoding='utf-8')

    # 8. 寫入 CSV 檔案
    for csv_name, csv_content in csv_files.items():
        (skill_folder / csv_name).write_text(csv_content, encoding='utf-8')

    # 9. 複製 FAISS 檔案
    shutil.copy2(index_faiss, skill_folder / "index.faiss")
    shutil.copy2(index_pkl, skill_folder / "index.pkl")

    # 10. 壓縮成 ZIP
    zip_path = Path(temp_dir) / f"{sanitize_filename(skill.get('skill_name'))}.zip"

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in skill_folder.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(skill_folder.parent)
                zipf.write(file_path, arcname)

    logger.info(f"[Export] Created ZIP: {zip_path} ({zip_path.stat().st_size} bytes)")

    # 11. 回傳檔案
    def iterfile():
        with open(zip_path, mode="rb") as file_like:
            yield from file_like

    headers = {
        'Content-Disposition': f'attachment; filename="{sanitize_filename(skill.get("skill_name"))}.zip"'
    }

    return StreamingResponse(
        iterfile(),
        media_type="application/zip",
        headers=headers
    )

finally:
    # 12. 清理臨時檔案
    shutil.rmtree(temp_dir, ignore_errors=True)
```

### Export ZIP 結構

```
大語言模型大全.zip
└── 大語言模型大全/
    ├── manifest.json                  # 元資料清單
    ├── skill_heads.csv                # Head 資料
    ├── skill_metadata.csv             # Skill 主資料
    ├── skill_chunk_metadata.csv       # 分塊資料
    ├── skill_document_mapping.csv     # 文檔映射
    ├── skill_overviews.csv            # 概覽資料
    ├── index.faiss                    # FAISS 向量索引
    └── index.pkl                      # FAISS metadata
```

### Manifest.json 範例

```json
{
  "export_version": "1.0",
  "export_date": "2025-12-25T10:30:00Z",
  "source_skill_id": "skill_20251216_124010_b45c5a1f_d81758",
  "skill_name": "大語言模型大全",
  "skill_description": "LLM 相關文檔集合",
  "head_id": "head_20251126_xxx",
  "total_chunks": 462,
  "embedding_model": "BAAI/bge-m3",
  "embedding_dimension": 1024,
  "database_tables": [
    "skill_heads.csv",
    "skill_metadata.csv",
    "skill_chunk_metadata.csv",
    "skill_document_mapping.csv",
    "skill_overviews.csv"
  ],
  "faiss_files": [
    "index.faiss",
    "index.pkl"
  ],
  "export_metadata": {
    "system_version": "DocAI v1.0",
    "export_tool": "skill_export_api"
  }
}
```

### Export 錯誤處理

| 錯誤情境 | HTTP Status | 處理策略 |
|---------|-------------|---------|
| **Skill 不存在** | 404 | 驗證 skill_id 有效性 |
| **FAISS 檔案遺失** | 500 | 檢查 index.faiss 和 index.pkl 存在 |
| **資料庫查詢失敗** | 500 | Try-catch with rollback |
| **ZIP 壓縮失敗** | 500 | 清理臨時檔案，回報錯誤 |
| **檔案名稱非法字元** | 400 | Sanitize filename (移除特殊字元) |

---

## 📥 Import Skill 功能設計

### API Endpoint

```python
@router.post("/config/skills/import")
async def import_skill(file: UploadFile = File(...))
```

**設計考量**：
- ✅ POST 方法適合檔案上傳
- ✅ 使用 `UploadFile` 支援大檔案串流上傳
- ✅ 路徑符合 `/config/skills` 慣例

### 實施流程

#### Phase 1: 檔案上傳與驗證 (Upload & Validation)

```python
async def import_skill(file: UploadFile = File(...)):
    logger.info(f"[Import] Receiving file: {file.filename}")

    # 1. 驗證檔案類型
    if not file.filename.endswith('.zip'):
        raise HTTPException(
            status_code=400,
            detail="Only ZIP files are accepted for skill import"
        )

    # 2. 建立臨時目錄
    import_temp_dir = tempfile.mkdtemp(prefix="skill_import_")
    zip_path = Path(import_temp_dir) / "uploaded.zip"

    try:
        # 3. 儲存上傳的 ZIP
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"[Import] Saved ZIP: {zip_path} ({zip_path.stat().st_size} bytes)")

        # 4. 解壓縮 ZIP
        extract_dir = Path(import_temp_dir) / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(extract_dir)

        # 5. 找到 skill 資料夾（ZIP 內第一層）
        skill_folders = [d for d in extract_dir.iterdir() if d.is_dir()]

        if not skill_folders:
            raise HTTPException(
                status_code=400,
                detail="Invalid ZIP structure: no skill folder found"
            )

        skill_folder = skill_folders[0]
        logger.info(f"[Import] Found skill folder: {skill_folder.name}")

    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail="Corrupted ZIP file"
        )
```

#### Phase 2: Manifest 讀取與驗證 (Manifest Validation)

```python
# 6. 讀取 manifest.json
manifest_path = skill_folder / "manifest.json"

if not manifest_path.exists():
    raise HTTPException(
        status_code=400,
        detail="Invalid skill export: manifest.json not found"
    )

with open(manifest_path, 'r', encoding='utf-8') as f:
    manifest = json.load(f)

# 7. 驗證必要欄位
required_fields = ['source_skill_id', 'skill_name', 'database_tables', 'faiss_files']
missing_fields = [field for field in required_fields if field not in manifest]

if missing_fields:
    raise HTTPException(
        status_code=400,
        detail=f"Invalid manifest: missing fields {missing_fields}"
    )

# 8. 驗證檔案存在
for table_csv in manifest['database_tables']:
    csv_path = skill_folder / table_csv
    if not csv_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Missing CSV file: {table_csv}"
        )

for faiss_file in manifest['faiss_files']:
    faiss_path = skill_folder / faiss_file
    if not faiss_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Missing FAISS file: {faiss_file}"
        )

logger.info(f"[Import] Manifest validated: {manifest['skill_name']}")
```

#### Phase 3: ID 重新生成 (ID Regeneration)

```python
# 9. 生成新的 ID（避免衝突）
import hashlib

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
skill_name = manifest['skill_name']
name_hash = hashlib.md5(skill_name.encode('utf-8')).hexdigest()[:8]
random_hash = hashlib.md5(str(time.time()).encode()).hexdigest()[:6]

new_skill_id = f"skill_{timestamp}_{name_hash}_{random_hash}"
new_head_id = f"head_{timestamp}_{name_hash[:8]}"

logger.info(f"[Import] Generated new IDs:")
logger.info(f"  - skill_id: {new_skill_id}")
logger.info(f"  - head_id: {new_head_id}")

# 10. 處理 skill_name 衝突
conn = sqlite3.connect("data/skill_metadata.db")
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM skill_heads WHERE skill_name = ?", (skill_name,))
existing_count = cursor.fetchone()[0]

if existing_count > 0:
    # 自動重命名：加上時間戳
    new_skill_name = f"{skill_name}_{timestamp}"
    logger.warning(f"[Import] Skill name conflict, renamed to: {new_skill_name}")
else:
    new_skill_name = skill_name

conn.close()
```

#### Phase 4: CSV ID 更新 (CSV ID Update)

```python
# 11. 更新 CSV 中的 ID（關鍵步驟）
id_mappings = {
    'old_skill_id': manifest['source_skill_id'],
    'new_skill_id': new_skill_id,
    'old_head_id': manifest.get('head_id'),
    'new_head_id': new_head_id,
    'old_skill_name': skill_name,
    'new_skill_name': new_skill_name
}

updated_csv_data = {}

for table_csv in manifest['database_tables']:
    csv_path = skill_folder / table_csv

    # 讀取 CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames

    # 更新 ID 欄位
    updated_rows = []
    for row in rows:
        # skill_id 更新
        if 'skill_id' in row:
            if row['skill_id'] == id_mappings['old_skill_id']:
                row['skill_id'] = id_mappings['new_skill_id']

        # head_id 更新
        if 'head_id' in row:
            if row['head_id'] == id_mappings['old_head_id']:
                row['head_id'] = id_mappings['new_head_id']

        # skill_name 更新（skill_heads 表）
        if 'skill_name' in row:
            if row['skill_name'] == id_mappings['old_skill_name']:
                row['skill_name'] = id_mappings['new_skill_name']

        # chunk_id 更新（需要重新生成）
        if 'chunk_id' in row and table_csv == 'skill_chunk_metadata.csv':
            # 保持 chunk_index，但更新 skill_id 部分
            chunk_index = row.get('chunk_index', 0)
            row['chunk_id'] = f"{new_skill_id}_chunk_{chunk_index}"

        updated_rows.append(row)

    updated_csv_data[table_csv] = (headers, updated_rows)
    logger.info(f"[Import] Updated IDs in {table_csv}: {len(updated_rows)} rows")
```

#### Phase 5: 資料庫交易式插入 (Transactional Insert)

```python
# 12. 交易式資料庫操作
conn = sqlite3.connect("data/skill_metadata.db")
conn.execute("BEGIN TRANSACTION")

try:
    cursor = conn.cursor()

    # 插入順序很重要：先 parent tables，後 child tables
    insert_order = [
        'skill_heads.csv',         # 1. Parent (head_id)
        'skill_metadata.csv',      # 2. Child of skill_heads
        'skill_chunk_metadata.csv',# 3. Child of skill_metadata
        'skill_document_mapping.csv', # 4. Child of skill_metadata
        'skill_overviews.csv'      # 5. Child of skill_metadata
    ]

    for table_csv in insert_order:
        if table_csv not in updated_csv_data:
            logger.warning(f"[Import] Skipping {table_csv}: no data")
            continue

        table_name = table_csv.replace('.csv', '')
        headers, rows = updated_csv_data[table_csv]

        if not rows:
            continue

        # 動態生成 INSERT 語句
        placeholders = ', '.join(['?' for _ in headers])
        columns = ', '.join(headers)
        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

        # 批次插入
        for row in rows:
            values = [row.get(col) for col in headers]
            cursor.execute(sql, values)

        logger.info(f"[Import] Inserted {len(rows)} rows into {table_name}")

    # 13. Commit 交易
    conn.commit()
    logger.info(f"[Import] Database transaction committed successfully")

except Exception as e:
    # 14. Rollback on error
    conn.rollback()
    logger.error(f"[Import] Database transaction failed: {str(e)}")
    raise HTTPException(
        status_code=500,
        detail=f"Database import failed: {str(e)}"
    )

finally:
    conn.close()
```

#### Phase 6: FAISS 索引複製 (FAISS Index Copy)

```python
# 15. 建立 FAISS 目錄
new_faiss_dir = Path(f"data/faiss_indices/skills/{new_skill_id}")
new_faiss_dir.mkdir(parents=True, exist_ok=True)

try:
    # 16. 複製 FAISS 檔案
    shutil.copy2(
        skill_folder / "index.faiss",
        new_faiss_dir / "index.faiss"
    )
    shutil.copy2(
        skill_folder / "index.pkl",
        new_faiss_dir / "index.pkl"
    )

    logger.info(f"[Import] FAISS index copied to {new_faiss_dir}")

    # 17. 驗證 FAISS 可載入
    from app.Providers.bge_embedding_provider import get_bge_embedding_provider
    from langchain_community.vectorstores import FAISS

    bge_provider = get_bge_embedding_provider()
    vector_store = FAISS.load_local(
        str(new_faiss_dir),
        bge_provider,
        allow_dangerous_deserialization=True
    )

    logger.info(f"[Import] FAISS index loaded successfully")

except Exception as e:
    # 清理已建立的 FAISS 目錄
    shutil.rmtree(new_faiss_dir, ignore_errors=True)

    # 清理資料庫記錄（需要再次連接）
    conn = sqlite3.connect("data/skill_metadata.db")
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM skill_chunk_metadata WHERE skill_id = ?", (new_skill_id,))
        cursor.execute("DELETE FROM skill_document_mapping WHERE skill_id = ?", (new_skill_id,))
        cursor.execute("DELETE FROM skill_overviews WHERE skill_id = ?", (new_skill_id,))
        cursor.execute("DELETE FROM skill_metadata WHERE skill_id = ?", (new_skill_id,))
        cursor.execute("DELETE FROM skill_heads WHERE head_id = ?", (new_head_id,))
        conn.commit()
    finally:
        conn.close()

    raise HTTPException(
        status_code=500,
        detail=f"FAISS index setup failed: {str(e)}"
    )
```

#### Phase 7: 清理與回應 (Cleanup & Response)

```python
# 18. 清理臨時檔案
shutil.rmtree(import_temp_dir, ignore_errors=True)

# 19. 回傳成功訊息
return {
    "success": True,
    "message": f"Skill '{new_skill_name}' imported successfully",
    "skill_id": new_skill_id,
    "head_id": new_head_id,
    "skill_name": new_skill_name,
    "total_chunks": len(updated_csv_data.get('skill_chunk_metadata.csv', ([], []))[1]),
    "import_timestamp": datetime.now(timezone.utc).isoformat()
}
```

### Import 錯誤處理策略

| 錯誤情境 | HTTP Status | 處理策略 | Rollback 動作 |
|---------|-------------|---------|--------------|
| **非 ZIP 檔案** | 400 | 拒絕上傳 | 無 |
| **ZIP 損壞** | 400 | 解壓縮失敗檢測 | 刪除臨時檔案 |
| **manifest.json 遺失** | 400 | 驗證檔案存在 | 刪除臨時檔案 |
| **CSV 檔案遺失** | 400 | 驗證所有 CSV 存在 | 刪除臨時檔案 |
| **FAISS 檔案遺失** | 400 | 驗證 index.faiss 和 index.pkl | 刪除臨時檔案 |
| **資料庫插入失敗** | 500 | Transaction Rollback | DB Rollback + 刪除臨時檔案 |
| **FAISS 載入失敗** | 500 | 驗證索引可載入 | DB Rollback + 刪除 FAISS 目錄 + 刪除臨時檔案 |
| **磁碟空間不足** | 507 | 檢查可用空間 | 完整清理 |

---

## 🎨 Frontend UI 設計

### 位置 1: Export 按鈕（每個 Skill Card）

**位置**: `template/skill_config.html` - Skill actions 區域（after "+" button）

**現有結構** (Lines 1666-1672):
```html
<div class="skill-actions" onclick="event.stopPropagation()">
    <button class="btn btn-outline btn-sm" onclick="showAddSourceModal(...)">
        <i class="fa-solid fa-plus"></i>
    </button>
    <button class="btn btn-outline btn-sm" onclick="showDeleteSkillModal(...)">
        <i class="fa-solid fa-trash"></i>
    </button>
</div>
```

**新增 Export 按鈕**:
```html
<div class="skill-actions" onclick="event.stopPropagation()">
    <!-- 現有按鈕 -->
    <button class="btn btn-outline btn-sm" onclick="showAddSourceModal(...)">
        <i class="fa-solid fa-plus"></i>
    </button>

    <!-- ✅ 新增：Export 按鈕 -->
    <button class="btn btn-outline btn-sm"
            onclick="exportSkill('${skill.head_id}')"
            title="匯出 Skill">
        <i class="fa-solid fa-download" style="color: #6b7280;"></i>
    </button>

    <button class="btn btn-outline btn-sm" onclick="showDeleteSkillModal(...)">
        <i class="fa-solid fa-trash"></i>
    </button>
</div>
```

**JavaScript 函數**:
```javascript
async function exportSkill(headId) {
    try {
        // 顯示載入中
        showLoading('正在匯出 Skill...');

        // 調用 Export API
        const response = await fetch(`/api/v1/config/skills/export/${headId}`, {
            method: 'GET'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '匯出失敗');
        }

        // 取得檔案名稱（從 Content-Disposition header）
        const contentDisposition = response.headers.get('Content-Disposition');
        const filenameMatch = contentDisposition && contentDisposition.match(/filename="(.+)"/);
        const filename = filenameMatch ? filenameMatch[1] : 'skill_export.zip';

        // 下載檔案
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        hideLoading();
        showToast('Skill 匯出成功', 'success');

    } catch (error) {
        console.error('[Export] Error:', error);
        hideLoading();
        showToast(`匯出失敗：${error.message}`, 'error');
    }
}
```

### 位置 2: Import 按鈕（頂部工具列）

**位置**: `template/skill_config.html` - Top toolbar（left of "Add Skill" button）

**現有結構** (Lines 858-864):
```html
<div class="skills-header-actions">
    <button class="btn btn-outline" onclick="loadConfig()">
        <i class="fa-solid fa-refresh"></i>
        <span id="btn-refresh">Refresh</span>
    </button>
    <button class="btn btn-primary" onclick="showAddSkillModal()">
        <i class="fa-solid fa-plus"></i>
        <span id="btn-add-skill">Add Skill</span>
    </button>
</div>
```

**新增 Import 按鈕**:
```html
<div class="skills-header-actions">
    <button class="btn btn-outline" onclick="loadConfig()">
        <i class="fa-solid fa-refresh"></i>
        <span id="btn-refresh">Refresh</span>
    </button>

    <!-- ✅ 新增：Import 按鈕 -->
    <button class="btn btn-outline" onclick="document.getElementById('import-file-input').click()">
        <i class="fa-solid fa-upload"></i>
        <span id="btn-import-skill">Import Skill</span>
    </button>
    <!-- 隱藏的檔案選擇器 -->
    <input type="file"
           id="import-file-input"
           accept=".zip"
           style="display: none;"
           onchange="handleImportFile(this)">

    <button class="btn btn-primary" onclick="showAddSkillModal()">
        <i class="fa-solid fa-plus"></i>
        <span id="btn-add-skill">Add Skill</span>
    </button>
</div>
```

**JavaScript 函數**:
```javascript
async function handleImportFile(input) {
    const file = input.files[0];
    if (!file) return;

    // 驗證檔案類型
    if (!file.name.endsWith('.zip')) {
        showToast('請選擇 ZIP 檔案', 'error');
        input.value = ''; // 清空選擇
        return;
    }

    try {
        // 顯示載入中（含進度）
        showLoading(`正在匯入 Skill: ${file.name}...`);

        // 建立 FormData
        const formData = new FormData();
        formData.append('file', file);

        // 調用 Import API
        const response = await fetch('/api/v1/config/skills/import', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || '匯入失敗');
        }

        hideLoading();

        // 顯示成功訊息
        showToast(
            `Skill "${result.skill_name}" 匯入成功！(${result.total_chunks} chunks)`,
            'success'
        );

        // 刷新列表
        await loadConfig();

    } catch (error) {
        console.error('[Import] Error:', error);
        hideLoading();
        showToast(`匯入失敗：${error.message}`, 'error');
    } finally {
        // 清空檔案選擇（允許重複匯入同一檔案）
        input.value = '';
    }
}
```

### UI 樣式建議

```css
/* Export 按鈕 hover 效果 */
.skill-actions button:hover i.fa-download {
    color: #3b82f6 !important;
}

/* Import 按鈕樣式 */
.btn-outline i.fa-upload {
    color: #10b981;
}

.btn-outline:hover i.fa-upload {
    color: #059669;
}
```

---

## 🛡️ 安全性與資料完整性

### 安全性檢查清單

| 檢查項目 | 實施方式 | 優先級 |
|---------|---------|--------|
| **檔案類型驗證** | 只接受 .zip 檔案 | 🔴 High |
| **ZIP 炸彈防護** | 限制解壓縮後大小 < 500MB | 🔴 High |
| **SQL Injection 防護** | 使用 parameterized queries | 🔴 High |
| **Path Traversal 防護** | Sanitize 檔案名稱，禁止 `../` | 🔴 High |
| **檔案名稱清理** | 移除特殊字元（只保留字母、數字、底線、中文） | 🟡 Medium |
| **磁碟空間檢查** | 確保至少 1GB 可用空間 | 🟡 Medium |
| **同時上傳限制** | 使用 asyncio lock，一次只處理一個 import | 🟢 Low |

### 檔案名稱 Sanitize 函數

```python
import re

def sanitize_filename(filename: str) -> str:
    """
    清理檔案名稱，移除非法字元

    允許：字母、數字、底線、中文、連字號
    禁止：/ \ : * ? " < > | 等特殊字元
    """
    # 移除路徑分隔符（防止 path traversal）
    filename = filename.replace('/', '_').replace('\\', '_')

    # 移除其他非法字元
    filename = re.sub(r'[<>:"|?*]', '_', filename)

    # 限制長度（避免檔案系統限制）
    if len(filename) > 200:
        filename = filename[:200]

    return filename
```

### ZIP 炸彈防護

```python
def check_zip_safety(zip_path: Path, max_size_mb: int = 500):
    """
    檢查 ZIP 檔案安全性

    防止 ZIP 炸彈攻擊（壓縮比過高的惡意檔案）
    """
    total_size = 0

    with zipfile.ZipFile(zip_path, 'r') as zipf:
        for info in zipf.infolist():
            total_size += info.file_size

            # 單一檔案大小檢查
            if info.file_size > 100 * 1024 * 1024:  # 100MB
                raise ValueError(f"File too large in ZIP: {info.filename}")

        # 總解壓縮大小檢查
        if total_size > max_size_mb * 1024 * 1024:
            raise ValueError(
                f"ZIP content too large: {total_size / 1024 / 1024:.2f}MB "
                f"(max: {max_size_mb}MB)"
            )

    return True
```

### 資料完整性驗證

```python
def validate_imported_data(new_skill_id: str, manifest: dict):
    """
    驗證匯入的資料完整性
    """
    conn = sqlite3.connect("data/skill_metadata.db")
    cursor = conn.cursor()

    # 1. 驗證 skill_metadata 存在
    cursor.execute("SELECT COUNT(*) FROM skill_metadata WHERE skill_id = ?", (new_skill_id,))
    if cursor.fetchone()[0] == 0:
        raise ValueError("skill_metadata not found after import")

    # 2. 驗證 chunks 數量一致
    cursor.execute(
        "SELECT COUNT(*) FROM skill_chunk_metadata WHERE skill_id = ?",
        (new_skill_id,)
    )
    actual_chunks = cursor.fetchone()[0]
    expected_chunks = manifest.get('total_chunks', 0)

    if actual_chunks != expected_chunks:
        logger.warning(
            f"Chunk count mismatch: expected {expected_chunks}, got {actual_chunks}"
        )

    # 3. 驗證 FAISS 索引可讀
    faiss_dir = Path(f"data/faiss_indices/skills/{new_skill_id}")
    if not (faiss_dir / "index.faiss").exists():
        raise ValueError("FAISS index file missing after import")

    conn.close()
    logger.info(f"[Import] Data integrity validated for {new_skill_id}")
```

---

## 🧪 測試計畫

### 單元測試

```python
# tests/test_skill_export_import.py

import pytest
import tempfile
from pathlib import Path

class TestSkillExport:
    """Export 功能測試"""

    def test_export_existing_skill(self, test_skill_id):
        """測試匯出存在的 skill"""
        response = client.get(f"/api/v1/config/skills/export/{test_skill_id}")
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/zip'

    def test_export_nonexistent_skill(self):
        """測試匯出不存在的 skill"""
        response = client.get("/api/v1/config/skills/export/fake_skill_id")
        assert response.status_code == 404

    def test_export_missing_faiss(self, test_skill_id_no_faiss):
        """測試 FAISS 檔案遺失的情況"""
        response = client.get(f"/api/v1/config/skills/export/{test_skill_id_no_faiss}")
        assert response.status_code == 500
        assert "FAISS index missing" in response.json()['detail']

class TestSkillImport:
    """Import 功能測試"""

    def test_import_valid_zip(self, valid_skill_zip):
        """測試匯入有效的 ZIP"""
        with open(valid_skill_zip, 'rb') as f:
            response = client.post(
                "/api/v1/config/skills/import",
                files={"file": ("skill.zip", f, "application/zip")}
            )
        assert response.status_code == 200
        result = response.json()
        assert result['success'] == True
        assert 'skill_id' in result

    def test_import_corrupted_zip(self, corrupted_zip):
        """測試匯入損壞的 ZIP"""
        with open(corrupted_zip, 'rb') as f:
            response = client.post(
                "/api/v1/config/skills/import",
                files={"file": ("bad.zip", f, "application/zip")}
            )
        assert response.status_code == 400
        assert "Corrupted ZIP" in response.json()['detail']

    def test_import_missing_manifest(self, zip_no_manifest):
        """測試缺少 manifest.json 的 ZIP"""
        with open(zip_no_manifest, 'rb') as f:
            response = client.post(
                "/api/v1/config/skills/import",
                files={"file": ("no_manifest.zip", f, "application/zip")}
            )
        assert response.status_code == 400
        assert "manifest.json not found" in response.json()['detail']

    def test_import_id_regeneration(self, valid_skill_zip):
        """測試 ID 重新生成（避免衝突）"""
        # 第一次匯入
        with open(valid_skill_zip, 'rb') as f:
            response1 = client.post(
                "/api/v1/config/skills/import",
                files={"file": ("skill.zip", f, "application/zip")}
            )
        skill_id_1 = response1.json()['skill_id']

        # 第二次匯入同一個 ZIP
        with open(valid_skill_zip, 'rb') as f:
            response2 = client.post(
                "/api/v1/config/skills/import",
                files={"file": ("skill.zip", f, "application/zip")}
            )
        skill_id_2 = response2.json()['skill_id']

        # 驗證 ID 不同
        assert skill_id_1 != skill_id_2
```

### 整合測試

```python
class TestExportImportRoundtrip:
    """完整的 Export → Import 循環測試"""

    def test_export_import_cycle(self, test_skill_id):
        """測試完整的匯出 → 匯入流程"""
        # 1. Export
        export_response = client.get(f"/api/v1/config/skills/export/{test_skill_id}")
        assert export_response.status_code == 200

        # 儲存 ZIP
        zip_path = Path(tempfile.mkdtemp()) / "exported_skill.zip"
        with open(zip_path, 'wb') as f:
            f.write(export_response.content)

        # 2. Import
        with open(zip_path, 'rb') as f:
            import_response = client.post(
                "/api/v1/config/skills/import",
                files={"file": ("skill.zip", f, "application/zip")}
            )
        assert import_response.status_code == 200

        new_skill_id = import_response.json()['skill_id']

        # 3. 驗證匯入的資料
        # 3a. 檢查資料庫記錄
        conn = sqlite3.connect("data/skill_metadata.db")
        cursor = conn.cursor()

        cursor.execute("SELECT total_chunks FROM skill_metadata WHERE skill_id = ?", (new_skill_id,))
        new_chunks = cursor.fetchone()[0]

        cursor.execute("SELECT total_chunks FROM skill_metadata WHERE skill_id = ?", (test_skill_id,))
        original_chunks = cursor.fetchone()[0]

        assert new_chunks == original_chunks

        # 3b. 檢查 FAISS 索引
        faiss_dir = Path(f"data/faiss_indices/skills/{new_skill_id}")
        assert (faiss_dir / "index.faiss").exists()
        assert (faiss_dir / "index.pkl").exists()

        conn.close()
```

### 手動測試清單

- [ ] **Export 測試**:
  1. [ ] 匯出包含大量 chunks 的 skill (>1000 chunks)
  2. [ ] 匯出包含中文名稱的 skill
  3. [ ] 匯出包含特殊字元的 skill name
  4. [ ] 檢查 ZIP 檔案結構完整性
  5. [ ] 檢查 manifest.json 內容正確性

- [ ] **Import 測試**:
  1. [ ] 匯入剛匯出的 ZIP
  2. [ ] 重複匯入同一個 ZIP（測試 ID 衝突處理）
  3. [ ] 匯入檔案名稱衝突的 skill
  4. [ ] 匯入損壞的 ZIP（手動破壞檔案）
  5. [ ] 匯入缺少檔案的 ZIP

- [ ] **UI 測試**:
  1. [ ] Export 按鈕位置正確（每個 skill card）
  2. [ ] Import 按鈕位置正確（頂部工具列）
  3. [ ] 點擊 Export 觸發下載
  4. [ ] 點擊 Import 開啟檔案選擇器
  5. [ ] 上傳後自動刷新列表

---

## 📊 效能考量

### Export 效能

| 操作 | 預估時間 | 瓶頸 |
|------|---------|------|
| **資料庫查詢** | ~100ms | SQLite I/O |
| **CSV 生成** | ~500ms (1000 chunks) | 記憶體序列化 |
| **FAISS 檔案複製** | ~50ms (1MB) | 磁碟 I/O |
| **ZIP 壓縮** | ~1s (10MB uncompressed) | CPU |
| **總計** | ~2s (中型 skill) | - |

### Import 效能

| 操作 | 預估時間 | 瓶頸 |
|------|---------|------|
| **檔案上傳** | 網路頻寬相關 | 網路 |
| **ZIP 解壓縮** | ~500ms | 磁碟 I/O |
| **Manifest 驗證** | ~50ms | JSON parsing |
| **CSV 解析與 ID 更新** | ~1s (1000 rows) | 記憶體操作 |
| **資料庫插入** | ~2s (批次插入) | SQLite transaction |
| **FAISS 複製與驗證** | ~500ms | 磁碟 I/O + 載入驗證 |
| **總計** | ~5s (中型 skill) | - |

### 最佳化建議

1. **批次操作**: 使用 `executemany()` 批次插入資料庫
2. **串流處理**: ZIP 檔案使用串流上傳，避免全部載入記憶體
3. **非同步處理**: 使用 BackgroundTasks 處理大型 import
4. **進度回報**: 使用 SSE 回報 import 進度（進階功能）

---

## 🚀 實施優先級與時程

### Phase 1: Backend Export API (優先級: 🔴 High)

**預估時間**: 4-6 小時

- [ ] 實作 `/config/skills/export/{skill_id}` endpoint
- [ ] 資料庫查詢與 CSV 生成
- [ ] Manifest.json 建立
- [ ] ZIP 壓縮與檔案回傳
- [ ] 錯誤處理與 logging
- [ ] 單元測試

### Phase 2: Backend Import API (優先級: 🔴 High)

**預估時間**: 6-8 小時

- [ ] 實作 `/config/skills/import` endpoint
- [ ] ZIP 上傳與解壓縮
- [ ] Manifest 驗證
- [ ] ID 重新生成邏輯
- [ ] CSV ID 更新
- [ ] 交易式資料庫插入
- [ ] FAISS 索引複製與驗證
- [ ] 完整的錯誤處理與 rollback
- [ ] 單元測試與整合測試

### Phase 3: Frontend UI (優先級: 🟡 Medium)

**預估時間**: 2-3 小時

- [ ] Export 按鈕 UI 實作（skill card）
- [ ] Import 按鈕 UI 實作（頂部工具列）
- [ ] JavaScript 函數實作
- [ ] Loading 指示器
- [ ] Toast 通知
- [ ] 前端錯誤處理

### Phase 4: 測試與除錯 (優先級: 🟡 Medium)

**預估時間**: 4-5 小時

- [ ] 完整的 Export → Import 循環測試
- [ ] 邊界案例測試
- [ ] 錯誤處理驗證
- [ ] UI 互動測試
- [ ] 效能測試

### Phase 5: 文檔與部署 (優先級: 🟢 Low)

**預估時間**: 2 小時

- [ ] API 文檔更新
- [ ] 使用者指南
- [ ] 部署與遷移說明

**總預估時間**: 18-24 小時

---

## 📝 實施檢查清單

### 開發前檢查

- [ ] 確認現有系統版本與資料庫 schema
- [ ] 備份現有 skill_metadata.db
- [ ] 建立開發分支 `feature/skill-export-import`
- [ ] 設定測試環境與測試資料

### 開發中檢查

- [ ] 遵循現有程式碼風格
- [ ] 每個函數都有 docstring
- [ ] 所有關鍵步驟都有 logging
- [ ] 錯誤訊息清晰且可操作
- [ ] 使用 type hints

### 測試檢查

- [ ] 所有單元測試通過
- [ ] 整合測試通過
- [ ] 手動測試清單完成
- [ ] 邊界案例全部覆蓋
- [ ] 錯誤處理驗證完成

### 部署前檢查

- [ ] Code review 完成
- [ ] 文檔更新完成
- [ ] 版本號更新
- [ ] Migration script 準備（如需要）
- [ ] Rollback plan 準備

---

## ⚠️ 風險與緩解策略

| 風險 | 影響 | 機率 | 緩解策略 |
|------|------|------|---------|
| **資料庫 schema 變更** | High | Low | 在 manifest 中記錄 schema version |
| **FAISS 版本不相容** | High | Medium | 在 manifest 中記錄 FAISS 版本 |
| **大型 skill 記憶體不足** | Medium | Medium | 使用串流處理，分批操作 |
| **並發 import 衝突** | Medium | Low | 使用 asyncio lock 限制並發 |
| **磁碟空間不足** | High | Low | 預先檢查可用空間 |
| **ID 衝突未處理** | High | Low | 完整的 ID 重新生成邏輯 |

---

## 📚 參考資料

### 相關檔案

| 檔案 | 用途 |
|------|------|
| `app/api/v1/endpoints/skills.py` | 現有 Skill API endpoints |
| `app/Providers/skill_metadata_provider/client.py` | 資料庫操作 provider |
| `template/skill_config.html` | Frontend UI |
| `data/skill_metadata.db` | SQLite 資料庫 |
| `data/faiss_indices/skills/` | FAISS 索引儲存 |

### 技術文檔

- [FastAPI File Upload](https://fastapi.tiangolo.com/tutorial/request-files/)
- [Python zipfile](https://docs.python.org/3/library/zipfile.html)
- [SQLite Transaction](https://docs.python.org/3/library/sqlite3.html#controlling-transactions)
- [FAISS save/load](https://github.com/facebookresearch/faiss/wiki/Getting-started#saving-and-loading-an-index)

---

## ✅ 總結

本實施計畫提供了完整的 Skill Export/Import 功能設計，涵蓋：

1. **完整的技術規格**：詳細的 API 設計、資料流程、錯誤處理
2. **安全性考量**：檔案驗證、SQL injection 防護、ZIP 炸彈防護
3. **資料完整性**：交易式操作、ID 衝突處理、完整性驗證
4. **使用者體驗**：清楚的 UI 位置、友善的錯誤訊息、進度指示
5. **測試策略**：單元測試、整合測試、手動測試清單

**下一步行動**：
1. ✅ Review 本計畫，確認所有需求已覆蓋
2. ⏳ 取得用戶批准後開始實施
3. ⏳ 按照 Phase 1-5 順序實作
4. ⏳ 每個 Phase 完成後進行測試與驗證

---

**文檔版本**: 1.0
**最後更新**: 2025-12-25
**作者**: SuperClaude Planning Agent
**狀態**: 待審核 → 待實施
