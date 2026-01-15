# DocAI RAG 系統架構全面分析

> **文件日期**: 2025-12-03
> **系統版本**: Dual Architecture (File-Based + Skill-Based)
> **分析範圍**: 完整資料流、組件關係、儲存架構、3-Level Tree 結構

---

## 📋 目錄

1. [系統概覽與核心理念](#1-系統概覽與核心理念)
2. [完整系統架構圖](#2-完整系統架構圖)
3. [資料流程詳解](#3-資料流程詳解)
4. [組件關係與互動](#4-組件關係與互動)
5. [資料儲存架構](#5-資料儲存架構)
6. [3-Level Tree 架構](#6-3-level-tree-架構)
7. [API 架構與端點映射](#7-api-架構與端點映射)
8. [OPMP 五階段 RAG Pipeline](#8-opmp-五階段-rag-pipeline)
9. [技術棧與依賴](#9-技術棧與依賴)
10. [系統隔離設計](#10-系統隔離設計)

---

## 1. 系統概覽與核心理念

### 1.1 系統 Profile

**DocAI** 是一個雙軌 RAG（Retrieval-Augmented Generation）系統，支援兩種完全隔離的使用模式：

| 屬性 | 描述 |
|------|------|
| **系統類型** | Dual-Architecture RAG System |
| **核心問題** | 解決大量 PDF 文件的智能檢索與問答 |
| **技術棧** | FastAPI + FAISS + SQLite + BGE-M3 + Gemini/GPT |
| **部署模式** | Monolithic Application (計劃 Microservices) |
| **資料規模** | 支援數百個 PDFs，數十萬 chunks |
| **並行能力** | Multi-skill parallel retrieval |

### 1.2 核心理念 - 雙鐵軌隔離設計

DocAI 採用「**雙鐵軌完全隔離**」設計，就像**火車的兩條軌道永不相交**：

```
🚂 File-Based Track (檔案模式)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ↑ 獨立 Database (docai.db)
   ↑ 獨立 FAISS Store (files/)
   ↑ 獨立 API Endpoints (/api/v1/files, /api/v1/chat)

🚂 Skill-Based Track (技能模式)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ↑ 獨立 Database (skill_metadata.db)
   ↑ 獨立 FAISS Store (skills/)
   ↑ 獨立 API Endpoints (/api/v1/skills)
```

**為何需要隔離？**

1. **Demo 優先策略**：快速開發新功能，不影響既有系統
2. **風險隔離**：新系統問題不會破壞舊系統穩定性
3. **效能優化**：各系統可獨立調優（chunk size, embedding model）
4. **漸進式遷移**：允許平滑過渡，無需一次性重構

---

## 2. 完整系統架構圖

### 2.1 高階系統架構 (High-Level Architecture)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Frontend Layer (UI)                            │
│  ┌──────────────────┐              ┌─────────────────────────────────┐ │
│  │  skill_main.html │              │      index.html                 │ │
│  │  (Skill Mode)    │              │   (File Mode)                   │ │
│  │  - 3-Level Tree  │              │   - Single PDF Query            │ │
│  │  - Multi-Select  │              │   - Document Management         │ │
│  │  - Loading UI    │              │   - OPMP Progress               │ │
│  └────────┬─────────┘              └─────────────┬───────────────────┘ │
└───────────┼────────────────────────────────────┼─────────────────────┘
            │                                    │
            ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        API Layer (FastAPI Router)                       │
│  ┌──────────────────────────┐      ┌──────────────────────────────┐   │
│  │   /api/v1/skills/*       │      │   /api/v1/chat               │   │
│  │   - query_demo_skill     │      │   - chat_stream (SSE)        │   │
│  │   - create_skill         │      │   - chat_non_streaming       │   │
│  │   - upload_source        │      │   /api/v1/files/*            │   │
│  │   - add_instant_attach   │      │   - upload, list, delete     │   │
│  └────────────┬─────────────┘      └────────────┬─────────────────┘   │
└───────────────┼──────────────────────────────────┼───────────────────┘
                │                                  │
                ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Service Layer (Business Logic)                     │
│  ┌───────────────────────────┐     ┌────────────────────────────────┐  │
│  │  SkillServices            │     │  OPMP Kernel (File-Based)      │  │
│  │  - SkillIngestionService  │     │  - Phase 1: Query Understanding│  │
│  │  - SkillRetrievalService  │     │  - Phase 2: Parallel Retrieval │  │
│  │  - AbstractRetrievalSvc   │     │  - Phase 3: Context Assembly   │  │
│  │                           │     │  - Phase 4: Response Generation│  │
│  │  PromptService (Shared)   │     │  - Phase 5: Post Processing    │  │
│  │  - RAG Prompt Engineering │     │                                │  │
│  └────────────┬──────────────┘     └────────────┬───────────────────┘  │
└───────────────┼──────────────────────────────────┼───────────────────┘
                │                                  │
                ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Provider Layer (Data Access)                       │
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐   │
│  │  SkillMetadataProvider       │  │  FileMetadataProvider        │   │
│  │  (skill_metadata.db)         │  │  (docai.db)                  │   │
│  │  - CRUD operations           │  │  - CRUD operations           │   │
│  │  - 3-level tree queries      │  │  - Chunk management          │   │
│  │                              │  │                              │   │
│  │  VectorStoreProvider         │  │  VectorStoreProvider         │   │
│  │  (skills/ FAISS indices)     │  │  (files/ FAISS indices)      │   │
│  │  - store_type="skill"        │  │  - store_type="file"         │   │
│  │                              │  │                              │   │
│  │  EmbeddingProvider (Shared)  │  │  LLMProvider (Shared)        │   │
│  │  - BGE-M3 embeddings         │  │  - Gemini/GPT integration    │   │
│  └──────────────────────────────┘  └──────────────────────────────┘   │
└───────────────┼──────────────────────────────────┼───────────────────┘
                │                                  │
                ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Storage Layer (Persistence)                        │
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐   │
│  │  SQLite Databases            │  │  FAISS Vector Stores         │   │
│  │  ├─ skill_metadata.db        │  │  ├─ skills/                  │   │
│  │  │  ├─ skill_metadata        │  │  │  ├─ skill_{id}_src_{n}/  │   │
│  │  │  ├─ skill_overviews       │  │  │  │  ├─ index.faiss       │   │
│  │  │  ├─ skill_doc_mapping     │  │  │  │  └─ index.pkl         │   │
│  │  │  └─ skill_chunk_metadata  │  │  │                           │   │
│  │  │                           │  │  ├─ files/                   │   │
│  │  └─ docai.db                 │  │  │  ├─ file_{id}/           │   │
│  │     ├─ file_metadata         │  │  │  │  ├─ index.faiss       │   │
│  │     ├─ chunks_metadata       │  │  │  │  └─ index.pkl         │   │
│  │     └─ document_overviews    │  │                              │   │
│  └──────────────────────────────┘  └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心組件隱喻 (Component Metaphors)

為了更好理解各組件的角色，我們使用**圖書館管理系統**的比喻：

| 組件 | 圖書館角色 | 職責 |
|------|-----------|------|
| **SkillIngestionService** | 📚 **圖書編目員** | 接收新書（PDF）→ 編目分類 → 製作索引卡 |
| **SkillMetadataProvider** | 📁 **檔案櫃管理員** | 管理書籍目錄卡片（metadata），提供快速查詢 |
| **VectorStoreProvider** | 🔍 **語義索引系統** | 將書籍內容轉為「語義指紋」，支援模糊搜尋 |
| **SkillRetrievalService** | 👨‍🏫 **參考館員** | 根據讀者問題，找出最相關的書籍段落 |
| **PromptService** | 📝 **問答顧問** | 將找到的段落整理成易讀的答案 |
| **LLMProvider** | 🤖 **智能助理** | 理解問題並生成自然語言回答 |
| **API Layer** | 🚪 **圖書館櫃檯** | 接待讀者，分發任務給後勤人員 |

---

## 3. 資料流程詳解

### 3.1 PDF 上傳 → 處理 → 儲存流程 (Skill-Based)

這是系統的「**消化管道**」（Digestive Pipeline）：食物（PDF）進入 → 分解（chunking）→ 吸收（embedding）→ 儲存（storage）。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PDF Upload & Processing Pipeline                     │
└─────────────────────────────────────────────────────────────────────────┘

Step 1: Upload (前端 → API)
────────────────────────────
User Action: 點擊 "Add PDF" 按鈕
   │
   ├─► Frontend: skill_main.html
   │   ├─ Collect: File object + skill_id + skill_name
   │   └─ POST /api/v1/skills/upload-source
   │
   └─► API: upload_source_to_skill()
       ├─ Receive: FormData with PDF binary
       ├─ Save: uploadfiles/{skill_name}/{filename}.pdf
       └─ Trigger: process_pdf_for_skill()

Step 2: Extract (PyPDF2 文字提取)
────────────────────────────
process_pdf_for_skill()
   │
   ├─► PyPDF2.PdfReader
   │   ├─ Open PDF file
   │   ├─ Extract text from each page
   │   └─ Store: [(page_num, page_text), ...]
   │
   └─► Result: pages_extracted = 385 (example)

Step 3: Chunk (文字切塊)
────────────────────────────
SkillIngestionService.chunk_skill_content()
   │
   ├─► RecursiveCharacterTextSplitter
   │   ├─ chunk_size: 1000 chars (Skill 模式較大)
   │   ├─ chunk_overlap: 100 chars
   │   └─ Split: long_text → [chunk_1, chunk_2, ...]
   │
   └─► Result: chunks_created = 385

Step 4: Generate Embeddings (向量化)
────────────────────────────
EmbeddingProvider.get_embeddings_batch()
   │
   ├─► BGE-M3 Model (BAAI/bge-m3)
   │   ├─ Input: List[chunk_text]
   │   ├─ Process: Text → 1024-dim dense vector
   │   └─ Output: List[List[float]] (embeddings)
   │
   └─► Result: 385 embeddings generated

Step 5: Store FAISS Index (向量儲存)
────────────────────────────
VectorStoreProvider.create_store_from_texts()
   │
   ├─► Build FAISS Index
   │   ├─ Create: IndexFlatL2 (L2 distance)
   │   ├─ Add: embeddings → index
   │   └─ Save: data/faiss_indices/skills/skill_{id}_src_{n}/
   │       ├─ index.faiss (vector data)
   │       └─ index.pkl (metadata)
   │
   └─► Result: FAISS index persisted

Step 6: Store Metadata (SQLite 記錄)
────────────────────────────
SkillMetadataProvider.create_skill()
   │
   ├─► Insert skill_metadata table
   │   ├─ skill_id: skill_20251203_054249_f333015b_src_00
   │   ├─ skill_name: "Decoding_Large_Language_Models"
   │   ├─ parent_skill_id: skill_20251126_105138_b8cc08c1
   │   ├─ total_chunks: 385
   │   └─ metadata: {"source_file": "...", "created_at": "..."}
   │
   ├─► Insert skill_chunk_metadata table (385 rows)
   │   └─ Each row: chunk_id, skill_id, document_name, page_number, chunk_text
   │
   └─► Insert skill_document_mapping table
       └─ Link: skill_id ↔ file_id

✅ Pipeline Complete
────────────────────────────
Response to Frontend:
{
  "status": "success",
  "pages_extracted": 385,
  "chunks_created": 385,
  "embedding_model": "BAAI/bge-m3",
  "skill_id": "skill_20251203_054249_f333015b_src_00"
}
```

**關鍵設計決策**：

- **Chunk Size**: Skill 用 1000 chars，File 用 500 chars（Skill 需要更多上下文）
- **Overlap**: 100 chars 避免跨段落切割導致語義丟失
- **ID 格式**: `skill_{timestamp}_{hash}_src_{index}` 確保唯一性
- **Instant Attachment**: 上傳到既有 skill 時，自動建立子 skill（非重複主 skill）

---

### 3.2 Query → Retrieval → Generation → Response 流程

這是系統的「**智能回答鏈路**」（Intelligent Response Chain）：問題進入 → 搜尋相關片段 → 組裝上下文 → 生成答案。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                Query Processing & Response Generation                   │
└─────────────────────────────────────────────────────────────────────────┘

Step 1: User Query (前端提交問題)
────────────────────────────
User Input: "LLM 訓練分成哪幾個階段？"
   │
   ├─► Frontend: skill_main.html
   │   ├─ Collect: query, selectedSkills = ["skill_A", "skill_B"]
   │   ├─ Show: Loading overlay with spinner
   │   └─ POST /api/v1/skills/demo/query
   │
   └─► API: query_demo_skill()
       ├─ Parse: skill_ids (multi-select support)
       ├─ Validate: Check skills exist in database
       └─ Prepare: top_k = 10, language = "zh"

Step 2: Vector Retrieval (Level 1 - 向量檢索)
────────────────────────────
SkillRetrievalService.retrieve_context()
   │
   ├─► Generate Query Embedding
   │   └─ EmbeddingProvider: query_text → query_vector[1024]
   │
   ├─► Parallel Search (Multi-Skill Optimization)
   │   ├─ For each skill_id in [skill_A, skill_B, skill_C]:
   │   │   ├─ Load FAISS index from disk
   │   │   ├─ Search: index.search(query_vector, top_k=3)
   │   │   └─ Return: [(chunk_text, score, metadata), ...]
   │   │
   │   ├─ Asyncio.gather(*tasks) - 並行執行
   │   └─ Merge results from all skills
   │
   └─► Sort & Filter
       ├─ Sort by score (ascending, L2 distance)
       ├─ Take top_k = 10 best results
       └─ Format: [{"content": "...", "score": 0.234, "metadata": {...}}, ...]

Step 3: Context Assembly (Level 2 - 上下文組裝)
────────────────────────────
Build Context for LLM
   │
   ├─► Extract Citation Information
   │   ├─ For each retrieved chunk:
   │   │   ├─ Get: document_name from metadata
   │   │   ├─ Get: page_number from metadata
   │   │   └─ Build: citation = "[CSS揭秘-第42頁]"
   │   │
   │   └─ Append citation to chunk text
   │
   ├─► Assemble Context
   │   └─ context_texts = [
   │         "...LLM訓練包括預訓練、微調...\n[CSS揭秘-第42頁]",
   │         "...Stage 1: Pre-training...\n[LLM_Handbook-第15頁]",
   │         ...
   │       ]
   │
   └─► Handle Empty Results
       └─ If context_texts is empty:
           └─ Set context_chunks = ["[無可用上下文]"]

Step 4: Prompt Engineering (Level 3 - Prompt 組裝)
────────────────────────────
PromptService.build_rag_prompt()
   │
   ├─► Build System Prompt (指導 LLM 行為)
   │   └─ Template:
   │       """
   │       你是專業的文檔助手，基於提供的文檔回答問題。
   │
   │       回答策略：
   │       1. 直接使用上方文檔
   │       2. 優先引用文檔
   │       3. 智能補充說明
   │       4. 準確性優先
   │       5. 🚨 不要開頭就說「找不到」
   │
   │       === 相關文檔內容 ===
   │       {context_chunks}
   │       === 文檔內容結束 ===
   │       """
   │
   └─► Build Messages Array
       └─ [
           {"role": "system", "content": system_prompt},
           {"role": "user", "content": "LLM 訓練分成哪幾個階段？"}
         ]

Step 5: LLM Generation (Level 4 - AI 生成答案)
────────────────────────────
LLMProvider.get_chat_completion()
   │
   ├─► Call Gemini/GPT API
   │   ├─ Model: gemini-1.5-pro / gpt-4
   │   ├─ Temperature: 0.7
   │   └─ Messages: [system_prompt, user_query]
   │
   ├─► Streaming Response (for OPMP)
   │   ├─ Token-by-token generation
   │   └─ SSE events: {"event": "token", "data": "..."}
   │
   └─► Non-Streaming Response (for Skill Demo)
       └─ Complete answer in single response

Step 6: Post Processing (Level 5 - 後處理)
────────────────────────────
Format Final Response
   │
   ├─► Add Citations to Answer
   │   └─ answer += "\n\n參考來源：\n[CSS揭秘-第42頁]\n[LLM_Handbook-第15頁]"
   │
   ├─► Build Results Array (Top 5 for display)
   │   └─ [
   │         {
   │           "content": "...",
   │           "score": 0.234,
   │           "citation": "[CSS揭秘-第42頁]",
   │           "source_name": "CSS揭秘"
   │         },
   │         ...
   │       ]
   │
   └─► Return JSON Response
       {
         "skill_ids": ["skill_A", "skill_B"],
         "query": "LLM 訓練分成哪幾個階段？",
         "answer": "LLM 訓練主要分為...\n\n參考來源：...",
         "results": [...],
         "documents_searched": 2
       }

Step 7: Frontend Display (前端渲染)
────────────────────────────
skill_main.html
   │
   ├─► Hide loading overlay
   ├─► Display answer with Markdown rendering
   ├─► Show top 5 results with citations
   └─► Update footer: "📚 搜尋了 2 個知識庫"

✅ Query Complete (Total: ~2-5 seconds)
```

**關鍵優化點**：

1. **Parallel Retrieval**: 多個 skills 並行搜尋（asyncio.gather）
2. **Score Ranking**: L2 距離排序，越小越相關
3. **Citation Tracking**: 完整追蹤每個 chunk 的來源檔案和頁碼
4. **Prompt Fix**: 明確禁止 LLM 在有資料時說「找不到」
5. **Multi-Layer Processing**: 4 層處理（Vector → Context → LLM → API）

---

### 3.3 File-Based vs Skill-Based 流程對比

| 流程階段 | File-Based (OPMP) | Skill-Based (Current) |
|---------|-------------------|----------------------|
| **Entry Point** | `/api/v1/chat` | `/api/v1/skills/demo/query` |
| **Retrieval** | Phase 2: Parallel Retrieval | SkillRetrievalService (parallel) |
| **Context** | Phase 3: Context Assembly | Inline context building |
| **Generation** | Phase 4: Token-by-token SSE | Single JSON response |
| **Progress** | 5-phase progress tracking | Loading spinner only |
| **Query Expansion** | ✅ Phase 1: Auto-expand | ❌ Not implemented |
| **Streaming** | ✅ SSE (Server-Sent Events) | ❌ Not implemented |
| **Response Time** | 3-8s (with progress) | 2-5s (faster) |

---

## 4. 組件關係與互動

### 4.1 組件依賴圖 (Component Dependency Graph)

```
┌───────────────────────────────────────────────────────────────┐
│                      Component Dependencies                   │
└───────────────────────────────────────────────────────────────┘

                    ┌─────────────────┐
                    │   API Layer     │
                    │  (skills.py)    │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
         ┌──────────▼─────────┐  ┌───▼─────────────────┐
         │ SkillIngestionSvc  │  │ SkillRetrievalSvc   │
         └──────────┬─────────┘  └───┬─────────────────┘
                    │                │
         ┌──────────┴────────┬───────┴─────────┬────────────┐
         │                   │                 │            │
  ┌──────▼─────────┐  ┌──────▼────────┐  ┌───▼────────┐  │
  │ SkillMetadata  │  │  VectorStore  │  │ Embedding  │  │
  │   Provider     │  │   Provider    │  │  Provider  │  │
  └────────────────┘  └───────────────┘  └────────────┘  │
                                                          │
                                                   ┌──────▼──────┐
                                                   │ PromptSvc   │
                                                   │ + LLMProvider│
                                                   └─────────────┘
```

### 4.2 核心互動序列 (Key Interaction Sequences)

#### 4.2.1 Skill Creation Sequence

```
Frontend                API                 IngestionSvc        MetadataProvider    VectorStore
   │                     │                       │                    │                │
   │  POST /create       │                       │                    │                │
   ├────────────────────►│                       │                    │                │
   │                     │  generate_skill_id()  │                    │                │
   │                     ├──────────────────────►│                    │                │
   │                     │◄──────────────────────┤                    │                │
   │                     │  skill_id             │                    │                │
   │                     │                       │                    │                │
   │                     │  create_skill()       │                    │                │
   │                     ├────────────────────────────────────────────►│                │
   │                     │                       │                    │  INSERT skill  │
   │                     │                       │                    │                │
   │                     │◄────────────────────────────────────────────┤                │
   │                     │  skill_created        │                    │                │
   │                     │                       │                    │                │
   │◄────────────────────┤                       │                    │                │
   │  200 OK             │                       │                    │                │
```

#### 4.2.2 Query Processing Sequence

```
Frontend             API              RetrievalSvc      VectorStore       LLMProvider      PromptSvc
   │                  │                    │                │                │               │
   │  POST /query     │                    │                │                │               │
   ├─────────────────►│                    │                │                │               │
   │                  │  retrieve()        │                │                │               │
   │                  ├───────────────────►│                │                │               │
   │                  │                    │  search()      │                │               │
   │                  │                    ├───────────────►│                │               │
   │                  │                    │◄───────────────┤                │               │
   │                  │                    │  chunks        │                │               │
   │                  │◄───────────────────┤                │                │               │
   │                  │  context_results   │                │                │               │
   │                  │                    │                │                │               │
   │                  │  build_rag_prompt()│                │                │               │
   │                  ├──────────────────────────────────────────────────────►               │
   │                  │◄────────────────────────────────────────────────────────────────────┤
   │                  │  messages          │                │                │               │
   │                  │                    │                │                │               │
   │                  │  get_completion()  │                │                │               │
   │                  ├────────────────────────────────────────────────────►│               │
   │                  │◄────────────────────────────────────────────────────┤               │
   │                  │  answer            │                │                │               │
   │                  │                    │                │                │               │
   │◄─────────────────┤                    │                │                │               │
   │  200 OK          │                    │                │                │               │
```

---

## 5. 資料儲存架構

### 5.1 SQLite Database Schema (skill_metadata.db)

```sql
-- 主要表：skill_metadata (技能基本資訊)
CREATE TABLE skill_metadata (
    skill_id TEXT PRIMARY KEY,              -- skill_20251203_054249_f333015b
    skill_name TEXT NOT NULL,               -- "大語言模型大全" or "CSS揭秘"
    skill_description TEXT,                 -- Optional description
    skill_category TEXT,                    -- "AI", "Legal", "Finance"
    skill_level TEXT DEFAULT 'intermediate',-- beginner/intermediate/advanced
    tags TEXT,                              -- JSON: ["LLM", "Training", "GPT"]
    related_skills TEXT,                    -- JSON: ["skill_B", "skill_C"]
    total_chunks INTEGER DEFAULT 0,         -- 385 chunks
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,                          -- JSON: {"source_file": "...", ...}
    embedding_model TEXT DEFAULT 'BAAI/bge-m3',
    embedding_dimension INTEGER DEFAULT 1024,
    parent_skill_id TEXT DEFAULT 'root',    -- 🔑 3-Level Tree key
    source_name TEXT DEFAULT NULL,          -- For instant attachments

    INDEX idx_skill_name ON skill_metadata(skill_name),
    INDEX idx_parent_skill_id ON skill_metadata(parent_skill_id)
);

-- skill_document_mapping (Skill ↔ Document 關聯)
CREATE TABLE skill_document_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,                 -- Foreign key to skill_metadata
    file_id TEXT NOT NULL,                  -- Document ID
    document_name TEXT,                     -- "CSS揭秘.pdf"
    document_path TEXT,                     -- "uploadfiles/LLM/CSS揭秘.pdf"
    total_pages INTEGER DEFAULT 0,          -- 385 pages
    relevance_score REAL DEFAULT 0.0,       -- Future use
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE,
    INDEX idx_skill_doc_mapping_skill ON skill_document_mapping(skill_id)
);

-- skill_chunk_metadata (Chunk 級別的元數據)
CREATE TABLE skill_chunk_metadata (
    chunk_id TEXT PRIMARY KEY,              -- "chunk_{skill_id}_{index}"
    skill_id TEXT NOT NULL,                 -- Foreign key
    document_id TEXT NOT NULL,              -- Document ID
    document_name TEXT NOT NULL,            -- "CSS揭秘"
    page_number INTEGER,                    -- 42 (for citation)
    chunk_index INTEGER,                    -- 0, 1, 2, ...
    chunk_text TEXT,                        -- Actual text content
    embedding_model TEXT DEFAULT 'BAAI/bge-m3',
    embedding_dimension INTEGER DEFAULT 1024,
    metadata TEXT,                          -- JSON: additional info
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE,
    INDEX idx_chunk_skill_page ON skill_chunk_metadata(skill_id, document_name, page_number)
);

-- skill_overviews (AI 生成的技能概述)
CREATE TABLE skill_overviews (
    skill_id TEXT PRIMARY KEY,
    overview TEXT NOT NULL,                 -- AI-generated summary
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- embedding_models (支援的嵌入模型)
CREATE TABLE embedding_models (
    model_name TEXT PRIMARY KEY,            -- "BAAI/bge-m3"
    model_type TEXT NOT NULL,               -- "dense", "sparse"
    dimension INTEGER NOT NULL,             -- 1024
    max_sequence_length INTEGER,            -- 8192
    language_support TEXT,                  -- "zh,en"
    configuration TEXT,                     -- JSON config
    is_active BOOLEAN DEFAULT 0,            -- Currently active?
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**設計亮點**：

1. **parent_skill_id**: 實現 3-Level Tree 結構（root → main → attachments）
2. **Cascading Delete**: `ON DELETE CASCADE` 確保刪除 skill 時清除所有關聯資料
3. **Flexible Metadata**: 使用 TEXT JSON 欄位支援未來擴展
4. **Citation Support**: `page_number` + `document_name` 支援精確引用

---

### 5.2 FAISS Vector Storage Structure

```
data/faiss_indices/
├── files/                          # File-Based 系統的向量
│   ├── file_1763976335_ad3729e0_6478b6e5/
│   │   ├── index.faiss             # FAISS binary index
│   │   └── index.pkl               # Metadata pickle
│   └── file_1764051375_fa2463e9_f03fc729/
│       ├── index.faiss
│       └── index.pkl
│
└── skills/                         # Skill-Based 系統的向量
    ├── skill_20251126_104421_4fdb3e9b/    # 六法全書-刑法 (Main)
    │   ├── index.faiss
    │   └── index.pkl
    │
    ├── skill_20251126_105138_b8cc08c1/    # 大語言模型大全 (Main)
    │   ├── index.faiss
    │   └── index.pkl
    │
    ├── skill_20251127_100500_b8cc08c1/    # Instant Attachment 1
    │   ├── index.faiss                     # Parent: 大語言模型大全
    │   └── index.pkl
    │
    ├── skill_20251128_030424_b8cc08c1/    # Instant Attachment 2
    │   ├── index.faiss                     # Parent: 大語言模型大全
    │   └── index.pkl
    │
    └── skill_20251203_054249_f333015b_src_00/  # Latest upload
        ├── index.faiss
        └── index.pkl
```

**FAISS Index 結構**：

```python
# index.faiss (Binary FAISS Index)
- Type: IndexFlatL2 (L2 distance metric)
- Dimension: 1024 (BGE-M3 embeddings)
- Vectors: N x 1024 float32 array
- Size: ~4MB per 1000 vectors

# index.pkl (Metadata Pickle)
{
    "metadatas": [
        {
            "content_id": "skill_20251126_105138_b8cc08c1",
            "document_id": "doc_12345",
            "document_name": "CSS揭秘",
            "page_number": 42,
            "chunk_index": 0,
            "timestamp": "2025-11-26T10:51:38"
        },
        ...
    ],
    "texts": [
        "CSS是層疊樣式表（Cascading Style Sheets）...",
        ...
    ]
}
```

**儲存策略**：

1. **Isolation by Directory**: `files/` vs `skills/` 完全隔離
2. **One Index Per Skill**: 每個 skill 獨立 FAISS index（未來可能合併）
3. **Lazy Loading**: 只在查詢時載入需要的 index
4. **Metadata Co-location**: FAISS index 與 metadata pickle 同目錄

---

## 6. 3-Level Tree 架構

### 6.1 樹狀結構設計理念

DocAI 的 Skill 系統採用「**森林結構**」（Forest of Trees），每個 Main Skill 是一棵樹：

```
📁 Skill Forest (技能森林)
│
├─ 🌳 Tree 1: 大語言模型大全 (Main Skill)
│  │   ├─ skill_id: skill_20251126_105138_b8cc08c1
│  │   ├─ parent_skill_id: "root"
│  │   ├─ total_chunks: 883
│  │   ├─ sources: [Build_a_Large_Language_Model.pdf, LLM_Engineers_Handbook.pdf]
│  │   │
│  │   └─ 📎 Instant Attachments (子節點)
│  │       │
│  │       ├─ 📄 CSS揭秘.pdf
│  │       │   ├─ skill_id: skill_20251128_030424_b8cc08c1
│  │       │   ├─ parent_skill_id: skill_20251126_105138_b8cc08c1 ⬅ 指向主 skill
│  │       │   ├─ total_chunks: 264
│  │       │   └─ source_name: "CSS揭秘"
│  │       │
│  │       └─ 📄 Decoding_Large_Language_Models.pdf
│  │           ├─ skill_id: skill_20251127_100500_b8cc08c1
│  │           ├─ parent_skill_id: skill_20251126_105138_b8cc08c1
│  │           ├─ total_chunks: 385
│  │           └─ source_name: "Decoding_Large_Language_Models"
│
├─ 🌳 Tree 2: 六法全書-刑法 (Main Skill)
│  │   ├─ skill_id: skill_20251126_104421_4fdb3e9b
│  │   ├─ parent_skill_id: "root"
│  │   ├─ total_chunks: 272
│  │   │
│  │   └─ 📎 Instant Attachments
│  │       │
│  │       └─ 📄 刑法補充.pdf
│  │           ├─ skill_id: skill_20251202_070843_4fdb3e9b
│  │           ├─ parent_skill_id: skill_20251126_104421_4fdb3e9b
│  │           └─ total_chunks: 172
│
└─ 🌳 Tree 3: 投資理財 (Main Skill)
    │   ├─ skill_id: skill_20251128_074913_b7380bf3
    │   ├─ parent_skill_id: "root"
    │   ├─ total_chunks: 95
    │   │
    │   └─ 📎 Instant Attachments
    │       └─ 📄 投資理財進階.pdf
    │           ├─ skill_id: skill_20251202_071055_b45c5a1f
    │           ├─ parent_skill_id: skill_20251128_074913_b7380bf3
    │           └─ total_chunks: 95
```

### 6.2 資料庫查詢邏輯

```sql
-- Query 1: 取得所有 Main Skills (根節點)
SELECT skill_id, skill_name, total_chunks
FROM skill_metadata
WHERE parent_skill_id = 'root'
ORDER BY created_at DESC;

-- Result:
-- skill_20251126_105138_b8cc08c1 | 大語言模型大全 | 883
-- skill_20251126_104421_4fdb3e9b | 六法全書-刑法 | 272
-- skill_20251128_074913_b7380bf3 | 投資理財 | 95

-- Query 2: 取得某個 Main Skill 的所有 Instant Attachments
SELECT skill_id, source_name, total_chunks
FROM skill_metadata
WHERE parent_skill_id = 'skill_20251126_105138_b8cc08c1'
ORDER BY created_at DESC;

-- Result:
-- skill_20251128_030424_b8cc08c1 | CSS揭秘 | 264
-- skill_20251127_100500_b8cc08c1 | Decoding_Large_Language_Models | 385

-- Query 3: 計算 Group Total Chunks (Main + Attachments)
SELECT
    main.skill_id,
    main.skill_name,
    main.total_chunks AS main_chunks,
    COALESCE(SUM(att.total_chunks), 0) AS attachment_chunks,
    main.total_chunks + COALESCE(SUM(att.total_chunks), 0) AS total_chunks
FROM skill_metadata main
LEFT JOIN skill_metadata att ON att.parent_skill_id = main.skill_id
WHERE main.parent_skill_id = 'root'
GROUP BY main.skill_id;

-- Result:
-- 大語言模型大全 | main: 883 | attachments: 649 | total: 1532
-- 六法全書-刑法 | main: 272 | attachments: 172 | total: 444
-- 投資理財 | main: 95 | attachments: 95 | total: 190
```

### 6.3 Frontend Rendering Logic

```javascript
// skill_main.html - buildSkillTree() function

async function buildSkillTree() {
    // Step 1: 取得所有 skills
    const skills = await fetch('/api/v1/skills/demo/list').then(r => r.json());

    // Step 2: 建立 Main Skill Map
    const mainSkills = {};
    const attachments = {};

    skills.forEach(skill => {
        if (skill.parent_skill_id === 'root') {
            mainSkills[skill.skill_id] = {
                ...skill,
                attachments: []
            };
        } else {
            if (!attachments[skill.parent_skill_id]) {
                attachments[skill.parent_skill_id] = [];
            }
            attachments[skill.parent_skill_id].push(skill);
        }
    });

    // Step 3: 組裝樹狀結構
    Object.keys(mainSkills).forEach(mainId => {
        if (attachments[mainId]) {
            mainSkills[mainId].attachments = attachments[mainId];
        }
    });

    // Step 4: 渲染 UI
    const treeHTML = Object.values(mainSkills).map(main => {
        const totalChunks = main.total_chunks +
            main.attachments.reduce((sum, att) => sum + att.total_chunks, 0);

        return `
            <div class="skill-group" data-skill-id="${main.skill_id}">
                <!-- Group Header (可點擊，選擇整組) -->
                <div class="skill-group-header" onclick="selectSkillGroup('${main.skill_id}')">
                    <i class="fas fa-folder-open"></i>
                    <span>${main.skill_name}</span>
                    <span class="chunk-count">(${totalChunks})</span>
                </div>

                <!-- Main Skill -->
                <div class="skill-item main" onclick="selectSkill('${main.skill_id}')">
                    <input type="checkbox" id="skill-${main.skill_id}">
                    <i class="fas fa-book"></i>
                    <span>📚 主要內容</span>
                    <span class="chunk-count">(${main.total_chunks})</span>
                </div>

                <!-- Instant Attachments -->
                ${main.attachments.map(att => `
                    <div class="skill-item attachment" onclick="selectSkill('${att.skill_id}')">
                        <input type="checkbox" id="skill-${att.skill_id}">
                        <i class="fas fa-paperclip"></i>
                        <span>📎 ${att.source_name}</span>
                        <span class="chunk-count">(${att.total_chunks})</span>
                    </div>
                `).join('')}
            </div>
        `;
    }).join('');

    document.getElementById('skill-tree').innerHTML = treeHTML;
}

// Step 5: Multi-Select Logic
function selectSkillGroup(mainSkillId) {
    // 點擊 Group Header → 選擇 Main + 所有 Attachments
    const group = document.querySelector(`[data-skill-id="${mainSkillId}"]`);
    const checkboxes = group.querySelectorAll('input[type="checkbox"]');

    checkboxes.forEach(cb => cb.checked = true);

    // Update selectedSkills array
    selectedSkills = Array.from(checkboxes).map(cb => cb.id.replace('skill-', ''));
}
```

### 6.4 UI 展示效果

```
┌─────────────────────────────────────────────────────────────────┐
│  📁 Skill Tree                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📁 🧠 大語言模型大全 (1532)  ← Group Header (點擊選擇全部)     │
│     ☑ 📚 主要內容 (883)                                         │
│     ☑ 📎 CSS揭秘 (264)                                          │
│     ☑ 📎 Decoding_Large_Language_Models (385)                   │
│                                                                 │
│  📁 📜 六法全書-刑法 (444)                                       │
│     ☐ 📚 主要內容 (272)                                         │
│     ☐ 📎 刑法補充 (172)                                         │
│                                                                 │
│  📁 💰 投資理財 (190)                                           │
│     ☐ 📚 主要內容 (95)                                          │
│     ☐ 📎 投資理財進階 (95)                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. API 架構與端點映射

### 7.1 Skill-Based API Endpoints

```python
# app/api/v1/endpoints/skills.py

# ============================================================
# 技能管理 API
# ============================================================

@router.get("/demo/list")
async def get_demo_skills():
    """取得所有 skills (包含 Main + Instant Attachments)"""
    # 回傳完整的 3-level tree 資料

@router.post("/create")
async def create_skill(request: SkillCreateRequest):
    """建立新的 Main Skill"""
    # 建立根節點 skill (parent_skill_id = "root")

@router.delete("/{skill_id}")
async def delete_skill_complete(skill_id: str):
    """刪除 skill (包含所有 attachments 和 FAISS indices)"""
    # Cascading delete

# ============================================================
# 文件上傳 API
# ============================================================

@router.post("/upload-source")
async def upload_source_to_skill(
    file: UploadFile = File(...),
    skill_id: str = Form(...),
    skill_name: str = Form(...)
):
    """上傳 PDF 到既有 skill (建立 Instant Attachment)"""
    # Step 1: Save PDF to disk
    # Step 2: Call process_pdf_for_skill()
    # Step 3: Return processing result

@router.post("/process-pdf")
async def process_pdf_for_skill(skill_id: str, pdf_path: str):
    """處理 PDF (Extract → Chunk → Embed → Store)"""
    # Complete processing pipeline

# ============================================================
# Instant Attachment 管理
# ============================================================

@router.get("/{skill_id}/instant-attachments")
async def get_instant_attachments(skill_id: str):
    """取得某個 Main Skill 的所有 Instant Attachments"""
    # Query: WHERE parent_skill_id = skill_id

@router.post("/{skill_id}/instant-attachments")
async def add_instant_attachment(skill_id: str, request: InstantAttachmentRequest):
    """新增 Instant Attachment"""
    # Create child skill with parent_skill_id = skill_id

@router.delete("/{skill_id}/instant-attachments")
async def clear_instant_attachments(skill_id: str):
    """清除所有 Instant Attachments (準備 Full Rebuild)"""
    # Delete all child skills

# ============================================================
# 查詢 & 聊天 API
# ============================================================

@router.post("/demo/query")
async def query_demo_skill(
    skill_id: str = Body(None),          # Single skill (backward compat)
    skill_ids: List[str] = Body(None),   # Multi-skill support
    query: str = Body(...),
    top_k: int = Body(10)
):
    """
    Demo-optimized skill query with parallel search.
    Supports single or multiple skills.
    """
    # Step 1: Validate skills exist
    # Step 2: Parallel retrieval (asyncio.gather)
    # Step 3: Build context with citations
    # Step 4: Generate LLM response
    # Step 5: Return formatted answer

@router.post("/{skill_id}/chat")
async def chat_with_skills(skill_id: str, request: SkillChatRequest):
    """Chat with specific skill (future: chat history)"""
    # Similar to query_demo_skill but with history

# ============================================================
# Rebuild 管理 API
# ============================================================

@router.post("/{skill_id}/rebuild")
async def trigger_rebuild(
    skill_id: str,
    request: RebuildRequest = Body(..., force_all: bool = False)
):
    """
    觸發 skill 重建 (merge instant attachments into main skill).
    force_all=true: 完全重建所有 skills
    """
    # Step 1: Clear instant attachments
    # Step 2: Re-process all PDFs
    # Step 3: Merge into single master index

@router.get("/{skill_id}/rebuild/status")
async def get_rebuild_status(skill_id: str):
    """取得 rebuild 進度 (未來實作)"""
    # Return progress percentage

# ============================================================
# Configuration API
# ============================================================

@router.get("/config")
async def get_skill_config():
    """取得 skill_config.json 內容"""
    # 回傳前端 config (圖示映射、顯示順序)

@router.post("/config/skills")
async def add_skill_to_config(skill_id: str, ...):
    """將 skill 新增到 config"""
    # Update skill_config.json

@router.put("/config/skills/reorder")
async def reorder_skills(request: ReorderSkillsRequest):
    """重新排序 skills"""
    # Update display order

# ============================================================
# Utility API
# ============================================================

@router.get("/available-pdfs")
async def get_available_pdfs():
    """列出 uploadfiles/ 中可用的 PDF 檔案"""
    # Scan directory for PDFs

@router.post("/translate")
async def translate_texts(request: TranslationRequest):
    """翻譯文字 (中文 ↔ 英文)"""
    # Use LLM for translation

@router.put("/{skill_id}/rename")
async def rename_skill(skill_id: str, request: RenameRequest):
    """重新命名 skill"""
    # Update skill_name in database
```

### 7.2 File-Based API Endpoints (OPMP)

```python
# app/api/v1/endpoints/chat.py

@router.post("/chat")
async def chat_stream(request: ChatRequest):
    """
    File-Based chat with OPMP 5-phase streaming.
    Returns: SSE (Server-Sent Events) stream
    """
    # Phase 1: Query Understanding (query expansion)
    # Phase 2: Parallel Retrieval (multi-file search)
    # Phase 3: Context Assembly (merge & rank)
    # Phase 4: Response Generation (token-by-token)
    # Phase 5: Post Processing (history, logging)

@router.post("/chat/non-streaming")
async def chat_non_streaming(request: ChatRequest):
    """Non-streaming version for testing"""
    # Complete response in single JSON

# app/api/v1/endpoints/files.py

@router.post("/upload")
async def upload_file(...):
    """上傳 PDF 到 File-Based 系統"""

@router.get("/list")
async def list_files():
    """列出所有已上傳的檔案"""

@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """刪除檔案"""
```

---

## 8. OPMP 五階段 RAG Pipeline

### 8.1 OPMP 架構概覽

**OPMP (Optimistic Progressive Markdown Parsing)** 是 File-Based 系統的核心，提供**5 階段串流式 RAG**：

```
┌────────────────────────────────────────────────────────────────┐
│            OPMP 5-Phase Streaming RAG Pipeline                 │
└────────────────────────────────────────────────────────────────┘

Phase 1: Query Understanding (0-20%)
─────────────────────────────────────
目標: 理解用戶意圖，擴展查詢
輸入: "LLM 訓練分成哪幾個階段？"
處理:
  ├─ Intent Recognition (意圖識別)
  ├─ Entity Extraction (實體提取: "LLM", "訓練", "階段")
  └─ Query Expansion (查詢擴展)
       └─ 原始: "LLM 訓練分成哪幾個階段？"
       └─ 擴展: ["預訓練階段", "微調階段", "對齊階段", "訓練流程"]
輸出: expanded_queries = ["...", "...", ...]
SSE: {"event": "progress", "phase": 1, "progress": 20, "message": "查詢擴展完成"}

Phase 2: Parallel Retrieval (20-50%)
─────────────────────────────────────
目標: 並行檢索多個檔案
輸入: expanded_queries + file_ids
處理:
  ├─ For each file in file_list:
  │   ├─ Load FAISS index
  │   ├─ For each expanded_query:
  │   │   └─ Search top_k=5 chunks
  │   └─ Merge results
  └─ Asyncio.gather(*tasks) - 並行執行
輸出: raw_results = [chunk1, chunk2, ..., chunkN] (N=file_count*query_count*5)
SSE: {"event": "progress", "phase": 2, "progress": 50, "message": "檢索 15 個文件完成"}

Phase 3: Context Assembly (50-70%)
─────────────────────────────────────
目標: 去重、排序、組裝上下文
輸入: raw_results (可能有重複)
處理:
  ├─ Deduplication (去重: based on chunk_text hash)
  ├─ Score Normalization (分數正規化: 不同檔案的分數尺度不同)
  ├─ Ranking (排序: by normalized score)
  ├─ Top-K Selection (選擇最佳 K=10)
  └─ Context Building (組裝上下文 + citations)
輸出: context_chunks = ["chunk1\n[Doc-A-P42]", "chunk2\n[Doc-B-P15]", ...]
SSE: {"event": "progress", "phase": 3, "progress": 70, "message": "上下文組裝完成"}

Phase 4: Response Generation (70-99%)
─────────────────────────────────────
目標: LLM 生成答案（Token-by-token 串流）
輸入: context_chunks + query
處理:
  ├─ Build RAG Prompt (system + context + query)
  └─ LLM Stream Generation
       ├─ Token 1: "LLM"
       ├─ Token 2: " 訓練"
       ├─ Token 3: "主要"
       └─ Token N: "。"
輸出: Token stream
SSE:
  {"event": "token", "data": "LLM"}
  {"event": "token", "data": " 訓練"}
  {"event": "progress", "phase": 4, "progress": 75}
  {"event": "token", "data": "主要"}
  ...

Phase 5: Post Processing (99-100%)
─────────────────────────────────────
目標: 後處理（儲存歷史、統計、回饋）
輸入: complete_answer + context_results
處理:
  ├─ Save Chat History (儲存到 database)
  ├─ Update Usage Statistics (更新統計)
  ├─ Generate Suggestions (生成改進建議)
  └─ Log Performance Metrics (記錄效能指標)
輸出: Processing complete
SSE: {"event": "progress", "phase": 5, "progress": 100, "message": "完成"}
     {"event": "done"}
```

### 8.2 OPMP vs Current Skill System

| Feature | OPMP (File-Based) | Skill System (Current) |
|---------|-------------------|------------------------|
| **Streaming** | ✅ SSE Token-by-token | ❌ Single JSON response |
| **Progress Tracking** | ✅ 5 phases (0-100%) | ❌ Loading spinner only |
| **Query Expansion** | ✅ Auto-expand to 3-5 queries | ❌ Single query |
| **Parallel Retrieval** | ✅ Multi-file parallel | ✅ Multi-skill parallel |
| **Context Assembly** | ✅ Dedup + Normalize + Rank | ✅ Basic ranking |
| **Chat History** | ✅ Stored in DB | ❌ Not implemented |
| **User Feedback** | ✅ Thumbs up/down | ❌ Not implemented |
| **Complexity** | 🔴 High (5 phases + SSE) | 🟢 Low (simple endpoint) |
| **Response Time** | 3-8s (with progress) | 2-5s (faster) |
| **User Experience** | 🌟 Best (real-time feedback) | ⭐ Good (simple) |

### 8.3 Post-Demo Integration Roadmap

```
Phase 1: 基礎串流 (Week 1)
─────────────────────────────
目標: Skill System 增加 SSE streaming
實作:
  ├─ New endpoint: /api/v1/skills/{skill_id}/chat/stream
  ├─ Token-by-token generation
  └─ Frontend EventSource integration

Phase 2: 進度追蹤 (Week 2)
─────────────────────────────
目標: 3 階段簡化版進度
實作:
  ├─ Phase 1: Retrieval (0-33%)
  ├─ Phase 2: Generation (34-99%)
  └─ Phase 3: Complete (100%)

Phase 3: 完整 OPMP 整合 (Week 3-4)
─────────────────────────────
目標: 將 5 階段系統移植到 Skill
實作:
  ├─ Phase 1: Query Understanding (query expansion)
  ├─ Phase 2: Parallel Retrieval (multi-skill)
  ├─ Phase 3: Context Assembly (dedup + rank)
  ├─ Phase 4: Response Generation (streaming)
  └─ Phase 5: Post Processing (history + stats)

Phase 4: 企業級功能 (Month 2+)
─────────────────────────────
實作:
  ├─ Master Index 優化 (merge all indices)
  ├─ Memory Management (LRU cache)
  ├─ 向量相似度閾值過濾
  ├─ 前端相關度指示器
  ├─ 智能知識庫推薦系統
  └─ 並行搜尋優化
```

---

## 9. 技術棧與依賴

### 9.1 核心技術棧

```yaml
Backend:
  Framework: FastAPI (Python 3.10+)
  API Style: RESTful + SSE (Server-Sent Events)
  Async: asyncio, aiofiles

Vector Database:
  Engine: FAISS (Facebook AI Similarity Search)
  Index Type: IndexFlatL2 (L2 distance metric)
  Storage: Persistent disk storage (index.faiss + index.pkl)

Relational Database:
  Engine: SQLite3
  Databases:
    - skill_metadata.db (Skill system)
    - docai.db (File system)

Embeddings:
  Model: BGE-M3 (BAAI/bge-m3)
  Dimension: 1024 (dense vectors)
  Provider: HuggingFace Transformers

LLM:
  Primary: Google Gemini 1.5 Pro
  Fallback: OpenAI GPT-4
  API: REST (google.generativeai / openai SDK)

PDF Processing:
  Extraction: PyPDF2
  Chunking: LangChain RecursiveCharacterTextSplitter
  OCR: (Future) Tesseract for scanned PDFs

Frontend:
  Templates: Jinja2 (server-side rendering)
  JavaScript: Vanilla JS (no framework)
  Markdown: marked.js
  Icons: Font Awesome 6.5.1
  Fonts: Google Fonts (Noto Sans TC + Inter)

Deployment:
  Server: Uvicorn (ASGI server)
  Process Manager: systemd / PM2 (未來)
  Reverse Proxy: Nginx (未來)
```

### 9.2 Python 依賴清單

```python
# requirements.txt (核心依賴)

# FastAPI & Server
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6  # For file uploads

# Machine Learning
sentence-transformers==2.2.2  # For BGE-M3
faiss-cpu==1.7.4  # Vector search
numpy==1.24.3

# LLM Providers
google-generativeai==0.3.1  # Gemini
openai==1.3.5  # GPT-4

# PDF Processing
PyPDF2==3.0.1
langchain==0.0.335  # Text splitting
langchain-community==0.0.5

# Database
aiosqlite==0.19.0  # Async SQLite

# Utilities
python-dotenv==1.0.0  # Environment variables
pydantic==2.5.0  # Data validation
jinja2==3.1.2  # Template engine
```

---

## 10. 系統隔離設計

### 10.1 隔離層級 (Isolation Levels)

DocAI 採用**多層隔離**確保兩個系統完全獨立：

```
┌─────────────────────────────────────────────────────────────────┐
│                    Isolation Architecture                       │
└─────────────────────────────────────────────────────────────────┘

Level 1: UI Layer Isolation
────────────────────────────
File-Based:     skill_main.html  (Skill Tree UI)
Skill-Based:    index.html       (Single PDF UI)
Toggle:         Radio button to switch modes

Level 2: API Endpoint Isolation
────────────────────────────
File-Based:     /api/v1/chat, /api/v1/files/*
Skill-Based:    /api/v1/skills/*
No Overlap:     ✅ Complete path separation

Level 3: Service Layer Isolation
────────────────────────────
File-Based:     OPMP Kernel (5-phase pipeline)
Skill-Based:    SkillServices/* (Ingestion, Retrieval)
Shared:         PromptService, LLMProvider, EmbeddingProvider

Level 4: Database Isolation
────────────────────────────
File-Based:     docai.db
                ├─ file_metadata
                ├─ chunks_metadata
                └─ document_overviews

Skill-Based:    skill_metadata.db
                ├─ skill_metadata
                ├─ skill_document_mapping
                ├─ skill_chunk_metadata
                └─ skill_overviews

Level 5: Vector Storage Isolation
────────────────────────────
File-Based:     data/faiss_indices/files/
                └─ file_{id}/

Skill-Based:    data/faiss_indices/skills/
                └─ skill_{id}_src_{n}/

Mechanism:      VectorStoreProvider.store_type parameter
                ├─ store_type="file"  → files/ directory
                └─ store_type="skill" → skills/ directory
```

### 10.2 共享組件 (Shared Components)

儘管兩個系統隔離，但有些組件是**共享**的以避免重複：

| 組件 | 共享原因 |
|------|---------|
| **EmbeddingProvider** | BGE-M3 模型載入昂貴，共享實例節省記憶體 |
| **LLMProvider** | API 金鑰與配置統一管理 |
| **PromptService** | RAG prompt engineering 邏輯相同 |
| **Config (.env)** | 統一的環境變數配置 |
| **Logging** | 集中式日誌管理 |

### 10.3 隔離測試 (Isolation Verification)

```bash
# Test 1: 驗證 Database 隔離
sqlite3 data/skill_metadata.db "SELECT COUNT(*) FROM skill_metadata"  # 10
sqlite3 data/docai.db "SELECT COUNT(*) FROM file_metadata"            # 8
# ✅ 不同數量，確認資料隔離

# Test 2: 驗證 FAISS 隔離
ls data/faiss_indices/files/   | wc -l   # 8 directories
ls data/faiss_indices/skills/  | wc -l   # 15 directories
# ✅ 不同目錄，確認向量隔離

# Test 3: 驗證 API 隔離
curl localhost:8000/api/v1/skills/demo/list     # Skill data
curl localhost:8000/api/v1/files/list           # File data
# ✅ 不同回應，確認 API 隔離

# Test 4: 驗證 UI 隔離
# Visit: http://localhost:8000/skill          # Skill UI
# Visit: http://localhost:8000/SinglePDFQuery # File UI
# ✅ 完全不同的介面
```

---

## 11. 總結與關鍵洞察

### 11.1 系統設計亮點

1. **雙軌隔離策略** 🚂🚂
   - 允許新舊系統共存，降低遷移風險
   - Demo 優先，快速驗證新架構可行性

2. **3-Level Tree 架構** 🌳
   - 靈活的層級結構（Root → Main → Attachments）
   - Instant Attachment 機制實現即時搜尋

3. **Parallel Retrieval** ⚡
   - Multi-skill 並行搜尋顯著提升效能
   - Asyncio 驅動的高效能 I/O

4. **Complete Citation Tracking** 📚
   - 精確追蹤每個答案的來源（文件 + 頁碼）
   - 提升回答可信度與可驗證性

5. **Prompt Engineering** 🎯
   - 4 層處理邏輯（Vector → Context → LLM → API）
   - 明確指令避免「找不到資料」誤判

### 11.2 未來優化方向

```
Short-Term (1-2 weeks):
├─ SSE Streaming integration
├─ Progress tracking (3-phase)
└─ Basic chat history

Mid-Term (1-2 months):
├─ Full OPMP integration (5-phase)
├─ Master index optimization
├─ Relevance threshold filtering
└─ Smart skill recommendation

Long-Term (3+ months):
├─ Microservices architecture
├─ Distributed FAISS (multi-node)
├─ Real-time collaboration
└─ Advanced analytics dashboard
```

### 11.3 效能指標

| Metric | File-Based | Skill-Based | Target |
|--------|-----------|-------------|--------|
| **Query Response Time** | 3-8s | 2-5s | <3s |
| **Parallel Retrieval** | ✅ Multi-file | ✅ Multi-skill | - |
| **Streaming** | ✅ Token-by-token | ❌ (planned) | ✅ |
| **Chunk Size** | 500 chars | 1000 chars | Adaptive |
| **Top-K Results** | 10 | 10 | Dynamic |
| **Memory Usage** | ~2GB | ~1.5GB | <2GB |

---

## 12. 關鍵檔案索引

### 12.1 Skill-Based System

```
app/SkillServices/
├── base_retrieval.py              # Abstract interface (182 lines)
├── skill_ingestion_service.py     # Content processing (383 lines)
└── skill_retrieval_service.py     # Vector retrieval (145 lines)

app/Providers/skill_metadata_provider/
└── client.py                       # SQLite metadata (685 lines)

app/Providers/vector_store_provider/
└── client.py                       # FAISS operations (605 lines)

app/api/v1/endpoints/
└── skills.py                       # API endpoints (1000+ lines)

app/Services/
└── prompt_service.py               # RAG prompts (380 lines)

template/
└── skill_main.html                 # Frontend UI (1200+ lines)

data/
├── skill_metadata.db               # SQLite database
└── faiss_indices/skills/           # FAISS indices
```

### 12.2 File-Based System (OPMP)

```
refData/Codes/opmp_kernel/
├── phase1_query_understanding.py   # Query expansion
├── phase2_parallel_retrieval.py    # Multi-file search
├── phase3_context_assembly.py      # Context merging
├── phase4_response_generation.py   # Token streaming
└── phase5_postprocessing.py        # History & stats

app/api/v1/endpoints/
├── chat.py                         # OPMP chat endpoints
└── files.py                        # File management

data/
├── docai.db                        # SQLite database
└── faiss_indices/files/            # FAISS indices
```

---

## 附錄 A: 完整資料流程圖 (Flowchart)

```
┌─────────────────────────────────────────────────────────────────┐
│             Complete Data Flow: Upload to Query                 │
└─────────────────────────────────────────────────────────────────┘

[User] Upload PDF
    │
    ├─► [Frontend] skill_main.html
    │       │
    │       ├─► POST /api/v1/skills/upload-source
    │       │
    │       └─► [API] upload_source_to_skill()
    │               │
    │               ├─► Save to disk: uploadfiles/{skill_name}/{file}.pdf
    │               │
    │               └─► [API] process_pdf_for_skill()
    │                       │
    │                       ├─► [PyPDF2] Extract text from PDF
    │                       │       └─► pages = [(1, "text1"), (2, "text2"), ...]
    │                       │
    │                       ├─► [SkillIngestionService] chunk_skill_content()
    │                       │       ├─► RecursiveCharacterTextSplitter
    │                       │       │   └─► chunk_size=1000, overlap=100
    │                       │       └─► chunks = ["chunk1", "chunk2", ...]
    │                       │
    │                       ├─► [EmbeddingProvider] get_embeddings_batch()
    │                       │       ├─► BGE-M3 Model
    │                       │       └─► embeddings = [[0.12, 0.34, ...], ...]
    │                       │
    │                       ├─► [VectorStoreProvider] create_store_from_texts()
    │                       │       ├─► FAISS IndexFlatL2
    │                       │       └─► Save: skills/skill_{id}_src_{n}/
    │                       │               ├─ index.faiss
    │                       │               └─ index.pkl
    │                       │
    │                       └─► [SkillMetadataProvider] create_skill()
    │                               ├─► INSERT skill_metadata
    │                               ├─► INSERT skill_chunk_metadata (N rows)
    │                               └─► INSERT skill_document_mapping
    │
    └─► [Frontend] Display: "✅ 成功處理 385 頁"

[User] Submit Query
    │
    ├─► [Frontend] skill_main.html
    │       │
    │       ├─► Show loading overlay
    │       │
    │       └─► POST /api/v1/skills/demo/query
    │               Body: {query, skill_ids, top_k}
    │
    └─► [API] query_demo_skill()
            │
            ├─► Validate skills exist
            │       └─► [SkillMetadataProvider] get_documents_for_skill()
            │
            ├─► [SkillRetrievalService] retrieve_context()
            │       │
            │       ├─► [EmbeddingProvider] get_embedding()
            │       │       └─► query_vector = [0.23, 0.45, ...]
            │       │
            │       ├─► For each skill_id (parallel):
            │       │       ├─► [VectorStoreProvider] _load_faiss_store()
            │       │       │       └─► Load: skills/skill_{id}/index.faiss
            │       │       │
            │       │       └─► [FAISS] index.search(query_vector, top_k=3)
            │       │               └─► results = [(distance, chunk_text, metadata), ...]
            │       │
            │       ├─► asyncio.gather(*tasks) - Parallel execution
            │       │
            │       └─► Merge & Sort results by score
            │               └─► context_results (top_k=10)
            │
            ├─► Build context with citations
            │       └─► context_texts = [
            │               "...LLM訓練...\n[CSS揭秘-第42頁]",
            │               ...
            │           ]
            │
            ├─► [PromptService] build_rag_prompt()
            │       └─► messages = [
            │               {role: "system", content: "..."},
            │               {role: "user", content: "LLM訓練...?"}
            │           ]
            │
            ├─► [LLMProvider] get_chat_completion()
            │       ├─► Gemini/GPT API call
            │       └─► answer = "LLM訓練主要分為..."
            │
            ├─► Add citations to answer
            │       └─► answer += "\n\n參考來源：\n[CSS揭秘-第42頁]..."
            │
            └─► Return JSON response
                    └─► {skill_ids, query, answer, results, documents_searched}
                        │
                        └─► [Frontend] skill_main.html
                                ├─► Hide loading overlay
                                ├─► Display answer (Markdown)
                                ├─► Show top 5 results
                                └─► Update footer: "📚 搜尋了 2 個知識庫"
```

---

**文件作者**: Claude (SuperClaude Framework)
**最後更新**: 2025-12-03
**版本**: v1.0.0
**標籤**: #Architecture #RAG #FAISS #DocAI #SystemDesign

---

