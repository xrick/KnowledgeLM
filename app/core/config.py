# app/core/config.py
"""
Application Configuration

Centralized configuration using Pydantic Settings for environment variable management.
Supports enterprise-grade storage backends: Milvus, MongoDB, Redis, SQLite.
"""

from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application Settings

    All configuration loaded from environment variables or .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # =============================================================================
    # Application Settings
    # =============================================================================
    APP_NAME: str = "DocAI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # =============================================================================
    # LLM Provider Settings
    # =============================================================================
    LLM_PROVIDER_BASE_URL: str = "http://localhost:11434/v1"
    # LLM_PROVIDER_BASE_URL: str = "http://192.168.200.48:11434/v1"
    LLM_PROVIDER_API_KEY: Optional[str] = "ollama"
    DEFAULT_LLM_MODEL: str = "gpt-oss:20b"  # phi4-mini:3.8b"
    LLM_TIMEOUT: float = 300.0  # Extended to 5 minutes for LLM cold start (was 60.0)
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: Optional[int] = None

    # =============================================================================
    # Embedding Model Settings
    # =============================================================================
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_FALLBACK: str = "jinaai/jina-embeddings-v2-base-zh"
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_DEVICE: str = "cpu"  # "mps"  # or "cuda:0"
    EMBEDDING_NORMALIZE: bool = False

    # =============================================================================
    # Milvus Settings (Vector Database)
    # =============================================================================
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: str = "19530"
    MILVUS_USER: Optional[str] = None
    MILVUS_PASSWORD: Optional[str] = None
    MILVUS_COLLECTION_NAME: str = "document_embeddings"
    MILVUS_INDEX_TYPE: str = "IVF_FLAT"
    MILVUS_METRIC_TYPE: str = "L2"
    MILVUS_NLIST: int = 1024

    # =============================================================================
    # MongoDB Settings (Chat History)
    # =============================================================================
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "docai"
    MONGODB_CHAT_COLLECTION: str = "chat_sessions"
    MONGODB_MIN_POOL_SIZE: int = 10
    MONGODB_MAX_POOL_SIZE: int = 100

    # =============================================================================
    # Redis Settings (Cache)
    # =============================================================================
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_CACHE_TTL: int = 3600  # 1 hour
    REDIS_EMBEDDING_TTL: int = 86400  # 24 hours
    REDIS_QUERY_EXPANSION_TTL: int = 3600  # 1 hour
    REDIS_SEARCH_RESULTS_TTL: int = 1800  # 30 minutes

    # =============================================================================
    # SQLite Settings (File Metadata)
    # =============================================================================
    SQLITE_DB_PATH: str = "./data/docai.db"

    # =============================================================================
    # File Upload Settings
    # =============================================================================
    UPLOAD_DIR: str = "./uploadfiles"
    PDF_UPLOAD_DIR: str = "./uploadfiles/pdf"  # PDF-specific directory
    MAX_FILE_SIZE: int = 50_000_000  # 50MB
    ALLOWED_EXTENSIONS: List[str] = Field(
        default_factory=lambda: ["pdf", "docx", "pptx", "txt", "md"]
    )

    # =============================================================================
    # Text Chunking Settings
    # =============================================================================
    # Default chunking strategy
    # RecursiveCharacterTextSplitter is most effective for PDF documents
    CHUNKING_STRATEGY: str = (
        "page_based"  # "hierarchical" or "recursive" or "page_based"
    )
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    CHUNK_SEPARATORS: List[str] = Field(
        default_factory=lambda: ["\n\n", "\n", "。", "！", "？", " ", ""]
    )
    PAGE_BASED_CHUNK_SIZE: int = 2000
    PAGE_BASED_CHUNK_OVERLAP: int = 200
    # Hierarchical Indexing Settings (Multi-level chunking)
    HIERARCHICAL_CHUNK_SIZES: List[int] = Field(
        default_factory=lambda: [2000, 1000, 500]
    )  # Parent, Child, Grandchild
    HIERARCHICAL_OVERLAP: int = 100
    ENABLE_MULTIVECTOR_RETRIEVAL: bool = True  # Use MultiVectorRetriever

    # =============================================================================
    # Query Enhancement Settings (Strategy 2: Question Expansion)
    # =============================================================================
    ENABLE_QUERY_ENHANCEMENT: bool = True
    ENHANCEMENT_STRATEGY: str = "question_expansion"  # Strategy 2
    EXPANSION_COUNT: int = 3  # Number of sub-questions to generate per round
    EXPANSION_TEMPERATURE: float = 0.3  # Lower temp for analysis

    # =============================================================================
    # Iterative Query Expansion Settings (Advanced Multi-Round Expansion)
    # =============================================================================
    ENABLE_ITERATIVE_EXPANSION: bool = True  # Enable advanced multi-round expansion
    ITERATIVE_EXPANSION_ROUNDS: int = (
        1  # Number of expansion rounds (1-3) - default 1 for speed
    )
    EXPANSION_PRUNING_THRESHOLD: float = 0.6  # Min quality score to keep query (0-1)
    ENABLE_EXPANSION_SCORING: bool = (
        False  # Disable LLM scoring for speed (adds 30s+ per call)
    )
    EXPANSION_STRATEGY_MODE: str = (
        "single"  # "single" for speed, "iterative" for quality, "adaptive"
    )

    # =============================================================================
    # Retrieval Settings
    # =============================================================================
    TOP_K_RESULTS: int = 20  # Default number of chunks to retrieve
    MIN_SIMILARITY_SCORE: float = 0.0  # Minimum similarity threshold
    ENABLE_RERANKING: bool = False  # Future: Cross-encoder reranking

    # =============================================================================
    # Default User Settings (for development/testing)
    # =============================================================================
    DEFAULT_USER_ID: str = "5a19a0da-7485-4656-8641-41402fef4049"
    DEFAULT_USER_ENABLED: bool = True  # Set to False in production

    # =============================================================================
    # Security Settings
    # =============================================================================
    SECRET_KEY: str = "your-secret-key-change-in-production"
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8080"]
    )
    CORS_CREDENTIALS: bool = True
    CORS_METHODS: List[str] = Field(default_factory=lambda: ["*"])
    CORS_HEADERS: List[str] = Field(default_factory=lambda: ["*"])

    # =============================================================================
    # Logging Settings
    # =============================================================================
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" or "text"
    LOG_FILE: Optional[str] = "./logs/docai.log"

    # =============================================================================
    # Vector Store Backend Selection
    # =============================================================================
    VECTOR_STORE_BACKEND: str = "faiss"  # "milvus" or "faiss"
    VECTOR_STORE_PATH: str = "./data/vector_store"  # For FAISS fallback

    # =============================================================================
    # Computed Properties
    # =============================================================================
    @property
    def milvus_uri(self) -> str:
        """Construct Milvus connection URI"""
        return f"http://{self.MILVUS_HOST}:{self.MILVUS_PORT}"

    @property
    def mongodb_url(self) -> str:
        """Get MongoDB connection URL"""
        return self.MONGODB_URI

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL"""
        password_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{password_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def sqlite_path(self) -> Path:
        """Get SQLite database path as Path object"""
        return Path(self.SQLITE_DB_PATH)

    @property
    def upload_path(self) -> Path:
        """Get upload directory as Path object"""
        return Path(self.UPLOAD_DIR)

    def ensure_directories(self):
        """Create necessary directories if they don't exist"""
        self.upload_path.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        if self.LOG_FILE:
            Path(self.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

        if self.VECTOR_STORE_BACKEND == "faiss":
            Path(self.VECTOR_STORE_PATH).mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()

# Ensure required directories exist
settings.ensure_directories()
