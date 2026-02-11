# app/api/v1/endpoints/skills.py
"""
Skill Management Endpoints

API endpoints for creating, listing, and chatting with Skills.
Includes PDF management for skill configuration.
Designed for "Demo First" stability.
"""

import asyncio
import csv
import hashlib
import io
import json
import logging
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import PyPDF2
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.Providers.bge_embedding_provider import get_bge_embedding_provider
from app.Providers.chat_history_provider.client import (
    ChatHistoryProvider,
    get_chat_history_provider,
)
from app.Providers.embedding_provider.client import get_embedding_provider
from app.Providers.llm_provider.client import LLMProviderClient, get_llm_provider

# Services & Providers
from app.Providers.skill_metadata_provider.client import (
    SkillMetadataProvider,
    get_skill_metadata_provider,
)
from app.Providers.vector_store_provider.client import VectorStoreProvider
from app.Services.input_data_handle_service import InputDataHandleService
from app.Services.prompt_service import PromptService, get_prompt_service
from app.SkillServices.index_integrity import (
    diagnose_incomplete_index,
    verify_index_integrity,
)
from app.SkillServices.skill_ingestion_service import (
    SkillIngestionService,
    get_skill_ingestion_service,
)
from app.SkillServices.skill_retrieval_service import (
    SkillRetrievalService,
    get_skill_retrieval_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Config file path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
SKILL_CONFIG_PATH = PROJECT_ROOT / "scripts" / "skill_data" / "skill_config.json"


# =============================================================================
# Data Models
# =============================================================================


class SkillCreateRequest(BaseModel):
    """Request model for creating a new skill"""

    name: str = Field(..., min_length=1, description="Name of the skill")
    content: str = Field(..., min_length=10, description="Text content of the skill")
    description: Optional[str] = Field(None, description="Brief description")
    category: Optional[str] = Field("General", description="Skill category")
    level: Optional[str] = Field("intermediate", description="Difficulty level")
    tags: List[str] = Field(default_factory=list, description="Tags for filtering")


class SkillResponse(BaseModel):
    """Response model for skill details"""

    skill_id: str
    skill_name: str
    skill_description: Optional[str]
    skill_category: Optional[str]
    total_chunks: int
    created_at: str
    parent_skill_id: Optional[str] = "root"  # For 3-level tree hierarchy
    source_name: Optional[str] = ""  # Document name for instant attachments


class SkillChatRequest(BaseModel):
    """Request model for chatting with skills"""

    query: str = Field(..., min_length=1)
    skill_ids: List[str] = Field(..., min_items=1, description="List of active skills")
    temperature: float = Field(0.7, ge=0.0, le=1.0)


class SkillChatResponse(BaseModel):
    """Response model for skill chat"""

    answer: str
    context_used: List[Dict[str, Any]]
    metadata: Dict[str, Any]


# -----------------------------------------------------------------------------
# PDF Management Models
# -----------------------------------------------------------------------------


class PDFSourceModel(BaseModel):
    """Model for a PDF source"""

    path: str = Field(..., description="Relative path to PDF file")
    enabled: bool = Field(True, description="Whether this source is enabled")
    description: Optional[str] = Field("", description="Description of the PDF")


class SkillConfigModel(BaseModel):
    """Model for skill configuration"""

    skill_name: str
    description: str = ""
    category: str = "General"
    enabled: bool = True
    sources: List[PDFSourceModel] = []


class AddSourceRequest(BaseModel):
    """Request to add a PDF source to a skill"""

    skill_name: str
    source: PDFSourceModel


class InstantAttachmentRequest(BaseModel):
    """Request to add an instant attachment"""

    skill_name: str
    path: str
    description: Optional[str] = ""


class RebuildRequest(BaseModel):
    """Request to rebuild skills"""

    skill_name: Optional[str] = Field(
        None, description="Optional: only rebuild this skill"
    )
    clean_first: bool = Field(True, description="Clean existing data before rebuild")
    use_smart_strategy: bool = Field(
        True, description="Use smart rebuild strategy (only rebuild affected skills)"
    )
    force_all: bool = Field(
        False, description="Force rebuild all skills, ignoring smart strategy"
    )


# =============================================================================
# Helper Functions
# =============================================================================


def load_skill_config() -> Dict[str, Any]:
    """Load skill configuration from JSON file"""
    try:
        if SKILL_CONFIG_PATH.exists():
            with open(SKILL_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return {
                "version": "1.0",
                "skills": [],
                "instant_attachments": [],
                "settings": {
                    "chunk_size": 1000,
                    "chunk_overlap": 200,
                    "embedding_model": "BAAI/bge-m3",
                    "embedding_dimension": 1024,
                    "rebuild_threshold": 5,
                },
            }
    except Exception as e:
        logger.error(f"Error loading skill config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load config: {e}")


def save_skill_config(config: Dict[str, Any]):
    """Save skill configuration to JSON file"""
    try:
        config["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        SKILL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SKILL_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logger.info(f"Saved skill config to {SKILL_CONFIG_PATH}")
    except Exception as e:
        logger.error(f"Error saving skill config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save config: {e}")


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/", response_model=List[SkillResponse])
async def list_skills(
    category: Optional[str] = None,
    provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    List all available skills.
    """
    try:
        skills = await provider.list_skills(category=category)
        return skills
    except Exception as e:
        logger.error(f"Error listing skills: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list skills")


@router.post("/upload", response_model=SkillResponse)
async def create_skill(
    request: SkillCreateRequest,
    ingestion_service: SkillIngestionService = Depends(get_skill_ingestion_service),
    retrieval_service: SkillRetrievalService = Depends(get_skill_retrieval_service),
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Create a new skill from text content.

    Process:
    0. Validate skill name uniqueness (NEW)
    1. Process text (chunking, ID generation) via IngestionService
    2. Store chunks in Vector DB via RetrievalService
    3. Store metadata in SQLite via MetadataProvider
    """
    try:
        # 0. VALIDATION: Check if skill name already exists (main skills only)
        existing_skills = await metadata_provider.list_skills()
        existing_main_skills = [
            s
            for s in existing_skills
            if s.get("parent_skill_id") == "root" and s.get("skill_id") != "root"
        ]

        for skill in existing_main_skills:
            if skill.get("skill_name") == request.name:
                raise HTTPException(
                    status_code=409,  # Conflict - duplicate resource
                    detail=f"Skill name '{request.name}' already exists. Please use a different name.",
                )

        # 1. Process and Chunk
        processed_skill = await ingestion_service.process_skill(
            skill_name=request.name,
            skill_content=request.content,
            skill_description=request.description,
            skill_category=request.category,
            skill_level=request.level,
            tags=request.tags,
            skill_metadata_provider=metadata_provider,
        )

        skill_id = processed_skill["skill_id"]
        chunks_data = processed_skill["chunks"]

        # Extract just text list for vector store
        chunk_texts = [c["content"] for c in chunks_data]
        chunk_metadatas = [c["metadata"] for c in chunks_data]

        # 2. Store Vectors (FAISS)
        # Note: This creates the 'skill' store type folder
        await retrieval_service.add_content(
            content_id=skill_id, chunks=chunk_texts, metadata=chunk_metadatas
        )

        # 3. Store Metadata (SQLite)
        await metadata_provider.create_skill(
            skill_id=skill_id,
            skill_name=request.name,
            skill_description=request.description,
            skill_category=request.category,
            skill_level=request.level,
            tags=request.tags,
            total_chunks=processed_skill["chunk_count"],
        )

        return SkillResponse(
            skill_id=skill_id,
            skill_name=processed_skill["skill_name"],
            skill_description=processed_skill["skill_description"],
            skill_category=processed_skill["skill_category"],
            total_chunks=processed_skill["chunk_count"],
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating skill: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create skill: {str(e)}")


@router.get("/demo", response_model=List[Dict[str, Any]])
async def get_demo_skills(
    provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Get all available skills for demo presentation.
    Returns enhanced skill information with auto-assigned icons based on name/category.
    """
    # Icon mapping based on skill name or category keywords
    ICON_MAPPING = {
        "LLM": "🧠",
        "AI": "🤖",
        "民法": "📜",
        "刑法": "⚔️",
        "法": "⚖️",
        "Legal": "⚖️",
        "Python": "🐍",
        "Programming": "💻",
        "Research": "📚",
        "Business": "📊",
        "Technology": "🔬",
    }

    def get_icon(skill_name: str, category: str) -> str:
        """Auto-assign icon based on skill name or category"""
        for keyword, icon in ICON_MAPPING.items():
            if keyword in skill_name or keyword in (category or ""):
                return icon
        return "📁"  # Default icon

    try:
        # Get ALL skills from database (no filtering by hardcoded IDs)
        skills = await provider.list_skills()
        demo_skills = []

        # Load display_order from skill_heads table (SQLite - Single Source of Truth)
        # No longer depends on skill_config.json
        skill_heads = await provider.list_skill_heads(enabled_only=False)
        # Build a map of skill_name -> display_order from skill_heads
        display_order_map = {
            h["skill_name"]: h.get("display_order", 999) for h in skill_heads
        }

        for skill in skills:
            skill_id = skill.get("skill_id")
            skill_name = skill.get("skill_name", "Unknown")
            skill_category = skill.get("skill_category", "General")
            parent_skill_id = skill.get("parent_skill_id", "root")

            # Skip system root record
            if skill_id == "root":
                continue

            # Get display_order: main skills get from skill_heads, attachments inherit from parent
            if parent_skill_id == "root":
                # Main skill - get order from skill_heads table
                display_order = display_order_map.get(skill_name, 999)
            else:
                # Instant attachment - inherit parent's display_order + 0.1 to stay grouped
                parent_skill = next(
                    (s for s in skills if s.get("skill_id") == parent_skill_id), None
                )
                if parent_skill:
                    parent_name = parent_skill.get("skill_name", "")
                    display_order = display_order_map.get(parent_name, 999) + 0.1
                else:
                    display_order = 999

            demo_skill = {
                "id": skill_id,
                "skill_id": skill_id,  # Include both formats for compatibility
                "name": skill_name,
                "skill_name": skill_name,
                "description": skill.get("skill_description", ""),
                "icon": get_icon(skill_name, skill_category),
                "tag": skill_category,
                "skill_category": skill_category,
                "fileCount": skill.get("file_count", 0),
                "chunkCount": skill.get("total_chunks", 0),
                "total_chunks": skill.get("total_chunks", 0),
                "status": "ready",
                "parent_skill_id": parent_skill_id,
                "source_name": skill.get(
                    "source_name", ""
                ),  # Document name for instant attachments
                "display_order": display_order,  # NEW: Include display_order for frontend sorting
            }
            demo_skills.append(demo_skill)

        # Sort by display_order before returning
        demo_skills.sort(key=lambda x: x.get("display_order", 999))

        logger.info(
            f"Returning {len(demo_skills)} skills for demo (sorted by display_order)"
        )
        return demo_skills

    except Exception as e:
        logger.error(f"Error getting demo skills: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get demo skills")


@router.post("/demo/query")
async def query_demo_skill(
    skill_id: str = Body(None, embed=False),  # Single skill (backward compat)
    skill_ids: List[str] = Body(None, embed=False),  # Multi-skill support
    query: str = Body(..., embed=False),
    top_k: int = Body(10, embed=False),
    # Memory 參數
    user_id: Optional[str] = Body(None, embed=False),
    session_id: Optional[str] = Body(None, embed=False),
    include_history: bool = Body(True, embed=False),
    history_limit: int = Body(10, embed=False),
    # Dependencies
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
    retrieval_service: SkillRetrievalService = Depends(get_skill_retrieval_service),
    llm_client: LLMProviderClient = Depends(get_llm_provider),
    prompt_service: PromptService = Depends(get_prompt_service),
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider),
):
    """
    Demo-optimized skill query endpoint with parallel search.
    Supports single skill_id (backward compat) or multiple skill_ids (multi-select).
    """
    try:
        # Build skill list - support both single and multi-skill queries
        if skill_ids:
            target_skill_ids = skill_ids
        elif skill_id:
            target_skill_ids = [skill_id]
        else:
            raise HTTPException(
                status_code=400, detail="skill_id or skill_ids required"
            )

        # ✅ FIX: Support both skill_id and head_id
        # Frontend may send head_id when clicking skill header without expanding
        valid_skill_ids = []
        skill_names = {}  # Cache skill names for citation

        for sid in target_skill_ids:
            # Check if this is a head_id (starts with 'head_')
            if sid.startswith("head_"):
                # Get all skill_ids under this head
                head_skills = await metadata_provider.list_skills(limit=1000)
                matching_skills = [s for s in head_skills if s.get("head_id") == sid]

                for skill in matching_skills:
                    skill_id = skill.get("skill_id")
                    if skill_id:
                        mappings = await metadata_provider.get_documents_for_skill(
                            skill_id
                        )
                        if mappings:
                            valid_skill_ids.append(skill_id)
                            # Cache skill name
                            skill_names[skill_id] = skill.get("skill_name", skill_id)
                            source_name = skill.get("source_name", "")
                            if source_name:
                                skill_names[skill_id] = source_name
            else:
                # Regular skill_id processing
                mappings = await metadata_provider.get_documents_for_skill(sid)
                if mappings:
                    valid_skill_ids.append(sid)
                    # Get skill name for citation
                    skill_info = await metadata_provider.get_skill(sid)
                    if skill_info:
                        skill_names[sid] = skill_info.get("skill_name", sid)
                        # Also get source_name for instant attachments
                        metadata = skill_info.get("metadata", {})
                        if metadata and metadata.get("source_file"):
                            source_file = metadata["source_file"]
                            skill_names[sid] = Path(source_file.split("/")[-1]).stem

        if not valid_skill_ids:
            raise HTTPException(
                status_code=404, detail=f"No documents found for specified skills"
            )

        # =========================================================================
        # Session Management - Memory 功能
        # =========================================================================
        # Session ID 格式: skill_{user_id}_{primary_skill_id}
        effective_user_id = user_id or settings.DEFAULT_USER_ID
        primary_skill_id = skill_id or (valid_skill_ids[0] if valid_skill_ids else None)
        effective_session_id = (
            session_id or f"skill_{effective_user_id}_{primary_skill_id}"
        )

        # 確保 Session 存在
        if not await chat_history_provider.session_exists(effective_session_id):
            await chat_history_provider.create_session(
                session_id=effective_session_id,
                user_id=effective_user_id,
                file_ids=[primary_skill_id] if primary_skill_id else [],
                metadata={"type": "skill_chat", "skill_id": primary_skill_id},
            )
            logger.info(f"Created new session: {effective_session_id}")

        # 獲取對話歷史
        chat_history = []
        if include_history:
            chat_history = await chat_history_provider.get_chat_history(
                session_id=effective_session_id, limit=history_limit
            )
            logger.debug(f"Loaded {len(chat_history)} messages from history")

        # IMPORTANT: Use skill_id directly as content_id for FAISS search
        # The FAISS store is indexed by skill_id, not individual document IDs
        content_ids = valid_skill_ids  # Multi-skill search

        # Level 1 並行搜尋優化 - Parallel search across skills
        if len(content_ids) > 1:
            # Parallel retrieval for multiple documents
            tasks = []
            for doc_id in content_ids[:10]:  # Limit to first 10 docs for demo
                task = retrieval_service.retrieve_context(
                    query=query,
                    content_ids=[doc_id],
                    top_k=3,  # 3 chunks per document
                    include_scores=True,
                )
                tasks.append(task)

            # Execute parallel
            all_results = await asyncio.gather(*tasks)

            # Merge and sort results
            context_results = []
            for results in all_results:
                context_results.extend(results)

            # Sort by score and take top_k
            context_results.sort(key=lambda x: x.get("score", float("inf")))
            context_results = context_results[:top_k]
        else:
            # Single document, direct search
            context_results = await retrieval_service.retrieve_context(
                query=query, content_ids=content_ids, top_k=top_k, include_scores=True
            )

        # ✅ SMART SEARCH SUGGESTION: If no results, suggest other skills
        if not context_results:
            # Search across ALL skills to find potential matches
            all_skills = await metadata_provider.list_skills(limit=100)

            # Try to find skills that might contain this query
            suggestions = []
            for skill in all_skills:
                skill_id = skill.get("skill_id")
                skill_name = skill.get("skill_name", "")
                source_name = skill.get("source_name", "")

                # Skip currently selected skills
                if skill_id in valid_skill_ids:
                    continue

                # Simple keyword matching in skill/source names
                search_text = f"{skill_name} {source_name}".lower()
                query_keywords = query.lower().split()

                # If any query keyword matches, suggest this skill
                if any(
                    keyword in search_text
                    for keyword in query_keywords
                    if len(keyword) > 2
                ):
                    suggestions.append(
                        {
                            "skill_name": skill_name,
                            "source_name": source_name,
                            "skill_id": skill_id,
                            "chunks": skill.get("total_chunks", 0),
                        }
                    )

            # Build helpful response
            selected_names = [skill_names.get(sid, sid) for sid in valid_skill_ids]
            answer = f"抱歉，我在您選擇的文檔「{', '.join(selected_names)}」中沒有找到與「{query}」相關的資訊。"

            if suggestions[:3]:  # Show top 3 suggestions
                answer += "\n\n💡 建議：以下文檔可能包含相關內容：\n"
                for sug in suggestions[:3]:
                    display_name = (
                        sug["source_name"] if sug["source_name"] else sug["skill_name"]
                    )
                    answer += f"  • 📁 {sug['skill_name']} - {display_name} ({sug['chunks']} chunks)\n"
                answer += "\n請在左側技能樹中選擇相應的文檔重新搜尋。"

            # Save conversation even for no-result queries
            await chat_history_provider.add_message(
                session_id=effective_session_id,
                role="user",
                content=query,
                metadata={"skill_id": primary_skill_id, "no_results": True},
            )
            await chat_history_provider.add_message(
                session_id=effective_session_id,
                role="assistant",
                content=answer,
                metadata={
                    "no_results": True,
                    "suggestions_count": len(suggestions[:3]),
                },
            )

            return {
                "answer": answer,
                "results": [],
                "query": query,
                "documents_searched": len(valid_skill_ids),
                "suggestions": suggestions[:3] if suggestions else [],
                "session_id": effective_session_id,
            }

        # Build context for LLM with citations
        context_texts = []
        citations = []

        for item in context_results:
            content = item.get("content", "")
            metadata = item.get("metadata", {})

            # Extract citation info from metadata
            # Try multiple sources for document name:
            # 1. document_name in metadata
            # 2. content_id mapped to skill_names
            # 3. skill_id fallback
            doc_name = metadata.get("document_name")
            if not doc_name or doc_name == "Unknown":
                content_id = metadata.get("content_id", "")
                doc_name = skill_names.get(content_id, content_id or "Unknown")
            page_num = metadata.get("page_number", 0)

            # Add citation reference
            if page_num:
                citation = f"[{doc_name}-第{page_num}頁]"
                citations.append(citation)
                # Add citation to context
                context_texts.append(f"{content}\n{citation}")
            else:
                # Even without page number, add source name
                if doc_name and doc_name != "Unknown":
                    citation = f"[{doc_name}]"
                    citations.append(citation)
                    context_texts.append(f"{content}\n{citation}")
                else:
                    context_texts.append(content)

        # Generate response (with chat history for multi-turn)
        messages = prompt_service.build_rag_prompt(
            query=query,
            context_chunks=context_texts,
            chat_history=chat_history,  # 傳入對話歷史
            language="zh",
        )

        response = await llm_client.get_chat_completion(
            messages=messages, temperature=0.3
        )

        answer = response["choices"][0]["message"]["content"]

        # Add unique citations at the end of answer
        if citations:
            unique_citations = list(set(citations))
            answer += f"\n\n參考來源：\n" + "\n".join(unique_citations)

        # =========================================================================
        # Save conversation to MongoDB
        # =========================================================================
        await chat_history_provider.add_message(
            session_id=effective_session_id,
            role="user",
            content=query,
            metadata={"skill_id": primary_skill_id, "skill_ids": valid_skill_ids},
        )
        await chat_history_provider.add_message(
            session_id=effective_session_id,
            role="assistant",
            content=answer,
            metadata={
                "sources_count": len(context_results),
                "citations": list(set(citations)) if citations else [],
            },
        )
        logger.info(f"Saved conversation to session: {effective_session_id}")

        # Build results with proper citations
        results = []
        for r in context_results[:5]:
            meta = r.get("metadata", {})
            content_id = meta.get("content_id", "")
            r_doc_name = meta.get("document_name") or skill_names.get(
                content_id, content_id or "Unknown"
            )
            r_page = meta.get("page_number", 0)
            citation = f"[{r_doc_name}-第{r_page}頁]" if r_page else f"[{r_doc_name}]"
            results.append(
                {
                    "content": r.get("content", ""),
                    "score": float(r.get("score", 0)),
                    "metadata": meta,
                    "citation": citation,
                    "source_name": r_doc_name,
                }
            )

        return {
            "skill_id": skill_id or (valid_skill_ids[0] if valid_skill_ids else None),
            "skill_ids": valid_skill_ids,  # All searched skills
            "query": query,
            "answer": answer,
            "results": results,
            "search_mode": "multi" if len(content_ids) > 1 else "single",
            "documents_searched": len(content_ids),
            "session_id": effective_session_id,  # Memory session ID
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in demo skill query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=SkillChatResponse)
async def chat_with_skills(
    request: SkillChatRequest,
    retrieval_service: SkillRetrievalService = Depends(get_skill_retrieval_service),
    llm_client: LLMProviderClient = Depends(get_llm_provider),
    prompt_service: PromptService = Depends(get_prompt_service),
):
    """
    Simple chat endpoint for Skills.

    1. Retrieve context from selected skills.
    2. Build prompt.
    3. Generate answer.
    """
    try:
        # 1. Retrieval (Parallel/Round-Robin is handled inside service if implemented,
        # currently sequential but sufficient for Demo)
        # Retrieve top 3 chunks per skill effectively
        # Since we don't have merged index yet, we search each skill.

        context_results = await retrieval_service.retrieve_context(
            query=request.query,
            content_ids=request.skill_ids,
            top_k=5,  # Total chunks
            include_scores=True,
        )

        # Extract content for prompt
        context_texts = [item["content"] for item in context_results]

        # 2. Build Prompt
        # Reuse existing PromptService which handles "Context" formatting well
        messages = prompt_service.build_rag_prompt(
            query=request.query,
            context_chunks=context_texts,
            language="zh",  # Force Traditional Chinese for Demo
        )

        # 3. Generate Answer
        response = await llm_client.get_chat_completion(
            messages=messages, temperature=request.temperature
        )

        answer = response["choices"][0]["message"]["content"]

        return SkillChatResponse(
            answer=answer,
            context_used=[
                {
                    "content": c.get("content")[:50] + "...",
                    "skill_id": c.get("metadata", {}).get("skill_id"),
                }
                for c in context_results
            ],
            metadata={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": "ollama",
            },
        )

    except Exception as e:
        logger.error(f"Error in skill chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PDF Configuration Management Endpoints (DEPRECATED - Use /tree and /heads instead)
# =============================================================================


@router.get("/config")
async def get_skill_config(
    provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    DEPRECATED: Use GET /tree for skill tree structure.

    Get the current skill configuration.
    Returns all skills with their PDF sources.
    Also queries database for instant attachments (skills with parent_skill_id != 'root').

    NOTE: This endpoint still reads from skill_config.json for backward compatibility.
    New code should use /tree and /heads endpoints which use SQLite as single source of truth.
    """
    config = load_skill_config()

    # Add file existence check for each source
    for skill in config.get("skills", []):
        for source in skill.get("sources", []):
            source_path = PROJECT_ROOT / source["path"]
            source["exists"] = source_path.exists()
            if source_path.exists():
                source["size_mb"] = round(source_path.stat().st_size / (1024 * 1024), 2)

    # Query database for instant attachments (skills with parent_skill_id != 'root')
    try:
        all_skills = await provider.list_skills()
        db_instant_attachments = [
            {
                "skill_id": s["skill_id"],
                "skill_name": s["skill_name"],
                "source_name": s.get("source_name", ""),
                "parent_skill_id": s.get("parent_skill_id", "root"),
                "total_chunks": s.get("total_chunks", 0),
                "category": s.get("skill_category", "General"),
            }
            for s in all_skills
            if s.get("parent_skill_id", "root") != "root"
            and s.get("skill_id") != "root"
        ]
        # Use database count instead of config file
        instant_count = len(db_instant_attachments)
        config["instant_attachments"] = db_instant_attachments
    except Exception as e:
        logger.warning(f"Failed to query database for instant attachments: {e}")
        instant_count = len(config.get("instant_attachments", []))
        db_instant_attachments = config.get("instant_attachments", [])

    # Check instant attachments from config file (legacy)
    for attachment in config.get("instant_attachments", []):
        if "path" in attachment:
            att_path = PROJECT_ROOT / attachment.get("path", "")
            attachment["exists"] = att_path.exists()

    rebuild_threshold = config.get("settings", {}).get("rebuild_threshold", 5)

    return {
        "config": config,
        "config_path": str(SKILL_CONFIG_PATH),
        "rebuild_threshold": rebuild_threshold,
        "instant_count": instant_count,
        "needs_rebuild": instant_count >= rebuild_threshold,
    }


@router.get("/config/skills")
async def get_config_skills():
    """
    DEPRECATED: Use GET /tree for skill tree structure.

    Get list of skills from configuration with their PDF sources.
    """
    config = load_skill_config()
    skills = []

    for skill in config.get("skills", []):
        sources = skill.get("sources", [])
        enabled_sources = [s for s in sources if s.get("enabled", True)]

        # Check if files exist
        existing_sources = []
        for source in sources:
            source_path = PROJECT_ROOT / source["path"]
            existing_sources.append(
                {
                    **source,
                    "exists": source_path.exists(),
                    "filename": Path(source["path"]).name,
                }
            )

        skills.append(
            {
                "skill_name": skill.get("skill_name"),
                "description": skill.get("description", ""),
                "category": skill.get("category", "General"),
                "enabled": skill.get("enabled", True),
                "total_sources": len(sources),
                "enabled_sources": len(enabled_sources),
                "sources": existing_sources,
            }
        )

    return {"skills": skills}


@router.post("/config/skills")
async def add_skill_to_config(skill: SkillConfigModel):
    """
    DEPRECATED: Use POST /heads to create a new skill head.

    Add a new skill to the configuration.
    """
    config = load_skill_config()
    skills = config.get("skills", [])

    # Check if skill already exists
    for existing in skills:
        if existing.get("skill_name") == skill.skill_name:
            raise HTTPException(
                status_code=409,
                detail=f"Skill name '{skill.skill_name}' already exists. Please use a different name.",
            )

    # Add new skill
    new_skill = {
        "skill_name": skill.skill_name,
        "description": skill.description,
        "category": skill.category,
        "enabled": skill.enabled,
        "sources": [s.dict() for s in skill.sources],
    }
    skills.append(new_skill)
    config["skills"] = skills

    save_skill_config(config)

    return {
        "message": f"Skill '{skill.skill_name}' added successfully",
        "skill": new_skill,
    }


@router.post("/config/skills/{skill_name}/sources")
async def add_source_to_skill(skill_name: str, source: PDFSourceModel):
    """
    Add a PDF source to an existing skill.
    """
    config = load_skill_config()
    skills = config.get("skills", [])

    # Find skill
    skill_found = False
    for skill in skills:
        if skill.get("skill_name") == skill_name:
            skill_found = True
            sources = skill.get("sources", [])

            # Check if source already exists
            for existing in sources:
                if existing.get("path") == source.path:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Source '{source.path}' already exists in skill",
                    )

            # Check if file exists
            source_path = PROJECT_ROOT / source.path
            if not source_path.exists():
                raise HTTPException(
                    status_code=400, detail=f"PDF file not found: {source.path}"
                )

            # Add source
            sources.append(source.dict())
            skill["sources"] = sources
            break

    if not skill_found:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    save_skill_config(config)

    return {"message": f"Source added to skill '{skill_name}'", "source": source.dict()}


# =============================================================================
# PDF Processing Helper Functions
# =============================================================================


async def process_pdf_for_skill(
    pdf_path: Path,
    skill_name: str,
    skill_description: str,
    skill_category: str = "General",
    parent_skill_id: str = "root",
    head_id: str = None,
) -> Dict[str, Any]:
    """
    Process a PDF file: extract text, generate embeddings, store in FAISS and SQLite.

    Args:
        pdf_path: Path to the PDF file
        skill_name: Name of the skill this PDF belongs to
        skill_description: Description of the skill
        skill_category: Category of the skill
        parent_skill_id: Parent skill ID for hierarchy ('root' for main skills,
                         existing skill_id for instant attachments)
        head_id: Reference to skill_heads table (new architecture)

    Returns:
        Dictionary with processing results
    """
    logger.info(f"Processing PDF for skill '{skill_name}': {pdf_path}")

    # Initialize providers
    embedding_provider = get_bge_embedding_provider()
    vector_provider = VectorStoreProvider(persist_directory="./data/faiss_indices")
    metadata_provider = SkillMetadataProvider(db_path="./data/skill_metadata.db")

    embedding_dimension = 1024  # BGE-M3 dimension

    # Generate skill ID - FIXED: Include file hash to prevent collision
    # When multiple files uploaded to same skill in same second, they need unique IDs
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name_hash = hashlib.md5(skill_name.encode("utf-8")).hexdigest()[:8]
    file_hash = hashlib.md5(pdf_path.name.encode("utf-8")).hexdigest()[
        :6
    ]  # Add file-specific hash
    skill_id = f"skill_{timestamp}_{name_hash}_{file_hash}"

    logger.info(f"Generated skill_id: {skill_id} for file: {pdf_path.name}")

    # ========== PHASE 1: Initialize Processing Status ==========
    try:
        await metadata_provider.update_processing_status(
            skill_id=skill_id, status="processing", indexed_chunks=0
        )
        logger.info(f"Set processing status to 'processing' for {skill_id}")
    except Exception as e:
        logger.warning(f"Failed to initialize processing status: {e}")

    # Extract pages from PDF
    pages = []
    try:
        with open(pdf_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            num_pages = len(pdf_reader.pages)

            for page_num in range(num_pages):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()

                # Clean text
                lines = text.split("\n")
                cleaned_lines = [line.strip() for line in lines if line.strip()]
                cleaned_text = "\n".join(cleaned_lines)
                while "  " in cleaned_text:
                    cleaned_text = cleaned_text.replace("  ", " ")

                if cleaned_text.strip():
                    pages.append(cleaned_text)

        logger.info(f"Extracted {len(pages)} pages from {pdf_path.name}")

    except Exception as e:
        logger.error(f"Error extracting PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to extract PDF: {str(e)}")

    if not pages:
        raise HTTPException(
            status_code=400, detail="PDF has no extractable text content"
        )

    # Create chunks and embeddings
    all_chunks = []
    all_embeddings = []

    doc_id = f"doc_{hashlib.md5(str(pdf_path).encode()).hexdigest()[:8]}"

    # ========== PHASE 4: Create Chunks (WITHOUT embeddings yet) ==========
    for page_num, page_text in enumerate(pages, 1):
        chunk_id = f"{skill_id}_{doc_id}_p{page_num}"

        chunk_metadata = {
            "chunk_id": chunk_id,
            "skill_id": skill_id,
            "document_id": doc_id,
            "document_name": pdf_path.stem,
            "page_number": page_num,
            "chunk_index": len(all_chunks),
            "embedding_model": "BAAI/bge-m3",
            "embedding_dimension": embedding_dimension,
        }

        all_chunks.append(
            {"chunk_id": chunk_id, "content": page_text, "metadata": chunk_metadata}
        )

    logger.info(
        f"Created {len(all_chunks)} chunks (embeddings will be generated in batches)"
    )

    # ========== PHASE 4.5: Batch Embedding Generation with Retry ==========
    BATCH_SIZE = 10  # Process 10 pages per batch
    MAX_RETRIES = 3  # Maximum retry attempts per batch

    for batch_start in range(0, len(all_chunks), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(all_chunks))
        batch_chunks = all_chunks[batch_start:batch_end]
        batch_texts = [chunk["content"] for chunk in batch_chunks]

        batch_num = (batch_start // BATCH_SIZE) + 1
        total_batches = (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE

        retry_count = 0
        batch_embeddings = None
        last_error = None

        while retry_count < MAX_RETRIES:
            try:
                logger.info(
                    f"🔄 Processing batch {batch_num}/{total_batches}: "
                    f"chunks {batch_start}-{batch_end - 1} "
                    f"(attempt {retry_count + 1}/{MAX_RETRIES})"
                )

                # Batch embedding generation
                batch_embeddings = embedding_provider.embed_texts(
                    texts=batch_texts,
                    batch_size=len(batch_texts),
                    normalize=True,
                    show_progress=False,
                )

                logger.info(
                    f"✅ Batch {batch_num}/{total_batches} successful: "
                    f"{len(batch_embeddings)} embeddings generated"
                )
                break  # Success, exit retry loop

            except Exception as e:
                retry_count += 1
                last_error = e
                logger.error(
                    f"❌ Batch {batch_num}/{total_batches} failed "
                    f"(attempt {retry_count}/{MAX_RETRIES}): {str(e)}"
                )

                if retry_count >= MAX_RETRIES:
                    # Final retry failed - mark as failed and raise
                    await metadata_provider.update_processing_status(
                        skill_id=skill_id,
                        status="failed",
                        indexed_chunks=len(
                            all_embeddings
                        ),  # Chunks successfully embedded so far
                        error=f"Embedding generation failed at chunk {batch_start}: {str(e)}",
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Embedding generation failed after {MAX_RETRIES} retries at batch {batch_num}: {str(e)}",
                    )

                # Wait before retry (exponential backoff: 2^retry_count seconds)
                wait_time = 2**retry_count
                logger.info(f"⏳ Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)

        # Add successful batch embeddings to all_embeddings
        all_embeddings.extend(batch_embeddings)

        # Update progress in database
        await metadata_provider.update_processing_status(
            skill_id=skill_id, status="processing", indexed_chunks=len(all_embeddings)
        )
        logger.info(
            f"📊 Progress: {len(all_embeddings)}/{len(all_chunks)} embeddings generated"
        )

    logger.info(
        f"✅ All embeddings generated successfully: {len(all_embeddings)} total"
    )

    # Store embeddings in FAISS
    try:
        texts = [chunk["content"] for chunk in all_chunks]
        metadata_list = [chunk["metadata"] for chunk in all_chunks]

        class EmbeddingWrapper:
            def __init__(self, provider):
                self._provider = provider

            def embed_query(self, text):
                return self._provider.embed_single(text).tolist()

        store_id = vector_provider.create_store_from_texts(
            texts=texts,
            embeddings=EmbeddingWrapper(embedding_provider),
            metadatas=metadata_list,
            file_id=skill_id,
            store_type="skill",
            precomputed_embeddings=all_embeddings,
        )

        logger.info(f"Stored embeddings in FAISS: {store_id}")

    except Exception as e:
        logger.error(f"Error storing embeddings: {e}")
        await metadata_provider.update_processing_status(
            skill_id=skill_id, status="failed", error=f"FAISS storage failed: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to store embeddings: {str(e)}"
        )

    # ========== PHASE 5: VERIFY INDEX INTEGRITY ==========
    try:
        is_valid, actual_vectors, error = await verify_index_integrity(
            skill_id=skill_id, expected_chunks=len(all_chunks)
        )

        if not is_valid:
            # Integrity check failed - mark as failed
            await metadata_provider.update_processing_status(
                skill_id=skill_id,
                status="failed",
                indexed_chunks=actual_vectors,
                error=error,
            )

            # Get diagnostic information
            diagnosis = await diagnose_incomplete_index(
                skill_id=skill_id, expected_chunks=len(all_chunks)
            )

            logger.error(f"Index integrity verification failed: {diagnosis}")

            raise HTTPException(
                status_code=500,
                detail=f"FAISS index verification failed for {skill_id}. "
                f"Expected {len(all_chunks)} vectors, got {actual_vectors}. "
                f"Diagnosis: {diagnosis.get('recommendations', [])}",
            )

        logger.info(
            f"✅ Index integrity verified: {actual_vectors}/{len(all_chunks)} vectors"
        )

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Index verification error: {e}")
        await metadata_provider.update_processing_status(
            skill_id=skill_id,
            status="failed",
            error=f"Index verification failed: {str(e)}",
        )
        raise HTTPException(
            status_code=500, detail=f"Index verification failed: {str(e)}"
        )

    # Store metadata in SQLite
    # Per-PDF Architecture: source_name should be the PDF filename (stem)
    source_name = pdf_path.stem  # e.g., "民法", "刑法"
    logger.info(
        f"Setting source_name='{source_name}' for skill_id={skill_id} (from pdf_path.stem)"
    )

    try:
        await metadata_provider.create_skill(
            skill_id=skill_id,
            skill_name=skill_name,
            skill_description=skill_description,
            skill_category=skill_category,
            skill_level="professional",
            tags=[skill_category.lower()],
            total_chunks=len(all_chunks),
            metadata={
                "embedding_model": "BAAI/bge-m3",
                "embedding_dimension": embedding_dimension,
                "source_file": str(pdf_path),
                "is_per_pdf_child": True,  # Mark as Per-PDF child
            },
            parent_skill_id=parent_skill_id,
            source_name=source_name,  # ✅ Per-PDF: Set the PDF filename
            head_id=head_id,  # ✅ Link to skill_heads table (new architecture)
        )

        # Store document mapping and chunk metadata
        db_path = Path("data/skill_metadata.db")
        conn = sqlite3.connect(db_path, timeout=30.0)  # Wait up to 30s for lock
        cursor = conn.cursor()

        # Insert document mapping
        cursor.execute(
            """
            INSERT INTO skill_document_mapping
            (skill_id, file_id, document_name, document_path, total_pages, relevance_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (skill_id, doc_id, pdf_path.stem, str(pdf_path), len(pages), 1.0),
        )

        # Insert chunk metadata
        for chunk in all_chunks:
            metadata = chunk["metadata"]
            cursor.execute(
                """
                INSERT INTO skill_chunk_metadata
                (chunk_id, skill_id, document_id, document_name, page_number,
                 chunk_index, chunk_text, embedding_model, embedding_dimension, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    metadata["chunk_id"],
                    skill_id,
                    metadata["document_id"],
                    metadata["document_name"],
                    metadata["page_number"],
                    metadata["chunk_index"],
                    chunk["content"][:500],
                    "BAAI/bge-m3",
                    embedding_dimension,
                    json.dumps(metadata),
                ),
            )

        conn.commit()
        conn.close()

        logger.info(f"Stored metadata in SQLite for skill {skill_id}")

    except Exception as e:
        logger.error(f"Error storing metadata: {e}")
        await metadata_provider.update_processing_status(
            skill_id=skill_id,
            status="failed",
            error=f"Metadata storage failed: {str(e)}",
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to store metadata: {str(e)}"
        )

    # ========== PHASE 6: Mark as Completed ==========
    await metadata_provider.update_processing_status(
        skill_id=skill_id, status="completed", indexed_chunks=len(all_chunks)
    )

    logger.info(
        f"✅ PDF processing completed successfully for {skill_id}: "
        f"{len(all_chunks)} chunks indexed and verified"
    )

    return {
        "skill_id": skill_id,
        "skill_name": skill_name,
        "document_name": pdf_path.stem,
        "total_pages": len(pages),
        "total_chunks": len(all_chunks),
        "embedding_model": "BAAI/bge-m3",
        "integrity_verified": True,
    }


# =============================================================================
# SSE Upload Progress - Real-time streaming feedback
# =============================================================================


def create_upload_sse_event(event_type: str, data: dict) -> dict:
    """Create SSE event dict for upload progress"""
    return {"event": event_type, "data": json.dumps(data, ensure_ascii=False)}


def _producer_loop(
    pdf_path: Path,
    batch_queue: queue.Queue,
    batch_size: int,
    is_ppt: bool,
    logger: logging.Logger,
):
    """
    Producer Thread: Reads PDF pages and queues text batches.

    Runs in separate thread to not block main event loop.
    Reads PDF sequentially, chunks text, and puts batches into queue.

    Args:
        pdf_path: Path to PDF file
        batch_queue: Queue to put text batches
        batch_size: Number of chunks per batch
        is_ppt: Whether PDF is PPT-converted (affects loader choice)
        logger: Logger instance
    """
    import PyPDF2

    try:
        text_buffer = []
        page_buffer = []

        if is_ppt:
            # Use PyMuPDFLoader for PPT-converted PDFs
            try:
                from langchain_community.document_loaders import PyMuPDFLoader

                loader = PyMuPDFLoader(str(pdf_path))
                langchain_pages = loader.load()
                total_pages = len(langchain_pages)

                logger.info(f"Producer: Processing {total_pages} pages (PPT mode)")

                for page_num, doc in enumerate(langchain_pages, 1):
                    page_text = doc.page_content.strip()

                    # Each page becomes one chunk for PPT
                    text_buffer.append(page_text)
                    page_buffer.append(page_num)

                    # When buffer reaches batch_size, put to queue
                    if len(text_buffer) >= batch_size:
                        batch_queue.put(
                            {
                                "texts": list(text_buffer),
                                "pages": list(page_buffer),
                                "batch_num": page_num // batch_size,
                            }
                        )
                        text_buffer.clear()
                        page_buffer.clear()

            except Exception as e:
                logger.error(
                    f"Producer: PyMuPDFLoader failed: {e}, falling back to PyPDF2"
                )
                is_ppt = False

        if not is_ppt:
            # Use PyPDF2 for regular PDFs
            with open(pdf_path, "rb") as f:
                pdf_reader = PyPDF2.PdfReader(f)
                total_pages = len(pdf_reader.pages)

                logger.info(f"Producer: Processing {total_pages} pages (PyPDF2 mode)")

                for page_num, page in enumerate(pdf_reader.pages, 1):
                    text = page.extract_text()

                    # Each page becomes one chunk
                    text_buffer.append(text)
                    page_buffer.append(page_num)

                    # When buffer reaches batch_size, put to queue
                    if len(text_buffer) >= batch_size:
                        batch_queue.put(
                            {
                                "texts": list(text_buffer),
                                "pages": list(page_buffer),
                                "batch_num": page_num // batch_size,
                            }
                        )
                        text_buffer.clear()
                        page_buffer.clear()

        # Flush remaining chunks
        if text_buffer:
            batch_queue.put(
                {
                    "texts": list(text_buffer),
                    "pages": list(page_buffer),
                    "batch_num": (page_num // batch_size) + 1,
                }
            )

        # Sentinel value: signals end of stream
        batch_queue.put(None)
        logger.info(f"Producer: Finished reading {total_pages} pages")

    except Exception as e:
        logger.error(f"Producer: Fatal error: {e}")
        # Put error dict to queue
        batch_queue.put({"error": str(e)})


async def process_pdf_for_skill_streaming(
    pdf_path: Path,
    skill_name: str,
    skill_description: str,
    skill_category: str = "General",
    parent_skill_id: str = "root",
    head_id: str = None,
):
    """
    ✅ REFACTORED 2025-12-12: Producer-Consumer Pattern for Real-time Progress!
    ✅ INTEGRATED PPT Detection: Detects PPT-converted PDFs and provides warnings

    Process a PDF file with SSE streaming progress updates using Producer-Consumer pattern.

    Architecture:
    - Producer Thread: Reads PDF pages in background, queues text batches
    - Consumer (Main): Gets batches from queue, embeds with GPU, yields SSE events
    - Queue: Bounded queue (maxsize=10) provides backpressure control

    Benefits:
    - Real-time progress updates (every 2-5 seconds per batch)
    - Non-blocking PDF reading (CPU doesn't wait for GPU)
    - Memory efficient (bounded queue prevents RAM explosion)
    - Graceful cancellation support

    Uses batch embedding (BATCH_SIZE=6) with retry mechanism (MAX_RETRIES=3)
    for robust embedding generation.

    Yields SSE events for each processing step.
    """
    import time

    import fitz  # PyMuPDF for PPT detection
    import PyPDF2

    start_time = time.time()

    def elapsed():
        return f"{time.time() - start_time:.1f}s"

    # Initialize providers
    vector_provider = VectorStoreProvider(persist_directory="./data/faiss_indices")
    metadata_provider = SkillMetadataProvider(db_path="./data/skill_metadata.db")
    embedding_provider = get_embedding_provider()

    # Generate skill ID
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name_hash = hashlib.md5(skill_name.encode("utf-8")).hexdigest()[:8]
    file_hash = hashlib.md5(pdf_path.name.encode("utf-8")).hexdigest()[:6]
    skill_id = f"skill_{timestamp}_{name_hash}_{file_hash}"

    # Yield initial event
    yield create_upload_sse_event(
        "start",
        {
            "message": f"開始處理 {pdf_path.name}",
            "filename": pdf_path.name,
            "skill_id": skill_id,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "elapsed": elapsed(),
        },
    )

    try:
        yield create_upload_sse_event(
            "progress",
            {
                "phase": "init",
                "message": f"初始化處理元件... Skill ID: {skill_id}",
                "skill_id": skill_id,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        # === PHASE 0: Detect PPT-converted PDF & Get Total Pages ===
        total_pages_count = 0  # Will be used for progress calculation
        try:
            doc = fitz.open(str(pdf_path))
            total_pages_count = len(doc)  # ✅ Get total pages for progress tracking

            # Check metadata
            metadata = doc.metadata
            creator = metadata.get("creator", "").lower()
            producer = metadata.get("producer", "").lower()

            is_ppt = False
            ppt_confidence = "unknown"

            if "powerpoint" in creator or "powerpoint" in producer:
                is_ppt = True
                ppt_confidence = "high (metadata)"
            else:
                # Check page orientation
                check_pages = min(3, len(doc))
                landscape_count = 0

                for i in range(check_pages):
                    page = doc.load_page(i)
                    rect = page.rect
                    if rect.width > rect.height:
                        landscape_count += 1

                if landscape_count > (check_pages / 2):
                    is_ppt = True
                    ppt_confidence = "medium (landscape orientation)"

            doc.close()

            if is_ppt:
                yield create_upload_sse_event(
                    "warning",
                    {
                        "phase": "detection",
                        "message": f"⚠️ 偵測到 PPT 轉 PDF 檔案 (信心度: {ppt_confidence})",
                        "file_type": "PPT",
                        "confidence": ppt_confidence,
                        "note": "PPT 轉檔的 PDF 可能導致文字提取品質較差，建議使用原始 PDF 或重新匯出",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "elapsed": elapsed(),
                    },
                )
                logger.warning(
                    f"PPT-converted PDF detected: {pdf_path.name} ({ppt_confidence})"
                )
            else:
                yield create_upload_sse_event(
                    "info",
                    {
                        "phase": "detection",
                        "message": "✓ 一般 PDF 文檔",
                        "file_type": "General_Document",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "elapsed": elapsed(),
                    },
                )

        except Exception as e:
            logger.warning(
                f"PPT detection failed: {e}, continuing with standard processing"
            )
            yield create_upload_sse_event(
                "info",
                {
                    "phase": "detection",
                    "message": "使用標準 PDF 處理流程",
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "elapsed": elapsed(),
                },
            )

        # === PHASE 1: Start Producer-Consumer Pipeline ===
        BATCH_SIZE = 6  # Batch size for embedding (GPU bound)
        MAX_RETRIES = 3
        QUEUE_SIZE = 10  # Max batches in RAM (backpressure control)

        # Create queue for producer-consumer communication
        batch_queue = queue.Queue(maxsize=QUEUE_SIZE)

        # Start Producer Thread (reads PDF in background)
        producer_thread = threading.Thread(
            target=_producer_loop,
            args=(pdf_path, batch_queue, BATCH_SIZE, is_ppt, logger),
            daemon=True,
        )
        producer_thread.start()

        yield create_upload_sse_event(
            "phase_start",
            {
                "phase": "pipeline",
                "message": f"📄 啟動處理管道 (批次大小: {BATCH_SIZE})",
                "batch_size": BATCH_SIZE,
                "queue_size": QUEUE_SIZE,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        logger.info(f"Producer thread started for {pdf_path.name}")

        # === PHASE 2 & 3: Consumer Loop (Read from Queue + Embed) ===
        all_chunks = []
        all_embeddings = []
        embedding_dimension = 1024
        doc_id = f"doc_{hashlib.md5(pdf_path.name.encode()).hexdigest()[:16]}"

        batch_num = 0
        total_pages = 0  # Will be updated as we receive batches

        while True:
            # Non-blocking get with timeout (keep connection alive)
            try:
                batch = await asyncio.to_thread(batch_queue.get, timeout=1.0)
            except queue.Empty:
                # Yield heartbeat to keep SSE connection alive
                yield create_upload_sse_event(
                    "heartbeat",
                    {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "elapsed": elapsed(),
                    },
                )
                continue

            # Check for end of stream (sentinel value)
            if batch is None:
                logger.info("Consumer: Received end-of-stream sentinel")
                break

            # Check for error from producer
            if "error" in batch:
                logger.error(f"Consumer: Producer error: {batch['error']}")
                yield create_upload_sse_event(
                    "error",
                    {
                        "phase": "producer",
                        "message": f"❌ PDF 讀取失敗: {batch['error']}",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "elapsed": elapsed(),
                    },
                )
                raise HTTPException(
                    status_code=500, detail=f"Producer error: {batch['error']}"
                )

            # Process batch
            batch_texts = batch["texts"]
            batch_pages = batch["pages"]
            batch_num += 1

            logger.info(
                f"Consumer: Processing batch {batch_num} ({len(batch_texts)} texts, pages {batch_pages[0]}-{batch_pages[-1]})"
            )

            # Calculate progress for batch start (slightly before batch_complete)
            batch_start_progress = 10
            if total_pages_count > 0:
                batch_start_progress = 10 + int(
                    (batch_pages[0] / total_pages_count) * 70
                )  # Estimate

            # Yield batch start event
            yield create_upload_sse_event(
                "checkpoint",
                {
                    "phase": "batch_start",
                    "message": f"📄 處理批次 {batch_num} (頁面 {batch_pages[0]}-{batch_pages[-1]})",
                    "batch_num": batch_num,
                    "batch_size": len(batch_texts),
                    "pages": f"{batch_pages[0]}-{batch_pages[-1]}",
                    "percent": batch_start_progress,  # ✅ Add progress percentage
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "elapsed": elapsed(),
                },
            )

            # Create chunks for this batch
            batch_chunks = []
            for idx, (page_text, page_num) in enumerate(zip(batch_texts, batch_pages)):
                chunk_id = f"{skill_id}_{doc_id}_p{page_num}"
                chunk_metadata = {
                    "chunk_id": chunk_id,
                    "skill_id": skill_id,
                    "document_id": doc_id,
                    "document_name": pdf_path.stem,
                    "page_number": page_num,
                    "chunk_index": len(all_chunks) + idx,
                    "embedding_model": "BAAI/bge-m3",
                    "embedding_dimension": embedding_dimension,
                }
                batch_chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "content": page_text,
                        "metadata": chunk_metadata,
                    }
                )

            # Generate embeddings for this batch with retry
            retry_count = 0
            batch_embeddings = None

            while retry_count < MAX_RETRIES:
                try:
                    yield create_upload_sse_event(
                        "progress",
                        {
                            "phase": "embedding",
                            "message": f"🧠 嵌入批次 {batch_num} (嘗試 {retry_count + 1}/{MAX_RETRIES})",
                            "batch_num": batch_num,
                            "batch_pages": f"{batch_pages[0]}-{batch_pages[-1]}",
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "elapsed": elapsed(),
                        },
                    )

                    # GPU embedding generation
                    batch_embeddings = embedding_provider.embed_texts(
                        texts=batch_texts,
                        batch_size=len(batch_texts),
                        normalize=True,
                        show_progress=False,
                    )

                    logger.info(
                        f"✅ Batch {batch_num} embedded successfully: {len(batch_embeddings)} embeddings"
                    )
                    break  # Success!

                except Exception as e:
                    retry_count += 1
                    logger.error(
                        f"❌ Batch {batch_num} embedding failed (attempt {retry_count}/{MAX_RETRIES}): {str(e)}"
                    )

                    if retry_count >= MAX_RETRIES:
                        yield create_upload_sse_event(
                            "error",
                            {
                                "phase": "embedding",
                                "message": f"❌ 批次 {batch_num} 嵌入失敗 (已重試 {MAX_RETRIES} 次): {str(e)}",
                                "batch_pages": f"{batch_pages[0]}-{batch_pages[-1]}",
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                                "elapsed": elapsed(),
                            },
                        )
                        raise HTTPException(
                            status_code=500,
                            detail=f"Embedding failed at batch {batch_num} after {MAX_RETRIES} retries",
                        )

                    # Exponential backoff
                    wait_time = 2**retry_count
                    await asyncio.sleep(wait_time)

            # Successfully processed this batch
            all_chunks.extend(batch_chunks)
            all_embeddings.extend(batch_embeddings)
            total_pages = max(total_pages, batch_pages[-1])

            # Calculate progress percentage (10% start, 90% end for processing phase)
            # Progress mapping: 10% (start) → 80% (embedding complete)
            progress_percent = 10
            if total_pages_count > 0:
                progress_percent = 10 + int(
                    (total_pages / total_pages_count) * 70
                )  # 10-80%

            # Yield checkpoint event
            yield create_upload_sse_event(
                "checkpoint",
                {
                    "phase": "batch_complete",
                    "message": f"✅ 批次 {batch_num} 完成 (累計 {len(all_chunks)} chunks)",
                    "batch_num": batch_num,
                    "total_chunks": len(all_chunks),
                    "total_embeddings": len(all_embeddings),
                    "page": total_pages,  # Fix: Add 'page' field for frontend compatibility
                    "pages_processed": total_pages,
                    "percent": progress_percent,  # ✅ Add progress percentage
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "elapsed": elapsed(),
                },
            )

        logger.info(
            f"✅ Consumer finished: {len(all_chunks)} chunks, {len(all_embeddings)} embeddings"
        )

        # === PHASE 4: Store FAISS ===
        yield create_upload_sse_event(
            "progress",
            {
                "phase": "storage",
                "message": "💾 儲存向量索引...",
                "percent": 90,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        documents = [chunk["content"] for chunk in all_chunks]
        metadatas = [chunk["metadata"] for chunk in all_chunks]

        vector_provider.create_store_from_texts(
            texts=documents,
            embeddings=embedding_provider,  # Pass embedding provider instance
            metadatas=metadatas,
            file_id=skill_id,
            store_type="skill",
            precomputed_embeddings=all_embeddings,  # Pass pre-computed embeddings
        )

        logger.info(f"✅ Stored {len(all_embeddings)} vectors in FAISS")

        # === PHASE 5: Store metadata ===
        source_name = pdf_path.stem
        await metadata_provider.create_skill(
            skill_id=skill_id,
            skill_name=skill_name,
            skill_description=skill_description,
            skill_category=skill_category,
            skill_level="professional",
            tags=[skill_category.lower()],
            total_chunks=len(all_chunks),
            metadata={
                "embedding_model": "BAAI/bge-m3",
                "embedding_dimension": embedding_dimension,
                "source_file": str(pdf_path),
                "is_per_pdf_child": True,
                "batch_size": BATCH_SIZE,
                "max_retries": MAX_RETRIES,
            },
            parent_skill_id=parent_skill_id,
            source_name=source_name,
            head_id=head_id,
        )

        # Update processing status with indexed chunks count
        await metadata_provider.update_processing_status(
            skill_id=skill_id, status="completed", indexed_chunks=len(all_embeddings)
        )

        # Insert document mapping and chunk metadata
        db_path = Path("data/skill_metadata.db")
        conn = sqlite3.connect(db_path, timeout=30.0)  # Wait up to 30s for lock
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO skill_document_mapping
            (skill_id, file_id, document_name, document_path, total_pages, relevance_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (skill_id, doc_id, pdf_path.stem, str(pdf_path), total_pages, 1.0),
        )

        # Insert chunk metadata (CRITICAL for retrieval!)
        yield create_upload_sse_event(
            "progress",
            {
                "phase": "metadata",
                "message": f"💾 儲存 {len(all_chunks)} 個 chunk 元資料...",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        for chunk in all_chunks:
            chunk_meta = chunk["metadata"]
            cursor.execute(
                """
                INSERT OR REPLACE INTO skill_chunk_metadata
                (chunk_id, skill_id, document_id, document_name, page_number,
                 chunk_index, chunk_text, embedding_model, embedding_dimension, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    chunk_meta["chunk_id"],
                    skill_id,
                    chunk_meta["document_id"],
                    chunk_meta["document_name"],
                    chunk_meta["page_number"],
                    chunk_meta["chunk_index"],
                    chunk["content"][:2000],  # Store first 2000 chars of chunk text
                    "BAAI/bge-m3",
                    embedding_dimension,
                    json.dumps(chunk_meta),
                ),
            )

        conn.commit()
        conn.close()
        logger.info(
            f"✅ Inserted document mapping and {len(all_chunks)} chunk metadata for skill {skill_id}"
        )

        total_time = time.time() - start_time
        yield create_upload_sse_event(
            "complete",
            {
                "message": "🎉 處理完成!",
                "skill_id": skill_id,
                "skill_name": skill_name,
                "document_name": pdf_path.stem,
                "total_pages": total_pages,
                "total_chunks": len(all_chunks),
                "indexed_chunks": len(all_embeddings),
                "success_rate": f"{len(all_embeddings) / len(all_chunks) * 100:.1f}%",
                "embedding_model": "BAAI/bge-m3",
                "batch_size": BATCH_SIZE,
                "total_time": f"{total_time:.1f}s",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

    except Exception as e:
        logger.error(f"PDF processing failed: {e}")
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


async def process_document_for_skill_streaming(
    file_path: Path,
    file_content: bytes,
    skill_name: str,
    skill_description: str,
    skill_category: str = "General",
    parent_skill_id: str = "root",
    head_id: str = None,
):
    """
    Non-PDF document processing with SSE streaming progress.

    Handles DOCX, PPTX, TXT, MD files using InputDataHandleService for text extraction,
    then follows the same embedding → FAISS → metadata pipeline as PDF processing.

    Uses the same SSE event format as process_pdf_for_skill_streaming() so the frontend
    does not need any SSE parsing changes.

    Yields SSE events for each processing step.
    """
    import time

    start_time = time.time()

    def elapsed():
        return f"{time.time() - start_time:.1f}s"

    # Initialize providers
    vector_provider = VectorStoreProvider(persist_directory="./data/faiss_indices")
    metadata_provider = SkillMetadataProvider(db_path="./data/skill_metadata.db")
    embedding_provider = get_embedding_provider()
    input_service = InputDataHandleService()

    # Generate skill ID
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name_hash = hashlib.md5(skill_name.encode("utf-8")).hexdigest()[:8]
    file_hash = hashlib.md5(file_path.name.encode("utf-8")).hexdigest()[:6]
    skill_id = f"skill_{timestamp}_{name_hash}_{file_hash}"

    BATCH_SIZE = 6
    MAX_RETRIES = 3

    # Yield initial event
    yield create_upload_sse_event(
        "start",
        {
            "message": f"開始處理 {file_path.name}",
            "filename": file_path.name,
            "skill_id": skill_id,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "elapsed": elapsed(),
        },
    )

    try:
        # === PHASE 1: Text Extraction ===
        yield create_upload_sse_event(
            "progress",
            {
                "phase": "extraction",
                "message": f"📄 正在提取文字 ({file_path.suffix.upper()})...",
                "percent": 10,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        try:
            corpus, page_count = input_service.extract_text(
                file_content, file_path.name
            )
        except ValueError as e:
            if "密碼保護" in str(e):
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
            raise

        yield create_upload_sse_event(
            "progress",
            {
                "phase": "extraction_complete",
                "message": f"✅ 文字提取完成 ({len(corpus)} 字元)",
                "percent": 25,
                "characters": len(corpus),
                "pages": page_count,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        # === PHASE 2: Chunking ===
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

        # Use page-based chunking: split corpus into chunks
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            separators=["\n\n", "\n", "。", ".", " ", ""],
        )
        text_chunks = text_splitter.split_text(corpus)

        doc_id = f"doc_{hashlib.md5(file_path.name.encode()).hexdigest()[:16]}"
        embedding_dimension = 1024

        all_chunks = []
        for idx, chunk_text in enumerate(text_chunks):
            chunk_id = f"{skill_id}_{doc_id}_c{idx}"
            chunk_metadata = {
                "chunk_id": chunk_id,
                "skill_id": skill_id,
                "document_id": doc_id,
                "document_name": file_path.stem,
                "page_number": idx + 1,
                "chunk_index": idx,
                "embedding_model": "BAAI/bge-m3",
                "embedding_dimension": embedding_dimension,
            }
            all_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "content": chunk_text,
                    "metadata": chunk_metadata,
                }
            )

        yield create_upload_sse_event(
            "checkpoint",
            {
                "phase": "chunking_complete",
                "message": f"✅ 分割完成 ({len(all_chunks)} 個 chunks)",
                "total_chunks": len(all_chunks),
                "percent": 35,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        # === PHASE 3: Batch Embedding ===
        all_embeddings = []
        total_batches = (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE

        for batch_idx in range(0, len(all_chunks), BATCH_SIZE):
            batch_end = min(batch_idx + BATCH_SIZE, len(all_chunks))
            batch_chunks_slice = all_chunks[batch_idx:batch_end]
            batch_texts = [c["content"] for c in batch_chunks_slice]
            batch_num = batch_idx // BATCH_SIZE + 1

            # Calculate progress: 35% to 80%
            progress_percent = 35 + int((batch_num / total_batches) * 45)

            retry_count = 0
            batch_embeddings = None

            while retry_count < MAX_RETRIES:
                try:
                    yield create_upload_sse_event(
                        "progress",
                        {
                            "phase": "embedding",
                            "message": f"🧠 嵌入批次 {batch_num}/{total_batches}",
                            "batch_num": batch_num,
                            "percent": progress_percent,
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "elapsed": elapsed(),
                        },
                    )

                    batch_embeddings = embedding_provider.embed_texts(
                        texts=batch_texts,
                        batch_size=len(batch_texts),
                        normalize=True,
                        show_progress=False,
                    )
                    break  # Success

                except Exception as e:
                    retry_count += 1
                    logger.error(
                        f"Batch {batch_num} embedding failed (attempt {retry_count}/{MAX_RETRIES}): {str(e)}"
                    )
                    if retry_count >= MAX_RETRIES:
                        yield create_upload_sse_event(
                            "error",
                            {
                                "phase": "embedding",
                                "message": f"❌ 批次 {batch_num} 嵌入失敗: {str(e)}",
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                                "elapsed": elapsed(),
                            },
                        )
                        raise
                    wait_time = 2**retry_count
                    await asyncio.sleep(wait_time)

            all_embeddings.extend(batch_embeddings)

            yield create_upload_sse_event(
                "checkpoint",
                {
                    "phase": "batch_complete",
                    "message": f"✅ 批次 {batch_num}/{total_batches} 完成",
                    "batch_num": batch_num,
                    "total_chunks": len(all_embeddings),
                    "total_embeddings": len(all_embeddings),
                    "percent": progress_percent,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "elapsed": elapsed(),
                },
            )

        # === PHASE 4: Store FAISS ===
        yield create_upload_sse_event(
            "progress",
            {
                "phase": "storage",
                "message": "💾 儲存向量索引...",
                "percent": 85,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        documents = [chunk["content"] for chunk in all_chunks]
        metadatas = [chunk["metadata"] for chunk in all_chunks]

        vector_provider.create_store_from_texts(
            texts=documents,
            embeddings=embedding_provider,
            metadatas=metadatas,
            file_id=skill_id,
            store_type="skill",
            precomputed_embeddings=all_embeddings,
        )

        logger.info(
            f"Stored {len(all_embeddings)} vectors in FAISS for {file_path.name}"
        )

        # === PHASE 5: Store metadata ===
        yield create_upload_sse_event(
            "progress",
            {
                "phase": "metadata",
                "message": f"💾 儲存元資料...",
                "percent": 90,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        source_name = file_path.stem
        await metadata_provider.create_skill(
            skill_id=skill_id,
            skill_name=skill_name,
            skill_description=skill_description,
            skill_category=skill_category,
            skill_level="professional",
            tags=[skill_category.lower()],
            total_chunks=len(all_chunks),
            metadata={
                "embedding_model": "BAAI/bge-m3",
                "embedding_dimension": embedding_dimension,
                "source_file": str(file_path),
                "is_per_pdf_child": True,
                "batch_size": BATCH_SIZE,
                "max_retries": MAX_RETRIES,
            },
            parent_skill_id=parent_skill_id,
            source_name=source_name,
            head_id=head_id,
        )

        await metadata_provider.update_processing_status(
            skill_id=skill_id, status="completed", indexed_chunks=len(all_embeddings)
        )

        # Insert document mapping and chunk metadata
        db_path = Path("data/skill_metadata.db")
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO skill_document_mapping
            (skill_id, file_id, document_name, document_path, total_pages, relevance_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (skill_id, doc_id, file_path.stem, str(file_path), page_count, 1.0),
        )

        yield create_upload_sse_event(
            "progress",
            {
                "phase": "metadata",
                "message": f"💾 儲存 {len(all_chunks)} 個 chunk 元資料...",
                "percent": 95,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

        for chunk in all_chunks:
            chunk_meta = chunk["metadata"]
            cursor.execute(
                """
                INSERT OR REPLACE INTO skill_chunk_metadata
                (chunk_id, skill_id, document_id, document_name, page_number,
                 chunk_index, chunk_text, embedding_model, embedding_dimension, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    chunk_meta["chunk_id"],
                    skill_id,
                    chunk_meta["document_id"],
                    chunk_meta["document_name"],
                    chunk_meta["page_number"],
                    chunk_meta["chunk_index"],
                    chunk["content"][:2000],
                    "BAAI/bge-m3",
                    embedding_dimension,
                    json.dumps(chunk_meta),
                ),
            )

        conn.commit()
        conn.close()
        logger.info(
            f"Inserted document mapping and {len(all_chunks)} chunk metadata for skill {skill_id}"
        )

        total_time = time.time() - start_time
        yield create_upload_sse_event(
            "complete",
            {
                "message": "🎉 處理完成!",
                "skill_id": skill_id,
                "skill_name": skill_name,
                "document_name": file_path.stem,
                "total_pages": page_count,
                "total_chunks": len(all_chunks),
                "indexed_chunks": len(all_embeddings),
                "success_rate": f"{len(all_embeddings) / len(all_chunks) * 100:.1f}%",
                "embedding_model": "BAAI/bge-m3",
                "batch_size": BATCH_SIZE,
                "total_time": f"{total_time:.1f}s",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "elapsed": elapsed(),
            },
        )

    except Exception as e:
        logger.error(f"Document processing failed for {file_path.name}: {e}")
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


@router.post("/config/skills/{skill_name}/upload-source-stream")
async def upload_source_to_skill_stream(
    skill_name: str,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Upload a PDF file with SSE streaming progress.
    Returns real-time progress updates via Server-Sent Events.
    """
    # 1. Validate File — strip directory components (webkitdirectory sends relative paths)
    safe_filename = Path(file.filename).name
    file_ext = Path(safe_filename).suffix.lower().lstrip(".")
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的檔案格式: '.{file_ext}'。支援格式: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )

    # 2. Save File first (synchronously to get the path)
    upload_dir = PROJECT_ROOT / "uploadfiles" / file_ext
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / safe_filename

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    logger.info(f"Uploaded source file for streaming: {file_path}")

    # 3. Get skill metadata
    skill_description = description or safe_filename
    skill_category = "General"
    head_id = None
    parent_skill_id = "root"

    try:
        skill_heads = await metadata_provider.list_skill_heads(enabled_only=False)
        skill_head = next(
            (h for h in skill_heads if h["skill_name"] == skill_name), None
        )

        if skill_head:
            head_id = skill_head["head_id"]
            skill_description = skill_head.get("description", skill_description)
            skill_category = skill_head.get("category", skill_category)
        else:
            head_id = await metadata_provider.create_skill_head(
                skill_name=skill_name,
                description=skill_description,
                category=skill_category,
            )

        # Find parent skill
        all_skills = await metadata_provider.list_skills()
        for skill in all_skills:
            if (
                skill.get("skill_name") == skill_name
                and skill.get("parent_skill_id") == "root"
                and skill.get("skill_id") != "root"
            ):
                parent_skill_id = skill.get("skill_id")
                break

    except Exception as e:
        logger.error(f"Error accessing skill_heads: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to access skill metadata: {str(e)}"
        )

    # 4. Create SSE event generator
    async def generate_sse_events():
        # Yield file saved event first
        yield create_upload_sse_event(
            "file_saved",
            {
                "message": f"📁 檔案已保存: {safe_filename}",
                "filename": safe_filename,
                "size": len(content),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            },
        )

        # Format-based routing: PDF uses Producer-Consumer, others use unified pipeline
        file_ext = Path(safe_filename).suffix.lower().lstrip(".")
        if file_ext == "pdf":
            async for event in process_pdf_for_skill_streaming(
                pdf_path=file_path,
                skill_name=skill_name,
                skill_description=skill_description,
                skill_category=skill_category,
                parent_skill_id=parent_skill_id,
                head_id=head_id,
            ):
                yield event
        else:
            async for event in process_document_for_skill_streaming(
                file_path=file_path,
                file_content=content,
                skill_name=skill_name,
                skill_description=skill_description,
                skill_category=skill_category,
                parent_skill_id=parent_skill_id,
                head_id=head_id,
            ):
                yield event

    return EventSourceResponse(generate_sse_events(), ping=15)


@router.post("/config/skills/{skill_name}/upload-source")
async def upload_source_to_skill(
    skill_name: str,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Upload a PDF file with SSE streaming progress (統一串流模式).

    All PDF uploads now use the same Generator-based streaming pipeline for:
    - Consistent UX (real-time progress updates)
    - Memory efficiency (O(batch_size) regardless of PDF size)
    - Checkpoint/resume support for large files

    Returns Server-Sent Events with progress updates.
    """
    # 1. Validate File — strip directory components (webkitdirectory sends relative paths)
    safe_filename = Path(file.filename).name
    file_ext = Path(safe_filename).suffix.lower().lstrip(".")
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的檔案格式: '.{file_ext}'。支援格式: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )

    # 2. Save File first (synchronously to get the path)
    upload_dir = PROJECT_ROOT / "uploadfiles" / file_ext
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / safe_filename

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    logger.info(f"Uploaded source file: {file_path} for skill {skill_name}")

    # 3. Get skill metadata from skill_heads table (SQLite - Single Source of Truth)
    skill_description = description or safe_filename
    skill_category = "General"
    head_id = None
    parent_skill_id = "root"

    try:
        # Find skill_head by name
        skill_heads = await metadata_provider.list_skill_heads(enabled_only=False)
        skill_head = next(
            (h for h in skill_heads if h["skill_name"] == skill_name), None
        )

        if skill_head:
            head_id = skill_head["head_id"]
            skill_description = skill_head.get("description", skill_description)
            skill_category = skill_head.get("category", skill_category)
            logger.info(f"Found skill_head for '{skill_name}': head_id={head_id}")
        else:
            # Skill head not found - create one automatically
            head_id = await metadata_provider.create_skill_head(
                skill_name=skill_name,
                description=skill_description,
                category=skill_category,
            )
            logger.info(f"Created new skill_head for '{skill_name}': head_id={head_id}")

        # Find existing main skill to link as parent (3-level tree hierarchy)
        all_skills = await metadata_provider.list_skills()
        for skill in all_skills:
            if (
                skill.get("skill_name") == skill_name
                and skill.get("parent_skill_id") == "root"
                and skill.get("skill_id") != "root"
            ):
                parent_skill_id = skill.get("skill_id")
                logger.info(
                    f"Found main skill '{skill_name}' with ID: {parent_skill_id}"
                )
                break

        if parent_skill_id == "root":
            logger.info(
                f"No existing main skill found for '{skill_name}', creating as top-level skill"
            )

    except Exception as e:
        logger.error(f"Error accessing skill_heads: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to access skill metadata: {str(e)}"
        )

    # 4. Create SSE event generator (統一串流模式)
    async def generate_sse_events():
        # Yield file saved event first
        yield create_upload_sse_event(
            "file_saved",
            {
                "message": f"📁 檔案已保存: {safe_filename}",
                "filename": safe_filename,
                "size": len(content),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            },
        )

        # Format-based routing: PDF uses Producer-Consumer, others use unified pipeline
        file_ext = Path(safe_filename).suffix.lower().lstrip(".")
        if file_ext == "pdf":
            async for event in process_pdf_for_skill_streaming(
                pdf_path=file_path,
                skill_name=skill_name,
                skill_description=skill_description,
                skill_category=skill_category,
                parent_skill_id=parent_skill_id,
                head_id=head_id,
            ):
                yield event
        else:
            async for event in process_document_for_skill_streaming(
                file_path=file_path,
                file_content=content,
                skill_name=skill_name,
                skill_description=skill_description,
                skill_category=skill_category,
                parent_skill_id=parent_skill_id,
                head_id=head_id,
            ):
                yield event

    return EventSourceResponse(generate_sse_events(), ping=15)


@router.delete("/config/skills/{skill_name}/sources")
async def remove_source_from_skill(skill_name: str, path: str = Body(..., embed=True)):
    """
    Remove a PDF source from a skill.
    """
    config = load_skill_config()
    skills = config.get("skills", [])

    skill_found = False
    source_removed = False

    for skill in skills:
        if skill.get("skill_name") == skill_name:
            skill_found = True
            sources = skill.get("sources", [])
            original_count = len(sources)
            skill["sources"] = [s for s in sources if s.get("path") != path]
            source_removed = len(skill["sources"]) < original_count
            break

    if not skill_found:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    if not source_removed:
        raise HTTPException(
            status_code=404, detail=f"Source '{path}' not found in skill"
        )

    save_skill_config(config)

    return {"message": f"Source removed from skill '{skill_name}'"}


# =============================================================================
# DELETE Skill by Name API - Complete Removal from Database + FAISS
# =============================================================================


@router.delete("/config/skills/{skill_name}")
async def delete_skill_by_name(
    skill_name: str,
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Complete deletion of a skill by name including all related resources:

    1. skill_heads table - Remove skill head definition (new architecture)
    2. SQLite Database - Delete all records with matching skill_name
    3. FAISS Indices - Delete all vector stores for this skill
    4. (Optional) PDF Files - NOT deleted by default (may be shared)

    NOTE: This endpoint is deprecated. Use DELETE /heads/{head_id} instead.
    This endpoint no longer depends on skill_config.json.
    """
    logger.info(f"Starting complete deletion for skill_name: {skill_name}")

    deletion_results = {
        "skill_name": skill_name,
        "head_deleted": False,
        "faiss_deleted": False,
        "sqlite_deleted": False,
        "skill_ids_deleted": [],
        "chunks_deleted": 0,
        "docs_deleted": 0,
        "pdfs_deleted": 0,
        "errors": [],
    }

    skill_head = None
    head_id = None

    try:
        # 1. Remove from skill_heads table (new architecture - single source of truth)
        try:
            skill_heads = await metadata_provider.list_skill_heads(enabled_only=False)
            skill_head = next(
                (h for h in skill_heads if h["skill_name"] == skill_name), None
            )

            if skill_head:
                head_id = skill_head["head_id"]
                await metadata_provider.delete_skill_head(head_id)
                deletion_results["head_deleted"] = True
                logger.info(f"Removed skill head '{skill_name}' (head_id={head_id})")
            else:
                logger.warning(
                    f"Skill head '{skill_name}' not found in skill_heads table"
                )
                deletion_results["errors"].append(f"Skill head not found")

        except Exception as e:
            logger.error(f"Failed to delete from skill_heads: {e}")
            deletion_results["errors"].append(f"Skill head deletion error: {str(e)}")

        # 2. Find all skill_ids linked to this skill via head_id or skill_name
        try:
            db_path = PROJECT_ROOT / "data" / "skill_metadata.db"
            conn = sqlite3.connect(
                str(db_path), timeout=30.0
            )  # Wait up to 30s for lock
            cursor = conn.cursor()

            # Prefer head_id lookup (more reliable than skill_name which may be duplicated)
            if skill_head and head_id:
                cursor.execute(
                    "SELECT skill_id FROM skill_metadata WHERE head_id = ?",
                    (head_id,),
                )
            else:
                # Fallback: use skill_name if head was not found
                cursor.execute(
                    "SELECT skill_id FROM skill_metadata WHERE skill_name = ?",
                    (skill_name,),
                )
            skill_ids = [row[0] for row in cursor.fetchall()]
            deletion_results["skill_ids_deleted"] = skill_ids
            logger.info(f"Found {len(skill_ids)} skill entries to delete: {skill_ids}")

            conn.close()

        except Exception as e:
            logger.error(f"Failed to query SQLite: {e}")
            deletion_results["errors"].append(f"SQLite query error: {str(e)}")
            skill_ids = []

        # 3. Delete FAISS indices for each skill_id
        import shutil

        for skill_id in skill_ids:
            try:
                faiss_path = (
                    PROJECT_ROOT / "data" / "faiss_indices" / "skills" / skill_id
                )
                if faiss_path.exists():
                    shutil.rmtree(faiss_path)
                    logger.info(f"Deleted FAISS index: {faiss_path}")
                else:
                    logger.warning(f"FAISS index not found: {faiss_path}")
            except Exception as e:
                logger.error(f"Failed to delete FAISS for {skill_id}: {e}")
                deletion_results["errors"].append(
                    f"FAISS deletion error ({skill_id}): {str(e)}"
                )

        deletion_results["faiss_deleted"] = len(skill_ids) > 0

        # 4. Delete SQLite records for each skill_id
        try:
            db_path = PROJECT_ROOT / "data" / "skill_metadata.db"
            conn = sqlite3.connect(
                str(db_path), timeout=30.0
            )  # Wait up to 30s for lock
            cursor = conn.cursor()

            total_chunks = 0
            total_docs = 0
            total_overviews = 0

            for skill_id in skill_ids:
                # Delete from skill_chunk_metadata
                cursor.execute(
                    "DELETE FROM skill_chunk_metadata WHERE skill_id = ?", (skill_id,)
                )
                total_chunks += cursor.rowcount

                # Delete from skill_document_mapping
                cursor.execute(
                    "DELETE FROM skill_document_mapping WHERE skill_id = ?", (skill_id,)
                )
                total_docs += cursor.rowcount

                # Delete from skill_overviews (overview/summary data)
                cursor.execute(
                    "DELETE FROM skill_overviews WHERE skill_id = ?", (skill_id,)
                )
                total_overviews += cursor.rowcount

                # Delete from skill_metadata
                cursor.execute(
                    "DELETE FROM skill_metadata WHERE skill_id = ?", (skill_id,)
                )
                logger.info(f"Deleted SQLite records for {skill_id}")

            conn.commit()
            conn.close()

            deletion_results["sqlite_deleted"] = True
            deletion_results["chunks_deleted"] = total_chunks
            deletion_results["docs_deleted"] = total_docs
            deletion_results["overviews_deleted"] = total_overviews
            logger.info(
                f"Deleted {total_chunks} chunks, {total_docs} docs, {total_overviews} overviews from SQLite"
            )

        except Exception as e:
            logger.error(f"Failed to delete SQLite records: {e}")
            deletion_results["errors"].append(f"SQLite deletion error: {str(e)}")

        # Determine overall success
        # ✅ FIX: Removed config_deleted (old JSON dependency)
        # SQLite deletion is the source of truth for new architecture
        all_success = (
            deletion_results["head_deleted"]
            or deletion_results["sqlite_deleted"]
            or deletion_results["faiss_deleted"]
        )

        if all_success:
            logger.info(f"Successfully deleted skill '{skill_name}'")
            return {
                "success": True,
                "message": f"Successfully deleted skill '{skill_name}'",
                **deletion_results,
            }
        else:
            logger.warning(f"No data found for skill '{skill_name}'")
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{skill_name}' not found in config or database",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complete deletion failed for {skill_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")


@router.get("/config/instant-attachments")
async def get_instant_attachments():
    """
    Get list of instant attachments (temporary PDFs pending rebuild).
    """
    config = load_skill_config()
    attachments = config.get("instant_attachments", [])
    threshold = config.get("settings", {}).get("rebuild_threshold", 5)

    # Enrich with file info
    enriched = []
    for att in attachments:
        att_path = PROJECT_ROOT / att.get("path", "")
        enriched.append(
            {
                **att,
                "exists": att_path.exists(),
                "filename": Path(att.get("path", "")).name,
                "size_mb": round(att_path.stat().st_size / (1024 * 1024), 2)
                if att_path.exists()
                else 0,
            }
        )

    return {
        "attachments": enriched,
        "count": len(attachments),
        "threshold": threshold,
        "needs_rebuild": len(attachments) >= threshold,
    }


@router.post("/config/instant-attachments")
async def add_instant_attachment(request: InstantAttachmentRequest):
    """
    Add an instant attachment (temporary PDF).
    When count reaches threshold, user should trigger rebuild.
    """
    config = load_skill_config()
    attachments = config.get("instant_attachments", [])
    threshold = config.get("settings", {}).get("rebuild_threshold", 5)

    # Check if file exists
    att_path = PROJECT_ROOT / request.path
    if not att_path.exists():
        raise HTTPException(
            status_code=400, detail=f"PDF file not found: {request.path}"
        )

    # Check if already exists
    for att in attachments:
        if att.get("path") == request.path:
            raise HTTPException(status_code=400, detail="Attachment already exists")

    # Add attachment
    new_attachment = {
        "skill_name": request.skill_name,
        "path": request.path,
        "description": request.description,
        "added_at": datetime.now().isoformat(),
    }
    attachments.append(new_attachment)
    config["instant_attachments"] = attachments

    save_skill_config(config)

    # Check if rebuild needed
    needs_rebuild = len(attachments) >= threshold

    return {
        "message": "Instant attachment added",
        "attachment": new_attachment,
        "count": len(attachments),
        "threshold": threshold,
        "needs_rebuild": needs_rebuild,
        "warning": "建議執行 rebuild 以避免資料碎片化" if needs_rebuild else None,
    }


@router.delete("/config/instant-attachments")
async def clear_instant_attachments():
    """
    Clear all instant attachments (usually after rebuild).
    """
    config = load_skill_config()
    cleared_count = len(config.get("instant_attachments", []))
    config["instant_attachments"] = []

    save_skill_config(config)

    return {"message": f"Cleared {cleared_count} instant attachments"}


class RebuildThresholdRequest(BaseModel):
    """Request model for updating rebuild threshold"""

    rebuild_threshold: int = Field(
        ..., ge=1, le=50, description="New rebuild threshold (1-50)"
    )


@router.put("/config/rebuild-threshold")
async def update_rebuild_threshold(request: RebuildThresholdRequest):
    """
    Update the rebuild threshold value.
    The threshold determines when to automatically trigger a rebuild when instant attachments accumulate.

    Args:
        rebuild_threshold: New threshold value (1-50)

    Returns:
        Updated configuration with new threshold
    """
    try:
        config = load_skill_config()
        old_threshold = config.get("settings", {}).get("rebuild_threshold", 5)

        # Update threshold
        if "settings" not in config:
            config["settings"] = {}

        config["settings"]["rebuild_threshold"] = request.rebuild_threshold
        save_skill_config(config)

        logger.info(
            f"Rebuild threshold updated: {old_threshold} → {request.rebuild_threshold}"
        )

        return {
            "message": f"Rebuild threshold updated successfully",
            "old_threshold": old_threshold,
            "new_threshold": request.rebuild_threshold,
            "current_attachments": len(config.get("instant_attachments", [])),
            "will_trigger_rebuild": len(config.get("instant_attachments", []))
            >= request.rebuild_threshold,
        }
    except Exception as e:
        logger.error(f"Error updating rebuild threshold: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to update threshold: {str(e)}"
        )


# -----------------------------------------------------------------------------
# Skill Reorder Endpoint
# -----------------------------------------------------------------------------


class SkillOrderItem(BaseModel):
    """Model for skill order item"""

    skill_name: str
    display_order: int


class ReorderSkillsRequest(BaseModel):
    """Request model for reordering skills"""

    order: List[SkillOrderItem]


@router.put("/config/reorder")
async def reorder_skills(
    request: ReorderSkillsRequest,
    provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Update the display order of skills.
    This affects both the config page and the chat page.

    NEW: Uses skill_heads table (SQLite - Single Source of Truth)
    DEPRECATED: No longer uses skill_config.json (archived)

    Args:
        order: List of skill names with their new display_order values
        provider: SkillMetadataProvider dependency

    Returns:
        Updated skill list with new order
    """
    try:
        # NEW: Get all skill heads from database
        skill_heads = await provider.list_skill_heads()

        # Create a map of skill_name -> display_order
        order_map = {item.skill_name: item.display_order for item in request.order}

        # Update display_order for each skill head in database
        updated_skills = []
        for head in skill_heads:
            skill_name = head.get("skill_name")
            if skill_name in order_map:
                new_order = order_map[skill_name]
                head_id = head.get("head_id")

                # Update display_order in skill_heads table
                await provider.update_skill_head(
                    head_id=head_id, display_order=new_order
                )

                updated_skills.append(
                    {
                        "skill_name": skill_name,
                        "display_order": new_order,
                        "head_id": head_id,
                    }
                )

                logger.info(f"Updated {skill_name} display_order to {new_order}")

        logger.info(f"Skills reordered: {[s['skill_name'] for s in updated_skills]}")

        return {"message": "Skills reordered successfully", "skills": updated_skills}
    except Exception as e:
        logger.error(f"Error reordering skills: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to reorder skills: {str(e)}"
        )


@router.get("/available-pdfs")
async def get_available_pdfs(base_path: str = "refData"):
    """
    Get list of all available PDF files in the project.
    Supports directory browsing for file picker.

    Returns a hierarchical structure of directories and PDF files.
    """
    try:
        base_dir = PROJECT_ROOT / base_path

        if not base_dir.exists():
            raise HTTPException(
                status_code=404, detail=f"Directory not found: {base_path}"
            )

        def scan_directory(dir_path: Path, relative_prefix: str = "") -> Dict[str, Any]:
            """Recursively scan directory for PDFs and subdirectories"""
            result = {
                "name": dir_path.name or "root",
                "path": relative_prefix,
                "type": "directory",
                "files": [],
                "subdirs": [],
            }

            try:
                for item in sorted(dir_path.iterdir()):
                    # Skip hidden files and __pycache__
                    if item.name.startswith(".") or item.name == "__pycache__":
                        continue

                    rel_path = f"{relative_prefix}/{item.name}".lstrip("/")

                    if item.is_dir():
                        # Recursively scan subdirectories
                        subdir = scan_directory(item, rel_path)
                        if (
                            subdir["files"] or subdir["subdirs"]
                        ):  # Only include non-empty directories
                            result["subdirs"].append(subdir)

                    elif (
                        item.is_file()
                        and item.suffix.lower().lstrip(".")
                        in settings.ALLOWED_EXTENSIONS
                    ):
                        # Add PDF file info
                        try:
                            size_mb = round(item.stat().st_size / (1024 * 1024), 2)
                        except:
                            size_mb = 0

                        result["files"].append(
                            {
                                "name": item.name,
                                "path": rel_path,
                                "size_mb": size_mb,
                                "modified": item.stat().st_mtime,
                            }
                        )
            except PermissionError:
                pass

            return result

        pdf_tree = scan_directory(base_dir)

        # Flatten the tree into a simple list for the file picker
        all_pdfs = []

        def flatten_tree(node: Dict[str, Any]):
            for file_info in node.get("files", []):
                all_pdfs.append(
                    {
                        "path": f"{base_path}/{file_info['path']}",
                        "name": file_info["name"],
                        "size_mb": file_info["size_mb"],
                        "directory": node.get("path", ""),
                    }
                )

            for subdir in node.get("subdirs", []):
                flatten_tree(subdir)

        flatten_tree(pdf_tree)

        return {
            "base_path": base_path,
            "total_count": len(all_pdfs),
            "tree": pdf_tree,  # Hierarchical structure for directory browser
            "files": sorted(
                all_pdfs, key=lambda x: x["path"]
            ),  # Flat list for dropdown/search
            "categories": list(
                set(
                    f.get("directory", "").split("/")[0]
                    for f in all_pdfs
                    if f.get("directory")
                )
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scanning PDFs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to scan PDFs: {str(e)}")


@router.post("/rebuild")
async def trigger_rebuild(request: RebuildRequest, background_tasks: BackgroundTasks):
    """
    Trigger skill rebuild from configuration with optional smart strategy.
    Runs in background to avoid timeout.

    Smart strategy:
    - If no instant attachments: no rebuild
    - If < threshold attachments: wait for more
    - If >= threshold: only rebuild affected skills (smart mode)
    - After rebuild: auto-clear processed attachments
    """

    def run_rebuild():
        """Background task to run rebuild with smart strategy"""
        try:
            config_path = str(
                PROJECT_ROOT / "scripts" / "skill_data" / "skill_config.json"
            )

            # Prepare environment variables for smart rebuild
            env = os.environ.copy()
            env["SKILL_CONFIG_PATH"] = config_path

            if request.skill_name:
                env["SKILL_FILTER"] = request.skill_name

            if request.force_all:
                env["FORCE_ALL"] = "true"

            if request.use_smart_strategy:
                env["SMART_REBUILD"] = "true"
            else:
                env["SMART_REBUILD"] = "false"

            # Use Python directly instead of shell script for better control
            script_path = (
                PROJECT_ROOT / "scripts" / "skill_data" / "rebuild_from_config.py"
            )

            cmd = [sys.executable, str(script_path)]

            logger.info(
                f"Starting rebuild with smart strategy: {request.use_smart_strategy}"
            )
            logger.info(f"  Force all: {request.force_all}")
            logger.info(f"  Skill filter: {request.skill_name or 'None'}")

            result = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )

            if result.returncode == 0:
                logger.info("Rebuild completed successfully")

                # Smart cleanup: only clear if rebuild actually happened
                if request.use_smart_strategy:
                    # Check if rebuild actually processed anything
                    if (
                        "無需重建" not in result.stderr
                        and "無需重建" not in result.stdout
                    ):
                        config = load_skill_config()
                        if config.get("instant_attachments"):
                            old_count = len(config.get("instant_attachments", []))
                            config["instant_attachments"] = []
                            save_skill_config(config)
                            logger.info(
                                f"Auto-cleared {old_count} instant attachments after rebuild"
                            )
                else:
                    # Traditional mode: always clear after rebuild
                    config = load_skill_config()
                    if config.get("instant_attachments"):
                        old_count = len(config.get("instant_attachments", []))
                        config["instant_attachments"] = []
                        save_skill_config(config)
                        logger.info(
                            f"Cleared {old_count} instant attachments after rebuild"
                        )
            else:
                logger.error(f"Rebuild failed: {result.stderr}")
                # Log stdout as well for debugging
                if result.stdout:
                    logger.error(f"Rebuild stdout: {result.stdout}")

        except subprocess.TimeoutExpired:
            logger.error("Rebuild timeout (10 minutes exceeded)")
        except Exception as e:
            logger.error(f"Rebuild error: {e}")
            import traceback

            traceback.print_exc()

    # Add to background tasks
    background_tasks.add_task(run_rebuild)

    return {
        "message": "Rebuild started in background",
        "skill_filter": request.skill_name,
        "clean_first": request.clean_first,
        "use_smart_strategy": request.use_smart_strategy,
        "force_all": request.force_all,
        "status": "running",
    }


@router.get("/rebuild/status")
async def get_rebuild_status():
    """
    Check rebuild status by examining log file.
    """
    log_path = PROJECT_ROOT / "logs" / "rebuild_skills.log"

    status = {"log_exists": log_path.exists(), "last_modified": None, "recent_logs": []}

    if log_path.exists():
        status["last_modified"] = datetime.fromtimestamp(
            log_path.stat().st_mtime
        ).isoformat()

        # Read last 20 lines
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                status["recent_logs"] = [l.strip() for l in lines[-20:]]
        except Exception as e:
            status["error"] = str(e)

    return status


# =============================================================================
# Index Integrity Check API - Manual verification endpoint
# =============================================================================


@router.get("/integrity-check")
async def check_index_integrity(
    skill_id: Optional[str] = None,
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Manual integrity check endpoint

    Query params:
        skill_id: Optional - check specific skill, or all incomplete skills if omitted

    Returns:
        Integrity check results with diagnosis information
    """
    from app.SkillServices.index_integrity import (
        diagnose_incomplete_index,
        verify_index_integrity,
    )

    if skill_id:
        # Check single skill
        try:
            skill_metadata = await metadata_provider.get_skill(skill_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

        if not skill_metadata:
            raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

        expected_chunks = skill_metadata["total_chunks"]

        is_valid, actual_vectors, error = await verify_index_integrity(
            skill_id=skill_id, expected_chunks=expected_chunks
        )

        if not is_valid:
            diagnosis = await diagnose_incomplete_index(skill_id, expected_chunks)
            return {
                "skill_id": skill_id,
                "skill_name": skill_metadata.get("skill_name"),
                "status": "failed",
                "expected_chunks": expected_chunks,
                "actual_vectors": actual_vectors,
                "completion_percent": diagnosis["completion_percent"],
                "diagnosis": diagnosis,
                "error": error,
            }

        return {
            "skill_id": skill_id,
            "skill_name": skill_metadata.get("skill_name"),
            "status": "ok",
            "vectors": actual_vectors,
            "expected": expected_chunks,
            "completion_percent": 100.0,
        }

    else:
        # Check all incomplete skills
        incomplete_skills = await metadata_provider.get_incomplete_skills()

        results = []
        for skill in incomplete_skills:
            skill_id = skill["skill_id"]
            expected = skill["total_chunks"]

            is_valid, actual, error = await verify_index_integrity(skill_id, expected)

            results.append(
                {
                    "skill_id": skill_id,
                    "skill_name": skill["skill_name"],
                    "expected_chunks": expected,
                    "actual_vectors": actual,
                    "is_valid": is_valid,
                    "completion_percent": (actual / expected * 100)
                    if expected > 0
                    else 0,
                    "error": error,
                }
            )

        return {
            "total_skills_checked": len(incomplete_skills),
            "results": results,
            "summary": {
                "valid": sum(1 for r in results if r["is_valid"]),
                "invalid": sum(1 for r in results if not r["is_valid"]),
            },
        }


# =============================================================================
# Translation API - LLM-based translation for UI
# =============================================================================


class TranslationRequest(BaseModel):
    """Request model for translation"""

    texts: List[str] = Field(..., description="List of texts to translate")
    target_lang: str = Field(
        "en", description="Target language: 'en' for English, 'zh' for Chinese"
    )


class TranslationResponse(BaseModel):
    """Response model for translation"""

    translations: Dict[str, str] = Field(
        ..., description="Map of original text to translated text"
    )
    target_lang: str


@router.post("/translate", response_model=TranslationResponse)
async def translate_texts(
    request: TranslationRequest,
    llm_client: LLMProviderClient = Depends(get_llm_provider),
):
    """
    Translate texts using LLM.

    Supports:
    - English -> Traditional Chinese (target_lang='zh')
    - Chinese -> English (target_lang='en')
    """
    logger.info(
        f"Translation request: {len(request.texts)} texts to {request.target_lang}"
    )

    if not request.texts:
        return TranslationResponse(translations={}, target_lang=request.target_lang)

    # Build translation prompt
    if request.target_lang == "en":
        direction = "Chinese to English"
        instruction = "Translate the following Chinese text to English. If the text is already in English or is a proper noun/technical term (like 'LLM', 'Investment'), keep it as-is."
    else:
        direction = "English to Traditional Chinese"
        instruction = "Translate the following English text to Traditional Chinese (繁體中文). If the text is already in Chinese or is a proper noun/technical term (like 'LLM', 'API'), keep it as-is."

    # Format texts for translation
    texts_formatted = "\n".join(
        [f"{i + 1}. {text}" for i, text in enumerate(request.texts)]
    )

    prompt = f"""{instruction}

Texts to translate:
{texts_formatted}

Return ONLY a JSON object mapping each original text to its translation. Example:
{{"LLM": "LLM", "六法全書-民法": "Civil Code - Civil Law"}}

Important:
- Keep technical terms, abbreviations, and proper nouns unchanged
- Return valid JSON only, no markdown or explanation"""

    try:
        messages = [
            {
                "role": "system",
                "content": f"You are a professional translator specializing in {direction} translation. Return only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ]

        response = await llm_client.get_chat_completion(
            messages=messages,
            temperature=0.3,  # Low temperature for consistent translations
        )

        # Extract content from LLM response dict
        # Response structure: {"choices": [{"message": {"content": "..."}}]}
        response_text = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        # Try to extract JSON from response (in case of markdown wrapping)
        if response_text.startswith("```"):
            # Extract JSON from code block
            lines = response_text.split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.startswith("```") and not in_json:
                    in_json = True
                    continue
                elif line.startswith("```") and in_json:
                    break
                elif in_json:
                    json_lines.append(line)
            response_text = "\n".join(json_lines)

        translations = json.loads(response_text)

        # Ensure all requested texts have a translation (fallback to original)
        for text in request.texts:
            if text not in translations:
                translations[text] = text

        return TranslationResponse(
            translations=translations, target_lang=request.target_lang
        )

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM translation response: {e}")
        # Fallback: return original texts
        return TranslationResponse(
            translations={text: text for text in request.texts},
            target_lang=request.target_lang,
        )
    except Exception as e:
        logger.error(f"Translation error: {e}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


# =============================================================================
# Rename Skill API
# =============================================================================


class RenameRequest(BaseModel):
    """Request model for renaming a skill"""

    new_name: str = Field(..., min_length=1, description="New name for the skill")


@router.put("/{skill_id}/rename")
async def rename_skill(
    skill_id: str,
    request: RenameRequest,
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Rename a skill.

    Updates the skill_name in the database.
    Supports both skill_heads (head_xxx) and skill_metadata (skill_xxx) IDs.
    """
    logger.info(f"Renaming skill {skill_id} to '{request.new_name}'")

    try:
        # Determine if this is a head_id or skill_id
        if skill_id.startswith("head_"):
            # This is a skill head - update skill_heads table
            head = await metadata_provider.get_skill_head(skill_id)
            if not head:
                raise HTTPException(
                    status_code=404, detail=f"Skill head not found: {skill_id}"
                )

            # Use the provider's update method
            updated_head = await metadata_provider.update_skill_head(
                skill_id, skill_name=request.new_name
            )

            if not updated_head:
                raise HTTPException(
                    status_code=500, detail="Failed to update skill head"
                )

            logger.info(
                f"Successfully renamed skill head {skill_id} to '{request.new_name}'"
            )

            return {
                "success": True,
                "skill_id": skill_id,
                "new_name": request.new_name,
                "message": f"Skill renamed to '{request.new_name}'",
            }
        else:
            # This is a regular skill_id - update skill_metadata table
            skill = await metadata_provider.get_skill(skill_id)
            if not skill:
                raise HTTPException(
                    status_code=404, detail=f"Skill not found: {skill_id}"
                )

            # Update the skill name in database
            db_path = PROJECT_ROOT / "data" / "skill_metadata.db"
            conn = sqlite3.connect(
                str(db_path), timeout=30.0
            )  # Wait up to 30s for lock
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE skill_metadata
                SET skill_name = ?, updated_at = ?
                WHERE skill_id = ?
            """,
                (request.new_name, datetime.now(timezone.utc).isoformat(), skill_id),
            )

            conn.commit()
            conn.close()

            logger.info(
                f"Successfully renamed skill {skill_id} to '{request.new_name}'"
            )

            return {
                "success": True,
                "skill_id": skill_id,
                "new_name": request.new_name,
                "message": f"Skill renamed to '{request.new_name}'",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rename skill {skill_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to rename skill: {str(e)}")


# =============================================================================
# DELETE Skill API - Complete Removal (NotebookLM Style)
# =============================================================================


@router.delete("/{skill_id}")
async def delete_skill_complete(
    skill_id: str,
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Complete deletion of a skill/source including all related resources:

    1. FAISS Vector Store - Delete embeddings index files
    2. PDF File - Delete the source PDF file
    3. SQLite Metadata - Delete from skill_metadata, skill_document_mapping, skill_chunk_metadata

    This is the NotebookLM-style "Remove Source" operation.
    """
    logger.info(f"Starting complete deletion for skill_id: {skill_id}")

    deletion_results = {
        "skill_id": skill_id,
        "faiss_deleted": False,
        "pdf_deleted": False,
        "sqlite_deleted": False,
        "errors": [],
    }

    try:
        # 1. Get skill metadata first (to find PDF path)
        skill = await metadata_provider.get_skill(skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

        skill_name = skill.get("skill_name", "Unknown")
        metadata = skill.get("metadata", {})
        source_file = (
            metadata.get("source_file", "") if isinstance(metadata, dict) else ""
        )

        logger.info(f"Deleting skill '{skill_name}' (source: {source_file})")

        # 2. Delete FAISS Vector Store
        try:
            import shutil

            faiss_base_path = (
                PROJECT_ROOT / "data" / "faiss_indices" / "skills" / skill_id
            )

            if faiss_base_path.exists():
                shutil.rmtree(faiss_base_path)
                deletion_results["faiss_deleted"] = True
                logger.info(f"Deleted FAISS index: {faiss_base_path}")
            else:
                # Also try without 'skills' subdirectory (legacy structure)
                faiss_alt_path = PROJECT_ROOT / "data" / "faiss_indices" / skill_id
                if faiss_alt_path.exists():
                    shutil.rmtree(faiss_alt_path)
                    deletion_results["faiss_deleted"] = True
                    logger.info(f"Deleted FAISS index (alt path): {faiss_alt_path}")
                else:
                    logger.warning(f"FAISS index not found for {skill_id}")
                    deletion_results["errors"].append(
                        f"FAISS index not found at {faiss_base_path}"
                    )

        except Exception as e:
            logger.error(f"Failed to delete FAISS: {e}")
            deletion_results["errors"].append(f"FAISS deletion error: {str(e)}")

        # 3. Delete PDF File (if exists)
        try:
            if source_file:
                pdf_path = Path(source_file)
                pdf_deleted = False

                # Handle different path formats
                if pdf_path.is_absolute():
                    # Absolute path - use directly
                    if pdf_path.exists():
                        pdf_path.unlink()
                        pdf_deleted = True
                        logger.info(f"Deleted PDF file (absolute): {pdf_path}")
                else:
                    # Relative path - check multiple locations
                    possible_paths = [
                        PROJECT_ROOT
                        / "uploadfiles"
                        / "pdf"
                        / source_file,  # Standard upload location
                        PROJECT_ROOT
                        / "uploadfiles"
                        / "pdf"
                        / pdf_path.name,  # Just filename
                        PROJECT_ROOT / source_file,  # Project root (legacy)
                    ]

                    for try_path in possible_paths:
                        if try_path.exists():
                            try_path.unlink()
                            pdf_deleted = True
                            logger.info(f"Deleted PDF file (relative): {try_path}")
                            break

                if pdf_deleted:
                    deletion_results["pdf_deleted"] = True
                else:
                    logger.warning(f"PDF file not found in any location: {source_file}")
                    deletion_results["errors"].append(
                        f"PDF file not found: {source_file}"
                    )
            else:
                logger.info(f"No source_file in metadata, skipping PDF deletion")

        except Exception as e:
            logger.error(f"Failed to delete PDF: {e}")
            deletion_results["errors"].append(f"PDF deletion error: {str(e)}")

        # 4. Delete SQLite Metadata (with cascade)
        try:
            db_path = PROJECT_ROOT / "data" / "skill_metadata.db"
            conn = sqlite3.connect(
                str(db_path), timeout=30.0
            )  # Wait up to 30s for lock
            cursor = conn.cursor()

            # Delete from skill_chunk_metadata
            cursor.execute(
                "DELETE FROM skill_chunk_metadata WHERE skill_id = ?", (skill_id,)
            )
            chunks_deleted = cursor.rowcount
            logger.info(f"Deleted {chunks_deleted} chunk records")

            # Delete from skill_document_mapping
            cursor.execute(
                "DELETE FROM skill_document_mapping WHERE skill_id = ?", (skill_id,)
            )
            docs_deleted = cursor.rowcount
            logger.info(f"Deleted {docs_deleted} document mapping records")

            # Delete from skill_overviews (overview/summary data)
            cursor.execute(
                "DELETE FROM skill_overviews WHERE skill_id = ?", (skill_id,)
            )
            overviews_deleted = cursor.rowcount
            logger.info(f"Deleted {overviews_deleted} overview records")

            # Delete from skill_metadata (main table)
            cursor.execute("DELETE FROM skill_metadata WHERE skill_id = ?", (skill_id,))
            skill_deleted = cursor.rowcount
            logger.info(f"Deleted {skill_deleted} skill metadata record")

            conn.commit()
            conn.close()

            deletion_results["sqlite_deleted"] = True
            deletion_results["chunks_deleted"] = chunks_deleted
            deletion_results["docs_deleted"] = docs_deleted
            deletion_results["overviews_deleted"] = overviews_deleted

        except Exception as e:
            logger.error(f"Failed to delete SQLite metadata: {e}")
            deletion_results["errors"].append(f"SQLite deletion error: {str(e)}")

        # 5. Update skill_config.json (remove from instant_attachments if present)
        try:
            config = load_skill_config()
            instant_attachments = config.get("instant_attachments", [])
            original_count = len(instant_attachments)

            # Filter out the deleted skill
            config["instant_attachments"] = [
                att for att in instant_attachments if att.get("skill_id") != skill_id
            ]

            if len(config["instant_attachments"]) < original_count:
                save_skill_config(config)
                logger.info(f"Removed skill from instant_attachments in config")

        except Exception as e:
            logger.warning(f"Failed to update skill_config.json: {e}")
            # Non-critical error, don't add to errors

        # Determine overall success
        # ✅ FIX: SQLite deletion is the source of truth
        # FAISS and PDF not found are warnings, not failures
        # As long as SQLite records are deleted, the skill is effectively removed
        sqlite_success = deletion_results["sqlite_deleted"]

        if sqlite_success:
            # Check for warnings (missing FAISS/PDF are acceptable if SQLite deleted)
            has_warnings = len(deletion_results["errors"]) > 0
            if has_warnings:
                logger.info(
                    f"Deleted skill '{skill_name}' ({skill_id}) with warnings: {deletion_results['errors']}"
                )
            else:
                logger.info(f"Successfully deleted skill '{skill_name}' ({skill_id})")

            return {
                "success": True,
                "message": f"Successfully deleted skill '{skill_name}'",
                "has_warnings": has_warnings,
                **deletion_results,
            }
        else:
            # SQLite deletion failed - this is a real failure
            logger.error(
                f"Failed to delete skill '{skill_name}': SQLite deletion failed"
            )
            return {
                "success": False,
                "message": f"Failed to delete skill '{skill_name}' - database error",
                **deletion_results,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complete deletion failed for {skill_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")


# =============================================================================
# NEW: Skill Heads API (Single Source of Truth Architecture)
# =============================================================================


class SkillHeadCreateRequest(BaseModel):
    """Request model for creating a skill head"""

    skill_name: str = Field(..., min_length=1, description="Unique skill name")
    description: str = Field("", description="Skill description")
    category: str = Field("General", description="Skill category")
    display_order: int = Field(0, description="Display order in UI")


class SkillHeadUpdateRequest(BaseModel):
    """Request model for updating a skill head"""

    skill_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    display_order: Optional[int] = None
    enabled: Optional[bool] = None


@router.get("/heads")
async def list_skill_heads(
    category: Optional[str] = None,
    enabled_only: bool = True,
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    List all skill heads.

    This is the new single source of truth for skill definitions.
    Returns skill heads without their documents (use /tree for full structure).
    """
    try:
        heads = await metadata_provider.list_skill_heads(
            category=category, enabled_only=enabled_only
        )
        return {"skill_heads": heads, "count": len(heads)}
    except Exception as e:
        logger.error(f"Failed to list skill heads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heads")
async def create_skill_head(
    request: SkillHeadCreateRequest,
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Create a new skill head.

    A skill head is the parent definition of a skill.
    Documents are uploaded separately and linked via head_id.
    """
    try:
        # Generate head_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hash_suffix = hashlib.md5(request.skill_name.encode()).hexdigest()[:8]
        head_id = f"head_{timestamp}_{hash_suffix}"

        # Check if skill name already exists
        existing = await metadata_provider.get_skill_head_by_name(request.skill_name)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Skill head with name '{request.skill_name}' already exists",
            )

        result = await metadata_provider.create_skill_head(
            head_id=head_id,
            skill_name=request.skill_name,
            description=request.description,
            category=request.category,
            display_order=request.display_order,
        )

        return {"success": True, "skill_head": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create skill head: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/heads/{head_id}")
async def get_skill_head(
    head_id: str,
    include_documents: bool = False,
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Get a skill head by ID.

    Optionally include the list of documents linked to this head.
    """
    try:
        head = await metadata_provider.get_skill_head(head_id)
        if not head:
            raise HTTPException(
                status_code=404, detail=f"Skill head {head_id} not found"
            )

        if include_documents:
            head["documents"] = await metadata_provider.get_documents_for_head(head_id)
            head["document_count"] = len(head["documents"])
            head["total_chunks"] = sum(
                doc.get("total_chunks", 0) for doc in head["documents"]
            )

        return head

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill head {head_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/heads/{head_id}")
async def update_skill_head(
    head_id: str,
    request: SkillHeadUpdateRequest,
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Update a skill head.
    """
    try:
        # Check if exists
        existing = await metadata_provider.get_skill_head(head_id)
        if not existing:
            raise HTTPException(
                status_code=404, detail=f"Skill head {head_id} not found"
            )

        # Build updates dict
        updates = {}
        if request.skill_name is not None:
            updates["skill_name"] = request.skill_name
        if request.description is not None:
            updates["description"] = request.description
        if request.category is not None:
            updates["category"] = request.category
        if request.display_order is not None:
            updates["display_order"] = request.display_order
        if request.enabled is not None:
            updates["enabled"] = request.enabled

        result = await metadata_provider.update_skill_head(head_id, **updates)
        return {"success": True, "skill_head": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update skill head {head_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/heads/{head_id}")
async def delete_skill_head(
    head_id: str,
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Delete a skill head and all associated documents.

    WARNING: This will also delete all documents and FAISS indices
    linked to this skill head.
    """
    try:
        # Check if exists
        existing = await metadata_provider.get_skill_head(head_id)
        if not existing:
            raise HTTPException(
                status_code=404, detail=f"Skill head {head_id} not found"
            )

        # Get documents for cleanup
        documents = await metadata_provider.get_documents_for_head(head_id)

        # Delete FAISS indices for each document
        faiss_deleted = []
        for doc in documents:
            skill_id = doc.get("skill_id")
            if skill_id:
                try:
                    index_path = (
                        PROJECT_ROOT / "data" / "faiss_indices" / "skills" / skill_id
                    )
                    if index_path.exists():
                        import shutil

                        shutil.rmtree(index_path)
                        faiss_deleted.append(skill_id)
                except Exception as e:
                    logger.warning(f"Failed to delete FAISS index for {skill_id}: {e}")

        # Delete from database
        deleted = await metadata_provider.delete_skill_head(head_id)

        return {
            "success": deleted,
            "skill_head": existing["skill_name"],
            "documents_deleted": len(documents),
            "faiss_indices_deleted": len(faiss_deleted),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete skill head {head_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tree")
async def get_skill_tree(
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Get the complete skill tree structure.

    Returns all skill heads with their nested documents.
    This is the recommended endpoint for UI rendering.
    """
    try:
        tree = await metadata_provider.get_skill_tree()
        return {
            "skill_tree": tree,
            "total_skills": len(tree),
            "total_documents": sum(s.get("document_count", 0) for s in tree),
            "total_chunks": sum(s.get("total_chunks", 0) for s in tree),
        }
    except Exception as e:
        logger.error(f"Failed to get skill tree: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/migrate")
async def run_migration(
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Run data migration from old schema to skill_heads architecture.

    This is an admin utility endpoint. Should only be run once
    to migrate existing data.
    """
    try:
        result = await metadata_provider.migrate_existing_data()
        return {"success": True, "migration_result": result}
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Progressive Streaming Endpoint (OPMP Integration)
# =============================================================================


class ProgressiveStreamRequest(BaseModel):
    """Request model for progressive streaming chat with Memory support"""

    query: str = Field(..., min_length=1, description="User query")
    document_ids: List[str] = Field(
        ..., min_items=1, description="Document IDs to search"
    )
    # Memory parameters (reusing pattern from demo/query endpoint)
    session_id: Optional[str] = Field(
        None, description="Session ID for conversation continuity"
    )
    user_id: Optional[str] = Field(None, description="User ID for session management")
    include_history: bool = Field(True, description="Include chat history in context")
    history_limit: int = Field(
        10, ge=1, le=50, description="Max history messages to include"
    )


@router.post("/{skill_id}/chat/stream")
async def stream_skill_chat(
    skill_id: str,
    http_request: Request,  # ✅ For disconnect detection (stop generation)
    request: ProgressiveStreamRequest = Body(...),
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
    llm_provider: LLMProviderClient = Depends(get_llm_provider),
    chat_history_provider: ChatHistoryProvider = Depends(
        get_chat_history_provider
    ),  # ✅ Memory support
):
    """
    Progressive streaming endpoint for Skill-Based chat with OPMP integration.

    This endpoint implements the 5-phase OPMP progressive streaming system:
    - Phase 1: Query Understanding
    - Phase 2: Document Retrieval (Parallel FAISS)
    - Phase 3: Context Assembly
    - Phase 4: Response Generation (Token streaming)
    - Phase 5: Post-processing

    Returns SSE stream with progressive updates.

    Example:
        POST /api/v1/skills/{skill_id}/chat/stream
        {
            "query": "What is LLM?",
            "document_ids": ["doc_001", "doc_002"]
        }

    Response: text/event-stream with events:
        - progress: Phase progress updates
        - markdown_token: Response tokens
        - complete: Final completion
    """
    try:
        from app.Providers.bge_embedding_provider import get_bge_embedding_provider
        from app.SkillServices.progressive_skill_streaming import (
            ProgressiveSkillStreaming,
        )

        # =====================================================================
        # Memory Integration (reusing pattern from /demo/query endpoint)
        # =====================================================================
        effective_user_id = request.user_id or settings.DEFAULT_USER_ID
        # ✅ FIX: Use provided session_id for conversation continuity (P0 session ID fix)
        effective_session_id = (
            request.session_id or f"skill_{effective_user_id}_{skill_id}"
        )

        # Ensure session exists (reusing ChatHistoryProvider)
        if not await chat_history_provider.session_exists(effective_session_id):
            await chat_history_provider.create_session(
                session_id=effective_session_id,
                user_id=effective_user_id,
                file_ids=[skill_id],
                metadata={"type": "skill_progressive_chat", "skill_id": skill_id},
            )
            logger.info(f"Created new session: {effective_session_id}")

        # Load chat history if enabled
        chat_history = []
        if request.include_history:
            chat_history = await chat_history_provider.get_chat_history(
                session_id=effective_session_id, limit=request.history_limit
            )
            logger.info(
                f"Loaded {len(chat_history)} messages from history for session: {effective_session_id}"
            )

        # Get services - with proper error handling for BGE model loading
        try:
            embedding_service = get_bge_embedding_provider()
        except Exception as embedding_error:
            logger.error(
                f"Failed to initialize BGE embedding provider: {embedding_error}"
            )
            raise HTTPException(
                status_code=503,
                detail=f"Embedding service unavailable: {str(embedding_error)}. "
                f"Please ensure BGE-M3 model is properly downloaded. "
                f"Try running: python -c 'from sentence_transformers import SentenceTransformer; SentenceTransformer(\"BAAI/bge-m3\")'",
            )

        # llm_provider IS the LLM itself (no need for get_llm())
        llm = llm_provider

        # FAISS base path
        faiss_base_path = str(PROJECT_ROOT / "data" / "faiss_indices" / "skills")

        # Create progressive streaming service
        progressive_service = ProgressiveSkillStreaming(
            skill_id=skill_id,
            llm=llm,
            embedding_service=embedding_service,
            metadata_provider=metadata_provider,
            faiss_base_path=faiss_base_path,
            config={
                "enable_cache": False,  # Disable cache for demo simplicity
                "max_context_tokens": 100000,
                "retrieval_top_k": int(
                    os.getenv("RETRIEVAL_TOP_K", "50")
                ),  # Increased from 5 to 20 (configurable via env)
                "model_name": "gpt-oss:20b",
            },
        )

        # Stream progressive updates with disconnect detection
        async def event_generator():
            full_response = ""  # ✅ Accumulate response for Memory saving
            saved = False  # ✅ Track if we've already saved (P0 fix)
            try:
                async for update in progressive_service.chat_stream_progressive(
                    query=request.query,
                    document_ids=request.document_ids,
                    chat_history=chat_history,  # ✅ Pass chat history to streaming service
                ):
                    # ✅ Check if client disconnected (user clicked Stop)
                    if await http_request.is_disconnected():
                        logger.info("🛑 Client disconnected, stopping generation")
                        break

                    # ✅ Accumulate markdown tokens for Memory saving
                    try:
                        # Parse SSE data to extract markdown content
                        if update.startswith("data: "):
                            data_str = update[6:].strip()
                            if data_str:
                                data = json.loads(data_str)
                                if data.get("type") == "markdown_token":
                                    # FIX: Phase4 sends {"type": "markdown_token", "token": ...}
                                    # not "content" - this bug caused chat history to never save
                                    full_response += data.get("token", "")
                    except (json.JSONDecodeError, Exception):
                        pass  # Ignore parsing errors, continue streaming

                    # Backend already formats as SSE (data: {...}\n\n)
                    # Use StreamingResponse instead of EventSourceResponse to avoid double wrapping
                    yield update

            except asyncio.CancelledError:
                logger.info("🛑 Stream cancelled by client")
            except Exception as e:
                logger.error(f"Stream error: {e}")
                # Send error event to client
                error_event = json.dumps({"type": "error", "message": str(e)})
                yield f"data: {error_event}\n\n"
            finally:
                # =====================================================================
                # P0 FIX: Save conversation in finally block to handle ALL scenarios:
                # - Normal completion (full stream received)
                # - Client disconnection (curl | head -20, user clicks Stop)
                # - asyncio.CancelledError
                # - Any other exception
                # =====================================================================
                if full_response.strip() and not saved:
                    try:
                        await chat_history_provider.add_message(
                            session_id=effective_session_id,
                            role="user",
                            content=request.query,
                            metadata={
                                "skill_id": skill_id,
                                "type": "progressive_stream",
                            },
                        )
                        await chat_history_provider.add_message(
                            session_id=effective_session_id,
                            role="assistant",
                            content=full_response,
                            metadata={
                                "skill_id": skill_id,
                                "type": "progressive_stream",
                            },
                        )
                        saved = True
                        logger.info(
                            f"✅ Saved conversation to session: {effective_session_id} (response: {len(full_response)} chars)"
                        )
                    except Exception as save_error:
                        logger.error(f"❌ Failed to save conversation: {save_error}")

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except ImportError as e:
        logger.error(f"Progressive streaming not available: {e}")
        raise HTTPException(
            status_code=501,
            detail="Progressive streaming feature not yet fully implemented",
        )
    except Exception as e:
        logger.error(f"Progressive streaming error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/acknowledge/{session_id}/{phase}")
async def acknowledge_phase_completion(session_id: str, phase: int):
    """
    Frontend acknowledgment endpoint for phase completion.

    The frontend calls this endpoint after it has finished rendering a phase's progress bar update.
    This unblocks the backend to proceed to the next phase.

    Protocol:
    1. Backend sends phase_result event
    2. Frontend renders progress bar update
    3. Frontend calls POST /acknowledge/{session_id}/{phase}
    4. Backend receives ACK and proceeds to next phase

    Args:
        session_id: Unique session identifier from session_init event
        phase: Phase number that was completed (1-4)

    Returns:
        {"status": "acknowledged", "session_id": str, "phase": int}
    """
    try:
        from app.SkillServices.progressive_skill_streaming import acknowledge_phase

        success = acknowledge_phase(session_id, phase)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or phase {phase} invalid",
            )

        return {"status": "acknowledged", "session_id": session_id, "phase": phase}

    except ImportError:
        raise HTTPException(
            status_code=501, detail="Progressive streaming feature not available"
        )
    except Exception as e:
        logger.error(f"Phase acknowledgment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Session Management Endpoints
# =============================================================================


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider),
):
    """
    Delete a specific chat session and all its messages.

    This endpoint clears the MongoDB chat history for the given session,
    effectively resetting the conversation context.

    Args:
        session_id: Session identifier (e.g., "skill_default_user_skill_xxx")

    Returns:
        {"status": "deleted", "session_id": str}
    """
    try:
        await chat_history_provider.delete_session(session_id)
        logger.info(f"Deleted session: {session_id}")
        return {"status": "deleted", "session_id": session_id}
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/skill/{skill_id}")
async def clear_skill_sessions(
    skill_id: str,
    user_id: Optional[str] = None,
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider),
):
    """
    Clear all chat sessions for a specific skill.

    This is useful when you want to reset all conversation history for a skill,
    such as when debugging contaminated chat history issues.

    Args:
        skill_id: Skill identifier
        user_id: Optional user ID filter (defaults to default_user if not specified)

    Returns:
        {"status": "cleared", "skill_id": str, "deleted_count": int}
    """
    try:
        effective_user_id = user_id or settings.DEFAULT_USER_ID
        session_id = f"skill_{effective_user_id}_{skill_id}"

        await chat_history_provider.delete_session(session_id)
        logger.info(f"Cleared session for skill {skill_id}: {session_id}")

        return {"status": "cleared", "skill_id": skill_id, "session_id": session_id}
    except Exception as e:
        logger.error(f"Failed to clear skill sessions for {skill_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/clear-all")
async def clear_all_sessions(
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider),
):
    """
    Clear ALL chat sessions in MongoDB.

    WARNING: This will delete all conversation history across all skills and users.
    Use with caution - primarily for debugging/development purposes.

    Returns:
        {"status": "cleared", "message": str}
    """
    try:
        collection = await chat_history_provider._get_collection()
        result = await collection.delete_many({})
        deleted_count = result.deleted_count

        logger.info(f"Cleared all sessions: {deleted_count} deleted")
        return {
            "status": "cleared",
            "deleted_count": deleted_count,
            "message": f"Successfully deleted {deleted_count} session(s)",
        }
    except Exception as e:
        logger.error(f"Failed to clear all sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/list")
async def list_all_sessions(
    chat_history_provider: ChatHistoryProvider = Depends(get_chat_history_provider),
):
    """
    List ALL chat sessions in MongoDB.

    Returns:
        {"sessions": [...], "count": int}
    """
    try:
        collection = await chat_history_provider._get_collection()
        cursor = collection.find(
            {}, {"session_id": 1, "messages": 1, "updated_at": 1, "_id": 0}
        )
        sessions = []
        async for doc in cursor:
            session_info = {
                "session_id": doc.get("session_id", "unknown"),
                "message_count": len(doc.get("messages", [])),
                "updated_at": str(doc.get("updated_at", "")),
            }
            # Extract last message preview if available
            messages = doc.get("messages", [])
            if messages:
                last_msg = messages[-1]
                session_info["last_message_preview"] = last_msg.get("content", "")[:100]
                session_info["last_role"] = last_msg.get("role", "unknown")
            sessions.append(session_info)

        logger.info(f"Listed {len(sessions)} sessions")
        return {"sessions": sessions, "count": len(sessions)}
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Skill Export/Import Endpoints
# =============================================================================


def sanitize_filename(filename: str) -> str:
    r"""
    清理檔案名稱，移除非法字元

    允許：字母、數字、底線、中文、連字號
    禁止：/ \ : * ? " < > | 等特殊字元
    """
    # 移除路徑分隔符（防止 path traversal）
    filename = filename.replace("/", "_").replace("\\", "_")

    # 移除其他非法字元
    filename = re.sub(r'[<>:"|?*]', "_", filename)

    # 移除開頭/結尾的空白和點
    filename = filename.strip().strip(".")

    # 限制長度（避免檔案系統限制）
    if len(filename) > 200:
        filename = filename[:200]

    # 如果檔名為空，使用預設名稱
    if not filename:
        filename = "skill_export"

    return filename


def check_zip_safety(zip_path: Path, max_size_mb: int = 500) -> bool:
    """
    檢查 ZIP 檔案安全性

    防止 ZIP 炸彈攻擊（壓縮比過高的惡意檔案）
    """
    total_size = 0

    with zipfile.ZipFile(zip_path, "r") as zipf:
        for info in zipf.infolist():
            total_size += info.file_size

            # 單一檔案大小檢查 (100MB)
            if info.file_size > 100 * 1024 * 1024:
                raise ValueError(f"File too large in ZIP: {info.filename}")

        # 總解壓縮大小檢查
        if total_size > max_size_mb * 1024 * 1024:
            raise ValueError(
                f"ZIP content too large: {total_size / 1024 / 1024:.2f}MB "
                f"(max: {max_size_mb}MB)"
            )

    return True


@router.get("/config/skills/export/{head_id}")
async def export_skill(
    head_id: str,
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Export a complete Skill (Database + FAISS) as a ZIP file.

    Args:
        head_id: The skill head ID to export

    Returns:
        StreamingResponse with ZIP file download
    """
    logger.info(f"[Export] Starting export for head_id: {head_id}")

    # 1. 驗證 skill head 存在
    try:
        skill_heads = await metadata_provider.list_skill_heads(enabled_only=False)
        skill_head = next((h for h in skill_heads if h["head_id"] == head_id), None)

        if not skill_head:
            raise HTTPException(
                status_code=404, detail=f"Skill head not found: {head_id}"
            )

        skill_name = skill_head.get("skill_name", "unknown")
        logger.info(f"[Export] Found skill head: {skill_name}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Export] Failed to get skill head: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get skill head: {str(e)}"
        )

    # 2. 獲取該 head 下的所有 skill documents
    try:
        documents = await metadata_provider.get_documents_for_head(head_id)
        if not documents:
            raise HTTPException(
                status_code=400, detail=f"No documents found for skill: {skill_name}"
            )

        logger.info(f"[Export] Found {len(documents)} documents for head {head_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Export] Failed to get documents: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get documents: {str(e)}"
        )

    # 3. 驗證 FAISS 索引存在（至少一個 document 需要有索引）
    faiss_base_dir = PROJECT_ROOT / "data" / "faiss_indices" / "skills"
    skill_ids_with_faiss = []

    for doc in documents:
        skill_id = doc.get("skill_id")
        faiss_dir = faiss_base_dir / skill_id
        index_faiss = faiss_dir / "index.faiss"
        index_pkl = faiss_dir / "index.pkl"

        if index_faiss.exists() and index_pkl.exists():
            skill_ids_with_faiss.append(skill_id)
        else:
            logger.warning(f"[Export] FAISS index missing for skill_id: {skill_id}")

    if not skill_ids_with_faiss:
        raise HTTPException(
            status_code=500, detail=f"No FAISS indices found for skill: {skill_name}"
        )

    logger.info(
        f"[Export] Found {len(skill_ids_with_faiss)} skill(s) with FAISS indices"
    )

    # 4. 建立臨時目錄
    temp_dir = tempfile.mkdtemp(prefix=f"skill_export_{head_id}_")
    safe_skill_name = sanitize_filename(skill_name)
    skill_folder = Path(temp_dir) / safe_skill_name
    skill_folder.mkdir(parents=True, exist_ok=True)

    try:
        # 5. 匯出資料庫資料
        # ============================================================
        # Export v2.0: 把 metadata 整合到 manifest.json
        # - skill_heads: 放入 manifest.json
        # - skill_metadata: 放入 manifest.json
        # - skill_document_mapping: 放入 manifest.json
        # - skill_chunk_metadata: 保留 CSV（資料量大）
        # - 保持原有 skill_id 不變，匯入時直接使用
        # ============================================================
        db_path = PROJECT_ROOT / "data" / "skill_metadata.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        total_chunks = 0

        # 5a. skill_heads → 放入 manifest
        cursor.execute("SELECT * FROM skill_heads WHERE head_id = ?", (head_id,))
        skill_heads_rows = cursor.fetchall()
        skill_heads_data = []
        if skill_heads_rows:
            columns = [desc[0] for desc in cursor.description]
            for row in skill_heads_rows:
                skill_heads_data.append(dict(zip(columns, tuple(row))))
            logger.info(
                f"[Export] Collected {len(skill_heads_data)} rows from skill_heads"
            )

        # 5b. skill_metadata → 放入 manifest
        skill_id_placeholders = ",".join(["?" for _ in skill_ids_with_faiss])
        cursor.execute(
            f"SELECT * FROM skill_metadata WHERE skill_id IN ({skill_id_placeholders})",
            skill_ids_with_faiss,
        )
        skill_metadata_rows = cursor.fetchall()
        skill_metadata_data = []
        if skill_metadata_rows:
            columns = [desc[0] for desc in cursor.description]
            for row in skill_metadata_rows:
                skill_metadata_data.append(dict(zip(columns, tuple(row))))
            logger.info(
                f"[Export] Collected {len(skill_metadata_data)} rows from skill_metadata"
            )

        # 5c. skill_document_mapping → 放入 manifest
        cursor.execute(
            f"SELECT * FROM skill_document_mapping WHERE skill_id IN ({skill_id_placeholders})",
            skill_ids_with_faiss,
        )
        doc_mapping_rows = cursor.fetchall()
        doc_mapping_data = []
        if doc_mapping_rows:
            columns = [desc[0] for desc in cursor.description]
            for row in doc_mapping_rows:
                doc_mapping_data.append(dict(zip(columns, tuple(row))))
            logger.info(
                f"[Export] Collected {len(doc_mapping_data)} rows from skill_document_mapping"
            )

        # 5d. skill_overviews → 放入 manifest
        cursor.execute(
            f"SELECT * FROM skill_overviews WHERE skill_id IN ({skill_id_placeholders})",
            skill_ids_with_faiss,
        )
        overviews_rows = cursor.fetchall()
        overviews_data = []
        if overviews_rows:
            columns = [desc[0] for desc in cursor.description]
            for row in overviews_rows:
                overviews_data.append(dict(zip(columns, tuple(row))))
            logger.info(
                f"[Export] Collected {len(overviews_data)} rows from skill_overviews"
            )

        # 5e. skill_chunk_metadata → 保留 CSV（資料量大）
        cursor.execute(
            f"SELECT * FROM skill_chunk_metadata WHERE skill_id IN ({skill_id_placeholders})",
            skill_ids_with_faiss,
        )
        chunk_rows = cursor.fetchall()
        csv_files = {}
        if chunk_rows:
            columns = [desc[0] for desc in cursor.description]
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(columns)
            writer.writerows([tuple(row) for row in chunk_rows])
            csv_files["skill_chunk_metadata.csv"] = csv_buffer.getvalue()
            total_chunks = len(chunk_rows)
            logger.info(
                f"[Export] Exported {total_chunks} rows to skill_chunk_metadata.csv"
            )

        conn.close()

        # 6. 建立 manifest.json（包含所有 metadata）
        # ============================================================
        # Export v2.0: manifest.json 是 Single Source of Truth
        # - 包含 skill_heads、skill_metadata、skill_document_mapping
        # - 匯入時直接使用原 ID，不生成新 ID
        # ============================================================
        manifest = {
            "export_version": "2.0",
            "export_date": datetime.now(timezone.utc).isoformat(),
            # 核心 ID（保持不變，匯入時直接使用）
            "head_id": head_id,
            "skill_ids": skill_ids_with_faiss,
            # 基本資訊
            "skill_name": skill_name,
            "skill_description": skill_head.get("description", ""),
            "category": skill_head.get("category", "General"),
            "total_chunks": total_chunks,
            "document_count": len(skill_ids_with_faiss),
            # 嵌入模型資訊
            "embedding_model": "BAAI/bge-m3",
            "embedding_dimension": 1024,
            # ===== 內嵌 metadata（不再使用 CSV）=====
            "skill_heads": skill_heads_data,
            "skill_metadata": skill_metadata_data,
            "skill_document_mapping": doc_mapping_data,
            "skill_overviews": overviews_data,
            # CSV 檔案（只有 chunk_metadata 因資料量大）
            "csv_files": list(csv_files.keys()),
            # FAISS 目錄（保持原 skill_id 作為目錄名）
            "faiss_folders": skill_ids_with_faiss,
            # 匯出元資訊
            "export_metadata": {
                "system_version": "DocAI v2.0",
                "export_tool": "skill_export_api",
                "note": "v2.0: metadata integrated into manifest.json, original IDs preserved",
            },
        }

        manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)

        # 7. 寫入檔案
        (skill_folder / "manifest.json").write_text(manifest_json, encoding="utf-8")
        logger.info(f"[Export] Written manifest.json with integrated metadata")

        # 只寫入 skill_chunk_metadata.csv
        for csv_name, csv_content in csv_files.items():
            (skill_folder / csv_name).write_text(csv_content, encoding="utf-8")

        # 8. 複製 FAISS 檔案（每個 skill_id 一個資料夾）
        faiss_export_dir = skill_folder / "faiss_indices"
        faiss_export_dir.mkdir(parents=True, exist_ok=True)

        for skill_id in skill_ids_with_faiss:
            src_faiss_dir = faiss_base_dir / skill_id
            dst_faiss_dir = faiss_export_dir / skill_id
            dst_faiss_dir.mkdir(parents=True, exist_ok=True)

            shutil.copy2(src_faiss_dir / "index.faiss", dst_faiss_dir / "index.faiss")
            shutil.copy2(src_faiss_dir / "index.pkl", dst_faiss_dir / "index.pkl")

            logger.info(f"[Export] Copied FAISS index for {skill_id}")

        # 9. 壓縮成 ZIP
        zip_filename = f"{safe_skill_name}.zip"
        zip_path = Path(temp_dir) / zip_filename

        # 建立 ZIP 檔案，確保支援 UTF-8 檔名
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in skill_folder.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(skill_folder.parent)
                    # Convert Path to string to ensure UTF-8 encoding
                    zipf.write(file_path, str(arcname))

        zip_size = zip_path.stat().st_size
        logger.info(f"[Export] Created ZIP: {zip_path} ({zip_size} bytes)")

        # 10. 回傳檔案
        def iterfile():
            with open(zip_path, mode="rb") as file_like:
                yield from file_like
            # 清理臨時檔案（在檔案讀取完成後）
            shutil.rmtree(temp_dir, ignore_errors=True)

        # RFC 5987: Support UTF-8 filenames in HTTP headers
        # filename must be ASCII-safe (for old browsers)
        # filename* can use UTF-8 encoding (for modern browsers)
        from urllib.parse import quote

        # ASCII-safe fallback name
        ascii_filename = "skill_export.zip"

        # UTF-8 encoded filename for modern browsers
        encoded_filename = quote(zip_filename)

        headers = {
            "Content-Disposition": f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}"'
        }

        return StreamingResponse(
            iterfile(), media_type="application/zip", headers=headers
        )

    except HTTPException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    except Exception as e:
        import traceback

        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.error(f"[Export] Failed to create export: {e}")
        logger.error(f"[Export] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/config/skills/preview")
async def preview_skill_import(
    file: UploadFile = File(...),
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Preview a Skill ZIP file before importing.

    解析 ZIP 內容並返回預覽資訊，不進行實際匯入。
    讓用戶確認內容後再決定是否匯入。

    Returns:
        - skill_name: 技能名稱
        - document_count: 文件數量
        - total_chunks: Chunks 數量
        - export_date: 匯出日期
        - export_version: 匯出格式版本
        - documents: 文件列表
        - has_name_conflict: 名稱是否衝突
        - has_id_conflict: ID 是否衝突
    """
    logger.info(f"[Preview] Receiving file: {file.filename}")

    # 1. 驗證檔案類型
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files are accepted")

    # 2. 建立臨時目錄
    preview_temp_dir = tempfile.mkdtemp(prefix="skill_preview_")
    zip_path = Path(preview_temp_dir) / "uploaded.zip"

    try:
        # 3. 儲存上傳的 ZIP
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = zip_path.stat().st_size
        logger.info(f"[Preview] Saved ZIP: {zip_path} ({file_size} bytes)")

        # 4. 安全性檢查
        try:
            check_zip_safety(zip_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 5. 解壓縮 ZIP
        extract_dir = Path(preview_temp_dir) / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as zipf:
                zipf.extractall(extract_dir)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Corrupted ZIP file")

        # 6. 找到 skill 資料夾
        skill_folders = [d for d in extract_dir.iterdir() if d.is_dir()]

        if not skill_folders:
            raise HTTPException(
                status_code=400, detail="Invalid ZIP structure: no skill folder found"
            )

        skill_folder = skill_folders[0]

        # 7. 讀取 manifest.json
        manifest_path = skill_folder / "manifest.json"

        if not manifest_path.exists():
            raise HTTPException(
                status_code=400, detail="Invalid skill export: manifest.json not found"
            )

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # 8. 解析資訊
        export_version = manifest.get("export_version", "1.0")
        skill_name = manifest.get("skill_name", "Unknown")
        # v2.0 使用 "export_date"，舊版本可能用 "export_timestamp" 或 "exported_at"
        export_date = manifest.get(
            "export_date",
            manifest.get("export_timestamp", manifest.get("exported_at", "Unknown")),
        )

        # 取得文件列表
        documents = []
        total_chunks = 0

        if export_version == "2.0":
            # v2.0: metadata 在 manifest 中，key 是 "skill_metadata" (不是 "metadata")
            metadata_list = manifest.get("skill_metadata", [])
            for meta in metadata_list:
                doc_name = meta.get("source_name") or meta.get("source_file", "Unknown")
                if doc_name and doc_name != "Unknown":
                    # 清理路徑，只取檔名
                    doc_name = Path(doc_name).name
                chunks = meta.get("total_chunks", 0)
                documents.append({"name": doc_name, "chunks": chunks})
                total_chunks += chunks
        else:
            # v1.0: 嘗試從 CSV 讀取
            csv_path = skill_folder / "metadata.csv"
            if csv_path.exists():
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        doc_name = row.get("source_name") or row.get(
                            "source_file", "Unknown"
                        )
                        if doc_name and doc_name != "Unknown":
                            doc_name = Path(doc_name).name
                        chunks = int(row.get("total_chunks", 0))
                        documents.append({"name": doc_name, "chunks": chunks})
                        total_chunks += chunks
            else:
                # 從 faiss_folders 推斷
                faiss_folders = manifest.get("faiss_folders", [])
                for folder in faiss_folders:
                    documents.append({"name": folder, "chunks": 0})

        # 9. 檢查衝突
        db_path = PROJECT_ROOT / "data" / "skill_metadata.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 檢查名稱衝突
        cursor.execute(
            "SELECT COUNT(*) FROM skill_heads WHERE skill_name = ?", (skill_name,)
        )
        has_name_conflict = cursor.fetchone()[0] > 0

        # 檢查 ID 衝突
        has_id_conflict = False
        if export_version == "2.0":
            original_head_id = manifest.get("head_id", "")
            original_skill_ids = manifest.get("skill_ids", [])

            if original_head_id:
                cursor.execute(
                    "SELECT COUNT(*) FROM skill_heads WHERE head_id = ?",
                    (original_head_id,),
                )
                if cursor.fetchone()[0] > 0:
                    has_id_conflict = True

            for sid in original_skill_ids:
                cursor.execute(
                    "SELECT COUNT(*) FROM skill_metadata WHERE skill_id = ?", (sid,)
                )
                if cursor.fetchone()[0] > 0:
                    has_id_conflict = True
                    break

        conn.close()

        # 10. 返回預覽資訊
        return {
            "skill_name": skill_name,
            "document_count": len(documents),
            "total_chunks": total_chunks,
            "export_date": export_date,
            "export_version": export_version,
            "file_size": file_size,
            "file_size_mb": round(file_size / 1024 / 1024, 2),
            "documents": documents,
            "has_name_conflict": has_name_conflict,
            "has_id_conflict": has_id_conflict,
            "conflict_warning": "技能名稱已存在，匯入時將自動重命名"
            if has_name_conflict
            else None,
        }

    finally:
        # 清理臨時檔案
        shutil.rmtree(preview_temp_dir, ignore_errors=True)


@router.post("/config/skills/import")
async def import_skill(
    file: UploadFile = File(...),
    metadata_provider: SkillMetadataProvider = Depends(get_skill_metadata_provider),
):
    """
    Import a Skill from a ZIP file (created by export_skill).

    ============================================================
    Import v2.0: 直接使用原 ID，不生成新 ID
    - 從 manifest.json 讀取 metadata（v2.0 格式）
    - 或從 CSV 讀取 metadata（v1.0 向下相容）
    - 只有 ID 衝突時才處理（而非總是生成新 ID）
    - FAISS 目錄保持原 skill_id
    ============================================================

    Args:
        file: ZIP file containing the skill data

    Returns:
        Import result with skill IDs (original or conflict-resolved)
    """
    logger.info(f"[Import v2.0] Receiving file: {file.filename}")

    # 1. 驗證檔案類型
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400, detail="Only ZIP files are accepted for skill import"
        )

    # 2. 建立臨時目錄
    import_temp_dir = tempfile.mkdtemp(prefix="skill_import_")
    zip_path = Path(import_temp_dir) / "uploaded.zip"

    try:
        # 3. 儲存上傳的 ZIP
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"[Import] Saved ZIP: {zip_path} ({zip_path.stat().st_size} bytes)")

        # 4. 安全性檢查
        try:
            check_zip_safety(zip_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 5. 解壓縮 ZIP
        extract_dir = Path(import_temp_dir) / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as zipf:
                zipf.extractall(extract_dir)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Corrupted ZIP file")

        # 6. 找到 skill 資料夾（ZIP 內第一層）
        skill_folders = [d for d in extract_dir.iterdir() if d.is_dir()]

        if not skill_folders:
            raise HTTPException(
                status_code=400, detail="Invalid ZIP structure: no skill folder found"
            )

        skill_folder = skill_folders[0]
        logger.info(f"[Import] Found skill folder: {skill_folder.name}")

        # 7. 讀取 manifest.json
        manifest_path = skill_folder / "manifest.json"

        if not manifest_path.exists():
            raise HTTPException(
                status_code=400, detail="Invalid skill export: manifest.json not found"
            )

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # 8. 檢測版本並驗證必要欄位
        export_version = manifest.get("export_version", "1.0")
        logger.info(f"[Import] Detected export version: {export_version}")

        if export_version == "2.0":
            # v2.0: metadata 在 manifest.json 中
            required_fields = ["skill_name", "head_id", "skill_ids", "faiss_folders"]
        else:
            # v1.0: metadata 在 CSV 中
            required_fields = ["skill_name", "faiss_folders"]

        missing_fields = [field for field in required_fields if field not in manifest]
        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid manifest: missing fields {missing_fields}",
            )

        # 9. 驗證 FAISS 檔案存在
        faiss_indices_dir = skill_folder / "faiss_indices"
        for faiss_folder in manifest["faiss_folders"]:
            faiss_dir = faiss_indices_dir / faiss_folder
            if not (faiss_dir / "index.faiss").exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing FAISS index: {faiss_folder}/index.faiss",
                )
            if not (faiss_dir / "index.pkl").exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing FAISS pkl: {faiss_folder}/index.pkl",
                )

        logger.info(f"[Import] Manifest validated: {manifest['skill_name']}")

        # ============================================================
        # 10. v2.0 核心改動：直接使用原 ID，只檢查衝突
        # ============================================================
        skill_name = manifest["skill_name"]
        db_path = PROJECT_ROOT / "data" / "skill_metadata.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 取得原 ID
        if export_version == "2.0":
            original_head_id = manifest["head_id"]
            original_skill_ids = manifest["skill_ids"]
        else:
            # v1.0 向下相容
            original_head_id = manifest.get(
                "source_head_id", manifest.get("head_id", "")
            )
            original_skill_ids = manifest.get("faiss_folders", [])

        # 檢查 head_id 衝突
        cursor.execute(
            "SELECT COUNT(*) FROM skill_heads WHERE head_id = ?", (original_head_id,)
        )
        head_id_conflict = cursor.fetchone()[0] > 0

        # 檢查 skill_id 衝突
        skill_id_conflicts = []
        for sid in original_skill_ids:
            cursor.execute(
                "SELECT COUNT(*) FROM skill_metadata WHERE skill_id = ?", (sid,)
            )
            if cursor.fetchone()[0] > 0:
                skill_id_conflicts.append(sid)

        # 檢查 skill_name 衝突
        cursor.execute(
            "SELECT COUNT(*) FROM skill_heads WHERE skill_name = ?", (skill_name,)
        )
        name_conflict = cursor.fetchone()[0] > 0

        conn.close()

        # 決定使用的 ID
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        if head_id_conflict or skill_id_conflicts:
            # 有衝突：需要生成新 ID
            logger.warning(f"[Import] ID conflicts detected:")
            if head_id_conflict:
                logger.warning(f"  - head_id conflict: {original_head_id}")
            if skill_id_conflicts:
                logger.warning(f"  - skill_id conflicts: {skill_id_conflicts}")

            name_hash = hashlib.md5(skill_name.encode("utf-8")).hexdigest()[:8]
            final_head_id = f"head_{timestamp}_{name_hash}"

            id_mapping = {}
            for i, old_sid in enumerate(original_skill_ids):
                file_hash = hashlib.md5(f"{old_sid}_{i}".encode()).hexdigest()[:6]
                id_mapping[old_sid] = f"skill_{timestamp}_{name_hash}_{file_hash}"

            ids_were_changed = True
            logger.info(f"[Import] Generated new IDs due to conflicts")
        else:
            # 無衝突：直接使用原 ID（v2.0 核心改動）
            final_head_id = original_head_id
            id_mapping = {sid: sid for sid in original_skill_ids}  # 原 ID = 新 ID
            ids_were_changed = False
            logger.info(f"[Import] Using original IDs (no conflicts)")

        # 處理 skill_name 衝突
        if name_conflict:
            final_skill_name = f"{skill_name}_{timestamp}"
            logger.warning(
                f"[Import] Skill name conflict, renamed to: {final_skill_name}"
            )
        else:
            final_skill_name = skill_name

        logger.info(f"[Import] Final IDs:")
        logger.info(f"  - head_id: {final_head_id}")
        for old_id, new_id in id_mapping.items():
            if old_id == new_id:
                logger.info(f"  - {old_id} (unchanged)")
            else:
                logger.info(f"  - {old_id} -> {new_id}")

        # ============================================================
        # 11. 準備資料庫資料
        # ============================================================
        if export_version == "2.0":
            # v2.0: 從 manifest.json 讀取 metadata
            skill_heads_data = manifest.get("skill_heads", [])
            skill_metadata_data = manifest.get("skill_metadata", [])
            doc_mapping_data = manifest.get("skill_document_mapping", [])
            overviews_data = manifest.get("skill_overviews", [])

            # 更新 ID（如果有衝突）
            for row in skill_heads_data:
                if row.get("head_id") == original_head_id:
                    row["head_id"] = final_head_id
                row["skill_name"] = final_skill_name

            for row in skill_metadata_data:
                if row.get("skill_id") in id_mapping:
                    row["skill_id"] = id_mapping[row["skill_id"]]
                if row.get("head_id") == original_head_id:
                    row["head_id"] = final_head_id
                row["skill_name"] = final_skill_name

            for row in doc_mapping_data:
                if row.get("skill_id") in id_mapping:
                    row["skill_id"] = id_mapping[row["skill_id"]]

            for row in overviews_data:
                if row.get("skill_id") in id_mapping:
                    row["skill_id"] = id_mapping[row["skill_id"]]

            logger.info(f"[Import v2.0] Loaded metadata from manifest.json")

        else:
            # v1.0 向下相容：從 CSV 讀取
            skill_heads_data = []
            skill_metadata_data = []
            doc_mapping_data = []
            overviews_data = []

            csv_tables = manifest.get("database_tables", [])

            for table_csv in csv_tables:
                csv_path = skill_folder / table_csv
                if not csv_path.exists():
                    continue

                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)

                for row in rows:
                    # 更新 ID
                    if "head_id" in row and row["head_id"] == original_head_id:
                        row["head_id"] = final_head_id
                    if "skill_id" in row and row["skill_id"] in id_mapping:
                        row["skill_id"] = id_mapping[row["skill_id"]]
                    if "skill_name" in row and table_csv == "skill_heads.csv":
                        row["skill_name"] = final_skill_name

                if table_csv == "skill_heads.csv":
                    skill_heads_data = rows
                elif table_csv == "skill_metadata.csv":
                    skill_metadata_data = rows
                elif table_csv == "skill_document_mapping.csv":
                    doc_mapping_data = rows
                elif table_csv == "skill_overviews.csv":
                    overviews_data = rows

            logger.info(f"[Import v1.0] Loaded metadata from CSV files")

        # 12. 讀取 skill_chunk_metadata.csv（所有版本都用 CSV）
        chunk_csv_path = skill_folder / "skill_chunk_metadata.csv"
        chunk_data = []

        if chunk_csv_path.exists():
            with open(chunk_csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                chunk_headers = reader.fieldnames
                for row in reader:
                    # 更新 skill_id（如果有衝突）
                    if row.get("skill_id") in id_mapping:
                        old_skill_id = row["skill_id"]
                        new_skill_id = id_mapping[old_skill_id]
                        row["skill_id"] = new_skill_id

                        # 只有在 ID 變更時才更新 chunk_id
                        if ids_were_changed and row.get("chunk_id", "").startswith(
                            old_skill_id
                        ):
                            row["chunk_id"] = row["chunk_id"].replace(
                                old_skill_id, new_skill_id, 1
                            )

                    chunk_data.append(row)

            logger.info(f"[Import] Loaded {len(chunk_data)} chunks from CSV")

        # ============================================================
        # 13. 交易式資料庫操作
        # ============================================================
        conn = sqlite3.connect(str(db_path))
        conn.execute("BEGIN TRANSACTION")

        try:
            cursor = conn.cursor()

            # 插入 skill_heads
            if skill_heads_data:
                for row in skill_heads_data:
                    columns = list(row.keys())
                    placeholders = ", ".join(["?" for _ in columns])
                    sql = f"INSERT INTO skill_heads ({', '.join(columns)}) VALUES ({placeholders})"
                    cursor.execute(sql, list(row.values()))
                logger.info(
                    f"[Import] Inserted {len(skill_heads_data)} rows into skill_heads"
                )

            # 插入 skill_metadata
            if skill_metadata_data:
                for row in skill_metadata_data:
                    columns = list(row.keys())
                    placeholders = ", ".join(["?" for _ in columns])
                    sql = f"INSERT INTO skill_metadata ({', '.join(columns)}) VALUES ({placeholders})"
                    cursor.execute(sql, list(row.values()))
                logger.info(
                    f"[Import] Inserted {len(skill_metadata_data)} rows into skill_metadata"
                )

            # 插入 skill_chunk_metadata (使用 INSERT OR REPLACE 避免 chunk_id 衝突)
            if chunk_data:
                for row in chunk_data:
                    columns = list(row.keys())
                    placeholders = ", ".join(["?" for _ in columns])
                    sql = f"INSERT OR REPLACE INTO skill_chunk_metadata ({', '.join(columns)}) VALUES ({placeholders})"
                    cursor.execute(sql, list(row.values()))
                logger.info(
                    f"[Import] Inserted/Updated {len(chunk_data)} rows into skill_chunk_metadata"
                )

            # 插入 skill_document_mapping (使用 INSERT OR REPLACE 避免衝突)
            if doc_mapping_data:
                for row in doc_mapping_data:
                    columns = list(row.keys())
                    placeholders = ", ".join(["?" for _ in columns])
                    sql = f"INSERT OR REPLACE INTO skill_document_mapping ({', '.join(columns)}) VALUES ({placeholders})"
                    cursor.execute(sql, list(row.values()))
                logger.info(
                    f"[Import] Inserted/Updated {len(doc_mapping_data)} rows into skill_document_mapping"
                )

            # 插入 skill_overviews
            if overviews_data:
                for row in overviews_data:
                    columns = list(row.keys())
                    placeholders = ", ".join(["?" for _ in columns])
                    sql = f"INSERT INTO skill_overviews ({', '.join(columns)}) VALUES ({placeholders})"
                    cursor.execute(sql, list(row.values()))
                logger.info(
                    f"[Import] Inserted {len(overviews_data)} rows into skill_overviews"
                )

            conn.commit()
            logger.info(f"[Import] Database transaction committed successfully")

        except Exception as e:
            conn.rollback()
            logger.error(f"[Import] Database transaction failed: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Database import failed: {str(e)}"
            )

        finally:
            conn.close()

        # ============================================================
        # 14. 複製 FAISS 索引（保持原目錄名或使用新名）
        # ============================================================
        faiss_base_dir = PROJECT_ROOT / "data" / "faiss_indices" / "skills"
        final_skill_ids = list(id_mapping.values())

        try:
            for original_sid, final_sid in id_mapping.items():
                src_faiss_dir = faiss_indices_dir / original_sid
                dst_faiss_dir = faiss_base_dir / final_sid
                dst_faiss_dir.mkdir(parents=True, exist_ok=True)

                shutil.copy2(
                    src_faiss_dir / "index.faiss", dst_faiss_dir / "index.faiss"
                )
                shutil.copy2(src_faiss_dir / "index.pkl", dst_faiss_dir / "index.pkl")

                if original_sid == final_sid:
                    logger.info(
                        f"[Import] Copied FAISS index: {original_sid} (unchanged)"
                    )
                else:
                    logger.info(
                        f"[Import] Copied FAISS index: {original_sid} -> {final_sid}"
                    )

            # 15. 驗證 FAISS 可載入
            from langchain_community.vectorstores import FAISS

            bge_provider = get_bge_embedding_provider()

            from langchain_core.embeddings import Embeddings as LCEmbeddings

            class BGEWrapper(LCEmbeddings):
                def __init__(self, provider):
                    self._provider = provider

                def embed_query(self, text: str):
                    return self._provider.embed_single(text).tolist()

                def embed_documents(self, texts):
                    return [self._provider.embed_single(t).tolist() for t in texts]

            embedding_wrapper = BGEWrapper(bge_provider)

            first_skill_id = final_skill_ids[0]
            test_faiss_dir = faiss_base_dir / first_skill_id

            vector_store = FAISS.load_local(
                str(test_faiss_dir),
                embedding_wrapper,
                allow_dangerous_deserialization=True,
            )

            logger.info(f"[Import] FAISS index verified successfully")

        except Exception as e:
            # 清理已建立的 FAISS 目錄和資料庫記錄
            for final_sid in final_skill_ids:
                faiss_dir = faiss_base_dir / final_sid
                shutil.rmtree(faiss_dir, ignore_errors=True)

            # 回滾資料庫
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.cursor()
                for final_sid in final_skill_ids:
                    cursor.execute(
                        "DELETE FROM skill_chunk_metadata WHERE skill_id = ?",
                        (final_sid,),
                    )
                    cursor.execute(
                        "DELETE FROM skill_document_mapping WHERE skill_id = ?",
                        (final_sid,),
                    )
                    cursor.execute(
                        "DELETE FROM skill_overviews WHERE skill_id = ?", (final_sid,)
                    )
                    cursor.execute(
                        "DELETE FROM skill_metadata WHERE skill_id = ?", (final_sid,)
                    )
                cursor.execute(
                    "DELETE FROM skill_heads WHERE head_id = ?", (final_head_id,)
                )
                conn.commit()
            finally:
                conn.close()

            raise HTTPException(
                status_code=500, detail=f"FAISS index setup failed: {str(e)}"
            )

        # 16. 清理臨時檔案
        shutil.rmtree(import_temp_dir, ignore_errors=True)

        # 17. 回傳成功訊息
        return {
            "success": True,
            "message": f"Skill '{final_skill_name}' imported successfully",
            "head_id": final_head_id,
            "skill_ids": final_skill_ids,
            "skill_name": final_skill_name,
            "original_skill_name": skill_name,
            "ids_were_changed": ids_were_changed,
            "name_was_renamed": skill_name != final_skill_name,
            "document_count": len(final_skill_ids),
            "total_chunks": len(chunk_data),
            "export_version": export_version,
            "import_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        shutil.rmtree(import_temp_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(import_temp_dir, ignore_errors=True)
        logger.error(f"[Import] Failed to import skill: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
