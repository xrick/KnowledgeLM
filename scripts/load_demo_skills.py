#!/usr/bin/env python
"""
Demo Skills Pre-loader (Corrected)
Loads 3 demo skills for the Skill-Based RAG Demo.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import Correct Services & Providers
from app.Providers.skill_metadata_provider.client import SkillMetadataProvider
from app.SkillServices.skill_ingestion_service import SkillIngestionService
from app.SkillServices.skill_retrieval_service import SkillRetrievalService
from app.Providers.vector_store_provider.client import VectorStoreProvider
from app.Providers.embedding_provider.client import EmbeddingProvider

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

DEMO_SKILLS = [
    {
        "name": "AI Research",
        "category": "Research",
        "level": "advanced",
        "tags": ["ai", "llm", "rag", "transformer"],
        "description": "2024 AI Research Papers: Deep Learning, RL, NLP.",
        "content": """
        [Deep Learning Advances]
        Deep Learning breakthroughs in 2024 include optimized Transformer architectures improving efficiency by 50%.
        New attention mechanisms handle longer sequences better.
        Self-supervised learning is now mainstream for training large models using contrastive learning.

        [LLM Optimization]
        Quantization (8-bit, 4-bit) reduces model size by 75% with minimal performance loss.
        Knowledge Distillation allows small models to reach 95% of teacher performance.
        Parameter-Efficient Fine-Tuning (PEFT) like LoRA reduces computational resources significantly.

        [AI Safety]
        Adversarial training improves robustness against complex attacks.
        Explainable AI (XAI) visualizes attention maps to reveal reasoning processes.
        RLHF (Reinforcement Learning from Human Feedback) aligns models with human values.
        """
    },
    {
        "name": "Python Documentation",
        "category": "Programming",
        "level": "intermediate",
        "tags": ["python", "asyncio", "fastapi"],
        "description": "Python Frameworks: FastAPI, Django, Data Science.",
        "content": """
        [FastAPI Advanced]
        Dependency Injection system allows elegant code organization via Depends().
        Async/await handles I/O bound tasks efficiently.
        Automatic OpenAPI documentation generation using Swagger UI.

        [Python Data Science]
        Pandas 2.0 uses PyArrow backend for massive performance gains.
        NumPy vectorization is 100x faster than loops.
        Scikit-learn Pipelines simplify preprocessing and training workflows.

        [Django Enterprise]
        Multi-tenant patterns for SaaS applications.
        Django REST Framework ViewSets and Routers simplify API development.
        Celery integration for handling background tasks asynchronously.
        """
    },
    {
        "name": "Business Report 2025",
        "category": "Business",
        "level": "beginner",
        "tags": ["report", "strategy", "2025"],
        "description": "2025 Market Analysis and Strategic Outlook.",
        "content": """
        [Market Trends 2024]
        AI-driven automation will save 30% of operating costs.
        Generative AI market size expected to reach $200B.
        Digital transformation accelerates with cloud-native microservices.

        [Data Driven Decisions]
        KPI tracking ensures alignment with business goals.
        A/B testing optimizes product strategies.
        Predictive analytics identifies opportunities early.

        [Digital Transformation]
        Shift from digitization to digital-first.
        API economy creates new revenue streams.
        Agile culture promotes innovation and cross-functional collaboration.
        """
    }
]

async def main():
    logger.info("🚀 Starting Demo Skills Loading...")
    
    # 1. Initialize Providers
    metadata_provider = SkillMetadataProvider()
    await metadata_provider.initialize_database()
    
    ingestion_service = SkillIngestionService()
    
    # Use existing EmbeddingProvider (Sentence-Transformers)
    embedding_provider = EmbeddingProvider() 
    vector_store_provider = VectorStoreProvider()
    
    retrieval_service = SkillRetrievalService(
        embedding_provider=embedding_provider,
        vector_store_provider=vector_store_provider
    )

    # 2. Process Skills
    for skill_data in DEMO_SKILLS:
        logger.info(f"Processing skill: {skill_data['name']}...")
        
        try:
            # Process Text
            processed = await ingestion_service.process_skill(
                skill_name=skill_data["name"],
                skill_content=skill_data["content"],
                skill_description=skill_data["description"],
                skill_category=skill_data["category"],
                skill_level=skill_data["level"],
                tags=skill_data["tags"],
                skill_metadata_provider=metadata_provider
            )
            
            skill_id = processed["skill_id"]
            chunks = [c["content"] for c in processed["chunks"]]
            metadatas = [c["metadata"] for c in processed["chunks"]]
            
            # Add to Vector Store
            await retrieval_service.add_content(
                content_id=skill_id,
                chunks=chunks,
                metadata=metadatas
            )
            
            # Add Metadata
            await metadata_provider.create_skill(
                skill_id=skill_id,
                skill_name=skill_data["name"],
                skill_description=skill_data["description"],
                skill_category=skill_data["category"],
                skill_level=skill_data["level"],
                tags=skill_data["tags"],
                total_chunks=processed["chunk_count"]
            )
            
            logger.info(f"✅ Created skill: {skill_data['name']} ({skill_id})")
            
        except ValueError as e:
             # Ignore if exists
             logger.warning(f"Skipping {skill_data['name']} (Duplicate?): {e}")
        except Exception as e:
            logger.error(f"❌ Failed to create skill {skill_data['name']}: {e}")

    logger.info("✨ All Demo Skills loaded successfully!")

if __name__ == "__main__":
    asyncio.run(main())
