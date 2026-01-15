# app/api/v1/endpoints/settings.py
"""
Settings Management Endpoints

API endpoints for retrieving and updating user preferences and system settings.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.core.config import settings
from app.Providers.llm_provider.manager import LLMManager, get_llm_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class UserPreferences(BaseModel):
    """User preferences that can be edited"""
    language: Optional[str] = Field(None, description="Language preference: 'zh' or 'en'")
    default_model: Optional[str] = Field(None, description="Default LLM model name")


class UserPreferencesResponse(BaseModel):
    """Response model for user preferences"""
    language: str = "zh"
    default_model: Optional[str] = None


class SystemSettingsResponse(BaseModel):
    """Response model for system settings (read-only)"""
    llm_provider_url: str
    default_llm_model: str
    llm_temperature: float
    llm_timeout: float
    embedding_model: str
    embedding_dimension: int
    embedding_device: str
    chunk_size: int
    chunk_overlap: int
    chunking_strategy: str
    top_k_results: int
    min_similarity_score: float
    reranking_enabled: bool
    vector_store_backend: str
    milvus_host: Optional[str] = None
    milvus_port: Optional[str] = None


class ModelInfo(BaseModel):
    """Model information"""
    name: str
    size: Optional[int] = None
    modified_at: Optional[str] = None
    digest: Optional[str] = None


class SettingsResponse(BaseModel):
    """Complete settings response"""
    user_preferences: UserPreferencesResponse
    system_settings: SystemSettingsResponse
    available_models: List[ModelInfo] = Field(default_factory=list)
    
    class Config:
        # Ensure all fields are included in JSON, even if empty
        exclude_unset = False
        exclude_none = False


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/settings", tags=["settings"])
async def get_settings(
    manager: LLMManager = Depends(get_llm_manager)
):
    """
    Get all settings (user preferences + system settings + available models)
    
    Returns:
        Combined settings including editable user preferences, read-only system settings, and available Ollama models
    """
    try:
        # User preferences (can be stored in localStorage on client side)
        # For now, return defaults - client will read from localStorage
        user_prefs = UserPreferencesResponse(
            language="zh",
            default_model=None
        )
        
        # System settings (read-only, from config)
        system_settings = SystemSettingsResponse(
            llm_provider_url=settings.LLM_PROVIDER_BASE_URL,
            default_llm_model=settings.DEFAULT_LLM_MODEL,
            llm_temperature=settings.LLM_TEMPERATURE,
            llm_timeout=settings.LLM_TIMEOUT,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dimension=settings.EMBEDDING_DIMENSION,
            embedding_device=settings.EMBEDDING_DEVICE,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            chunking_strategy=settings.CHUNKING_STRATEGY,
            top_k_results=settings.TOP_K_RESULTS,
            min_similarity_score=settings.MIN_SIMILARITY_SCORE,
            reranking_enabled=settings.ENABLE_RERANKING,
            vector_store_backend=settings.VECTOR_STORE_BACKEND,
            milvus_host=settings.MILVUS_HOST if settings.VECTOR_STORE_BACKEND == "milvus" else None,
            milvus_port=settings.MILVUS_PORT if settings.VECTOR_STORE_BACKEND == "milvus" else None
        )
        
        # Get available models from Ollama
        available_models = []
        try:
            logger.info(f"Fetching models from Ollama at {manager.base_url}")
            models = await manager.list_available_models()
            logger.info(f"Fetched {len(models)} models from Ollama: {[m.get('name', 'unknown') for m in models]}")
            if models:
                # Convert dict models to ModelInfo objects
                available_models = [
                    ModelInfo(
                        name=m.get("name", ""),
                        size=m.get("size"),
                        modified_at=m.get("modified_at"),
                        digest=m.get("digest")
                    )
                    for m in models
                    if m.get("name")  # Only include models with names
                ]
                logger.info(f"Converted {len(available_models)} models to ModelInfo: {[m.name for m in available_models]}")
            else:
                logger.warning("No models returned from Ollama - list is empty")
        except Exception as e:
            logger.error(f"Failed to fetch available models: {e}", exc_info=True)
            # Continue without models - frontend can handle empty list
        
        # Ensure available_models is always a list, even if empty
        if not isinstance(available_models, list):
            available_models = []
        
        logger.info(f"Building response with {len(available_models)} models")
        
        # Build response dict explicitly to ensure all fields are included
        response_dict = {
            "user_preferences": {
                "language": user_prefs.language,
                "default_model": user_prefs.default_model
            },
            "system_settings": {
                "llm_provider_url": system_settings.llm_provider_url,
                "default_llm_model": system_settings.default_llm_model,
                "llm_temperature": system_settings.llm_temperature,
                "llm_timeout": system_settings.llm_timeout,
                "embedding_model": system_settings.embedding_model,
                "embedding_dimension": system_settings.embedding_dimension,
                "embedding_device": system_settings.embedding_device,
                "chunk_size": system_settings.chunk_size,
                "chunk_overlap": system_settings.chunk_overlap,
                "chunking_strategy": system_settings.chunking_strategy,
                "top_k_results": system_settings.top_k_results,
                "min_similarity_score": system_settings.min_similarity_score,
                "reranking_enabled": system_settings.reranking_enabled,
                "vector_store_backend": system_settings.vector_store_backend,
                "milvus_host": system_settings.milvus_host,
                "milvus_port": system_settings.milvus_port
            },
            "available_models": [
                {
                    "name": m.name,
                    "size": m.size,
                    "modified_at": m.modified_at,
                    "digest": m.digest
                }
                for m in available_models
            ]
        }
        
        logger.info(f"Response dict keys: {list(response_dict.keys())}")
        logger.info(f"Response available_models in dict: {'available_models' in response_dict}")
        logger.info(f"Response available_models length: {len(response_dict['available_models'])}")
        logger.info(f"Response available_models: {response_dict['available_models']}")
        
        return response_dict
        
    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve settings: {str(e)}")


@router.get("/settings/system", response_model=SystemSettingsResponse, tags=["settings"])
async def get_system_settings():
    """
    Get system settings (read-only)
    
    Returns:
        System configuration settings that cannot be modified via UI
    """
    try:
        return SystemSettingsResponse(
            llm_provider_url=settings.LLM_PROVIDER_BASE_URL,
            default_llm_model=settings.DEFAULT_LLM_MODEL,
            llm_temperature=settings.LLM_TEMPERATURE,
            llm_timeout=settings.LLM_TIMEOUT,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dimension=settings.EMBEDDING_DIMENSION,
            embedding_device=settings.EMBEDDING_DEVICE,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            chunking_strategy=settings.CHUNKING_STRATEGY,
            top_k_results=settings.TOP_K_RESULTS,
            min_similarity_score=settings.MIN_SIMILARITY_SCORE,
            reranking_enabled=settings.ENABLE_RERANKING,
            vector_store_backend=settings.VECTOR_STORE_BACKEND,
            milvus_host=settings.MILVUS_HOST if settings.VECTOR_STORE_BACKEND == "milvus" else None,
            milvus_port=settings.MILVUS_PORT if settings.VECTOR_STORE_BACKEND == "milvus" else None
        )
    except Exception as e:
        logger.error(f"Failed to get system settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve system settings: {str(e)}")


@router.put("/settings/user", response_model=UserPreferencesResponse, tags=["settings"])
async def update_user_preferences(preferences: UserPreferences):
    """
    Update user preferences
    
    Note: User preferences are stored client-side in localStorage.
    This endpoint validates the preferences but doesn't persist them server-side.
    The client should save to localStorage after successful validation.
    
    Args:
        preferences: User preference updates
        
    Returns:
        Updated user preferences
    """
    try:
        # Validate language
        if preferences.language and preferences.language not in ["zh", "en"]:
            raise HTTPException(
                status_code=400,
                detail="Language must be 'zh' or 'en'"
            )
        
        # Return validated preferences
        # Client will save to localStorage
        return UserPreferencesResponse(
            language=preferences.language or "zh",
            default_model=preferences.default_model
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user preferences: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update preferences: {str(e)}")

