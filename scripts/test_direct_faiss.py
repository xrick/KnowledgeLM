#!/usr/bin/env python3
"""
Direct FAISS test to understand why Thunderbolt 4 chunks are not retrieved
"""
import asyncio
import sys
import os
import faiss
import pickle

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.Providers.bge_embedding_provider import BGEEmbeddingProvider

async def test_direct_faiss():
    """Test FAISS retrieval directly"""
    skill_id = "skill_20251211_075133_48af4341_5c6743"
    query = "PATHWAY TO THUNDERBOLT 4 CERTIFICATION"

    print(f"\n{'='*80}")
    print(f"Direct FAISS Test")
    print(f"{'='*80}\n")

    # Load FAISS index
    index_path = f"data/faiss_indices/skills/{skill_id}/index.faiss"
    metadata_path = f"data/faiss_indices/skills/{skill_id}/index.pkl"

    print(f"Loading FAISS index from: {index_path}")
    index = faiss.read_index(index_path)
    print(f"✅ Index loaded: {index.ntotal} vectors\n")

    print(f"Loading metadata from: {metadata_path}")
    with open(metadata_path, 'rb') as f:
        metadata = pickle.load(f)
    print(f"✅ Metadata loaded: {len(metadata)} entries\n")

    # Generate query embedding
    print(f"Generating query embedding...")
    embedding_provider = BGEEmbeddingProvider()
    query_embedding = await embedding_provider.generate_embeddings([query])
    query_vector = query_embedding[0]
    print(f"✅ Query embedding generated: shape {len(query_vector)}\n")

    # Search FAISS
    k = 30
    print(f"Searching for top-{k} results...")
    distances, indices = index.search(query_vector.reshape(1, -1), k)

    print(f"\n📊 Search Results:\n")

    # Check if Thunderbolt chunks are in results
    thunderbolt_indices = [53, 54]  # We know these contain Thunderbolt 4

    for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
        meta = metadata[idx] if idx < len(metadata) else {}
        chunk_text = meta.get('chunk_text', '')

        is_thunderbolt = 'THUNDERBOLT' in chunk_text.upper()
        is_target = idx in thunderbolt_indices

        marker = "🎯" if is_target else ("✅" if is_thunderbolt else "  ")

        print(f"{marker} Rank {i+1}: idx={idx}, dist={dist:.4f}")

        if is_thunderbolt or i < 10:
            preview = chunk_text[:150] if chunk_text else "No text"
            print(f"     Preview: {preview}...")

        if is_thunderbolt:
            print(f"     ✅ Contains THUNDERBOLT!")

        print()

    # Summary
    print(f"{'='*80}")
    print(f"Summary")
    print(f"{'='*80}")

    found_53 = 53 in indices[0]
    found_54 = 54 in indices[0]

    print(f"Chunk 53 (Thunderbolt Page 54) in top-{k}: {'✅ YES' if found_53 else '❌ NO'}")
    print(f"Chunk 54 (Thunderbolt Page 55) in top-{k}: {'✅ YES' if found_54 else '❌ NO'}")

    if found_53:
        rank_53 = list(indices[0]).index(53) + 1
        dist_53 = distances[0][list(indices[0]).index(53)]
        print(f"  → Chunk 53 rank: {rank_53}, distance: {dist_53:.4f}")

    if found_54:
        rank_54 = list(indices[0]).index(54) + 1
        dist_54 = distances[0][list(indices[0]).index(54)]
        print(f"  → Chunk 54 rank: {rank_54}, distance: {dist_54:.4f}")

    print(f"\n{'='*80}\n")

if __name__ == "__main__":
    asyncio.run(test_direct_faiss())
