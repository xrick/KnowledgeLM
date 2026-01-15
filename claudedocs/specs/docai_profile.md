# DocAI System Profile - 系統鳥瞰圖

## 系統定位

**DocAI** 是一個基於 **Skill-Based Architecture** 的企業級 RAG（Retrieval-Augmented Generation）系統，專為 PDF 文檔的智能問答而設計。

---

## 系統鳥瞰圖

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 DocAI System                                     │
│                        Skill-Based RAG Architecture                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ╔═══════════════════════════════════════════════════════════════════════════╗ │
│  ║                         Presentation Layer                                 ║ │
│  ║  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                        ║ │
│  ║  │ skill_main  │  │skill_config │  │   index     │                        ║ │
│  ║  │   (Chat)    │  │  (Manage)   │  │  (Legacy)   │                        ║ │
│  ║  └─────────────┘  └─────────────┘  └─────────────┘                        ║ │
│  ╚═══════════════════════════════════════════════════════════════════════════╝ │
│                                      │                                          │
│                                      ▼                                          │
│  ╔═══════════════════════════════════════════════════════════════════════════╗ │
│  ║                            API Layer (FastAPI)                             ║ │
│  ║  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                        ║ │
│  ║  │  /skills/*  │  │   /chat/*   │  │  /upload/*  │                        ║ │
│  ║  │ (Primary)   │  │  (Legacy)   │  │  (Shared)   │                        ║ │
│  ║  └─────────────┘  └─────────────┘  └─────────────┘                        ║ │
│  ╚═══════════════════════════════════════════════════════════════════════════╝ │
│                                      │                                          │
│                                      ▼                                          │
│  ╔═══════════════════════════════════════════════════════════════════════════╗ │
│  ║                          Service Layer                                     ║ │
│  ║  ┌─────────────────────────────────────────────────────────────────────┐  ║ │
│  ║  │                    SkillServices (Primary)                          │  ║ │
│  ║  │  ┌──────────────┐ ┌──────────────┐ ┌────────────────────────────┐  │  ║ │
│  ║  │  │ Retrieval    │ │ Ingestion    │ │ Progressive Streaming      │  │  ║ │
│  ║  │  │ Service      │ │ Service      │ │ (OPMP 5-Phase)             │  │  ║ │
│  ║  │  └──────────────┘ └──────────────┘ └────────────────────────────┘  │  ║ │
│  ║  └─────────────────────────────────────────────────────────────────────┘  ║ │
│  ║  ┌─────────────────────────────────────────────────────────────────────┐  ║ │
│  ║  │                    Core Services (Shared)                           │  ║ │
│  ║  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │  ║ │
│  ║  │  │   Prompt     │ │   Query      │ │  Chunking    │                 │  ║ │
│  ║  │  │   Service    │ │ Enhancement  │ │ Strategies   │                 │  ║ │
│  ║  │  └──────────────┘ └──────────────┘ └──────────────┘                 │  ║ │
│  ║  └─────────────────────────────────────────────────────────────────────┘  ║ │
│  ╚═══════════════════════════════════════════════════════════════════════════╝ │
│                                      │                                          │
│                                      ▼                                          │
│  ╔═══════════════════════════════════════════════════════════════════════════╗ │
│  ║                          Provider Layer                                    ║ │
│  ║  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        ║ │
│  ║  │ Skill    │ │ Vector   │ │   LLM    │ │Embedding │ │  Cache   │        ║ │
│  ║  │ Metadata │ │  Store   │ │ Provider │ │ Provider │ │ Provider │        ║ │
│  ║  │(SQLite)  │ │ (FAISS)  │ │ (Ollama) │ │ (BGE-M3) │ │ (Redis)  │        ║ │
│  ║  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘        ║ │
│  ╚═══════════════════════════════════════════════════════════════════════════╝ │
│                                      │                                          │
│                                      ▼                                          │
│  ╔═══════════════════════════════════════════════════════════════════════════╗ │
│  ║                         Storage Layer                                      ║ │
│  ║  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            ║ │
│  ║  │   SQLite        │  │     FAISS       │  │   File System   │            ║ │
│  ║  │ skill_metadata  │  │ Vector Indices  │  │  PDF Storage    │            ║ │
│  ║  │    .db          │  │   /skills/      │  │  /uploadfiles/  │            ║ │
│  ║  └─────────────────┘  └─────────────────┘  └─────────────────┘            ║ │
│  ╚═══════════════════════════════════════════════════════════════════════════╝ │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 各層職責說明

### 1. Presentation Layer（展示層）

| 組件 | 檔案 | 職責 |
|------|------|------|
| **skill_main** | `template/skill_main.html` | 主聊天介面，包含技能樹、對話框、查詢輸入 |
| **skill_config** | `template/skill_config.html` | 技能管理介面，PDF 上傳、技能重建、刪除 |
| **index** | `template/index.html` | Legacy 檔案模式介面（備用） |

**特色功能**：
- 三層技能樹（Head → Document → Chunks）
- Progressive Markdown 渲染（SSE 串流）
- 多選查詢支援
- 深色/淺色主題切換

---

### 2. API Layer（API 層）

| 路由 | 檔案 | 職責 |
|------|------|------|
| `/api/v1/skills/*` | `skills.py` | **主要**：技能 CRUD、查詢、上傳、串流 |
| `/api/v1/chat/*` | `chat.py` | Legacy：檔案模式聊天 |
| `/api/v1/upload/*` | `upload.py` | 共用：檔案上傳處理 |

**主要端點**：

```python
# Skill 管理
POST   /skills/create              # 建立新技能
GET    /skills/demo                # 獲取技能列表
GET    /skills/tree                # 獲取技能樹結構
GET    /skills/heads               # 獲取技能群組
DELETE /skills/{skill_id}          # 刪除技能

# 查詢
POST   /skills/demo/query          # 傳統 JSON 查詢
POST   /skills/{id}/progressive-stream  # SSE 串流查詢

# 上傳
POST   /skills/upload-source-streaming  # SSE 進度上傳
```

---

### 3. Service Layer（服務層）

#### SkillServices（技能專用服務）

| 服務 | 檔案 | 職責 |
|------|------|------|
| **SkillRetrievalService** | `skill_retrieval_service.py` | 向量檢索、相似度搜尋 |
| **SkillIngestionService** | `skill_ingestion_service.py` | PDF 處理、嵌入生成 |
| **ProgressiveStreaming** | `progressive_streaming.py` | 5 階段 SSE 串流協調 |
| **IndexIntegrity** | `index_integrity.py` | FAISS 索引完整性檢查 |

#### Core Services（核心共用服務）

| 服務 | 檔案 | 職責 |
|------|------|------|
| **PromptService** | `prompt_service.py` | RAG Prompt 模板與組裝 |
| **QueryEnhancement** | `query_enhancement_service.py` | 查詢擴展與優化 |
| **ChunkingStrategies** | `chunking_strategies.py` | 文本分塊策略 |

---

### 4. Provider Layer（提供者層）

| Provider | 檔案 | 後端 | 職責 |
|----------|------|------|------|
| **SkillMetadataProvider** | `skill_metadata_provider/client.py` | SQLite | 技能元資料管理 |
| **VectorStoreProvider** | `vector_store_provider/client.py` | FAISS | 向量儲存與檢索 |
| **LLMProviderClient** | `llm_provider/client.py` | Ollama | LLM API 呼叫 |
| **BGEEmbeddingProvider** | `bge_embedding_provider.py` | Local | 向量嵌入生成 |
| **CacheProvider** | `cache_provider/client.py` | Redis | 快取管理 |

---

### 5. Storage Layer（儲存層）

```
data/
├── skill_metadata.db           # SQLite 主資料庫
│   ├── skill_heads             # 技能群組定義
│   ├── skill_metadata          # 技能詳細資訊
│   ├── skill_document_mapping  # 技能-文檔映射
│   ├── skill_chunk_metadata    # 分塊元資料
│   └── processing_jobs         # 處理任務狀態
│
├── faiss_indices/
│   ├── files/                  # Legacy 檔案索引
│   └── skills/                 # 技能向量索引
│       ├── skill_xxx/
│       │   ├── index.faiss     # 向量索引
│       │   └── index.pkl       # 元資料
│       └── skill_yyy/
│
└── uploadfiles/
    └── pdf/                    # PDF 原始檔案
```

---

## 模組分工矩陣

```
┌────────────────────┬─────────┬─────────┬─────────┬─────────┬─────────┐
│      功能 \ 模組   │ skills  │ Services│Providers│ Storage │Frontend │
├────────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ PDF 上傳           │    ●    │    ○    │    ○    │    ●    │    ●    │
│ 文字提取           │    ●    │    ●    │         │         │         │
│ 向量嵌入           │         │    ●    │    ●    │    ●    │         │
│ 元資料管理         │    ●    │         │    ●    │    ●    │         │
│ 向量檢索           │    ●    │    ●    │    ●    │    ●    │         │
│ LLM 生成           │    ●    │    ●    │    ●    │         │         │
│ Prompt 組裝        │    ○    │    ●    │         │         │         │
│ SSE 串流           │    ●    │    ●    │         │         │    ●    │
│ 技能樹顯示         │    ●    │         │    ○    │    ○    │    ●    │
│ 聊天介面           │         │         │         │         │    ●    │
└────────────────────┴─────────┴─────────┴─────────┴─────────┴─────────┘

● 主要負責  ○ 參與協作
```

---

## 資料流向

### 1. PDF 上傳流程

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Browser │───>│ skills.py │───>│ Ingestion│───>│ BGE-M3   │───>│  FAISS   │
│         │    │ endpoint  │    │ Service  │    │ Embedding│    │  Store   │
└─────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │              │               │               │               │
     │              │               │               │               │
     ▼              ▼               ▼               ▼               ▼
 File Upload   Save PDF &    Extract Text    Generate         Store
 (FormData)    Create Skill  (PyPDF2)        Vectors          Index
                Metadata                     (1024-dim)
```

### 2. 查詢流程

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Browser │───>│ skills.py │───>│ Retrieval│───>│  FAISS   │───>│   LLM    │
│         │    │ endpoint  │    │ Service  │    │  Search  │    │ Generate │
└─────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │              │               │               │               │
     │              │               │               │               │
     ▼              ▼               ▼               ▼               ▼
 User Query   Validate &     Generate          Similarity     RAG Response
 + Skills     Expand IDs     Query Vector      Search         + Citations
```

---

## 技術堆疊摘要

| 類別 | 技術 |
|------|------|
| **Web Framework** | FastAPI + Uvicorn |
| **Template Engine** | Jinja2 |
| **Vector Database** | FAISS (LangChain) |
| **Relational DB** | SQLite (aiosqlite) |
| **Embedding Model** | BAAI/BGE-M3 (1024-dim) |
| **LLM Backend** | Ollama (OpenAI-compatible API) |
| **Cache** | Redis (optional) |
| **PDF Processing** | PyPDF2 |
| **Frontend** | Vanilla JS + CSS |

---

## 設計原則

### 1. 完全隔離

Skill-Based 系統與 File-Based 系統完全隔離：
- 分離的資料庫檔案
- 分離的 FAISS 索引目錄
- 分離的 API 路由

### 2. Single Source of Truth

`skill_heads` 表作為技能定義的唯一真相來源，取代了舊的 JSON 配置檔。

### 3. 漸進式串流

OPMP（Optimistic Progressive Markdown Parsing）提供 5 階段漸進式回應，改善使用者體驗。

### 4. 容錯設計

- 資料庫連線使用 timeout 防止鎖定
- 處理任務支援斷點續傳
- 完整性檢查確保索引一致性

---

*文件版本：2025-12-16*
*作者：Claude (SuperClaude)*
