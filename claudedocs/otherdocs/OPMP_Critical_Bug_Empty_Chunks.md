# OPMP Critical Bug: Empty Chunk Content

**Date**: 2025-12-06
**Severity**: 🔴 **CRITICAL** - Complete retrieval failure
**Status**: 🔍 Root cause identified

---

## 🚨 Problem Summary

Progressive streaming completes all 5 phases successfully but displays **zero response content**. Progress bar reaches 100% with "✓ 工作達成" but chat area remains empty.

### Visual Evidence

1. **Screenshot 1**: Red completion bar at 100% - "✓ 工作達成"
2. **Screenshot 2**: Empty chat response area (no content displayed)
3. **Video**: User query → progress animation → completion → **no answer**

---

## 🔍 Root Cause Analysis

### Phase 2 Retrieval Returns Empty Chunks

```bash
curl /api/v1/skills/{skill_id}/chat/stream
```

**Response (Phase 2 result)**:
```json
{
  "type": "phase_result",
  "phase": 2,
  "data": {
    "chunks": [
      {
        "chunk_id": "skill_20251203_071733_2a43e5ac_src_00_chunk_24",
        "document_id": "skill_20251203_071733_2a43e5ac_src_00",
        "distance": 0.827,
        "score": 0.547,
        "content": "",  // ❌ EMPTY!
        "page": 0,
        "source_file": ""  // ❌ EMPTY!
      }
    ],
    "total_chunks_found": 5
  }
}
```

**All 5 retrieved chunks have empty `content` and `source_file` fields!**

---

## 🐛 Root Cause: Missing Metadata Provider Method

### Code Flow

```
Phase 2: SkillDocumentRetrieval._search_document_index()
    ↓
Line 329: chunks_metadata = await self._fetch_chunks_metadata(chunk_ids)
    ↓
Line 383: chunk_metadata = await self.metadata_provider.get_chunk_metadata(doc_id, chunk_idx)
    ↓
❌ METHOD DOES NOT EXIST in SkillMetadataProvider!
    ↓
Returns None → chunk content remains empty
    ↓
Phase 3: Context assembly with empty chunks
    ↓
Phase 4: LLM generates response with NO CONTEXT
    ↓
Phase 5: Completes successfully with empty response
```

### The Missing Method

**File**: `app/SkillServices/progressive_skill_streaming/phase2_skill_retrieval.py`
**Line 383**:
```python
chunk_metadata = await self.metadata_provider.get_chunk_metadata(
    doc_id,  # e.g., "skill_20251203_071733_2a43e5ac_src_00"
    chunk_idx  # e.g., 24
)
```

**Problem**: `SkillMetadataProvider` (in `app/Providers/skill_metadata_provider/client.py`) **does NOT implement `get_chunk_metadata()` method!**

**Result**: Method call silently fails → returns `None` → chunk content empty

---

## 📊 Database Schema Issue

### Current Schema (Likely)

```sql
CREATE TABLE skill_chunk_metadata (
    chunk_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,  -- ✅ Data exists here
    page INTEGER,
    source_file TEXT,
    created_at TEXT
)
```

### What Phase 2 Expects

```python
chunk_metadata = {
    "content": "...",  # ❌ Not "chunk_text"
    "page": 25,
    "source_file": "LLM_Handbook.pdf"
}
```

**Field Name Mismatch**: Database uses `chunk_text`, code expects `content`

---

## 🔧 Solution (3 Steps)

### Step 1: Add Missing Method to SkillMetadataProvider

**File**: `app/Providers/skill_metadata_provider/client.py`

**Add method** (around line 700):
```python
async def get_chunk_metadata(
    self,
    skill_id: str,
    chunk_index: int
) -> Optional[Dict[str, Any]]:
    """
    Get chunk metadata by skill_id and chunk_index

    Args:
        skill_id: Skill document identifier
        chunk_index: Chunk index (0-based)

    Returns:
        Dict with keys: content, page, source_file
        None if not found
    """
    conn = await self._get_connection()

    try:
        chunk_id = f"{skill_id}_chunk_{chunk_index}"

        query = """
            SELECT chunk_text, page, source_file
            FROM skill_chunk_metadata
            WHERE chunk_id = ?
        """

        async with conn.execute(query, (chunk_id,)) as cursor:
            row = await cursor.fetchone()

        if not row:
            logger.warning(f"Chunk not found: {chunk_id}")
            return None

        return {
            "content": row["chunk_text"],  # Map chunk_text → content
            "page": row["page"] or 0,
            "source_file": row["source_file"] or ""
        }

    except Exception as e:
        logger.error(f"Failed to get chunk metadata for {skill_id}[{chunk_index}]: {e}")
        return None
```

---

### Step 2: Verify Database Contains Data

```bash
sqlite3 data/skill_metadata.db

# Check if chunks exist
SELECT COUNT(*) FROM skill_chunk_metadata
WHERE skill_id = 'skill_20251203_071733_2a43e5ac_src_00';
# Expected: > 0

# Check chunk content
SELECT chunk_id, LENGTH(chunk_text), page, source_file
FROM skill_chunk_metadata
WHERE skill_id = 'skill_20251203_071733_2a43e5ac_src_00'
LIMIT 3;
# Expected: chunk_text should have length > 0
```

**If no data exists**: Need to re-run ingestion for this skill

---

### Step 3: Test Fix

```bash
# Restart server
./start_system.sh

# Test endpoint
curl -X POST http://localhost:8082/api/v1/skills/skill_20251203_071733_2a43e5ac_src_00/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"query":"什麼是LLM?","document_ids":["skill_20251203_071733_2a43e5ac_src_00"]}' \
  --no-buffer | grep -A 5 '"type": "phase_result", "phase": 2'

# Expected: chunks[0].content should have text (not empty)
```

---

## 🎯 Expected Behavior After Fix

### Phase 2 Response (Fixed)
```json
{
  "type": "phase_result",
  "phase": 2,
  "data": {
    "chunks": [
      {
        "chunk_id": "skill_20251203_071733_2a43e5ac_src_00_chunk_24",
        "content": "LLM stands for Large Language Model. It is a type of AI model...",  // ✅ HAS CONTENT!
        "page": 25,
        "source_file": "LLM_Handbook.pdf"  // ✅ HAS SOURCE!
      }
    ]
  }
}
```

### Phase 4 Response (Token Streaming)
```
data: {"type": "markdown_token", "token": "##"}
data: {"type": "markdown_token", "token": " "}
data: {"type": "markdown_token", "token": "什麼是"}
data: {"type": "markdown_token", "token": "LLM"}
data: {"type": "markdown_token", "token": "?\n\n"}
data: {"type": "markdown_token", "token": "LLM"}
data: {"type": "markdown_token", "token": " (Large Language Model)"}
```

### UI Display (Fixed)
```
User: 什麼是LLM?