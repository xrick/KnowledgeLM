# app/SkillServices/skill_retrieval_service.py
"""
Skill Retrieval Service

Skill-based RAG retrieval using FAISS vector stores.
Implements AbstractRetrievalService interface for polymorphism.
"""

import logging
from typing import List, Dict, Optional, Any
from fastapi import Depends

# Reference to existing Services (not duplicating code)
from app.SkillServices.base_retrieval import AbstractRetrievalService
from app.Providers.embedding_provider.client import EmbeddingProvider, get_embedding_provider
from app.Providers.vector_store_provider.client import VectorStoreProvider, get_vector_store_provider

logger = logging.getLogger(__name__)


class SkillRetrievalService(AbstractRetrievalService):
    """
    Skill-based retrieval service

    Implements AbstractRetrievalService interface for skill-based RAG.
    Uses store_type="skill" for physical isolation from file-based stores.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
        vector_store_provider: VectorStoreProvider = Depends(get_vector_store_provider)
    ):
        self.embedding_provider = embedding_provider
        self.vector_store_provider = vector_store_provider

        logger.info("Skill Retrieval Service initialized")

    async def add_content(
        self,
        content_id: str,  # skill_id
        chunks: List[str],
        metadata: Optional[List[dict]] = None,
        embeddings: Optional[List] = None  # Pre-computed embeddings for BGE-M3
    ) -> str:
        """Add skill chunks to vector store with store_type='skill'"""
        try:
            # ✅ FIX: BGEEmbeddingProvider doesn't have get_underlying_model()
            # It IS the embedding provider, create wrapper for LangChain compatibility
            from app.Providers.vector_store_provider.client import VectorStoreProvider

            # Use the BGEEmbeddingWrapper from VectorStoreProvider
            embedding_provider = self.embedding_provider

            # Enhance metadata with skill_id
            if metadata is None:
                metadata = [{"skill_id": content_id, "chunk_index": i} for i in range(len(chunks))]
            else:
                for i, meta in enumerate(metadata):
                    meta["skill_id"] = content_id
                    if "chunk_index" not in meta:
                        meta["chunk_index"] = i

            # Create vector store with store_type="skill" for isolation
            store_id = self.vector_store_provider.create_store_from_texts(
                texts=chunks,
                embeddings=embedding_provider,
                metadatas=metadata,
                file_id=content_id,  # Use skill_id as store identifier
                store_type="skill",   # Physical isolation from file stores
                precomputed_embeddings=embeddings  # Pass pre-computed embeddings if available
            )

            logger.info(f"Added {len(chunks)} chunks for skill '{content_id}' to store '{store_id}'")
            return store_id

        except Exception as e:
            logger.error(f"Error adding skill chunks: {str(e)}")
            raise

    async def retrieve_context(
        self,
        query: str,
        content_ids: List[str],  # skill_ids
        top_k: int = 5,
        include_scores: bool = False,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant context from skills"""
        try:
            all_results = []

            logger.info(f"Skill retrieval: query='{query[:50]}...', skill_ids={content_ids}, top_k={top_k}")

            # Search in each skill's vector store
            for skill_id in content_ids:
                try:
                    if include_scores:
                        results = self.vector_store_provider.similarity_search_with_score(
                            store_id=skill_id,
                            query=query,
                            k=top_k
                        )
                    else:
                        results = self.vector_store_provider.similarity_search(
                            store_id=skill_id,
                            query=query,
                            k=top_k
                        )

                    logger.info(f"  Retrieved {len(results)} chunks from skill {skill_id}")
                    all_results.extend(results)

                except ValueError as e:
                    logger.warning(f"Store not found for skill_id '{skill_id}': {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"Error searching skill '{skill_id}': {str(e)}")
                    continue

            # Sort by score if available (lower is better for FAISS)
            if include_scores and all_results:
                all_results.sort(key=lambda x: x.get('score', float('inf')))

            # Limit to top_k overall results
            final_results = all_results[:top_k]

            logger.info(f"Retrieved {len(final_results)} context chunks from {len(content_ids)} skills")
            return final_results

        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            raise

    async def delete_content(self, content_id: str):
        """Delete skill's vector store"""
        try:
            self.vector_store_provider.delete_store(content_id)
            logger.info(f"Deleted skill vector store: {content_id}")
        except Exception as e:
            logger.error(f"Error deleting skill '{content_id}': {str(e)}")
            raise

    def get_retrieval_mode(self) -> str:
        return "skill_based"


# ============================================================================
# Dependency Injection
# ============================================================================

def get_skill_retrieval_service(
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store_provider: VectorStoreProvider = Depends(get_vector_store_provider)
) -> SkillRetrievalService:
    """FastAPI dependency for Skill Retrieval Service"""
    return SkillRetrievalService(
        embedding_provider=embedding_provider,
        vector_store_provider=vector_store_provider
    )
