"""
Skill Metadata Provider.

SQLite-based provider for skill metadata persistence.
Handles: skill metadata, skill overviews, skill-document mappings.
"""

from app.Providers.skill_metadata_provider.client import (
    SkillMetadataProvider,
    get_skill_metadata_provider
)

__all__ = [
    "SkillMetadataProvider",
    "get_skill_metadata_provider"
]
