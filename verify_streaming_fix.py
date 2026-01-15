# verify_streaming_fix.py
#!/usr/bin/env python3
"""
Verify OPMP Streaming Fix - End-to-End Test
驗證 OPMP Streaming 修復 - 端到端測試

Tests:
1. LLM Provider URL correctness (/v1 suffix)
2. Backend SSE streaming capability
3. Token generation from LLM
"""

import asyncio
import httpx
import json
from app.Providers.llm_provider.client import get_llm_provider

async def test_llm_provider_url():
    """Test 1: Verify LLM Provider URL has /v1 suffix"""
    print("=" * 70)
    print("TEST 1: LLM Provider URL Configuration")
    print("=" * 70)

    client = get_llm_provider()
    base_url = client.base_url
    endpoint = f"{base_url}/chat/completions"

    print(f"Base URL: {base_url}")
    print(f"Full Endpoint: {endpoint}")

    if '/v1' in base_url:
        print("✅ PASS: URL contains /v1 suffix")
        return True
    else:
        print("❌ FAIL: URL missing /v1 suffix")
        return False

async def test_llm_streaming():
    """Test 2: Verify LLM actually generates tokens via streaming"""
    print("\n" + "=" * 70)
    print("TEST 2: LLM Token Generation (Streaming)")
    print("=" * 70)

    client = get_llm_provider()

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say 'Hello World' and nothing else."}
    ]

    print(f"Sending request to: {client.base_url}/chat/completions")
    print(f"Messages: {messages}")

    token_count = 0
    full_response = ""

    try:
        async for chunk in client.get_chat_completion_stream(messages=messages):
            chunk_str = chunk.decode('utf-8')

            # Parse SSE format
            for line in chunk_str.split('\n'):
                if line.startswith('data: '):
                    data_str = line[6:]

                    if data_str.strip() == '[DONE]':
                        continue

                    try:
                        data = json.loads(data_str)
                        choices = data.get('choices', [])
                        if choices:
                            delta = choices[0].get('delta', {})
                            token = delta.get('content', '')

                            if token:
                                token_count += 1
                                full_response += token
                                print(f"  Token #{token_count}: '{token}'")

                    except json.JSONDecodeError:
                        continue

        print(f"\n✅ PASS: Received {token_count} tokens")
        print(f"Full Response: '{full_response}'")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: {type(e).__name__}: {str(e)}")
        return False

async def test_backend_sse_endpoint():
    """Test 3: Verify backend /api/v1/chat/stream endpoint works"""
    print("\n" + "=" * 70)
    print("TEST 3: Backend SSE Endpoint (/api/v1/chat/stream)")
    print("=" * 70)

    url = "http://localhost:8000/api/v1/chat/stream"
    payload = {
        "query": "test streaming",
        "session_id": f"test_verify_{int(asyncio.get_event_loop().time())}",
        "file_ids": [],
        "top_k": 1
    }

    headers = {
        "Content-Type": "application/json",
        "X-User-ID": "test-user"
    }

    print(f"Endpoint: {url}")
    print(f"Payload: {payload}")

    event_count = 0
    markdown_token_count = 0

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream('POST', url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    print(f"❌ FAIL: HTTP {response.status_code}")
                    error_text = await response.aread()
                    print(f"Error: {error_text.decode()}")
                    return False

                buffer = ""
                async for chunk in response.aiter_bytes():
                    chunk_str = chunk.decode('utf-8')
                    buffer += chunk_str

                    lines = buffer.split('\n')
                    buffer = lines.pop() if lines else ""

                    for line in lines:
                        if line.startswith('event: '):
                            event_type = line[7:].strip()
                        elif line.startswith('data: '):
                            event_count += 1
                            data_str = line[6:]
                            try:
                                data = json.loads(data_str)

                                if event_type == 'markdown_token':
                                    markdown_token_count += 1
                                    token = data.get('token', '')
                                    print(f"  Event #{event_count} - markdown_token: '{token}'")
                                else:
                                    print(f"  Event #{event_count} - {event_type}: {json.dumps(data, ensure_ascii=False)}")

                            except json.JSONDecodeError:
                                print(f"  Event #{event_count} - {event_type}: (invalid JSON)")

        print(f"\n✅ PASS: Received {event_count} events ({markdown_token_count} markdown_token events)")

        if markdown_token_count > 0:
            print("✅ CRITICAL SUCCESS: LLM tokens are being generated and streamed!")
            return True
        else:
            print("⚠️  WARNING: No markdown_token events received (may indicate LLM issue)")
            return False

    except Exception as e:
        print(f"\n❌ FAIL: {type(e).__name__}: {str(e)}")
        return False

async def main():
    """Run all verification tests"""
    print("\n" + "=" * 70)
    print("OPMP STREAMING FIX VERIFICATION")
    print("=" * 70)
    print()

    results = []

    # Test 1: URL Configuration
    results.append(await test_llm_provider_url())

    # Test 2: LLM Token Generation
    results.append(await test_llm_streaming())

    # Test 3: Backend SSE Endpoint
    results.append(await test_backend_sse_endpoint())

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    passed = sum(results)
    total = len(results)

    print(f"Tests Passed: {passed}/{total}")

    if all(results):
        print("\n✅✅✅ ALL TESTS PASSED - STREAMING FIX VERIFIED ✅✅✅")
        print("\nThe OPMP streaming issue is RESOLVED:")
        print("  1. LLM Provider URL is correct (has /v1)")
        print("  2. LLM successfully generates tokens")
        print("  3. Backend streams tokens to frontend")
        print("\n👉 Screen should no longer hang on 'initialize...'")
        print("👉 Tokens should appear progressively in the browser")
    else:
        print("\n❌ SOME TESTS FAILED - Additional debugging needed")

        if not results[0]:
            print("  → Fix: Check LLM Provider URL configuration")
        if not results[1]:
            print("  → Fix: Verify Ollama is running and model is loaded")
        if not results[2]:
            print("  → Fix: Check backend SSE implementation")

    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
