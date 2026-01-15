# app/Services/chunking_strategies.py
"""
Chunking Strategies using Strategy and Factory Design Patterns

Implements multiple text chunking strategies for RAG applications:
- Recursive Character Splitting (baseline)
- Hierarchical Indexing (multi-level with parent-child relationships)

Future strategies can be added by extending ChunkingStrategy base class.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
# Note: MultiVectorRetriever not actively used - commented for langchain 1.x compatibility
# from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain_core.stores import InMemoryStore  # Updated for langchain 1.x
from langchain_core.documents import Document
import uuid
from app.core.config import settings


logger = logging.getLogger(__name__)


# =============================================================================
# Strategy Pattern: Base Class
# =============================================================================

class ChunkingStrategy(ABC):
    """
    Abstract base class for chunking strategies

    All chunking strategies must implement the chunk() method.
    """

    def __init__(self, **kwargs):
        """
        Initialize strategy with configuration

        Args:
            **kwargs: Strategy-specific configuration
        """
        self.config = kwargs

    @abstractmethod
    def chunk(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Chunk text according to strategy

        Args:
            text: Input text to chunk
            metadata: Optional metadata to attach to chunks

        Returns:
            List of chunk dicts with keys:
            - content: Chunk text
            - metadata: Chunk metadata
            - chunk_index: Position in document
            - (strategy-specific fields)
        """
        pass

    def get_strategy_name(self) -> str:
        """Return strategy name"""
        return self.__class__.__name__


# =============================================================================
# Strategy 1: Recursive Character Splitting (Baseline)
# =============================================================================

class RecursiveChunkingStrategy(ChunkingStrategy):
    """
    Standard recursive character text splitting

    Uses LangChain's RecursiveCharacterTextSplitter with configurable
    separators, chunk size, and overlap.

    Best for: General-purpose document chunking
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: Optional[List[str]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or settings.CHUNK_SEPARATORS

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=self.separators,
            length_function=len
        )

        logger.info(
            f"Recursive Chunking Strategy initialized: "
            f"size={chunk_size}, overlap={chunk_overlap}"
        )

    def chunk(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Chunk text using recursive character splitting

        Args:
            text: Input text
            metadata: Optional base metadata

        Returns:
            List of chunk dicts

        Example:
            >>> strategy = RecursiveChunkingStrategy(chunk_size=1000)
            >>> chunks = strategy.chunk(text)
            >>> print(len(chunks))
        """
        try:
            # Split text
            text_chunks = self.splitter.split_text(text)

            # Build chunk dicts
            chunks = []
            for i, chunk_text in enumerate(text_chunks):
                chunk = {
                    "content": chunk_text.strip(),
                    "chunk_index": i,
                    "metadata": {
                        **(metadata or {}),
                        "chunking_strategy": "recursive",
                        "chunk_size": self.chunk_size,
                        "chunk_overlap": self.chunk_overlap                       
                    }
                }
                chunks.append(chunk)

            logger.info(f"Recursive chunking: {len(chunks)} chunks generated")
            return chunks

        except Exception as e:
            logger.error(f"Recursive chunking failed: {str(e)}")
            raise


# =============================================================================
# Strategy 2: Hierarchical Indexing (Multi-Level)
# =============================================================================

class HierarchicalChunkingStrategy(ChunkingStrategy):
    """
    Hierarchical multi-level chunking with parent-child relationships

    Creates multiple granularity levels:
    - Level 0 (Parent): Large chunks for context (e.g., 2000 chars)
    - Level 1 (Child): Medium chunks for retrieval (e.g., 1000 chars)
    - Level 2 (Grandchild): Small chunks for precise matching (e.g., 500 chars)

    Benefits:
    - Retrieve small chunks for precision
    - Access parent chunks for broader context
    - Better handling of long documents

    Compatible with LangChain's MultiVectorRetriever.

    Best for: Long documents, technical papers, reports
    """

    def __init__(
        self,
        chunk_sizes: Optional[List[int]] = None,
        overlap: int = 100,
        separators: Optional[List[str]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)

        # Default: [Parent, Child, Grandchild]
        self.chunk_sizes = chunk_sizes or [2000, 1000, 500]
        self.overlap = overlap
        self.separators = separators or ["\n\n", "\n", " ", ""]

        # Create splitter for each level
        self.splitters = [
            RecursiveCharacterTextSplitter(
                chunk_size=size,
                chunk_overlap=overlap,
                separators=self.separators,
                length_function=len
            )
            for size in self.chunk_sizes
        ]

        logger.info(
            f"Hierarchical Chunking Strategy initialized: "
            f"levels={len(self.chunk_sizes)}, sizes={self.chunk_sizes}, overlap={overlap}"
        )

    def chunk(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Chunk text hierarchically with parent-child relationships

        Args:
            text: Input text
            metadata: Optional base metadata

        Returns:
            List of chunk dicts with hierarchical metadata

        Example:
            >>> strategy = HierarchicalChunkingStrategy(chunk_sizes=[2000, 1000, 500])
            >>> chunks = strategy.chunk(text)
            >>> # Chunks have parent_id, level, and children relationships
        """
        try:
            all_chunks = []
            chunk_id_map = {}  # Map level -> chunk_index -> chunk_id

            # Process each hierarchical level
            for level, splitter in enumerate(self.splitters):
                level_chunks = splitter.split_text(text)
                chunk_id_map[level] = {}

                for local_idx, chunk_text in enumerate(level_chunks):
                    # Generate unique chunk ID
                    chunk_id = str(uuid.uuid4())
                    chunk_id_map[level][local_idx] = chunk_id

                    # Determine parent chunk ID (from previous level)
                    parent_id = None
                    if level > 0:
                        # Find parent by position overlap
                        parent_level = level - 1
                        parent_idx = self._find_parent_index(
                            local_idx,
                            len(level_chunks),
                            len(chunk_id_map[parent_level])
                        )
                        parent_id = chunk_id_map[parent_level].get(parent_idx)

                    # Build chunk dict
                    chunk = {
                        "content": chunk_text.strip(),
                        "chunk_id": chunk_id,
                        "chunk_index": len(all_chunks),  # Global index
                        "level": level,
                        "level_index": local_idx,  # Index within level
                        "parent_id": parent_id,
                        "metadata": {
                            **(metadata or {}),
                            "chunking_strategy": "hierarchical",
                            "level": level,
                            "level_name": self._get_level_name(level),
                            "chunk_size": self.chunk_sizes[level],
                            "parent_id": parent_id
                        }
                    }

                    all_chunks.append(chunk)

            logger.info(
                f"Hierarchical chunking: {len(all_chunks)} chunks across "
                f"{len(self.chunk_sizes)} levels"
            )

            return all_chunks

        except Exception as e:
            logger.error(f"Hierarchical chunking failed: {str(e)}")
            raise

    def _find_parent_index(
        self,
        child_idx: int,
        child_count: int,
        parent_count: int
    ) -> int:
        """
        Determine which parent chunk this child belongs to

        Args:
            child_idx: Child chunk index
            child_count: Total number of child chunks
            parent_count: Total number of parent chunks

        Returns:
            Parent chunk index

        Logic:
        - Distribute children evenly among parents
        - Example: 10 children, 5 parents → 2 children per parent
        """
        if parent_count == 0:
            return 0

        children_per_parent = max(1, child_count / parent_count)
        parent_idx = int(child_idx / children_per_parent)

        # Ensure within bounds
        return min(parent_idx, parent_count - 1)

    def _get_level_name(self, level: int) -> str:
        """
        Get human-readable name for hierarchical level

        Args:
            level: Level index (0, 1, 2, ...)

        Returns:
            Level name ("parent", "child", "grandchild", "level_N")
        """
        names = ["parent", "child", "grandchild"]
        if level < len(names):
            return names[level]
        return f"level_{level}"

    def get_multivector_config(self) -> Dict[str, Any]:
        """
        Get configuration for LangChain MultiVectorRetriever

        Returns:
            Dict with configuration for MultiVectorRetriever setup

        Example:
            >>> config = strategy.get_multivector_config()
            >>> retriever = MultiVectorRetriever(**config)
        """
        return {
            "vector_store": None,  # To be set by caller
            "doc_store": InMemoryStore(),
            "id_key": "chunk_id",
            "search_kwargs": {"k": 5}
        }
        
# =============================================================================
# Strategy 3: Page-Based Chunking
# =============================================================================
class PageBasedChunkingStrategy(ChunkingStrategy):
    """
    Chunking strategy that splits text based on page breaks.

    Best for: Documents with clear page demarcations (e.g., PDFs)
    """

    def __init__(
        self,
        chunk_size: int = 600,
        overlap: int = 100,
        # separators: Optional[List[str]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.chunk_size = chunk_size
        self.chunk_overlap = overlap
        logger.info("Page-Based Chunking Strategy initialized")

    def chunk(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Chunk text by splitting at page breaks

        Args:
            text: Input text
            metadata: Optional base metadata

        Returns:
            List of chunk dicts with 'content' key

        Example:
            >>> strategy = PageBasedChunkingStrategy()
            >>> chunks = strategy.chunk(text)
            >>> print(len(chunks))
        """
        try:
            # 初始化切分器 (用於處理字數過多的頁面)
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.PAGE_BASED_CHUNK_SIZE,
                chunk_overlap=settings.PAGE_BASED_CHUNK_OVERLAP,
                separators=["\n\n", "\n", "。", "！", "？", " ", ""]
            )

            # Debug info
            _file_name = metadata.get("filename", "unknown") if metadata else "unknown"
            _page_count = metadata.get("page_count") if metadata else None
            logger.info(f"開始處理文件: {_file_name}, 頁數: {_page_count}")

            # FIX: 先用 form feed (\f) 分割頁面，如果沒有則用 text_splitter
            pages = text.split('\f')

            # 如果沒有頁面分隔符（只有一個元素），使用 RecursiveCharacterTextSplitter
            if len(pages) == 1 and len(text) > self.chunk_size:
                pages = text_splitter.split_text(text)
                logger.info(f"No page breaks found, using text_splitter: {len(pages)} chunks")
            else:
                logger.info(f"Split by page breaks: {len(pages)} pages")

            # Build chunk dicts
            all_chunks = []
            for page_num, page_text in enumerate(pages):
                page_text = page_text.strip()
                if not page_text:
                    continue  # 跳過空白頁

                # 如果頁面內容過長，進一步切分
                if len(page_text) > self.chunk_size * 1.5:
                    sub_chunks = text_splitter.split_text(page_text)
                    for sub_idx, sub_text in enumerate(sub_chunks):
                        chunk = {
                            "content": sub_text.strip(),
                            "chunk_index": len(all_chunks),
                            "metadata": {
                                **(metadata or {}),
                                "chunking_strategy": "page_based",
                                "file_name": _file_name,
                                "page_num": page_num + 1,
                                "sub_chunk": sub_idx + 1
                            }
                        }
                        all_chunks.append(chunk)
                else:
                    # 頁面內容適中，整頁當作一個 Chunk
                    chunk = {
                        "content": page_text,
                        "chunk_index": len(all_chunks),
                        "metadata": {
                            **(metadata or {}),
                            "chunking_strategy": "page_based",
                            "file_name": _file_name,
                            "page_num": page_num + 1
                        }
                    }
                    all_chunks.append(chunk)

            logger.info(f"Page-based chunking: {len(all_chunks)} chunks generated")
            return all_chunks

        except Exception as e:
            logger.error(f"Page-based chunking failed: {str(e)}")
            raise

# =============================================================================
# Factory Pattern: Strategy Selection
# =============================================================================

class ChunkingStrategyFactory:
    """
    Factory for creating chunking strategies

    Provides centralized strategy instantiation with configuration.

    Usage:
        >>> factory = ChunkingStrategyFactory()
        >>> strategy = factory.create("hierarchical", chunk_sizes=[2000, 1000])
        >>> chunks = strategy.chunk(text)
    """

    _strategies = {
        "recursive": RecursiveChunkingStrategy,
        "hierarchical": HierarchicalChunkingStrategy,
        "page_based": PageBasedChunkingStrategy
    }

    @classmethod
    def create(
        cls,
        strategy_name: str,
        **kwargs
    ) -> ChunkingStrategy:
        """
        Create chunking strategy by name

        Args:
            strategy_name: Strategy name ("recursive" or "hierarchical")
            **kwargs: Strategy-specific configuration

        Returns:
            ChunkingStrategy instance

        Raises:
            ValueError: If strategy name not recognized

        Example:
            >>> strategy = ChunkingStrategyFactory.create("hierarchical")
            >>> chunks = strategy.chunk(text)
        """
        strategy_class = cls._strategies.get(strategy_name.lower())

        if strategy_class is None:
            available = ", ".join(cls._strategies.keys())
            raise ValueError(
                f"Unknown chunking strategy: '{strategy_name}'. "
                f"Available: {available}"
            )

        logger.info(f"Creating chunking strategy: {strategy_name}")
        return strategy_class(**kwargs)

    @classmethod
    def register_strategy(
        cls,
        name: str,
        strategy_class: type
    ):
        """
        Register custom chunking strategy

        Args:
            name: Strategy name
            strategy_class: ChunkingStrategy subclass

        Example:
            >>> class MyStrategy(ChunkingStrategy):
            ...     def chunk(self, text, metadata):
            ...         return [...]
            >>> ChunkingStrategyFactory.register_strategy("my_strategy", MyStrategy)
        """
        if not issubclass(strategy_class, ChunkingStrategy):
            raise TypeError("Strategy class must inherit from ChunkingStrategy")

        cls._strategies[name.lower()] = strategy_class
        logger.info(f"Registered custom chunking strategy: {name}")

    @classmethod
    def list_strategies(cls) -> List[str]:
        """
        List all available strategy names

        Returns:
            List of strategy names

        Example:
            >>> ChunkingStrategyFactory.list_strategies()
            >>> ['recursive', 'hierarchical']
        """
        return list(cls._strategies.keys())


# =============================================================================
# Convenience Functions
# =============================================================================

def get_default_strategy() -> ChunkingStrategy:
    """
    Get default chunking strategy from settings

    Returns:
        Configured ChunkingStrategy instance

    Example:
        >>> strategy = get_default_strategy()
        >>> chunks = strategy.chunk(text)
    """
    

    if settings.CHUNKING_STRATEGY == "hierarchical":
        return ChunkingStrategyFactory.create(
            "hierarchical",
            chunk_sizes=settings.HIERARCHICAL_CHUNK_SIZES,
            overlap=settings.HIERARCHICAL_OVERLAP
        )
    elif settings.CHUNKING_STRATEGY == "recursive":
        return ChunkingStrategyFactory.create(
            "recursive",
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=settings.CHUNK_SEPARATORS
        )
    elif settings.CHUNKING_STRATEGY == "page_based":
        return PageBasedChunkingStrategy.create(
            "page_based",
            chunk_size=settings.PAGE_BASED_CHUNK_SIZE,
            chunk_overlap=settings.PAGE_BASED_CHUNK_OVERLAP,
            separators=settings.CHUNK_SEPARATORS
        )
