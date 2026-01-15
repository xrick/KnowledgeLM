# Document Overview Solution - RAG Retrieval Failure Fix

## Problem Analysis

### Issue Observed
User reported: "有文件卻回應沒有文件" (Files exist but response says no files found)

![Error Screenshot](../refData/errors/images/有文件卻回應沒有文件_1.png)

The user:
- Has 2 files checked in sidebar: `2006_CTC_Conn...` and `2022_Whisper_v...`
- Sent 3 requests asking for summaries
- **All 3 responses said "no content found" despite files being selected**

### Root Cause

**FAISS indices directory was EMPTY!**

```bash
$ ls -la data/faiss_indices/
total 0
drwxr-xr-x@ 2 xrickliao  staff   64 Nov 22 03:00 .
drwxr-xr-x@ 5 xrickliao  staff  160 Nov 22 03:00 ..
# NO FILES!
```

While SQLite `file_metadata` table showed `embedding_status=completed`, the actual vector stores were never persisted or were deleted. When the server restarted, `_load_all_faiss_stores()` found nothing to load.

---

## Solution Architecture

### 1. Document Overview System

Created a **document-level overview** system that:
- Generates a concise overview (200-300 chars) during file upload
- Stores overview in SQLite with `file_id` reference
- Provides fallback context when vector search fails

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCUMENT OVERVIEW SYSTEM                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  File Upload                                                    │
│      │                                                          │
│      ├─► Extract Text                                           │
│      ├─► Chunk Text                                             │
│      ├─► Generate Embeddings → FAISS Store                      │
│      └─► Generate Overview → SQLite (NEW!)                      │
│                                                                 │
│  Chat Query                                                     │
│      │                                                          │
│      ├─► Get Document Overviews (SQLite)                        │
│      ├─► Try Vector Search (FAISS)                              │
│      │     │                                                    │
│      │     ├─► Chunks Found → Use chunks                        │
│      │     └─► No Chunks → FALLBACK to overviews                │
│      │                                                          │
│      └─► Build Prompt with context                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2. New Database Table

Added `document_overviews` table to SQLite:

```sql
CREATE TABLE IF NOT EXISTS document_overviews (
    file_id TEXT PRIMARY KEY,
    overview TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES file_metadata(file_id)
);
```

### 3. Modified RAG Pipeline

The chat endpoint now:
1. **Gets document overviews first** (fast, reliable SQLite lookup)
2. **Tries vector search** (may fail if FAISS not loaded)
3. **Falls back to overviews** if no chunks found

```python
# Step 2.1: Get document overviews first
overviews = await overview_service.get_multiple_overviews(
    file_metadata_provider=file_metadata_provider,
    file_ids=request.file_ids
)

# Step 2.2: Try vector retrieval
retrieval_results = await asyncio.gather(*retrieval_tasks)

# Step 2.3: FALLBACK - If no chunks found, use document overviews
if len(context_chunks) == 0 and overviews:
    for file_id, overview in overviews.items():
        context_chunks.append({
            "content": f"[文件概述 - {file_id}]\n{overview}",
            "metadata": {"file_id": file_id, "source": "overview"}
        })
```

### 4. Sequential Multi-Document Processing

Added new endpoint for sequential document summaries:

```
POST /api/v1/chat/sequential-summary
```

This processes each document one-by-one, which is more reliable for:
- Large documents
- Multiple documents
- When parallel processing fails

---

## Files Modified

| File | Changes |
|------|---------|
| `app/Services/document_overview_service.py` | **NEW** - Overview generation and storage |
| `app/api/v1/endpoints/upload.py` | Added overview generation on upload |
| `app/api/v1/endpoints/chat.py` | Added overview fallback, sequential endpoint |
| `app/Providers/file_metadata_provider/client.py` | Table created on-demand |

---

## New API Endpoints

### Sequential Summary Endpoint

```http
POST /api/v1/chat/sequential-summary
Content-Type: application/json

{
  "query": "請分別幫我摘要這些文件",
  "session_id": "session_xyz",
  "file_ids": ["file_1", "file_2"]
}
```

**Response:**
```json
{
  "session_id": "session_xyz",
  "query": "請分別幫我摘要這些文件",
  "summaries": [
    {
      "file_id": "file_1",
      "filename": "2006_CTC_Conn...",
      "summary": "..."
    },
    {
      "file_id": "file_2",
      "filename": "2022_Whisper_v...",
      "summary": "..."
    }
  ],
  "combined_summary": "整合觀點...",
  "metadata": {
    "document_count": 2,
    "processing_mode": "sequential"
  }
}
```

---

## User Impact

### Before Fix
- Files uploaded successfully
- Files appear in sidebar
- Queries return "no content found"
- User confused: "有文件卻回應沒有文件"

### After Fix
1. **Immediate fallback**: If vector search fails, use document overviews
2. **Graceful degradation**: Always provide some context to LLM
3. **Sequential option**: Use `/sequential-summary` for reliable per-document summaries
4. **Better logging**: Clear warnings when fallback is triggered

---

## How to Re-Index Existing Files

For existing files without overviews, re-upload them to generate overviews:

```bash
# Example: Re-upload to generate overview
curl -X POST "http://localhost:8000/api/v1/upload" \
  -H "X-User-ID: 5a19a0da-7485-4656-8641-41402fef4049" \
  -F "file=@document.pdf"
```

Or manually generate overviews for existing files (future enhancement).

---

## Monitoring

Watch for these log messages:

```
# Normal operation
INFO: Retrieved 3 document overviews for 3 files
INFO: Retrieved 15 unique context chunks from vector search

# Fallback triggered (indicates FAISS issue)
WARNING: No chunks from vector search, falling back to 3 document overviews

# Overview generation
INFO: Generated overview for file_xxx: 280 chars
INFO: Document overview generated and stored for file_xxx
```

---

## RAG PIPELINE FLOW - Complete Architecture

### Pipeline Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RAG PIPELINE FLOW                                   │
│                                                                             │
│  User Query → Query Expansion → Get Overview → Build Prompt → LLM          │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐                                                            │
│  │ User Query  │  "請幫我摘要這份文件"                                        │
│  └──────┬──────┘                                                            │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────┐                                │
│  │  PHASE 1: Query Understanding           │                                │
│  │  ┌───────────────────────────────────┐  │                                │
│  │  │  Query Expansion (Strategy 2)     │  │                                │
│  │  │  • Detect intent (summary/QA)     │  │                                │
│  │  │  • Generate sub-questions         │  │                                │
│  │  │  • Select best query              │  │                                │
│  │  └───────────────────────────────────┘  │                                │
│  │  Code: iterative_expansion_service.     │                                │
│  │        expand_iteratively()             │                                │
│  │  File: chat.py:196-210                  │                                │
│  └──────────────┬──────────────────────────┘                                │
│                 │                                                           │
│                 │  expanded_questions[], best_query                         │
│                 ▼                                                           │
│  ┌─────────────────────────────────────────┐                                │
│  │  PHASE 2: Parallel Retrieval            │                                │
│  │                                         │                                │
│  │  ┌─────────────────┐ ┌───────────────┐  │                                │
│  │  │  Get Overviews  │ │ Vector Search │  │                                │
│  │  │  (SQLite)       │ │ (FAISS)       │  │                                │
│  │  │                 │ │               │  │                                │
│  │  │  Reliable ✓     │ │ May fail ⚠    │  │                                │
│  │  └────────┬────────┘ └───────┬───────┘  │                                │
│  │           │                  │          │                                │
│  │           │         ┌───────▼────────┐  │                                │
│  │           │         │ Chunks found?  │  │                                │
│  │           │         └───────┬────────┘  │                                │
│  │           │            Yes  │  No       │                                │
│  │           │           ┌─────┴─────┐     │                                │
│  │           │           ▼           ▼     │                                │
│  │           │      Use Chunks   FALLBACK  │                                │
│  │           │           │       to        │                                │
│  │           └───────────┼───►Overviews    │                                │
│  │                       │                 │                                │
│  │  Code: overview_service.get_multiple_   │                                │
│  │        overviews()                      │                                │
│  │        retrieval_service.retrieve_      │                                │
│  │        context()                        │                                │
│  │  File: chat.py:242-283                  │                                │
│  └──────────────┬──────────────────────────┘                                │
│                 │                                                           │
│                 │  context_chunks[]                                         │
│                 ▼                                                           │
│  ┌─────────────────────────────────────────┐                                │
│  │  PHASE 3: Context Assembly              │                                │
│  │  ┌───────────────────────────────────┐  │                                │
│  │  │  Build RAG Prompt                 │  │                                │
│  │  │  • System prompt (language)       │  │                                │
│  │  │  • Context chunks/overviews       │  │                                │
│  │  │  • Chat history (last 10 msgs)    │  │                                │
│  │  │  • User query                     │  │                                │
│  │  └───────────────────────────────────┘  │                                │
│  │  Code: prompt_service.build_rag_prompt()│                                │
│  │  File: chat.py:312-318                  │                                │
│  └──────────────┬──────────────────────────┘                                │
│                 │                                                           │
│                 │  messages[]                                               │
│                 ▼                                                           │
│  ┌─────────────────────────────────────────┐                                │
│  │  PHASE 4: Response Generation           │                                │
│  │  ┌───────────────────────────────────┐  │                                │
│  │  │  LLM Streaming (OPMP)             │  │                                │
│  │  │  • Send messages to LLM           │  │                                │
│  │  │  • Stream tokens via SSE          │  │                                │
│  │  │  • Progressive markdown render    │  │                                │
│  │  └───────────────────────────────────┘  │                                │
│  │  Code: llm_client.get_chat_completion_  │                                │
│  │        stream()                         │                                │
│  │  File: chat.py:338-371                  │                                │
│  └──────────────┬──────────────────────────┘                                │
│                 │                                                           │
│                 │  full_response                                            │
│                 ▼                                                           │
│  ┌─────────────────────────────────────────┐                                │
│  │  PHASE 5: Post Processing               │                                │
│  │  • Save user message to history         │                                │
│  │  • Save assistant response to history   │                                │
│  │  • Return completion event              │                                │
│  │  File: chat.py:391-436                  │                                │
│  └─────────────────────────────────────────┘                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Pipeline Summary Table

| Phase | Operation | Service/Method | File:Line |
|-------|-----------|----------------|-----------|
| 1 | User Query Input | `ChatRequest.query` | chat.py:57-67 |
| 1 | Query Expansion | `iterative_expansion_service.expand_iteratively()` | chat.py:196-210 |
| 2 | Get Overviews | `overview_service.get_multiple_overviews()` | chat.py:242-246 |
| 2 | Vector Search | `retrieval_service.retrieve_context()` | chat.py:252-271 |
| 2 | Fallback Logic | If no chunks → use overviews | chat.py:276-283 |
| 3 | Build Prompt | `prompt_service.build_rag_prompt()` | chat.py:312-318 |
| 4 | LLM Response | `llm_client.get_chat_completion_stream()` | chat.py:338-371 |
| 5 | Save History | `chat_history_provider.add_message()` | chat.py:391-411 |

### Key Design Decisions

1. **Query Expansion BEFORE Retrieval**: Generates multiple sub-questions to improve recall
2. **Overview Fetch BEFORE Vector Search**: Ensures fallback is always ready
3. **Parallel Operations**: Overview fetch and vector search can run concurrently
4. **Graceful Degradation**: System always provides some context to LLM

---

## Future Improvements

1. **Batch Overview Generation**: Script to generate overviews for all existing files
2. **Overview Refresh**: Endpoint to regenerate overview for a specific file
3. **Hybrid Retrieval**: Always include overview + chunks for better context
4. **Overview Caching**: Redis cache for frequently accessed overviews

---

*Resolution documented: 2024-11-22*
