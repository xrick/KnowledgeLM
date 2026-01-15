#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 3: Context Assembly & Ranking

Adapted from OPMP Phase 3 for DocAI Skill-Based system.
Handles chunk ranking and intelligent context truncation.

Changes from Original OPMP:
- Product ranking → Chunk ranking
- Feature completeness → Concept relevance
- Keep token truncation logic (same)

Author: Claude (SuperClaude)
Date: 2025-12-06
Based on: OPMP Phase 3 (2025-10-01)
"""

import json
import logging
from typing import Dict, Any, AsyncGenerator, List, Optional

logger = logging.getLogger(__name__)


class Phase3ContextAssembly:
    """
    Phase 3: Context Assembly & Ranking

    Adapted from OPMP Phase 3 for document chunk ranking.

    Handles:
    - Ranking chunks by relevance
    - Intelligent context truncation to fit token limits
    - Token estimation and management
    - Context optimization for LLM

    Features:
    - Multi-criteria chunk ranking
    - Smart field selection based on query intent
    - Token-aware truncation
    - Context optimization for LLM
    """

    def __init__(self, max_context_tokens: int = 100000):
        """
        Initialize Phase 3 processor

        Args:
            max_context_tokens: Maximum tokens allowed for context (default: 100K)
        """
        self.MAX_CONTEXT_TOKENS = max_context_tokens
        logger.info(f"Phase3ContextAssembly initialized (max tokens: {max_context_tokens})")

    async def process(
        self,
        retrieval_results: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process retrieval results and assemble context

        Args:
            retrieval_results: Results from Phase 2 (chunks)
            analysis: Query analysis from Phase 1

        Yields:
            Progress updates and final phase result
        """
        try:
            yield {
                "type": "progress",
                "phase": 3,
                "message": "正在組織回覆訊息",
                "progress": 55
            }

            # Get chunks from Phase 2
            chunks = retrieval_results.get("chunks", [])

            if not chunks:
                logger.warning("No chunks to process")
                yield {
                    "type": "phase_result",
                    "phase": 3,
                    "data": {
                        "chunks": [],
                        "token_count": 0,
                        "truncation_applied": False
                    },
                    "progress": 65
                }
                return

            # Rank chunks by relevance
            ranked_chunks = self._rank_chunks_by_relevance(
                chunks,
                analysis.get("key_concepts", []),
                analysis.get("document_keywords", [])
            )

            # Context truncation based on token limits
            truncated_context = self._truncate_context(
                ranked_chunks,
                max_tokens=self.MAX_CONTEXT_TOKENS - 10000,  # Reserve for prompt
                key_concepts=analysis.get("key_concepts", [])
            )

            yield {
                "type": "progress",
                "phase": 3,
                "message": "組織回覆訊息完成",
                "progress": 65
            }

            yield {
                "type": "phase_result",
                "phase": 3,
                "data": truncated_context,
                "progress": 65
            }

        except Exception as e:
            logger.error(f"Phase 3 error: {e}")
            raise

    def _rank_chunks_by_relevance(
        self,
        chunks: List[Dict[str, Any]],
        key_concepts: List[str],
        document_keywords: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Rank chunks by relevance to query

        Ranking criteria:
        1. Normalized score from Phase 2 (highest priority)
        2. Keyword match count
        3. Concept coverage
        4. Document source priority

        Args:
            chunks: List of chunk dictionaries from Phase 2
            key_concepts: Key concepts from query analysis
            document_keywords: Document keywords from query

        Returns:
            Ranked list of chunks
        """
        for chunk in chunks:
            score = 0.0

            # Criterion 1: Normalized score from Phase 2 (highest weight)
            if "normalized_score" in chunk:
                score += chunk["normalized_score"] * 100.0
            elif "score" in chunk:
                score += chunk["score"] * 50.0

            # Criterion 2: Keyword match count
            content = chunk.get("content", "").lower()
            keyword_matches = sum(
                1 for keyword in document_keywords
                if keyword.lower() in content
            )
            if document_keywords:
                keyword_ratio = keyword_matches / len(document_keywords)
                score += keyword_ratio * 30.0

            # Criterion 3: Concept coverage
            concept_matches = sum(
                1 for concept in key_concepts
                if concept.lower() in content
            )
            if key_concepts:
                concept_ratio = concept_matches / len(key_concepts)
                score += concept_ratio * 20.0

            # Criterion 4: Document source priority (if available)
            # Prioritize chunks from selected documents
            if chunk.get("document_id"):
                score += 10.0

            # Store relevance score
            chunk["relevance_score"] = score

        # Sort by relevance score (descending)
        ranked = sorted(chunks, key=lambda c: c.get("relevance_score", 0), reverse=True)

        logger.info(
            f"Ranked {len(ranked)} chunks. "
            f"Top 3 scores: {[c.get('relevance_score', 0) for c in ranked[:3]]}"
        )

        return ranked

    def _truncate_context(
        self,
        chunks: List[Dict[str, Any]],
        max_tokens: int,
        key_concepts: List[str]
    ) -> Dict[str, Any]:
        """
        Intelligent context truncation to fit token limits

        Strategy:
        1. Keep top-ranked chunks (relevance priority)
        2. Select essential fields
        3. Estimate tokens and iteratively truncate
        4. Ensure minimum viable context

        Args:
            chunks: Ranked chunk list
            max_tokens: Maximum allowed tokens
            key_concepts: Key concepts from query

        Returns:
            Truncated context dictionary
        """
        # Strategy 1: Keep top chunks by relevance
        initial_limit = min(20, len(chunks))
        truncated_chunks = chunks[:initial_limit]

        # Strategy 2: Essential fields for chunks
        essential_fields = ['chunk_id', 'document_id', 'content', 'page', 'source_file', 'relevance_score']

        # Strategy 3: Extract essential fields from chunks
        minimized_chunks = []
        for chunk in truncated_chunks:
            minimized = {}
            for field in essential_fields:
                if field in chunk and chunk[field] is not None:
                    minimized[field] = chunk[field]

            # Truncate content if too long
            if "content" in minimized and minimized["content"]:
                content = str(minimized["content"])
                if len(content) > 500:
                    minimized["content"] = content[:500] + "..."

            minimized_chunks.append(minimized)

        # Strategy 4: Estimate tokens
        context_text = json.dumps(minimized_chunks, ensure_ascii=False)
        estimated_tokens = self._estimate_tokens(context_text)

        # Strategy 5: Further truncate if still over limit
        if estimated_tokens > max_tokens:
            # Reduce number of chunks
            target_count = max(5, int(len(minimized_chunks) * max_tokens / estimated_tokens))
            minimized_chunks = minimized_chunks[:target_count]

            # Re-estimate
            context_text = json.dumps(minimized_chunks, ensure_ascii=False)
            estimated_tokens = self._estimate_tokens(context_text)

            logger.warning(
                f"Context truncated to {target_count} chunks "
                f"({estimated_tokens} tokens)"
            )

        return {
            "chunks": minimized_chunks,
            "token_count": estimated_tokens,
            "truncation_applied": len(minimized_chunks) < len(chunks),
            "original_count": len(chunks),
            "kept_count": len(minimized_chunks)
        }

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text

        Uses tiktoken if available, otherwise falls back to character-based estimation.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        # Try to use tiktoken if available
        try:
            import tiktoken
            encoder = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
            return len(encoder.encode(text))
        except (ImportError, Exception):
            # Fallback to character-based estimation
            # English: ~1 token per 4 characters
            # Chinese: ~1 token per 2-3 characters
            # Mixed: Use average of 3 characters per token
            return len(text) // 3
