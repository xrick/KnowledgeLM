# app/api/v1/endpoints/llm.py
"""
LLM Management API Endpoints

Provides endpoints for:
- Listing available LLM models
- Getting current model info
- Switching between models
- Refreshing LLM connection
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from app.Providers.llm_provider.manager import LLMManager, get_llm_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class SwitchModelRequest(BaseModel):
    """Request to switch LLM model"""
    model_name: str = Field(..., description="Name of the model to switch to", example="llama3.2:latest")


class SwitchModelResponse(BaseModel):
    """Response from model switch operation"""
    success: bool
    old_model: str
    new_model: str
    message: Optional[str] = None
    error: Optional[str] = None


class CurrentModelResponse(BaseModel):
    """Response with current model information"""
    current_model: str
    base_url: str
    client_initialized: bool


class ModelInfo(BaseModel):
    """Information about an available model"""
    name: str
    size: Optional[int] = None
    modified_at: Optional[str] = None
    digest: Optional[str] = None


class ModelsListResponse(BaseModel):
    """Response with list of available models"""
    models: List[ModelInfo]
    count: int
    current_model: str


class RefreshResponse(BaseModel):
    """Response from refresh operation"""
    success: bool
    model: str
    message: Optional[str] = None
    error: Optional[str] = None


class StatusResponse(BaseModel):
    """Response with LLM manager status"""
    current_model: str
    base_url: str
    client_initialized: bool
    is_connected: bool
    available_models_count: int


# =============================================================================
# API Endpoints
# =============================================================================

@router.get(
    "/current",
    response_model=CurrentModelResponse,
    summary="Get Current LLM Model",
    description="Returns information about the currently active LLM model."
)
async def get_current_model(
    manager: LLMManager = Depends(get_llm_manager)
) -> CurrentModelResponse:
    """
    Get the current LLM model information.

    Returns:
        Current model name, base URL, and client status.
    """
    return CurrentModelResponse(
        current_model=manager.current_model,
        base_url=manager.base_url,
        client_initialized=manager._client is not None
    )


@router.get(
    "/models",
    response_model=ModelsListResponse,
    summary="List Available LLM Models",
    description="Lists all LLM models available from the Ollama server."
)
async def list_models(
    manager: LLMManager = Depends(get_llm_manager)
) -> ModelsListResponse:
    """
    List all available LLM models from Ollama.

    Returns:
        List of available models with their metadata.
    """
    models = await manager.list_available_models()

    return ModelsListResponse(
        models=[ModelInfo(**m) for m in models],
        count=len(models),
        current_model=manager.current_model
    )


@router.post(
    "/switch",
    response_model=SwitchModelResponse,
    summary="Switch LLM Model",
    description="Switches to a different LLM model. Releases current model resources first."
)
async def switch_model(
    request: SwitchModelRequest,
    manager: LLMManager = Depends(get_llm_manager)
) -> SwitchModelResponse:
    """
    Switch to a different LLM model.

    This will:
    1. Release resources of the current model
    2. Initialize the new model
    3. Return success/failure status

    Args:
        request: Contains the model_name to switch to

    Returns:
        Result of the switch operation
    """
    logger.info(f"Request to switch LLM model to: {request.model_name}")

    result = await manager.switch_model(request.model_name)

    if not result["success"]:
        logger.error(f"Failed to switch model: {result.get('error')}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to switch model: {result.get('error')}"
        )

    return SwitchModelResponse(**result)


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Refresh LLM Connection",
    description="Force refresh the LLM client connection. Useful for reconnecting after issues."
)
async def refresh_llm(
    manager: LLMManager = Depends(get_llm_manager)
) -> RefreshResponse:
    """
    Force refresh the LLM client.

    This will:
    1. Release current client resources
    2. Create a new client with current settings
    3. Return success/failure status

    Returns:
        Result of the refresh operation
    """
    logger.info("Request to refresh LLM client")

    result = await manager.refresh()

    if not result["success"]:
        logger.error(f"Failed to refresh LLM client: {result.get('error')}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh LLM client: {result.get('error')}"
        )

    return RefreshResponse(**result)


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Get LLM Status",
    description="Returns comprehensive status of the LLM manager including connection state."
)
async def get_status(
    manager: LLMManager = Depends(get_llm_manager)
) -> StatusResponse:
    """
    Get comprehensive LLM manager status.

    Returns:
        Status including current model, connection state, and available models count.
    """
    status = await manager.get_status()
    return StatusResponse(**status)


@router.post(
    "/test",
    summary="Test LLM Connection",
    description="Send a simple test message to verify LLM is responding."
)
async def test_llm(
    manager: LLMManager = Depends(get_llm_manager)
) -> Dict[str, Any]:
    """
    Test the LLM connection with a simple prompt.

    Returns:
        Test result including response or error.
    """
    try:
        client = await manager.get_client()

        messages = [
            {"role": "user", "content": "Hello! Please respond with 'LLM connection successful.'"}
        ]

        response = await client.get_chat_completion(
            messages=messages,
            max_tokens=50
        )

        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        return {
            "success": True,
            "model": manager.current_model,
            "response": content[:200],  # Limit response length
            "usage": response.get("usage", {})
        }

    except Exception as e:
        logger.error(f"LLM test failed: {e}")
        return {
            "success": False,
            "model": manager.current_model,
            "error": str(e)
        }
