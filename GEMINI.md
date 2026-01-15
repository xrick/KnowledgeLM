# GEMINI.md - Project Context & Guidelines

## 1. Project Overview: DocAI

**Goal**: A local RAG (Retrieval-Augmented Generation) system supporting both file-based ad-hoc queries and curated "Skill" knowledge bases.
**Current Phase**: Demo Ready ✅ (Track B: Skill-Based RAG).
**Last Updated**: 2025-12-05

## 2. Tech Stack

- **Backend**: Python 3.11, FastAPI, Asyncio.
- **Database**:
  - **Vector**: FAISS (主要向量儲存，per-skill 物理隔離).
  - **Metadata**: SQLite (`skill_metadata.db`), MySQL (Legacy/User).
- **LLM**: Ollama (Local), OpenAI (Optional).
- **Embeddings**: BAAI/bge-m3 (1024 dimensions).
- **Frontend**: Vanilla JS + HTML Templates (Jinja2-like).

## 3. Architecture Guidelines

### Dual RAG Architecture

1.  **File-Based RAG** (Legacy):
    - Uses Milvus partitions per file.
    - 5-Phase OPMP Pipeline: Query -> Retrieval -> Rerank -> Generation -> Post-process.
    - Supports multi-file selection with SSE streaming.
2.  **Skill-Based RAG** (New/Demo):
    - Uses FAISS indices (physically isolated per skill).
    - "Skill" = Curated collection of PDFs merged into a unified knowledge domain.
    - **Key Constraint**: Demo stability > Perfect architecture.
    - **Storage**: `/data/faiss_indices/skills/{skill_id}`.

### 🎯 Architecture Refactoring Complete (2025-12-04) ✅

**問題：Dual Source of Truth (反模式) → 已解決**

舊的 `skill_config.json` + `skill_metadata.db` 雙來源已廢棄。

**新架構：skill_heads 表（Single Source of Truth）**

```sql
-- skill_heads (Skill 定義層)
CREATE TABLE skill_heads (
    head_id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL UNIQUE,
    description TEXT,
    category TEXT DEFAULT 'General',
    display_order INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    updated_at DATETIME
);

-- skill_metadata 透過 head_id 關聯
ALTER TABLE skill_metadata ADD COLUMN head_id TEXT REFERENCES skill_heads(head_id);
```

**實施狀態**

| 步驟 | 狀態 |
|------|------|
| 創建 skill_heads 表 | ✅ 完成 |
| 添加 head_id 外鍵 | ✅ 完成 |
| 資料遷移 (5 heads, 17 docs) | ✅ 完成 |
| API endpoints 更新 | ✅ 完成 |
| 前端更新 | ✅ 完成 |
| skill_config.json 封存 | ✅ 完成 |

**封存位置**：`scripts/skill_data/archive/skill_config.json.deprecated`

### Instant Attachment Workflow (New Concept)

上傳 PDF 到既有 Skill 的流程：

```text
Upload PDF → Create Instant Attachment → Searchable Immediately
                        ↓
         Accumulate 5-10 attachments → Trigger Full Skill Rebuild
```

- **Instant Attachments**: 立即可搜尋，暫存於 skill 下
- **Rebuild Threshold**: 累積 5-10 個後統一重建，避免碎片化
- **UI**: 三層架構 (Skill Tree → Skills → Instant Attachments)

### Key Patterns

- **Service Layer**: Business logic in `app/Services` or `app/SkillServices`.
- **Dependency Injection**: Use FastAPI `Depends()` for all providers.
- **Async First**: All I/O operations (DB, LLM, File) must be `async/await`.

## 4. Coding Rules

- **Language**: Python (Backend), JavaScript (Frontend).
- **Style**: PEP 8 compliant.
- **Type Hinting**: Mandatory for all function signatures (e.g., `def func(x: int) -> str:`).
- **Error Handling**:
  - Use `try/except` blocks in Service/Endpoint layers.
  - Log errors using `logger.error` with tracebacks if needed.
  - Return clean `HTTPException` to frontend.
- **Comments**: Explain "Why", not just "What". Keep Docstrings updated.

## 5. Operational Protocol (RIPER-5)

**You must follow strictly:**

1.  **[MODE: RESEARCH]**: Analyze, read files, understand before acting.
2.  **[MODE: INNOVATE]**: Brainstorm solutions (optional).
3.  **[MODE: PLAN]**: Create a detailed checklist of changes.
4.  **[MODE: EXECUTE]**: Implement changes exactly as planned.
5.  **[MODE: REVIEW]**: Verify implementation against the plan.

## 6. 🚨 Known Issues / 已知問題

### ❌ 聊天介面捲動問題 (UNSOLVED)

**問題描述**：
在 `skill_main.html` 聊天介面中，當用戶輸入新的 query 時，舊的訊息（包含前一個 query 和 AI 回答）無法自動向上捲動出畫面，直到只剩下新的 query 顯示在畫面上。

**期望行為**：
```
輸入新 query 後，畫面應該：
┌─────────────────────────────────────────┐
│  [新 query]            ← 新 query 在頂部 │
│  [進度條..........]                     │
│  [AI 回答區域]                          │
│                                         │
├─────────────────────────────────────────┤
│  [輸入框]                               │
└─────────────────────────────────────────┘
（舊訊息應該被完全捲出可視範圍上方）
```

**目前狀況**：
- 舊訊息仍然顯示在畫面上方
- `scrollIntoView` 無法正確將新 query 定位到畫面頂部

**相關檔案**：
- `template/skill_main.html` - 聊天介面主頁面
- `static/js/progressive_markdown_renderer.js` - 串流渲染器

**嘗試過的修復**：
1. `scrollTop = scrollHeight` → 捲到最底部，不是想要的效果
2. `scrollIntoView({ block: 'start' })` → 無法正確定位
3. `offsetTop` 計算 → 可能計算不正確

**Last Updated**: 2025-12-16

---

## 7. Current Status (2025-12-04)

### ✅ Completed Features

| Feature | Status | Notes |
|---------|--------|-------|
| PDF Upload Pipeline | ✅ | Extract → Embed → Store FAISS |
| Chat Query | ✅ | Working with BGE-M3 embeddings |
| UI Toggle | ✅ | File/Skill mode switch exists |
| Loading Spinner | ✅ | Full-screen overlay with blur |
| Prompt Fix | ✅ | No more false "找不到資料" |
| 3-Level Tree UI | ✅ | parent_skill_id hierarchy |
| Multi-Select Query | ✅ | skill_ids array support |
| Source Name Display | ✅ | Fixed "Unknown" issue |
| Skill Names Sync | ✅ | Config ↔ Database 名稱一致 |
| Re-Build Modal | ✅ | 確認 Modal + 紅色警告按鈕 |
| FAISS Demo Mode | ✅ | Milvus 檢查禁用 for 12/1-12/2 |
| skill_heads 架構 | ✅ | Single Source of Truth (SQLite) |
| JSON 依賴移除 | ✅ | skill_config.json 已封存 |
| 前端 /tree 整合 | ✅ | skill_config.html, skill_main.html |
| SSE 上傳進度 | ✅ | 即時進度條、階段顯示、自動刷新 |
| 刪除來源功能 | ✅ | skill_config 頁面刪除按鈕 + 確認 Modal |
| UI 文字參考 | ✅ | 名稱修改.txt 快速查找指南 |

### ⏳ Post-Demo Roadmap

1. ~~**Week 1**: Implement 3-level instant_attachments UI hierarchy~~ ✅ Done
2. ~~**Week 2**: Merged query (main skill + instant attachments)~~ ✅ Done
3. **Week 3**: Full OPMP integration for Skill system

### Recent Session Updates

- **2025-12-05**: SSE 上傳進度修復, 刪除來源功能遷移至 skill_config, UI 文字參考文件
- **2025-12-04**: skill_heads 架構重構完成, skill_config.json 依賴移除, 前端更新 (skill_config.html, skill_main.html)
- **2025-12-03**: skill_heads 表創建, API endpoints 新增, 資料遷移完成
- **2025-11-28 Afternoon**: Skill Names Sync, Re-Build Modal, FAISS Demo Mode
- **2025-11-28 Morning**: 3-Level Tree UI, Multi-Select Query, Source Name Fix
- **2025-11-27 Evening**: PDF processing pipeline completed (385 pages, 385 chunks)
- **2025-11-27 Morning**: Demo scripts fix, PDF upload UX fix
- **2025-11-26 Evening**: Loading spinner UI, Prompt response fix

## 7. Critical Files

- **PDF Processing**: `app/api/v1/endpoints/skills.py` (process_pdf_for_skill)
- **Skill Metadata**: `app/Providers/skill_metadata_provider/client.py` (含 skill_heads CRUD)
- **Vector Store**: `app/Providers/vector_store_provider/client.py`
- **Prompt Service**: `app/Services/prompt_service.py`
- **Skill UI**: `template/skill_main.html`, `template/skill_config.html`
- **Database**: `data/skill_metadata.db` (skill_heads + skill_metadata 表)
- **封存檔**: `scripts/skill_data/archive/skill_config.json.deprecated`

## 8. Language Requirement

- **Response Language**: Traditional Chinese (繁體中文).



