# app/Providers/vector_store_provider/client.py
"""
Vector Store Provider Client

Vector database interface for storing and retrieving document embeddings.
Supports FAISS (in-memory with persistence) and ChromaDB (persistent) backends.
"""

import logging
import os
import json
import numpy as np
from typing import List, Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Default persistence directory for FAISS indices
FAISS_PERSIST_DIR = "data/faiss_indices"


class VectorStoreProvider:
    """
    Vector Store Provider for similarity search

    Provides a unified interface for different vector database backends.
    Currently supports:
    - FAISS (fast in-memory search)
    - ChromaDB (persistent storage)
    - Milvus (distributed persistent vector database)
    """

    def __init__(
        self,
        backend: str = "faiss",
        persist_directory: Optional[str] = None,
        collection_name: str = "documents"
    ):
        """
        Initialize Vector Store Provider

        Args:
            backend: Vector store backend ("faiss", "chroma", or "milvus")
            persist_directory: Directory for persistent storage (ChromaDB only)
            collection_name: Name of the vector collection
        """
        from app.core.config import settings

        self.backend = backend.lower() if backend else settings.VECTOR_STORE_BACKEND.lower()
        self.persist_directory = persist_directory or settings.VECTOR_STORE_PATH
        self.collection_name = collection_name

        # Storage for file-specific vector stores (in-memory mapping for FAISS/Chroma)
        self._stores: Dict[str, Any] = {}

        # Milvus client (lazy initialization)
        self._milvus_client: Optional[Any] = None

        # FAISS persistence directory with store_type isolation
        self._faiss_persist_dir = Path(FAISS_PERSIST_DIR)
        self._faiss_file_dir = self._faiss_persist_dir / "files"
        self._faiss_skill_dir = self._faiss_persist_dir / "skills"

        # Create directories for both store types
        self._faiss_file_dir.mkdir(parents=True, exist_ok=True)
        self._faiss_skill_dir.mkdir(parents=True, exist_ok=True)

        # Auto-load persisted FAISS indices on startup
        if self.backend == "faiss":
            self._load_all_faiss_stores()

        logger.info(f"Vector Store Provider initialized with backend: {self.backend}")

    def _save_faiss_store(self, store_id: str, vector_store: Any, store_type: str = "file") -> bool:
        """
        Save a FAISS vector store to disk for persistence.

        Args:
            store_id: Vector store identifier
            vector_store: FAISS vector store instance
            store_type: Store type ("file" or "skill") for isolation

        Returns:
            bool: True if saved successfully
        """
        try:
            # Determine base directory by store type
            if store_type == "skill":
                base_dir = self._faiss_skill_dir
            else:
                base_dir = self._faiss_file_dir

            store_path = base_dir / store_id
            store_path.mkdir(parents=True, exist_ok=True)

            # Save FAISS index
            vector_store.save_local(str(store_path))

            logger.info(f"Saved FAISS store '{store_id}' ({store_type}) to {store_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save FAISS store '{store_id}': {str(e)}")
            return False

    def _load_faiss_store(self, store_id: str, embeddings: Any, store_type: str = "file") -> Optional[Any]:
        """
        Load a FAISS vector store from disk.

        Args:
            store_id: Vector store identifier
            embeddings: Embedding model for loading
            store_type: Store type ("file" or "skill") for isolation

        Returns:
            FAISS vector store instance or None if not found
        """
        from langchain_community.vectorstores import FAISS

        try:
            # Determine base directory by store type
            if store_type == "skill":
                base_dir = self._faiss_skill_dir
            else:
                base_dir = self._faiss_file_dir

            store_path = base_dir / store_id

            if not store_path.exists():
                return None

            # ✅ FIX: MUST include allow_dangerous_deserialization=True
            # LangChain requires this for security - we trust our own FAISS indices
            vector_store = FAISS.load_local(
                str(store_path),
                embeddings,
                allow_dangerous_deserialization=True
            )

            logger.info(f"Loaded FAISS store '{store_id}' ({store_type}) from {store_path}")
            return vector_store

        except Exception as e:
            logger.error(f"Failed to load FAISS store '{store_id}': {str(e)}")
            return None

    def _load_all_faiss_stores(self):
        """
        Load all persisted FAISS stores on startup.
        Iterates over both 'files/' and 'skills/' subdirectories.
        Uses appropriate embedding provider for each store type:
        - files: default embedding provider (384 dim)
        - skills: BGE-M3 embedding provider (1024 dim)
        """
        from app.Providers.embedding_provider.client import get_embedding_provider

        try:
            if not self._faiss_persist_dir.exists():
                logger.info("No FAISS persistence directory found, starting fresh")
                return

            loaded_count = 0

            # Load file stores from files/ directory (default 384-dim embeddings)
            if self._faiss_file_dir.exists():
                file_embedding_provider = get_embedding_provider()
                file_embeddings = file_embedding_provider.get_underlying_model()

                for store_dir in self._faiss_file_dir.iterdir():
                    if store_dir.is_dir():
                        store_id = store_dir.name
                        vector_store = self._load_faiss_store(store_id, file_embeddings, store_type="file")
                        if vector_store is not None:
                            self._stores[store_id] = vector_store
                            loaded_count += 1

            # Load skill stores from skills/ directory (BGE-M3 1024-dim embeddings)
            if self._faiss_skill_dir.exists():
                try:
                    from app.Providers.bge_embedding_provider import get_bge_embedding_provider

                    # Create BGE-M3 wrapper for FAISS compatibility
                    bge_provider = get_bge_embedding_provider()

                    # Import LangChain Embeddings base class
                    from langchain_core.embeddings import Embeddings as LCEmbeddings

                    class BGEEmbeddingWrapper(LCEmbeddings):
                        """Wrapper to make BGE-M3 compatible with LangChain FAISS"""
                        def __init__(self, provider):
                            self._provider = provider
                            # DO NOT call super().__init__() - causes the error
                            # LangChain Embeddings is an ABC with no __init__ params

                        def embed_query(self, text: str):
                            """Embed a single query text"""
                            return self._provider.embed_single(text).tolist()

                        def embed_documents(self, texts):
                            """Embed a list of documents"""
                            return [self._provider.embed_single(t).tolist() for t in texts]

                    skill_embeddings = BGEEmbeddingWrapper(bge_provider)

                    for store_dir in self._faiss_skill_dir.iterdir():
                        if store_dir.is_dir():
                            store_id = store_dir.name
                            vector_store = self._load_faiss_store(store_id, skill_embeddings, store_type="skill")
                            if vector_store is not None:
                                self._stores[store_id] = vector_store
                                loaded_count += 1

                except ImportError as e:
                    logger.warning(f"BGE-M3 provider not available, skipping skill stores: {e}")

            if loaded_count > 0:
                logger.info(f"Loaded {loaded_count} FAISS stores from disk: {list(self._stores.keys())}")
            else:
                logger.info("No persisted FAISS stores found")

        except Exception as e:
            logger.error(f"Failed to load persisted FAISS stores: {str(e)}")

    def create_store_from_texts(
        self,
        texts: List[str],
        embeddings: Any,  # HuggingFaceEmbeddings instance or pre-computed embeddings
        metadatas: Optional[List[dict]] = None,
        file_id: Optional[str] = None,
        store_type: str = "file",
        precomputed_embeddings: Optional[List] = None
    ) -> str:
        """
        Create a vector store from text chunks and embeddings

        Args:
            texts: List of text chunks
            embeddings: Embedding provider instance (ignored if precomputed_embeddings provided)
            metadatas: Metadata for each chunk (e.g., file_id, chunk_index)
            file_id: Unique identifier for this file's vector store
            store_type: Store type ("file" or "skill") for physical isolation
            precomputed_embeddings: Optional pre-computed embeddings for texts

        Returns:
            str: Store identifier (file_id or generated ID)

        Example:
            >>> texts = ["chunk1", "chunk2"]
            >>> embeddings = get_embedding_provider()
            >>> store_id = provider.create_store_from_texts(texts, embeddings)
        """
        from langchain_community.vectorstores import FAISS
        import numpy as np

        if self.backend == "faiss":
            # Create FAISS vector store
            if precomputed_embeddings is not None:
                # Use pre-computed embeddings (for BGE-M3)
                import faiss

                # Convert to numpy array if needed
                if not isinstance(precomputed_embeddings, np.ndarray):
                    precomputed_embeddings = np.array(precomputed_embeddings).astype('float32')

                # Create FAISS index
                dimension = precomputed_embeddings.shape[1]
                index = faiss.IndexFlatL2(dimension)

                # Batch add for large datasets (reduces memory pressure)
                # Default batch size: 10000 vectors per batch
                faiss_batch_size = 10000
                total_vectors = len(precomputed_embeddings)

                if total_vectors <= faiss_batch_size:
                    # Small dataset: add all at once (original behavior)
                    index.add(precomputed_embeddings)
                else:
                    # Large dataset: batch add for memory efficiency
                    for i in range(0, total_vectors, faiss_batch_size):
                        batch = precomputed_embeddings[i:i + faiss_batch_size]
                        index.add(batch)
                        logger.debug(f"FAISS batch add: {i + len(batch)}/{total_vectors} vectors")
                    logger.info(f"FAISS batch add complete: {total_vectors} vectors in {(total_vectors + faiss_batch_size - 1) // faiss_batch_size} batches")

                # Create FAISS wrapper with texts and metadata
                from langchain_community.docstore.in_memory import InMemoryDocstore
                from langchain_core.documents import Document

                documents = []
                for i, text in enumerate(texts):
                    doc = Document(
                        page_content=text,
                        metadata=metadatas[i] if metadatas else {}
                    )
                    documents.append(doc)

                # Create docstore
                docstore = InMemoryDocstore({str(i): doc for i, doc in enumerate(documents)})

                # ✅ FIX: Create LangChain-compatible wrapper for BGE embeddings
                # If embeddings is BGEEmbeddingProvider, wrap it
                if hasattr(embeddings, 'embed_single') and not hasattr(embeddings, 'embed_query'):
                    # This is BGEEmbeddingProvider, wrap it
                    from langchain_core.embeddings import Embeddings as LCEmbeddings

                    class BGEWrapper(LCEmbeddings):
                        def __init__(self, provider):
                            self._provider = provider
                        def embed_query(self, text: str):
                            return self._provider.embed_single(text).tolist()
                        def embed_documents(self, texts):
                            return [self._provider.embed_single(t).tolist() for t in texts]

                    embedding_function = BGEWrapper(embeddings)
                else:
                    # Already LangChain-compatible or None
                    embedding_function = embeddings

                # Create vector store wrapper
                vector_store = FAISS(
                    embedding_function=embedding_function,
                    index=index,
                    docstore=docstore,
                    index_to_docstore_id={i: str(i) for i in range(len(texts))}
                )
            else:
                # Use regular embedding provider
                vector_store = FAISS.from_texts(
                    texts=texts,
                    embedding=embeddings,
                    metadatas=metadatas
                )

            # Store in memory with file_id as key
            store_id = file_id or f"store_{len(self._stores)}"
            self._stores[store_id] = vector_store

            # Auto-save to disk for persistence across restarts with store_type
            self._save_faiss_store(store_id, vector_store, store_type=store_type)

            logger.info(f"Created FAISS store '{store_id}' with {len(texts)} chunks (persisted to disk)")
            return store_id

        elif self.backend == "chroma":
            # ChromaDB implementation
            try:
                import chromadb
                from langchain_community.vectorstores import Chroma

                # Create persistent ChromaDB
                persist_path = Path(self.persist_directory)
                persist_path.mkdir(parents=True, exist_ok=True)

                vector_store = Chroma.from_texts(
                    texts=texts,
                    embedding=embeddings,
                    metadatas=metadatas,
                    collection_name=self.collection_name,
                    persist_directory=str(persist_path)
                )

                store_id = file_id or f"store_{len(self._stores)}"
                self._stores[store_id] = vector_store

                logger.info(f"Created ChromaDB store '{store_id}' with {len(texts)} chunks")
                return store_id

            except ImportError:
                logger.error("ChromaDB not installed. Install with: pip install chromadb")
                raise

        elif self.backend == "milvus":
            # Milvus implementation
            try:
                from app.Providers.vector_store_provider.milvus_client import MilvusClient
                from app.Providers.embedding_provider.client import EmbeddingProvider

                # Initialize Milvus client if not already done
                if self._milvus_client is None:
                    self._milvus_client = MilvusClient()
                    self._milvus_client.connect()

                store_id = file_id or f"store_{len(self._stores)}"

                # Generate embeddings from texts
                embedding_vectors = embeddings.embed_documents(texts)

                # Create partition for this file
                partition_name = self._milvus_client.create_partition(store_id)

                # Prepare chunk indices
                chunk_indices = list(range(len(texts)))
                if metadatas:
                    chunk_indices = [m.get("chunk_index", i) for i, m in enumerate(metadatas)]

                # Insert vectors into Milvus
                self._milvus_client.insert_vectors(
                    file_id=store_id,
                    texts=texts,
                    embeddings=embedding_vectors,
                    chunk_indices=chunk_indices
                )

                # Store file_id in memory mapping (for lookup)
                self._stores[store_id] = {"type": "milvus", "partition": partition_name}

                logger.info(f"Created Milvus store '{store_id}' with {len(texts)} chunks in partition '{partition_name}'")
                return store_id

            except ImportError as e:
                logger.error(f"Milvus dependencies not installed: {str(e)}")
                raise
            except Exception as e:
                logger.error(f"Failed to create Milvus store: {str(e)}")
                raise

        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    def similarity_search(
        self,
        store_id: str,
        query: str,
        k: int = 5,
        filter_dict: Optional[dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search in a vector store

        Args:
            store_id: Vector store identifier
            query: Query string
            k: Number of results to return
            filter_dict: Metadata filters (e.g., {"file_id": "doc1"})

        Returns:
            List of dicts with 'content', 'metadata', and optionally 'score'

        Example:
            >>> results = provider.similarity_search(
            ...     store_id="file_123",
            ...     query="What is RAG?",
            ...     k=3
            ... )
            >>> print(results[0]['content'])
        """
        # ✅ FIX: Try lazy-loading if store not in memory
        if store_id not in self._stores:
            # Attempt to load store from disk (may be skill or file)
            vector_store = self._try_lazy_load_store(store_id)
            if vector_store is None:
                raise ValueError(f"Vector store '{store_id}' not found")
            self._stores[store_id] = vector_store

        vector_store = self._stores[store_id]

        try:
            # Check if this is a Milvus store
            if isinstance(vector_store, dict) and vector_store.get("type") == "milvus":
                # Milvus similarity search
                from app.Providers.embedding_provider.client import get_embedding_provider

                # Get embedding provider for query embedding
                embedding_provider = get_embedding_provider()
                query_embedding = embedding_provider.get_embedding(query)

                # Search in Milvus
                search_results = self._milvus_client.search_similar_vectors(
                    file_id=store_id,
                    query_embedding=query_embedding,
                    top_k=k
                )

                # Format results
                results = []
                for result in search_results:
                    results.append({
                        "content": result.get("content", ""),
                        "metadata": {
                            "file_id": result.get("file_id", store_id),
                            "chunk_index": result.get("chunk_index", 0)
                        }
                    })

                logger.info(f"Found {len(results)} similar documents for store '{store_id}' in Milvus")
                return results

            else:
                # FAISS/ChromaDB similarity search
                if filter_dict:
                    docs = vector_store.similarity_search(
                        query,
                        k=k,
                        filter=filter_dict
                    )
                else:
                    docs = vector_store.similarity_search(query, k=k)

                # Format results
                results = []
                for doc in docs:
                    results.append({
                        "content": doc.page_content,
                        "metadata": doc.metadata
                    })

                logger.info(f"Found {len(results)} similar documents for store '{store_id}'")
                return results

        except Exception as e:
            logger.error(f"Error during similarity search: {str(e)}")
            raise

    def similarity_search_with_score(
        self,
        store_id: str,
        query: str,
        k: int = 5,
        filter_dict: Optional[dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search with relevance scores

        Args:
            store_id: Vector store identifier
            query: Query string
            k: Number of results to return
            filter_dict: Metadata filters

        Returns:
            List of dicts with 'content', 'metadata', and 'score'

        Example:
            >>> results = provider.similarity_search_with_score(
            ...     store_id="file_123",
            ...     query="What is RAG?",
            ...     k=3
            ... )
            >>> print(f"Score: {results[0]['score']}, Content: {results[0]['content']}")
        """
        # ✅ FIX: Try lazy-loading if store not in memory
        if store_id not in self._stores:
            # Attempt to load store from disk (may be skill or file)
            vector_store = self._try_lazy_load_store(store_id)
            if vector_store is None:
                raise ValueError(f"Vector store '{store_id}' not found")
            self._stores[store_id] = vector_store

        vector_store = self._stores[store_id]

        try:
            # Check if this is a Milvus store
            if isinstance(vector_store, dict) and vector_store.get("type") == "milvus":
                # Milvus similarity search (includes scores)
                from app.Providers.embedding_provider.client import get_embedding_provider

                # Get embedding provider for query embedding
                embedding_provider = get_embedding_provider()
                query_embedding = embedding_provider.get_embedding(query)

                # Search in Milvus
                search_results = self._milvus_client.search_similar_vectors(
                    file_id=store_id,
                    query_embedding=query_embedding,
                    top_k=k
                )

                # Format results
                results = []
                for result in search_results:
                    results.append({
                        "content": result.get("content", ""),
                        "metadata": {
                            "file_id": result.get("file_id", store_id),
                            "chunk_index": result.get("chunk_index", 0)
                        },
                        "score": result.get("distance", 0.0)  # Milvus returns distance
                    })

                logger.info(f"Found {len(results)} similar documents with scores for store '{store_id}' in Milvus")
                return results

            else:
                # FAISS/ChromaDB similarity search with scores
                if filter_dict:
                    docs_with_scores = vector_store.similarity_search_with_score(
                        query,
                        k=k,
                        filter=filter_dict
                    )
                else:
                    docs_with_scores = vector_store.similarity_search_with_score(query, k=k)

                # Format results
                results = []
                for doc, score in docs_with_scores:
                    results.append({
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "score": float(score)
                    })

                logger.info(f"Found {len(results)} similar documents with scores for store '{store_id}'")
                return results

        except Exception as e:
            logger.error(f"Error during similarity search with score: {str(e)}")
            raise

    def get_store(self, store_id: str) -> Any:
        """
        Get raw vector store instance

        Args:
            store_id: Vector store identifier

        Returns:
            Vector store instance (FAISS or Chroma)
        """
        if store_id not in self._stores:
            raise ValueError(f"Vector store '{store_id}' not found")

        return self._stores[store_id]

    def list_stores(self) -> List[str]:
        """
        List all vector store IDs

        Returns:
            List of store identifiers
        """
        return list(self._stores.keys())

    def _try_lazy_load_store(self, store_id: str) -> Optional[Any]:
        """
        Try lazy-loading a FAISS store from disk when not in memory.
        Attempts both skill and file store types.

        Args:
            store_id: Vector store identifier

        Returns:
            FAISS vector store instance or None if not found
        """
        # Try skill stores first (with BGE-M3 embeddings)
        skill_path = self._faiss_skill_dir / store_id
        if skill_path.exists():
            try:
                from app.Providers.bge_embedding_provider import get_bge_embedding_provider
                from langchain_core.embeddings import Embeddings as LCEmbeddings

                class BGEEmbeddingWrapper(LCEmbeddings):
                    """Wrapper to make BGE-M3 compatible with LangChain FAISS"""
                    def __init__(self, provider):
                        self._provider = provider
                    def embed_query(self, text: str):
                        return self._provider.embed_single(text).tolist()
                    def embed_documents(self, texts):
                        return [self._provider.embed_single(t).tolist() for t in texts]

                bge_provider = get_bge_embedding_provider()
                skill_embeddings = BGEEmbeddingWrapper(bge_provider)

                vector_store = self._load_faiss_store(store_id, skill_embeddings, store_type="skill")
                if vector_store is not None:
                    logger.info(f"✅ Lazy-loaded skill store '{store_id}'")
                    return vector_store
            except Exception as e:
                logger.warning(f"Failed to lazy-load skill store '{store_id}': {e}")

        # Try file stores (with default embeddings)
        file_path = self._faiss_file_dir / store_id
        if file_path.exists():
            try:
                from app.Providers.embedding_provider.client import get_embedding_provider

                file_embedding_provider = get_embedding_provider()
                file_embeddings = file_embedding_provider.get_underlying_model()

                vector_store = self._load_faiss_store(store_id, file_embeddings, store_type="file")
                if vector_store is not None:
                    logger.info(f"✅ Lazy-loaded file store '{store_id}'")
                    return vector_store
            except Exception as e:
                logger.warning(f"Failed to lazy-load file store '{store_id}': {e}")

        return None

    def delete_store(self, store_id: str):
        """
        Delete a vector store (from memory and disk)

        Args:
            store_id: Vector store identifier
        """
        import shutil

        if store_id in self._stores:
            del self._stores[store_id]

            # Also delete persisted FAISS store if exists
            if self.backend == "faiss":
                store_path = self._faiss_persist_dir / store_id
                if store_path.exists():
                    shutil.rmtree(store_path)
                    logger.info(f"Deleted persisted FAISS store '{store_id}'")

            logger.info(f"Deleted vector store '{store_id}'")
        else:
            logger.warning(f"Attempted to delete non-existent store '{store_id}'")


# Singleton instance for dependency injection
_vector_store_provider_instance: Optional[VectorStoreProvider] = None


def get_vector_store_provider() -> VectorStoreProvider:
    """
    FastAPI dependency for Vector Store Provider (Singleton)

    Usage in endpoints:
        @router.post("/upload")
        async def upload(
            vector_provider: VectorStoreProvider = Depends(get_vector_store_provider)
        ):
            ...
    """
    global _vector_store_provider_instance

    if _vector_store_provider_instance is None:
        _vector_store_provider_instance = VectorStoreProvider()

    return _vector_store_provider_instance
