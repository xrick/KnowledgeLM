"""
Image Generation Provider Client

Wraps StableDiffusionXL-compatible pipelines (e.g. SSD-1B) for inference.
Follows the same pattern as LLMProviderClient.
"""

import logging
from pathlib import Path
from typing import Optional

import torch
from PIL import Image

logger = logging.getLogger(__name__)


class ImageGenClient:
    """
    Thin wrapper around a StableDiffusionXL pipeline.

    Handles model loading, inference, and VRAM cleanup.
    Not a singleton itself - lifecycle is managed by ImageGenManager.
    """

    def __init__(
        self,
        model_id: str = "segmind/SSD-1B",
        device: str = "cuda",
        torch_dtype: torch.dtype = torch.float16,
    ):
        self._model_id = model_id
        self._device = device
        self._torch_dtype = torch_dtype
        self._pipe = None

    def _ensure_loaded(self):
        """Lazy-load the pipeline on first use."""
        if self._pipe is not None:
            return

        from diffusers import StableDiffusionXLPipeline

        logger.info(f"Loading image generation model: {self._model_id}")
        self._pipe = StableDiffusionXLPipeline.from_pretrained(
            self._model_id,
            torch_dtype=self._torch_dtype,
            use_safetensors=True,
            variant="fp16",
        ).to(self._device)
        logger.info(f"Model loaded on {self._device}")

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "ugly, blurry, poor quality",
        num_inference_steps: int = 25,
        guidance_scale: float = 7.0,
        width: int = 1024,
        height: int = 1024,
        save_path: Optional[str] = None,
        **kwargs,
    ) -> Image.Image:
        """
        Generate an image from a text prompt.

        Args:
            prompt: Text description of the desired image.
            negative_prompt: What to avoid in the image.
            num_inference_steps: Denoising steps (higher = better quality, slower).
            guidance_scale: How closely to follow the prompt.
            width: Output image width.
            height: Output image height.
            save_path: If provided, save the image to this path.
            **kwargs: Additional arguments passed to the pipeline.

        Returns:
            PIL.Image.Image: The generated image.
        """
        self._ensure_loaded()

        image = self._pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            width=width,
            height=height,
            **kwargs,
        ).images[0]

        if save_path:
            path = Path(save_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(str(path))
            logger.info(f"Image saved to {path}")

        return image

    def release(self):
        """Release GPU memory."""
        if self._pipe is not None:
            del self._pipe
            self._pipe = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("Image generation pipeline released")
