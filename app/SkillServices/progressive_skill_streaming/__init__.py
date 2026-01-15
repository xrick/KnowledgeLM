"""
Progressive Skill Streaming - OPMP Adapted for DocAI Skill System

This package implements the 5-phase OPMP (Optimistic Progressive Markdown Parsing)
system adapted for DocAI's Skill-Based architecture.

Phases:
1. Skill Query Understanding - Document concept extraction and intent analysis
2. Skill Document Retrieval - Parallel FAISS file-level queries
3. Context Assembly - Chunk ranking and context truncation
4. Response Generation - Token-by-token markdown streaming
5. Post-processing - Markdown validation and quality checks

Architecture Adaptation:
- Phase 1: Product extraction → Document concept extraction
- Phase 2: Milvus/DuckDB → Parallel FAISS file-level indices
- Phase 3-5: Minimal changes (chunk ranking vs product ranking)

Author: Claude (SuperClaude)
Date: 2025-12-06
Based on: OPMP v1.0 (2025-10-01)
"""

from .progressive_streaming import (
    ProgressiveSkillStreaming,
    acknowledge_phase,
    cleanup_session
)

__all__ = [
    "ProgressiveSkillStreaming",
    "acknowledge_phase",
    "cleanup_session"
]

__version__ = "1.0.0"
