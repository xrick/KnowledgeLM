#!/usr/bin/env python3
"""
Test OPMP Progressive Streaming After Fix

This script tests the critical bug fix for empty chunk content in Phase 2 retrieval.

Bug Fixed:
- Added missing `get_chunk_metadata()` method to SkillMetadataProvider
- Maps database `chunk_text` field to expected `content` field

Usage:
    python scripts/test_opmp_fixed.py
"""

import asyncio
import aiohttp
import json
from datetime import datetime


async def test_progressive_streaming():
    """Test the progressive streaming endpoint"""

    print("=" * 70)
    print("OPMP Progressive Streaming Test - After Fix")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}\n")

    # Test configuration
    base_url = "http://localhost:8082"
    skill_id = "skill_20251203_071733_2a43e5ac_src_00"
    endpoint = f"{base_url}/api/v1/skills/{skill_id}/chat/stream"

    query_data = {
        "query": "什麼是LLM?",
        "document_ids": [skill_id]
    }

    print(f"📡 Endpoint: {endpoint}")
    print(f"📝 Query: {query_data['query']}")
    print(f"📂 Document IDs: {query_data['document_ids']}\n")

    # Track results
    phase_results = {}
    tokens_received = []
    errors = []

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint,
                json=query_data,
                headers={"Content-Type": "application/json"}
            ) as response:

                if response.status != 200:
                    print(f"❌ HTTP Error: {response.status}")
                    error_text = await response.text()
                    print(f"Error details: {error_text}")
                    return False

                print("✅ Connection established\n")
                print("📊 Processing SSE stream...")
                print("-" * 70)

                # Read SSE stream
                buffer = ""
                async for chunk in response.content.iter_any():
                    if not chunk:
                        continue

                    buffer += chunk.decode('utf-8')

                    # Process complete lines
                    while '\n\n' in buffer:
                        message, buffer = buffer.split('\n\n', 1)

                        # Parse SSE message
                        if not message.startswith('data: '):
                            continue

                        data_str = message[6:]  # Remove "data: " prefix

                        try:
                            data = json.loads(data_str)
                            event_type = data.get('type')
                            phase = data.get('phase', 0)

                            if event_type == 'progress':
                                msg = data.get('message', '')
                                progress = data.get('progress', 0)
                                print(f"  Phase {phase}: [{progress:3d}%] {msg}")

                            elif event_type == 'phase_result':
                                phase_data = data.get('data', {})
                                phase_results[phase] = phase_data

                                if phase == 2:
                                    # Critical check: Verify chunks have content
                                    chunks = phase_data.get('chunks', [])
                                    print(f"\n🔍 Phase 2 Results:")
                                    print(f"   Total chunks found: {len(chunks)}")

                                    if chunks:
                                        first_chunk = chunks[0]
                                        content = first_chunk.get('content', '')
                                        source = first_chunk.get('source_file', '')

                                        print(f"   First chunk ID: {first_chunk.get('chunk_id')}")
                                        print(f"   Content length: {len(content)} chars")
                                        print(f"   Source file: {source or '(empty)'}")
                                        print(f"   Score: {first_chunk.get('score', 0):.4f}")

                                        # Show content preview
                                        if content:
                                            preview = content[:100] + "..." if len(content) > 100 else content
                                            print(f"   Content preview: {repr(preview)}")
                                            print(f"   ✅ CHUNKS HAVE CONTENT!")
                                        else:
                                            print(f"   ❌ CHUNKS ARE EMPTY! (Bug still exists)")
                                            errors.append("Phase 2 chunks are empty")
                                    else:
                                        print(f"   ⚠️  No chunks retrieved")
                                        errors.append("Phase 2 returned no chunks")

                                    print()

                            elif event_type == 'markdown_token':
                                token = data.get('token', '')
                                tokens_received.append(token)

                            elif event_type == 'complete':
                                complete_data = data.get('data', {})
                                print(f"\n✅ Streaming complete!")
                                print(f"   Total response length: {len(complete_data.get('response', ''))} chars")
                                break

                            elif event_type == 'error':
                                error_msg = data.get('message', '')
                                print(f"❌ Error in phase {phase}: {error_msg}")
                                errors.append(f"Phase {phase}: {error_msg}")

                        except json.JSONDecodeError as e:
                            print(f"⚠️  Failed to parse JSON: {data_str[:50]}...")
                            continue

        print("-" * 70)
        print("\n📋 Test Summary:")
        print(f"   Phases completed: {len(phase_results)}")
        print(f"   Tokens received: {len(tokens_received)}")
        print(f"   Errors: {len(errors)}")

        if errors:
            print("\n❌ Test FAILED")
            for error in errors:
                print(f"   - {error}")
            return False
        else:
            print("\n✅ Test PASSED")

            # Show final response
            if tokens_received:
                response_text = ''.join(tokens_received)
                print(f"\n📄 Generated Response ({len(response_text)} chars):")
                print("─" * 70)
                print(response_text[:500] + ("..." if len(response_text) > 500 else ""))
                print("─" * 70)

            return True

    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def verify_database():
    """Verify that chunk data exists in the database"""
    print("\n🔍 Database Verification")
    print("=" * 70)

    try:
        import aiosqlite
        from pathlib import Path

        db_path = Path("data/skill_metadata.db")

        if not db_path.exists():
            print(f"❌ Database not found: {db_path}")
            return False

        print(f"✅ Database found: {db_path}")

        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row

            # Check chunk count
            async with conn.execute(
                "SELECT COUNT(*) as count FROM skill_chunk_metadata WHERE skill_id = ?",
                ("skill_20251203_071733_2a43e5ac_src_00",)
            ) as cursor:
                row = await cursor.fetchone()
                chunk_count = row[0]

            print(f"✅ Chunk count: {chunk_count}")

            if chunk_count == 0:
                print("⚠️  No chunks found for this skill!")
                return False

            # Check chunk content
            async with conn.execute(
                """
                SELECT chunk_id, LENGTH(chunk_text) as content_len, page, source_file
                FROM skill_chunk_metadata
                WHERE skill_id = ?
                LIMIT 3
                """,
                ("skill_20251203_071733_2a43e5ac_src_00",)
            ) as cursor:
                rows = await cursor.fetchall()

            print(f"\n📄 Sample chunks:")
            for row in rows:
                print(f"   {row['chunk_id']}")
                print(f"      Content length: {row['content_len']} chars")
                print(f"      Page: {row['page']}")
                print(f"      Source: {row['source_file'] or '(empty)'}")

            return True

    except Exception as e:
        print(f"❌ Database check failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("OPMP Bug Fix Verification Test Suite")
    print("=" * 70)

    # Step 1: Verify database
    db_ok = await verify_database()

    if not db_ok:
        print("\n⚠️  Database issues detected. Cannot proceed with streaming test.")
        return

    # Step 2: Test streaming
    print("\n")
    streaming_ok = await test_progressive_streaming()

    # Final verdict
    print("\n" + "=" * 70)
    if streaming_ok:
        print("🎉 ALL TESTS PASSED! Bug fix is working correctly.")
    else:
        print("❌ TESTS FAILED. Bug may still exist or new issues detected.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
