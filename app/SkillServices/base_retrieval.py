# app/SkillServices/base_retrieval.py
"""
Abstract Retrieval Service Interface

Defines common interface for file-based and skill-based retrieval services.
Enables polymorphism and consistent API surface across different retrieval modes.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class AbstractRetrievalService(ABC):
    """
    Abstract base class for retrieval services

    Both file-based (app/Services/retrieval_service.py) and skill-based
    (app/SkillServices/skill_retrieval_service.py) retrieval services
    implement this interface.

    This enables:
    1. Polymorphism: UnifiedRetrievalService can work with both
    2. Consistent API: Same method signatures for all retrievals
    3. Easy extension: New retrieval modes can be added

    Example:
        # File-based retrieval
        file_service: AbstractRetrievalService = RetrievalService(...)
        results = await file_service.retrieve_context(
            query="What is RAG?",
            content_ids=["file_001", "file_002"],
            top_k=5
        )

        # Skill-based retrieval
        skill_service: AbstractRetrievalService = SkillRetrievalService(...)
        results = await skill_service.retrieve_context(
            query="Python async programming",
            content_ids=["skill_001", "skill_002"],
            top_k=5
        )
    """

    @abstractmethod
    async def add_content(
        self,
        content_id: str,
        chunks: List[str],
        metadata: Optional[List[dict]] = None
    ) -> str:
        """
        Add content chunks to vector store

        Args:
            content_id: Unique identifier (file_id or skill_id)
            chunks: List of text chunks to embed
            metadata: Optional metadata for each chunk

        Returns:
            Store identifier (typically same as content_id)

        Raises:
            ValueError: If content_id already exists
            Exception: If vector store operation fails

        Example:
            >>> store_id = await service.add_content(
            ...     content_id="skill_123",
            ...     chunks=["chunk1", "chunk2", "chunk3"],
            ...     metadata=[
            ...         {"skill_id": "skill_123", "chunk_index": 0},
            ...         {"skill_id": "skill_123", "chunk_index": 1},
            ...         {"skill_id": "skill_123", "chunk_index": 2}
            ...     ]
            ... )
        """
        pass

    @abstractmethod
    async def retrieve_context(
        self,
        query: str,
        content_ids: List[str],
        top_k: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context for a query

        Args:
            query: User query text
            content_ids: List of content IDs to search (file_ids or skill_ids)
            top_k: Number of top results to return
            **kwargs: Additional retrieval parameters
                - include_scores: Whether to include similarity scores
                - fair_distribution: Whether to balance results across contents
                - filters: Additional filtering criteria

        Returns:
            List of context dicts, each containing:
            - content: Text chunk content
            - metadata: Chunk metadata (file_id/skill_id, chunk_index, etc.)
            - score: Similarity score (if include_scores=True)

        Example:
            >>> results = await service.retrieve_context(
            ...     query="What is async programming?",
            ...     content_ids=["skill_001", "skill_002"],
            ...     top_k=5,
            ...     include_scores=True
            ... )
            >>> for result in results:
            ...     print(f"Score: {result['score']}, Content: {result['content'][:100]}")
        """
        pass

    @abstractmethod
    async def delete_content(self, content_id: str):
        """
        Delete content from vector store

        Args:
            content_id: Content identifier to delete

        Raises:
            ValueError: If content_id not found
            Exception: If deletion fails

        Example:
            >>> await service.delete_content("skill_123")
        """
        pass

    @abstractmethod
    def get_retrieval_mode(self) -> str:
        """
        Return retrieval mode identifier

        Returns:
            Retrieval mode: "file_based" or "skill_based"

        Example:
            >>> mode = service.get_retrieval_mode()
            >>> print(f"Using {mode} retrieval")
        """
        pass

    # =========================================================================
    # Optional Methods (Default Implementations)
    # =========================================================================

    def get_store_path(self, content_id: str) -> str:
        """
        Get vector store path for content ID

        Optional method with default implementation.
        Can be overridden by subclasses.

        Args:
            content_id: Content identifier

        Returns:
            Store path string
        """
        mode = self.get_retrieval_mode()
        return f"./data/vectorstores/{mode}s/{content_id}"

    async def content_exists(self, content_id: str) -> bool:
        """
        Check if content exists in vector store

        Optional method with default implementation.
        Can be overridden by subclasses for more efficient checks.

        Args:
            content_id: Content identifier

        Returns:
            True if content exists, False otherwise
        """
        try:
            # Attempt to retrieve with minimal top_k
            results = await self.retrieve_context(
                query="test",
                content_ids=[content_id],
                top_k=1
            )
            return len(results) > 0
        except (ValueError, Exception):
            return False

    def get_metadata_fields(self) -> List[str]:
        """
        Get expected metadata fields for this retrieval mode

        Optional method with default implementation.

        Returns:
            List of metadata field names

        Example:
            >>> fields = service.get_metadata_fields()
            >>> print(fields)
            ['skill_id', 'skill_name', 'chunk_index', 'total_chunks']
        """
        mode = self.get_retrieval_mode()

        if mode == "file_based":
            return [
                "file_id",
                "filename",
                "chunk_index",
                "total_chunks",
                "page_number"
            ]
        elif mode == "skill_based":
            return [
                "skill_id",
                "skill_name",
                "skill_category",
                "chunk_index",
                "total_chunks"
            ]
        else:
            return []


class RetrievalMode:
    """
    Retrieval mode constants

    Usage:
        from app.SkillServices.base_retrieval import RetrievalMode

        if service.get_retrieval_mode() == RetrievalMode.FILE_BASED:
            print("Using file-based retrieval")
    """
    FILE_BASED = "file_based"
    SKILL_BASED = "skill_based"
    HYBRID = "hybrid"  # Future: combine both modes
