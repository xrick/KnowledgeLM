"""
Image Generation Manager (Singleton)

Mirrors LLMManager pattern: __new__ singleton + threading.Lock for thread safety.
Uses threading.Lock (not asyncio.Lock) because torch model loading is synchronous.
"""

import logging
import threading
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

_image_gen_manager: Optional["ImageGenManager"] = None


class ImageGenManager:
    """
    Singleton manager for the image generation pipeline.

    Ensures the heavy model is loaded only once across the entire application.
    Thread-safe via threading.Lock (torch operations are synchronous).

    Usage:
        manager = ImageGenManager()
        image = manager.generate("A cat in space")
        manager.release()  # free VRAM when done
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # double-checked locking
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        model_id: str = "segmind/SSD-1B",
        device: str = "cuda",
    ):
        if self._initialized:
            return

        self._initialized = True
        self._model_id = model_id
        self._device = device
        self._client: Optional["ImageGenClient"] = None
        self._client_lock = threading.Lock()

        logger.info(
            f"ImageGenManager initialized (model={self._model_id}, device={self._device})"
        )

    def get_client(self) -> "ImageGenClient":
        """
        Get the singleton ImageGenClient instance.

        Creates the client lazily on first access.
        Thread-safe via threading.Lock.
        """
        with self._client_lock:
            if self._client is None:
                from app.Providers.image_gen_provider.client import ImageGenClient

                self._client = ImageGenClient(
                    model_id=self._model_id,
                    device=self._device,
                )
                logger.info(f"Created ImageGenClient with model: {self._model_id}")
            return self._client

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "ugly, blurry, poor quality",
        save_path: Optional[str] = None,
        **kwargs,
    ) -> Image.Image:
        """
        Convenience method: get client and generate in one call.
        """
        client = self.get_client()
        return client.generate(
            prompt=prompt,
            negative_prompt=negative_prompt,
            save_path=save_path,
            **kwargs,
        )

    def release(self):
        """Release the pipeline and free GPU memory."""
        with self._client_lock:
            if self._client is not None:
                self._client.release()
                self._client = None
                logger.info("ImageGenManager: pipeline released")

    def shutdown(self):
        """Alias for release(), matches LLMManager.shutdown() convention."""
        self.release()
        ImageGenManager._instance = None
        self._initialized = False


def get_image_gen_manager() -> ImageGenManager:
    """
    Get the global ImageGenManager singleton.

    Usage in FastAPI endpoints:
        @router.post("/generate")
        async def generate_image(
            manager: ImageGenManager = Depends(get_image_gen_manager)
        ):
            ...
    """
    global _image_gen_manager
    if _image_gen_manager is None:
        _image_gen_manager = ImageGenManager()
    return _image_gen_manager
