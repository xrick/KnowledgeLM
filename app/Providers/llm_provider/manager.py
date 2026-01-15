# app/Providers/llm_provider/manager.py
"""
LLM Manager - Singleton Pattern with Dynamic Model Switching

Manages LLM client lifecycle with support for:
- Dynamic model switching at runtime
- Resource cleanup when switching models
- Thread-safe singleton access
- Available models discovery via Ollama API
"""

import asyncio
import httpx
import logging
from typing import Optional, List, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMManager:
    """
    LLM Manager Singleton

    Manages a single LLMProviderClient instance with support for
    dynamic model switching and resource cleanup.

    Usage:
        manager = get_llm_manager()
        client = await manager.get_client()
        await manager.switch_model("llama3.2:latest")
    """

    _instance: Optional["LLMManager"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._client: Optional["LLMProviderClient"] = None
        self._current_model: str = settings.DEFAULT_LLM_MODEL
        self._base_url: str = settings.LLM_PROVIDER_BASE_URL
        self._api_key: str = settings.LLM_PROVIDER_API_KEY or "ollama"
        self._client_lock: asyncio.Lock = asyncio.Lock()

        logger.info(f"LLMManager initialized with default model: {self._current_model}")

    @property
    def current_model(self) -> str:
        """Get the current model name"""
        return self._current_model

    @property
    def base_url(self) -> str:
        """Get the LLM provider base URL"""
        return self._base_url

    async def get_client(self) -> "LLMProviderClient":
        """
        Get the singleton LLM client instance

        Creates the client lazily on first access.
        Thread-safe via asyncio.Lock.

        Returns:
            LLMProviderClient: The singleton client instance
        """
        async with self._client_lock:
            if self._client is None:
                # Import here to avoid circular import
                from app.Providers.llm_provider.client import LLMProviderClient

                self._client = LLMProviderClient(
                    base_url=self._base_url,
                    api_key=self._api_key,
                    model_name=self._current_model
                )
                logger.info(f"Created LLM client with model: {self._current_model}")

            return self._client

    async def switch_model(self, new_model: str) -> Dict[str, Any]:
        """
        Switch to a different LLM model

        Releases the current client resources and creates a new one
        with the specified model.

        Args:
            new_model: The model name to switch to (e.g., "llama3.2:latest")

        Returns:
            dict: Result with old_model, new_model, and success status
        """
        async with self._client_lock:
            old_model = self._current_model

            # Skip if already using this model
            if old_model == new_model:
                logger.info(f"Already using model: {new_model}")
                return {
                    "success": True,
                    "old_model": old_model,
                    "new_model": new_model,
                    "message": "Already using this model"
                }

            try:
                # Release current client if exists
                if self._client is not None:
                    logger.info(f"Releasing current LLM client (model: {old_model})")
                    await self._client.release()
                    self._client = None

                # Update current model
                self._current_model = new_model

                # Create new client with new model
                from app.Providers.llm_provider.client import LLMProviderClient

                self._client = LLMProviderClient(
                    base_url=self._base_url,
                    api_key=self._api_key,
                    model_name=new_model
                )

                logger.info(f"Switched LLM model: {old_model} -> {new_model}")

                return {
                    "success": True,
                    "old_model": old_model,
                    "new_model": new_model,
                    "message": f"Successfully switched from {old_model} to {new_model}"
                }

            except Exception as e:
                logger.error(f"Failed to switch model: {e}")
                # Attempt to restore previous model
                self._current_model = old_model
                return {
                    "success": False,
                    "old_model": old_model,
                    "new_model": new_model,
                    "error": str(e)
                }

    async def refresh(self) -> Dict[str, Any]:
        """
        Force refresh the LLM client

        Releases and recreates the client with current settings.
        Useful for reconnecting after connection issues.

        Returns:
            dict: Result with model and success status
        """
        async with self._client_lock:
            try:
                if self._client is not None:
                    await self._client.release()
                    self._client = None

                from app.Providers.llm_provider.client import LLMProviderClient

                self._client = LLMProviderClient(
                    base_url=self._base_url,
                    api_key=self._api_key,
                    model_name=self._current_model
                )

                logger.info(f"Refreshed LLM client with model: {self._current_model}")

                return {
                    "success": True,
                    "model": self._current_model,
                    "message": "LLM client refreshed successfully"
                }

            except Exception as e:
                logger.error(f"Failed to refresh LLM client: {e}")
                return {
                    "success": False,
                    "model": self._current_model,
                    "error": str(e)
                }

    async def list_available_models(self) -> List[Dict[str, Any]]:
        """
        List available models from Ollama

        Queries the Ollama API to get list of installed models.

        Returns:
            list: List of available model info dicts
        """
        try:
            # Ollama API endpoint for listing models
            # Note: /v1 is for OpenAI-compatible API, /api is for native Ollama API
            base = self._base_url.replace("/v1", "")
            endpoint = f"{base}/api/tags"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(endpoint)
                response.raise_for_status()
                data = response.json()

                models = data.get("models", [])
                logger.info(f"Found {len(models)} available models from Ollama")

                return [
                    {
                        "name": m.get("name"),
                        "size": m.get("size"),
                        "modified_at": m.get("modified_at"),
                        "digest": m.get("digest", "")[:12] + "..." if m.get("digest") else None
                    }
                    for m in models
                ]

        except httpx.ConnectError:
            logger.warning("Cannot connect to Ollama - is it running?")
            return []
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []

    async def get_status(self) -> Dict[str, Any]:
        """
        Get current LLM manager status

        Returns:
            dict: Status information including model, connection, etc.
        """
        is_connected = False
        available_models = []

        try:
            available_models = await self.list_available_models()
            is_connected = len(available_models) > 0
        except Exception:
            pass

        return {
            "current_model": self._current_model,
            "base_url": self._base_url,
            "client_initialized": self._client is not None,
            "is_connected": is_connected,
            "available_models_count": len(available_models)
        }

    async def shutdown(self):
        """
        Shutdown the LLM manager and release all resources

        Should be called during application shutdown.
        """
        async with self._client_lock:
            if self._client is not None:
                logger.info("Shutting down LLM manager")
                await self._client.release()
                self._client = None


# Global singleton instance
_llm_manager: Optional[LLMManager] = None


def get_llm_manager() -> LLMManager:
    """
    Get the global LLM Manager singleton

    Usage in FastAPI endpoints:
        @router.post("/switch")
        async def switch_model(
            manager: LLMManager = Depends(get_llm_manager)
        ):
            ...

    Returns:
        LLMManager: The singleton manager instance
    """
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    return _llm_manager
