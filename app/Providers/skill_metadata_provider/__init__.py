"""
Knowledge Metadata Provider.

SQLite-based provider for knowledge metadata persistence.
Handles: knowledge metadata, knowledge overviews, knowledge-document mappings.
"""

from app.Providers.skill_metadata_provider.client import (
    SkillMetadataProvider,
    get_skill_metadata_provider,
)

__all__ = ["SkillMetadataProvider", "get_skill_metadata_provider"]
