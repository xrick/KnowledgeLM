#!/usr/bin/env python3
"""
Test SSE streaming to diagnose why frontend doesn't receive data
"""
import requests
import time
import json

def test_streaming():
    url = "http://localhost:8000/api/v1/chat/stream"
    headers = {
        "Content-Type": "application/json",
        "X-User-ID": "test-user"
    }
    payload = {
        "query": "請簡單說明這份文件",
        "session_id": f"test_{int(time.time())}",
        "file_ids": ["file_dc59ebf5af9c"],
        "top_k": 3
    }

    print("=" * 80)
    print("Testing SSE Streaming")
    print("=" * 80)
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    print("=" * 80)
    print()

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            stream=True,  # Important for SSE
            timeout=90
        )

        print(f"Response Status: {response.status_code}")
        print(f"Response Headers:")
        for key, value in response.headers.items():
            print(f"  {key}: {value}")
        print()

        if response.status_code != 200:
            print(f"ERROR: Status code {response.status_code}")
            print(response.text)
            return

        print("Starting to receive SSE stream...")
        print("=" * 80)

        event_count = 0
        chunk_count = 0
        markdown_tokens = []

        # Read stream line by line
        for line in response.iter_lines(decode_unicode=True):
            chunk_count += 1

            if not line:  # Empty line marks end of event
                continue

            if line.startswith('event:'):
                event_type = line[6:].strip()
                print(f"\n[Event #{event_count + 1}] Type: {event_type}")

            elif line.startswith('data:'):
                data_str = line[5:].strip()
                try:
                    data = json.loads(data_str)
                    print(f"  Data: {json.dumps(data, ensure_ascii=False)[:200]}...")

                    if event_type == 'markdown_token':
                        token = data.get('token', '')
                        markdown_tokens.append(token)
                        print(f"  → Token: '{token}'")

                    event_count += 1

                except json.JSONDecodeError as e:
                    print(f"  Data (raw): {data_str[:200]}...")

            # Show first 50 events in detail, then summary
            if event_count >= 50 and event_count % 10 == 0:
                print(f"\n... {event_count} events received so far ...")

        print()
        print("=" * 80)
        print(f"Stream completed!")
        print(f"Total events: {event_count}")
        print(f"Total chunks: {chunk_count}")
        print(f"Markdown tokens: {len(markdown_tokens)}")
        if markdown_tokens:
            full_text = ''.join(markdown_tokens)
            print(f"\nReconstructed text ({len(full_text)} chars):")
            print(full_text[:500])
            if len(full_text) > 500:
                print("...")
        print("=" * 80)

    except requests.exceptions.Timeout:
        print("ERROR: Request timed out after 90 seconds")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: {type(e).__name__}: {e}")
    except KeyboardInterrupt:
        print("\nInterrupted by user")

if __name__ == "__main__":
    test_streaming()
