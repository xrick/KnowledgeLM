# DocAI System Architecture - 系統架構圖

## 概述

本文檔詳細描述 DocAI 系統的架構設計，包含各模組分工、技術堆疊、資料流向及部署架構。

---

## 整體架構圖

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    DocAI System                                      │
│                          Skill-Based RAG Architecture v2.0                          │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           CLIENT TIER                                        │   │
│  │  ┌───────────────────────────────────────────────────────────────────────┐  │   │
│  │  │                        Web Browser                                     │  │   │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │   │
│  │  │  │ skill_main  │  │skill_config │  │   index     │  │ skill_demo  │  │  │   │
│  │  │  │  .html      │  │   .html     │  │   .html     │  │   .html     │  │  │   │
│  │  │  │             │  │             │  │             │  │             │  │  │   │
│  │  │  │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │  │  │   │
│  │  │  │ │Chat UI  │ │  │ │Config UI│ │  │ │File Mode│ │  │ │Demo UI  │ │  │  │   │
│  │  │  │ │Skill    │ │  │ │Upload   │ │  │ │Legacy   │ │  │ │Testing  │ │  │  │   │
│  │  │  │ │Tree     │ │  │ │Manage   │ │  │ │         │ │  │ │         │ │  │  │   │
│  │  │  │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │  │  │   │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │  │   │
│  │  │                                                                       │  │   │
│  │  │  ┌─────────────────────────────────────────────────────────────────┐  │  │   │
│  │  │  │                    JavaScript Libraries                         │  │  │   │
│  │  │  │  ├── progressive_markdown_renderer.js  (SSE 串流渲染)           │  │  │   │
│  │  │  │  ├── marked.min.js                     (Markdown 解析)          │  │  │   │
│  │  │  │  └── highlight.min.js                  (程式碼高亮)             │  │  │   │
│  │  │  └─────────────────────────────────────────────────────────────────┘  │  │   │
│  │  └───────────────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                            │
│                                        │ HTTP/SSE                                   │
│                                        ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           SERVER TIER                                        │   │
│  │  ┌───────────────────────────────────────────────────────────────────────┐  │   │
│  │  │                        FastAPI Application                             │  │   │
│  │  │  ┌─────────────────────────────────────────────────────────────────┐  │  │   │
│  │  │  │                     API Router (v1)                              │  │  │   │
│  │  │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │  │  │   │
│  │  │  │  │ /skills/*    │  │   /chat/*    │  │  /upload/*   │           │  │  │   │
│  │  │  │  │              │  │              │  │              │           │  │  │   │
│  │  │  │  │ • demo/query │  │ • (legacy)   │  │ • file       │           │  │  │   │
│  │  │  │  │ • stream     │  │              │  │              │           │  │  │   │
│  │  │  │  │ • heads      │  │              │  │              │           │  │  │   │
│  │  │  │  │ • tree       │  │              │  │              │           │  │  │   │
│  │  │  │  │ • upload     │  │              │  │              │           │  │  │   │
│  │  │  │  └──────────────┘  └──────────────┘  └──────────────┘           │  │  │   │
│  │  │  └─────────────────────────────────────────────────────────────────┘  │  │   │
│  │  │                                   │                                    │  │   │
│  │  │                                   ▼                                    │  │   │
│  │  │  ┌─────────────────────────────────────────────────────────────────┐  │  │   │
│  │  │  │                     Service Layer                                │  │  │   │
│  │  │  │  ┌──────────────────────────────────────────────────────────┐   │  │  │   │
│  │  │  │  │               SkillServices Module                        │   │  │  │   │
│  │  │  │  │  ┌─────────────────┐  ┌─────────────────┐                │   │  │  │   │
│  │  │  │  │  │ skill_retrieval │  │ skill_ingestion │                │   │  │  │   │
│  │  │  │  │  │ _service.py     │  │ _service.py     │                │   │  │  │   │
│  │  │  │  │  │ ┌─────────────┐ │  │ ┌─────────────┐ │                │   │  │  │   │
│  │  │  │  │  │ │retrieve_    │ │  │ │ingest_pdf  │ │                │   │  │  │   │
│  │  │  │  │  │ │context()    │ │  │ │extract_    │ │                │   │  │  │   │
│  │  │  │  │  │ │add_content()│ │  │ │text()      │ │                │   │  │  │   │
│  │  │  │  │  │ └─────────────┘ │  │ └─────────────┘ │                │   │  │  │   │
│  │  │  │  │  └─────────────────┘  └─────────────────┘                │   │  │  │   │
│  │  │  │  │  ┌────────────────────────────────────────────────────┐  │   │  │  │   │
│  │  │  │  │  │         progressive_skill_streaming/               │  │   │  │  │   │
│  │  │  │  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │  │   │  │  │   │
│  │  │  │  │  │  │Phase 1  │ │Phase 2  │ │Phase 3  │ │Phase 4  │  │  │   │  │  │   │
│  │  │  │  │  │  │Query    │→│Retrieval│→│Context  │→│Response │  │  │   │  │  │   │
│  │  │  │  │  │  │Underst. │ │(FAISS)  │ │Assembly │ │Generate │  │  │   │  │  │   │
│  │  │  │  │  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘  │  │   │  │  │   │
│  │  │  │  │  │        └──────────► Phase 5: Postprocessing       │  │   │  │  │   │
│  │  │  │  │  └────────────────────────────────────────────────────┘  │   │  │  │   │
│  │  │  │  └──────────────────────────────────────────────────────────┘   │  │  │   │
│  │  │  │  ┌──────────────────────────────────────────────────────────┐   │  │  │   │
│  │  │  │  │                 Core Services                             │   │  │  │   │
│  │  │  │  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐ │   │  │  │   │
│  │  │  │  │  │prompt_      │ │query_       │ │chunking_strategies │ │   │  │  │   │
│  │  │  │  │  │service.py   │ │enhancement  │ │.py                  │ │   │  │  │   │
│  │  │  │  │  │             │ │_service.py  │ │                     │ │   │  │  │   │
│  │  │  │  │  │build_rag_   │ │expand_      │ │page_based_chunking  │ │   │  │  │   │
│  │  │  │  │  │prompt()     │ │query()      │ │recursive_chunking  │ │   │  │  │   │
│  │  │  │  │  └─────────────┘ └─────────────┘ └─────────────────────┘ │   │  │  │   │
│  │  │  │  └──────────────────────────────────────────────────────────┘   │  │  │   │
│  │  │  └─────────────────────────────────────────────────────────────────┘  │  │   │
│  │  │                                   │                                    │  │   │
│  │  │                                   ▼                                    │  │   │
│  │  │  ┌─────────────────────────────────────────────────────────────────┐  │  │   │
│  │  │  │                    Provider Layer                                │  │  │   │
│  │  │  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐       │  │  │   │
│  │  │  │  │  Skill    │ │  Vector   │ │   LLM     │ │ Embedding │       │  │  │   │
│  │  │  │  │ Metadata  │ │  Store    │ │ Provider  │ │ Provider  │       │  │  │   │
│  │  │  │  │ Provider  │ │ Provider  │ │           │ │ (BGE-M3)  │       │  │  │   │
│  │  │  │  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘       │  │  │   │
│  │  │  │        │             │             │             │              │  │  │   │
│  │  │  │        │ aiosqlite   │ FAISS       │ httpx       │ sentence-   │  │  │   │
│  │  │  │        │             │ LangChain   │             │ transformers│  │  │   │
│  │  │  │        ▼             ▼             ▼             ▼              │  │  │   │
│  │  │  └─────────────────────────────────────────────────────────────────┘  │  │   │
│  │  └───────────────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                            │
│                                        ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          DATA TIER                                           │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐ │   │
│  │  │    SQLite     │  │    FAISS      │  │  File System  │  │    Ollama     │ │   │
│  │  │               │  │               │  │               │  │               │ │   │
│  │  │ skill_meta    │  │ /skills/      │  │ /uploadfiles/ │  │ gpt-oss:20b   │ │   │
│  │  │ data.db       │  │   index.faiss │  │   /pdf/       │  │               │ │   │
│  │  │               │  │   index.pkl   │  │               │  │ localhost:    │ │   │
│  │  │ Tables:       │  │               │  │ ├─ doc1.pdf   │  │   11434       │ │   │
│  │  │ • skill_heads │  │ /files/       │  │ ├─ doc2.pdf   │  │               │ │   │
│  │  │ • skill_meta  │  │ (legacy)      │  │ └─ ...        │  │               │ │   │
│  │  │ • skill_doc   │  │               │  │               │  │               │ │   │
│  │  │ • skill_chunk │  │               │  │               │  │               │ │   │
│  │  │ • proc_jobs   │  │               │  │               │  │               │ │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘  └───────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 技術堆疊詳細說明

### Backend Stack

| 層級 | 技術 | 版本 | 用途 |
|------|------|------|------|
| **Web Framework** | FastAPI | 0.104+ | 非同步 API 框架 |
| **ASGI Server** | Uvicorn | 0.24+ | 高效能 ASGI 伺服器 |
| **Async Runtime** | asyncio | Python 3.11+ | 非同步 I/O |
| **HTTP Client** | httpx | 0.25+ | 非同步 HTTP 請求 |
| **SSE** | sse-starlette | 1.6+ | Server-Sent Events |

### AI/ML Stack

| 層級 | 技術 | 用途 |
|------|------|------|
| **LLM Backend** | Ollama | 本地 LLM 推理引擎 |
| **LLM Model** | gpt-oss:20b | 主要語言模型 |
| **Embedding Model** | BAAI/BGE-M3 | 多語言向量嵌入 (1024-dim) |
| **Vector Framework** | LangChain | 向量存儲抽象層 |
| **Vector Index** | FAISS | Facebook AI 相似度搜尋 |

### Data Stack

| 層級 | 技術 | 用途 |
|------|------|------|
| **Relational DB** | SQLite | 元資料儲存 |
| **Async DB Driver** | aiosqlite | 非同步 SQLite 存取 |
| **Vector Storage** | FAISS | 向量索引持久化 |
| **Cache** | Redis (optional) | 查詢快取 |

### Frontend Stack

| 層級 | 技術 | 用途 |
|------|------|------|
| **Template** | Jinja2 | HTML 模板渲染 |
| **JavaScript** | Vanilla ES6+ | 無框架前端邏輯 |
| **Markdown** | marked.js | Markdown 解析 |
| **Code Highlight** | highlight.js | 程式碼語法高亮 |
| **CSS** | Custom Variables | 主題系統（深色/淺色）|

### DevOps Stack

| 層級 | 技術 | 用途 |
|------|------|------|
| **Process Manager** | systemd | 服務管理 |
| **Startup Script** | start_system.sh | 系統啟動腳本 |
| **Logging** | Python logging | 結構化日誌 |

---

## 模組詳細架構

### 1. API 模組 (`app/api/v1/endpoints/`)

```
endpoints/
├── skills.py          # 主要 API (3500+ lines)
│   ├── Skill CRUD     # 建立/讀取/更新/刪除技能
│   ├── Query API      # 查詢端點
│   ├── Stream API     # SSE 串流端點
│   ├── Upload API     # 檔案上傳處理
│   └── Tree API       # 技能樹結構
│
├── chat.py            # Legacy 檔案模式 API
│   └── (保留相容性)
│
└── upload.py          # 通用上傳 API
    └── (檔案驗證、儲存)
```

### 2. Services 模組

```
Services/
├── prompt_service.py           # RAG Prompt 工程
│   ├── SYSTEM_PROMPT_TEMPLATE  # 系統提示詞模板
│   ├── build_rag_prompt()      # 組裝 RAG Prompt
│   └── detect_summary_intent() # 摘要意圖偵測
│
├── query_enhancement_service.py  # 查詢增強
│   ├── expand_query()          # 查詢擴展
│   └── generate_subquestions() # 子問題生成
│
├── chunking_strategies.py      # 分塊策略
│   ├── page_based_chunking()   # 基於頁面
│   ├── recursive_chunking()    # 遞迴分割
│   └── hierarchical_chunking() # 階層式分割
│
└── retrieval_service.py        # Legacy 檢索服務
```

### 3. SkillServices 模組

```
SkillServices/
├── skill_retrieval_service.py    # 技能檢索
│   ├── retrieve_context()        # 向量檢索
│   ├── add_content()             # 新增內容
│   └── delete_content()          # 刪除內容
│
├── skill_ingestion_service.py    # 技能攝取
│   ├── process_pdf()             # PDF 處理
│   └── generate_embeddings()     # 嵌入生成
│
├── progressive_skill_streaming/   # OPMP 串流
│   ├── progressive_streaming.py   # 主協調器
│   ├── phase1_skill_query_understanding.py
│   ├── phase2_skill_retrieval.py
│   ├── phase3_context_assembly.py
│   ├── phase4_response_generation.py
│   └── phase5_postprocessing.py
│
├── index_integrity.py            # 索引完整性
│   └── verify_index()            # 驗證 FAISS 索引
│
└── base_retrieval.py             # 抽象基類
    └── AbstractRetrievalService
```

### 4. Providers 模組

```
Providers/
├── skill_metadata_provider/
│   └── client.py                 # SQLite 操作
│       ├── create_skill()
│       ├── get_skill()
│       ├── list_skills()
│       ├── create_skill_head()
│       ├── get_skill_tree()
│       └── update_processing_status()
│
├── vector_store_provider/
│   └── client.py                 # FAISS 操作
│       ├── create_store_from_texts()
│       ├── similarity_search()
│       ├── similarity_search_with_score()
│       └── delete_store()
│
├── llm_provider/
│   └── client.py                 # LLM API
│       ├── get_chat_completion()
│       └── stream_chat_completion()
│
├── bge_embedding_provider.py     # BGE-M3 嵌入
│   ├── embed_query()
│   └── embed_documents()
│
└── cache_provider/
    └── client.py                 # Redis 快取
```

---

## 資料流架構

### 上傳流程（Data Ingestion）

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────>│  skills.py  │────>│  Ingestion  │────>│   PyPDF2    │
│  (FormData) │     │  endpoint   │     │   Service   │     │  (Extract)  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                                                                   │ Text
                                                                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   SQLite    │<────│  Metadata   │<────│    FAISS    │<────│   BGE-M3    │
│  (Metadata) │     │  Provider   │     │  (Vectors)  │     │ (Embedding) │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘

SSE Progress Events:
[5%] 開始處理
[10%] 文字提取中
[40%] 向量嵌入中
[80%] FAISS 儲存中
[100%] 完成
```

### 查詢流程（Query Processing）

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────>│  skills.py  │────>│  Retrieval  │────>│   BGE-M3    │
│   (Query)   │     │  endpoint   │     │   Service   │     │  (Query→Vec)│
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                                                                   │ Query Vector
                                                                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │<────│   Prompt    │<────│    LLM      │<────│    FAISS    │
│  (Response) │     │   Service   │     │  (Ollama)   │     │  (Search)   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

---

## 部署架構

### 單機部署（目前）

```
┌─────────────────────────────────────────────────────────────┐
│                      Host Machine                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                   DocAI Application                    │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │  │
│  │  │   FastAPI   │  │   SQLite    │  │    FAISS    │   │  │
│  │  │   :8000     │  │   ./data/   │  │   ./data/   │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                     Ollama LLM                         │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  ollama serve                                    │  │  │
│  │  │  :11434                                          │  │  │
│  │  │  Model: gpt-oss:20b                              │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 目錄結構

```
DocAI/
├── app/                          # 應用程式碼
│   ├── api/v1/endpoints/         # API 端點
│   ├── Services/                 # 核心服務
│   ├── SkillServices/            # 技能服務
│   ├── Providers/                # 資料提供者
│   ├── core/                     # 核心配置
│   └── models/                   # 資料模型
│
├── data/                         # 資料儲存
│   ├── skill_metadata.db         # SQLite 資料庫
│   └── faiss_indices/            # FAISS 索引
│       ├── files/                # (Legacy)
│       └── skills/               # 技能索引
│
├── template/                     # HTML 模板
│   ├── skill_main.html           # 主聊天介面
│   ├── skill_config.html         # 配置介面
│   └── ...
│
├── static/                       # 靜態資源
│   ├── js/                       # JavaScript
│   ├── css/                      # 樣式表
│   └── i18n/                     # 國際化
│
├── uploadfiles/                  # 上傳檔案
│   └── pdf/                      # PDF 儲存
│
├── logs/                         # 日誌
│   └── server.log
│
├── scripts/                      # 腳本
│   └── skill_data/               # 技能資料腳本
│
└── claudedocs/                   # 技術文檔
```

---

## 擴展架構（未來）

### 分散式部署

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Load Balancer (Nginx)                        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
    ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
    │   FastAPI #1  │       │   FastAPI #2  │       │   FastAPI #3  │
    │   (Stateless) │       │   (Stateless) │       │   (Stateless) │
    └───────────────┘       └───────────────┘       └───────────────┘
            │                       │                       │
            └───────────────────────┼───────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
    ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
    │  PostgreSQL   │       │    Milvus     │       │     Redis     │
    │  (Metadata)   │       │   (Vectors)   │       │    (Cache)    │
    └───────────────┘       └───────────────┘       └───────────────┘
```

---

## 安全架構

### 現行措施

| 層級 | 措施 |
|------|------|
| **API** | CORS 白名單 |
| **Database** | SQLite timeout 防鎖定 |
| **File Upload** | 副檔名白名單、大小限制 |
| **FAISS** | `allow_dangerous_deserialization=True` (受信任索引) |

### 待改進

- [ ] JWT 身份驗證
- [ ] API Rate Limiting
- [ ] 輸入驗證強化
- [ ] 加密靜態資料

---

*文件版本：2025-12-16*
*作者：Claude (SuperClaude)*
