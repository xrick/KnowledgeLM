#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2: Skill Document Retrieval - Parallel FAISS Queries

Adapted from OPMP Phase 2 for DocAI Skill-Based system.
Performs parallel searches across file-level FAISS indices instead of Milvus/DuckDB.

Changes from Original OPMP:
- Milvus semantic search → Parallel FAISS file-level queries
- DuckDB structured query → Eliminated (FAISS only)
- Product retrieval → Document chunk retrieval
- Result merging with score normalization across files

Key Performance:
- Parallel execution: Search N documents concurrently
- Expected: 1.5-3.5s for 10 documents (vs OPMP's 2-5s)
- No network overhead (local FAISS)
- Smaller indices per document

Author: Claude (SuperClaude)
Date: 2025-12-06
Based on: OPMP Phase 2 (2025-10-01)
"""

import asyncio
import logging
import faiss
import numpy as np
from typing import Dict, Any, Optional, List, AsyncGenerator
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillDocumentRetrieval:
    """
    Phase 2: Parallel Document Retrieval using FAISS

    Adapted from OPMP Phase 2 for file-level FAISS indices.

    Features:
    - Parallel search across multiple document indices
    - Score normalization for fair ranking
    - In-memory LRU cache (fallback to Redis if available)
    - Progressive streaming of results

    Example:
        >>> retriever = SkillDocumentRetrieval(
        ...     skill_id="skill_xxx",
        ...     faiss_base_path="/data/faiss_indices/skills/"
        ... )
        >>> async for update in retriever.retrieve(
        ...     query="What is LLM pre-training?",
        ...     document_ids=["doc_001", "doc_002"],
        ...     top_k=5
        ... ):
        ...     if update["type"] == "phase_result":
        ...         chunks = update["data"]["chunks"]
    """

    def __init__(
        self,
        skill_id: str,
        faiss_base_path: str,
        embedding_service: Any,
        metadata_provider: Any,
        cache: Optional[Any] = None,
        enable_cache: bool = True
    ):
        """
        Initialize Phase 2 parallel retrieval

        Args:
            skill_id: Skill ID for path resolution
            faiss_base_path: Base path for FAISS indices (/data/faiss_indices/skills/)
            embedding_service: Service for generating query embeddings
            metadata_provider: Provider for retrieving chunk metadata
            cache: Optional cache instance (Redis or in-memory LRU)
            enable_cache: Enable caching (default: True)
        """
        self.skill_id = skill_id
        self.faiss_base_path = Path(faiss_base_path)
        self.embedding_service = embedding_service
        self.metadata_provider = metadata_provider
        self.enable_cache = enable_cache
        self.cache = cache if enable_cache else None

        # Statistics
        self.stats = {
            'total_retrievals': 0,
            'cache_hits': 0,
            'parallel_retrievals': 0,
            'avg_retrieval_time': 0.0
        }

        logger.info(f"SkillDocumentRetrieval initialized for skill {skill_id}")

    async def retrieve(
        self,
        query: str,
        document_ids: List[str],
        top_k: int = 5,
        use_cache: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute parallel retrieval with progress streaming

        Args:
            query: User query string
            document_ids: List of document IDs to search
            top_k: Number of results per document (default: 5)
            use_cache: Use cache if available (default: True)

        Yields:
            Progress updates and final results
        """
        start_time = datetime.now()
        self.stats['total_retrievals'] += 1

        # Check cache first
        if use_cache and self.enable_cache:
            cached_result = await self._check_cache(query, document_ids, top_k)
            if cached_result:
                self.stats['cache_hits'] += 1
                yield {
                    "type": "progress",
                    "phase": 2,
                    "message": "正在檢索文件資料...",
                    "progress": 25,
                    "from_cache": True
                }

                yield {
                    "type": "phase_result",
                    "phase": 2,
                    "data": cached_result,
                    "progress": 50,
                    "from_cache": True,
                    "retrieval_time": (datetime.now() - start_time).total_seconds()
                }
                return

        # Initial progress
        yield {
            "type": "progress",
            "phase": 2,
            "message": "正在檢索文件資料...",
            "progress": 25
        }

        try:
            # Generate query embedding
            query_embedding = await self._generate_query_embedding(query)

            # Parallel search across document indices
            self.stats['parallel_retrievals'] += 1
            search_results = await self._parallel_search(
                query_embedding,
                document_ids,
                top_k
            )

            # Merge and normalize scores
            merged_chunks = self._merge_and_normalize(search_results, top_k * 2)

            # Prepare result
            result = {
                "chunks": merged_chunks,
                "total_documents_searched": len(document_ids),
                "total_chunks_found": len(merged_chunks),
                "query_embedding_shape": query_embedding.shape
            }

            # Cache result
            if use_cache and self.enable_cache:
                await self._cache_result(query, document_ids, top_k, result)

            # Update stats
            retrieval_time = (datetime.now() - start_time).total_seconds()
            self._update_avg_retrieval_time(retrieval_time)

            yield {
                "type": "progress",
                "phase": 2,
                "message": "檢索文件資料完成",
                "progress": 50
            }

            yield {
                "type": "phase_result",
                "phase": 2,
                "data": result,
                "progress": 50,
                "retrieval_time": retrieval_time
            }

        except Exception as e:
            logger.error(f"Phase 2 retrieval error: {e}")
            yield {
                "type": "phase_result",
                "phase": 2,
                "data": {
                    "chunks": [],
                    "total_documents_searched": 0,
                    "total_chunks_found": 0,
                    "error": str(e)
                },
                "progress": 50,
                "error": str(e)
            }

    async def _generate_query_embedding(self, query: str) -> np.ndarray:
        """
        Generate query embedding using embedding service

        Args:
            query: User query string

        Returns:
            Query embedding as numpy array
        """
        try:
            # Use BGE embedding service (correct method name: embed_single)
            embedding_result = self.embedding_service.embed_single(query)

            # BGEEmbeddingProvider.embed_single() returns np.ndarray directly
            if isinstance(embedding_result, np.ndarray):
                return embedding_result
            elif isinstance(embedding_result, list):
                return np.array(embedding_result, dtype=np.float32)
            elif isinstance(embedding_result, dict) and 'embedding' in embedding_result:
                return np.array(embedding_result['embedding'], dtype=np.float32)
            else:
                raise ValueError(f"Unexpected embedding format: {type(embedding_result)}")

        except Exception as e:
            logger.error(f"Query embedding generation failed: {e}")
            raise

    async def _parallel_search(
        self,
        query_embedding: np.ndarray,
        document_ids: List[str],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Parallel search across file-level FAISS indices

        Args:
            query_embedding: Query embedding vector
            document_ids: List of document IDs to search
            top_k: Number of results per document

        Returns:
            List of search results from each document
        """
        # Create search tasks for each document
        search_tasks = [
            self._search_document_index(
                doc_id,
                query_embedding,
                top_k
            )
            for doc_id in document_ids
        ]

        # Execute in parallel
        results_list = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = []
        for i, result in enumerate(results_list):
            if isinstance(result, Exception):
                logger.warning(f"Document {document_ids[i]} search failed: {result}")
            else:
                valid_results.append(result)

        return valid_results

    async def _search_document_index(
        self,
        document_id: str,
        query_embedding: np.ndarray,
        top_k: int
    ) -> Dict[str, Any]:
        """
        Search a single document's FAISS index

        Args:
            document_id: Document ID (e.g., doc_20251127_xxx)
            query_embedding: Query embedding vector
            top_k: Number of results to return

        Returns:
            Search results with metadata
        """
        try:
            # Construct FAISS index path
            # FIX: FAISS indices are stored by document_id directly under faiss_base_path, NOT under skill_id
            # Path structure: /data/faiss_indices/skills/{document_id}/index.faiss
            index_path = self.faiss_base_path / document_id / "index.faiss"

            if not index_path.exists():
                logger.warning(f"FAISS index not found: {index_path}")
                return {
                    "document_id": document_id,
                    "chunks": [],
                    "error": "Index not found"
                }

            # Load FAISS index
            index = await asyncio.to_thread(faiss.read_index, str(index_path))

            # Ensure query embedding is 2D
            if query_embedding.ndim == 1:
                query_embedding = query_embedding.reshape(1, -1)

            # Search
            distances, indices = await asyncio.to_thread(
                index.search,
                query_embedding.astype(np.float32),
                top_k
            )

            # ✅ FIXED: Fetch metadata using document_id and FAISS indices directly
            # No need to construct fake chunk_ids - pass indices to metadata provider
            chunks_metadata = await self._fetch_chunks_metadata(document_id, indices[0])

            # Combine with distances (scores)
            chunks = []
            for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
                if idx == -1:  # Invalid index
                    continue

                # Use FAISS index as key (metadata provider handles the mapping)
                metadata = chunks_metadata.get(idx, {})

                chunks.append({
                    "chunk_id": f"{document_id}_faiss_{idx}",  # Temporary ID for tracking
                    "document_id": document_id,
                    "distance": float(distance),
                    "score": float(1 / (1 + distance)),  # Convert distance to score
                    "content": metadata.get("content", ""),
                    "page": metadata.get("page", 0),
                    "source_file": metadata.get("source_file", "")
                })

            return {
                "document_id": document_id,
                "chunks": chunks
            }

        except Exception as e:
            logger.error(f"Document {document_id} search error: {e}")
            return {
                "document_id": document_id,
                "chunks": [],
                "error": str(e)
            }

    async def _fetch_chunks_metadata(
        self,
        document_id: str,
        faiss_indices: np.ndarray
    ) -> Dict[int, Dict[str, Any]]:
        """
        Fetch metadata for FAISS indices from metadata provider

        Args:
            document_id: Document identifier (actually skill_id in current architecture)
            faiss_indices: Array of FAISS indices

        Returns:
            Dict mapping FAISS index to metadata
        """
        try:
            metadata_map = {}
            for idx in faiss_indices:
                if idx == -1:  # Skip invalid indices
                    continue

                # ✅ FIXED: Pass BOTH skill_id and document_id
                # For single-document skills: both are the same (skill_id)
                # For multi-document skills: need to determine actual document_id from FAISS metadata
                chunk_metadata = await self.metadata_provider.get_chunk_metadata(
                    skill_id=document_id,      # FAISS path = skill_id
                    document_id=document_id,   # Currently same as skill_id (single-doc)
                    faiss_index=int(idx)
                )

                if chunk_metadata:
                    metadata_map[int(idx)] = chunk_metadata

            return metadata_map

        except Exception as e:
            logger.error(f"Metadata fetch error: {e}")
            return {}

    def _merge_and_normalize(
        self,
        results_list: List[Dict[str, Any]],
        max_chunks: int
    ) -> List[Dict[str, Any]]:
        """
        Merge results from multiple documents and normalize scores

        Uses Min-Max normalization to ensure fair ranking across documents.

        Args:
            results_list: List of search results from each document
            max_chunks: Maximum number of chunks to return

        Returns:
            Merged and ranked list of chunks
        """
        # Collect all chunks
        all_chunks = []
        for result in results_list:
            all_chunks.extend(result.get("chunks", []))

        if not all_chunks:
            return []

        # Extract all scores for normalization
        scores = [chunk["score"] for chunk in all_chunks]

        if len(scores) == 0:
            return []

        # Min-Max normalization
        min_score = min(scores)
        max_score = max(scores)
        score_range = max_score - min_score

        if score_range > 0:
            for chunk in all_chunks:
                chunk["normalized_score"] = (chunk["score"] - min_score) / score_range
        else:
            for chunk in all_chunks:
                chunk["normalized_score"] = 1.0

        # Sort by normalized score (descending)
        all_chunks.sort(key=lambda x: x["normalized_score"], reverse=True)

        # Return top N
        return all_chunks[:max_chunks]

    def _update_avg_retrieval_time(self, retrieval_time: float):
        """Update average retrieval time statistics"""
        n = self.stats['total_retrievals']
        prev_avg = self.stats['avg_retrieval_time']
        self.stats['avg_retrieval_time'] = (prev_avg * (n - 1) + retrieval_time) / n

    async def _check_cache(
        self,
        query: str,
        document_ids: List[str],
        top_k: int
    ) -> Optional[Dict[str, Any]]:
        """Check cache for existing results"""
        if not self.cache:
            return None

        try:
            import hashlib
            cache_key_data = f"{query}:{sorted(document_ids)}:{top_k}"
            cache_hash = hashlib.md5(cache_key_data.encode()).hexdigest()
            cache_key = f"skill_phase2:{self.skill_id}:{cache_hash}"

            # Try async method
            if hasattr(self.cache, 'get_async'):
                cached = await self.cache.get_async(cache_key)
            elif hasattr(self.cache, 'get'):
                import json
                cached = await asyncio.to_thread(self.cache.get, cache_key)
            else:
                return None

            if cached:
                import json
                return json.loads(cached)

        except Exception as e:
            logger.warning(f"Cache check error: {e}")

        return None

    async def _cache_result(
        self,
        query: str,
        document_ids: List[str],
        top_k: int,
        result: Dict[str, Any]
    ):
        """Cache search results"""
        if not self.cache:
            return

        try:
            import hashlib
            import json

            cache_key_data = f"{query}:{sorted(document_ids)}:{top_k}"
            cache_hash = hashlib.md5(cache_key_data.encode()).hexdigest()
            cache_key = f"skill_phase2:{self.skill_id}:{cache_hash}"

            # Try async method
            if hasattr(self.cache, 'set_async'):
                await self.cache.set_async(
                    cache_key,
                    json.dumps(result, ensure_ascii=False),
                    ttl=300  # 5 minutes
                )
            elif hasattr(self.cache, 'set'):
                await asyncio.to_thread(
                    self.cache.set,
                    cache_key,
                    json.dumps(result, ensure_ascii=False),
                    300  # 5 minutes TTL
                )

        except Exception as e:
            logger.warning(f"Cache set error: {e}")
