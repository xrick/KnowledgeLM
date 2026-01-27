# app/Providers/skill_metadata_provider/client.py
"""
SQLite Knowledge Metadata Provider

Lightweight relational database for knowledge tracking, knowledge-document mappings, and knowledge overviews.
Implements async operations using aiosqlite.

This provider operates independently from FileMetadataProvider,
using a separate database file for complete isolation.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class SkillMetadataProvider:
    """
    SQLite Knowledge Metadata Provider

    Tables:
    1. knowledge_metadata: Knowledge-level information
       - doc_id (PK), knowledge_name, knowledge_description
       - knowledge_type, knowledge_level, tags, related_knowledge
       - total_chunks, created_at, updated_at, metadata

    2. knowledge_overviews: LLM-generated knowledge summaries
       - doc_id (PK/FK), overview, created_at, updated_at

    3. knowledge_document_mapping: Link knowledge to source documents
       - mapping_id (PK), doc_id (FK), file_id
       - relevance_score, created_at
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize Skill Metadata Provider

        Args:
            db_path: Path to SQLite database file (default from settings)
        """
        from app.core.config import settings

        # Use separate database for skill metadata (isolation)
        self.db_path = Path(
            db_path
            or getattr(settings, "SKILL_METADATA_DB_PATH", "./data/skill_metadata.db")
        )
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()  # Prevent concurrent connection initialization

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Knowledge Metadata Provider initialized: {self.db_path}")

    async def _get_connection(self) -> aiosqlite.Connection:
        """
        Get database connection using Singleton pattern with WAL mode.

        This reuses a single connection across all requests to avoid
        connection storm under high concurrency. SQLite WAL mode allows
        concurrent reads while maintaining write serialization.

        Returns:
            Async SQLite connection with optimized settings
        """
        # Fast path: connection already exists
        if self._connection is not None:
            return self._connection

        # Slow path: need to create connection (with lock to prevent race)
        async with self._lock:
            # Double-check after acquiring lock
            if self._connection is not None:
                return self._connection

            # Create singleton connection
            self._connection = await aiosqlite.connect(
                str(self.db_path),
                timeout=30.0,  # Increased from default 5.0s to 30.0s
                check_same_thread=False,  # Allow async usage
            )
            self._connection.row_factory = aiosqlite.Row  # Enable dict-like access

            # Enable WAL mode for better concurrent read/write performance
            await self._connection.execute("PRAGMA journal_mode=WAL")

            # Optimize for concurrent access
            await self._connection.execute(
                "PRAGMA synchronous=NORMAL"
            )  # Faster writes with WAL
            await self._connection.execute("PRAGMA cache_size=10000")  # 10MB cache
            await self._connection.execute(
                "PRAGMA temp_store=MEMORY"
            )  # Use memory for temp tables
            await self._connection.execute(
                "PRAGMA busy_timeout=5000"
            )  # 5 second busy wait
            await self._connection.execute(
                "PRAGMA wal_autocheckpoint=1000"
            )  # Checkpoint at 1000 pages

            logger.info("Created singleton knowledge database connection with WAL mode")

        return self._connection

    async def _execute_with_cleanup(self, func):
        """
        Execute database operation using singleton connection.

        Note: With Singleton pattern, connection is NOT closed after each operation.
        The connection persists for the lifetime of the application.

        Args:
            func: Async function that takes a connection and performs operations

        Returns:
            Result from func
        """
        conn = await self._get_connection()
        return await func(conn)
        # Note: No conn.close() - Singleton connection stays open

    async def initialize_database(self):
        """
        Create tables if they don't exist

        Call this once during application startup
        """
        conn = await self._get_connection()

        # Create knowledge_metadata table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_metadata (
                doc_id TEXT PRIMARY KEY,
                knowledge_name TEXT NOT NULL,
                knowledge_description TEXT,
                knowledge_type TEXT,
                knowledge_level TEXT DEFAULT 'intermediate',
                tags TEXT,
                related_knowledge TEXT,
                total_chunks INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)

        # Create knowledge_overviews table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_overviews (
                doc_id TEXT PRIMARY KEY,
                overview TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (doc_id) REFERENCES knowledge_metadata(doc_id) ON DELETE CASCADE
            )
        """)

        # Create knowledge_document_mapping table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_document_mapping (
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                relevance_score REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (doc_id) REFERENCES knowledge_metadata(doc_id) ON DELETE CASCADE
            )
        """)

        # Create indexes for performance
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_type
            ON knowledge_metadata(knowledge_type)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_name
            ON knowledge_metadata(knowledge_name)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_level
            ON knowledge_metadata(knowledge_level)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_id
            ON knowledge_document_mapping(doc_id)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_id
            ON knowledge_document_mapping(file_id)
        """)

        # =====================================================================
        # knowledge_info table - Single source of truth for knowledge definitions
        # =====================================================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_info (
                knowledge_id TEXT PRIMARY KEY,
                knowledge_name TEXT NOT NULL UNIQUE,
                description TEXT,
                category TEXT DEFAULT 'General',
                display_order INTEGER DEFAULT 0,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add knowledge_id column to knowledge_metadata if not exists
        # (for migration from old schema)
        try:
            await conn.execute("""
                ALTER TABLE knowledge_metadata ADD COLUMN knowledge_id TEXT REFERENCES knowledge_info(knowledge_id)
            """)
            logger.info("Added knowledge_id column to knowledge_metadata")
        except Exception:
            # Column already exists, ignore
            pass

        # Create index for knowledge_id
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_id
            ON knowledge_metadata(knowledge_id)
        """)

        # =====================================================================
        # NEW: processing_jobs table - Track large PDF processing tasks
        # Supports checkpoint/resume and dirty marking for fault tolerance
        # =====================================================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS processing_jobs (
                job_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                knowledge_id TEXT,
                pdf_path TEXT NOT NULL,
                pdf_filename TEXT,
                pdf_size_bytes INTEGER,
                total_pages INTEGER DEFAULT 0,
                last_processed_page INTEGER DEFAULT 0,
                total_chunks INTEGER DEFAULT 0,
                processed_chunks INTEGER DEFAULT 0,
                batch_size INTEGER DEFAULT 12,
                status TEXT DEFAULT 'pending',
                dirty_batches TEXT,
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                error_stack TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT,
                processing_time_seconds REAL,
                avg_page_time_ms REAL,
                FOREIGN KEY (doc_id) REFERENCES knowledge_metadata(doc_id),
                FOREIGN KEY (knowledge_id) REFERENCES knowledge_info(knowledge_id)
            )
        """)

        # Create indexes for processing_jobs
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pj_status
            ON processing_jobs(status)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pj_doc
            ON processing_jobs(doc_id)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pj_created
            ON processing_jobs(created_at)
        """)

        await conn.commit()

        logger.info(
            "Knowledge metadata database tables initialized (including processing_jobs)"
        )

    # =========================================================================
    # Knowledge Metadata Operations
    # =========================================================================

    async def create_skill(
        self,
        doc_id: str,
        knowledge_name: str,
        knowledge_description: Optional[str] = None,
        knowledge_type: Optional[str] = None,
        knowledge_level: str = "intermediate",
        tags: Optional[List[str]] = None,
        related_knowledge: Optional[List[str]] = None,
        total_chunks: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        parent_knowledge_id: str = "root",
        source_name: Optional[str] = None,
        knowledge_id: Optional[str] = None,
    ):
        """
        Create knowledge metadata record

        Args:
            doc_id: Unique document identifier
            knowledge_name: Knowledge name
            knowledge_description: Optional description
            knowledge_type: Knowledge type (e.g., "Programming/Python")
            knowledge_level: Knowledge level (beginner|intermediate|advanced)
            tags: List of tags
            related_knowledge: List of related knowledge IDs
            total_chunks: Number of chunks in knowledge content
            metadata: Additional metadata as dict
            parent_knowledge_id: Parent knowledge ID for hierarchy ('root' for main)
            source_name: Source file name for display (e.g., "民法.pdf")
            knowledge_id: Reference to knowledge_info table

        Example:
            >>> await provider.create_skill(
            ...     doc_id="doc_abc123",
            ...     knowledge_name="Python Async Programming",
            ...     knowledge_type="Programming/Python",
            ...     knowledge_level="advanced",
            ...     tags=["python", "async", "coroutines"],
            ...     knowledge_id="knowledge_xxx"
            ... )
        """
        conn = await self._get_connection()

        try:
            tags_json = json.dumps(tags) if tags else None
            related_knowledge_json = (
                json.dumps(related_knowledge) if related_knowledge else None
            )
            metadata_json = json.dumps(metadata) if metadata else None

            await conn.execute(
                """
                INSERT INTO knowledge_metadata (
                    doc_id, knowledge_name, knowledge_description, knowledge_type,
                    knowledge_level, tags, related_knowledge, total_chunks,
                    created_at, updated_at, metadata, parent_knowledge_id, source_name, knowledge_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    doc_id,
                    knowledge_name,
                    knowledge_description,
                    knowledge_type,
                    knowledge_level,
                    tags_json,
                    related_knowledge_json,
                    total_chunks,
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                    metadata_json,
                    parent_knowledge_id,
                    source_name,
                    knowledge_id,
                ),
            )

            await conn.commit()
            logger.info(
                f"Created knowledge metadata: {doc_id} ({knowledge_name}), parent={parent_knowledge_id}, source={source_name}, knowledge_id={knowledge_id}"
            )

        except Exception as e:
            logger.error(f"Failed to create knowledge metadata: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def get_skill(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve knowledge metadata

        Args:
            doc_id: Document identifier

        Returns:
            Knowledge metadata dict or None if not found

        Example:
            >>> skill = await provider.get_skill("doc_abc123")
            >>> if skill:
            ...     print(skill["knowledge_name"])
        """
        conn = await self._get_connection()

        try:
            async with conn.execute(
                "SELECT * FROM knowledge_metadata WHERE doc_id = ?", (doc_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                return {
                    "doc_id": row["doc_id"],
                    "knowledge_name": row["knowledge_name"],
                    "knowledge_description": row["knowledge_description"],
                    "knowledge_type": row["knowledge_type"],
                    "knowledge_level": row["knowledge_level"],
                    "tags": json.loads(row["tags"]) if row["tags"] else [],
                    "related_knowledge": json.loads(row["related_knowledge"])
                    if row["related_knowledge"]
                    else [],
                    "total_chunks": row["total_chunks"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "metadata": json.loads(row["metadata"])
                    if row["metadata"]
                    else None,
                    "parent_knowledge_id": row["parent_knowledge_id"]
                    if "parent_knowledge_id" in row.keys()
                    else "root",
                    "source_name": row["source_name"]
                    if "source_name" in row.keys()
                    else None,
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get knowledge: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def list_skills(
        self,
        category: Optional[str] = None,
        level: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        List knowledge entries with optional filters

        Args:
            category: Filter by knowledge type
            level: Filter by knowledge level
            tags: Filter by tags (entries matching ANY tag)
            limit: Maximum number of results

        Returns:
            List of knowledge metadata dicts

        Example:
            >>> skills = await provider.list_skills(
            ...     category="Programming/Python",
            ...     level="advanced"
            ... )
        """
        conn = await self._get_connection()

        try:
            query = "SELECT * FROM knowledge_metadata WHERE 1=1"
            params = []

            if category:
                query += " AND knowledge_type = ?"
                params.append(category)

            if level:
                query += " AND knowledge_level = ?"
                params.append(level)

            query += " ORDER BY created_at DESC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            async with conn.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()

            skills = []
            for row in rows:
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}

                # Priority: use source_name column if exists, fallback to metadata.source_file
                db_source_name = (
                    row["source_name"]
                    if "source_name" in row.keys() and row["source_name"]
                    else None
                )
                if not db_source_name:
                    source_file = metadata.get("source_file", "") if metadata else ""
                    db_source_name = (
                        source_file.split("/")[-1].replace(".pdf", "")
                        if source_file
                        else ""
                    )

                skill = {
                    "doc_id": row["doc_id"],
                    "knowledge_name": row["knowledge_name"],
                    "knowledge_description": row["knowledge_description"],
                    "knowledge_type": row["knowledge_type"],
                    "knowledge_level": row["knowledge_level"],
                    "tags": json.loads(row["tags"]) if row["tags"] else [],
                    "related_knowledge": json.loads(row["related_knowledge"])
                    if row["related_knowledge"]
                    else [],
                    "total_chunks": row["total_chunks"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "metadata": metadata,
                    "parent_knowledge_id": row["parent_knowledge_id"]
                    if "parent_knowledge_id" in row.keys()
                    else "root",
                    "source_name": db_source_name,  # Document name from DB column or metadata fallback
                }

                # Filter by tags if specified (match ANY tag)
                if tags and not any(tag in skill["tags"] for tag in tags):
                    continue

                skills.append(skill)

            logger.info(
                f"Listed {len(skills)} knowledge entries (filters: category={category}, level={level})"
            )
            return skills

        except Exception as e:
            logger.error(f"Failed to list knowledge entries: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def update_skill(self, doc_id: str, **updates):
        """
        Update knowledge metadata fields

        Args:
            doc_id: Document identifier
            **updates: Fields to update (knowledge_name, knowledge_description, etc.)

        Example:
            >>> await provider.update_skill(
            ...     doc_id="doc_abc123",
            ...     knowledge_description="Updated description",
            ...     total_chunks=150
            ... )
        """
        conn = await self._get_connection()

        try:
            # Build dynamic update query
            set_clauses = []
            params = []

            for field, value in updates.items():
                if (
                    field in ["tags", "related_knowledge", "metadata"]
                    and value is not None
                ):
                    value = json.dumps(value)
                set_clauses.append(f"{field} = ?")
                params.append(value)

            # Always update updated_at
            set_clauses.append("updated_at = ?")
            params.append(datetime.now(timezone.utc).isoformat())

            # Add doc_id to params
            params.append(doc_id)

            query = f"""
                UPDATE knowledge_metadata
                SET {", ".join(set_clauses)}
                WHERE doc_id = ?
            """

            await conn.execute(query, tuple(params))
            await conn.commit()

            logger.info(f"Updated knowledge metadata: {doc_id}")

        except Exception as e:
            logger.error(f"Failed to update knowledge: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def delete_skill(self, doc_id: str):
        """
        Delete knowledge metadata and related records (cascade)

        Args:
            doc_id: Document identifier

        Example:
            >>> await provider.delete_skill("doc_abc123")
        """
        conn = await self._get_connection()

        try:
            await conn.execute(
                "DELETE FROM knowledge_metadata WHERE doc_id = ?", (doc_id,)
            )

            await conn.commit()
            logger.info(f"Deleted knowledge metadata: {doc_id}")

        except Exception as e:
            logger.error(f"Failed to delete knowledge: {str(e)}")
            raise
        # Singleton connection - no close needed

    # =========================================================================
    # Progress Tracking Operations (FAISS Index Integrity Support)
    # =========================================================================

    async def update_processing_status(
        self,
        doc_id: str,
        status: str,  # 'pending', 'processing', 'completed', 'failed'
        indexed_chunks: Optional[int] = None,
        error: Optional[str] = None,
    ):
        """
        Update knowledge processing status for integrity tracking

        Args:
            doc_id: Document identifier
            status: Processing status (pending, processing, completed, failed)
            indexed_chunks: Number of chunks successfully indexed
            error: Error message if status is 'failed'

        Example:
            >>> # Start processing
            >>> await provider.update_processing_status(
            ...     doc_id="doc_abc123",
            ...     status="processing",
            ...     indexed_chunks=0
            ... )
            >>>
            >>> # Update progress
            >>> await provider.update_processing_status(
            ...     doc_id="doc_abc123",
            ...     status="processing",
            ...     indexed_chunks=25
            ... )
            >>>
            >>> # Mark as completed
            >>> await provider.update_processing_status(
            ...     doc_id="doc_abc123",
            ...     status="completed",
            ...     indexed_chunks=65
            ... )
        """
        conn = await self._get_connection()

        try:
            updates = {"processing_status": status}

            if indexed_chunks is not None:
                updates["indexed_chunks"] = indexed_chunks

            if error is not None:
                updates["last_error"] = error

            # Set timestamps based on status
            if status == "processing" and not await self._has_processing_started(
                conn, doc_id
            ):
                updates["processing_started_at"] = datetime.now(
                    timezone.utc
                ).isoformat()

            if status in ["completed", "failed"]:
                updates["processing_completed_at"] = datetime.now(
                    timezone.utc
                ).isoformat()

            await self.update_skill(doc_id, **updates)

            logger.info(
                f"Updated processing status for {doc_id}: {status} ({indexed_chunks} chunks)"
            )

        except Exception as e:
            logger.error(f"Failed to update processing status for {doc_id}: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def _has_processing_started(
        self, conn: aiosqlite.Connection, doc_id: str
    ) -> bool:
        """Check if processing has already started"""
        cursor = await conn.execute(
            "SELECT processing_started_at FROM knowledge_metadata WHERE doc_id = ?",
            (doc_id,),
        )
        row = await cursor.fetchone()
        return row and row[0] is not None

    async def get_incomplete_skills(self) -> List[Dict[str, Any]]:
        """
        Find knowledge entries with incomplete processing or index integrity issues

        Returns entries where:
        - processing_status != 'completed', OR
        - indexed_chunks < total_chunks

        Returns:
            List of knowledge metadata dicts with integrity issues

        Example:
            >>> incomplete = await provider.get_incomplete_skills()
            >>> for skill in incomplete:
            ...     print(f"Knowledge {skill['doc_id']}: {skill['indexed_chunks']}/{skill['total_chunks']} chunks")
        """
        conn = await self._get_connection()

        try:
            cursor = await conn.execute("""
                SELECT doc_id, knowledge_name, total_chunks, indexed_chunks,
                       processing_status, last_error, created_at, processing_started_at
                FROM knowledge_metadata
                WHERE (processing_status != 'completed'
                   OR indexed_chunks < total_chunks)
                  AND parent_knowledge_id = 'root'
                ORDER BY created_at DESC
            """)

            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            incomplete_skills = []
            for row in rows:
                skill_dict = dict(zip(columns, row))
                incomplete_skills.append(skill_dict)

            logger.info(
                f"Found {len(incomplete_skills)} knowledge entries with incomplete processing/indexing"
            )

            return incomplete_skills

        except Exception as e:
            logger.error(f"Failed to get incomplete skills: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def reset_failed_skills(self) -> int:
        """
        Reset failed knowledge entries to 'pending' status for retry

        Returns:
            Number of entries reset

        Example:
            >>> count = await provider.reset_failed_skills()
            >>> print(f"Reset {count} failed entries")
        """
        conn = await self._get_connection()

        try:
            cursor = await conn.execute("""
                UPDATE knowledge_metadata
                SET processing_status = 'pending',
                    last_error = NULL,
                    processing_started_at = NULL,
                    processing_completed_at = NULL
                WHERE processing_status = 'failed'
            """)

            await conn.commit()
            reset_count = cursor.rowcount

            logger.info(
                f"Reset {reset_count} failed knowledge entries to pending status"
            )

            return reset_count

        except Exception as e:
            logger.error(f"Failed to reset failed knowledge entries: {str(e)}")
            raise
        # Singleton connection - no close needed

    # =========================================================================
    # Knowledge Overview Operations
    # =========================================================================

    async def store_overview(self, doc_id: str, overview: str):
        """
        Store or update knowledge overview

        Args:
            doc_id: Document identifier
            overview: LLM-generated knowledge summary

        Example:
            >>> await provider.store_overview(
            ...     doc_id="doc_abc123",
            ...     overview="This knowledge covers Python async programming..."
            ... )
        """
        conn = await self._get_connection()

        try:
            # Use INSERT OR REPLACE for upsert behavior
            await conn.execute(
                """
                INSERT OR REPLACE INTO knowledge_overviews (
                    doc_id, overview, created_at, updated_at
                ) VALUES (
                    ?,
                    ?,
                    COALESCE((SELECT created_at FROM knowledge_overviews WHERE doc_id = ?), ?),
                    ?
                )
            """,
                (
                    doc_id,
                    overview,
                    doc_id,
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

            await conn.commit()
            logger.info(f"Stored overview for knowledge: {doc_id}")

        except Exception as e:
            logger.error(f"Failed to store overview: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def get_overview(self, doc_id: str) -> Optional[str]:
        """
        Retrieve knowledge overview

        Args:
            doc_id: Document identifier

        Returns:
            Overview text or None if not found
        """
        conn = await self._get_connection()

        try:
            async with conn.execute(
                "SELECT overview FROM knowledge_overviews WHERE doc_id = ?", (doc_id,)
            ) as cursor:
                row = await cursor.fetchone()

            return row["overview"] if row else None

        except Exception as e:
            logger.error(f"Failed to get overview: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def get_multiple_overviews(self, doc_ids: List[str]) -> Dict[str, str]:
        """
        Batch retrieve knowledge overviews

        Args:
            doc_ids: List of document identifiers

        Returns:
            Dict mapping doc_id to overview text
        """
        conn = await self._get_connection()

        try:
            placeholders = ",".join("?" * len(doc_ids))
            query = f"""
                SELECT doc_id, overview
                FROM knowledge_overviews
                WHERE doc_id IN ({placeholders})
            """

            async with conn.execute(query, tuple(doc_ids)) as cursor:
                rows = await cursor.fetchall()

            overviews = {row["doc_id"]: row["overview"] for row in rows}
            logger.info(f"Retrieved {len(overviews)} overviews")
            return overviews

        except Exception as e:
            logger.error(f"Failed to get multiple overviews: {str(e)}")
            raise
        # Singleton connection - no close needed

    # =========================================================================
    # Knowledge-Document Mapping Operations
    # =========================================================================

    async def link_skill_to_document(
        self, doc_id: str, file_id: str, relevance_score: float = 0.0
    ):
        """
        Create knowledge-document mapping

        Args:
            doc_id: Document identifier
            file_id: File identifier (from FileMetadataProvider)
            relevance_score: Relevance score (0.0-1.0)

        Example:
            >>> await provider.link_skill_to_document(
            ...     doc_id="doc_abc123",
            ...     file_id="file_xyz789",
            ...     relevance_score=0.95
            ... )
        """
        conn = await self._get_connection()

        try:
            await conn.execute(
                """
                INSERT INTO knowledge_document_mapping (
                    doc_id, file_id, relevance_score, created_at
                ) VALUES (?, ?, ?, ?)
            """,
                (
                    doc_id,
                    file_id,
                    relevance_score,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

            await conn.commit()
            logger.info(f"Linked knowledge {doc_id} to document {file_id}")

        except Exception as e:
            logger.error(f"Failed to link knowledge to document: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def get_documents_for_skill(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Get all documents linked to a knowledge entry

        Args:
            doc_id: Document identifier

        Returns:
            List of document mapping dicts
        """
        conn = await self._get_connection()

        try:
            async with conn.execute(
                """
                SELECT file_id, relevance_score, created_at
                FROM knowledge_document_mapping
                WHERE doc_id = ?
                ORDER BY relevance_score DESC
            """,
                (doc_id,),
            ) as cursor:
                rows = await cursor.fetchall()

            documents = [
                {
                    "file_id": row["file_id"],
                    "relevance_score": row["relevance_score"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

            logger.info(f"Retrieved {len(documents)} documents for knowledge {doc_id}")
            return documents

        except Exception as e:
            logger.error(f"Failed to get documents for knowledge: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def get_skills_for_document(self, file_id: str) -> List[Dict[str, Any]]:
        """
        Get all knowledge entries linked to a document

        Args:
            file_id: File identifier

        Returns:
            List of knowledge mapping dicts
        """
        conn = await self._get_connection()

        try:
            async with conn.execute(
                """
                SELECT doc_id, relevance_score, created_at
                FROM knowledge_document_mapping
                WHERE file_id = ?
                ORDER BY relevance_score DESC
            """,
                (file_id,),
            ) as cursor:
                rows = await cursor.fetchall()

            skills = [
                {
                    "doc_id": row["doc_id"],
                    "relevance_score": row["relevance_score"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

            logger.info(
                f"Retrieved {len(skills)} knowledge entries for document {file_id}"
            )
            return skills

        except Exception as e:
            logger.error(f"Failed to get knowledge entries for document: {str(e)}")
            raise
        # Singleton connection - no close needed

    # =========================================================================
    # Knowledge Info Operations (Single Source of Truth)
    # =========================================================================

    async def create_skill_head(
        self,
        knowledge_id: str,
        knowledge_name: str,
        description: str = "",
        category: str = "General",
        display_order: int = 0,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a new knowledge info entry (the parent definition of a knowledge).

        This is the single source of truth for knowledge definitions.
        Documents are linked via knowledge_id in knowledge_metadata.

        Args:
            knowledge_id: Unique identifier for the knowledge info
            knowledge_name: Human-readable knowledge name (must be unique)
            description: Optional description
            category: Knowledge category for grouping
            display_order: Order for UI display
            enabled: Whether the knowledge is active

        Returns:
            Created knowledge info dict
        """
        conn = await self._get_connection()

        try:
            await conn.execute(
                """
                INSERT INTO knowledge_info
                (knowledge_id, knowledge_name, description, category, display_order, enabled)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    knowledge_id,
                    knowledge_name,
                    description,
                    category,
                    display_order,
                    enabled,
                ),
            )

            await conn.commit()

            result = {
                "knowledge_id": knowledge_id,
                "knowledge_name": knowledge_name,
                "description": description,
                "category": category,
                "display_order": display_order,
                "enabled": enabled,
            }

            logger.info(
                f"Created knowledge info: {knowledge_name} (ID: {knowledge_id})"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to create knowledge info: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def get_skill_head(self, knowledge_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a knowledge info entry by ID.

        Args:
            knowledge_id: The knowledge info ID

        Returns:
            Knowledge info dict or None if not found
        """
        conn = await self._get_connection()

        try:
            async with conn.execute(
                """
                SELECT knowledge_id, knowledge_name, description, category,
                       display_order, enabled, created_at, updated_at
                FROM knowledge_info
                WHERE knowledge_id = ?
            """,
                (knowledge_id,),
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                return None

            return dict(row)

        except Exception as e:
            logger.error(f"Failed to get knowledge info {knowledge_id}: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def get_skill_head_by_name(
        self, knowledge_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a knowledge info entry by name.

        Args:
            knowledge_name: The knowledge name

        Returns:
            Knowledge info dict or None if not found
        """
        conn = await self._get_connection()

        try:
            async with conn.execute(
                """
                SELECT knowledge_id, knowledge_name, description, category,
                       display_order, enabled, created_at, updated_at
                FROM knowledge_info
                WHERE knowledge_name = ?
            """,
                (knowledge_name,),
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                return None

            return dict(row)

        except Exception as e:
            logger.error(
                f"Failed to get knowledge info by name {knowledge_name}: {str(e)}"
            )
            raise
        # Singleton connection - no close needed

    async def list_skill_heads(
        self, category: Optional[str] = None, enabled_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List all knowledge info entries with optional filtering.

        Args:
            category: Filter by category
            enabled_only: Only return enabled entries

        Returns:
            List of knowledge info dicts
        """
        conn = await self._get_connection()

        try:
            query = """
                SELECT knowledge_id, knowledge_name, description, category,
                       display_order, enabled, created_at, updated_at
                FROM knowledge_info
                WHERE 1=1
            """
            params = []

            if category:
                query += " AND category = ?"
                params.append(category)

            if enabled_only:
                query += " AND enabled = TRUE"

            query += " ORDER BY display_order ASC, knowledge_name ASC"

            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to list knowledge info: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def update_skill_head(
        self, knowledge_id: str, **updates
    ) -> Optional[Dict[str, Any]]:
        """
        Update a knowledge info entry.

        Args:
            knowledge_id: The knowledge info ID
            **updates: Fields to update (knowledge_name, description, category, display_order, enabled)

        Returns:
            Updated knowledge info dict or None if not found
        """
        conn = await self._get_connection()

        allowed_fields = {
            "knowledge_name",
            "description",
            "category",
            "display_order",
            "enabled",
        }
        update_fields = {k: v for k, v in updates.items() if k in allowed_fields}

        if not update_fields:
            return await self.get_skill_head(knowledge_id)

        try:
            set_clause = ", ".join([f"{k} = ?" for k in update_fields.keys()])
            set_clause += ", updated_at = CURRENT_TIMESTAMP"

            query = f"UPDATE knowledge_info SET {set_clause} WHERE knowledge_id = ?"
            params = list(update_fields.values()) + [knowledge_id]

            await conn.execute(query, params)
            await conn.commit()

            logger.info(f"Updated knowledge info {knowledge_id}")
            return await self.get_skill_head(knowledge_id)

        except Exception as e:
            logger.error(f"Failed to update knowledge info {knowledge_id}: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def delete_skill_head(self, knowledge_id: str) -> bool:
        """
        Delete a knowledge info entry and all associated documents.

        This method performs cascade deletion of ALL related data:
        1. knowledge_chunk_metadata - chunk embeddings metadata
        2. knowledge_document_mapping - document-knowledge relationships
        3. knowledge_overviews - knowledge overview/summary data
        4. knowledge_metadata - document/source metadata
        5. knowledge_info - the knowledge info entry itself

        Args:
            knowledge_id: The knowledge info ID

        Returns:
            True if deleted, False if not found
        """
        conn = await self._get_connection()

        try:
            # Step 1: Get all doc_ids linked to this knowledge_id
            # This is CRITICAL for cascade deletion - only delete data for these specific doc_ids
            cursor = await conn.execute(
                """
                SELECT doc_id FROM knowledge_metadata WHERE knowledge_id = ?
            """,
                (knowledge_id,),
            )
            rows = await cursor.fetchall()
            doc_ids = [row[0] for row in rows]

            logger.info(
                f"Found {len(doc_ids)} doc_ids linked to knowledge_id {knowledge_id}"
            )

            if doc_ids:
                # Create placeholders for IN clause
                placeholders = ", ".join(["?" for _ in doc_ids])

                # Step 2: Delete from knowledge_chunk_metadata (chunks for these docs only)
                await conn.execute(
                    f"""
                    DELETE FROM knowledge_chunk_metadata WHERE doc_id IN ({placeholders})
                """,
                    doc_ids,
                )
                logger.info(f"Deleted chunk metadata for doc_ids: {doc_ids}")

                # Step 3: Delete from knowledge_document_mapping (document mappings for these docs only)
                await conn.execute(
                    f"""
                    DELETE FROM knowledge_document_mapping WHERE doc_id IN ({placeholders})
                """,
                    doc_ids,
                )
                logger.info(f"Deleted document mappings for doc_ids: {doc_ids}")

                # Step 4: Delete from knowledge_overviews (overviews for these docs only)
                await conn.execute(
                    f"""
                    DELETE FROM knowledge_overviews WHERE doc_id IN ({placeholders})
                """,
                    doc_ids,
                )
                logger.info(f"Deleted overviews for doc_ids: {doc_ids}")

            # Step 5: Delete all documents (knowledge_metadata) linked to this knowledge
            await conn.execute(
                """
                DELETE FROM knowledge_metadata WHERE knowledge_id = ?
            """,
                (knowledge_id,),
            )
            logger.info(
                f"Deleted knowledge_metadata records for knowledge_id: {knowledge_id}"
            )

            # Step 6: Delete the knowledge info entry itself
            cursor = await conn.execute(
                """
                DELETE FROM knowledge_info WHERE knowledge_id = ?
            """,
                (knowledge_id,),
            )

            await conn.commit()

            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(
                    f"Successfully deleted knowledge info {knowledge_id} and ALL associated data "
                    f"({len(doc_ids)} documents, including chunks, mappings, overviews)"
                )
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete knowledge info {knowledge_id}: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def get_documents_for_head(self, knowledge_id: str) -> List[Dict[str, Any]]:
        """
        Get all documents (knowledge_metadata entries) for a knowledge info entry.

        Args:
            knowledge_id: The knowledge info ID

        Returns:
            List of document metadata dicts
        """

        async def _get_docs(conn):
            async with conn.execute(
                """
                SELECT doc_id, knowledge_name, knowledge_description, knowledge_type,
                       total_chunks, source_name, parent_knowledge_id, knowledge_id,
                       created_at, updated_at
                FROM knowledge_metadata
                WHERE knowledge_id = ?
                ORDER BY created_at ASC
            """,
                (knowledge_id,),
            ) as cursor:
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]

        try:
            return await self._execute_with_cleanup(_get_docs)
        except Exception as e:
            logger.error(
                f"Failed to get documents for knowledge {knowledge_id}: {str(e)}"
            )
            raise

    async def get_skill_tree(self) -> List[Dict[str, Any]]:
        """
        Get the complete knowledge tree structure with FAISS vector counts.

        Returns a list of knowledge info entries, each with a 'documents' list containing
        all linked documents and their FAISS vector counts.

        Returns:
            List of knowledge info dicts with nested documents
        """
        from app.SkillServices.index_integrity import get_index_stats

        try:
            # Get all knowledge info entries
            heads = await self.list_skill_heads(enabled_only=False)

            # For each head, get its documents (each call uses separate connection)
            for head in heads:
                head["documents"] = await self.get_documents_for_head(
                    head["knowledge_id"]
                )

                # Add FAISS vector count for each document
                for doc in head["documents"]:
                    doc_id = doc["doc_id"]
                    try:
                        # Get FAISS index stats
                        index_stats = await get_index_stats(doc_id)
                        doc["indexed_vectors"] = index_stats.get("vector_count", 0)
                        doc["index_exists"] = index_stats.get("index_exists", False)
                    except Exception as e:
                        logger.warning(f"Failed to get index stats for {doc_id}: {e}")
                        doc["indexed_vectors"] = 0
                        doc["index_exists"] = False

                # Calculate totals
                head["total_chunks"] = sum(
                    doc.get("total_chunks", 0) for doc in head["documents"]
                )
                head["total_vectors"] = sum(
                    doc.get("indexed_vectors", 0) for doc in head["documents"]
                )
                head["document_count"] = len(head["documents"])

            return heads

        except Exception as e:
            logger.error(f"Failed to get knowledge tree: {str(e)}")
            raise

    async def migrate_existing_data(self) -> Dict[str, Any]:
        """
        Migrate existing data from old schema to new knowledge_info architecture.

        This function:
        1. Finds all "group header" entries (parent_knowledge_id='root', source_name is NULL)
        2. Creates corresponding knowledge_info entries
        3. Links child documents to their knowledge_id

        Returns:
            Migration summary dict
        """
        conn = await self._get_connection()

        try:
            migrated_heads = 0
            updated_documents = 0

            # Find all group headers (root-level entries without source_name)
            async with conn.execute("""
                SELECT doc_id, knowledge_name, knowledge_description, knowledge_type
                FROM knowledge_metadata
                WHERE parent_knowledge_id = 'root'
                AND (source_name IS NULL OR source_name = '')
                AND doc_id != 'root'
            """) as cursor:
                group_headers = await cursor.fetchall()

            for header in group_headers:
                knowledge_id = header["doc_id"]
                knowledge_name = header["knowledge_name"]

                # Check if knowledge_info already exists
                existing = await self.get_skill_head(knowledge_id)
                if existing:
                    logger.info(f"Knowledge info already exists: {knowledge_name}")
                    continue

                # Create knowledge_info entry
                try:
                    await conn.execute(
                        """
                        INSERT INTO knowledge_info
                        (knowledge_id, knowledge_name, description, category)
                        VALUES (?, ?, ?, ?)
                    """,
                        (
                            knowledge_id,
                            knowledge_name,
                            header["knowledge_description"] or "",
                            header["knowledge_type"] or "General",
                        ),
                    )
                    migrated_heads += 1
                    logger.info(f"Created knowledge_info for: {knowledge_name}")
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e):
                        logger.warning(
                            f"Knowledge info name already exists: {knowledge_name}"
                        )
                    else:
                        raise

                # Update child documents to link to this knowledge
                cursor = await conn.execute(
                    """
                    UPDATE knowledge_metadata
                    SET knowledge_id = ?
                    WHERE parent_knowledge_id = ?
                """,
                    (knowledge_id, knowledge_id),
                )
                updated_documents += cursor.rowcount

            await conn.commit()

            result = {
                "migrated_heads": migrated_heads,
                "updated_documents": updated_documents,
                "status": "success",
            }

            logger.info(f"Migration complete: {result}")
            return result

        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            raise
        # Singleton connection - no close needed

    # =========================================================================
    # Chunk Metadata Operations (For OPMP Progressive Streaming)
    # =========================================================================

    async def get_chunk_metadata(
        self, doc_id: str, document_id: str, faiss_index: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get chunk metadata by doc_id and FAISS index (chunk_index).

        This method is called by the OPMP progressive streaming Phase 2
        to retrieve full chunk content for context assembly.

        IMPORTANT: chunk_index is GLOBAL within a knowledge entry (not per document).
        - Single-doc: chunk_index 0-66
        - Multi-doc: doc1 has 0-369, doc2 has 370-882 (continuous)

        Args:
            doc_id: Document identifier (e.g., "doc_20251211_xxx")
            document_id: Document identifier (kept for API compatibility, but not used in query)
            faiss_index: FAISS index position = chunk_index (0-based integer)

        Returns:
            Dict with keys:
                - content: Full chunk text
                - page: Page number (or 0 if not available)
                - source_file: Source filename
            Returns None if chunk not found

        Example:
            metadata = await provider.get_chunk_metadata(
                doc_id="doc_20251211_022234_48af4341_feb60e",
                document_id="doc_871d2f9d",  # Not used in query
                faiss_index=24
            )
            # Returns: {"content": "Strix Halo is...", "page": 25, "source_file": "Strix Halo.pdf"}
        """
        conn = await self._get_connection()

        try:
            # ✅ FIX: Use chunk_index directly (it's global within knowledge entry, not per document)
            # FAISS index == chunk_index (both are 0-based, continuous within knowledge entry)
            # Do NOT filter by document_id - chunk_index is unique within knowledge entry
            query = """
                SELECT chunk_text, page_number, document_name
                FROM knowledge_chunk_metadata
                WHERE doc_id = ?
                  AND chunk_index = ?
            """

            async with conn.execute(query, (doc_id, faiss_index)) as cursor:
                row = await cursor.fetchone()

            if not row:
                logger.warning(
                    f"Chunk not found for doc {doc_id} at chunk_index {faiss_index}"
                )
                return None

            # Map database fields to expected format
            return {
                "content": row["chunk_text"] or "",  # Map chunk_text → content
                "page": row["page_number"] or 0,  # Correct column name
                "source_file": row["document_name"] or "",  # Correct column name
            }

        except Exception as e:
            logger.error(
                f"Failed to get chunk metadata for doc {doc_id}, document {document_id}[{faiss_index}]: {e}"
            )
            return None
        # Singleton connection - no close needed

    # =========================================================================
    # Processing Jobs Operations (Large PDF Checkpoint/Resume)
    # =========================================================================

    async def create_processing_job(
        self,
        job_id: str,
        doc_id: str,
        pdf_path: str,
        total_pages: int,
        knowledge_id: Optional[str] = None,
        pdf_filename: Optional[str] = None,
        pdf_size_bytes: Optional[int] = None,
        batch_size: int = 12,
    ) -> Dict[str, Any]:
        """
        Create a new processing job for large PDF tracking

        Args:
            job_id: Unique job identifier (UUID)
            doc_id: Associated document ID
            pdf_path: Path to the PDF file
            total_pages: Total number of pages in PDF
            knowledge_id: Optional knowledge info ID
            pdf_filename: Optional filename
            pdf_size_bytes: Optional file size
            batch_size: Batch size for processing (default 12)

        Returns:
            Created job record
        """
        conn = await self._get_connection()

        try:
            await conn.execute(
                """
                INSERT INTO processing_jobs (
                    job_id, doc_id, knowledge_id, pdf_path, pdf_filename,
                    pdf_size_bytes, total_pages, batch_size, status, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'processing', CURRENT_TIMESTAMP)
            """,
                (
                    job_id,
                    doc_id,
                    knowledge_id,
                    pdf_path,
                    pdf_filename,
                    pdf_size_bytes,
                    total_pages,
                    batch_size,
                ),
            )

            await conn.commit()

            logger.info(
                f"Created processing job: {job_id} for {pdf_filename or pdf_path}"
            )

            return {
                "job_id": job_id,
                "doc_id": doc_id,
                "knowledge_id": knowledge_id,
                "pdf_path": pdf_path,
                "total_pages": total_pages,
                "status": "processing",
            }

        except Exception as e:
            logger.error(f"Failed to create processing job: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def get_processing_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get processing job by ID

        Args:
            job_id: Job identifier

        Returns:
            Job record dict or None
        """
        conn = await self._get_connection()

        try:
            async with conn.execute(
                """
                SELECT * FROM processing_jobs WHERE job_id = ?
            """,
                (job_id,),
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                return dict(row)
            return None

        except Exception as e:
            logger.error(f"Failed to get processing job {job_id}: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def update_processing_job(
        self,
        job_id: str,
        last_processed_page: Optional[int] = None,
        processed_chunks: Optional[int] = None,
        total_chunks: Optional[int] = None,
        status: Optional[str] = None,
        dirty_batches: Optional[str] = None,
        error_message: Optional[str] = None,
        error_stack: Optional[str] = None,
        retry_count: Optional[int] = None,
        processing_time_seconds: Optional[float] = None,
        avg_page_time_ms: Optional[float] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> bool:
        """
        Update processing job checkpoint

        Args:
            job_id: Job identifier
            last_processed_page: Last successfully processed page number
            processed_chunks: Number of chunks processed
            total_chunks: Total chunks in job
            status: Job status (pending/processing/dirty/completed/failed)
            dirty_batches: JSON string of dirty batch info
            error_message: Error message if any
            error_stack: Error stack trace
            retry_count: Number of retries
            processing_time_seconds: Total processing time
            avg_page_time_ms: Average time per page
            started_at: Job start timestamp (ISO format)
            completed_at: Job completion timestamp (ISO format)

        Returns:
            True if updated successfully
        """
        conn = await self._get_connection()

        # Build dynamic update query
        updates = ["updated_at = CURRENT_TIMESTAMP"]
        params = []

        if last_processed_page is not None:
            updates.append("last_processed_page = ?")
            params.append(last_processed_page)

        if processed_chunks is not None:
            updates.append("processed_chunks = ?")
            params.append(processed_chunks)

        if total_chunks is not None:
            updates.append("total_chunks = ?")
            params.append(total_chunks)

        if status is not None:
            updates.append("status = ?")
            params.append(status)
            if status == "completed":
                updates.append("completed_at = CURRENT_TIMESTAMP")

        if dirty_batches is not None:
            updates.append("dirty_batches = ?")
            params.append(dirty_batches)

        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        if error_stack is not None:
            updates.append("error_stack = ?")
            params.append(error_stack)

        if retry_count is not None:
            updates.append("retry_count = ?")
            params.append(retry_count)

        if processing_time_seconds is not None:
            updates.append("processing_time_seconds = ?")
            params.append(processing_time_seconds)

        if avg_page_time_ms is not None:
            updates.append("avg_page_time_ms = ?")
            params.append(avg_page_time_ms)

        if started_at is not None:
            updates.append("started_at = ?")
            params.append(started_at)

        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at)

        params.append(job_id)

        try:
            await conn.execute(
                f"""
                UPDATE processing_jobs
                SET {", ".join(updates)}
                WHERE job_id = ?
            """,
                tuple(params),
            )

            await conn.commit()

            logger.debug(
                f"Updated processing job {job_id}: status={status}, page={last_processed_page}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to update processing job {job_id}: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def get_interrupted_jobs(self) -> List[Dict[str, Any]]:
        """
        Get all interrupted processing jobs (for startup recovery)

        Returns jobs with status 'processing' or 'dirty' that need recovery.

        Returns:
            List of interrupted job records
        """
        conn = await self._get_connection()

        try:
            async with conn.execute("""
                SELECT * FROM processing_jobs
                WHERE status IN ('processing', 'dirty')
                ORDER BY created_at ASC
            """) as cursor:
                rows = await cursor.fetchall()

            jobs = [dict(row) for row in rows]
            logger.info(f"Found {len(jobs)} interrupted processing jobs")
            return jobs

        except Exception as e:
            logger.error(f"Failed to get interrupted jobs: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def mark_job_dirty(
        self, job_id: str, dirty_batch_info: Dict[str, Any], error_message: str
    ) -> bool:
        """
        Mark a processing job as dirty (recoverable error)

        Args:
            job_id: Job identifier
            dirty_batch_info: Info about the dirty batch (start_idx, count, page)
            error_message: Error that caused the dirty state

        Returns:
            True if marked successfully
        """
        import json

        conn = await self._get_connection()

        try:
            # Get existing dirty_batches
            async with conn.execute(
                """
                SELECT dirty_batches FROM processing_jobs WHERE job_id = ?
            """,
                (job_id,),
            ) as cursor:
                row = await cursor.fetchone()

            existing_batches = []
            if row and row["dirty_batches"]:
                try:
                    existing_batches = json.loads(row["dirty_batches"])
                except json.JSONDecodeError:
                    existing_batches = []

            # Append new dirty batch
            existing_batches.append(dirty_batch_info)

            # Update job
            await conn.execute(
                """
                UPDATE processing_jobs
                SET status = 'dirty',
                    dirty_batches = ?,
                    error_message = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ?
            """,
                (json.dumps(existing_batches), error_message, job_id),
            )

            await conn.commit()

            logger.warning(f"Marked job {job_id} as dirty: {error_message}")
            return True

        except Exception as e:
            logger.error(f"Failed to mark job {job_id} as dirty: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def delete_processing_job(self, job_id: str) -> bool:
        """
        Delete a processing job record

        Args:
            job_id: Job identifier

        Returns:
            True if deleted successfully
        """
        conn = await self._get_connection()

        try:
            await conn.execute(
                """
                DELETE FROM processing_jobs WHERE job_id = ?
            """,
                (job_id,),
            )

            await conn.commit()

            logger.info(f"Deleted processing job: {job_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete processing job {job_id}: {str(e)}")
            raise
        # Singleton connection - no close needed

    async def close(self):
        """Close database connection"""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.debug("Closed knowledge database connection")

    # =========================================================================
    # WAL Maintenance Operations
    # =========================================================================

    async def checkpoint_wal(self, mode: str = "PASSIVE") -> dict:
        """
        Perform WAL checkpoint to clean up WAL file.

        Call during maintenance windows or when WAL file grows large.

        Checkpoint Modes:
        - PASSIVE: Checkpoint as many frames as possible without waiting
        - FULL: Wait for readers, then checkpoint all frames
        - RESTART: Like FULL, also restarts the WAL file
        - TRUNCATE: Like RESTART, also truncates the WAL file to zero bytes

        Args:
            mode: Checkpoint mode (PASSIVE, FULL, RESTART, TRUNCATE)

        Returns:
            Dict with checkpoint results

        Example:
            >>> result = await provider.checkpoint_wal("TRUNCATE")
            >>> print(f"Checkpointed {result['checkpointed']} frames")
        """
        from app.Providers.db_utils import checkpoint_wal as _checkpoint_wal

        conn = await self._get_connection()
        return await _checkpoint_wal(conn, mode)

    async def get_wal_stats(self) -> dict:
        """
        Get WAL file statistics for monitoring.

        Returns:
            Dict with WAL statistics (journal_mode, wal_autocheckpoint, page_size)

        Example:
            >>> stats = await provider.get_wal_stats()
            >>> print(f"Journal mode: {stats['journal_mode']}")
        """
        from app.Providers.db_utils import get_wal_stats as _get_wal_stats

        conn = await self._get_connection()
        return await _get_wal_stats(conn)


# ============================================================================
# Singleton Instance
# ============================================================================

_skill_metadata_provider_instance: Optional[SkillMetadataProvider] = None


def get_skill_metadata_provider() -> SkillMetadataProvider:
    """
    FastAPI dependency for Knowledge Metadata Provider

    Returns:
        Singleton SkillMetadataProvider instance

    Usage:
        @router.get("/skills")
        async def list_skills(
            provider: SkillMetadataProvider = Depends(get_skill_metadata_provider)
        ):
            skills = await provider.list_skills()
            return {"skills": skills}
    """
    global _skill_metadata_provider_instance

    if _skill_metadata_provider_instance is None:
        _skill_metadata_provider_instance = SkillMetadataProvider()

    return _skill_metadata_provider_instance
