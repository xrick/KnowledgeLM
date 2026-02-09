# app/api/v1/endpoints/upload.py
"""
Upload API Endpoint

Handles PDF file uploads with text extraction, hierarchical chunking, and vectorization.

POST /api/v1/upload - Upload single PDF file for processing
"""

import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings

# Application imports
from app.models.schemas import ErrorResponse, UploadResponse
from app.Providers.embedding_provider.client import get_embedding_provider
from app.Providers.file_metadata_provider.client import (
    FileMetadataProvider,
    get_file_metadata_provider,
)
from app.Services.document_overview_service import (
    DocumentOverviewService,
    get_document_overview_service,
)
from app.Services.input_data_handle_service import (
    InputDataHandleService,
    get_input_data_service,
)
from app.Services.retrieval_service import RetrievalService, get_retrieval_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


# =============================================================================
# Helper Functions
# =============================================================================


def save_uploaded_file(file_content: bytes, filename: str, file_id: str) -> Path:
    """
    Save uploaded file content to disk

    Args:
        file_content: Binary file content
        filename: Original filename (for extension extraction)
        file_id: Generated file identifier

    Returns:
        Path to saved file

    Example:
        >>> file_path = save_uploaded_file(content, "doc.pdf", "file_abc123")
    """
    # Ensure upload directory exists
    upload_dir = Path(settings.PDF_UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save with file_id as filename
    file_extension = Path(filename).suffix
    file_path = upload_dir / f"{file_id}{file_extension}"

    # Write binary content directly
    with file_path.open("wb") as buffer:
        buffer.write(file_content)

    logger.info(f"Saved uploaded file: {file_path} ({len(file_content)} bytes)")
    return file_path


async def process_and_embed_file(
    file_content: bytes,
    filename: str,
    user_id: str,
    input_service: InputDataHandleService,
    retrieval_service: RetrievalService,
    file_metadata_provider: FileMetadataProvider,
    embedding_provider,
    overview_service: Optional[DocumentOverviewService] = None,
) -> dict:
    """
    Process file and generate embeddings (Multi-User Support)

    Workflow:
    1. Extract text from PDF
    2. Chunk text using hierarchical strategy
    3. Generate embeddings for chunks
    4. Store in vector database
    5. Update file metadata with user ownership

    Args:
        file_content: Binary file content
        filename: Original filename
        user_id: User identifier (UUID format)
        input_service: Input data handle service
        retrieval_service: Retrieval service for embedding
        file_metadata_provider: File metadata provider
        embedding_provider: Embedding provider

    Returns:
        Processing result dict with user_id

    Example:
        >>> result = await process_and_embed_file(
        ...     content, "doc.pdf", "550e8400-...", ...
        ... )
    """
    try:
        # Step 1: Process file (extract + chunk) with unique file_id generation
        process_result = await input_service.process_file(
            file_content,
            filename,
            file_metadata_provider,  # Pass provider for collision detection
        )

        file_id = process_result["file_id"]
        chunks = process_result["chunks"]
        chunk_count = process_result["chunk_count"]

        logger.info(
            f"File processed: {file_id}, {chunk_count} chunks "
            f"(strategy: {process_result['chunking_strategy']})"
        )

        # Step 2: Store file metadata in SQLite (with user ownership)
        if settings.CHUNKING_STRATEGY == "recursive":
            chunk_size = settings.CHUNK_SIZE
        elif settings.CHUNKING_STRATEGY == "page_based":
            chunk_size = settings.PAGE_BASED_CHUNK_SIZE
        else:
            chunk_size = None  # For hierarchical, sizes vary

        await file_metadata_provider.add_file(
            file_id=file_id,
            filename=filename,
            file_type="pdf",
            file_size=process_result["file_size"],
            user_id=user_id,  # NEW: Associate file with user
            chunk_count=chunk_count,
            milvus_partition=f"file_{file_id}",
            metadata={
                "chunking_strategy": process_result["chunking_strategy"],
                "chunk_sizes": settings.CHUNK_SIZE
                if settings.CHUNKING_STRATEGY == "recursive"
                else None,
            },
        )

        # Step 3: Extract chunk texts and metadata for embedding
        chunk_texts = [chunk["content"] for chunk in chunks]
        chunk_metadata = [chunk["metadata"] for chunk in chunks]

        # Step 4: Add chunks to vector store (with embeddings)
        store_id = await retrieval_service.add_document_chunks(
            file_id=file_id, chunks=chunk_texts, metadata=chunk_metadata
        )

        logger.info(f"Embeddings generated and stored: {store_id}")

        # Step 5: Update embedding status
        await file_metadata_provider.update_embedding_status(file_id, "completed")

        # Step 6: Generate and store document overview (for better retrieval)
        if overview_service:
            try:
                overview = await overview_service.generate_overview(
                    file_id=file_id, chunks=chunk_texts, filename=filename
                )
                await overview_service.store_overview(
                    file_metadata_provider=file_metadata_provider,
                    file_id=file_id,
                    overview=overview,
                )
                logger.info(f"Document overview generated and stored for {file_id}")
            except Exception as overview_error:
                # Overview generation is non-critical, log error but continue
                logger.warning(
                    f"Failed to generate overview for {file_id}: {overview_error}"
                )

        return {
            "file_id": file_id,
            "filename": filename,
            "file_size": process_result["file_size"],
            "chunk_count": chunk_count,
            "embedding_status": "completed",
            "chunking_strategy": process_result["chunking_strategy"],
        }

    except Exception as e:
        logger.error(f"File processing failed: {str(e)}")
        # Update status to failed if file_id exists
        if "file_id" in locals():
            try:
                await file_metadata_provider.update_embedding_status(file_id, "failed")
            except:
                pass
        raise


# =============================================================================
# API Endpoints
# =============================================================================


@router.post(
    "",
    response_model=UploadResponse,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Invalid file or validation error",
        },
        500: {"model": ErrorResponse, "description": "Server error during processing"},
    },
    summary="Upload PDF file for RAG indexing",
    description="""
    Upload a single PDF file for processing with hierarchical chunking and embedding generation.

    **Workflow**:
    1. Validate PDF file (type, size, content)
    2. Extract text using PyPDF2
    3. Chunk text using configured strategy (hierarchical or recursive)
    4. Generate embeddings using HuggingFace model
    5. Store embeddings in Milvus vector database
    6. Save file metadata to SQLite

    **Chunking Strategy**:
    - **Hierarchical Indexing** (default): Multi-level chunks with parent-child relationships
      - Parent chunks (2000 chars): Broad context
      - Child chunks (1000 chars): Retrieval targets
      - Grandchild chunks (500 chars): Precision matching
    - **Recursive** (fallback): Standard character-based splitting

    **Constraints**:
    - Max file size: 50MB
    - Supported format: PDF only
    - Processing time: ~1-5 seconds per MB
    """,
)
async def upload_pdf(
    file: UploadFile = File(..., description="PDF file to upload"),
    user_id: Optional[str] = Header(
        None,
        alias="X-User-ID",
        description="User UUID (optional, uses default if not provided)",
    ),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    input_service: InputDataHandleService = Depends(get_input_data_service),
    file_metadata_provider: FileMetadataProvider = Depends(get_file_metadata_provider),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    embedding_provider=Depends(get_embedding_provider),
    overview_service: DocumentOverviewService = Depends(get_document_overview_service),
):
    """
    Upload PDF file for processing and indexing (Multi-User Support)

    Args:
        file: Uploaded PDF file
        user_id: User identifier (UUID v4 format, required via X-User-ID header)
        background_tasks: FastAPI background tasks for async processing
        input_service: Input data handle service (dependency injection)
        file_metadata_provider: File metadata provider (dependency injection)
        retrieval_service: Retrieval service (dependency injection)
        embedding_provider: Embedding provider (dependency injection)

    Returns:
        UploadResponse with file_id, filename, chunk_count, status

    Raises:
        HTTPException: 400 for validation errors, 500 for processing errors

    Example:
        ```bash
        curl -X POST "http://localhost:8000/api/v1/upload" \\
          -H "X-User-ID: 550e8400-e29b-41d4-a716-446655440000" \\
          -F "file=@document.pdf"
        ```
    """
    # Use default user if not provided
    import re

    if user_id is None:
        if settings.DEFAULT_USER_ENABLED:
            user_id = settings.DEFAULT_USER_ID
            logger.info(f"Using default user_id: {user_id}")
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "ValidationError",
                    "message": "X-User-ID header is required",
                    "details": {
                        "hint": "Provide X-User-ID header with a valid UUID v4"
                    },
                },
            )

    # Validate user_id format (UUID v4)
    UUID_PATTERN = (
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    if not re.match(UUID_PATTERN, user_id, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "ValidationError",
                "message": "Invalid user_id format. Must be UUID v4.",
                "details": {
                    "user_id": user_id,
                    "expected_format": "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx",
                },
            },
        )
    try:
        # Validate file extension
        file_ext = Path(file.filename).suffix.lower().lstrip(".")
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "ValidationError",
                    "message": f"不支援的檔案格式: '.{file_ext}'。支援格式: {', '.join(settings.ALLOWED_EXTENSIONS)}",
                    "details": {"filename": file.filename},
                },
            )

        # Read file content
        file_content = await file.read()

        # Validate file (uses InputDataHandleService validation)
        is_valid, error_msg = input_service.validate_file(file_content, file.filename)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "ValidationError",
                    "message": error_msg,
                    "details": {"filename": file.filename},
                },
            )

        # Process file and generate embeddings (with user ownership)
        result = await process_and_embed_file(
            file_content=file_content,
            filename=file.filename,
            user_id=user_id,  # NEW: Pass user_id for ownership tracking
            input_service=input_service,
            retrieval_service=retrieval_service,
            file_metadata_provider=file_metadata_provider,
            embedding_provider=embedding_provider,
            overview_service=overview_service,  # Generate document overview
        )

        # Save file to disk using the already-read content
        file_path = save_uploaded_file(file_content, file.filename, result["file_id"])

        logger.info(
            f"File upload completed: {result['file_id']} "
            f"({result['chunk_count']} chunks, {result['chunking_strategy']} strategy)"
        )

        # Return response
        return UploadResponse(
            file_id=result["file_id"],
            filename=result["filename"],
            file_size=result["file_size"],
            chunk_count=result["chunk_count"],
            embedding_status=result["embedding_status"],
            message=f"File uploaded and indexed successfully using {result['chunking_strategy']} chunking",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload endpoint error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "ProcessingError",
                "message": f"Failed to process file: {str(e)}",
                "details": {},
            },
        )


# =============================================================================
# SSE Streaming Upload Endpoint
# =============================================================================


def create_upload_sse_event(event_type: str, data: dict) -> dict:
    """
    Create SSE event dict for upload progress streaming.

    Uses the same format as skills.py create_upload_sse_event() to ensure
    frontend consistency across Skill-Based and File-Based systems.

    Args:
        event_type: Event type string (start, progress, checkpoint, complete, error)
        data: Event data dict

    Returns:
        SSE event dict with 'event' and 'data' keys
    """
    return {"event": event_type, "data": json.dumps(data, ensure_ascii=False)}


async def process_file_streaming(
    file_content: bytes,
    filename: str,
    user_id: str,
    input_service: InputDataHandleService,
    retrieval_service: RetrievalService,
    file_metadata_provider: FileMetadataProvider,
    embedding_provider,
    overview_service: Optional[DocumentOverviewService] = None,
):
    """
    Process uploaded file with SSE streaming progress events.

    Reuses existing InputDataHandleService for text extraction and chunking,
    and RetrievalService for embedding storage. Yields SSE events at each
    processing phase so the frontend can display real-time progress.

    Supports all file types: PDF, DOCX, PPTX, TXT, MD.

    Args:
        file_content: Binary file content
        filename: Original filename
        user_id: User UUID
        input_service: InputDataHandleService instance
        retrieval_service: RetrievalService instance
        file_metadata_provider: FileMetadataProvider instance
        embedding_provider: Embedding provider instance
        overview_service: Optional DocumentOverviewService instance

    Yields:
        SSE event dicts with progress updates
    """
    start_time = time.time()

    def elapsed():
        return f"{time.time() - start_time:.1f}s"

    file_ext = Path(filename).suffix.lower().lstrip(".")

    # === PHASE 1: Validation ===
    yield create_upload_sse_event(
        "start",
        {
            "message": f"開始處理 {filename}",
            "filename": filename,
            "file_type": file_ext,
            "file_size": len(file_content),
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "elapsed": elapsed(),
        },
    )

    # Validate file
    is_valid, error_msg = input_service.validate_file(file_content, filename)
    if not is_valid:
        yield create_upload_sse_event(
            "error",
            {
                "phase": "validation",
                "message": f"❌ 檔案驗證失敗: {error_msg}",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )
        return

    yield create_upload_sse_event(
        "progress",
        {
            "phase": "validation",
            "message": "✅ 檔案驗證通過",
            "percent": 5,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "elapsed": elapsed(),
        },
    )

    try:
        # === PHASE 2: Text Extraction ===
        yield create_upload_sse_event(
            "progress",
            {
                "phase": "extraction",
                "message": f"📄 正在提取文字 ({file_ext.upper()})...",
                "percent": 10,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        try:
            text, page_count = input_service.extract_text(file_content, filename)
        except ValueError as e:
            yield create_upload_sse_event(
                "error",
                {
                    "phase": "extraction",
                    "message": str(e),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "elapsed": elapsed(),
                },
            )
            return

        yield create_upload_sse_event(
            "progress",
            {
                "phase": "extraction_complete",
                "message": f"✅ 文字提取完成 ({len(text)} 字元, {page_count} 頁/段落)",
                "percent": 25,
                "characters": len(text),
                "pages": page_count,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        # === PHASE 3: Chunking ===
        yield create_upload_sse_event(
            "progress",
            {
                "phase": "chunking",
                "message": "📋 正在分割文字...",
                "percent": 30,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        # Generate unique file_id using existing service method
        file_id = await input_service.generate_unique_file_id(
            file_content, filename, file_metadata_provider
        )

        # Chunk text using configured strategy
        chunks = input_service.chunk_text(text)

        # Enrich chunk metadata
        chunks = input_service.enrich_chunk_metadata(
            chunks=chunks,
            file_id=file_id,
            filename=filename,
            file_size=len(file_content),
        )

        chunk_count = len(chunks)

        yield create_upload_sse_event(
            "checkpoint",
            {
                "phase": "chunking_complete",
                "message": f"✅ 分割完成 ({chunk_count} 個 chunks)",
                "total_chunks": chunk_count,
                "percent": 35,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        # === PHASE 4: Store Metadata ===
        yield create_upload_sse_event(
            "progress",
            {
                "phase": "metadata",
                "message": "💾 儲存檔案元資料...",
                "percent": 40,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        if settings.CHUNKING_STRATEGY == "recursive":
            chunk_size = settings.CHUNK_SIZE
        elif settings.CHUNKING_STRATEGY == "page_based":
            chunk_size = settings.PAGE_BASED_CHUNK_SIZE
        else:
            chunk_size = None

        await file_metadata_provider.add_file(
            file_id=file_id,
            filename=filename,
            file_type=file_ext,
            file_size=len(file_content),
            user_id=user_id,
            chunk_count=chunk_count,
            milvus_partition=f"file_{file_id}",
            metadata={
                "chunking_strategy": input_service.chunking_strategy.get_strategy_name(),
                "chunk_sizes": chunk_size,
            },
        )

        # === PHASE 5: Embedding ===
        chunk_texts = [chunk["content"] for chunk in chunks]
        chunk_metadata = [chunk["metadata"] for chunk in chunks]

        yield create_upload_sse_event(
            "progress",
            {
                "phase": "embedding",
                "message": f"🧠 正在生成向量嵌入 ({chunk_count} chunks)...",
                "percent": 45,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        store_id = await retrieval_service.add_document_chunks(
            file_id=file_id, chunks=chunk_texts, metadata=chunk_metadata
        )

        yield create_upload_sse_event(
            "progress",
            {
                "phase": "embedding_complete",
                "message": f"✅ 向量嵌入完成 (store: {store_id})",
                "percent": 80,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        # Update embedding status
        await file_metadata_provider.update_embedding_status(file_id, "completed")

        # === PHASE 6: Save file to disk ===
        yield create_upload_sse_event(
            "progress",
            {
                "phase": "saving",
                "message": "💾 儲存檔案到磁碟...",
                "percent": 85,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        save_uploaded_file(file_content, filename, file_id)

        # === PHASE 7: Document Overview (optional) ===
        if overview_service:
            yield create_upload_sse_event(
                "progress",
                {
                    "phase": "overview",
                    "message": "📝 生成文件摘要...",
                    "percent": 90,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "elapsed": elapsed(),
                },
            )
            try:
                overview = await overview_service.generate_overview(
                    file_id=file_id, chunks=chunk_texts, filename=filename
                )
                await overview_service.store_overview(
                    file_metadata_provider=file_metadata_provider,
                    file_id=file_id,
                    overview=overview,
                )
            except Exception as overview_error:
                logger.warning(
                    f"Failed to generate overview for {file_id}: {overview_error}"
                )
                yield create_upload_sse_event(
                    "warning",
                    {
                        "phase": "overview",
                        "message": f"⚠️ 文件摘要生成失敗 (非關鍵): {str(overview_error)[:100]}",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "elapsed": elapsed(),
                    },
                )

        # === COMPLETE ===
        total_time = time.time() - start_time
        yield create_upload_sse_event(
            "complete",
            {
                "message": "🎉 處理完成!",
                "file_id": file_id,
                "filename": filename,
                "file_type": file_ext,
                "file_size": len(file_content),
                "pages": page_count,
                "total_chunks": chunk_count,
                "chunking_strategy": input_service.chunking_strategy.get_strategy_name(),
                "embedding_status": "completed",
                "total_time": f"{total_time:.1f}s",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

    except Exception as e:
        logger.error(f"File streaming processing failed for {filename}: {e}")
        import traceback

        yield create_upload_sse_event(
            "error",
            {
                "phase": "processing",
                "message": f"❌ 處理失敗: {str(e)}",
                "error": str(e),
                "stack": traceback.format_exc()[:500],
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )


@router.post(
    "/stream",
    summary="Upload file with SSE streaming progress",
    description="Upload a file (PDF, DOCX, PPTX, TXT, MD) and receive real-time "
    "processing progress via Server-Sent Events.",
)
async def upload_file_stream(
    file: UploadFile = File(..., description="File to upload"),
    user_id: Optional[str] = Header(
        None,
        alias="X-User-ID",
        description="User UUID (optional, uses default if not provided)",
    ),
    input_service: InputDataHandleService = Depends(get_input_data_service),
    file_metadata_provider: FileMetadataProvider = Depends(get_file_metadata_provider),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    embedding_provider=Depends(get_embedding_provider),
    overview_service: DocumentOverviewService = Depends(get_document_overview_service),
):
    """
    Upload file with SSE streaming progress (File-Based System).

    Returns Server-Sent Events with real-time progress updates for each
    processing phase: validation → extraction → chunking → embedding → complete.

    Uses the same SSE event format as the Skill-Based system for frontend consistency.
    """
    import re

    # Resolve user_id
    if user_id is None:
        if settings.DEFAULT_USER_ENABLED:
            user_id = settings.DEFAULT_USER_ID
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "ValidationError",
                    "message": "X-User-ID header is required",
                },
            )

    UUID_PATTERN = (
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    if not re.match(UUID_PATTERN, user_id, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "ValidationError",
                "message": "Invalid user_id format. Must be UUID v4.",
            },
        )

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower().lstrip(".")
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的檔案格式: '.{file_ext}'。支援格式: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )

    # Read file content
    file_content = await file.read()

    async def generate_sse_events():
        # Yield file received event
        yield create_upload_sse_event(
            "file_saved",
            {
                "message": f"📁 檔案已接收: {file.filename}",
                "filename": file.filename,
                "size": len(file_content),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            },
        )

        # Stream processing events
        async for event in process_file_streaming(
            file_content=file_content,
            filename=file.filename,
            user_id=user_id,
            input_service=input_service,
            retrieval_service=retrieval_service,
            file_metadata_provider=file_metadata_provider,
            embedding_provider=embedding_provider,
            overview_service=overview_service,
        ):
            yield event

    return EventSourceResponse(generate_sse_events(), ping=15)
