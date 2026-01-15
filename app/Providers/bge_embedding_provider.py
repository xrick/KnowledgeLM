# app/Providers/bge_embedding_provider.py
"""
BGE-M3 Embedding Provider for Legal Documents
Provides multilingual embeddings optimized for Chinese legal text
"""

import logging
import os
from typing import List, Dict, Any, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
import torch

logger = logging.getLogger(__name__)

class BGEEmbeddingProvider:
    """
    Provider for BGE-M3 embeddings
    BGE-M3 is a multilingual model with 1024 dimensions,
    particularly effective for Chinese text
    """

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = None):
        """
        Initialize BGE-M3 embedding provider

        Args:
            model_name: Model identifier (default: BAAI/bge-m3)
            device: Device to use (cpu/cuda), auto-detect if None
        """
        self.model_name = model_name
        self.device = device or ('cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu')
        self.dimension = 1024  # BGE-M3 has 1024 dimensions
        self.max_sequence_length = 8192  # BGE-M3 supports up to 8192 tokens

        # Disable hf_transfer to avoid incomplete downloads (fix for config.json missing issue)
        os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'

        try:
            logger.info(f"Loading BGE-M3 model on {self.device}...")
            self.model = SentenceTransformer(model_name, device=self.device)

            # Set max sequence length
            self.model.max_seq_length = self.max_sequence_length

            # Enable fp16 for faster inference on GPU
            if self.device == 'cuda':
                self.model = self.model.half()
            
            if self.device == 'mps':
                self.model = self.model.half()

            logger.info(f"✅ BGE-M3 model loaded successfully (dim={self.dimension})")

        except Exception as e:
            logger.error(f"Failed to load BGE-M3 model: {str(e)}")
            logger.info("Falling back to sentence-transformers for BGE-M3...")
            # Try alternative loading method
            try:
                from FlagEmbedding import FlagModel
                self.model = FlagModel(model_name, use_fp16=(self.device == 'cuda'))
                self.use_flag_embedding = True
                logger.info("✅ BGE-M3 loaded via FlagEmbedding")
            except:
                raise RuntimeError(f"Could not load BGE-M3 model: {str(e)}")

    def embed_texts(self, texts: List[str],
                   batch_size: int = 32,
                   normalize: bool = True,
                   show_progress: bool = False) -> np.ndarray:
        """
        Generate embeddings for a list of texts

        Args:
            texts: List of text strings to embed
            batch_size: Batch size for processing
            normalize: Whether to normalize embeddings
            show_progress: Show progress bar

        Returns:
            Numpy array of embeddings (shape: [n_texts, 1024])
        """
        if not texts:
            return np.array([])

        try:
            # Clean texts - remove excessive whitespace
            cleaned_texts = [self._clean_text(text) for text in texts]

            # Generate embeddings
            logger.info(f"Generating embeddings for {len(cleaned_texts)} texts...")

            if hasattr(self, 'use_flag_embedding') and self.use_flag_embedding:
                # Use FlagEmbedding
                embeddings = self.model.encode(cleaned_texts, batch_size=batch_size)
            else:
                # Use SentenceTransformers
                embeddings = self.model.encode(
                    cleaned_texts,
                    batch_size=batch_size,
                    normalize_embeddings=normalize,
                    show_progress_bar=show_progress,
                    convert_to_numpy=True
                )

            # Ensure correct shape
            if len(embeddings.shape) == 1:
                embeddings = embeddings.reshape(1, -1)

            logger.info(f"✅ Generated {embeddings.shape[0]} embeddings (dim={embeddings.shape[1]})")

            return embeddings

        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise

    def embed_single(self, text: str, normalize: bool = True) -> np.ndarray:
        """
        Generate embedding for a single text

        Args:
            text: Text string to embed
            normalize: Whether to normalize embedding

        Returns:
            Numpy array of embedding (shape: [1024,])
        """
        embeddings = self.embed_texts([text], normalize=normalize)
        return embeddings[0] if len(embeddings) > 0 else np.zeros(self.dimension)

    def _clean_text(self, text: str) -> str:
        """
        Clean text for embedding

        Args:
            text: Raw text

        Returns:
            Cleaned text
        """
        # Remove excessive whitespace
        text = ' '.join(text.split())

        # Truncate if too long (leave room for special tokens)
        max_chars = self.max_sequence_length * 3  # Approximate char limit
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        return text

    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Cosine similarity score
        """
        # Flatten if needed
        embedding1 = embedding1.flatten()
        embedding2 = embedding2.flatten()

        # Compute cosine similarity
        dot_product = np.dot(embedding1, embedding2)
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)
        return float(similarity)

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the model

        Returns:
            Dictionary with model information
        """
        return {
            "model_name": self.model_name,
            "dimension": self.dimension,
            "max_sequence_length": self.max_sequence_length,
            "device": self.device,
            "type": "BGE-M3",
            "language_support": "multilingual (optimized for Chinese)",
            "features": [
                "Dense embeddings (1024d)",
                "Multilingual support",
                "Long context (8192 tokens)",
                "Optimized for retrieval"
            ]
        }


# Singleton instance
_bge_provider_instance = None

def get_bge_embedding_provider() -> BGEEmbeddingProvider:
    """Get or create BGE embedding provider singleton"""
    global _bge_provider_instance
    if _bge_provider_instance is None:
        _bge_provider_instance = BGEEmbeddingProvider()
    return _bge_provider_instance