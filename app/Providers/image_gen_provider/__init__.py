"""
Image Generation Provider Module

Singleton-managed StableDiffusionXL pipeline (SSD-1B) for text-to-image generation.
Follows the same architectural pattern as llm_provider.

Components:
- ImageGenClient: Pipeline wrapper for model loading and inference
- ImageGenManager: Singleton manager ensuring single model instance
- get_image_gen_manager: Dependency injection for FastAPI endpoints
"""

from app.Providers.image_gen_provider.client import ImageGenClient
from app.Providers.image_gen_provider.manager import (
    ImageGenManager,
    get_image_gen_manager,
)

__all__ = [
    "ImageGenClient",
    "ImageGenManager",
    "get_image_gen_manager",
]
