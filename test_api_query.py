#!/usr/bin/env python3
import requests
import json

# Test API endpoint
url = "http://localhost:8082/api/v1/skills/demo/query"

payload = {
    "skill_id": "skill_20251211_161308_48af4341_feb60e",
    "query": "strix halo",
    "top_k": 10
}

headers = {
    "Content-Type": "application/json"
}

print("📤 Sending request...")
print(f"URL: {url}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print()

try:
    response = requests.post(url, json=payload, headers=headers)

    print(f"📥 Response Status: {response.status_code}")
    print()

    if response.status_code == 200:
        data = response.json()
        print("✅ Success!")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("❌ Error!")
        print(response.text)

except Exception as e:
    print(f"❌ Exception: {e}")
    import traceback
    traceback.print_exc()
