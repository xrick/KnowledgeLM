#!/usr/bin/env python
"""Test OPMP fixed progressive streaming"""
import requests
import json

# Test with "大語言模型大全" skill (query in Chinese)
url = "http://localhost:8082/api/v1/skills/tree"
print("🔍 Getting skill tree...")
response = requests.get(url)
skills = response.json()

# Find the LLM skill
llm_skill = None
for skill in skills.get('skill_tree', []):
    if '大語言模型' in skill['skill_name']:
        llm_skill = skill
        break

if not llm_skill:
    print("❌ Could not find '大語言模型大全' skill")
    exit(1)

head_id = llm_skill['head_id']
document_ids = [doc['skill_id'] for doc in llm_skill['documents'][:3]]  # First 3 docs

print(f"✅ Found skill: {llm_skill['skill_name']}")
print(f"📚 Documents: {len(document_ids)}")
print(f"🆔 Head ID: {head_id}")
print()

# Test progressive streaming
stream_url = f"http://localhost:8082/api/v1/skills/{head_id}/chat/stream"
payload = {
    "query": "什麼是大語言模型？",  # "What is a large language model?"
    "document_ids": document_ids
}

print(f"🧪 Testing: {stream_url}")
print(f"📝 Query: {payload['query']}")
print("="*80)

try:
    response = requests.post(stream_url, json=payload, stream=True, timeout=60)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        print("\n✅ STREAMING SUCCESS! Watching for data...")
        print("-"*80)

        chunks_retrieved = None
        response_content = ""
        phase_updates = []

        for line in response.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith('data: '):
                    data_str = decoded[6:].strip()
                    if data_str and data_str != 'data:':
                        try:
                            data = json.loads(data_str)

                            # Track phase progress
                            if data.get('type') == 'progress':
                                phase = data.get('phase')
                                message = data.get('message')
                                progress = data.get('progress', 0)
                                phase_updates.append(f"Phase {phase} ({progress}%): {message}")

                            # Track chunks retrieved
                            elif data.get('type') == 'phase_result' and data.get('phase') == 2:
                                chunks_retrieved = data['data'].get('total_chunks_found', 0)
                                print(f"\n📊 Phase 2 Result: {chunks_retrieved} chunks retrieved")

                            # Track markdown tokens
                            elif data.get('type') == 'markdown_token':
                                token = data.get('token', '')
                                response_content += token
                                print(token, end='', flush=True)

                            # Track completion
                            elif data.get('type') == 'complete':
                                complete_data = data.get('data', {})
                                metadata = complete_data.get('metadata', {})
                                quality = complete_data.get('quality', {})

                                print(f"\n\n{'='*80}")
                                print("📋 COMPLETION REPORT")
                                print(f"{'='*80}")
                                print(f"✅ Response Length: {len(response_content)} chars")
                                print(f"📊 Chunks Analyzed: {metadata.get('chunks_analyzed', 0)}")
                                print(f"🔤 Context Tokens: {metadata.get('context_tokens', 0)}")
                                print(f"📚 Sources: {len(complete_data.get('sources', []))}")
                                print(f"⭐ Quality Score: {quality.get('score', 0)}/100")
                                print(f"{'='*80}")

                                if response_content:
                                    print("✅ SUCCESS: Response generated with content!")
                                else:
                                    print("❌ FAILURE: Empty response!")

                        except json.JSONDecodeError:
                            pass

        print(f"\n\n📊 Phase Updates:")
        for update in phase_updates:
            print(f"  {update}")

    else:
        print(f"❌ FAILED: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
