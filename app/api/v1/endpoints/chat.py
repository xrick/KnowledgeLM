# /home/mapleleaf/LCJRepos/gitprjs/DocAI/app/api/v1/endpoints/chat.py
# app/api/v1/endpoints/chat.py
"""
Chat Endpoint with OPMP (Optimistic Progressive Markdown Parsing)

Implements five-phase RAG pipeline with SSE streaming:
1. Query Understanding (Strategy 2: Question Expansion)
2. Parallel Retrieval
3. Context Assembly
4. Response Generation (OPMP Core)
5. Post Processing
"""

import json
import logging
import asyncio
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

# Providers
from app.Providers.llm_provider.client import LLMProviderClient, get_llm_provider
from app.Providers.embedding_provider.client import EmbeddingProvider, get_embedding_provider
from app.Providers.vector_store_provider.client import VectorStoreProvider, get_vector_store_provider
from app.Providers.chat_history_provider.client import ChatHistoryProvider, get_chat_history_provider
from app.Providers.cache_provider.client import CacheProvider, get_cache_provider

# Services
from app.Services.retrieval_service import RetrievalService, get_retrieval_service
from app.Services.prompt_service import PromptService, get_prompt_service
from app.Services.iterative_query_expansion_service import (
    IterativeQueryExpansionService,
    get_iterative_query_expansion_service,
    ExpansionStrategy
)
from app.Services.document_overview_service import (
    DocumentOverviewService,
    get_document_overview_service
)
from app.Providers.file_metadata_provider.client import (
    FileMetadataProvider,
    get_file_metadata_provider
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Schemas
# =============================================================================

class ChatRequest(BaseModel):
    """Chat request schema"""
    query: str = Field(..., description="User's question", min_length=1)
    session_id: str = Field(..., description="Session identifier")
    file_ids: List[str] = Field(..., description="Document file IDs to query against")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    language: Optional[str] = Field("zh", description="Response language (zh/en)")
    top_k: Optional[int] = Field(10, description="Number of context chunks to retrieve")
    enable_expansion: Optional[bool] = Field(True, description="Enable query expansion (Strategy 2)")
    enable_iterative_expansion: Optional[bool] = Field(None, description="Enable iterative multi-round expansion (overrides settings)")
    expansion_rounds: Optional[int] = Field(None, description="Number of expansion rounds (1-3, overrides settings)")


class ChatResponse(BaseModel):
    """Chat response schema (non-streaming fallback)"""
    session_id: str
    query: str
    answer: str
    context_count: int
    expanded_questions: Optional[List[str]] = None
    best_query: Optional[str] = None  # Best query selected by iterative expansion
    expansion_rounds: Optional[int] = None  # Number of expansion rounds used
    metadata: dict = {}


# =============================================================================
# SSE Event Helpers
# =============================================================================

def create_sse_event(event_type: str, data: dict) -> dict:
    """
    Create SSE event dict

    Args:
        event_type: Event type (progress, markdown_token, complete, error)
        data: Event data payload

    Returns:
        dict: SSE event with 'event' and 'data' keys
    """
    return {
        "event": event_type,
        "data": json.dumps(data, ensure_ascii=False)
    }


# =============================================================================
# Chat Endpoints
# =============================================================================

@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    llm_client: LLMProviderClient = Depends(get_llm_provider),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    prompt_service: PromptService = Depends(get_prompt_service),
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider),
    cache_provider: CacheProvider = Depends(get_cache_provider),
    iterative_expansion_service: IterativeQueryExpansionService = Depends(get_iterative_query_expansion_service),
    overview_service: DocumentOverviewService = Depends(get_document_overview_service),
    file_metadata_provider: FileMetadataProvider = Depends(get_file_metadata_provider)
):
    """
    Chat with documents using SSE streaming (OPMP)

    Five-Phase RAG Pipeline:
    1. Query Understanding: Expand user query into sub-questions
    2. Parallel Retrieval: Retrieve context from multiple sub-questions
    3. Context Assembly: Build enhanced RAG prompt
    4. Response Generation: Stream LLM response with OPMP
    5. Post Processing: Save chat history and metadata

    SSE Events:
    - progress: Phase progress updates (phase 1-5, progress 0-100%)
    - markdown_token: Individual tokens for progressive rendering
    - complete: Final completion event with metadata
    - error: Error event if something fails

    Example:
        >>> POST /api/v1/chat/stream
        >>> {
        ...   "query": "What is RAG?",
        ...   "session_id": "session_xyz",
        ...   "file_ids": ["file_abc"],
        ...   "language": "zh"
        ... }
    """

    async def generate_sse_events():
        """Generate SSE events for OPMP streaming"""
        from app.core.config import settings

        full_response = ""
        expanded_questions = []
        context_chunks = []
        best_query = None
        expansion_rounds_used = 0

        try:
            # =====================================================================
            # Phase 1: Query Understanding (Strategy 2: Question Expansion)
            # =====================================================================
            yield create_sse_event("progress", {
                "phase": 1,
                "phase_name": "Query Understanding",
                "progress": 0,
                "message": "Analyzing user query..."
            })

            # Detect summary intent (using consolidated iterative expansion service)
            # Pass file_count to enable multi-file summary detection
            query_metadata = iterative_expansion_service.get_query_metadata(
                request.query,
                file_count=len(request.file_ids)
            )
            is_summary = query_metadata.get("is_summary", False)
            is_multi_file_summary = query_metadata.get("is_multi_file_summary", False)
            intent_type = query_metadata.get("intent_type", "question")
            logger.info(f"Query intent detected: {intent_type} (is_summary={is_summary}, is_multi_file_summary={is_multi_file_summary})")

            # Determine if iterative expansion should be used
            use_iterative = request.enable_iterative_expansion
            if use_iterative is None:
                use_iterative = getattr(settings, 'ENABLE_ITERATIVE_EXPANSION', False)

            if request.enable_expansion:
                # Use iterative multi-round expansion (consolidated service)
                yield create_sse_event("progress", {
                    "phase": 1,
                    "phase_name": "Query Understanding",
                    "progress": 30,
                    "message": "Starting query expansion..."
                })

                # Determine expansion strategy based on settings or request
                strategy_mode = getattr(settings, 'EXPANSION_STRATEGY_MODE', 'adaptive')
                if not use_iterative:
                    strategy = ExpansionStrategy.SINGLE  # Single round if iterative disabled
                elif strategy_mode == 'single':
                    strategy = ExpansionStrategy.SINGLE
                elif strategy_mode == 'iterative':
                    strategy = ExpansionStrategy.ITERATIVE
                else:
                    strategy = ExpansionStrategy.ADAPTIVE

                # Perform expansion
                iterative_result = await iterative_expansion_service.expand_iteratively(
                    query=request.query,
                    strategy=strategy,
                    cache_provider=cache_provider
                )

                # Extract results
                best_query = iterative_result.best_query
                expanded_questions = iterative_result.final_queries
                expansion_rounds_used = iterative_result.total_rounds

                logger.info(
                    f"Query expansion complete: {expansion_rounds_used} rounds, "
                    f"{len(expanded_questions)} final queries, "
                    f"best query: {best_query[:50]}..."
                )

                yield create_sse_event("progress", {
                    "phase": 1,
                    "phase_name": "Query Understanding",
                    "progress": 80,
                    "message": f"Query expansion: {expansion_rounds_used} rounds, {len(expanded_questions)} queries"
                })
            else:
                expanded_questions = [request.query]
                best_query = request.query
                expansion_rounds_used = 0

            yield create_sse_event("progress", {
                "phase": 1,
                "phase_name": "Query Understanding",
                "progress": 100,
                "message": f"Query expanded into {len(expanded_questions)} queries ({expansion_rounds_used} rounds)"
            })

            # =====================================================================
            # Phase 2: Parallel Retrieval (with Overview Fallback)
            # =====================================================================
            yield create_sse_event("progress", {
                "phase": 2,
                "phase_name": "Parallel Retrieval",
                "progress": 0,
                "message": "Retrieving relevant context from documents..."
            })

            # Step 2.1: Get document overviews first (for fallback and multi-doc handling)
            overviews = await overview_service.get_multiple_overviews(
                file_metadata_provider=file_metadata_provider,
                file_ids=request.file_ids
            )
            logger.info(f"Retrieved {len(overviews)} document overviews for {len(request.file_ids)} files")

            # =====================================================================
            # SHORTCUT: Multi-file summary using overviews (skip FAISS)
            # =====================================================================
            # When user asks to summarize/explain multiple files, we bypass FAISS
            # and directly use document overviews from SQLite for faster, more
            # comprehensive results.
            if is_multi_file_summary and overviews:
                logger.info(f"[SHORTCUT] Multi-file summary detected, using overview shortcut for {len(overviews)} files")

                yield create_sse_event("progress", {
                    "phase": 2,
                    "phase_name": "Parallel Retrieval",
                    "progress": 50,
                    "message": f"Using document overviews for {len(overviews)} files (shortcut mode)..."
                })

                # Separate files with valid overviews from those without
                # IMPORTANT: Compare against request.file_ids to find files missing from overviews dict
                files_with_overview = []
                files_without_overview = []

                # First, check files that ARE in overviews dict
                for file_id, overview in overviews.items():
                    if overview and overview.strip():
                        files_with_overview.append(file_id)
                        context_chunks.append({
                            "content": overview,
                            "metadata": {"file_id": file_id, "source": "overview_shortcut"}
                        })
                    else:
                        files_without_overview.append(file_id)

                # Second, find files that are NOT in overviews dict at all (completely missing)
                overviews_keys = set(overviews.keys())
                for file_id in request.file_ids:
                    if file_id not in overviews_keys:
                        files_without_overview.append(file_id)
                        logger.warning(f"[SHORTCUT] File {file_id} has no overview record at all")

                logger.info(f"[SHORTCUT] {len(files_with_overview)} files have valid overviews, {len(files_without_overview)} need FAISS fallback")

                # For files without valid overviews, use FAISS retrieval
                if files_without_overview:
                    logger.info(f"[SHORTCUT-FALLBACK] Using FAISS for files without overview: {files_without_overview}")
                    fallback_tasks = [
                        retrieval_service.retrieve_context(
                            query=expanded_questions[0] if expanded_questions else request.query,
                            file_ids=files_without_overview,
                            top_k=request.top_k,
                            fair_distribution=True,
                            include_scores=True  # Enable score-based ranking for fallback retrieval
                        )
                    ]
                    fallback_results = await asyncio.gather(*fallback_tasks)

                    seen_contents = {chunk.get("content", "") for chunk in context_chunks}
                    for results in fallback_results:
                        for result in results:
                            content = result.get("content", "")
                            if content and content not in seen_contents:
                                context_chunks.append(result)
                                seen_contents.add(content)

                    logger.info(f"[SHORTCUT-FALLBACK] Added {len(context_chunks) - len(files_with_overview)} chunks from FAISS for files without overview")

                logger.info(f"[SHORTCUT] Total {len(context_chunks)} context chunks (overview + FAISS fallback)")

            # =====================================================================
            # Standard path: Vector retrieval with FAISS
            # =====================================================================
            else:
                # Step 2.2: Try vector retrieval
                # Enable fair distribution for summary requests with multiple files
                enable_fair_dist = is_summary and len(request.file_ids) > 1

                retrieval_tasks = [
                    retrieval_service.retrieve_context(
                        query=question,
                        file_ids=request.file_ids,
                        top_k=request.top_k,
                        fair_distribution=enable_fair_dist,
                        include_scores=True  # Enable score-based ranking for multi-file retrieval
                    )
                    for question in expanded_questions
                ]

                retrieval_results = await asyncio.gather(*retrieval_tasks)

                # Merge and deduplicate context chunks
                seen_contents = set()
                for results in retrieval_results:
                    for result in results:
                        content = result.get("content", "")
                        if content and content not in seen_contents:
                            context_chunks.append(result)
                            seen_contents.add(content)

                logger.info(f"Retrieved {len(context_chunks)} unique context chunks from vector search")

                # Step 2.3: FALLBACK - If no chunks found, use document overviews
                if len(context_chunks) == 0 and overviews:
                    logger.warning(f"No chunks from vector search, falling back to {len(overviews)} document overviews")
                    for file_id, overview in overviews.items():
                        context_chunks.append({
                            "content": f"[文件概述 - {file_id}]\n{overview}",
                            "metadata": {"file_id": file_id, "source": "overview"}
                        })
                        seen_contents.add(overview)

            yield create_sse_event("progress", {
                "phase": 2,
                "phase_name": "Parallel Retrieval",
                "progress": 100,
                "message": f"Retrieved {len(context_chunks)} relevant chunks"
            })

            # =====================================================================
            # Phase 3: Context Assembly
            # =====================================================================
            yield create_sse_event("progress", {
                "phase": 3,
                "phase_name": "Context Assembly",
                "progress": 0,
                "message": "Building enhanced RAG prompt..."
            })

            # Get chat history
            chat_history = await chat_history_provider.get_chat_history(
                session_id=request.session_id,
                limit=10  # Last 10 messages for context
            )

            # Build file_id to filename mapping for context display
            file_id_to_filename = {}
            for chunk in context_chunks:
                file_id = chunk.get("metadata", {}).get("file_id")
                if file_id and file_id not in file_id_to_filename:
                    file_info = await file_metadata_provider.get_file(file_id)
                    if file_info:
                        file_id_to_filename[file_id] = file_info.get("filename", file_id)
                    else:
                        file_id_to_filename[file_id] = file_id

            # Extract content strings with filename for prompt building
            context_strings = []
            for chunk in context_chunks:
                content = chunk.get("content", "")
                file_id = chunk.get("metadata", {}).get("file_id", "unknown")
                filename = file_id_to_filename.get(file_id, file_id)
                context_strings.append(f"[文檔片段 - 來源: {filename}]\n{content}")

            # Build prompt based on intent type
            if is_multi_file_summary:
                # Use multi-file summary prompt (shortcut mode)
                messages = prompt_service.build_multi_file_summary_prompt(
                    query=request.query,
                    context_chunks=context_strings,
                    file_count=len(request.file_ids),
                    chat_history=chat_history
                )
                logger.info(f"[SHORTCUT] Using multi-file summary prompt for {len(request.file_ids)} files")
            else:
                # Use standard RAG prompt
                messages = prompt_service.build_rag_prompt(
                    query=request.query,
                    context_chunks=context_strings,
                    chat_history=chat_history,
                    language=request.language,
                    is_summary=is_summary
                )

            yield create_sse_event("progress", {
                "phase": 3,
                "phase_name": "Context Assembly",
                "progress": 100,
                "message": "Prompt built with context and history"
            })

            # =====================================================================
            # Phase 4: Response Generation (OPMP Core)
            # =====================================================================
            yield create_sse_event("progress", {
                "phase": 4,
                "phase_name": "Response Generation",
                "progress": 0,
                "message": "Generating answer from LLM..."
            })

            # Stream LLM response
            async for chunk in llm_client.get_chat_completion_stream(
                messages=messages,
                temperature=0.3
            ):
                # Parse SSE chunk from LLM provider
                chunk_str = chunk.decode('utf-8')

                # Handle SSE format: "data: {json}\n\n"
                for line in chunk_str.split('\n'):
                    if line.startswith('data: '):
                        data_str = line[6:]  # Remove "data: " prefix

                        if data_str.strip() == '[DONE]':
                            continue

                        try:
                            data = json.loads(data_str)

                            # Extract token from OpenAI-compatible format
                            choices = data.get('choices', [])
                            if choices:
                                delta = choices[0].get('delta', {})
                                token = delta.get('content', '')

                                if token:
                                    full_response += token

                                    # OPMP: Send token for progressive rendering
                                    yield create_sse_event("markdown_token", {
                                        "token": token
                                    })

                        except json.JSONDecodeError:
                            continue

            yield create_sse_event("progress", {
                "phase": 4,
                "phase_name": "Response Generation",
                "progress": 100,
                "message": "Answer generation complete"
            })

            # =====================================================================
            # Phase 5: Post Processing
            # =====================================================================
            yield create_sse_event("progress", {
                "phase": 5,
                "phase_name": "Post Processing",
                "progress": 0,
                "message": "Saving chat history..."
            })

            # Save user message and assistant response to chat history
            await chat_history_provider.add_message(
                session_id=request.session_id,
                role="user",
                content=request.query,
                metadata={
                    "file_ids": request.file_ids,
                    "expanded_questions": expanded_questions,
                    "context_count": len(context_chunks),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )

            await chat_history_provider.add_message(
                session_id=request.session_id,
                role="assistant",
                content=full_response,
                metadata={
                    "context_count": len(context_chunks),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )

            yield create_sse_event("progress", {
                "phase": 5,
                "phase_name": "Post Processing",
                "progress": 100,
                "message": "Chat history saved"
            })

            # =====================================================================
            # Completion Event
            # =====================================================================
            yield create_sse_event("complete", {
                "session_id": request.session_id,
                "query": request.query,
                "answer": full_response,
                "context_count": len(context_chunks),
                "expanded_questions": expanded_questions,
                "best_query": best_query,
                "expansion_rounds": expansion_rounds_used,
                "metadata": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "language": request.language,
                    "iterative_expansion_used": use_iterative if 'use_iterative' in dir() else False
                }
            })

            logger.info(f"Chat streaming completed for session: {request.session_id}")

        except Exception as e:
            logger.error(f"Error in chat streaming: {str(e)}")

            # Send error event
            yield create_sse_event("error", {
                "error": str(e),
                "message": "An error occurred during chat processing"
            })

    # ping=15 sends keep-alive comments every 15 seconds to prevent connection timeout
    return EventSourceResponse(generate_sse_events(), ping=15)


@router.post("", response_model=ChatResponse)
async def chat_non_streaming(
    request: ChatRequest,
    llm_client: LLMProviderClient = Depends(get_llm_provider),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    prompt_service: PromptService = Depends(get_prompt_service),
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider),
    cache_provider: CacheProvider = Depends(get_cache_provider),
    iterative_expansion_service: IterativeQueryExpansionService = Depends(get_iterative_query_expansion_service),
    overview_service: DocumentOverviewService = Depends(get_document_overview_service),
    file_metadata_provider: FileMetadataProvider = Depends(get_file_metadata_provider)
):
    """
    Chat with documents (non-streaming fallback)

    Same RAG pipeline as streaming endpoint, but returns complete response.
    Use this for clients that don't support SSE.

    Example:
        >>> POST /api/v1/chat
        >>> {
        ...   "query": "What is RAG?",
        ...   "session_id": "session_xyz",
        ...   "file_ids": ["file_abc"]
        ... }
    """
    from app.core.config import settings

    try:
        # Phase 1: Query Understanding (using consolidated iterative expansion service)
        expanded_questions = [request.query]
        best_query = request.query
        expansion_rounds_used = 0

        # Detect summary intent
        query_metadata = iterative_expansion_service.get_query_metadata(request.query)
        is_summary = query_metadata.get("is_summary", False)

        # Determine if iterative expansion should be used
        use_iterative = request.enable_iterative_expansion
        if use_iterative is None:
            use_iterative = getattr(settings, 'ENABLE_ITERATIVE_EXPANSION', False)

        if request.enable_expansion:
            # Determine expansion strategy
            strategy_mode = getattr(settings, 'EXPANSION_STRATEGY_MODE', 'adaptive')
            if not use_iterative:
                strategy = ExpansionStrategy.SINGLE
            elif strategy_mode == 'single':
                strategy = ExpansionStrategy.SINGLE
            elif strategy_mode == 'iterative':
                strategy = ExpansionStrategy.ITERATIVE
            else:
                strategy = ExpansionStrategy.ADAPTIVE

            # Perform expansion
            iterative_result = await iterative_expansion_service.expand_iteratively(
                query=request.query,
                strategy=strategy,
                cache_provider=cache_provider
            )

            best_query = iterative_result.best_query
            expanded_questions = iterative_result.final_queries
            expansion_rounds_used = iterative_result.total_rounds

        # Phase 2: Parallel Retrieval (with Overview Fallback)
        # Step 2.1: Get document overviews first
        overviews = await overview_service.get_multiple_overviews(
            file_metadata_provider=file_metadata_provider,
            file_ids=request.file_ids
        )
        logger.info(f"Retrieved {len(overviews)} document overviews for {len(request.file_ids)} files")

        # Step 2.2: Try vector retrieval
        # Enable fair distribution for summary requests with multiple files
        enable_fair_dist = is_summary and len(request.file_ids) > 1

        retrieval_tasks = [
            retrieval_service.retrieve_context(
                query=question,
                file_ids=request.file_ids,
                top_k=request.top_k,
                fair_distribution=enable_fair_dist,
                include_scores=True  # Enable score-based ranking for multi-file retrieval
            )
            for question in expanded_questions
        ]
        retrieval_results = await asyncio.gather(*retrieval_tasks)

        # Merge and deduplicate
        context_chunks = []
        seen_contents = set()
        for results in retrieval_results:
            for result in results:
                content = result.get("content", "")
                if content and content not in seen_contents:
                    context_chunks.append(result)
                    seen_contents.add(content)

        # Step 2.3: FALLBACK - If no chunks found, use document overviews
        if len(context_chunks) == 0 and overviews:
            logger.warning(f"No chunks from vector search, falling back to {len(overviews)} document overviews")
            for file_id, overview in overviews.items():
                context_chunks.append({
                    "content": f"[文件概述 - {file_id}]\n{overview}",
                    "metadata": {"file_id": file_id, "source": "overview"}
                })
                seen_contents.add(overview)

        # Phase 3: Context Assembly
        chat_history = await chat_history_provider.get_chat_history(
            session_id=request.session_id,
            limit=10
        )

        # Build file_id to filename mapping for context display
        file_id_to_filename = {}
        for chunk in context_chunks:
            file_id = chunk.get("metadata", {}).get("file_id")
            if file_id and file_id not in file_id_to_filename:
                file_info = await file_metadata_provider.get_file(file_id)
                if file_info:
                    file_id_to_filename[file_id] = file_info.get("filename", file_id)
                else:
                    file_id_to_filename[file_id] = file_id

        # Extract content strings with filename for prompt building
        context_strings = []
        for chunk in context_chunks:
            content = chunk.get("content", "")
            file_id = chunk.get("metadata", {}).get("file_id", "unknown")
            filename = file_id_to_filename.get(file_id, file_id)
            context_strings.append(f"[文檔片段 - 來源: {filename}]\n{content}")

        messages = prompt_service.build_rag_prompt(
            query=request.query,
            context_chunks=context_strings,
            chat_history=chat_history,
            language=request.language,
            is_summary=is_summary
        )

        # Phase 4: Response Generation (non-streaming)
        response = await llm_client.get_chat_completion(
            messages=messages,
            temperature=0.3
        )

        answer = response['choices'][0]['message']['content']

        # Phase 5: Post Processing
        await chat_history_provider.add_message(
            session_id=request.session_id,
            role="user",
            content=request.query,
            metadata={"file_ids": request.file_ids}
        )

        await chat_history_provider.add_message(
            session_id=request.session_id,
            role="assistant",
            content=answer
        )

        return ChatResponse(
            session_id=request.session_id,
            query=request.query,
            answer=answer,
            context_count=len(context_chunks),
            expanded_questions=expanded_questions,
            best_query=best_query,
            expansion_rounds=expansion_rounds_used,
            metadata={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "language": request.language,
                "iterative_expansion_used": use_iterative
            }
        )

    except Exception as e:
        logger.error(f"Error in non-streaming chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Sequential Multi-Document Processing Endpoint
# =============================================================================

class SequentialSummaryRequest(BaseModel):
    """Request schema for sequential multi-document summary"""
    query: str = Field(..., description="User's summary request", min_length=1)
    session_id: str = Field(..., description="Session identifier")
    file_ids: List[str] = Field(..., description="Document file IDs to summarize sequentially")
    language: Optional[str] = Field("zh", description="Response language (zh/en)")


class SequentialSummaryResponse(BaseModel):
    """Response schema for sequential multi-document summary"""
    session_id: str
    query: str
    summaries: List[dict]  # List of {file_id, filename, summary}
    combined_summary: Optional[str] = None
    metadata: dict = {}


@router.post("/sequential-summary", response_model=SequentialSummaryResponse)
async def sequential_document_summary(
    request: SequentialSummaryRequest,
    llm_client: LLMProviderClient = Depends(get_llm_provider),
    overview_service: DocumentOverviewService = Depends(get_document_overview_service),
    file_metadata_provider: FileMetadataProvider = Depends(get_file_metadata_provider),
    prompt_service: PromptService = Depends(get_prompt_service)
):
    """
    Sequential Multi-Document Summary Generation

    Processes each document one-by-one for more thorough summaries.
    Use this when parallel processing fails to capture document content.

    Workflow:
    1. For each file_id, get document overview
    2. Generate summary for each document sequentially
    3. Optionally combine into a unified summary

    Example:
        >>> POST /api/v1/chat/sequential-summary
        >>> {
        ...   "query": "請分別幫我摘要這些文件",
        ...   "session_id": "session_xyz",
        ...   "file_ids": ["file_1", "file_2"]
        ... }
    """
    try:
        summaries = []

        # Get file metadata for filenames
        file_metadata = {}
        for file_id in request.file_ids:
            file_info = await file_metadata_provider.get_file(file_id)
            if file_info:
                file_metadata[file_id] = file_info

        # Process each document sequentially
        for file_id in request.file_ids:
            filename = file_metadata.get(file_id, {}).get("filename", f"文件 {file_id}")

            # Get document overview
            overview = await overview_service.get_overview(
                file_metadata_provider=file_metadata_provider,
                file_id=file_id
            )

            if overview:
                # Use overview as context for summary generation
                context_text = f"[文件: {filename}]\n\n{overview}"

                messages = [
                    {
                        "role": "system",
                        "content": """你是一位專業的文檔摘要專家。請根據提供的文件概述，生成一份簡潔、結構化的摘要。

摘要格式：
1. 文件主題/目的
2. 核心內容（3-5個要點）
3. 主要結論或貢獻

請用200-300字完成摘要，使用繁體中文。"""
                    },
                    {
                        "role": "user",
                        "content": f"請為以下文件生成摘要：\n\n{context_text}"
                    }
                ]

                response = await llm_client.get_chat_completion(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=500
                )

                summary_text = response['choices'][0]['message']['content']
            else:
                summary_text = f"[無法取得文件 {file_id} 的概述，請重新上傳此文件]"

            summaries.append({
                "file_id": file_id,
                "filename": filename,
                "summary": summary_text
            })

            logger.info(f"Generated sequential summary for {file_id}: {len(summary_text)} chars")

        # Generate combined summary if multiple documents
        combined_summary = None
        if len(summaries) > 1:
            all_summaries_text = "\n\n---\n\n".join([
                f"**{s['filename']}**:\n{s['summary']}"
                for s in summaries
            ])

            combine_messages = [
                {
                    "role": "system",
                    "content": "你是一位專業的文檔整合專家。請根據多份文件的個別摘要，提供一個簡短的整合觀點（3-5句話）。"
                },
                {
                    "role": "user",
                    "content": f"請根據以下文件摘要，提供整合觀點：\n\n{all_summaries_text}"
                }
            ]

            combine_response = await llm_client.get_chat_completion(
                messages=combine_messages,
                temperature=0.3,
                max_tokens=300
            )

            combined_summary = combine_response['choices'][0]['message']['content']

        return SequentialSummaryResponse(
            session_id=request.session_id,
            query=request.query,
            summaries=summaries,
            combined_summary=combined_summary,
            metadata={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "language": request.language,
                "document_count": len(summaries),
                "processing_mode": "sequential"
            }
        )

    except Exception as e:
        logger.error(f"Error in sequential summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
