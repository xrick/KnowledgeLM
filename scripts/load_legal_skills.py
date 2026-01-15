#!/usr/bin/env python3
"""
Load Legal Document Skills with BGE-M3 Embeddings
Creates skills for 六法全書-刑法 and 六法全書-民法
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.SkillServices.pdf_skill_ingestion_service import get_pdf_skill_ingestion_service
from app.Providers.skill_metadata_provider.client import get_skill_metadata_provider
from app.Providers.vector_store_provider.client import get_vector_store_provider

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Legal Skills Configuration
LEGAL_SKILLS = [
    {
        'directory': 'refData/rawdata/law/刑法',
        'skill_name': '六法全書-刑法',
        'skill_description': '台灣刑法及刑事訴訟法相關法律文件，包含刑法總則、分則及刑事訴訟程序',
        'skill_category': 'Legal-Criminal'
    },
    {
        'directory': 'refData/rawdata/law/民法',
        'skill_name': '六法全書-民法',
        'skill_description': '台灣民法及民事訴訟法相關法律文件，包含民法總則、債權、物權、親屬、繼承及民事訴訟程序',
        'skill_category': 'Legal-Civil'
    }
]

async def check_existing_skills(metadata_provider) -> set:
    """Check which skills already exist"""
    try:
        existing_skills = await metadata_provider.list_all_skills()
        skill_names = {skill['skill_name'] for skill in existing_skills}
        return skill_names
    except Exception as e:
        logger.warning(f"Could not check existing skills: {e}")
        return set()

async def load_legal_skills():
    """Main function to load legal document skills"""

    logger.info("=" * 60)
    logger.info("🏛️ Legal Document Skills Loader with BGE-M3")
    logger.info("=" * 60)

    # Initialize providers
    metadata_provider = get_skill_metadata_provider()
    vector_provider = get_vector_store_provider()
    pdf_service = get_pdf_skill_ingestion_service()

    # Check existing skills
    existing_skills = await check_existing_skills(metadata_provider)
    logger.info(f"Existing skills: {existing_skills}")

    # Process each legal skill
    results = []
    for skill_config in LEGAL_SKILLS:
        skill_name = skill_config['skill_name']

        # Check if already exists
        if skill_name in existing_skills:
            logger.warning(f"⚠️ Skill '{skill_name}' already exists, skipping...")
            continue

        logger.info(f"\n📚 Processing: {skill_name}")
        logger.info(f"   Directory: {skill_config['directory']}")

        try:
            # Process the PDF directory
            result = await pdf_service.process_pdf_directory(
                directory_path=skill_config['directory'],
                skill_name=skill_name,
                skill_description=skill_config['skill_description'],
                skill_category=skill_config['skill_category'],
                metadata_provider=metadata_provider,
                vector_provider=vector_provider
            )

            results.append(result)

            # Display results
            logger.info(f"\n✅ Successfully created skill: {skill_name}")
            logger.info(f"   Skill ID: {result['skill_id']}")
            logger.info(f"   Documents: {result['documents_processed']}")
            logger.info(f"   Total Pages: {result['total_pages']}")
            logger.info(f"   Total Chunks: {result['total_chunks']}")
            logger.info(f"   Embedding Model: {result['embedding_model']}")
            logger.info(f"   Dimension: {result['embedding_dimension']}")
            logger.info(f"   Files processed:")
            for doc_name in result['documents']:
                logger.info(f"     - {doc_name}.pdf")

        except Exception as e:
            logger.error(f"❌ Failed to create skill '{skill_name}': {str(e)}")
            continue

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 Summary")
    logger.info("=" * 60)

    if results:
        logger.info(f"✅ Successfully created {len(results)} legal skills:")
        for result in results:
            logger.info(f"   - {result['skill_name']}: {result['total_pages']} pages, {result['total_chunks']} chunks")

        logger.info("\n💡 Testing Instructions:")
        logger.info("   1. Start the system: ./start_system.sh")
        logger.info("   2. Open browser: http://localhost:8001/skill-demo")
        logger.info("   3. Select a legal skill")
        logger.info("   4. Try queries like:")
        logger.info("      - 刑法: '詐欺', '竊盜', '傷害罪'")
        logger.info("      - 民法: '契約', '債權', '繼承'")

    else:
        logger.info("ℹ️ No new skills created (may already exist)")

    logger.info("\n🎯 BGE-M3 Features:")
    logger.info("   - 1024-dimensional embeddings")
    logger.info("   - Multilingual support (optimized for Chinese)")
    logger.info("   - Page-based chunking with citations")
    logger.info("   - Format: [document_name-page_xxx]")

if __name__ == "__main__":
    try:
        asyncio.run(load_legal_skills())
    except KeyboardInterrupt:
        logger.info("\n⚠️ Process interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        sys.exit(1)