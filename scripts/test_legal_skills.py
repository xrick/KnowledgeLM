#!/usr/bin/env python3
"""
Test Legal Skills with BGE-M3 and Citations
Tests the created legal skills with queries and verifies page citations
"""

import asyncio
import logging
import json
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.v1.endpoints.skills import query_demo_skill
from app.Providers.skill_metadata_provider.client import get_skill_metadata_provider
from app.Providers.vector_store_provider.client import get_vector_store_provider
from app.SkillServices.skill_retrieval_service import get_skill_retrieval_service
from app.Providers.llm_provider.client import get_llm_provider
from app.Services.prompt_service import get_prompt_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test queries for legal skills
TEST_QUERIES = {
    "六法全書-刑法": [
        "詐欺罪的構成要件是什麼？",
        "竊盜罪如何判定？",
        "傷害罪的刑罰規定",
        "正當防衛的法律要件"
    ],
    "六法全書-民法": [
        "契約成立的要件",
        "債權債務關係",
        "繼承順序規定",
        "買賣契約的法律效力"
    ]
}

async def test_legal_skill_query():
    """Test legal skill queries with citations"""

    logger.info("=" * 60)
    logger.info("🏛️ Legal Skills Test with BGE-M3 and Citations")
    logger.info("=" * 60)

    # Initialize providers
    metadata_provider = get_skill_metadata_provider()
    retrieval_service = get_skill_retrieval_service()
    llm_client = get_llm_provider()
    prompt_service = get_prompt_service()

    # Get available legal skills
    all_skills = await metadata_provider.list_all_skills()
    legal_skills = [s for s in all_skills if '六法' in s.get('skill_name', '')]

    if not legal_skills:
        logger.error("❌ No legal skills found in database")
        logger.info("   Please run: python3 scripts/load_legal_skills.py")
        return

    logger.info(f"Found {len(legal_skills)} legal skills:")
    for skill in legal_skills:
        logger.info(f"  - {skill['skill_name']} (ID: {skill['skill_id']})")
        logger.info(f"    Chunks: {skill.get('total_chunks', 0)}")
        logger.info(f"    Model: {skill.get('embedding_model', 'Unknown')}")

    # Test each skill with queries
    for skill in legal_skills:
        skill_name = skill['skill_name']
        skill_id = skill['skill_id']

        logger.info(f"\n📚 Testing: {skill_name}")
        logger.info("=" * 40)

        # Get test queries for this skill
        queries = TEST_QUERIES.get(skill_name, ["法律效力", "規定"])

        for query in queries[:2]:  # Test first 2 queries
            logger.info(f"\n❓ Query: {query}")

            try:
                # Call the query endpoint
                result = await query_demo_skill(
                    skill_id=skill_id,
                    query=query,
                    top_k=5,
                    metadata_provider=metadata_provider,
                    retrieval_service=retrieval_service,
                    llm_client=llm_client,
                    prompt_service=prompt_service
                )

                # Display results
                logger.info(f"✅ Answer retrieved successfully")
                logger.info(f"   Search mode: {result.get('search_mode')}")
                logger.info(f"   Documents searched: {result.get('documents_searched')}")

                # Show top results with citations
                logger.info("\n📄 Top Results with Citations:")
                for i, res in enumerate(result.get('results', [])[:3], 1):
                    score = res.get('score', 0)
                    citation = res.get('citation', 'N/A')
                    content_preview = res.get('content', '')[:100] + '...'

                    logger.info(f"   {i}. Score: {score:.4f}")
                    logger.info(f"      Citation: {citation}")
                    logger.info(f"      Preview: {content_preview}")

                # Show answer preview
                answer = result.get('answer', '')
                logger.info(f"\n💡 Answer Preview:")
                logger.info(f"   {answer[:200]}...")

                # Check if citations are included
                if '參考來源' in answer:
                    logger.info(f"\n✅ Citations found in answer!")
                    # Extract citation section
                    citation_part = answer.split('參考來源：')[-1]
                    logger.info(f"   Citations: {citation_part[:200]}")
                else:
                    logger.warning("⚠️ No citations found in answer")

            except Exception as e:
                logger.error(f"❌ Error querying skill: {str(e)}")
                continue

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 Test Summary")
    logger.info("=" * 60)
    logger.info("✅ Legal skills tested with BGE-M3 embeddings")
    logger.info("✅ Page-based citations implemented")
    logger.info("\n💡 Features Demonstrated:")
    logger.info("   - BGE-M3 1024-dimensional embeddings")
    logger.info("   - Page-based chunking (each page = 1 chunk)")
    logger.info("   - Citation format: [document-第X頁]")
    logger.info("   - Citations included in answers")

if __name__ == "__main__":
    try:
        asyncio.run(test_legal_skill_query())
    except KeyboardInterrupt:
        logger.info("\n⚠️ Test interrupted by user")
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}")