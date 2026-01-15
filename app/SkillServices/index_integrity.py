# app/SkillServices/index_integrity.py
"""
FAISS Index Integrity Verification

Provides functions to verify and ensure FAISS indices are complete and consistent
with SQLite metadata. Critical for preventing data loss issues.

Created: 2025-12-11
Purpose: Fix Thunderbolt 4 issue - FAISS index incompleteness
"""

import logging
import faiss
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


async def verify_index_integrity(
    skill_id: str,
    expected_chunks: int,
    faiss_indices_path: str = "data/faiss_indices/skills"
) -> Tuple[bool, int, Optional[str]]:
    """
    Verify FAISS index contains expected number of vectors

    Args:
        skill_id: Skill identifier
        expected_chunks: Expected number of chunks from database
        faiss_indices_path: Base path to FAISS indices

    Returns:
        Tuple of (is_valid, actual_vectors, error_message)

    Example:
        >>> is_valid, count, error = await verify_index_integrity("skill_123", 65)
        >>> if not is_valid:
        ...     logger.error(f"Index integrity failed: {error}")
    """
    index_path = Path(faiss_indices_path) / skill_id / "index.faiss"

    try:
        if not index_path.exists():
            error_msg = f"FAISS index file not found: {index_path}"
            logger.error(error_msg)
            return False, 0, error_msg

        # Load FAISS index
        index = faiss.read_index(str(index_path))
        actual_vectors = index.ntotal

        if actual_vectors != expected_chunks:
            error_msg = (
                f"❌ Index integrity check FAILED for {skill_id}! "
                f"Expected {expected_chunks} vectors, got {actual_vectors} "
                f"({actual_vectors/expected_chunks*100:.1f}% complete)"
            )
            logger.error(error_msg)
            return False, actual_vectors, error_msg

        logger.info(
            f"✅ Index integrity verified for {skill_id}: "
            f"{actual_vectors}/{expected_chunks} vectors"
        )
        return True, actual_vectors, None

    except Exception as e:
        error_msg = f"Index verification failed for {skill_id}: {str(e)}"
        logger.error(error_msg)
        return False, 0, error_msg


async def get_index_stats(
    skill_id: str,
    faiss_indices_path: str = "data/faiss_indices/skills"
) -> dict:
    """
    Get statistics about a FAISS index

    Args:
        skill_id: Skill identifier
        faiss_indices_path: Base path to FAISS indices

    Returns:
        Dict with index statistics
    """
    index_path = Path(faiss_indices_path) / skill_id / "index.faiss"
    metadata_path = Path(faiss_indices_path) / skill_id / "index.pkl"

    stats = {
        "skill_id": skill_id,
        "index_exists": index_path.exists(),
        "metadata_exists": metadata_path.exists(),
        "vector_count": 0,
        "index_size_bytes": 0,
        "metadata_size_bytes": 0
    }

    try:
        if index_path.exists():
            index = faiss.read_index(str(index_path))
            stats["vector_count"] = index.ntotal
            stats["index_size_bytes"] = index_path.stat().st_size

        if metadata_path.exists():
            stats["metadata_size_bytes"] = metadata_path.stat().st_size

    except Exception as e:
        logger.error(f"Failed to get index stats for {skill_id}: {str(e)}")
        stats["error"] = str(e)

    return stats


async def diagnose_incomplete_index(
    skill_id: str,
    expected_chunks: int,
    faiss_indices_path: str = "data/faiss_indices/skills"
) -> dict:
    """
    Diagnose why an index might be incomplete

    Returns detailed diagnostic information for troubleshooting

    Args:
        skill_id: Skill identifier
        expected_chunks: Expected chunk count from database
        faiss_indices_path: Base path to FAISS indices

    Returns:
        Dict with diagnostic information
    """
    stats = await get_index_stats(skill_id, faiss_indices_path)
    is_valid, actual_count, error = await verify_index_integrity(
        skill_id, expected_chunks, faiss_indices_path
    )

    diagnosis = {
        "skill_id": skill_id,
        "expected_chunks": expected_chunks,
        "actual_vectors": actual_count,
        "completion_percent": (actual_count / expected_chunks * 100) if expected_chunks > 0 else 0,
        "is_complete": is_valid,
        "index_stats": stats,
        "recommendations": []
    }

    if not is_valid:
        if actual_count == 0:
            diagnosis["recommendations"].append("Index appears to be empty - full rebuild required")
            diagnosis["recommendations"].append("Check embedding generation logs for errors")
        elif actual_count < expected_chunks * 0.1:
            diagnosis["recommendations"].append("Less than 10% indexed - likely failed early in processing")
            diagnosis["recommendations"].append("Check for BGE-M3 timeout or memory issues")
        elif actual_count < expected_chunks:
            diagnosis["recommendations"].append("Partial indexing - batch processing may have failed")
            diagnosis["recommendations"].append(f"Missing {expected_chunks - actual_count} chunks")
            diagnosis["recommendations"].append("Recommend: rebuild index for this skill")

    if error:
        diagnosis["error"] = error

    return diagnosis
