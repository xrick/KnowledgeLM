# app/Providers/llm_provider/client.py
"""
LLM Provider Client

Unified client for OpenAI-compatible API endpoints.
Supports streaming responses for real-time chat applications.
Includes resource management for singleton pattern usage.
"""

import httpx
import logging
from typing import AsyncGenerator, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMProviderClient:
    """
    Unified LLM Provider Client

    Communicates with any OpenAI-compatible API endpoint (Ollama, vLLM, llama.cpp).
    Provides streaming responses for optimistic progressive markdown parsing.
    Supports resource management for dynamic model switching.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        model_name: Optional[str] = None
    ):
        """
        Initialize LLM Provider Client

        Args:
            base_url: Base URL of the LLM service (e.g., http://localhost:11434/v1)
            api_key: API key for authentication (optional for local services)
            timeout: Request timeout in seconds (defaults to settings.LLM_TIMEOUT)
            model_name: Default model name for this client instance
        """
        self.base_url = base_url or settings.LLM_PROVIDER_BASE_URL

        # FIX: Ensure base_url has /v1 suffix for Ollama API compatibility
        if self.base_url and not self.base_url.endswith('/v1'):
            self.base_url = f"{self.base_url}/v1"
            logger.warning(f"Auto-corrected base_url to include /v1 suffix: {self.base_url}")

        self.api_key = api_key or settings.LLM_PROVIDER_API_KEY or "ollama"
        self.timeout = timeout or settings.LLM_TIMEOUT
        self.model_name = model_name or settings.DEFAULT_LLM_MODEL

        # Persistent httpx client for connection pooling
        self._http_client: Optional[httpx.AsyncClient] = None

        logger.info(
            f"LLM Provider initialized: model={self.model_name}, "
            f"base_url={self.base_url}, timeout={self.timeout}s"
        )

    async def _get_http_client(self) -> httpx.AsyncClient:
        """
        Get or create the persistent HTTP client

        Returns:
            httpx.AsyncClient: The HTTP client instance
        """
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self._http_client

    async def release(self):
        """
        Release HTTP client resources

        Should be called when switching models or shutting down.
        The client can be recreated automatically on next request.
        """
        if self._http_client is not None and not self._http_client.is_closed:
            logger.info(f"Releasing LLM client resources (model: {self.model_name})")
            await self._http_client.aclose()
            self._http_client = None

    async def get_chat_completion_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncGenerator[bytes, None]:
        """
        Get streaming chat completion from LLM

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (defaults to self.model_name)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional model-specific parameters

        Yields:
            bytes: Server-Sent Events (SSE) formatted chunks

        Example:
            >>> messages = [
            ...     {"role": "system", "content": "You are a helpful assistant."},
            ...     {"role": "user", "content": "Hello!"}
            ... ]
            >>> async for chunk in client.get_chat_completion_stream(messages):
            ...     print(chunk)
        """
        # Use instance model_name as default
        model = model or self.model_name

        request_body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }

        if max_tokens:
            request_body["max_tokens"] = max_tokens

        # Merge additional kwargs
        request_body.update(kwargs)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        endpoint = f"{self.base_url}/chat/completions"

        try:
            # Use fresh client for streaming to avoid connection conflicts
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    endpoint,
                    json=request_body,
                    headers=headers
                ) as response:
                    # Check status without reading response content (streaming-safe)
                    if response.status_code >= 400:
                        error_text = await response.aread()
                        logger.error(f"HTTP {response.status_code} from LLM provider: {error_text.decode()}")
                        raise httpx.HTTPStatusError(
                            f"HTTP {response.status_code}",
                            request=response.request,
                            response=response
                        )

                    # Stream raw SSE chunks directly to client
                    async for chunk in response.aiter_bytes():
                        yield chunk

        except httpx.HTTPStatusError as e:
            # FIX: Don't access e.response.text for streaming responses
            # Error details already logged in line 113 before raising
            logger.error(f"HTTP error from LLM provider: {e.response.status_code}")
            raise
        except httpx.ReadTimeout as e:
            # Specific handling for read timeout
            logger.error(
                f"LLM provider read timeout after {self.timeout}s. "
                f"Consider increasing LLM_TIMEOUT in .env if model is slow to respond. "
                f"Error: {type(e).__name__}: {e}"
            )
            raise
        except httpx.ConnectTimeout as e:
            # Specific handling for connection timeout
            logger.error(
                f"LLM provider connection timeout after {self.timeout}s. "
                f"Check if Ollama is running at {self.base_url}. "
                f"Error: {type(e).__name__}: {e}"
            )
            raise
        except httpx.RequestError as e:
            # Generic request error (network, etc.)
            logger.error(f"Request error to LLM provider: {type(e).__name__}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in LLM provider client: {type(e).__name__}: {e}")
            raise

    async def get_chat_completion(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> dict:
        """
        Get non-streaming chat completion from LLM

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (defaults to self.model_name)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional model-specific parameters

        Returns:
            dict: Complete response from LLM with 'choices', 'usage', etc.
        """
        # Use instance model_name as default
        model = model or self.model_name

        request_body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
        }

        if max_tokens:
            request_body["max_tokens"] = max_tokens

        request_body.update(kwargs)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        endpoint = f"{self.base_url}/chat/completions"

        try:
            client = await self._get_http_client()
            response = await client.post(
                endpoint,
                json=request_body,
                headers=headers
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            # FIX: Safe error logging - attempt to read response text, fallback to status code only
            try:
                error_detail = e.response.text
                logger.error(f"HTTP error from LLM provider: {e.response.status_code} - {error_detail}")
            except Exception:
                logger.error(f"HTTP error from LLM provider: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error to LLM provider: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in LLM provider client: {str(e)}")
            raise


# ============================================================================
# Dependency Injection Helpers
# ============================================================================

def get_llm_provider_client() -> LLMProviderClient:
    """
    FastAPI dependency for LLM Provider Client (creates new instance)

    Note: For singleton access, use get_llm_manager().get_client() instead.

    Usage in endpoints:
        @router.post("/chat")
        async def chat(
            llm_client: LLMProviderClient = Depends(get_llm_provider_client)
        ):
            ...
    """
    return LLMProviderClient()


async def get_llm_client_from_manager() -> LLMProviderClient:
    """
    FastAPI dependency for singleton LLM client via Manager

    This returns the managed singleton client instance.

    Usage in endpoints:
        @router.post("/chat")
        async def chat(
            llm_client: LLMProviderClient = Depends(get_llm_client_from_manager)
        ):
            ...
    """
    from app.Providers.llm_provider.manager import get_llm_manager
    manager = get_llm_manager()
    return await manager.get_client()


# Alias for compatibility
# ✅ FIXED: Use manager-based client to respect model switching
get_llm_provider = get_llm_client_from_manager
