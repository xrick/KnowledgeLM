# app/Services/document_overview_service.py
"""
Document Overview Service

Generates and manages document-level overviews for improved RAG retrieval.
Addresses the "file exists but no content found" issue by providing:
1. Pre-computed document overviews stored in SQLite
2. Overview-based context for LLM responses
3. Sequential multi-document processing

Architecture:
- Overview is generated during file upload (async background task)
- Overview is stored in SQLite with file_id reference
- RAG pipeline uses overview + chunks for better context
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Maximum chunks to use for overview generation
OVERVIEW_CHUNK_LIMIT = 30
# Maximum characters per overview
OVERVIEW_MAX_CHARS = 1500 
MAX_TOKENS = 1000


class DocumentOverviewService:
    """
    Document Overview Service

    Generates concise document overviews for:
    1. Faster context retrieval
    2. Better multi-document handling
    3. Fallback when vector search fails
    """

    OVERVIEW_GENERATION_PROMPT = """你是一位專業的文檔摘要專家。請根據以下文檔片段生成一份簡潔的文檔概述。

[文檔片段]
{chunks_text}

[任務要求]
請生成一份200-300字的文檔概述，包含：
1. 文檔的主題和目的
2. 核心內容和關鍵概念
3. 主要結論或貢獻

請直接輸出概述內容，不要包含其他說明文字。"""

    def __init__(self, llm_client=None):
        """
        Initialize Document Overview Service

        Args:
            llm_client: LLM provider client for overview generation
        """
        self.llm_client = llm_client
        logger.info("Document Overview Service initialized")

    async def generate_overview(
        self,
        file_id: str,
        chunks: List[str],
        filename: str
    ) -> str:
        """
        Generate document overview from chunks

        Args:
            file_id: Document file identifier
            chunks: List of text chunks from the document
            filename: Original filename for context

        Returns:
            str: Generated document overview
        """
        try:
            # Take first N chunks for overview generation
            overview_chunks = chunks[:OVERVIEW_CHUNK_LIMIT]
            chunks_text = "\n\n---\n\n".join(overview_chunks)

            # Truncate if too long
            if len(chunks_text) > 10000:
                chunks_text = chunks_text[:10000] + "...\n[截斷]"

            # Generate overview using LLM
            if self.llm_client:
                prompt = self.OVERVIEW_GENERATION_PROMPT.format(chunks_text=chunks_text)

                messages = [
                    {"role": "system", "content": "你是一位專業的文檔摘要專家，善於提取文檔的核心信息。"},
                    {"role": "user", "content": prompt}
                ]

                response = await self.llm_client.get_chat_completion(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=MAX_TOKENS
                )

                overview = response['choices'][0]['message']['content']

                # Truncate if too long
                if len(overview) > OVERVIEW_MAX_CHARS:
                    overview = overview[:OVERVIEW_MAX_CHARS] + "..."

                logger.info(f"Generated overview for {file_id}: {len(overview)} chars")
                return overview

            else:
                # Fallback: Use first chunk as simple overview
                fallback_overview = f"文檔: {filename}\n\n" + chunks_text[:OVERVIEW_MAX_CHARS]
                logger.warning(f"No LLM client, using fallback overview for {file_id}")
                return fallback_overview

        except Exception as e:
            logger.error(f"Failed to generate overview for {file_id}: {str(e)}")
            # Return a basic overview on error
            return f"文檔: {filename}\n\n[概述生成失敗，請查看原文檔]"

    async def store_overview(
        self,
        file_metadata_provider,
        file_id: str,
        overview: str
    ):
        """
        Store document overview in SQLite

        Args:
            file_metadata_provider: File metadata provider instance
            file_id: Document file identifier
            overview: Generated overview text
        """
        try:
            conn = await file_metadata_provider._get_connection()

            # Check if document_overviews table exists, create if not
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS document_overviews (
                    file_id TEXT PRIMARY KEY,
                    overview TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_id) REFERENCES file_metadata(file_id)
                )
            """)

            # Insert or update overview
            await conn.execute("""
                INSERT INTO document_overviews (file_id, overview, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                    overview = excluded.overview,
                    updated_at = excluded.updated_at
            """, (
                file_id,
                overview,
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat()
            ))

            await conn.commit()
            logger.info(f"Stored overview for file_id: {file_id}")

        except Exception as e:
            logger.error(f"Failed to store overview for {file_id}: {str(e)}")
            raise

    async def get_overview(
        self,
        file_metadata_provider,
        file_id: str
    ) -> Optional[str]:
        """
        Retrieve document overview from SQLite

        Args:
            file_metadata_provider: File metadata provider instance
            file_id: Document file identifier

        Returns:
            str: Document overview or None if not found
        """
        try:
            conn = await file_metadata_provider._get_connection()

            async with conn.execute(
                "SELECT overview FROM document_overviews WHERE file_id = ?",
                (file_id,)
            ) as cursor:
                row = await cursor.fetchone()

                if row:
                    return row[0]
                return None

        except Exception as e:
            logger.error(f"Failed to get overview for {file_id}: {str(e)}")
            return None

    async def get_multiple_overviews(
        self,
        file_metadata_provider,
        file_ids: List[str]
    ) -> Dict[str, str]:
        """
        Retrieve overviews for multiple files

        Args:
            file_metadata_provider: File metadata provider instance
            file_ids: List of document file identifiers

        Returns:
            Dict mapping file_id to overview text
        """
        overviews = {}

        for file_id in file_ids:
            overview = await self.get_overview(file_metadata_provider, file_id)
            if overview:
                overviews[file_id] = overview

        logger.info(f"Retrieved {len(overviews)}/{len(file_ids)} overviews")
        return overviews

    def build_overview_context(
        self,
        overviews: Dict[str, str],
        file_metadata: Optional[Dict[str, Dict]] = None
    ) -> str:
        """
        Build context string from multiple document overviews

        Args:
            overviews: Dict mapping file_id to overview text
            file_metadata: Optional dict mapping file_id to metadata (filename, etc.)

        Returns:
            str: Formatted context string for LLM prompt
        """
        if not overviews:
            return "[無可用文檔概述]"

        context_parts = []
        for i, (file_id, overview) in enumerate(overviews.items(), 1):
            # Get filename if available
            filename = "未知文件"
            if file_metadata and file_id in file_metadata:
                filename = file_metadata[file_id].get("filename", filename)

            context_parts.append(
                f"【文件 {i}: {filename}】\n"
                f"文件ID: {file_id}\n"
                f"概述: {overview}"
            )

        return "\n\n" + "=" * 50 + "\n\n".join(context_parts)


# Dependency injection helper
def get_document_overview_service(llm_client=None) -> DocumentOverviewService:
    """
    FastAPI dependency for Document Overview Service
    """
    from app.Providers.llm_provider.client import get_llm_provider

    if llm_client is None:
        llm_client = get_llm_provider()

    return DocumentOverviewService(llm_client=llm_client)
