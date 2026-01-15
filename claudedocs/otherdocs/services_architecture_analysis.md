# Services Architecture Analysis & Skill-Based System Design

**Date**: 2025-11-25
**Purpose**: Analyze existing Services architecture + Design new Skill-based retrieval system
**Status**: No existing skill components found - designing from scratch

---

## Executive Summary

### Current State
- **Existing System**: File-based RAG (per-document vector stores)
- **Architecture**: Clean 3-tier (Providers → Services → API)
- **Dependency Injection**: FastAPI Depends() pattern throughout
- **No Skill Components**: Zero existing skill-related code found

### Proposed Solution
- **New Subsystem**: `app/SkillServices/` (parallel to `app/Services/`)
- **Isolation Strategy**: Separate vector stores, separate metadata DB, shared providers
- **Migration Path**: Feature-flag controlled gradual rollout
- **Interface**: Abstract base class for polymorphism (file vs skill retrieval)

---

## Part 1: Existing Services Architecture Analysis

### 1.1 Service Dependency Graph

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer 3: API Endpoints                   │
│              app/api/v1/endpoints/*.py                      │
└───────────────────────────┬─────────────────────────────────┘
                            │ Depends()
┌───────────────────────────▼─────────────────────────────────┐
│                    Layer 2: Services                        │
│                   app/Services/*.py                         │
│                                                             │
│  ┌─────────────────┐  ┌────────────────────┐              │
│  │ RetrievalService│  │DocumentOverview    │              │
│  │                 │  │Service             │              │
│  │ • FAISS search  │  │                    │              │
│  │ • Context       │  │ • LLM summaries    │              │
│  │   assembly      │  │ • SQLite storage   │              │
│  └────────┬────────┘  └──────────┬─────────┘              │
│           │                       │                         │
│  ┌────────▼────────┐  ┌──────────▼────────┐               │
│  │QueryEnhancement │  │InputDataHandle    │               │
│  │Service          │  │Service            │               │
│  │                 │  │                   │               │
│  │ • Query         │  │ • PDF extraction  │               │
│  │   expansion     │  │ • Text chunking   │               │
│  │ • Intent detect │  │ • File validation │               │
│  └─────────────────┘  └───────────────────┘               │
└───────────────────────────┬─────────────────────────────────┘
                            │ Depends()
┌───────────────────────────▼─────────────────────────────────┐
│                    Layer 1: Providers                       │
│                  app/Providers/*/client.py                  │
│                                                             │
│  ┌────────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │ Embedding      │ │ VectorStore  │ │ LLMProvider      │ │
│  │ Provider       │ │ Provider     │ │ Client           │ │
│  │                │ │              │ │                  │ │
│  │ • SentenceTfmr │ │ • FAISS ops  │ │ • Chat complete │ │
│  └────────────────┘ └──────────────┘ └──────────────────┘ │
│                                                             │
│  ┌────────────────┐ ┌──────────────┐                      │
│  │ FileMetadata   │ │ CacheProvider│                      │
│  │ Provider       │ │              │                      │
│  │                │ │              │                      │
│  │ • SQLite CRUD  │ │ • Redis-like │                      │
│  └────────────────┘ └──────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Core Services Analysis

#### RetrievalService
```python
# Location: app/Services/retrieval_service.py

Dependencies:
  - EmbeddingProvider (for text → vectors)
  - VectorStoreProvider (for FAISS operations)

Key Methods:
  • add_document_chunks(file_id, chunks, metadata)
    → Create FAISS index per file

  • retrieve_context(query, file_ids, top_k, fair_distribution)
    → Vector similarity search across selected files
    → Fair distribution mode for multi-doc summaries

  • delete_document(file_id)
    → Remove FAISS index

File-based Paradigm:
  - One FAISS index per file_id
  - Metadata includes: file_id, chunk_index, filename
  - Store ID = file_id
```

#### DocumentOverviewService
```python
# Location: app/Services/document_overview_service.py

Dependencies:
  - LLMProviderClient (for overview generation)
  - FileMetadataProvider (for SQLite storage)

Key Methods:
  • generate_overview(file_id, chunks, filename)
    → LLM-based document summary (200-300 chars)

  • store_overview(file_metadata_provider, file_id, overview)
    → Save to document_overviews table

  • get_overview(file_metadata_provider, file_id)
    → Retrieve single overview

  • get_multiple_overviews(file_metadata_provider, file_ids)
    → Batch retrieval for multi-doc queries

SQLite Schema:
  CREATE TABLE document_overviews (
      file_id TEXT PRIMARY KEY,
      overview TEXT NOT NULL,
      created_at TIMESTAMP,
      updated_at TIMESTAMP,
      FOREIGN KEY (file_id) REFERENCES file_metadata(file_id)
  )
```

#### QueryEnhancementService / IterativeQueryExpansionService
```python
# Location: app/Services/query_enhancement_service.py
#           app/Services/iterative_query_expansion_service.py

Dependencies:
  - LLMProviderClient (for query expansion)
  - CacheProvider (optional, for caching expansions)
  - IntentDetectorFactory (for multi-file intent detection)

Key Methods:
  • expand_query(query, cache_provider)
    → LLM-based query expansion (3-5 sub-questions)

  • detect_summary_intent(query)
    → Keyword-based summary detection

  • expand_query_iterative(query, rounds, cache_provider)
    → Multi-round iterative expansion with quality scoring

Retrieval-Agnostic:
  ✓ These services work with ANY retrieval paradigm
  ✓ No file_id dependencies
  ✓ Can be reused directly for skill-based system
```

#### InputDataHandleService
```python
# Location: app/Services/input_data_handle_service.py

Dependencies:
  - ChunkingStrategyFactory (for text splitting)
  - FileMetadataProvider (for unique file_id generation)

Key Methods:
  • validate_file(file_content, filename)
    → Type/size validation

  • extract_text(file_content, filename)
    → PDF/DOCX/TXT extraction

  • chunk_text(text, metadata)
    → Strategy-based text chunking

  • generate_unique_file_id(file_content, filename, provider)
    → Collision-resistant ID: file_{timestamp}_{uuid8}_{hash8}

  • process_file(file_content, filename, provider)
    → Complete ingestion workflow

File-based Paradigm:
  - Generates file_ids
  - Stores file_metadata in SQLite
```

### 1.3 Key Architectural Patterns

**1. Dependency Injection (FastAPI Depends)**
```python
class RetrievalService:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
        vector_store_provider: VectorStoreProvider = Depends(get_vector_store_provider)
    ):
        self.embedding_provider = embedding_provider
        self.vector_store_provider = vector_store_provider
```

**2. Strategy Pattern (Chunking)**
```python
# Factory creates appropriate strategy
strategy = ChunkingStrategyFactory.create(
    "hierarchical",  # or "recursive", "page_based"
    chunk_sizes=[2000, 1000, 500],
    overlap=200
)

chunks = strategy.chunk(text, metadata)
```

**3. Factory Method (Intent Detection)**
```python
detector = IntentDetectorFactory.create_detector('regex')
result = detector.detect_multi_file_intent(query, file_count)
```

**4. Singleton (Provider Instances)**
```python
_embedding_provider_instance = None

def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider_instance
    if _embedding_provider_instance is None:
        _embedding_provider_instance = EmbeddingProvider()
    return _embedding_provider_instance
```

### 1.4 Provider Layer Details

```python
# All providers follow this pattern:

EmbeddingProvider (app/Providers/embedding_provider/client.py)
  ├── Purpose: Text → Vector embeddings
  ├── Implementation: SentenceTransformer
  ├── Methods: embed_text(), embed_batch(), get_underlying_model()
  └── Used by: RetrievalService

VectorStoreProvider (app/Providers/vector_store_provider/client.py)
  ├── Purpose: FAISS vector store operations
  ├── Storage: ./data/vectorstores/{file_id}/
  ├── Methods: create_store_from_texts(), similarity_search(), delete_store()
  └── Used by: RetrievalService

LLMProviderClient (app/Providers/llm_provider/client.py)
  ├── Purpose: OpenAI-compatible LLM inference
  ├── Methods: get_chat_completion(messages, temperature, max_tokens)
  └── Used by: DocumentOverviewService, QueryEnhancementService

FileMetadataProvider (app/Providers/file_metadata_provider/client.py)
  ├── Purpose: SQLite file metadata persistence
  ├── Database: ./data/file_metadata.db
  ├── Methods: create_file(), get_file(), list_files(), delete_file()
  └── Used by: InputDataHandleService, DocumentOverviewService

CacheProvider (app/Providers/cache_provider/client.py)
  ├── Purpose: Redis-like caching (query expansions)
  ├── Methods: get_query_expansion(), set_query_expansion()
  └── Used by: QueryEnhancementService (optional)
```

---

## Part 2: Skill-Based System Design (NEW)

### 2.1 System Requirements

**Functional Requirements**:
1. Store skill content (text, descriptions, examples)
2. Create skill-based vector embeddings
3. Retrieve relevant skills based on user queries
4. Support skill categories and hierarchies
5. Generate skill overviews/summaries
6. Enable skill-based RAG responses

**Non-Functional Requirements**:
1. **Isolation**: Zero impact on existing file-based system
2. **Performance**: Retrieval latency < 200ms (p95)
3. **Scalability**: Support up to 1000 skills
4. **Maintainability**: Clean interfaces, extensible architecture
5. **Testability**: >80% code coverage

### 2.2 Skill Data Model

```python
# Skill Metadata
Skill = {
    "skill_id": str,              # "skill_{timestamp}_{uuid8}"
    "skill_name": str,            # "Python Async Programming"
    "skill_description": str,     # "Understanding asyncio and coroutines"
    "skill_category": str,        # "Programming/Python"
    "skill_level": str,           # "beginner" | "intermediate" | "advanced"
    "tags": List[str],            # ["python", "async", "coroutines"]
    "related_skills": List[str],  # ["skill_001", "skill_002"]
    "content_chunks": List[str],  # Text chunks for embedding
    "total_chunks": int,          # Number of chunks
    "created_at": datetime,
    "updated_at": datetime,
    "metadata": Dict[str, Any]    # Extensible metadata
}

# Skill-Document Relationship (optional)
SkillDocumentMapping = {
    "skill_id": str,
    "file_id": str,               # Links skills to source documents
    "relevance_score": float,     # 0.0-1.0
    "created_at": datetime
}
```

### 2.3 Directory Structure (NEW)

```
app/
├── Services/                    # Existing file-based services (UNCHANGED)
│   ├── __init__.py
│   ├── retrieval_service.py
│   ├── document_overview_service.py
│   ├── query_enhancement_service.py   ← Reuse directly
│   ├── iterative_query_expansion_service.py   ← Reuse directly
│   ├── input_data_handle_service.py
│   ├── prompt_service.py
│   └── query_intent_detection/
│       ├── __init__.py
│       ├── base.py
│       ├── factory.py
│       └── regex_strategy.py
│
├── SkillServices/               # NEW: Skill-based services
│   ├── __init__.py
│   ├── skill_retrieval_service.py       # Core skill retrieval
│   ├── skill_overview_service.py        # Skill summaries
│   ├── skill_ingestion_service.py       # Skill content processing
│   ├── unified_retrieval_service.py     # Orchestrator (file + skill)
│   └── base_retrieval.py                # Abstract interface
│
├── Providers/                   # Shared infrastructure (MODIFIED)
│   ├── __init__.py
│   ├── embedding_provider/      ← Reuse (shared)
│   ├── vector_store_provider/   ← Modify for skill stores
│   ├── llm_provider/            ← Reuse (shared)
│   ├── file_metadata_provider/  ← Keep separate
│   ├── skill_metadata_provider/ # NEW: Skill metadata
│   │   ├── __init__.py
│   │   └── client.py
│   └── cache_provider/          ← Reuse (shared)
│
└── api/
    └── v1/
        ├── endpoints/
        │   ├── files.py         # Existing file endpoints
        │   └── skills.py        # NEW: Skill endpoints
        └── chat.py              # Modify for unified retrieval
```

### 2.4 Core Components Design

#### 2.4.1 Abstract Retrieval Interface

```python
# app/SkillServices/base_retrieval.py (NEW)
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class AbstractRetrievalService(ABC):
    """
    Abstract base class for retrieval services.

    Both file-based and skill-based retrieval implement this interface
    for polymorphism and consistent API surface.
    """

    @abstractmethod
    async def add_content(
        self,
        content_id: str,
        chunks: List[str],
        metadata: Optional[List[dict]] = None
    ) -> str:
        """
        Add content chunks to vector store.

        Args:
            content_id: Unique identifier (file_id or skill_id)
            chunks: List of text chunks
            metadata: Optional metadata for each chunk

        Returns:
            Store identifier
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
        Retrieve relevant context for a query.

        Args:
            query: User query
            content_ids: List of content IDs to search
            top_k: Number of results
            **kwargs: Additional retrieval parameters

        Returns:
            List of context dicts with 'content', 'metadata', 'score'
        """
        pass

    @abstractmethod
    async def delete_content(self, content_id: str):
        """Delete content from vector store."""
        pass

    @abstractmethod
    def get_retrieval_mode(self) -> str:
        """Return retrieval mode identifier ('file_based' or 'skill_based')."""
        pass


# Existing RetrievalService adapts to this interface
class RetrievalService(AbstractRetrievalService):
    """File-based retrieval (existing implementation)."""

    async def add_content(self, content_id, chunks, metadata=None):
        return await self.add_document_chunks(content_id, chunks, metadata)

    async def retrieve_context(self, query, content_ids, top_k=5, **kwargs):
        return await self.retrieve_context(
            query=query,
            file_ids=content_ids,
            top_k=top_k,
            **kwargs
        )

    async def delete_content(self, content_id):
        return await self.delete_document(content_id)

    def get_retrieval_mode(self) -> str:
        return "file_based"
```

#### 2.4.2 SkillMetadataProvider

```python
# app/Providers/skill_metadata_provider/client.py (NEW)
import aiosqlite
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillMetadataProvider:
    """
    SQLite provider for skill metadata persistence.

    Analogous to FileMetadataProvider but for skill-based system.
    Stores: skill metadata, skill overviews, skill-document mappings
    """

    def __init__(self, db_path: str = "./data/skill_metadata.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Skill Metadata Provider initialized: {db_path}")

    async def _get_connection(self):
        """Get database connection."""
        return await aiosqlite.connect(self.db_path)

    async def initialize_db(self):
        """Create tables if not exist."""
        conn = await self._get_connection()

        # Skill metadata table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_metadata (
                skill_id TEXT PRIMARY KEY,
                skill_name TEXT NOT NULL,
                skill_description TEXT,
                skill_category TEXT,
                skill_level TEXT,
                tags JSON,
                related_skills JSON,
                total_chunks INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSON
            )
        """)

        # Skill overviews table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_overviews (
                skill_id TEXT PRIMARY KEY,
                overview TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
            )
        """)

        # Skill-document mapping table (optional)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_document_mapping (
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                relevance_score REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
            )
        """)

        # Indexes for performance
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_category ON skill_metadata(skill_category)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_name ON skill_metadata(skill_name)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_level ON skill_metadata(skill_level)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_doc_mapping_skill ON skill_document_mapping(skill_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_doc_mapping_file ON skill_document_mapping(file_id)")

        await conn.commit()
        await conn.close()

        logger.info("Skill metadata database initialized")

    async def create_skill(
        self,
        skill_id: str,
        skill_name: str,
        skill_description: Optional[str] = None,
        skill_category: Optional[str] = None,
        skill_level: str = "intermediate",
        tags: Optional[List[str]] = None,
        related_skills: Optional[List[str]] = None,
        total_chunks: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Create skill metadata record."""
        conn = await self._get_connection()

        await conn.execute("""
            INSERT INTO skill_metadata
            (skill_id, skill_name, skill_description, skill_category, skill_level,
             tags, related_skills, total_chunks, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            skill_id,
            skill_name,
            skill_description,
            skill_category,
            skill_level,
            json.dumps(tags) if tags else None,
            json.dumps(related_skills) if related_skills else None,
            total_chunks,
            json.dumps(metadata) if metadata else None,
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        await conn.commit()
        await conn.close()

        logger.info(f"Created skill metadata: {skill_id} ({skill_name})")

    async def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve skill metadata."""
        conn = await self._get_connection()

        async with conn.execute(
            "SELECT * FROM skill_metadata WHERE skill_id = ?",
            (skill_id,)
        ) as cursor:
            row = await cursor.fetchone()

        await conn.close()

        if row:
            return {
                "skill_id": row[0],
                "skill_name": row[1],
                "skill_description": row[2],
                "skill_category": row[3],
                "skill_level": row[4],
                "tags": json.loads(row[5]) if row[5] else [],
                "related_skills": json.loads(row[6]) if row[6] else [],
                "total_chunks": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "metadata": json.loads(row[10]) if row[10] else None
            }

        return None

    async def list_skills(
        self,
        category: Optional[str] = None,
        level: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """List skills with optional filters."""
        conn = await self._get_connection()

        query = "SELECT * FROM skill_metadata WHERE 1=1"
        params = []

        if category:
            query += " AND skill_category = ?"
            params.append(category)

        if level:
            query += " AND skill_level = ?"
            params.append(level)

        async with conn.execute(query, tuple(params)) as cursor:
            rows = await cursor.fetchall()

        await conn.close()

        skills = []
        for row in rows:
            skill = {
                "skill_id": row[0],
                "skill_name": row[1],
                "skill_description": row[2],
                "skill_category": row[3],
                "skill_level": row[4],
                "tags": json.loads(row[5]) if row[5] else [],
                "related_skills": json.loads(row[6]) if row[6] else [],
                "total_chunks": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "metadata": json.loads(row[10]) if row[10] else None
            }

            # Filter by tags if specified
            if tags and not any(tag in skill["tags"] for tag in tags):
                continue

            skills.append(skill)

        return skills

    async def delete_skill(self, skill_id: str):
        """Delete skill metadata and related records (cascade)."""
        conn = await self._get_connection()

        await conn.execute("DELETE FROM skill_metadata WHERE skill_id = ?", (skill_id,))

        await conn.commit()
        await conn.close()

        logger.info(f"Deleted skill metadata: {skill_id}")

    async def link_skill_to_document(
        self,
        skill_id: str,
        file_id: str,
        relevance_score: float = 0.0
    ):
        """Create skill-document mapping."""
        conn = await self._get_connection()

        await conn.execute("""
            INSERT INTO skill_document_mapping
            (skill_id, file_id, relevance_score, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            skill_id,
            file_id,
            relevance_score,
            datetime.now(timezone.utc).isoformat()
        ))

        await conn.commit()
        await conn.close()

        logger.info(f"Linked skill {skill_id} to document {file_id}")

    async def get_documents_for_skill(self, skill_id: str) -> List[Dict[str, Any]]:
        """Get all documents linked to a skill."""
        conn = await self._get_connection()

        async with conn.execute("""
            SELECT file_id, relevance_score, created_at
            FROM skill_document_mapping
            WHERE skill_id = ?
            ORDER BY relevance_score DESC
        """, (skill_id,)) as cursor:
            rows = await cursor.fetchall()

        await conn.close()

        return [
            {
                "file_id": row[0],
                "relevance_score": row[1],
                "created_at": row[2]
            }
            for row in rows
        ]


# Singleton instance
_skill_metadata_provider_instance: Optional[SkillMetadataProvider] = None


def get_skill_metadata_provider() -> SkillMetadataProvider:
    """FastAPI dependency for Skill Metadata Provider."""
    global _skill_metadata_provider_instance

    if _skill_metadata_provider_instance is None:
        _skill_metadata_provider_instance = SkillMetadataProvider()

    return _skill_metadata_provider_instance
```

#### 2.4.3 SkillRetrievalService

```python
# app/SkillServices/skill_retrieval_service.py (NEW)
import logging
from typing import List, Dict, Optional, Any
from fastapi import Depends

from app.SkillServices.base_retrieval import AbstractRetrievalService
from app.Providers.embedding_provider.client import EmbeddingProvider, get_embedding_provider
from app.Providers.vector_store_provider.client import VectorStoreProvider, get_vector_store_provider

logger = logging.getLogger(__name__)


class SkillRetrievalService(AbstractRetrievalService):
    """
    Skill-based retrieval service.

    Implements AbstractRetrievalService interface for skill-based RAG.
    Operates on skill_ids instead of file_ids.
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
        metadata: Optional[List[dict]] = None
    ) -> str:
        """
        Add skill chunks to vector store.

        Args:
            content_id: skill_id
            chunks: List of text chunks
            metadata: Optional metadata for each chunk

        Returns:
            Store identifier (skill_id)
        """
        try:
            embeddings = self.embedding_provider.get_underlying_model()

            # Enhance metadata with skill_id
            if metadata is None:
                metadata = [{"skill_id": content_id, "chunk_index": i} for i in range(len(chunks))]
            else:
                for i, meta in enumerate(metadata):
                    meta["skill_id"] = content_id
                    if "chunk_index" not in meta:
                        meta["chunk_index"] = i

            # Create vector store (skill stores isolated in ./data/vectorstores/skills/)
            store_id = self.vector_store_provider.create_store_from_texts(
                texts=chunks,
                embeddings=embeddings,
                metadatas=metadata,
                file_id=content_id,  # Use skill_id as store identifier
                store_type="skill"   # NEW parameter for isolation
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
        """
        Retrieve relevant context from skills.

        Args:
            query: User query text
            content_ids: List of skill IDs to search
            top_k: Number of top results
            include_scores: Whether to include similarity scores

        Returns:
            List of context dicts with 'content', 'metadata', 'score'
        """
        try:
            all_results = []

            logger.info(f"Skill-based retrieval: query='{query[:50]}...', skill_ids={content_ids}")

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
        """Delete skill's vector store."""
        try:
            self.vector_store_provider.delete_store(content_id)
            logger.info(f"Deleted skill vector store: {content_id}")
        except Exception as e:
            logger.error(f"Error deleting skill '{content_id}': {str(e)}")
            raise

    def get_retrieval_mode(self) -> str:
        return "skill_based"


# Dependency injection helper
def get_skill_retrieval_service(
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store_provider: VectorStoreProvider = Depends(get_vector_store_provider)
) -> SkillRetrievalService:
    """FastAPI dependency for Skill Retrieval Service."""
    return SkillRetrievalService(
        embedding_provider=embedding_provider,
        vector_store_provider=vector_store_provider
    )
```

#### 2.4.4 SkillIngestionService

```python
# app/SkillServices/skill_ingestion_service.py (NEW)
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import hashlib
import time
import uuid

logger = logging.getLogger(__name__)


class SkillIngestionService:
    """
    Skill content ingestion and processing.

    Handles:
    - Skill content validation
    - Skill ID generation
    - Text chunking for skills
    - Metadata enrichment
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        Initialize Skill Ingestion Service.

        Args:
            chunk_size: Default chunk size for skill content
            chunk_overlap: Chunk overlap size
        """
        from langchain.text_splitter import RecursiveCharacterTextSplitter

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len
        )

        logger.info(f"Skill Ingestion Service initialized (chunk_size={chunk_size})")

    def generate_skill_id(
        self,
        skill_name: str,
        content: str
    ) -> str:
        """
        Generate unique skill ID.

        Format: skill_{timestamp}_{uuid8}_{hash8}

        Args:
            skill_name: Skill name
            content: Skill content for hashing

        Returns:
            Unique skill ID
        """
        # Component 1: Timestamp (sortable)
        timestamp = int(time.time())

        # Component 2: Random UUID (collision resistance)
        uuid_part = str(uuid.uuid4()).replace('-', '')[:8]

        # Component 3: Content hash (duplicate detection)
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]

        skill_id = f"skill_{timestamp}_{uuid_part}_{content_hash}"

        return skill_id

    async def generate_unique_skill_id(
        self,
        skill_name: str,
        content: str,
        skill_metadata_provider,
        max_retries: int = 3
    ) -> str:
        """
        Generate unique skill ID with database collision detection.

        Args:
            skill_name: Skill name
            content: Skill content
            skill_metadata_provider: SkillMetadataProvider instance
            max_retries: Maximum retry attempts

        Returns:
            Unique skill ID
        """
        for attempt in range(max_retries):
            skill_id = self.generate_skill_id(skill_name, content)

            # Check if skill_id already exists
            try:
                existing_skill = await skill_metadata_provider.get_skill(skill_id)

                if existing_skill is None:
                    return skill_id
                else:
                    logger.warning(
                        f"skill_id collision detected: {skill_id} "
                        f"(attempt {attempt + 1}/{max_retries}). Retrying..."
                    )
                    continue

            except Exception as e:
                logger.error(f"Error checking skill_id uniqueness: {str(e)}")
                return skill_id

        raise ValueError(
            f"Failed to generate unique skill_id after {max_retries} attempts"
        )

    def chunk_skill_content(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Chunk skill content into smaller pieces.

        Args:
            content: Skill text content
            metadata: Optional base metadata

        Returns:
            List of chunk dicts with 'content' and 'metadata'
        """
        try:
            # Split text
            text_chunks = self.text_splitter.split_text(content)

            # Enrich with metadata
            chunks = []
            for i, chunk_text in enumerate(text_chunks):
                chunk_meta = metadata.copy() if metadata else {}
                chunk_meta["chunk_index"] = i
                chunk_meta["total_chunks"] = len(text_chunks)

                chunks.append({
                    "content": chunk_text,
                    "metadata": chunk_meta
                })

            logger.info(f"Chunked skill content into {len(chunks)} chunks")
            return chunks

        except Exception as e:
            logger.error(f"Skill content chunking failed: {str(e)}")
            raise ValueError(f"Failed to chunk skill content: {str(e)}")

    async def process_skill(
        self,
        skill_name: str,
        skill_content: str,
        skill_description: Optional[str] = None,
        skill_category: Optional[str] = None,
        skill_level: str = "intermediate",
        tags: Optional[List[str]] = None,
        skill_metadata_provider = None
    ) -> Dict[str, Any]:
        """
        Complete skill ingestion workflow.

        Workflow:
        1. Generate unique skill_id
        2. Chunk skill content
        3. Enrich chunk metadata

        Args:
            skill_name: Skill name
            skill_content: Full skill text content
            skill_description: Optional description
            skill_category: Optional category
            skill_level: Skill difficulty level
            tags: Optional tags
            skill_metadata_provider: Optional provider for unique ID generation

        Returns:
            Dict with skill_id, chunks, metadata
        """
        # Step 1: Generate unique skill ID
        if skill_metadata_provider is not None:
            skill_id = await self.generate_unique_skill_id(
                skill_name, skill_content, skill_metadata_provider
            )
        else:
            skill_id = self.generate_skill_id(skill_name, skill_content)

        # Step 2: Chunk skill content
        base_metadata = {
            "skill_id": skill_id,
            "skill_name": skill_name,
            "skill_category": skill_category,
            "skill_level": skill_level
        }

        chunks = self.chunk_skill_content(skill_content, metadata=base_metadata)

        # Step 3: Return result
        result = {
            "skill_id": skill_id,
            "skill_name": skill_name,
            "skill_description": skill_description,
            "skill_category": skill_category,
            "skill_level": skill_level,
            "tags": tags or [],
            "chunks": chunks,
            "chunk_count": len(chunks),
            "content_length": len(skill_content)
        }

        logger.info(
            f"Processed skill '{skill_name}': "
            f"skill_id={skill_id}, chunks={len(chunks)}"
        )

        return result


# Singleton instance
_skill_ingestion_service_instance: Optional[SkillIngestionService] = None


def get_skill_ingestion_service() -> SkillIngestionService:
    """FastAPI dependency for Skill Ingestion Service."""
    global _skill_ingestion_service_instance

    if _skill_ingestion_service_instance is None:
        _skill_ingestion_service_instance = SkillIngestionService()

    return _skill_ingestion_service_instance
```

#### 2.4.5 UnifiedRetrievalService (Orchestrator)

```python
# app/SkillServices/unified_retrieval_service.py (NEW)
import logging
from typing import List, Dict, Any, Optional
from enum import Enum
from fastapi import Depends

from app.Services.retrieval_service import RetrievalService, get_retrieval_service
from app.SkillServices.skill_retrieval_service import (
    SkillRetrievalService,
    get_skill_retrieval_service
)

logger = logging.getLogger(__name__)


class RetrievalMode(Enum):
    """Retrieval mode enumeration."""
    FILE_BASED = "file_based"
    SKILL_BASED = "skill_based"
    HYBRID = "hybrid"  # Future: combine both


class UnifiedRetrievalService:
    """
    Orchestrator service that routes retrieval requests to appropriate backend.

    Supports:
    - File-based retrieval (existing system)
    - Skill-based retrieval (new system)
    - Hybrid mode (future: combine both)

    Usage:
        # In API endpoint
        unified_service = get_unified_retrieval_service()

        # File-based retrieval
        results = await unified_service.retrieve_context(
            query="What is RAG?",
            content_ids=["file_001", "file_002"],
            mode=RetrievalMode.FILE_BASED
        )

        # Skill-based retrieval
        results = await unified_service.retrieve_context(
            query="Python async programming",
            content_ids=["skill_001", "skill_002"],
            mode=RetrievalMode.SKILL_BASED
        )
    """

    def __init__(
        self,
        file_retrieval_service: RetrievalService = Depends(get_retrieval_service),
        skill_retrieval_service: SkillRetrievalService = Depends(get_skill_retrieval_service),
        default_mode: RetrievalMode = RetrievalMode.FILE_BASED
    ):
        self.file_service = file_retrieval_service
        self.skill_service = skill_retrieval_service
        self.default_mode = default_mode

        logger.info(f"Unified Retrieval Service initialized (default: {default_mode.value})")

    async def retrieve_context(
        self,
        query: str,
        content_ids: List[str],
        mode: Optional[RetrievalMode] = None,
        top_k: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Retrieve context using specified mode.

        Args:
            query: User query
            content_ids: List of file_ids or skill_ids
            mode: Retrieval mode (file/skill/hybrid)
            top_k: Number of results
            **kwargs: Additional parameters for specific retrieval services

        Returns:
            List of context dicts with 'content', 'metadata', 'score'
        """
        mode = mode or self.default_mode

        if mode == RetrievalMode.FILE_BASED:
            logger.info(f"[UNIFIED] Using file-based retrieval for {len(content_ids)} files")
            return await self.file_service.retrieve_context(
                query=query,
                file_ids=content_ids,
                top_k=top_k,
                **kwargs
            )

        elif mode == RetrievalMode.SKILL_BASED:
            logger.info(f"[UNIFIED] Using skill-based retrieval for {len(content_ids)} skills")
            return await self.skill_service.retrieve_context(
                query=query,
                content_ids=content_ids,
                top_k=top_k,
                **kwargs
            )

        elif mode == RetrievalMode.HYBRID:
            logger.info(f"[UNIFIED] Using hybrid retrieval (future implementation)")
            # Future: Combine file-based and skill-based results
            # Could use:
            # - Score fusion (e.g., weighted average)
            # - Re-ranking (e.g., cross-encoder)
            # - Interleaving strategies
            raise NotImplementedError("Hybrid mode not yet implemented")

        else:
            raise ValueError(f"Unknown retrieval mode: {mode}")

    async def add_content(
        self,
        content_id: str,
        chunks: List[str],
        mode: RetrievalMode,
        metadata: Optional[List[dict]] = None
    ) -> str:
        """
        Add content to appropriate vector store.

        Args:
            content_id: file_id or skill_id
            chunks: Text chunks
            mode: Retrieval mode
            metadata: Optional metadata

        Returns:
            Store identifier
        """
        if mode == RetrievalMode.FILE_BASED:
            return await self.file_service.add_document_chunks(
                file_id=content_id,
                chunks=chunks,
                metadata=metadata
            )
        elif mode == RetrievalMode.SKILL_BASED:
            return await self.skill_service.add_content(
                content_id=content_id,
                chunks=chunks,
                metadata=metadata
            )
        else:
            raise ValueError(f"Unsupported mode for add_content: {mode}")

    async def delete_content(
        self,
        content_id: str,
        mode: RetrievalMode
    ):
        """Delete content from appropriate vector store."""
        if mode == RetrievalMode.FILE_BASED:
            await self.file_service.delete_document(content_id)
        elif mode == RetrievalMode.SKILL_BASED:
            await self.skill_service.delete_content(content_id)
        else:
            raise ValueError(f"Unsupported mode for delete_content: {mode}")


# Dependency injection
def get_unified_retrieval_service(
    file_service: RetrievalService = Depends(get_retrieval_service),
    skill_service: SkillRetrievalService = Depends(get_skill_retrieval_service)
) -> UnifiedRetrievalService:
    """FastAPI dependency for Unified Retrieval Service."""
    from app.core.config import settings

    # Determine default mode from settings
    default_mode = RetrievalMode.FILE_BASED  # Safe default
    if hasattr(settings, 'DEFAULT_RETRIEVAL_MODE'):
        default_mode = RetrievalMode(settings.DEFAULT_RETRIEVAL_MODE)

    return UnifiedRetrievalService(
        file_retrieval_service=file_service,
        skill_retrieval_service=skill_service,
        default_mode=default_mode
    )
```

#### 2.4.6 API Endpoints

```python
# app/api/v1/endpoints/skills.py (NEW)
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel, Field

from app.SkillServices.skill_retrieval_service import (
    SkillRetrievalService,
    get_skill_retrieval_service
)
from app.SkillServices.skill_ingestion_service import (
    SkillIngestionService,
    get_skill_ingestion_service
)
from app.Providers.skill_metadata_provider.client import (
    SkillMetadataProvider,
    get_skill_metadata_provider
)

router = APIRouter(prefix="/skills", tags=["skills"])


# =====================================================================
# Request/Response Models
# =====================================================================

class SkillUploadRequest(BaseModel):
    """Request model for skill upload."""
    skill_name: str = Field(..., description="Skill name")
    skill_content: str = Field(..., description="Full skill text content")
    skill_description: Optional[str] = Field(None, description="Optional description")
    skill_category: Optional[str] = Field(None, description="Skill category (e.g., 'Programming/Python')")
    skill_level: str = Field("intermediate", description="Skill level: beginner|intermediate|advanced")
    tags: Optional[List[str]] = Field(None, description="Optional tags")


class SkillQueryRequest(BaseModel):
    """Request model for skill query."""
    query: str = Field(..., description="User query")
    skill_ids: List[str] = Field(..., description="List of skill IDs to search")
    top_k: int = Field(5, ge=1, le=20, description="Number of results (1-20)")


class SkillListResponse(BaseModel):
    """Response model for skill listing."""
    skill_id: str
    skill_name: str
    skill_description: Optional[str]
    skill_category: Optional[str]
    skill_level: str
    tags: List[str]
    total_chunks: int
    created_at: str


# =====================================================================
# Endpoints
# =====================================================================

@router.post("/upload")
async def upload_skill(
    request: SkillUploadRequest,
    skill_ingestion: SkillIngestionService = Depends(get_skill_ingestion_service),
    skill_retrieval: SkillRetrievalService = Depends(get_skill_retrieval_service),
    skill_metadata: SkillMetadataProvider = Depends(get_skill_metadata_provider)
):
    """
    Upload skill content and create vector embeddings.

    Workflow:
    1. Process skill content (chunk text)
    2. Create skill metadata record
    3. Add skill chunks to vector store

    Returns:
        - skill_id: Generated skill ID
        - chunk_count: Number of chunks created
        - store_id: Vector store identifier
    """
    try:
        # Step 1: Process skill content
        result = await skill_ingestion.process_skill(
            skill_name=request.skill_name,
            skill_content=request.skill_content,
            skill_description=request.skill_description,
            skill_category=request.skill_category,
            skill_level=request.skill_level,
            tags=request.tags,
            skill_metadata_provider=skill_metadata
        )

        skill_id = result["skill_id"]
        chunks = result["chunks"]

        # Step 2: Create skill metadata
        await skill_metadata.create_skill(
            skill_id=skill_id,
            skill_name=request.skill_name,
            skill_description=request.skill_description,
            skill_category=request.skill_category,
            skill_level=request.skill_level,
            tags=request.tags,
            total_chunks=len(chunks)
        )

        # Step 3: Add chunks to vector store
        chunk_texts = [chunk["content"] for chunk in chunks]
        chunk_metadata = [chunk["metadata"] for chunk in chunks]

        store_id = await skill_retrieval.add_content(
            content_id=skill_id,
            chunks=chunk_texts,
            metadata=chunk_metadata
        )

        return {
            "status": "success",
            "skill_id": skill_id,
            "skill_name": request.skill_name,
            "chunk_count": len(chunks),
            "store_id": store_id
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Skill upload failed: {str(e)}"
        )


@router.post("/query")
async def query_skills(
    request: SkillQueryRequest,
    skill_retrieval: SkillRetrievalService = Depends(get_skill_retrieval_service)
):
    """
    Query skills and retrieve relevant context.

    Args:
        query: User query
        skill_ids: List of skill IDs to search
        top_k: Number of results to return

    Returns:
        - query: Original query
        - results: List of context dicts
        - retrieval_mode: 'skill_based'
    """
    try:
        context = await skill_retrieval.retrieve_context(
            query=request.query,
            content_ids=request.skill_ids,
            top_k=request.top_k,
            include_scores=True
        )

        return {
            "status": "success",
            "query": request.query,
            "retrieval_mode": "skill_based",
            "results": context,
            "result_count": len(context)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Skill query failed: {str(e)}"
        )


@router.get("/list")
async def list_skills(
    category: Optional[str] = None,
    level: Optional[str] = None,
    tags: Optional[str] = None,  # Comma-separated tags
    skill_metadata: SkillMetadataProvider = Depends(get_skill_metadata_provider)
):
    """
    List all skills with optional filters.

    Query Parameters:
        - category: Filter by skill category
        - level: Filter by skill level (beginner|intermediate|advanced)
        - tags: Filter by tags (comma-separated)

    Returns:
        - skills: List of skill metadata dicts
        - total: Total count
    """
    try:
        tag_list = tags.split(",") if tags else None

        skills = await skill_metadata.list_skills(
            category=category,
            level=level,
            tags=tag_list
        )

        return {
            "status": "success",
            "skills": skills,
            "total": len(skills)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list skills: {str(e)}"
        )


@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    skill_metadata: SkillMetadataProvider = Depends(get_skill_metadata_provider)
):
    """Get detailed skill metadata by ID."""
    try:
        skill = await skill_metadata.get_skill(skill_id)

        if skill is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill not found: {skill_id}"
            )

        return {
            "status": "success",
            "skill": skill
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get skill: {str(e)}"
        )


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: str,
    skill_retrieval: SkillRetrievalService = Depends(get_skill_retrieval_service),
    skill_metadata: SkillMetadataProvider = Depends(get_skill_metadata_provider)
):
    """
    Delete a skill and its vector store.

    Workflow:
    1. Delete skill metadata (cascades to overviews and mappings)
    2. Delete vector store
    """
    try:
        # Check if skill exists
        skill = await skill_metadata.get_skill(skill_id)
        if skill is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill not found: {skill_id}"
            )

        # Delete vector store
        await skill_retrieval.delete_content(skill_id)

        # Delete metadata (cascades)
        await skill_metadata.delete_skill(skill_id)

        return {
            "status": "success",
            "message": f"Skill '{skill_id}' deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Skill deletion failed: {str(e)}"
        )
```

### 2.5 VectorStoreProvider Modifications

```python
# app/Providers/vector_store_provider/client.py (MODIFY)

# ADD to existing VectorStoreProvider class:

class VectorStoreProvider:
    def __init__(self, store_path: str = "./data/vectorstores"):
        self.store_path = Path(store_path)

        # NEW: Separate directories for file vs skill stores
        self.file_store_path = self.store_path / "files"
        self.skill_store_path = self.store_path / "skills"

        self.file_store_path.mkdir(parents=True, exist_ok=True)
        self.skill_store_path.mkdir(parents=True, exist_ok=True)

        self.stores = {}
        logger.info(f"Vector Store Provider initialized: {store_path}")

    def create_store_from_texts(
        self,
        texts: List[str],
        embeddings,
        metadatas: List[dict],
        file_id: str,
        store_type: str = "file"  # NEW: "file" or "skill"
    ) -> str:
        """
        Create FAISS store with type isolation.

        Args:
            texts: Text chunks
            embeddings: Embedding model
            metadatas: Chunk metadata
            file_id: Store identifier (file_id or skill_id)
            store_type: "file" or "skill" for isolation

        Returns:
            Store identifier
        """
        try:
            # Determine store directory based on type
            if store_type == "file":
                store_dir = self.file_store_path / file_id
            elif store_type == "skill":
                store_dir = self.skill_store_path / file_id
            else:
                raise ValueError(f"Unknown store_type: {store_type}")

            store_dir.mkdir(parents=True, exist_ok=True)

            # Create FAISS store
            vectorstore = FAISS.from_texts(
                texts=texts,
                embedding=embeddings,
                metadatas=metadatas
            )

            # Save to disk
            vectorstore.save_local(str(store_dir))

            # Cache in memory
            self.stores[file_id] = vectorstore

            logger.info(f"Created {store_type} store: {file_id} with {len(texts)} texts")
            return file_id

        except Exception as e:
            logger.error(f"Error creating store: {str(e)}")
            raise
```

### 2.6 Configuration Updates

```python
# app/core/config.py (ADD)

class Settings(BaseSettings):
    # ... existing settings ...

    # =====================================================================
    # Feature Flags for Skill-Based Retrieval
    # =====================================================================
    ENABLE_SKILL_RETRIEVAL: bool = Field(
        default=False,
        description="Master switch for skill-based retrieval system"
    )

    SKILL_RETRIEVAL_BETA_USERS: List[str] = Field(
        default=[],
        description="User IDs for beta testing skill retrieval"
    )

    DEFAULT_RETRIEVAL_MODE: str = Field(
        default="file_based",
        description="Default retrieval mode: 'file_based' or 'skill_based'"
    )

    # Skill-specific settings
    SKILL_CHUNK_SIZE: int = Field(default=1000, description="Skill content chunk size")
    SKILL_CHUNK_OVERLAP: int = Field(default=200, description="Skill chunk overlap")

    # Database paths
    SKILL_METADATA_DB_PATH: str = Field(
        default="./data/skill_metadata.db",
        description="SQLite database path for skill metadata"
    )

    # Vector store paths
    SKILL_VECTORSTORE_PATH: str = Field(
        default="./data/vectorstores/skills",
        description="FAISS vector store path for skills"
    )
```

---

## Part 3: Integration Strategy

### 3.1 Migration Phases

```
Phase 1: Development & Testing (Week 1-2)
├── Create app/SkillServices/ directory structure
├── Implement SkillMetadataProvider
├── Implement SkillRetrievalService
├── Implement SkillIngestionService
├── Implement UnifiedRetrievalService
├── Add /api/v1/skills/ endpoints
├── Write unit tests (target: >80% coverage)
├── Write integration tests
└── Feature flag: ENABLE_SKILL_RETRIEVAL = False (disabled)

Phase 2: Alpha Testing (Week 3)
├── Deploy to staging environment
├── Set ENABLE_SKILL_RETRIEVAL = True
├── Set DEFAULT_RETRIEVAL_MODE = "file_based" (existing system)
├── Manual testing of skill upload/query/delete
├── Performance benchmarking
├── Bug fixes and refinements
└── Documentation updates

Phase 3: Beta Testing (Week 4)
├── Deploy to production with feature flag
├── Enable for beta users: SKILL_RETRIEVAL_BETA_USERS = ["user_1", "user_2"]
├── Monitor metrics: latency, error rates, user feedback
├── A/B comparison: file-based vs skill-based
├── Gradual expansion: 5% → 10% → 25% users
└── Collect feedback and iterate

Phase 4: Gradual Rollout (Week 5-6)
├── Increase beta user percentage: 25% → 50% → 75%
├── Monitor system health at each stage
├── Rollback threshold: error rate > 1% or latency > 2x baseline
├── Performance optimization based on metrics
└── Prepare for full rollout

Phase 5: Full Deployment (Week 7)
├── Set DEFAULT_RETRIEVAL_MODE = "skill_based" for all users
├── Keep file-based system active for fallback
├── Monitor for 2 weeks with full traffic
├── Document lessons learned
└── Celebrate! 🎉

Phase 6: Optional Deprecation (Month 2+)
├── Announce deprecation timeline for file-based endpoints
├── Migrate remaining file-based users
├── Optionally remove file-based code
└── Maintain both systems or fully transition
```

### 3.2 Feature Flag Usage

```python
# Example: API endpoint with feature flag

from app.core.config import settings

@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    unified_service: UnifiedRetrievalService = Depends(get_unified_retrieval_service)
):
    """Chat endpoint with feature flag-controlled retrieval."""

    # Determine retrieval mode based on feature flag and user
    if settings.ENABLE_SKILL_RETRIEVAL:
        # Check if user is beta tester
        if request.user_id in settings.SKILL_RETRIEVAL_BETA_USERS:
            mode = RetrievalMode.SKILL_BASED
        else:
            mode = RetrievalMode(settings.DEFAULT_RETRIEVAL_MODE)
    else:
        # Feature disabled, use file-based
        mode = RetrievalMode.FILE_BASED

    # Retrieve context
    context = await unified_service.retrieve_context(
        query=request.query,
        content_ids=request.content_ids,
        mode=mode,
        top_k=5
    )

    return {
        "retrieval_mode": mode.value,
        "results": context
    }
```

### 3.3 Rollback Procedure

```bash
# Emergency Rollback (< 5 minutes)

# Step 1: Set feature flag in production config
export ENABLE_SKILL_RETRIEVAL=false

# Step 2: Restart application (or hot reload)
systemctl restart docai-app

# Step 3: Verify rollback
curl http://localhost:8000/api/v1/health
# Should show retrieval_mode: file_based

# Step 4: Monitor logs
tail -f logs/app.log | grep "retrieval_mode"

# Result:
# - All requests now use file-based retrieval
# - Skill-based code paths dormant
# - Zero data loss (skill metadata remains in DB)
# - Can re-enable for investigation
```

### 3.4 Testing Strategy

```python
# Unit Tests

# tests/test_skill_retrieval_service.py
@pytest.mark.asyncio
async def test_add_skill_chunks():
    service = SkillRetrievalService(embedding_provider, vector_store_provider)
    store_id = await service.add_content("skill_001", ["chunk1", "chunk2"])
    assert store_id == "skill_001"


# Integration Tests

# tests/test_unified_retrieval.py
def test_mode_switching():
    response_file = client.post("/api/v1/chat", json={
        "query": "test",
        "content_ids": ["file_001"],
        "retrieval_mode": "file_based"
    })
    assert response_file.json()["retrieval_mode"] == "file_based"

    response_skill = client.post("/api/v1/chat", json={
        "query": "test",
        "content_ids": ["skill_001"],
        "retrieval_mode": "skill_based"
    })
    assert response_skill.json()["retrieval_mode"] == "skill_based"


# Isolation Tests

@pytest.mark.asyncio
async def test_skill_file_isolation():
    # Add skill chunks
    await skill_service.add_content("skill_test", ["skill content"])

    # Add file chunks
    await file_service.add_document_chunks("file_test", ["file content"])

    # Verify skill retrieval doesn't return file content
    skill_results = await skill_service.retrieve_context("content", ["skill_test"])
    assert all("skill" in r['content'].lower() for r in skill_results)
```

---

## Part 4: Monitoring & Observability

### 4.1 Metrics to Track

```python
# Prometheus metrics

retrieval_mode_requests = Counter(
    'retrieval_mode_requests',
    'Requests per retrieval mode',
    ['mode']  # 'file_based' or 'skill_based'
)

retrieval_latency = Histogram(
    'retrieval_latency_seconds',
    'Retrieval latency',
    ['mode']
)

retrieval_errors = Counter(
    'retrieval_errors_total',
    'Retrieval errors',
    ['mode', 'error_type']
)

skill_upload_count = Counter(
    'skill_upload_total',
    'Total skills uploaded'
)
```

### 4.2 Logging Strategy

```python
# Structured logging

logger.info(
    "Skill retrieval completed",
    extra={
        "retrieval_mode": "skill_based",
        "query": query[:100],
        "skill_ids": skill_ids,
        "results_count": len(results),
        "latency_ms": latency * 1000
    }
)
```

---

## Part 5: Summary

### Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Service Isolation** | Separate `app/SkillServices/` | Clean separation, parallel development, easy rollback |
| **Shared Providers** | Reuse existing Providers | DRY principle, consistent infrastructure |
| **Interface Abstraction** | `AbstractRetrievalService` | Polymorphism, API compatibility |
| **Orchestrator** | `UnifiedRetrievalService` | Single API surface, mode switching |
| **Feature Flags** | `ENABLE_SKILL_RETRIEVAL` | Zero downtime, gradual rollout |
| **Database Isolation** | Separate `skill_metadata.db` | Zero risk to existing data |
| **Vector Store Isolation** | `./data/vectorstores/skills/` | Physical separation, independent cleanup |

### Services to Reuse

**High Priority** (Must reuse):
1. **EmbeddingProvider** → Shared embedding generation
2. **VectorStoreProvider** → FAISS abstraction (modify for isolation)
3. **LLMProviderClient** → Shared LLM inference
4. **QueryEnhancementService** → Already paradigm-agnostic

**Medium Priority** (Adapt patterns):
5. **DocumentOverviewService** → Pattern for SkillOverviewService
6. **PromptService** → Skill-specific prompt templates
7. **FileMetadataProvider** → Pattern for SkillMetadataProvider

### File Path References

**New Files**:
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/SkillServices/__init__.py`
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/SkillServices/base_retrieval.py`
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/SkillServices/skill_retrieval_service.py`
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/SkillServices/skill_ingestion_service.py`
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/SkillServices/unified_retrieval_service.py`
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/Providers/skill_metadata_provider/client.py`
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/Providers/skill_metadata_provider/__init__.py`
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/api/v1/endpoints/skills.py`

**Existing Files** (Unchanged):
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/Services/retrieval_service.py`
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/Services/query_enhancement_service.py`
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/Providers/embedding_provider/client.py`
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/Providers/llm_provider/client.py`

**Existing Files** (Modified):
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/Providers/vector_store_provider/client.py`
- `/home/mapleleaf/LCJRepos/gitprjs/DocAI/app/core/config.py`

---

**End of Analysis Report**

Generated: 2025-11-25
Author: Claude (Backend Architect)
Project: DocAI - Skill-Based Retrieval System Design
