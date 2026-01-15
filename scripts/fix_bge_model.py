#!/usr/bin/env python3
"""
BGE-M3 Model Fix Script

Diagnoses and fixes BGE-M3 model loading issues.
Run this if you get "Can't load the configuration of 'BAAI/bge-m3'" errors.

Usage:
    python scripts/fix_bge_model.py
"""

import os
import shutil
from pathlib import Path

def main():
    print("=" * 60)
    print("BGE-M3 Model Diagnostic and Fix Script")
    print("=" * 60)
    print()

    # 1. Check HuggingFace cache location
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    print(f"📁 HuggingFace cache location: {hf_cache}")

    if hf_cache.exists():
        print(f"   ✅ Cache directory exists")

        # Check for BGE-M3 model
        bge_dirs = list(hf_cache.glob("models--BAAI--bge-m3*"))
        if bge_dirs:
            print(f"   Found {len(bge_dirs)} BGE-M3 cache directories:")
            for d in bge_dirs:
                print(f"      - {d.name}")
        else:
            print(f"   ⚠️ No BGE-M3 model cache found")
    else:
        print(f"   ⚠️ Cache directory does not exist")

    print()

    # 2. Offer to clean cache
    print("Options:")
    print("  1. Clear BGE-M3 cache and force re-download (recommended)")
    print("  2. Keep cache and try re-loading")
    print("  3. Exit without changes")
    print()

    try:
        choice = input("Select option (1/2/3): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return

    if choice == "1":
        # Clear BGE-M3 cache
        print("\n🗑️  Clearing BGE-M3 cache...")
        bge_dirs = list(hf_cache.glob("models--BAAI--bge-m3*"))
        for d in bge_dirs:
            try:
                shutil.rmtree(d)
                print(f"   ✅ Removed: {d.name}")
            except Exception as e:
                print(f"   ❌ Failed to remove {d.name}: {e}")

        # Try downloading fresh model
        print("\n📥 Downloading BGE-M3 model (this may take a few minutes)...")
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("BAAI/bge-m3")
            print(f"   ✅ Model loaded successfully!")
            print(f"   Model dimension: {model.get_sentence_embedding_dimension()}")
            print(f"   Max sequence length: {model.max_seq_length}")
        except Exception as e:
            print(f"   ❌ Failed to load model: {e}")
            print(f"\n💡 Try manually downloading:")
            print(f"      python -c 'from sentence_transformers import SentenceTransformer; SentenceTransformer(\"BAAI/bge-m3\")'")
            return

    elif choice == "2":
        # Try loading without clearing cache
        print("\n🔄 Attempting to load BGE-M3 model...")
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("BAAI/bge-m3")
            print(f"   ✅ Model loaded successfully!")
            print(f"   Model dimension: {model.get_sentence_embedding_dimension()}")
        except Exception as e:
            print(f"   ❌ Failed to load model: {e}")
            print(f"\n💡 Recommendation: Run this script again and choose option 1 to clear cache")
            return

    else:
        print("\n👋 Exiting without changes.")
        return

    print("\n" + "=" * 60)
    print("✅ BGE-M3 Model is now ready!")
    print("=" * 60)
    print("\n🚀 You can now restart your DocAI server:")
    print("   ./start_system.sh")
    print()

if __name__ == "__main__":
    main()
