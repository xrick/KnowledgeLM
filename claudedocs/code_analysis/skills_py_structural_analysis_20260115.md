# `skills.py` Structural Analysis Report

**Analysis Date**: 2026-01-15  
**File Path**: `app/api/v1/endpoints/skills.py`  
**Total Lines**: ~5,150  
**Purpose**: Comprehensive structural analysis for modular refactoring

---

## Executive Summary

This monolithic file contains the entire Skill Management API for the DocAI RAG system. It has grown to over 5,000 lines and requires refactoring into smaller, cohesive modules based on **Vertical Slicing** (feature-based organization).

### Key Statistics

| Metric | Count |
|:---|:---|
| **Pydantic Models** | 14 |
| **Route Handlers** | 38 |
| **Helper Functions** | 10 |
| **Constants** | 4 |
| **Total Lines** | ~5,150 |
| **Recommended Modules** | 15 |

---

## Feature Group Classification Table

### Shared/Common Utilities

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Constant | `PROJECT_ROOT` | Project root directory path |
| Constant | `SKILL_CONFIG_PATH` | Skill config file path |
| Constant | `router` | FastAPI APIRouter instance |
| Constant | `logger` | Module logger instance |
| Function | `load_skill_config()` | Load skill_config.json |
| Function | `save_skill_config()` | Save skill_config.json |
| Function | `sanitize_filename()` | Sanitize filename (prevent path traversal) |
| Function | `check_zip_safety()` | ZIP security check (prevent ZIP bomb) |

---

### Data Models - Skill Core

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Model | `SkillCreateRequest` | Create Skill request payload |
| Model | `SkillResponse` | Skill response format |
| Model | `SkillChatRequest` | Skill chat request payload |
| Model | `SkillChatResponse` | Skill chat response format |

---

### Data Models - PDF/Config

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Model | `PDFSourceModel` | PDF source definition |
| Model | `SkillConfigModel` | Skill configuration model |
| Model | `AddSourceRequest` | Add PDF source request |
| Model | `InstantAttachmentRequest` | Instant attachment request |
| Model | `RebuildRequest` | Rebuild request payload |
| Model | `RebuildThresholdRequest` | Rebuild threshold request |

---

### Data Models - Skill Heads

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Model | `SkillHeadCreateRequest` | Create Skill Head request |
| Model | `SkillHeadUpdateRequest` | Update Skill Head request |
| Model | `SkillOrderItem` | Skill order item for reordering |
| Model | `ReorderSkillsRequest` | Reorder skills request |

---

### Data Models - Other

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Model | `TranslationRequest` | Translation request payload |
| Model | `TranslationResponse` | Translation response format |
| Model | `RenameRequest` | Rename skill request |
| Model | `ProgressiveStreamRequest` | Progressive streaming request |

---

### Skill CRUD

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `GET /` → `list_skills()` | List all Skills |
| Route | `POST /upload` → `create_skill()` | Create Skill from text content |
| Route | `DELETE /{skill_id}` → `delete_skill_complete()` | Complete delete (FAISS+DB+PDF) |
| Route | `PUT /{skill_id}/rename` → `rename_skill()` | Rename a Skill |

---

### Skill Heads Management

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `GET /heads` → `list_skill_heads()` | List all Skill Heads |
| Route | `POST /heads` → `create_skill_head()` | Create new Skill Head |
| Route | `GET /heads/{head_id}` → `get_skill_head()` | Get single Skill Head |
| Route | `PUT /heads/{head_id}` → `update_skill_head()` | Update Skill Head |
| Route | `DELETE /heads/{head_id}` → `delete_skill_head()` | Delete Skill Head |
| Route | `GET /tree` → `get_skill_tree()` | Get complete skill tree |
| Route | `POST /migrate` → `run_migration()` | Run data migration |

---

### Demo/Query Endpoints

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `GET /demo` → `get_demo_skills()` | Get Demo Skills (with icon mapping) |
| Route | `POST /demo/query` → `query_demo_skill()` | Demo query (multi-select, Memory) |
| Route | `POST /chat` → `chat_with_skills()` | Basic Skill chat |

---

### PDF Processing Pipeline

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Function | `process_pdf_for_skill()` | PDF processing core (extract→embed→FAISS→SQLite) |
| Function | `process_pdf_for_skill_streaming()` | Streaming PDF processing (SSE progress) |
| Function | `_producer_loop()` | Producer Thread (read PDF pages) |
| Function | `create_upload_sse_event()` | Create SSE event dict |

---

### PDF Upload Endpoints

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `POST /config/skills/{skill_name}/upload-source` → `upload_source_to_skill()` | Upload PDF (unified streaming mode) |
| Route | `POST /config/skills/{skill_name}/upload-source-stream` → `upload_source_to_skill_stream()` | Upload PDF (streaming mode) |

---

### Config Management (DEPRECATED)

> ⚠️ **Note**: These endpoints are deprecated. Use `/tree` and `/heads` endpoints instead.

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `GET /config` → `get_skill_config()` | Get config (deprecated, use /tree) |
| Route | `GET /config/skills` → `get_config_skills()` | Get skills from config (deprecated) |
| Route | `POST /config/skills` → `add_skill_to_config()` | Add Skill to config (deprecated, use /heads) |
| Route | `POST /config/skills/{skill_name}/sources` → `add_source_to_skill()` | Add source to Skill |
| Route | `DELETE /config/skills/{skill_name}/sources` → `remove_source_from_skill()` | Remove source |
| Route | `DELETE /config/skills/{skill_name}` → `delete_skill_by_name()` | Delete Skill by name |

---

### Instant Attachments

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `GET /config/instant-attachments` → `get_instant_attachments()` | Get instant attachments list |
| Route | `POST /config/instant-attachments` → `add_instant_attachment()` | Add instant attachment |
| Route | `DELETE /config/instant-attachments` → `clear_instant_attachments()` | Clear instant attachments |

---

### Rebuild/Reorder

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `POST /rebuild` → `trigger_rebuild()` | Trigger Skill rebuild |
| Route | `GET /rebuild/status` → `get_rebuild_status()` | Check rebuild status |
| Route | `PUT /config/rebuild-threshold` → `update_rebuild_threshold()` | Update rebuild threshold |
| Route | `PUT /config/reorder` → `reorder_skills()` | Reorder Skills |

---

### PDF Browser

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `GET /available-pdfs` → `get_available_pdfs()` | Scan available PDF files |

---

### Index Integrity

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `GET /integrity-check` → `check_index_integrity()` | Check FAISS index integrity |

---

### Translation Service

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `POST /translate` → `translate_texts()` | LLM translation service |

---

### Progressive Streaming (OPMP)

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `POST /{skill_id}/chat/stream` → `stream_skill_chat()` | Progressive streaming chat (5 phases) |
| Route | `POST /acknowledge/{session_id}/{phase}` → `acknowledge_phase_completion()` | Phase completion acknowledgment |

---

### Session Management

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `DELETE /sessions/{session_id}` → `delete_session()` | Delete specific Session |
| Route | `DELETE /sessions/skill/{skill_id}` → `clear_skill_sessions()` | Clear Skill-related Sessions |
| Route | `POST /sessions/clear-all` → `clear_all_sessions()` | Clear all Sessions |
| Route | `GET /sessions/list` → `list_all_sessions()` | List all Sessions |

---

### Export/Import

| Component Type | Component Name | Purpose / Responsibility |
|:---|:---|:---|
| Route | `GET /config/skills/export/{head_id}` → `export_skill()` | Export Skill (ZIP) |
| Route | `POST /config/skills/preview` → `preview_skill_import()` | Preview import |
| Route | `POST /config/skills/import` → `import_skill()` | Import Skill (ZIP) |

---

## Recommended Module Structure

Based on the analysis above, the recommended refactoring structure is:

```
app/api/v1/endpoints/skills/
├── __init__.py              # Router integration & exports
├── models.py                # All Pydantic Models (14 models)
├── utils.py                 # Shared utilities (load/save config, sanitize, etc.)
├── crud.py                  # Skill CRUD operations (list, create, delete, rename)
├── heads.py                 # Skill Heads management (7 routes)
├── demo.py                  # Demo endpoints (get_demo_skills, query_demo_skill)
├── chat.py                  # Chat endpoints (chat_with_skills)
├── pdf_processing.py        # PDF processing pipeline (process_pdf_for_skill, streaming)
├── upload.py                # PDF upload endpoints
├── config_legacy.py         # DEPRECATED config endpoints (marked for removal)
├── instant_attachments.py   # Instant attachment management
├── rebuild.py               # Rebuild/reorder operations
├── integrity.py             # Index integrity check
├── streaming.py             # Progressive streaming (OPMP)
├── sessions.py              # Session management
└── export_import.py         # Export/Import functionality
```

---

## Module Size Estimates

| Module | Estimated Lines | Routes/Functions |
|:---|:---|:---|
| `models.py` | ~150 | 14 models |
| `utils.py` | ~100 | 4 functions + constants |
| `crud.py` | ~200 | 4 routes |
| `heads.py` | ~250 | 7 routes |
| `demo.py` | ~350 | 3 routes |
| `chat.py` | ~100 | 1 route |
| `pdf_processing.py` | ~600 | 4 functions |
| `upload.py` | ~200 | 2 routes |
| `config_legacy.py` | ~300 | 6 routes (deprecated) |
| `instant_attachments.py` | ~150 | 3 routes |
| `rebuild.py` | ~250 | 4 routes |
| `integrity.py` | ~100 | 1 route |
| `streaming.py` | ~300 | 2 routes |
| `sessions.py` | ~150 | 4 routes |
| `export_import.py` | ~800 | 3 routes |

---

## Dependencies Between Modules

```
┌─────────────────────────────────────────────────────────────┐
│                        __init__.py                          │
│                    (Router Integration)                     │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   ┌─────────┐          ┌──────────┐         ┌──────────┐
   │ models  │◄─────────│  utils   │─────────►│  crud    │
   └─────────┘          └──────────┘         └──────────┘
        │                     │                     │
        │                     ▼                     │
        │              ┌──────────┐                 │
        └──────────────│  heads   │◄────────────────┘
                       └──────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   ┌─────────┐          ┌──────────┐         ┌──────────┐
   │  demo   │          │   chat   │         │ streaming│
   └─────────┘          └──────────┘         └──────────┘
        │
        ▼
   ┌───────────────┐
   │pdf_processing │◄───────┐
   └───────────────┘        │
        │                   │
        ▼                   │
   ┌─────────┐         ┌────────────┐
   │ upload  │─────────│export_import│
   └─────────┘         └────────────┘
```

---

## Refactoring Priority

### Phase 1: High Priority (Immediate)
1. **`models.py`** - Extract all Pydantic models (no dependencies)
2. **`utils.py`** - Extract shared utilities
3. **`crud.py`** - Core CRUD operations

### Phase 2: Medium Priority
4. **`heads.py`** - Skill Heads management (new architecture)
5. **`demo.py`** - Demo endpoints
6. **`chat.py`** - Chat functionality

### Phase 3: Feature Extraction
7. **`pdf_processing.py`** - PDF processing pipeline
8. **`upload.py`** - Upload endpoints
9. **`streaming.py`** - OPMP streaming

### Phase 4: Cleanup
10. **`config_legacy.py`** - Mark deprecated, plan removal
11. **`instant_attachments.py`** - Attachment management
12. **`rebuild.py`** - Rebuild operations
13. **`sessions.py`** - Session management
14. **`export_import.py`** - Export/Import
15. **`integrity.py`** - Index integrity

---

## Notes

1. **Backward Compatibility**: The deprecated `config_legacy.py` endpoints should remain functional but emit deprecation warnings.

2. **Router Integration**: The `__init__.py` should use `include_router()` with appropriate prefixes to maintain existing API paths.

3. **Shared Dependencies**: All modules will depend on:
   - `app.Providers.skill_metadata_provider`
   - `app.Providers.vector_store_provider`
   - `app.Services.prompt_service`

4. **Testing Strategy**: Each module should have corresponding test files in `tests/api/v1/endpoints/skills/`.

---

*Generated by Claude Code Analysis - 2026-01-15*
