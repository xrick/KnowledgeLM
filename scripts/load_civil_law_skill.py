#!/usr/bin/env python3
"""
Load Civil Law Skill with BGE-M3 Embeddings
專門處理六法全書-民法的載入腳本
Processes: 家事事件法, 強制執行法, 民事訴訟法, 民法, 消費者保護法
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.SkillServices.pdf_skill_ingestion_service import get_pdf_skill_ingestion_service
from app.Providers.skill_metadata_provider.client import get_skill_metadata_provider
from app.Providers.vector_store_provider.client import get_vector_store_provider

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/civil_law_loading.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# Civil Law Skill Configuration
CIVIL_LAW_CONFIG = {
    'directory': 'refData/rawdata/law/民法',
    'skill_name': '六法全書-民法',
    'skill_description': '台灣民法及相關法律文件，包含民法總則、債權、物權、親屬、繼承，以及民事訴訟法、家事事件法、強制執行法、消費者保護法等完整民事法律體系',
    'skill_category': 'Legal-Civil',
    'expected_files': [
        '家事事件法.pdf',
        '強制執行法.pdf',
        '民事訴訟法.pdf',
        '民法.pdf',
        '消費者保護法.pdf'
    ]
}

async def verify_files():
    """Verify all expected PDF files exist"""
    logger.info("=" * 60)
    logger.info("📁 Verifying Civil Law PDF Files")
    logger.info("=" * 60)

    base_path = Path(CIVIL_LAW_CONFIG['directory'])
    if not base_path.exists():
        logger.error(f"❌ Directory not found: {base_path}")
        return False

    all_files_exist = True
    total_size = 0

    for pdf_file in CIVIL_LAW_CONFIG['expected_files']:
        file_path = base_path / pdf_file
        if file_path.exists():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            total_size += size_mb
            logger.info(f"✅ Found: {pdf_file} ({size_mb:.2f} MB)")
        else:
            logger.error(f"❌ Missing: {pdf_file}")
            all_files_exist = False

    logger.info(f"📊 Total size: {total_size:.2f} MB")
    return all_files_exist

async def check_existing_skill(metadata_provider):
    """Check if civil law skill already exists"""
    try:
        all_skills = await metadata_provider.list_all_skills()
        for skill in all_skills:
            if skill.get('skill_name') == CIVIL_LAW_CONFIG['skill_name']:
                logger.warning(f"⚠️ Skill '{CIVIL_LAW_CONFIG['skill_name']}' already exists")
                logger.info(f"   ID: {skill.get('skill_id')}")
                logger.info(f"   Chunks: {skill.get('total_chunks')}")
                return True
        return False
    except Exception as e:
        logger.warning(f"Could not check existing skills: {e}")
        return False

async def load_civil_law_skill():
    """Main function to load civil law skill with BGE-M3"""

    start_time = time.time()

    logger.info("=" * 60)
    logger.info("🏛️ Civil Law Skill Loader with BGE-M3")
    logger.info("=" * 60)
    logger.info(f"📅 Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Step 1: Verify files
    if not await verify_files():
        logger.error("❌ File verification failed. Exiting.")
        return False

    # Step 2: Initialize providers
    logger.info("\n📦 Initializing providers...")
    metadata_provider = get_skill_metadata_provider()
    vector_provider = get_vector_store_provider()
    pdf_service = get_pdf_skill_ingestion_service()

    # Step 3: Check if skill exists
    if await check_existing_skill(metadata_provider):
        user_input = input("\n⚠️ Skill already exists. Overwrite? (y/n): ")
        if user_input.lower() != 'y':
            logger.info("Cancelled by user")
            return False
        # TODO: Delete existing skill if needed

    # Step 4: Process PDFs
    logger.info("\n🔄 Processing Civil Law PDFs with BGE-M3...")
    logger.info(f"   Directory: {CIVIL_LAW_CONFIG['directory']}")
    logger.info(f"   Expected files: {len(CIVIL_LAW_CONFIG['expected_files'])}")

    try:
        # Process the entire directory
        result = await pdf_service.process_pdf_directory(
            directory_path=CIVIL_LAW_CONFIG['directory'],
            skill_name=CIVIL_LAW_CONFIG['skill_name'],
            skill_description=CIVIL_LAW_CONFIG['skill_description'],
            skill_category=CIVIL_LAW_CONFIG['skill_category'],
            metadata_provider=metadata_provider,
            vector_provider=vector_provider
        )

        # Step 5: Display results
        elapsed_time = time.time() - start_time

        logger.info("\n" + "=" * 60)
        logger.info("✅ Civil Law Skill Successfully Created!")
        logger.info("=" * 60)
        logger.info(f"📊 Processing Summary:")
        logger.info(f"   Skill ID: {result['skill_id']}")
        logger.info(f"   Skill Name: {result['skill_name']}")
        logger.info(f"   Documents Processed: {result['documents_processed']}")
        logger.info(f"   Total Pages: {result['total_pages']}")
        logger.info(f"   Total Chunks: {result['total_chunks']}")
        logger.info(f"   Embedding Model: {result['embedding_model']}")
        logger.info(f"   Dimension: {result['embedding_dimension']}")
        logger.info(f"   Processing Time: {elapsed_time:.2f} seconds")

        logger.info("\n📚 Documents included:")
        for doc_name in result['documents']:
            logger.info(f"   - {doc_name}.pdf")

        # Step 6: Verification queries
        logger.info("\n💡 Verification & Testing:")
        logger.info("   You can now test with queries like:")
        logger.info("   - '契約成立的要件'")
        logger.info("   - '債權債務關係'")
        logger.info("   - '繼承順序規定'")
        logger.info("   - '消費者保護法的適用範圍'")
        logger.info("   - '家事事件的管轄法院'")

        # Step 7: FAISS index location
        logger.info(f"\n📂 FAISS Index Location:")
        logger.info(f"   data/faiss_indices/skills/{result['skill_id']}/")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to create civil law skill: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

async def verify_skill_creation():
    """Verify the skill was created successfully"""
    logger.info("\n🔍 Verifying Skill Creation...")

    metadata_provider = get_skill_metadata_provider()

    # Check database
    skills = await metadata_provider.list_all_skills()
    civil_skill = None
    for skill in skills:
        if skill.get('skill_name') == CIVIL_LAW_CONFIG['skill_name']:
            civil_skill = skill
            break

    if civil_skill:
        logger.info("✅ Database verification passed")
        logger.info(f"   Skill ID: {civil_skill.get('skill_id')}")
        logger.info(f"   Total chunks: {civil_skill.get('total_chunks')}")

        # Check FAISS index
        faiss_path = Path(f"data/faiss_indices/skills/{civil_skill.get('skill_id')}")
        if faiss_path.exists():
            logger.info("✅ FAISS index verification passed")
            logger.info(f"   Path: {faiss_path}")
        else:
            logger.error("❌ FAISS index not found")
            return False

        return True
    else:
        logger.error("❌ Skill not found in database")
        return False

if __name__ == "__main__":
    try:
        logger.info("🚀 Starting Civil Law Skill Loader")

        # Run main loading process
        success = asyncio.run(load_civil_law_skill())

        if success:
            # Verify creation
            verified = asyncio.run(verify_skill_creation())
            if verified:
                logger.info("\n🎉 All verifications passed! Civil Law Skill is ready for use.")
            else:
                logger.warning("\n⚠️ Skill created but verification failed.")
        else:
            logger.error("\n❌ Civil Law Skill creation failed.")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("\n⚠️ Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)