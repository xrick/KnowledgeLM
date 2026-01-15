# app/Services/retrieval_service.py
"""
Retrieval Service

Coordinates embedding and vector store providers for document retrieval.
Handles query processing and context assembly for RAG pipeline.
"""

import logging
from typing import List, Dict, Optional, Any
from fastapi import Depends

from app.Providers.embedding_provider.client import EmbeddingProvider, get_embedding_provider
from app.Providers.vector_store_provider.client import VectorStoreProvider, get_vector_store_provider

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    Retrieval Service for RAG pipeline

    Coordinates embedding generation and vector similarity search.
    Ensures answers come only from uploaded documents.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
        vector_store_provider: VectorStoreProvider = Depends(get_vector_store_provider)
    ):
        """
        Initialize Retrieval Service

        Args:
            embedding_provider: Provider for text embeddings
            vector_store_provider: Provider for vector storage and search
        """
        self.embedding_provider = embedding_provider
        self.vector_store_provider = vector_store_provider

        logger.info("Retrieval Service initialized")

    async def add_document_chunks(
        self,
        file_id: str,
        chunks: List[str],
        metadata: Optional[List[dict]] = None
    ) -> str:
        """
        Add document chunks to vector store

        Args:
            file_id: Unique identifier for the document
            chunks: List of text chunks from the document
            metadata: Optional metadata for each chunk

        Returns:
            str: Vector store identifier

        Example:
            >>> chunks = ["chunk1 text", "chunk2 text"]
            >>> metadata = [{"chunk_index": 0}, {"chunk_index": 1}]
            >>> store_id = await service.add_document_chunks("file_123", chunks, metadata)
        """
        try:
            # Get the underlying embedding model for LangChain integration
            embeddings = self.embedding_provider.get_underlying_model()

            # Enhance metadata with file_id
            if metadata is None:
                metadata = [{"file_id": file_id, "chunk_index": i} for i in range(len(chunks))]
            else:
                for i, meta in enumerate(metadata):
                    meta["file_id"] = file_id
                    if "chunk_index" not in meta:
                        meta["chunk_index"] = i

            # Create vector store from chunks
            store_id = self.vector_store_provider.create_store_from_texts(
                texts=chunks,
                embeddings=embeddings,
                metadatas=metadata,
                file_id=file_id
            )

            logger.info(f"Added {len(chunks)} chunks for file '{file_id}' to store '{store_id}'")
            return store_id

        except Exception as e:
            logger.error(f"Error adding document chunks: {str(e)}")
            raise

    async def retrieve_context(
        self,
        query: str,
        file_ids: List[str],
        top_k: int = 5,
        include_scores: bool = False,
        fair_distribution: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context for a query from specific files

        Args:
            query: User query text
            file_ids: List of file IDs to search within
            top_k: Number of top results to return
            include_scores: Whether to include similarity scores
            fair_distribution: If True, ensures each file gets representation (for multi-doc summaries)

        Returns:
            List of context dicts with 'content', 'metadata', and optionally 'score'

        Example:
            >>> context = await service.retrieve_context(
            ...     query="What is RAG?",
            ...     file_ids=["file_123", "file_456"],
            ...     top_k=3
            ... )
            >>> print(context[0]['content'])
        """
        try:
            all_results = []

            # Log retrieval parameters
            logger.info(f"retrieve_context called: query='{query[:50]}...', file_ids={file_ids}, fair_distribution={fair_distribution}")

            # Fair distribution mode: ensure each file gets representation
            if fair_distribution and len(file_ids) > 1:
                # Calculate chunks per file to ensure fair distribution
                chunks_per_file = max(1, top_k // len(file_ids))
                logger.info(f"Fair distribution mode: {chunks_per_file} chunks per file for {len(file_ids)} files")

                # Search in each file's vector store
                for file_id in file_ids:
                    try:
                        if include_scores:
                            results = self.vector_store_provider.similarity_search_with_score(
                                store_id=file_id,
                                query=query,
                                k=chunks_per_file
                            )
                        else:
                            results = self.vector_store_provider.similarity_search(
                                store_id=file_id,
                                query=query,
                                k=chunks_per_file
                            )

                        logger.info(f"  [Fair] Retrieved {len(results)} chunks from file {file_id}")
                        all_results.extend(results)

                    except ValueError as e:
                        logger.warning(f"Store not found for file_id '{file_id}': {str(e)}")
                        continue
                    except Exception as e:
                        logger.error(f"Error searching in store '{file_id}': {str(e)}")
                        continue

                # If we have remaining capacity, add more chunks from best matches
                if len(all_results) < top_k and include_scores:
                    remaining = top_k - len(all_results)
                    for file_id in file_ids:
                        try:
                            # Get more chunks from this file
                            extra_results = self.vector_store_provider.similarity_search_with_score(
                                store_id=file_id,
                                query=query,
                                k=chunks_per_file + remaining
                            )
                            # Add chunks we don't already have
                            existing_contents = {r['content'] for r in all_results}
                            for result in extra_results:
                                if result['content'] not in existing_contents and len(all_results) < top_k:
                                    all_results.append(result)
                                    existing_contents.add(result['content'])
                        except:
                            continue

                final_results = all_results[:top_k]

            # Standard mode: retrieve top_k from each file, then rank globally
            else:
                logger.info(f"Standard mode: {top_k} chunks per file for {len(file_ids)} files")
                # Search in each file's vector store
                for file_id in file_ids:
                    try:
                        if include_scores:
                            results = self.vector_store_provider.similarity_search_with_score(
                                store_id=file_id,
                                query=query,
                                k=top_k
                            )
                        else:
                            results = self.vector_store_provider.similarity_search(
                                store_id=file_id,
                                query=query,
                                k=top_k
                            )

                        logger.info(f"  [Std] Retrieved {len(results)} chunks from file {file_id}")
                        all_results.extend(results)

                    except ValueError as e:
                        logger.warning(f"Store not found for file_id '{file_id}': {str(e)}")
                        continue
                    except Exception as e:
                        logger.error(f"Error searching in store '{file_id}': {str(e)}")
                        continue

                # Sort by score if available (lower is better for FAISS)
                if include_scores and all_results:
                    all_results.sort(key=lambda x: x.get('score', float('inf')))

                # Limit to top_k overall results
                final_results = all_results[:top_k]

            logger.info(f"Retrieved {len(final_results)} context chunks for query from {len(file_ids)} files")

            # DEBUG: Log retrieved chunks preview
            logger.debug(f"Retrieval details - file_ids: {file_ids}")
            for i, result in enumerate(final_results[:3]):  # Log first 3 chunks
                content_preview = result.get('content', '')[:150]
                metadata = result.get('metadata', {})
                logger.debug(f"Chunk {i+1}: file_id={metadata.get('file_id', 'N/A')}, preview={content_preview}...")

            return final_results

        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            raise

    async def retrieve_context_text(
        self,
        query: str,
        file_ids: List[str],
        top_k: int = 5
    ) -> str:
        """
        Retrieve context as a single concatenated text string

        Args:
            query: User query text
            file_ids: List of file IDs to search within
            top_k: Number of top results to return

        Returns:
            str: Concatenated context text

        Example:
            >>> context_text = await service.retrieve_context_text(
            ...     query="What is RAG?",
            ...     file_ids=["file_123"],
            ...     top_k=3
            ... )
            >>> print(context_text)
        """
        results = await self.retrieve_context(
            query=query,
            file_ids=file_ids,
            top_k=top_k,
            include_scores=False
        )

        # Concatenate all content with separators
        context_parts = [result['content'] for result in results]
        context_text = "\n\n---\n\n".join(context_parts)

        return context_text

    def list_available_stores(self) -> List[str]:
        """
        List all available vector store IDs

        Returns:
            List of store identifiers (file IDs)
        """
        return self.vector_store_provider.list_stores()

    async def delete_document(self, file_id: str):
        """
        Delete a document's vector store

        Args:
            file_id: Document identifier
        """
        try:
            self.vector_store_provider.delete_store(file_id)
            logger.info(f"Deleted vector store for file '{file_id}'")
        except Exception as e:
            logger.error(f"Error deleting document '{file_id}': {str(e)}")
            raise


# Dependency injection helper
def get_retrieval_service(
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store_provider: VectorStoreProvider = Depends(get_vector_store_provider)
) -> RetrievalService:
    """
    FastAPI dependency for Retrieval Service

    Usage in endpoints:
        @router.post("/upload")
        async def upload(
            retrieval_service: RetrievalService = Depends(get_retrieval_service)
        ):
            ...
    """
    return RetrievalService(
        embedding_provider=embedding_provider,
        vector_store_provider=vector_store_provider
    )
