#!/usr/bin/env python3
"""
Test script to verify Gorgon Point skill retrieval for Thunderbolt 4 content
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.SkillServices.skill_retrieval_service import SkillRetrievalService
from app.Providers.skill_metadata_provider.client import SkillMetadataProvider
from app.Providers.embedding_provider.client import get_embedding_provider
from app.Providers.vector_store_provider.client import get_vector_store_provider

async def test_gorgon_retrieval():
    """Test retrieval from Gorgon Point skill specifically"""

    # Skill ID for Gorgon Point
    skill_id = "skill_20251211_075133_48af4341_5c6743"
    query = "PATHWAY TO THUNDERBOLT 4 CERTIFICATION"

    print(f"\n{'='*80}")
    print(f"Testing Retrieval for Gorgon Point Skill")
    print(f"{'='*80}")
    print(f"Skill ID: {skill_id}")
    print(f"Query: {query}")
    print(f"{'='*80}\n")

    # Initialize services
    metadata_provider = SkillMetadataProvider()
    embedding_provider = get_embedding_provider()
    vector_store_provider = get_vector_store_provider()
    retrieval_service = SkillRetrievalService(
        embedding_provider=embedding_provider,
        vector_store_provider=vector_store_provider
    )

    # Get skill metadata
    skill_metadata = await metadata_provider.get_skill(skill_id)
    print(f"✅ Skill Metadata:")
    print(f"   - Name: {skill_metadata.get('skill_name')}")
    print(f"   - Source: {skill_metadata.get('source_name')}")
    print(f"   - Total Chunks: {skill_metadata.get('total_chunks')}")
    print(f"   - Created: {skill_metadata.get('created_at')}\n")

    # Perform retrieval
    print(f"🔍 Performing Vector Retrieval...")
    results = await retrieval_service.retrieve_context(
        query=query,
        content_ids=[skill_id],
        top_k=30,  # Increased to find Thunderbolt 4 chunks
        include_scores=True
    )

    print(f"\n📊 Retrieval Results: {len(results)} chunks found\n")

    # Display top results
    print(f"Showing all results with 'THUNDERBOLT' keyword first:\n")

    # First show Thunderbolt results
    thunderbolt_results = [r for r in results if 'THUNDERBOLT' in r.get('content', '').upper()]
    for i, result in enumerate(thunderbolt_results, 1):
        print(f"{'─'*80}")
        print(f"Result #{i}")
        print(f"{'─'*80}")
        print(f"Score: {result.get('score', 'N/A'):.4f}")
        print(f"Chunk Index: {result.get('chunk_index', 'N/A')}")
        print(f"Page: {result.get('page_number', 'N/A')}")
        print(f"Document: {result.get('document_name', 'N/A')}")
        print(f"\nContent Preview:")
        content = result.get('content', '')
        print(f"{content[:300]}...")

        print(f"\n✅ Contains 'THUNDERBOLT' keyword!")
        print()

    # Then show top 5 non-Thunderbolt results
    if thunderbolt_results:
        print(f"\n{'='*80}")
        print(f"Top 5 Non-Thunderbolt Results for comparison:")
        print(f"{'='*80}\n")

    non_thunderbolt = [r for r in results if 'THUNDERBOLT' not in r.get('content', '').upper()]
    for i, result in enumerate(non_thunderbolt[:5], 1):
        print(f"Score: {result.get('score', 'N/A'):.4f} | Preview: {result.get('content', '')[:100]}...")
        print()

    # Statistics
    print(f"\n{'='*80}")
    print(f"📈 Statistics")
    print(f"{'='*80}")

    thunderbolt_count = sum(1 for r in results if 'THUNDERBOLT' in r.get('content', '').upper())
    print(f"Chunks containing 'THUNDERBOLT': {thunderbolt_count}/{len(results)}")

    if thunderbolt_count > 0:
        print(f"\n✅ SUCCESS: Found Thunderbolt 4 content in retrieval results!")
    else:
        print(f"\n❌ ISSUE: No Thunderbolt 4 content found despite being in chunks!")
        print(f"\nPossible causes:")
        print(f"  1. Embedding quality - vectors not capturing semantic meaning")
        print(f"  2. Query mismatch - 'CERTIFICATION' vs 'CERTIFI' in chunks")
        print(f"  3. Low similarity scores being filtered out")

    print(f"{'='*80}\n")

if __name__ == "__main__":
    asyncio.run(test_gorgon_retrieval())
