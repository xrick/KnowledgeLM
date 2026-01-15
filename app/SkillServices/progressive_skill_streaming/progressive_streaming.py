# app/SkillServices/progressive_skill_streaming/progressive_streaming.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Progressive Skill Streaming - Main Orchestrator

Adapted from OPMP for DocAI Skill-Based system.
Coordinates all 5 phases for progressive streaming chat responses.

Architecture:
- Phase 1: Skill Query Understanding
- Phase 2: Skill Document Retrieval (Parallel FAISS)
- Phase 3: Context Assembly
- Phase 4: Response Generation (Token streaming)
- Phase 5: Post-processing

Author: Claude (SuperClaude)
Date: 2025-12-06
Based on: OPMP progressive_streaming.py
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator

from .phase1_skill_query_understanding import SkillQueryUnderstanding
from .phase2_skill_retrieval import SkillDocumentRetrieval
from .phase3_context_assembly import Phase3ContextAssembly
from .phase4_response_generation import Phase4ResponseGeneration
from .phase5_postprocessing import Phase5Postprocessing

logger = logging.getLogger(__name__)

# Configuration: Phase acknowledgment settings
PHASE_ACK_TIMEOUT = 10.0  # Maximum seconds to wait for frontend ACK
PHASE_ACK_ENABLED = True  # Enable/disable acknowledgment protocol

# Global acknowledgment tracking (session_id -> asyncio.Event)
_phase_ack_events: Dict[str, Dict[int, asyncio.Event]] = {}


def acknowledge_phase(session_id: str, phase: int) -> bool:
    """
    Acknowledge that frontend has finished rendering a phase.

    Args:
        session_id: Unique session identifier
        phase: Phase number (1-4, Phase 5 doesn't need ACK)

    Returns:
        True if acknowledgment was successful, False if session not found
    """
    if session_id not in _phase_ack_events:
        logger.warning(f"ACK for unknown session: {session_id}")
        return False

    if phase not in _phase_ack_events[session_id]:
        logger.warning(f"ACK for invalid phase {phase} (session: {session_id})")
        return False

    # Set the event to unblock the backend
    _phase_ack_events[session_id][phase].set()
    logger.info(f"Phase {phase} acknowledged (session: {session_id})")
    return True


def cleanup_session(session_id: str):
    """Clean up session acknowledgment events"""
    if session_id in _phase_ack_events:
        del _phase_ack_events[session_id]
        logger.info(f"Session {session_id} cleaned up")


class ProgressiveSkillStreaming:
    """
    Main orchestrator for progressive streaming chat

    Coordinates all 5 phases and provides unified SSE streaming interface.

    Usage:
        >>> service = ProgressiveSkillStreaming(
        ...     skill_id="skill_xxx",
        ...     llm=llm_instance,
        ...     embedding_service=embedding_service,
        ...     metadata_provider=metadata_provider,
        ...     faiss_base_path="/data/faiss_indices/skills/"
        ... )
        >>> async for update in service.chat_stream_progressive(
        ...     query="What is LLM?",
        ...     document_ids=["doc_001", "doc_002"]
        ... ):
        ...     # SSE format: data: {...}\n\n
        ...     print(update)
    """

    def __init__(
        self,
        skill_id: str,
        llm: Any,
        embedding_service: Any,
        metadata_provider: Any,
        faiss_base_path: str,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize progressive streaming service

        Args:
            skill_id: Skill ID for retrieval
            llm: LangChain LLM instance
            embedding_service: Embedding generation service
            metadata_provider: Skill metadata provider
            faiss_base_path: Base path for FAISS indices
            config: Optional configuration dict
        """
        self.skill_id = skill_id
        self.config = config or {}

        # Initialize cache (optional Redis, fallback to in-memory)
        cache = self.config.get("cache", None)

        # Initialize all phase processors
        self.phase1 = SkillQueryUnderstanding(
            llm=llm,
            cache=cache
        )

        self.phase2 = SkillDocumentRetrieval(
            skill_id=skill_id,
            faiss_base_path=faiss_base_path,
            embedding_service=embedding_service,
            metadata_provider=metadata_provider,
            cache=cache,
            enable_cache=self.config.get("enable_cache", True)
        )

        self.phase3 = Phase3ContextAssembly(
            max_context_tokens=self.config.get("max_context_tokens", 100000)
        )

        self.phase4 = Phase4ResponseGeneration(
            llm=llm,
            cache=cache
        )

        self.phase5 = Phase5Postprocessing()

        logger.info(f"ProgressiveSkillStreaming initialized for skill {skill_id}")

    async def chat_stream_progressive(
        self,
        query: str,
        document_ids: List[str],
        selected_documents: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None  # ✅ Memory support
    ) -> AsyncGenerator[str, None]:
        """
        Main progressive streaming function with frontend acknowledgment protocol

        Orchestrates all 5 phases:
        1. Query understanding
        2. Document retrieval
        3. Context assembly
        4. Response generation (streaming)
        5. Post-processing

        Args:
            query: User query string
            document_ids: List of document IDs to search
            selected_documents: Optional list of selected document names for Phase 1
            session_id: Unique session ID for acknowledgment tracking
            chat_history: Optional list of previous messages for multi-turn context

        Yields:
            SSE-formatted updates (data: {...}\n\n)
        """
        start_time = datetime.now()

        # Generate session ID if not provided
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())

        # Initialize acknowledgment events for this session
        if PHASE_ACK_ENABLED:
            _phase_ack_events[session_id] = {
                1: asyncio.Event(),
                2: asyncio.Event(),
                3: asyncio.Event(),
                4: asyncio.Event()
            }

            # Send session ID to frontend
            yield f"data: {json.dumps({'type': 'session_init', 'session_id': session_id}, ensure_ascii=False)}\n\n"

        try:
            # Use document_ids as selected_documents if not provided
            if selected_documents is None:
                selected_documents = document_ids

            # ============================================================
            # Phase 1: Query Understanding (with conversational detection)
            # ============================================================
            phase1_data = None
            is_conversational = False  # NEW: Track if this is a conversational query

            try:
                # Pass has_chat_history for conversational intent detection
                async for update in self.phase1.process(
                    query,
                    selected_documents,
                    has_chat_history=bool(chat_history)  # NEW: Enable conversational detection
                ):
                    # Forward Phase 1 updates
                    yield f"data: {json.dumps(update, ensure_ascii=False)}\n\n"

                    if update.get("type") == "phase_result":
                        phase1_data = update.get("data")
                        is_conversational = phase1_data.get("is_conversational", False)
                        logger.info(f"Phase 1 complete: {phase1_data} (conversational={is_conversational})")

                        # Wait for frontend acknowledgment before proceeding
                        if PHASE_ACK_ENABLED:
                            try:
                                await asyncio.wait_for(
                                    _phase_ack_events[session_id][1].wait(),
                                    timeout=PHASE_ACK_TIMEOUT
                                )
                                logger.info(f"Phase 1 ACK received from frontend (session: {session_id})")
                            except asyncio.TimeoutError:
                                logger.warning(f"Phase 1 ACK timeout (session: {session_id}) - proceeding anyway")


            except Exception as e:
                logger.error(f"Phase 1 error: {e}")
                # Use fallback analysis
                phase1_data = {
                    "intent": "general_inquiry",
                    "key_concepts": query.split()[:3],
                    "document_keywords": query.split()[:2],
                    "query_focus": "general",
                    "complexity": "medium",
                    "confidence": "low",
                    "is_conversational": False,
                    "conversational_type": "none",
                    "error": str(e)
                }

                yield f"data: {json.dumps({'type': 'warning', 'phase': 1, 'message': 'Using fallback analysis'}, ensure_ascii=False)}\n\n"

            # ============================================================
            # CONDITIONAL: Skip RAG for conversational queries
            # ============================================================
            phase2_data = None
            phase3_data = None

            if is_conversational and chat_history:
                # ========================================================
                # CONVERSATIONAL PATH: Skip Phase 2 & 3, use chat history
                # ========================================================
                logger.info(f"🗣️ Conversational query detected - skipping RAG retrieval")

                # Send progress updates (skipped)
                yield f"data: {json.dumps({'type': 'progress', 'phase': 2, 'message': '對話式請求 - 使用對話歷史', 'progress': 50, 'skipped': True}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'progress', 'phase': 3, 'message': '對話式請求 - 跳過檢索', 'progress': 70, 'skipped': True}, ensure_ascii=False)}\n\n"

                # Build minimal context for Phase 4 (no document chunks)
                phase2_data = {
                    "chunks": [],
                    "total_documents_searched": 0,
                    "total_chunks_found": 0,
                    "skipped": True,
                    "reason": "conversational_query"
                }

                phase3_data = {
                    "chunks": [],
                    "kept_count": 0,
                    "original_count": 0,
                    "truncation_applied": False,
                    "is_conversational": True,
                    "conversational_type": phase1_data.get("conversational_type", "follow_up")
                }

            else:
                # ========================================================
                # NORMAL PATH: Phase 2 (RAG) → Phase 3 (Context Assembly)
                # ========================================================

                # ============================================================
                # Phase 2: Document Retrieval
                # ============================================================
                try:
                    async for update in self.phase2.retrieve(
                        query=query,
                        document_ids=document_ids,
                        top_k=self.config.get("retrieval_top_k", 5),
                        use_cache=self.config.get("enable_cache", True)
                    ):
                        # Forward Phase 2 updates
                        yield f"data: {json.dumps(update, ensure_ascii=False)}\n\n"

                        if update.get("type") == "phase_result":
                            phase2_data = update.get("data")
                            logger.info(f"Phase 2 complete: {phase2_data.get('total_chunks_found', 0)} chunks")

                            # Wait for frontend acknowledgment before proceeding
                            if PHASE_ACK_ENABLED:
                                try:
                                    await asyncio.wait_for(
                                        _phase_ack_events[session_id][2].wait(),
                                        timeout=PHASE_ACK_TIMEOUT
                                    )
                                    logger.info(f"Phase 2 ACK received from frontend (session: {session_id})")
                                except asyncio.TimeoutError:
                                    logger.warning(f"Phase 2 ACK timeout (session: {session_id}) - proceeding anyway")

                except Exception as e:
                    logger.error(f"Phase 2 error: {e}")
                    # Empty results on error
                    phase2_data = {
                        "chunks": [],
                        "total_documents_searched": 0,
                        "total_chunks_found": 0,
                        "error": str(e)
                    }

                    yield f"data: {json.dumps({'type': 'error', 'phase': 2, 'message': f'Retrieval error: {e}'}, ensure_ascii=False)}\n\n"

                # ============================================================
                # Phase 3: Context Assembly
                # ============================================================
                try:
                    # FIX: Use correct parameter names - retrieval_results and analysis (not retrieval_result and analysis_result)
                    async for update in self.phase3.process(
                        retrieval_results=phase2_data,
                        analysis=phase1_data
                    ):
                        # Forward Phase 3 updates
                        yield f"data: {json.dumps(update, ensure_ascii=False)}\n\n"

                        if update.get("type") == "phase_result":
                            phase3_data = update.get("data")
                            logger.info(f"Phase 3 complete: {phase3_data.get('kept_count', 0)} chunks kept")

                            # Wait for frontend acknowledgment before proceeding
                            if PHASE_ACK_ENABLED:
                                try:
                                    await asyncio.wait_for(
                                        _phase_ack_events[session_id][3].wait(),
                                        timeout=PHASE_ACK_TIMEOUT
                                    )
                                    logger.info(f"Phase 3 ACK received from frontend (session: {session_id})")
                                except asyncio.TimeoutError:
                                    logger.warning(f"Phase 3 ACK timeout (session: {session_id}) - proceeding anyway")

                except Exception as e:
                    logger.error(f"Phase 3 error: {e}")
                    # Use phase2 data as fallback
                    phase3_data = {
                        "chunks": phase2_data.get("chunks", []),
                        "kept_count": len(phase2_data.get("chunks", [])),
                        "original_count": len(phase2_data.get("chunks", [])),
                        "truncation_applied": False,
                        "error": str(e)
                    }

                    yield f"data: {json.dumps({'type': 'warning', 'phase': 3, 'message': 'Using unranked chunks'}, ensure_ascii=False)}\n\n"

            # ============================================================
            # Phase 4: Response Generation (Streaming)
            # ============================================================
            generated_response = ""

            try:
                async for update in self.phase4.process(
                    query=query,
                    analysis=phase1_data,
                    context=phase3_data,
                    chat_history=chat_history  # ✅ Pass chat history for multi-turn context
                ):
                    # Forward Phase 4 updates (including tokens)
                    yield f"data: {json.dumps(update, ensure_ascii=False)}\n\n"

                    # Accumulate response tokens
                    if update.get("type") == "markdown_token":
                        generated_response += update.get("token", "")

            except Exception as e:
                logger.error(f"Phase 4 error: {e}")
                # Generate fallback response
                generated_response = f"抱歉，生成回答時發生錯誤：{str(e)}"

                yield f"data: {json.dumps({'type': 'error', 'phase': 4, 'message': f'Generation error: {e}'}, ensure_ascii=False)}\n\n"

            # ============================================================
            # Phase 5: Post-processing
            # ============================================================
            try:
                async for update in self.phase5.process(
                    generated_response=generated_response,
                    context=phase3_data,
                    analysis=phase1_data,
                    query=query
                ):
                    # Forward Phase 5 updates (final completion)
                    yield f"data: {json.dumps(update, ensure_ascii=False)}\n\n"

                    if update.get("type") == "complete":
                        total_time = (datetime.now() - start_time).total_seconds()
                        logger.info(f"Progressive streaming complete in {total_time:.2f}s")

            except Exception as e:
                logger.error(f"Phase 5 error: {e}")
                # Send minimal completion
                yield f"data: {json.dumps({'type': 'complete', 'phase': 5, 'data': {'response': generated_response, 'error': str(e)}}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Fatal error in progressive streaming: {e}")
            # Send error completion
            yield f"data: {json.dumps({'type': 'complete', 'phase': 0, 'error': str(e), 'message': '系統發生錯誤'}, ensure_ascii=False)}\n\n"
        finally:
            # Clean up session acknowledgment events
            if PHASE_ACK_ENABLED and session_id:
                cleanup_session(session_id)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics from all phases

        Returns:
            Dictionary with phase statistics
        """
        return {
            "phase2_stats": self.phase2.stats,
            "cache_enabled": self.config.get("enable_cache", True),
            "max_context_tokens": self.config.get("max_context_tokens", 100000)
        }
