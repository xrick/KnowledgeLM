# Skill Data Management System - 完整實作指南

**版本**: 1.0
**日期**: 2025-11-27
**作者**: Claude Code (SuperClaude Framework)
**狀態**: ✅ 完成並通過測試 (19/19)

---

## 📋 目錄

1. [任務描述](#任務描述)
2. [系統架構](#系統架構)
3. [實作細節](#實作細節)
4. [資料庫設計](#資料庫設計)
5. [API 參考文檔](#api-參考文檔)
6. [使用者手冊](#使用者手冊)
7. [集成指南](#集成指南)
8. [故障排除](#故障排除)

---

## 任務描述

### 目標
建立一套完整的 Skill 資料生命週期管理系統，支援：
- **多 Skill 支援**: 管理多個獨立的知識庫
- **PDF 來源管理**: 為每個 Skill 配置多個 PDF 來源
- **臨時附件機制**: 支援臨時添加 PDF，達到閾值後觸發完整重建
- **Web UI 管理**: 視覺化管理界面
- **RESTful API**: 程式化管理接口

### 核心功能

| 功能 | 說明 | 使用場景 |
|------|------|---------|
| **資料清除** | 安全刪除舊的 skill 資料，保留 embedding_models | 完整重建前的準備 |
| **配置管理** | JSON 配置定義 skills 與 PDF 對應關係 | 版本控制、備份 |
| **資料重建** | 根據配置重新生成 embeddings 和索引 | 新增 PDF、修改配置後 |
| **臨時附件** | 快速添加 PDF 到 skills，不需重建 | 即時添加臨時資料 |
| **Web UI** | 友善的管理界面 | 非技術用戶操作 |
| **API 接口** | REST endpoints 支援程式化操作 | 自動化、集成 |

---

## 系統架構

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Skill Data Management System                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   Scripts Layer  │    │ Config Layer │    │  Web UI Layer│     │
│  ├──────────────────┤    ├──────────────┤    ├──────────────┤     │
│  │ • clean_*.sh     │    │ skill_config │    │ skill_config │     │
│  │ • rebuild_*.sh   │◄──►│ .json        │◄──►│ .html        │     │
│  │ • rebuild_*.py   │    │              │    │              │     │
│  └──────────────────┘    └──────────────┘    └──────────────┘     │
│         │                       │                    │              │
│         └───────────────────────┴────────────────────┘              │
│                          │                                          │
│                          ▼                                          │
│         ┌────────────────────────────────┐                         │
│         │   RESTful API Layer            │                         │
│         │  /api/v1/skills/config/*       │                         │
│         │  /api/v1/skills/rebuild        │                         │
│         └────────────────────────────────┘                         │
│                          │                                          │
│                          ▼                                          │
│         ┌────────────────────────────────┐                         │
│         │   Service Layer                │                         │
│         │ • SkillMetadataProvider        │                         │
│         │ • SkillIngestionService        │                         │
│         │ • SkillRetrievalService        │                         │
│         │ • BGEEmbeddingProvider         │                         │
│         │ • VectorStoreProvider          │                         │
│         └────────────────────────────────┘                         │
│                          │                                          │
│                          ▼                                          │
│         ┌────────────────────────────────┐                         │
│         │   Data Layer                   │                         │
│         │ • skill_metadata.db (SQLite)   │                         │
│         │ • faiss_indices/skills/        │                         │
│         │   - skill_master.index         │                         │
│         │   - skill_master.metadata      │                         │
│         └────────────────────────────────┘                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 實作細節

### 新增檔案

#### 1. Scripts 目錄 (`scripts/skill_data/`)

##### clean_skill_tables.sh
**用途**: 安全清除舊 skill 資料

**功能**:
```bash
# 清除的表格
- skill_chunk_metadata
- skill_document_mapping
- skill_metadata
- skill_overviews

# 保留的表格
- embedding_models ✅
```

**特色**:
- ✅ 自動備份資料庫 (backup_skill_metadata.db.{timestamp})
- ✅ 清除相應的 FAISS 索引目錄
- ✅ 顯示清除前後的表格統計
- ✅ 支援互動模式和強制模式

**使用方式**:
```bash
# 互動模式（需確認）
./scripts/skill_data/clean_skill_tables.sh

# 強制模式（跳過確認）
./scripts/skill_data/clean_skill_tables.sh --force
```

---

##### rebuild_skills.sh
**用途**: Skill 重建的 Shell wrapper

**流程**:
1. 驗證依賴 (python3, sqlite3, PyPDF2)
2. 檢查配置文件有效性
3. 可選: 執行清除操作
4. 執行 Python 重建腳本
5. 驗證結果

**選項**:
```bash
--clean              # 重建前先執行清除
--config <path>      # 使用自定義配置文件
--skill <name>       # 只重建指定的 skill
--dry-run            # 模擬執行（不實際修改）
--force              # 跳過確認步驟
```

**使用方式**:
```bash
# 完整重建（含清除）
./scripts/skill_data/rebuild_skills.sh --clean --force

# 只重建特定 skill
./scripts/skill_data/rebuild_skills.sh --skill "LLM"

# 使用自定義配置
./scripts/skill_data/rebuild_skills.sh --config /path/to/config.json

# 模擬執行
./scripts/skill_data/rebuild_skills.sh --dry-run
```

---

##### rebuild_from_config.py
**用途**: 核心重建邏輯，根據 JSON 配置重建 skills

**核心類**: `SkillConfigRebuilder`

**主要方法**:
```python
class SkillConfigRebuilder:
    def __init__(self, config_path: str)
        # 初始化配置和 providers

    def rebuild_all_skills(self, skill_filter: Optional[str] = None)
        # 根據配置重建所有 skills（可選過濾特定 skill）

    def rebuild_skill(self, skill_config: Dict)
        # 重建單個 skill：
        # 1. 提取 PDF 頁面文字
        # 2. 分割 chunks
        # 3. 生成 embeddings (BGE-M3)
        # 4. 儲存到 FAISS
        # 5. 儲存 metadata 到 SQLite

    def process_pdf_file(self, pdf_path: str) -> List[str]
        # 使用 PyPDF2 提取 PDF 文字內容

    def chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]
        # 將文字分割為重疊的 chunks

    def generate_embeddings(self, chunks: List[str]) -> np.ndarray
        # 使用 BGE-M3 生成向量 (1024-dim)

    def save_to_faiss(self, skill_id: str, vectors: np.ndarray, metadata: Dict)
        # 儲存到 FAISS 索引和元資料
```

**重建流程**:
```
1. 載入 skill_config.json
2. 對每個啟用的 skill:
   a. 取得所有啟用的 PDF 來源
   b. 提取文字內容 (PyPDF2)
   c. 分割成 chunks (size=1000, overlap=200)
   d. 生成 embeddings (BGE-M3, dim=1024)
   e. 儲存到 FAISS (skills/{skill_id}/master.index)
   f. 儲存 metadata 到 SQLite
   g. 記錄重建統計
3. 清除 instant_attachments
4. 輸出摘要報告
```

**環境變數**:
```bash
SKILL_CONFIG_PATH  # 配置文件路徑 (可選，預設: scripts/skill_data/skill_config.json)
SKILL_FILTER       # 只重建指定 skill (可選)
```

---

##### skill_config.json
**用途**: Skills 與 PDF 來源的對應配置

**結構**:
```json
{
    "version": "1.0",
    "description": "...",
    "last_updated": "2025-11-27",

    "skills": [
        {
            "skill_name": "LLM",
            "description": "Large Language Model 基礎知識與實作",
            "category": "Technology",
            "enabled": true,
            "sources": [
                {
                    "path": "refData/rawdata/LLM/book1.pdf",
                    "enabled": true,
                    "description": "書籍描述"
                }
            ]
        }
    ],

    "instant_attachments": [
        // 臨時添加的 PDF，達到 threshold 後應執行重建
    ],

    "settings": {
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "embedding_model": "BAAI/bge-m3",
        "embedding_dimension": 1024,
        "rebuild_threshold": 5
    }
}
```

**欄位說明**:

| 欄位 | 型態 | 說明 |
|------|------|------|
| `skill_name` | string | Skill 唯一識別符 |
| `description` | string | Skill 的功能描述 |
| `category` | string | Skill 分類 (Technology, Legal 等) |
| `enabled` | boolean | 此 skill 是否啟用 |
| `sources[].path` | string | PDF 相對路徑（相對於項目根目錄） |
| `sources[].enabled` | boolean | 此 PDF 是否包含在重建中 |
| `sources[].description` | string | PDF 的簡短描述 |
| `chunk_size` | number | 每個 chunk 的字元數 |
| `chunk_overlap` | number | chunk 之間的重疊字元數 |
| `embedding_model` | string | 使用的 embedding 模型 |
| `embedding_dimension` | number | embedding 向量維度 |
| `rebuild_threshold` | number | instant_attachments 達到此數量時建議重建 |

**當前配置範例**:
- **LLM** (5 本書): 大型語言模型基礎與實作
- **六法全書-刑法** (2 本): 刑法及刑事訴訟法
- **六法全書-民法** (5 本): 民法及相關訴訟程序

---

##### test_workflow.sh
**用途**: 完整的工作流程測試

**測試項目** (19 個):

1. **檔案存在性測試** (4 個):
   - clean_skill_tables.sh
   - rebuild_skills.sh
   - rebuild_from_config.py
   - skill_config.json

2. **配置文件測試** (3 個):
   - skill_config.json 是有效的 JSON
   - 配置有 skills 陣列
   - 配置有 settings

3. **腳本語法測試** (3 個):
   - clean_skill_tables.sh bash 語法
   - rebuild_skills.sh bash 語法
   - rebuild_from_config.py Python 語法

4. **資料庫測試** (3 個):
   - skill_metadata.db 存在
   - skill_metadata 表存在
   - embedding_models 表存在

5. **API 測試** (3 個):
   - 伺服器健康檢查
   - Skills API 回應
   - Demo skills API 回應

6. **Template 測試** (3 個):
   - skill_main.html 存在
   - skill_config.html 存在
   - skill_main.html 有配置連結

**執行**:
```bash
./scripts/skill_data/test_workflow.sh
```

**預期輸出**:
```
✅ 19/19 測試通過
```

---

### 修改檔案

#### 1. app/api/v1/endpoints/skills.py

**新增的資料模型**:

```python
class PDFSourceModel(BaseModel):
    """PDF 來源模型"""
    path: str              # 相對路徑
    enabled: bool = True   # 是否啟用
    description: str = ""  # 描述

class SkillConfigModel(BaseModel):
    """Skill 配置模型"""
    skill_name: str
    description: str = ""
    category: str = "General"
    enabled: bool = True
    sources: List[PDFSourceModel] = []

class InstantAttachmentRequest(BaseModel):
    """臨時附件請求"""
    skill_name: str
    path: str
    description: Optional[str] = ""

class RebuildRequest(BaseModel):
    """重建請求"""
    skill_name: Optional[str] = None  # 可選: 只重建某 skill
    clean_first: bool = True           # 是否先清除舊資料
```

**新增的輔助函數**:

```python
def load_skill_config() -> Dict[str, Any]:
    """載入 skill_config.json"""
    # 從 scripts/skill_data/skill_config.json 讀取
    # 如果不存在則返回預設配置

def save_skill_config(config: Dict[str, Any]):
    """儲存 skill_config.json"""
    # 寫入到 scripts/skill_data/skill_config.json
    # 自動更新 last_updated 時間戳
```

**新增的 API Endpoints**:

| 方法 | 路徑 | 功能 |
|------|------|------|
| GET | `/api/v1/skills/config` | 獲取完整配置 |
| GET | `/api/v1/skills/config/skills` | 獲取 skills 清單 |
| POST | `/api/v1/skills/config/skills` | 新增 skill |
| POST | `/api/v1/skills/config/skills/{skill_name}/sources` | 新增 PDF 來源 |
| DELETE | `/api/v1/skills/config/skills/{skill_name}/sources` | 移除 PDF 來源 |
| GET | `/api/v1/skills/config/instant-attachments` | 獲取臨時附件 |
| POST | `/api/v1/skills/config/instant-attachments` | 新增臨時附件 |
| DELETE | `/api/v1/skills/config/instant-attachments` | 清除所有臨時附件 |
| POST | `/api/v1/skills/rebuild` | 觸發重建（背景執行） |
| GET | `/api/v1/skills/rebuild/status` | 查看重建日誌 |

---

#### 2. main.py

**新增的路由**:

```python
@app.get("/skill", response_class=HTMLResponse)
async def serve_skill_alias():
    """Skill 主介面別名"""
    # 返回 template/skill_main.html

@app.get("/skill/config", response_class=HTMLResponse)
async def serve_skill_config():
    """Skill 配置管理介面"""
    # 返回 template/skill_config.html
```

---

#### 3. template/skill_main.html

**新增的導航連結**:

```html
<!-- 在側邊欄新增 -->
<a href="/skill/config" class="nav-link">
    <i class="fa-solid fa-cog"></i>
    <span>Skill 配置管理</span>
    <i class="fa-solid fa-arrow-right nav-arrow"></i>
</a>
```

---

### 新增檔案 - Template

#### template/skill_config.html

**用途**: 視覺化管理 Skills 與 PDF 來源的 Web UI

**功能模塊**:

1. **統計儀表板**:
   - 總 Skill 數
   - 啟用 Skill 數
   - 總 PDF 來源數
   - 臨時附件數
   - 重建狀態

2. **Skill 卡片列表**:
   - 顯示每個 skill 的基本信息
   - 展開/摺疊 PDF 來源列表
   - 快速操作按鈕（新增、刪除）
   - 視覺化指示器（啟用/停用）

3. **新增 Skill 模態框**:
   - Skill 名稱
   - 描述
   - 分類
   - 初始 PDF 來源

4. **新增 PDF 來源模態框**:
   - 選擇目標 skill
   - 輸入 PDF 路徑
   - 輸入描述

5. **臨時附件面板**:
   - 列出所有臨時附件
   - 檢查重建狀態
   - 清除操作

6. **重建控制面板**:
   - 選擇重建範圍（所有 skills 或特定 skill）
   - 是否清除舊資料
   - 觸發重建按鈕
   - 重建日誌查看

7. **即時日誌查看**:
   - 實時更新重建進度
   - 錯誤信息顯示
   - 自動刷新

**URL**: http://localhost:8000/skill/config

**視覺設計**:
- 淺色主題，符合應用統一風格
- 響應式設計，支援行動設備
- 即時反饋，操作後立即更新 UI
- 清晰的視覺層次，易於導航

---

## 資料庫設計

### skill_metadata.db (SQLite)

**數據庫位置**: `./data/skill_metadata.db`

**表結構**:

#### 1. skill_metadata
**用途**: 儲存 skill 的元資料

```sql
CREATE TABLE skill_metadata (
    id TEXT PRIMARY KEY,
    skill_id TEXT UNIQUE NOT NULL,
    skill_name TEXT NOT NULL,
    description TEXT,
    category TEXT DEFAULT 'General',
    enabled BOOLEAN DEFAULT 1,
    embedding_model TEXT DEFAULT 'BAAI/bge-m3',
    embedding_dimension INTEGER DEFAULT 1024,
    total_chunks INTEGER DEFAULT 0,
    total_documents INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON
);
```

| 欄位 | 型態 | 說明 |
|------|------|------|
| `id` | TEXT | UUID，主鍵 |
| `skill_id` | TEXT | Skill 唯一識別符 |
| `skill_name` | TEXT | Skill 名稱 |
| `description` | TEXT | Skill 描述 |
| `category` | TEXT | Skill 分類 |
| `enabled` | BOOLEAN | 是否啟用 |
| `embedding_model` | TEXT | 使用的 embedding 模型 |
| `embedding_dimension` | INTEGER | embedding 維度 |
| `total_chunks` | INTEGER | 總 chunk 數 |
| `total_documents` | INTEGER | 總文檔數 |
| `created_at` | TIMESTAMP | 建立時間 |
| `updated_at` | TIMESTAMP | 最後更新時間 |
| `metadata` | JSON | 額外元資料 |

---

#### 2. skill_document_mapping
**用途**: 將 PDF 來源對應到 skills

```sql
CREATE TABLE skill_document_mapping (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    pdf_path TEXT NOT NULL,
    pdf_name TEXT,
    page_count INTEGER,
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id),
    UNIQUE(skill_id, document_id)
);
```

| 欄位 | 型態 | 說明 |
|------|------|------|
| `id` | TEXT | UUID，主鍵 |
| `skill_id` | TEXT | 所屬 skill |
| `document_id` | TEXT | 文檔唯一識別符 |
| `pdf_path` | TEXT | PDF 相對路徑 |
| `pdf_name` | TEXT | PDF 檔案名稱 |
| `page_count` | INTEGER | 頁數 |
| `enabled` | BOOLEAN | 是否啟用 |
| `created_at` | TIMESTAMP | 建立時間 |

---

#### 3. skill_chunk_metadata
**用途**: 儲存 skill chunks 的詳細信息

```sql
CREATE TABLE skill_chunk_metadata (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    document_id TEXT,
    chunk_index INTEGER,
    content TEXT NOT NULL,
    content_hash TEXT,
    chunk_size INTEGER,
    page_number INTEGER,
    embedding_generated BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id),
    FOREIGN KEY (document_id) REFERENCES skill_document_mapping(document_id),
    UNIQUE(skill_id, document_id, chunk_index)
);
```

| 欄位 | 型態 | 說明 |
|------|------|------|
| `id` | TEXT | UUID，主鍵 |
| `skill_id` | TEXT | 所屬 skill |
| `document_id` | TEXT | 所屬文檔 |
| `chunk_index` | INTEGER | chunk 在文檔中的索引 |
| `content` | TEXT | chunk 的實際內容 |
| `content_hash` | TEXT | 內容 hash，用於去重 |
| `chunk_size` | INTEGER | chunk 字元數 |
| `page_number` | INTEGER | 原 PDF 頁碼 |
| `embedding_generated` | BOOLEAN | embedding 是否已生成 |
| `created_at` | TIMESTAMP | 建立時間 |

---

#### 4. skill_overviews
**用途**: 儲存 skill 的概要信息

```sql
CREATE TABLE skill_overviews (
    id TEXT PRIMARY KEY,
    skill_id TEXT UNIQUE NOT NULL,
    overview_text TEXT,
    key_topics TEXT,  -- JSON 陣列
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id)
);
```

| 欄位 | 型態 | 說明 |
|------|------|------|
| `id` | TEXT | UUID，主鍵 |
| `skill_id` | TEXT | 所屬 skill |
| `overview_text` | TEXT | Skill 概述文本 |
| `key_topics` | TEXT | 主要主題 (JSON) |
| `generated_at` | TIMESTAMP | 生成時間 |

---

#### 5. embedding_models (保留)
**用途**: 記錄可用的 embedding 模型

```sql
CREATE TABLE embedding_models (
    id TEXT PRIMARY KEY,
    model_name TEXT UNIQUE NOT NULL,
    model_path TEXT,
    dimension INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**重要**: 此表在清除操作中被保留，不會被刪除。

---

### FAISS 索引結構

**儲存位置**: `./data/faiss_indices/skills/`

```
faiss_indices/
├── files/                    # File-based 索引（隔離）
│   ├── file_{timestamp}.index
│   ├── file_{timestamp}.metadata
│   └── ...
│
└── skills/                   # Skill-based 索引
    ├── skill_{skill_id}/
    │   ├── master.index      # 合併後的 FAISS 索引
    │   └── master.metadata   # 元資料 JSON
    │
    ├── skill_LLM/
    │   ├── master.index
    │   └── master.metadata
    │
    └── skill_law/
        ├── master.index
        └── master.metadata
```

**索引文件格式**:

- **\*.index**: FAISS 二進制索引文件，包含 1024-dimensional vectors
- **\*.metadata**: JSON 文件，包含 chunk metadata 映射

---

## API 參考文檔

### Base URL
```
http://localhost:8000/api/v1/skills
```

### 1. 獲取完整配置

**請求**:
```
GET /config
```

**回應**:
```json
{
    "config": {
        "version": "1.0",
        "skills": [...],
        "instant_attachments": [...],
        "settings": {...}
    },
    "config_path": "/path/to/skill_config.json",
    "rebuild_threshold": 5,
    "instant_count": 0,
    "needs_rebuild": false
}
```

---

### 2. 獲取 Skills 清單

**請求**:
```
GET /config/skills
```

**回應**:
```json
{
    "skills": [
        {
            "skill_name": "LLM",
            "description": "...",
            "category": "Technology",
            "enabled": true,
            "total_sources": 5,
            "enabled_sources": 5,
            "sources": [
                {
                    "path": "refData/rawdata/LLM/book1.pdf",
                    "enabled": true,
                    "description": "...",
                    "exists": true,
                    "filename": "book1.pdf"
                }
            ]
        }
    ]
}
```

---

### 3. 新增 Skill

**請求**:
```
POST /config/skills
Content-Type: application/json

{
    "skill_name": "Python",
    "description": "Python 編程基礎",
    "category": "Programming",
    "enabled": true,
    "sources": []
}
```

**回應**:
```json
{
    "message": "Skill 'Python' added successfully",
    "skill": {...}
}
```

**錯誤**:
- `400`: Skill 已存在
- `500`: 無法儲存配置

---

### 4. 新增 PDF 來源到 Skill

**請求**:
```
POST /config/skills/{skill_name}/sources
Content-Type: application/json

{
    "path": "refData/rawdata/Python/python_book.pdf",
    "enabled": true,
    "description": "Python 完整教程"
}
```

**回應**:
```json
{
    "message": "Source added to skill 'Python'",
    "source": {
        "path": "refData/rawdata/Python/python_book.pdf",
        "enabled": true,
        "description": "Python 完整教程"
    }
}
```

**錯誤**:
- `400`: PDF 檔案不存在或已存在
- `404`: Skill 不存在
- `500`: 無法儲存配置

---

### 5. 從 Skill 移除 PDF 來源

**請求**:
```
DELETE /config/skills/{skill_name}/sources
Content-Type: application/json

{
    "path": "refData/rawdata/Python/python_book.pdf"
}
```

**回應**:
```json
{
    "message": "Source removed from skill 'Python'"
}
```

**錯誤**:
- `404`: Skill 或來源不存在
- `500`: 無法儲存配置

---

### 6. 獲取臨時附件清單

**請求**:
```
GET /config/instant-attachments
```

**回應**:
```json
{
    "attachments": [
        {
            "skill_name": "LLM",
            "path": "refData/rawdata/LLM/temp.pdf",
            "description": "臨時文件",
            "added_at": "2025-11-27T10:30:00",
            "exists": true,
            "filename": "temp.pdf",
            "size_mb": 5.2
        }
    ],
    "count": 1,
    "threshold": 5,
    "needs_rebuild": false
}
```

---

### 7. 新增臨時附件

**請求**:
```
POST /config/instant-attachments
Content-Type: application/json

{
    "skill_name": "LLM",
    "path": "refData/rawdata/LLM/temp_doc.pdf",
    "description": "臨時添加的文件"
}
```

**回應**:
```json
{
    "message": "Instant attachment added",
    "attachment": {
        "skill_name": "LLM",
        "path": "refData/rawdata/LLM/temp_doc.pdf",
        "description": "臨時添加的文件",
        "added_at": "2025-11-27T10:35:00"
    },
    "count": 1,
    "threshold": 5,
    "needs_rebuild": false,
    "warning": null
}
```

**當達到閾值時**:
```json
{
    ...
    "needs_rebuild": true,
    "warning": "建議執行 rebuild 以避免資料碎片化"
}
```

**錯誤**:
- `400`: PDF 檔案不存在或已存在
- `500`: 無法儲存配置

---

### 8. 清除所有臨時附件

**請求**:
```
DELETE /config/instant-attachments
```

**回應**:
```json
{
    "message": "Cleared 3 instant attachments"
}
```

---

### 9. 觸發重建

**請求**:
```
POST /rebuild
Content-Type: application/json

{
    "skill_name": null,          // 可選: 只重建特定 skill
    "clean_first": true          // 是否先清除舊資料
}
```

**回應** (立即返回):
```json
{
    "message": "Rebuild started in background",
    "skill_filter": null,
    "clean_first": true,
    "status": "running"
}
```

**注意**: 重建在背景執行，避免 HTTP 超時。可用 `/rebuild/status` 檢查進度。

**錯誤**:
- `400`: 無效的請求參數
- `500`: 無法啟動重建

---

### 10. 檢查重建狀態

**請求**:
```
GET /rebuild/status
```

**回應**:
```json
{
    "log_exists": true,
    "last_modified": "2025-11-27T10:40:00.123456",
    "recent_logs": [
        "2025-11-27 10:40:00 - INFO - Starting rebuild...",
        "2025-11-27 10:40:05 - INFO - Processing skill: LLM",
        "...",
        "2025-11-27 10:45:00 - INFO - Rebuild completed successfully"
    ]
}
```

---

## 使用者手冊

### 場景 1: 初始設置

**目標**: 為新系統建立第一批 skills

**步驟**:

1. **編輯配置文件**:
   ```bash
   nano scripts/skill_data/skill_config.json
   ```

   編輯 `skills` 陣列，定義想要的 skills 和 PDF 來源。

2. **執行初始重建**:
   ```bash
   ./scripts/skill_data/rebuild_skills.sh --clean --force
   ```

   此命令會：
   - 清除舊資料（如有）
   - 根據配置重建所有 skills
   - 生成 embeddings
   - 建立索引

3. **驗證結果**:
   ```bash
   ./scripts/skill_data/test_workflow.sh
   ```

   應顯示 `✅ All tests passed!`

4. **訪問管理界面**:
   ```
   http://localhost:8000/skill/config
   ```

---

### 場景 2: 新增 PDF 到現有 Skill

**目標**: 為現有 skill 添加更多 PDF 來源

**方法 1: 編輯 JSON（推薦）**
```bash
# 編輯配置文件
nano scripts/skill_data/skill_config.json

# 在目標 skill 的 sources 陣列新增
{
    "path": "refData/rawdata/LLM/new_book.pdf",
    "enabled": true,
    "description": "新書籍"
}

# 執行重建
./scripts/skill_data/rebuild_skills.sh --force
```

**方法 2: 使用 API**
```bash
curl -X POST http://localhost:8000/api/v1/skills/config/skills/LLM/sources \
  -H "Content-Type: application/json" \
  -d '{
    "path": "refData/rawdata/LLM/new_book.pdf",
    "enabled": true,
    "description": "新書籍"
  }'
```

**方法 3: 使用 Web UI**
1. 訪問 http://localhost:8000/skill/config
2. 找到目標 Skill 卡片
3. 點擊「新增來源」按鈕
4. 輸入 PDF 路徑和描述
5. 點擊「新增」

---

### 場景 3: 臨時添加 PDF（不需重建）

**目標**: 快速添加臨時文件，無需完整重建

**使用方式**:

1. **通過 API**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/skills/config/instant-attachments \
     -H "Content-Type: application/json" \
     -d '{
       "skill_name": "LLM",
       "path": "refData/rawdata/LLM/temp_doc.pdf",
       "description": "臨時文件"
     }'
   ```

2. **通過 Web UI**:
   - 訪問 http://localhost:8000/skill/config
   - 切換到「臨時附件」頁籤
   - 點擊「新增附件」
   - 選擇 skill 和 PDF
   - 點擊「新增」

3. **監控重建狀態**:
   - 查看臨時附件計數
   - 當達到 `rebuild_threshold` (預設 5) 時，UI 會顯示警告
   - 點擊「執行重建」按鈕

4. **執行完整重建**:
   ```bash
   ./scripts/skill_data/rebuild_skills.sh --force
   ```

---

### 場景 4: 修改 Skill 配置

**目標**: 啟用/停用 PDF 或修改 skill 設定

**通過配置文件**:
```json
{
    "skill_name": "LLM",
    "enabled": true,              // 改為 false 可停用整個 skill
    "sources": [
        {
            "path": "...",
            "enabled": true        // 改為 false 可停用單個 PDF
        }
    ]
}
```

**執行重建後生效**:
```bash
./scripts/skill_data/rebuild_skills.sh --skill "LLM"
```

---

### 場景 5: 完全重建

**目標**: 清除所有舊資料，重新開始

**步驟**:
```bash
# 1. 清除舊資料（有備份）
./scripts/skill_data/clean_skill_tables.sh --force

# 2. 編輯配置（如需要）
nano scripts/skill_data/skill_config.json

# 3. 執行重建
./scripts/skill_data/rebuild_skills.sh --force

# 4. 驗證
./scripts/skill_data/test_workflow.sh
```

**結果**:
- ✅ 所有舊 skill 資料被清除
- ✅ 新資料根據當前配置重建
- ✅ Embedding 重新生成
- ✅ FAISS 索引重新建立

---

### 場景 6: 監控重建進度

**目標**: 實時查看重建狀態

**方法 1: Web UI**
1. 訪問 http://localhost:8000/skill/config
2. 點擊「重建」頁籤
3. 查看即時日誌

**方法 2: API**
```bash
curl http://localhost:8000/api/v1/skills/rebuild/status
```

**方法 3: 檢查日誌文件**
```bash
tail -f logs/rebuild_skills.log
```

---

## 集成指南

### 與現有 File-Based 系統的關係

```
DocAI 系統
├── File-Based 模式 (原有)
│   ├── 單個 PDF 上傳
│   ├── /api/v1/chat 接口
│   └── /data/docai.db (SQLite)
│
└── Skill-Based 模式 (新增)
    ├── 多 Skill 管理
    ├── /api/v1/skills/* 接口
    └── /data/skill_metadata.db (SQLite)
```

**重要**: 兩個系統完全隔離，使用不同的資料庫和索引。

---

### 在前端集成

**在 skill_main.html 中**:
```html
<!-- 添加管理連結 -->
<a href="/skill/config" class="nav-link">
    <i class="fa-solid fa-cog"></i>
    <span>Skill 配置管理</span>
</a>

<!-- 或在 JavaScript 中 -->
<script>
// 切換到配置頁面
function goToSkillConfig() {
    window.location.href = '/skill/config';
}
</script>
```

---

### 在外部應用集成

**Python 範例**:
```python
import requests
import json

BASE_URL = "http://localhost:8000/api/v1/skills"

# 獲取 skills 清單
response = requests.get(f"{BASE_URL}/config/skills")
skills = response.json()

# 新增臨時附件
attachment_data = {
    "skill_name": "LLM",
    "path": "refData/rawdata/LLM/new.pdf",
    "description": "新文件"
}
response = requests.post(
    f"{BASE_URL}/config/instant-attachments",
    json=attachment_data
)

# 觸發重建
rebuild_data = {
    "skill_name": None,
    "clean_first": False
}
response = requests.post(
    f"{BASE_URL}/rebuild",
    json=rebuild_data
)
print(response.json())
```

**JavaScript 範例**:
```javascript
// 獲取 skills
fetch('/api/v1/skills/config/skills')
    .then(r => r.json())
    .then(data => console.log(data.skills));

// 新增臨時附件
fetch('/api/v1/skills/config/instant-attachments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        skill_name: 'LLM',
        path: 'refData/rawdata/LLM/new.pdf',
        description: '新文件'
    })
})
.then(r => r.json())
.then(data => console.log(data));

// 觸發重建
fetch('/api/v1/skills/rebuild', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        skill_name: null,
        clean_first: false
    })
})
.then(r => r.json())
.then(data => console.log(data));
```

**cURL 範例**:
```bash
# 獲取配置
curl http://localhost:8000/api/v1/skills/config | jq

# 新增 skill
curl -X POST http://localhost:8000/api/v1/skills/config/skills \
  -H "Content-Type: application/json" \
  -d '{"skill_name":"Python","description":"Python編程"}'

# 觸發重建
curl -X POST http://localhost:8000/api/v1/skills/rebuild \
  -H "Content-Type: application/json" \
  -d '{"skill_name":null,"clean_first":true}'

# 檢查重建狀態
curl http://localhost:8000/api/v1/skills/rebuild/status | jq
```

---

## 故障排除

### 問題 1: 重建失敗 - PyPDF2 錯誤

**症狀**:
```
Error: PyPDF2.PdfReadError: File has not been initialized
```

**原因**: PDF 文件損壞或格式不支援

**解決**:
1. 驗證 PDF 完整性
2. 在配置文件中停用該 PDF：`"enabled": false`
3. 重新執行重建

---

### 問題 2: 重建超時

**症狀**:
```
HTTP 504 Gateway Timeout
```

**原因**: PDF 過大或系統資源不足

**解決**:
1. 減小 `chunk_size` (在 skill_config.json)
2. 分批重建特定 skills：`--skill "LLM"`
3. 檢查磁碟空間和內存

---

### 問題 3: 資料庫被鎖定

**症狀**:
```
sqlite3.OperationalError: database is locked
```

**原因**: 另一個進程正在訪問資料庫

**解決**:
```bash
# 檢查進程
ps aux | grep python

# 停止伺服器
./stop_system.sh

# 檢查數據庫
sqlite3 data/skill_metadata.db ".tables"

# 重啟伺服器
./start_system.sh
```

---

### 問題 4: API 返回 404

**症狀**:
```
404 Not Found - /api/v1/skills/config
```

**原因**: 伺服器未重啟，新端點未載入

**解決**:
```bash
# 重啟伺服器
./stop_system.sh && ./start_system.sh
```

---

### 問題 5: 配置文件無效

**症狀**:
```
json.JSONDecodeError: Expecting value
```

**原因**: skill_config.json JSON 語法錯誤

**解決**:
```bash
# 驗證 JSON
python3 -m json.tool scripts/skill_data/skill_config.json

# 使用線上工具檢查
# https://jsonlint.com/

# 修復後重新驗證
python3 -c "import json; json.load(open('scripts/skill_data/skill_config.json'))"
```

---

## 附錄: 完整檢查清單

### 安裝完成後

- [ ] 所有腳本文件存在且可執行
- [ ] skill_config.json 有效且包含至少一個 skill
- [ ] 資料庫 skill_metadata.db 已建立
- [ ] FAISS 索引目錄已建立
- [ ] 伺服器已重啟
- [ ] 測試全部通過 (`./test_workflow.sh`)

### 執行重建後

- [ ] 資料庫中有 skill_metadata 記錄
- [ ] FAISS 索引已生成
- [ ] 日誌文件無錯誤
- [ ] Web UI 可訪問且顯示正確資料
- [ ] API endpoints 可用

### 日常維護

- [ ] 定期備份 skill_metadata.db
- [ ] 監控重建日誌文件大小
- [ ] 檢查磁碟空間（FAISS 索引較大）
- [ ] 驗證 PDF 來源路徑有效

---

## 版本歷史

| 版本 | 日期 | 更新 |
|------|------|------|
| 1.0 | 2025-11-27 | 初始版本 - 完整實作並通過測試 |

---

## 相關文檔

- [Skill 架構實作報告](skill_architecture_implementation_20251125.md)
- [系統診斷報告](系統診斷報告_20251103.md)
- [RAG Prompt 最佳實踐](RAG_prompt_best_practices_20251103.md)

---

*此文檔由 Claude Code 自動生成*
*最後更新: 2025-11-27*
*SuperClaude Framework v2.0.1*
