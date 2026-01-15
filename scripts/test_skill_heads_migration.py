#!/usr/bin/env python3
"""
Test script for skill_heads migration.
Run this to verify the new architecture works correctly.
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.Providers.skill_metadata_provider.client import get_skill_metadata_provider


async def main():
    print("=" * 60)
    print("Testing skill_heads Migration")
    print("=" * 60)

    provider = get_skill_metadata_provider()

    # Step 1: Initialize database (creates tables if not exist)
    print("\n[1] Initializing database...")
    await provider.initialize_database()
    print("✅ Database initialized")

    # Step 2: Check if skill_heads table exists
    print("\n[2] Checking skill_heads table...")
    conn = await provider._get_connection()
    async with conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='skill_heads'
    """) as cursor:
        result = await cursor.fetchone()

    if result:
        print("✅ skill_heads table exists")
    else:
        print("❌ skill_heads table NOT found")
        return

    # Step 3: Check schema
    print("\n[3] skill_heads schema:")
    async with conn.execute("PRAGMA table_info(skill_heads)") as cursor:
        columns = await cursor.fetchall()
    for col in columns:
        print(f"   - {col['name']}: {col['type']}")

    # Step 4: Check if head_id column exists in skill_metadata
    print("\n[4] Checking head_id column in skill_metadata...")
    async with conn.execute("PRAGMA table_info(skill_metadata)") as cursor:
        columns = await cursor.fetchall()

    has_head_id = any(col['name'] == 'head_id' for col in columns)
    if has_head_id:
        print("✅ head_id column exists in skill_metadata")
    else:
        print("❌ head_id column NOT found")

    # Step 5: Run migration
    print("\n[5] Running migration...")
    result = await provider.migrate_existing_data()
    print(f"   Migrated heads: {result['migrated_heads']}")
    print(f"   Updated documents: {result['updated_documents']}")
    print(f"   Status: {result['status']}")

    # Step 6: List skill heads
    print("\n[6] Listing skill heads...")
    heads = await provider.list_skill_heads(enabled_only=False)
    for head in heads:
        print(f"   📁 {head['skill_name']} (ID: {head['head_id']})")

    # Step 7: Get skill tree
    print("\n[7] Getting skill tree structure...")
    tree = await provider.get_skill_tree()
    for skill in tree:
        print(f"   📁 {skill['skill_name']} ({skill['document_count']} docs, {skill['total_chunks']} chunks)")
        for doc in skill.get('documents', []):
            print(f"      └── 📄 {doc.get('source_name') or 'Main'} ({doc.get('total_chunks', 0)} chunks)")

    print("\n" + "=" * 60)
    print("Migration test complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
