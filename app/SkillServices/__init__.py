"""
Skill-based RAG Services.

This package contains services for skill-based retrieval system,
operating independently from the file-based system in app/Services/.

Components:
- base_retrieval: Abstract interface for retrieval services
- skill_retrieval_service: Skill-based vector retrieval
- skill_ingestion_service: Skill content processing and chunking
- unified_retrieval_service: Orchestrator for file + skill retrieval
"""

__version__ = "1.0.0"
