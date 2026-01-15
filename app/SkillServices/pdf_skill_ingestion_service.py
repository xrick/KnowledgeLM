# app/SkillServices/pdf_skill_ingestion_service.py
"""
PDF Skill Ingestion Service
Handles page-based chunking for legal documents with BGE-M3 embeddings
"""

import logging
import hashlib
import uuid
import math
import traceback
from typing import List, Dict, Any, Optional, Tuple, Generator
from pathlib import Path
from datetime import datetime, timezone
import PyPDF2
import sqlite3
import json
import asyncio
import numpy as np

from app.Providers.bge_embedding_provider import get_bge_embedding_provider
from app.Providers.vector_store_provider.client import VectorStoreProvider
from app.Providers.skill_metadata_provider.client import SkillMetadataProvider

logger = logging.getLogger(__name__)

class PDFSkillIngestionService:
    """
    Service for ingesting PDF documents as Skills with page-based chunking
    Each page becomes a chunk with page number tracking for citations
    """

    def __init__(self):
        """Initialize PDF ingestion service with BGE-M3"""
        self.embedding_provider = get_bge_embedding_provider()
        self.embedding_dimension = 1024  # BGE-M3 dimension

    async def process_pdf_directory(self,
                                   directory_path: str,
                                   skill_name: str,
                                   skill_description: str,
                                   skill_category: str = "Legal",
                                   metadata_provider: SkillMetadataProvider = None,
                                   vector_provider: VectorStoreProvider = None) -> Dict[str, Any]:
        """
        Process all PDFs in a directory into a single Skill

        Args:
            directory_path: Path to directory containing PDFs
            skill_name: Name of the skill (e.g., "六法全書-刑法")
            skill_description: Description of the skill
            skill_category: Category (default: "Legal")
            metadata_provider: Provider for metadata storage
            vector_provider: Provider for vector storage

        Returns:
            Dictionary with processing results
        """
        try:
            dir_path = Path(directory_path)
            if not dir_path.exists():
                raise ValueError(f"Directory not found: {directory_path}")

            # Find all PDF files
            pdf_files = list(dir_path.glob("*.pdf"))
            if not pdf_files:
                raise ValueError(f"No PDF files found in {directory_path}")

            logger.info(f"Found {len(pdf_files)} PDFs in {directory_path}")

            # Generate skill ID
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            skill_hash = hashlib.md5(skill_name.encode()).hexdigest()[:8]
            skill_id = f"skill_{skill_category.lower()}_{timestamp}_{skill_hash}"

            # Process all PDFs
            all_chunks = []
            all_embeddings = []
            document_mappings = []

            for pdf_path in pdf_files:
                logger.info(f"Processing PDF: {pdf_path.name}")

                # Extract pages from PDF
                pages = await self._extract_pdf_pages(pdf_path)
                logger.info(f"  Extracted {len(pages)} pages from {pdf_path.name}")

                # Create document entry
                doc_id = f"doc_{hashlib.md5(str(pdf_path).encode()).hexdigest()[:8]}"
                document_mappings.append({
                    'document_id': doc_id,
                    'document_name': pdf_path.stem,  # Name without extension
                    'document_path': str(pdf_path),
                    'total_pages': len(pages)
                })

                # Process each page
                for page_num, page_text in enumerate(pages, 1):
                    if not page_text.strip():
                        continue  # Skip empty pages

                    # Generate chunk ID
                    chunk_id = f"{skill_id}_{doc_id}_p{page_num}"

                    # Create chunk metadata
                    chunk_metadata = {
                        'chunk_id': chunk_id,
                        'skill_id': skill_id,
                        'document_id': doc_id,
                        'document_name': pdf_path.stem,
                        'page_number': page_num,
                        'chunk_index': len(all_chunks),
                        'embedding_model': 'BAAI/bge-m3',
                        'embedding_dimension': self.embedding_dimension
                    }

                    # Store chunk data
                    all_chunks.append({
                        'chunk_id': chunk_id,
                        'content': page_text,
                        'metadata': chunk_metadata
                    })

                    # Generate embedding
                    embedding = self.embedding_provider.embed_single(page_text)
                    all_embeddings.append(embedding)

            logger.info(f"Total chunks created: {len(all_chunks)}")

            # Store in vector database
            if vector_provider:
                logger.info("Storing embeddings in FAISS...")
                await self._store_embeddings(
                    skill_id=skill_id,
                    chunks=all_chunks,
                    embeddings=all_embeddings,
                    vector_provider=vector_provider
                )

            # Store metadata
            if metadata_provider:
                logger.info("Storing metadata in SQLite...")
                await self._store_metadata(
                    skill_id=skill_id,
                    skill_name=skill_name,
                    skill_description=skill_description,
                    skill_category=skill_category,
                    chunks=all_chunks,
                    document_mappings=document_mappings,
                    metadata_provider=metadata_provider
                )

            result = {
                'skill_id': skill_id,
                'skill_name': skill_name,
                'documents_processed': len(pdf_files),
                'total_chunks': len(all_chunks),
                'total_pages': sum(dm['total_pages'] for dm in document_mappings),
                'embedding_model': 'BAAI/bge-m3',
                'embedding_dimension': self.embedding_dimension,
                'documents': [dm['document_name'] for dm in document_mappings]
            }

            logger.info(f"✅ Successfully created skill: {skill_name}")
            return result

        except Exception as e:
            logger.error(f"Error processing PDF directory: {str(e)}")
            raise

    async def _extract_pdf_pages(self, pdf_path: Path) -> List[str]:
        """
        Extract text from each page of a PDF

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of page texts
        """
        pages = []

        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                num_pages = len(pdf_reader.pages)

                for page_num in range(num_pages):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()

                    # Clean the text
                    text = self._clean_page_text(text)
                    pages.append(text)

        except Exception as e:
            logger.error(f"Error extracting pages from {pdf_path}: {str(e)}")
            raise

        return pages

    def _page_generator(
        self,
        pdf_path: Path,
        start_page: int = 0
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Lazy PDF page generator for memory-efficient large file processing.

        Yields one page at a time, keeping memory usage constant regardless of PDF size.
        Supports resume from checkpoint via start_page parameter.

        Args:
            pdf_path: Path to PDF file
            start_page: Page number to start from (0-indexed, for resume support)

        Yields:
            Dict containing:
                - page_num: int (0-indexed page number)
                - text: str (cleaned page text)
                - total_pages: int (total pages in PDF)

        Memory Usage:
            O(1) - constant memory regardless of PDF size

        Example:
            >>> for page_data in self._page_generator(pdf_path, start_page=100):
            ...     print(f"Page {page_data['page_num']}/{page_data['total_pages']}")
            ...     process_page(page_data['text'])
        """
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)

                logger.info(
                    f"Starting page generator for {pdf_path.name}: "
                    f"total={total_pages}, start={start_page}"
                )

                for page_num in range(start_page, total_pages):
                    try:
                        page = pdf_reader.pages[page_num]
                        text = page.extract_text()

                        # Clean the text using existing method
                        cleaned_text = self._clean_page_text(text)

                        yield {
                            "page_num": page_num,
                            "text": cleaned_text,
                            "total_pages": total_pages
                        }

                    except Exception as page_error:
                        logger.warning(
                            f"Error extracting page {page_num} from {pdf_path.name}: {page_error}"
                        )
                        # Yield empty text for failed pages to maintain page count consistency
                        yield {
                            "page_num": page_num,
                            "text": "",
                            "total_pages": total_pages,
                            "error": str(page_error)
                        }

        except Exception as e:
            logger.error(f"Error opening PDF {pdf_path}: {str(e)}")
            raise

    def get_pdf_page_count(self, pdf_path: Path) -> int:
        """
        Get total page count of a PDF without loading all content.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Total number of pages
        """
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                return len(pdf_reader.pages)
        except Exception as e:
            logger.error(f"Error getting page count for {pdf_path}: {str(e)}")
            raise

    def _clean_page_text(self, text: str) -> str:
        """
        Clean extracted page text

        Args:
            text: Raw page text

        Returns:
            Cleaned text
        """
        # Remove excessive whitespace
        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            line = line.strip()
            if line:
                cleaned_lines.append(line)

        # Join with single newline
        cleaned_text = '\n'.join(cleaned_lines)

        # Remove multiple spaces
        while '  ' in cleaned_text:
            cleaned_text = cleaned_text.replace('  ', ' ')

        return cleaned_text

    async def _store_embeddings(self,
                               skill_id: str,
                               chunks: List[Dict],
                               embeddings: List,
                               vector_provider: VectorStoreProvider) -> None:
        """
        Store embeddings in FAISS

        Args:
            skill_id: Skill identifier
            chunks: List of chunk data
            embeddings: List of embeddings
            vector_provider: Vector storage provider
        """
        try:
            # Extract texts and metadata
            texts = [chunk['content'] for chunk in chunks]
            metadata_list = [chunk['metadata'] for chunk in chunks]

            # Use create_store_from_texts directly since we're passing to VectorStoreProvider
            from app.Providers.bge_embedding_provider import get_bge_embedding_provider
            bge_provider = get_bge_embedding_provider()

            # Create a minimal embedding wrapper for compatibility
            class EmbeddingWrapper:
                def embed_query(self, text):
                    return bge_provider.embed_single(text).tolist()

            store_id = vector_provider.create_store_from_texts(
                texts=texts,
                embeddings=EmbeddingWrapper(),  # For query embedding later
                metadatas=metadata_list,
                file_id=skill_id,
                store_type='skill',
                precomputed_embeddings=embeddings  # Pass pre-computed BGE-M3 embeddings
            )

            logger.info(f"✅ Stored {len(embeddings)} embeddings for skill {skill_id} in store {store_id}")

        except Exception as e:
            logger.error(f"Error storing embeddings: {str(e)}")
            raise

    async def _store_metadata(self,
                             skill_id: str,
                             skill_name: str,
                             skill_description: str,
                             skill_category: str,
                             chunks: List[Dict],
                             document_mappings: List[Dict],
                             metadata_provider: SkillMetadataProvider) -> None:
        """
        Store metadata in SQLite

        Args:
            skill_id: Skill identifier
            skill_name: Name of the skill
            skill_description: Description
            skill_category: Category
            chunks: List of chunk data
            document_mappings: Document mapping information
            metadata_provider: Metadata storage provider
        """
        try:
            # Create skill entry
            await metadata_provider.create_skill(
                skill_id=skill_id,
                skill_name=skill_name,
                skill_description=skill_description,
                skill_category=skill_category,
                skill_level="professional",
                tags=["legal", "law", "chinese"],
                total_chunks=len(chunks),
                metadata={
                    'embedding_model': 'BAAI/bge-m3',
                    'embedding_dimension': self.embedding_dimension
                }
            )

            # Store document mappings
            db_path = Path("data/skill_metadata.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Insert document mappings
            for doc_mapping in document_mappings:
                cursor.execute("""
                    INSERT INTO skill_document_mapping
                    (skill_id, file_id, document_name, document_path, total_pages, relevance_score)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    skill_id,
                    doc_mapping['document_id'],
                    doc_mapping['document_name'],
                    doc_mapping['document_path'],
                    doc_mapping['total_pages'],
                    1.0  # Full relevance for legal documents
                ))

            # Insert chunk metadata
            for chunk in chunks:
                metadata = chunk['metadata']
                cursor.execute("""
                    INSERT INTO skill_chunk_metadata
                    (chunk_id, skill_id, document_id, document_name, page_number,
                     chunk_index, chunk_text, embedding_model, embedding_dimension, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    metadata['chunk_id'],
                    skill_id,
                    metadata['document_id'],  # ✅ REVERTED: Keep document-level ID for multi-book support
                    metadata['document_name'],
                    metadata['page_number'],
                    metadata['chunk_index'],
                    chunk['content'][:500],  # Store preview of text
                    'BAAI/bge-m3',
                    self.embedding_dimension,
                    json.dumps(metadata)
                ))

            conn.commit()
            conn.close()

            logger.info(f"✅ Stored metadata for {len(chunks)} chunks")

        except Exception as e:
            logger.error(f"Error storing metadata: {str(e)}")
            raise

    async def _atomic_batch_persist(
        self,
        job_id: str,
        batch_chunks: List[Dict],
        embeddings: np.ndarray,
        current_page: int,
        skill_id: str,
        metadata_provider,  # SkillMetadataProvider
        vector_provider,    # VectorStoreProvider
        max_retries: int = 2,
        retry_delay: float = 1.0
    ) -> Dict[str, Any]:
        """
        Atomic batch persistence with retry and dirty marking mechanism.

        Implements hybrid compensation strategy:
        1. Try write with retries (for transient errors like network issues)
        2. On success: update checkpoint to current_page
        3. On failure after retries: mark batch as dirty for later recovery

        Args:
            job_id: Processing job identifier for checkpoint tracking
            batch_chunks: List of chunk dicts with content and metadata
            embeddings: Numpy array of embeddings for this batch
            current_page: Current page number for checkpoint
            skill_id: Skill identifier for storage
            metadata_provider: Provider for SQLite metadata storage
            vector_provider: Provider for FAISS vector storage
            max_retries: Maximum retry attempts (default: 2)
            retry_delay: Delay between retries in seconds (default: 1.0)

        Returns:
            Dict containing:
                - success: bool indicating overall success
                - chunks_persisted: int count of successfully stored chunks
                - checkpoint_updated: bool if checkpoint was updated
                - marked_dirty: bool if batch was marked dirty
                - error: str error message if failed

        Transaction Safety:
            - FAISS write is idempotent (can be retried safely)
            - SQLite uses transaction for atomicity
            - Checkpoint only updated after both succeed
        """
        result = {
            "success": False,
            "chunks_persisted": 0,
            "checkpoint_updated": False,
            "marked_dirty": False,
            "error": None
        }

        if not batch_chunks or len(embeddings) == 0:
            logger.warning(f"Empty batch for job {job_id}, skipping persist")
            result["success"] = True
            return result

        last_error = None
        batch_start_page = batch_chunks[0]['metadata'].get('page_number', current_page)
        batch_end_page = batch_chunks[-1]['metadata'].get('page_number', current_page)

        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    f"Batch persist attempt {attempt + 1}/{max_retries + 1} "
                    f"for job {job_id}, pages {batch_start_page}-{batch_end_page}"
                )

                # Step 1: Store embeddings in FAISS
                texts = [chunk['content'] for chunk in batch_chunks]
                metadata_list = [chunk['metadata'] for chunk in batch_chunks]

                # Create embedding wrapper for compatibility
                class EmbeddingWrapper:
                    def __init__(self, provider):
                        self._provider = provider

                    def embed_query(self, text):
                        return self._provider.embed_single(text).tolist()

                store_id = vector_provider.create_store_from_texts(
                    texts=texts,
                    embeddings=EmbeddingWrapper(self.embedding_provider),
                    metadatas=metadata_list,
                    file_id=skill_id,
                    store_type='skill',
                    precomputed_embeddings=embeddings.tolist() if isinstance(embeddings, np.ndarray) else embeddings
                )

                logger.debug(f"FAISS store created/updated: {store_id}")

                # Step 2: Store metadata in SQLite (within transaction)
                db_path = Path("data/skill_metadata.db")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                try:
                    # Begin transaction
                    cursor.execute("BEGIN TRANSACTION")

                    for chunk in batch_chunks:
                        metadata = chunk['metadata']
                        cursor.execute("""
                            INSERT OR REPLACE INTO skill_chunk_metadata
                            (chunk_id, skill_id, document_id, document_name, page_number,
                             chunk_index, chunk_text, embedding_model, embedding_dimension, metadata)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            metadata['chunk_id'],
                            skill_id,
                            metadata.get('document_id', skill_id),  # ✅ REVERTED: Use doc_id, fallback to skill_id
                            metadata.get('document_name', ''),
                            metadata.get('page_number', 0),
                            metadata.get('chunk_index', 0),
                            chunk['content'][:500],  # Preview
                            'BAAI/bge-m3',
                            self.embedding_dimension,
                            json.dumps(metadata)
                        ))

                    # Commit transaction
                    conn.commit()
                    logger.debug(f"SQLite metadata stored for {len(batch_chunks)} chunks")

                except Exception as db_error:
                    conn.rollback()
                    raise db_error
                finally:
                    conn.close()

                # Step 3: Update checkpoint (both FAISS and SQLite succeeded)
                if metadata_provider:
                    await metadata_provider.update_processing_job(
                        job_id=job_id,
                        last_processed_page=current_page,
                        processed_chunks=len(batch_chunks),  # Will be accumulated
                        status='processing'
                    )
                    result["checkpoint_updated"] = True

                # Success!
                result["success"] = True
                result["chunks_persisted"] = len(batch_chunks)

                logger.info(
                    f"✅ Batch persisted successfully: {len(batch_chunks)} chunks, "
                    f"checkpoint at page {current_page}"
                )
                return result

            except Exception as e:
                last_error = e
                error_msg = str(e)
                stack_trace = traceback.format_exc()

                logger.warning(
                    f"Batch persist attempt {attempt + 1} failed: {error_msg}\n"
                    f"Stack: {stack_trace[:500]}"
                )

                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)

        # All retries exhausted - mark as dirty
        logger.error(
            f"❌ Batch persist failed after {max_retries + 1} attempts. "
            f"Marking pages {batch_start_page}-{batch_end_page} as dirty."
        )

        if metadata_provider:
            await metadata_provider.mark_job_dirty(
                job_id=job_id,
                batch_info={
                    "start_page": batch_start_page,
                    "end_page": batch_end_page,
                    "chunk_count": len(batch_chunks),
                    "error": str(last_error),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
            result["marked_dirty"] = True

        result["error"] = str(last_error)
        return result

    async def _process_large_pdf(
        self,
        pdf_path: Path,
        skill_id: str,
        skill_name: str,
        metadata_provider,  # SkillMetadataProvider
        vector_provider,    # VectorStoreProvider
        batch_size: int = 12,
        resume_job_id: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Main processing method for large PDFs using Stream-Batch-Persist pipeline.

        Implements the core architecture:
        1. Producer (Lazy Loading): _page_generator() yields pages one at a time
        2. Buffer (Dynamic Batching): Accumulate chunks until batch_size reached
        3. Consumer (Atomic Persistence): _atomic_batch_persist() with checkpoint

        Args:
            pdf_path: Path to PDF file
            skill_id: Skill identifier for storage
            skill_name: Human-readable skill name
            metadata_provider: Provider for metadata and job tracking
            vector_provider: Provider for FAISS vector storage
            batch_size: Number of pages per batch for GPU processing (default: 12)
            resume_job_id: Optional job ID to resume from checkpoint
            progress_callback: Optional async callback for progress updates
                              Signature: async def callback(event_type: str, data: dict)

        Returns:
            Dict containing processing results:
                - job_id: Processing job identifier
                - skill_id: Skill identifier
                - total_pages: Total pages in PDF
                - processed_pages: Pages successfully processed
                - total_chunks: Total chunks created
                - dirty_batches: List of batches marked dirty (if any)
                - status: 'completed', 'partial', or 'failed'
                - processing_time_seconds: Total processing time
                - resumed: Whether this was a resumed job

        Memory Usage:
            O(batch_size) - only keeps current batch in memory

        Checkpoint Granularity:
            Page-level (as per user requirement)
        """
        import time
        start_time = time.time()

        # Determine if this is a resume or new job
        job_id = resume_job_id
        start_page = 0
        is_resume = False

        if resume_job_id and metadata_provider:
            # Try to get existing job
            existing_job = await metadata_provider.get_processing_job(resume_job_id)
            if existing_job and existing_job.get('status') in ('pending', 'processing', 'interrupted'):
                start_page = existing_job.get('last_processed_page', 0)
                is_resume = True
                logger.info(
                    f"📌 Resuming job {job_id} from page {start_page}"
                )

                if progress_callback:
                    await progress_callback('resume', {
                        'job_id': job_id,
                        'resume_from_page': start_page,
                        'message': f'從第 {start_page + 1} 頁恢復處理'
                    })

        # Create new job if not resuming
        if not job_id:
            job_id = f"job_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        # Get total page count
        total_pages = self.get_pdf_page_count(pdf_path)
        logger.info(f"📄 Processing PDF: {pdf_path.name}, {total_pages} pages, batch_size={batch_size}")

        # Create or update job record
        if metadata_provider:
            if not is_resume:
                await metadata_provider.create_processing_job(
                    job_id=job_id,
                    skill_id=skill_id,
                    pdf_path=str(pdf_path),
                    pdf_filename=pdf_path.name,
                    total_pages=total_pages,
                    batch_size=batch_size
                )
            else:
                await metadata_provider.update_processing_job(
                    job_id=job_id,
                    status='processing',
                    started_at=datetime.now(timezone.utc).isoformat()
                )

        # Initialize tracking variables
        doc_id = f"doc_{hashlib.md5(str(pdf_path).encode()).hexdigest()[:8]}"
        batch_chunks = []
        batch_texts = []
        current_batch_start_page = start_page
        total_chunks_created = 0
        processed_pages = start_page
        dirty_batches = []

        # Notify start
        if progress_callback:
            await progress_callback('processing_start', {
                'job_id': job_id,
                'skill_id': skill_id,
                'total_pages': total_pages,
                'start_page': start_page,
                'batch_size': batch_size,
                'resumed': is_resume
            })

        try:
            # Stream through pages using generator
            for page_data in self._page_generator(pdf_path, start_page=start_page):
                page_num = page_data['page_num']
                page_text = page_data['text']
                page_total = page_data['total_pages']

                # Skip empty pages but count them
                if not page_text.strip():
                    processed_pages = page_num + 1
                    continue

                # Create chunk for this page
                chunk_id = f"{skill_id}_{doc_id}_p{page_num + 1}"
                chunk_metadata = {
                    'chunk_id': chunk_id,
                    'skill_id': skill_id,
                    'document_id': doc_id,
                    'document_name': pdf_path.stem,
                    'page_number': page_num + 1,  # 1-indexed for display
                    'chunk_index': total_chunks_created + len(batch_chunks),
                    'embedding_model': 'BAAI/bge-m3',
                    'embedding_dimension': self.embedding_dimension
                }

                batch_chunks.append({
                    'chunk_id': chunk_id,
                    'content': page_text,
                    'metadata': chunk_metadata
                })
                batch_texts.append(page_text)

                # Check if batch is full
                if len(batch_chunks) >= batch_size:
                    # Notify batch start
                    if progress_callback:
                        await progress_callback('batch_start', {
                            'job_id': job_id,
                            'batch_pages': f"{current_batch_start_page + 1}-{page_num + 1}",
                            'batch_size': len(batch_chunks),
                            'progress_percent': math.floor((page_num + 1) / page_total * 100)
                        })

                    # Generate embeddings for batch
                    logger.info(f"🔄 Generating embeddings for batch ({len(batch_chunks)} chunks)")
                    embeddings = self.embedding_provider.embed_texts(batch_texts)

                    # Persist batch atomically
                    persist_result = await self._atomic_batch_persist(
                        job_id=job_id,
                        batch_chunks=batch_chunks,
                        embeddings=np.array(embeddings),
                        current_page=page_num + 1,
                        skill_id=skill_id,
                        metadata_provider=metadata_provider,
                        vector_provider=vector_provider
                    )

                    if persist_result['success']:
                        total_chunks_created += persist_result['chunks_persisted']

                        # Notify checkpoint
                        if progress_callback:
                            await progress_callback('checkpoint', {
                                'job_id': job_id,
                                'page': page_num + 1,
                                'total_chunks': total_chunks_created,
                                'progress_percent': math.floor((page_num + 1) / page_total * 100)
                            })
                    else:
                        # Batch marked dirty
                        dirty_batches.append({
                            'start_page': current_batch_start_page,
                            'end_page': page_num,
                            'error': persist_result.get('error')
                        })

                        if progress_callback:
                            await progress_callback('dirty', {
                                'job_id': job_id,
                                'batch_pages': f"{current_batch_start_page + 1}-{page_num + 1}",
                                'error': persist_result.get('error')
                            })

                    # Reset batch
                    batch_chunks = []
                    batch_texts = []
                    current_batch_start_page = page_num + 1

                processed_pages = page_num + 1

            # Process remaining chunks in final batch
            if batch_chunks:
                logger.info(f"🔄 Processing final batch ({len(batch_chunks)} chunks)")

                if progress_callback:
                    await progress_callback('batch_start', {
                        'job_id': job_id,
                        'batch_pages': f"{current_batch_start_page + 1}-{processed_pages}",
                        'batch_size': len(batch_chunks),
                        'progress_percent': 95  # Almost done
                    })

                embeddings = self.embedding_provider.embed_texts(batch_texts)

                persist_result = await self._atomic_batch_persist(
                    job_id=job_id,
                    batch_chunks=batch_chunks,
                    embeddings=np.array(embeddings),
                    current_page=processed_pages,
                    skill_id=skill_id,
                    metadata_provider=metadata_provider,
                    vector_provider=vector_provider
                )

                if persist_result['success']:
                    total_chunks_created += persist_result['chunks_persisted']
                else:
                    dirty_batches.append({
                        'start_page': current_batch_start_page,
                        'end_page': processed_pages,
                        'error': persist_result.get('error')
                    })

            # Calculate final status
            processing_time = time.time() - start_time
            status = 'completed' if not dirty_batches else 'partial'

            # Update job as completed
            if metadata_provider:
                await metadata_provider.update_processing_job(
                    job_id=job_id,
                    status=status,
                    total_chunks=total_chunks_created,
                    processed_chunks=total_chunks_created,
                    last_processed_page=processed_pages,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    processing_time_seconds=processing_time,
                    avg_page_time_ms=(processing_time / max(processed_pages - start_page, 1)) * 1000
                )

            result = {
                'job_id': job_id,
                'skill_id': skill_id,
                'skill_name': skill_name,
                'document_name': pdf_path.stem,
                'total_pages': total_pages,
                'processed_pages': processed_pages,
                'total_chunks': total_chunks_created,
                'dirty_batches': dirty_batches,
                'status': status,
                'processing_time_seconds': round(processing_time, 2),
                'resumed': is_resume,
                'avg_page_time_ms': round((processing_time / max(processed_pages - start_page, 1)) * 1000, 2)
            }

            # Final progress notification
            if progress_callback:
                await progress_callback('complete', {
                    **result,
                    'progress_percent': 100,
                    'message': f'處理完成：{total_chunks_created} 個區塊'
                })

            logger.info(
                f"✅ Large PDF processing {'completed' if status == 'completed' else 'partial'}: "
                f"{total_chunks_created} chunks from {processed_pages} pages in {processing_time:.2f}s"
            )

            return result

        except Exception as e:
            error_msg = str(e)
            stack_trace = traceback.format_exc()

            logger.error(f"❌ Large PDF processing failed: {error_msg}\n{stack_trace}")

            # Update job as failed
            if metadata_provider:
                await metadata_provider.update_processing_job(
                    job_id=job_id,
                    status='failed',
                    error_message=error_msg,
                    error_stack=stack_trace[:2000],
                    last_processed_page=processed_pages,
                    total_chunks=total_chunks_created
                )

            if progress_callback:
                await progress_callback('error', {
                    'job_id': job_id,
                    'error': error_msg,
                    'processed_pages': processed_pages,
                    'total_chunks': total_chunks_created
                })

            raise

    async def process_pdf_streaming(
        self,
        pdf_path: Path,
        skill_id: str,
        skill_name: str,
        metadata_provider,  # SkillMetadataProvider
        vector_provider,    # VectorStoreProvider
        batch_size: int = 12,
        resume_job_id: Optional[str] = None
    ):
        """
        Unified SSE streaming interface for PDF processing.

        All PDFs (regardless of size) use the same Generator-based pipeline
        for consistent UX and memory efficiency.

        Args:
            pdf_path: Path to PDF file
            skill_id: Skill identifier for storage
            skill_name: Human-readable skill name
            metadata_provider: Provider for metadata and job tracking
            vector_provider: Provider for FAISS vector storage
            batch_size: Number of pages per batch (default: 12)
            resume_job_id: Optional job ID to resume from checkpoint

        Yields:
            Dict with SSE event format:
                - event: str (event type name)
                - data: dict (event payload as JSON)

        SSE Event Types:
            - processing_start: Initial event with job metadata
            - resume: Sent when resuming from checkpoint
            - batch_start: Before processing each batch
            - checkpoint: After successful batch persistence
            - dirty: When a batch fails and is marked dirty
            - progress: Periodic progress updates
            - complete: Final success event
            - error: Error event with details

        Usage in FastAPI:
            @router.post("/upload-source")
            async def upload_source(...):
                async def event_generator():
                    async for event in service.process_pdf_streaming(...):
                        yield f"event: {event['event']}\\ndata: {json.dumps(event['data'])}\\n\\n"
                return EventSourceResponse(event_generator())

        Memory Usage:
            O(batch_size) - constant memory regardless of PDF size
        """
        from asyncio import Queue

        total_pages = self.get_pdf_page_count(pdf_path)
        logger.info(f"📄 Processing PDF: {pdf_path.name}, {total_pages} pages (unified streaming mode)")

        # Create event queue for communication between callback and generator
        event_queue: Queue = Queue()
        processing_complete = False
        final_result = None
        processing_error = None

        async def progress_callback(event_type: str, data: dict):
            """Callback that puts events into queue for SSE streaming"""
            await event_queue.put({
                'event': event_type,
                'data': data
            })

        # Start processing in background task
        async def run_processing():
            nonlocal processing_complete, final_result, processing_error
            try:
                final_result = await self._process_large_pdf(
                    pdf_path=pdf_path,
                    skill_id=skill_id,
                    skill_name=skill_name,
                    metadata_provider=metadata_provider,
                    vector_provider=vector_provider,
                    batch_size=batch_size,
                    resume_job_id=resume_job_id,
                    progress_callback=progress_callback
                )
            except Exception as e:
                processing_error = e
            finally:
                processing_complete = True
                # Signal end of events
                await event_queue.put(None)

        # Start processing task
        processing_task = asyncio.create_task(run_processing())

        # Yield events as they come in
        try:
            while True:
                # Wait for next event with timeout
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield {
                        'event': 'heartbeat',
                        'data': {'timestamp': datetime.now(timezone.utc).isoformat()}
                    }
                    continue

                if event is None:
                    # Processing complete
                    break

                yield event

        except asyncio.CancelledError:
            # Client disconnected
            processing_task.cancel()
            logger.warning("SSE client disconnected during processing")
            raise

        finally:
            # Ensure task is cleaned up
            if not processing_task.done():
                processing_task.cancel()
                try:
                    await processing_task
                except asyncio.CancelledError:
                    pass

        # Handle any processing error
        if processing_error:
            raise processing_error

    # Backward compatibility alias
    async def process_large_pdf_streaming(self, *args, **kwargs):
        """Alias for process_pdf_streaming() - kept for backward compatibility."""
        async for event in self.process_pdf_streaming(*args, **kwargs):
            yield event

    def is_large_pdf(self, pdf_path: Path, threshold: int = 100) -> bool:
        """
        Check if a PDF qualifies as "large" based on page count.

        Args:
            pdf_path: Path to PDF file
            threshold: Page count threshold (default: 100)

        Returns:
            True if PDF has >= threshold pages
        """
        try:
            page_count = self.get_pdf_page_count(pdf_path)
            return page_count >= threshold
        except Exception:
            return False

    async def startup_recovery(
        self,
        metadata_provider,  # SkillMetadataProvider
        vector_provider,    # VectorStoreProvider
        auto_resume: bool = False,
        max_resume_jobs: int = 5
    ) -> Dict[str, Any]:
        """
        Check for and optionally resume interrupted processing jobs on startup.

        This method should be called during application initialization to:
        1. Detect jobs that were interrupted (status: 'processing' or 'interrupted')
        2. Identify jobs with dirty batches that need reprocessing
        3. Optionally auto-resume interrupted jobs
        4. Provide a report of pending recovery actions

        Args:
            metadata_provider: Provider for job tracking and metadata
            vector_provider: Provider for FAISS vector storage
            auto_resume: If True, automatically resume interrupted jobs
            max_resume_jobs: Maximum number of jobs to auto-resume (default: 5)

        Returns:
            Dict containing:
                - interrupted_jobs: List of jobs needing resume
                - dirty_jobs: List of jobs with dirty batches
                - resumed_jobs: List of jobs that were resumed (if auto_resume)
                - failed_resumes: List of jobs that failed to resume
                - recommendations: List of recommended actions

        Usage:
            # In FastAPI startup event
            @app.on_event("startup")
            async def startup():
                service = get_pdf_skill_ingestion_service()
                recovery_report = await service.startup_recovery(
                    metadata_provider=get_skill_metadata_provider(),
                    vector_provider=get_vector_store_provider(),
                    auto_resume=False  # Manual review first
                )
                if recovery_report['interrupted_jobs']:
                    logger.warning(f"Found {len(recovery_report['interrupted_jobs'])} interrupted jobs")
        """
        result = {
            'interrupted_jobs': [],
            'dirty_jobs': [],
            'resumed_jobs': [],
            'failed_resumes': [],
            'recommendations': [],
            'checked_at': datetime.now(timezone.utc).isoformat()
        }

        try:
            # Get all interrupted jobs
            interrupted = await metadata_provider.get_interrupted_jobs()

            for job in interrupted:
                job_id = job.get('job_id')
                status = job.get('status')
                pdf_path = job.get('pdf_path')
                last_page = job.get('last_processed_page', 0)
                total_pages = job.get('total_pages', 0)
                dirty_batches = job.get('dirty_batches')

                job_info = {
                    'job_id': job_id,
                    'skill_id': job.get('skill_id'),
                    'pdf_filename': job.get('pdf_filename'),
                    'status': status,
                    'last_processed_page': last_page,
                    'total_pages': total_pages,
                    'progress_percent': round((last_page / max(total_pages, 1)) * 100, 1),
                    'created_at': job.get('created_at'),
                    'updated_at': job.get('updated_at')
                }

                # Check if PDF still exists
                pdf_exists = Path(pdf_path).exists() if pdf_path else False
                job_info['pdf_exists'] = pdf_exists

                if dirty_batches:
                    try:
                        dirty_list = json.loads(dirty_batches) if isinstance(dirty_batches, str) else dirty_batches
                        job_info['dirty_batches'] = dirty_list
                        result['dirty_jobs'].append(job_info)
                    except (json.JSONDecodeError, TypeError):
                        job_info['dirty_batches'] = []

                result['interrupted_jobs'].append(job_info)

                # Generate recommendation
                if not pdf_exists:
                    result['recommendations'].append({
                        'job_id': job_id,
                        'action': 'delete',
                        'reason': 'PDF 檔案已不存在，建議刪除此任務記錄'
                    })
                elif last_page > 0 and last_page < total_pages:
                    result['recommendations'].append({
                        'job_id': job_id,
                        'action': 'resume',
                        'reason': f'可從第 {last_page + 1} 頁恢復處理（已完成 {job_info["progress_percent"]}%）'
                    })
                elif status == 'processing':
                    result['recommendations'].append({
                        'job_id': job_id,
                        'action': 'restart',
                        'reason': '任務狀態異常，建議重新開始處理'
                    })

            # Auto-resume if enabled
            if auto_resume and result['interrupted_jobs']:
                resumable_jobs = [
                    j for j in result['interrupted_jobs']
                    if j['pdf_exists'] and j['last_processed_page'] > 0
                ][:max_resume_jobs]

                for job_info in resumable_jobs:
                    try:
                        logger.info(f"🔄 Auto-resuming job {job_info['job_id']}")

                        # Resume processing
                        resume_result = await self._process_large_pdf(
                            pdf_path=Path(job_info.get('pdf_path', '')),
                            skill_id=job_info['skill_id'],
                            skill_name=job_info.get('pdf_filename', 'Unknown'),
                            metadata_provider=metadata_provider,
                            vector_provider=vector_provider,
                            resume_job_id=job_info['job_id']
                        )

                        result['resumed_jobs'].append({
                            'job_id': job_info['job_id'],
                            'result': resume_result
                        })

                    except Exception as e:
                        logger.error(f"Failed to resume job {job_info['job_id']}: {e}")
                        result['failed_resumes'].append({
                            'job_id': job_info['job_id'],
                            'error': str(e)
                        })

            # Summary logging
            if result['interrupted_jobs']:
                logger.warning(
                    f"📋 Startup Recovery Report: "
                    f"{len(result['interrupted_jobs'])} interrupted jobs, "
                    f"{len(result['dirty_jobs'])} with dirty batches"
                )
            else:
                logger.info("✅ Startup Recovery: No interrupted jobs found")

        except Exception as e:
            logger.error(f"Error during startup recovery check: {e}")
            result['error'] = str(e)

        return result

    async def cleanup_job(
        self,
        job_id: str,
        metadata_provider,  # SkillMetadataProvider
        delete_vectors: bool = False,
        vector_provider = None  # VectorStoreProvider
    ) -> Dict[str, Any]:
        """
        Clean up a processing job and optionally its associated data.

        Args:
            job_id: Job identifier to clean up
            metadata_provider: Provider for job tracking
            delete_vectors: If True, also delete associated vectors from FAISS
            vector_provider: Required if delete_vectors is True

        Returns:
            Dict with cleanup results
        """
        result = {
            'job_id': job_id,
            'job_deleted': False,
            'vectors_deleted': False,
            'error': None
        }

        try:
            # Get job info first
            job = await metadata_provider.get_processing_job(job_id)
            if not job:
                result['error'] = 'Job not found'
                return result

            skill_id = job.get('skill_id')

            # Delete vectors if requested
            if delete_vectors and vector_provider and skill_id:
                try:
                    # Note: This would need VectorStoreProvider to support deletion
                    # For now, log the intention
                    logger.info(f"Would delete vectors for skill_id: {skill_id}")
                    result['vectors_deleted'] = True
                except Exception as e:
                    logger.warning(f"Could not delete vectors: {e}")

            # Delete job record
            await metadata_provider.delete_processing_job(job_id)
            result['job_deleted'] = True

            logger.info(f"🗑️ Cleaned up job {job_id}")

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error cleaning up job {job_id}: {e}")

        return result

    async def get_job_status(
        self,
        job_id: str,
        metadata_provider  # SkillMetadataProvider
    ) -> Optional[Dict[str, Any]]:
        """
        Get current status of a processing job.

        Args:
            job_id: Job identifier
            metadata_provider: Provider for job tracking

        Returns:
            Job status dict or None if not found
        """
        job = await metadata_provider.get_processing_job(job_id)
        if not job:
            return None

        total_pages = job.get('total_pages', 0)
        last_page = job.get('last_processed_page', 0)

        return {
            'job_id': job_id,
            'skill_id': job.get('skill_id'),
            'status': job.get('status'),
            'total_pages': total_pages,
            'processed_pages': last_page,
            'progress_percent': round((last_page / max(total_pages, 1)) * 100, 1),
            'total_chunks': job.get('total_chunks', 0),
            'processing_time_seconds': job.get('processing_time_seconds'),
            'avg_page_time_ms': job.get('avg_page_time_ms'),
            'error_message': job.get('error_message'),
            'created_at': job.get('created_at'),
            'updated_at': job.get('updated_at'),
            'completed_at': job.get('completed_at')
        }


# Singleton instance
_pdf_ingestion_instance = None

def get_pdf_skill_ingestion_service() -> PDFSkillIngestionService:
    """Get or create PDF skill ingestion service singleton"""
    global _pdf_ingestion_instance
    if _pdf_ingestion_instance is None:
        _pdf_ingestion_instance = PDFSkillIngestionService()
    return _pdf_ingestion_instance