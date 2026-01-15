# Implementation Guide: Index Integrity Enhancement

**Date**: 2025-12-11
**Purpose**: Complete implementation guide for FAISS index integrity system
**Status**: Partially Implemented - Integration Required

---

## ✅ Completed Components

### 1. Database Schema ✅
**File**: `data/skill_metadata.db`

Added columns to `skill_metadata` table:
- `processing_status` TEXT DEFAULT 'completed'
- `indexed_chunks` INTEGER DEFAULT 0
- `last_error` TEXT DEFAULT NULL
- `processing_started_at` TEXT
- `processing_completed_at` TEXT

**Index**: Created `idx_processing_status` for query performance

### 2. SkillMetadataProvider Enhancements ✅
**File**: `app/Providers/skill_metadata_provider/client.py` (Lines 532-688)

**New Methods**:
```python
async def update_processing_status(skill_id, status, indexed_chunks, error)
async def get_incomplete_skills() -> List[Dict]
async def reset_failed_skills() -> int
```

**Usage**:
```python
# Start processing
await metadata_provider.update_processing_status(
    skill_id="skill_123",
    status="processing",
    indexed_chunks=0
)

# Update progress
await metadata_provider.update_processing_status(
    skill_id="skill_123",
    status="processing",
    indexed_chunks=25
)

# Mark complete
await metadata_provider.update_processing_status(
    skill_id="skill_123",
    status="completed",
    indexed_chunks=65
)
```

### 3. Index Integrity Verification ✅
**File**: `app/SkillServices/index_integrity.py` (NEW)

**Functions**:
```python
async def verify_index_integrity(skill_id, expected_chunks) -> Tuple[bool, int, str]
async def get_index_stats(skill_id) -> dict
async def diagnose_incomplete_index(skill_id, expected_chunks) -> dict
```

---

## 🔧 Remaining Integration Steps

### STEP A: Integrate into process_pdf_for_skill()

**File**: `app/api/v1/endpoints/skills.py`
**Location**: Lines 628-821 (process_pdf_for_skill function)

**Add imports**:
```python
from app.SkillServices.index_integrity import verify_index_integrity, diagnose_incomplete_index
from app.Providers.skill_metadata_provider.client import SkillMetadataProvider
```

**Modify process_pdf_for_skill()** - Add verification after FAISS storage:

```python
async def process_pdf_for_skill(
    pdf_path: Path,
    skill_name: str,
    head_id: Optional[str] = None,
    skill_config: Optional[Dict] = None
) -> Dict[str, Any]:
    """Process PDF with integrity verification"""

    metadata_provider = SkillMetadataProvider()

    try:
        # ========== PHASE 1: Initialize ==========
        skill_id = generate_skill_id()

        # Set status to 'processing'
        await metadata_provider.update_processing_status(
            skill_id=skill_id,
            status="processing",
            indexed_chunks=0
        )

        # ========== PHASE 2: Extract Text ==========
        chunks = await extract_text_from_pdf(pdf_path)

        # ========== PHASE 3: Generate Embeddings ==========
        embeddings = await embedding_provider.generate_embeddings(chunks)

        # Update progress
        await metadata_provider.update_processing_status(
            skill_id=skill_id,
            status="processing",
            indexed_chunks=len(embeddings)
        )

        # ========== PHASE 4: Store in FAISS ==========
        await skill_ingestion_service.add_content(
            content_id=skill_id,
            chunks=chunks,
            embeddings=embeddings
        )

        # ========== PHASE 5: VERIFY INDEX INTEGRITY ==========
        is_valid, actual_vectors, error = await verify_index_integrity(
            skill_id=skill_id,
            expected_chunks=len(chunks)
        )

        if not is_valid:
            # Integrity check failed - mark as failed
            await metadata_provider.update_processing_status(
                skill_id=skill_id,
                status="failed",
                indexed_chunks=actual_vectors,
                error=error
            )

            # Get diagnostic information
            diagnosis = await diagnose_incomplete_index(
                skill_id=skill_id,
                expected_chunks=len(chunks)
            )

            logger.error(f"Index integrity verification failed: {diagnosis}")

            raise ValueError(
                f"FAISS index verification failed for {skill_id}. "
                f"Expected {len(chunks)} vectors, got {actual_vectors}. "
                f"Diagnosis: {diagnosis['recommendations']}"
            )

        # ========== PHASE 6: Mark as completed ==========
        await metadata_provider.update_processing_status(
            skill_id=skill_id,
            status="completed",
            indexed_chunks=len(chunks)
        )

        logger.info(
            f"✅ PDF processing completed successfully for {skill_id}: "
            f"{len(chunks)} chunks indexed and verified"
        )

        return {
            "skill_id": skill_id,
            "status": "success",
            "pages_extracted": len(chunks),
            "chunks_created": len(chunks),
            "indexed_chunks": actual_vectors,
            "integrity_verified": True
        }

    except Exception as e:
        # Mark as failed
        if 'skill_id' in locals():
            await metadata_provider.update_processing_status(
                skill_id=skill_id,
                status="failed",
                error=str(e)
            )

        logger.error(f"PDF processing failed: {str(e)}")
        raise
```

---

### STEP B: Create Background Integrity Checker

**File**: `app/SkillServices/background_integrity_checker.py` (NEW)

```python
"""
Background Integrity Checker

Periodically scans for incomplete FAISS indices and attempts recovery.
Runs as a background task in FastAPI.
"""

import logging
import asyncio
from typing import List
from app.Providers.skill_metadata_provider.client import SkillMetadataProvider
from app.SkillServices.index_integrity import verify_index_integrity, diagnose_incomplete_index

logger = logging.getLogger(__name__)


async def check_and_repair_indices():
    """
    Background task to check and repair incomplete indices

    Runs periodically to:
    1. Find skills with incomplete processing
    2. Verify index integrity
    3. Log issues for manual intervention
    """
    metadata_provider = SkillMetadataProvider()

    try:
        # Find incomplete skills
        incomplete_skills = await metadata_provider.get_incomplete_skills()

        if not incomplete_skills:
            logger.info("✅ No incomplete skills found - all indices healthy")
            return

        logger.warning(
            f"⚠️  Found {len(incomplete_skills)} skills with potential integrity issues"
        )

        for skill in incomplete_skills:
            skill_id = skill['skill_id']
            expected_chunks = skill['total_chunks']
            indexed_chunks = skill['indexed_chunks']

            logger.info(
                f"Checking skill {skill_id}: "
                f"{indexed_chunks}/{expected_chunks} chunks indexed"
            )

            # Verify FAISS index
            is_valid, actual_vectors, error = await verify_index_integrity(
                skill_id=skill_id,
                expected_chunks=expected_chunks
            )

            if not is_valid:
                # Get detailed diagnosis
                diagnosis = await diagnose_incomplete_index(
                    skill_id=skill_id,
                    expected_chunks=expected_chunks
                )

                logger.error(
                    f"❌ Index integrity issue for {skill_id}:\\n"
                    f"   Expected: {expected_chunks}\\n"
                    f"   Actual: {actual_vectors}\\n"
                    f"   Completion: {diagnosis['completion_percent']:.1f}%\\n"
                    f"   Recommendations: {diagnosis['recommendations']}"
                )

                # Update database with current status
                await metadata_provider.update_processing_status(
                    skill_id=skill_id,
                    status="failed",
                    indexed_chunks=actual_vectors,
                    error=f"Incomplete index: {actual_vectors}/{expected_chunks} vectors"
                )

    except Exception as e:
        logger.error(f"Background integrity checker failed: {str(e)}")


async def start_background_checker(interval_seconds: int = 3600):
    """
    Start background integrity checker loop

    Args:
        interval_seconds: Check interval (default 1 hour)
    """
    logger.info(
        f"Starting background integrity checker "
        f"(interval: {interval_seconds}s / {interval_seconds/60:.1f}min)"
    )

    while True:
        try:
            await check_and_repair_indices()
        except Exception as e:
            logger.error(f"Error in integrity checker loop: {str(e)}")

        # Wait before next check
        await asyncio.sleep(interval_seconds)
```

**Integration into main.py**:
```python
# app/main.py

from app.SkillServices.background_integrity_checker import start_background_checker

@app.on_event("startup")
async def startup_event():
    """Start background tasks on server startup"""

    # Start index integrity checker (runs every hour)
    asyncio.create_task(start_background_checker(interval_seconds=3600))

    logger.info("✅ Background integrity checker started")
```

---

### STEP C: Add API Endpoint for Manual Integrity Check

**File**: `app/api/v1/endpoints/skills.py`

```python
@router.get("/integrity-check")
async def check_index_integrity(
    skill_id: Optional[str] = None,
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider)
):
    """
    Manual integrity check endpoint

    Query params:
        skill_id: Optional - check specific skill, or all if omitted
    """
    from app.SkillServices.index_integrity import verify_index_integrity, diagnose_incomplete_index

    if skill_id:
        # Check single skill
        skill_metadata = await metadata_provider.get_skill(skill_id)

        if not skill_metadata:
            raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

        expected_chunks = skill_metadata['total_chunks']

        is_valid, actual_vectors, error = await verify_index_integrity(
            skill_id=skill_id,
            expected_chunks=expected_chunks
        )

        if not is_valid:
            diagnosis = await diagnose_incomplete_index(skill_id, expected_chunks)
            return {
                "skill_id": skill_id,
                "status": "failed",
                "diagnosis": diagnosis
            }

        return {
            "skill_id": skill_id,
            "status": "ok",
            "vectors": actual_vectors,
            "expected": expected_chunks
        }

    else:
        # Check all skills
        incomplete_skills = await metadata_provider.get_incomplete_skills()

        results = []
        for skill in incomplete_skills:
            skill_id = skill['skill_id']
            expected = skill['total_chunks']

            is_valid, actual, error = await verify_index_integrity(skill_id, expected)

            results.append({
                "skill_id": skill_id,
                "skill_name": skill['skill_name'],
                "expected_chunks": expected,
                "actual_vectors": actual,
                "is_valid": is_valid,
                "error": error
            })

        return {
            "total_skills_checked": len(incomplete_skills),
            "results": results
        }
```

---

## 🧪 Testing Steps

### 1. Test Progress Tracking
```python
# Test script: scripts/test_progress_tracking.py
import asyncio
from app.Providers.skill_metadata_provider.client import SkillMetadataProvider

async def test():
    provider = SkillMetadataProvider()

    # Update status
    await provider.update_processing_status(
        skill_id="test_skill",
        status="processing",
        indexed_chunks=25
    )

    # Check incomplete
    incomplete = await provider.get_incomplete_skills()
    print(f"Incomplete skills: {len(incomplete)}")

asyncio.run(test())
```

### 2. Test Index Verification
```bash
# Use existing Gorgon Point skill
docaienv/bin/python3 -c "
import asyncio
from app.SkillServices.index_integrity import verify_index_integrity, diagnose_incomplete_index

async def test():
    is_valid, count, error = await verify_index_integrity(
        'skill_20251211_075133_48af4341_5c6743',
        65
    )
    print(f'Valid: {is_valid}, Count: {count}, Error: {error}')

    if not is_valid:
        diagnosis = await diagnose_incomplete_index(
            'skill_20251211_075133_48af4341_5c6743',
            65
        )
        print(f'Diagnosis: {diagnosis}')

asyncio.run(test())
"
```

### 3. Test Background Checker
```bash
# Run once manually
docaienv/bin/python3 -c "
import asyncio
from app.SkillServices.background_integrity_checker import check_and_repair_indices

asyncio.run(check_and_repair_indices())
"
```

### 4. End-to-End Test
```bash
# Upload a new PDF and verify full pipeline
curl -F "file=@test.pdf" -F "skill_name=TestSkill" \\
  http://localhost:8765/api/v1/skills/upload-source

# Check integrity
curl http://localhost:8765/api/v1/skills/integrity-check?skill_id=skill_xxx
```

---

## 📝 Summary

**Completed**:
- ✅ Database schema updates
- ✅ SkillMetadataProvider progress tracking methods
- ✅ Index integrity verification module

**Remaining** (Copy-paste ready code above):
- 📋 Integrate verification into process_pdf_for_skill()
- 📋 Create background_integrity_checker.py
- 📋 Add API endpoint for manual checks
- 📋 Update main.py to start background task

**Estimated Time**: 30 minutes for remaining integration

**Priority**: HIGH - Prevents future data loss issues

---

## 🔗 Related Files

**Modified**:
- `data/skill_metadata.db` - Schema updated
- `app/Providers/skill_metadata_provider/client.py` - Progress tracking added

**Created**:
- `app/SkillServices/index_integrity.py` - Verification functions

**Pending Creation**:
- `app/SkillServices/background_integrity_checker.py`

**Pending Modification**:
- `app/api/v1/endpoints/skills.py` - Add verification to process_pdf_for_skill()
- `app/main.py` - Start background checker

---

**Status**: 🟡 70% Complete - Integration code provided above for completion
