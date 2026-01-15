"""
Background Integrity Checker

Periodically scans for incomplete FAISS indices and attempts recovery.
Runs as a background task in FastAPI.

Created: 2025-12-11
Purpose: Prevent and detect index integrity issues
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
                    f"❌ Index integrity issue for {skill_id}:\n"
                    f"   Expected: {expected_chunks}\n"
                    f"   Actual: {actual_vectors}\n"
                    f"   Completion: {diagnosis['completion_percent']:.1f}%\n"
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
