# app/SkillServices/skill_ingestion_service.py
"""
Skill Ingestion Service

Skill content validation, ID generation, text chunking, and metadata enrichment.
Operates on text content (not files), optimized for skill-based knowledge representation.
"""

import logging
import hashlib
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

# LangChain text splitting (updated for langchain 1.x)
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Application imports
from app.core.config import settings

logger = logging.getLogger(__name__)


class SkillIngestionService:
    """
    Service for handling skill content ingestion workflow

    Workflow:
    1. Generate unique skill_id
    2. Chunk skill content into smaller pieces
    3. Enrich chunk metadata
    4. Return processed skill data

    Differences from file-based ingestion:
    - No file extraction (direct text input)
    - Skill-specific chunk size (default 1000 vs file 500)
    - Skill-centric metadata structure
    """

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None
    ):
        """
        Initialize Skill Ingestion Service

        Args:
            chunk_size: Text chunk size (default from settings or 1000)
            chunk_overlap: Chunk overlap size (default from settings or 200)
        """
        # Skill-specific chunking configuration
        # Skills typically contain conceptual content, use larger chunks
        self.chunk_size = chunk_size or getattr(
            settings,
            'SKILL_CHUNK_SIZE',
            1024  # Larger than file chunks (500)
        )
        self.chunk_overlap = chunk_overlap or getattr(
            settings,
            'SKILL_CHUNK_OVERLAP',
            200
        )

        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len
        )

        logger.info(
            f"Skill Ingestion Service initialized "
            f"(chunk_size={self.chunk_size}, overlap={self.chunk_overlap})"
        )

    def generate_skill_id(
        self,
        skill_name: str,
        content: str
    ) -> str:
        """
        Generate unique skill ID

        Format: skill_{timestamp}_{uuid8}_{hash8}

        Components:
        - timestamp: For sortability
        - uuid: For collision resistance
        - hash: For duplicate detection

        Args:
            skill_name: Skill name
            content: Skill content for hashing

        Returns:
            Unique skill ID

        Example:
            >>> service.generate_skill_id(
            ...     "Python Async",
            ...     "This skill covers async programming..."
            ... )
            'skill_1732523400_abc12345_def67890'
        """
        # Component 1: Timestamp (sortable)
        timestamp = int(time.time())

        # Component 2: Random UUID (collision resistance)
        uuid_part = str(uuid.uuid4()).replace('-', '')[:8]

        # Component 3: Content hash (duplicate detection)
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:8]

        skill_id = f"skill_{timestamp}_{uuid_part}_{content_hash}"

        logger.debug(f"Generated skill_id: {skill_id}")
        return skill_id

    async def generate_unique_skill_id(
        self,
        skill_name: str,
        content: str,
        skill_metadata_provider,
        max_retries: int = 3
    ) -> str:
        """
        Generate unique skill ID with database collision detection

        Args:
            skill_name: Skill name
            content: Skill content
            skill_metadata_provider: SkillMetadataProvider instance
            max_retries: Maximum retry attempts

        Returns:
            Unique skill ID

        Raises:
            ValueError: If failed to generate unique ID after max_retries
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
                        f"Skill ID collision detected: {skill_id} "
                        f"(attempt {attempt + 1}/{max_retries}). Retrying..."
                    )
                    # Add small delay before retry
                    time.sleep(0.1)
                    continue

            except Exception as e:
                logger.error(f"Error checking skill_id uniqueness: {str(e)}")
                # If check fails, return the ID (optimistic approach)
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
        Chunk skill content into smaller pieces

        Args:
            content: Skill text content
            metadata: Optional base metadata

        Returns:
            List of chunk dicts with 'content' and 'metadata'

        Example:
            >>> chunks = service.chunk_skill_content(
            ...     content="This is skill content...",
            ...     metadata={"skill_id": "skill_123", "skill_name": "Python"}
            ... )
            >>> print(len(chunks))
            5
        """
        try:
            # Validate input
            if not content or not content.strip():
                raise ValueError("Skill content cannot be empty")

            # Split text using configured splitter
            text_chunks = self.text_splitter.split_text(content)

            # Enrich with metadata
            chunks = []
            for i, chunk_text in enumerate(text_chunks):
                chunk_meta = metadata.copy() if metadata else {}
                chunk_meta["chunk_index"] = i
                chunk_meta["total_chunks"] = len(text_chunks)
                chunk_meta["chunk_size"] = len(chunk_text)

                chunks.append({
                    "content": chunk_text,
                    "metadata": chunk_meta
                })

            logger.info(f"Chunked skill content into {len(chunks)} chunks")
            return chunks

        except Exception as e:
            logger.error(f"Skill content chunking failed: {str(e)}")
            raise ValueError(f"Failed to chunk skill content: {str(e)}")

    def validate_skill_content(
        self,
        content: str,
        min_length: int = 100,
        max_length: int = 1000000
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate skill content

        Args:
            content: Skill text content
            min_length: Minimum content length
            max_length: Maximum content length

        Returns:
            Tuple of (is_valid, error_message)

        Example:
            >>> is_valid, error = service.validate_skill_content(content)
            >>> if not is_valid:
            ...     print(f"Validation failed: {error}")
        """
        # Check if empty
        if not content or not content.strip():
            return False, "Skill content cannot be empty"

        # Check length
        content_length = len(content)
        if content_length < min_length:
            return False, f"Skill content too short (minimum: {min_length} characters)"

        if content_length > max_length:
            return False, f"Skill content too long (maximum: {max_length} characters)"

        # Basic quality checks
        if content.count('\n') / content_length > 0.5:
            return False, "Skill content has too many line breaks (possible formatting issue)"

        return True, None

    async def process_skill(
        self,
        skill_name: str,
        skill_content: str,
        skill_description: Optional[str] = None,
        skill_category: Optional[str] = None,
        skill_level: str = "intermediate",
        tags: Optional[List[str]] = None,
        skill_metadata_provider = None,
        validate: bool = True
    ) -> Dict[str, Any]:
        """
        Complete skill ingestion workflow

        Workflow:
        1. Validate skill content (optional)
        2. Generate unique skill_id
        3. Chunk skill content
        4. Enrich chunk metadata

        Args:
            skill_name: Skill name
            skill_content: Full skill text content
            skill_description: Optional description
            skill_category: Optional category
            skill_level: Skill difficulty level
            tags: Optional tags
            skill_metadata_provider: Optional provider for unique ID generation
            validate: Whether to validate content (default True)

        Returns:
            Dict with skill_id, chunks, metadata

        Example:
            >>> result = await service.process_skill(
            ...     skill_name="Python Async Programming",
            ...     skill_content="This skill covers...",
            ...     skill_category="Programming/Python",
            ...     skill_level="advanced",
            ...     skill_metadata_provider=provider
            ... )
            >>> print(result["skill_id"])
            'skill_1732523400_abc12345'
        """
        try:
            # Step 1: Validate content
            if validate:
                is_valid, error = self.validate_skill_content(skill_content)
                if not is_valid:
                    raise ValueError(f"Skill content validation failed: {error}")

            # Step 2: Generate unique skill ID
            if skill_metadata_provider is not None:
                skill_id = await self.generate_unique_skill_id(
                    skill_name,
                    skill_content,
                    skill_metadata_provider
                )
            else:
                skill_id = self.generate_skill_id(skill_name, skill_content)

            # Step 3: Chunk skill content
            base_metadata = {
                "skill_id": skill_id,
                "skill_name": skill_name,
                "skill_category": skill_category,
                "skill_level": skill_level,
                "processing_timestamp": datetime.now(timezone.utc).isoformat()
            }

            chunks = self.chunk_skill_content(skill_content, metadata=base_metadata)

            # Step 4: Return result
            result = {
                "skill_id": skill_id,
                "skill_name": skill_name,
                "skill_description": skill_description,
                "skill_category": skill_category,
                "skill_level": skill_level,
                "tags": tags or [],
                "chunks": chunks,
                "chunk_count": len(chunks),
                "content_length": len(skill_content),
                "processing_timestamp": base_metadata["processing_timestamp"]
            }

            logger.info(
                f"Processed skill '{skill_name}': "
                f"skill_id={skill_id}, chunks={len(chunks)}, "
                f"content_length={len(skill_content)}"
            )

            return result

        except ValueError as e:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error(f"Skill processing failed: {str(e)}")
            raise ValueError(f"Failed to process skill: {str(e)}")

    def estimate_chunk_count(self, content: str) -> int:
        """
        Estimate number of chunks without actually splitting

        Args:
            content: Skill text content

        Returns:
            Estimated chunk count

        Example:
            >>> count = service.estimate_chunk_count(content)
            >>> print(f"Will generate approximately {count} chunks")
        """
        content_length = len(content)
        effective_chunk_size = self.chunk_size - self.chunk_overlap

        if effective_chunk_size <= 0:
            return 0

        estimated_count = max(1, (content_length + effective_chunk_size - 1) // effective_chunk_size)
        return estimated_count


# ============================================================================
# Singleton Instance
# ============================================================================

_skill_ingestion_service_instance: Optional[SkillIngestionService] = None


def get_skill_ingestion_service() -> SkillIngestionService:
    """
    FastAPI dependency for Skill Ingestion Service

    Returns:
        Singleton SkillIngestionService instance

    Usage:
        @router.post("/skills/upload")
        async def upload_skill(
            service: SkillIngestionService = Depends(get_skill_ingestion_service)
        ):
            result = await service.process_skill(...)
            return result
    """
    global _skill_ingestion_service_instance

    if _skill_ingestion_service_instance is None:
        _skill_ingestion_service_instance = SkillIngestionService()

    return _skill_ingestion_service_instance
