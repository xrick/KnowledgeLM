# app/Providers/llm_provider/__init__.py
"""
LLM Provider Module

Unified OpenAI-compatible API client for various LLM backends:
- Ollama
- vLLM
- llama.cpp
- Any OpenAI-compatible endpoint

Components:
- LLMProviderClient: The HTTP client for LLM API calls
- LLMManager: Singleton manager for dynamic model switching
- get_llm_manager: Dependency injection for manager access
- get_llm_client_from_manager: Dependency injection for singleton client
"""

from app.Providers.llm_provider.client import (
    LLMProviderClient,
    get_llm_provider_client,
    get_llm_client_from_manager,
    get_llm_provider,  # Alias for compatibility
)
from app.Providers.llm_provider.manager import (
    LLMManager,
    get_llm_manager,
)

__all__ = [
    # Client
    "LLMProviderClient",
    "get_llm_provider_client",
    "get_llm_client_from_manager",
    "get_llm_provider",
    # Manager
    "LLMManager",
    "get_llm_manager",
]
