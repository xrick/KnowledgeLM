# PDF Upload Progress Window - Producer-Consumer Pattern Analysis

**Date**: 2025-12-06
**Issue**: Progress window shows start message, then freezes until PDF processing completes
**Root Cause**: Synchronous (blocking) processing prevents SSE events from streaming

---

## 🎯 Problem Analysis

### Current Behavior (Blocking)

```
User uploads PDF
    ↓
Progress modal opens → "開始處理..."
    ↓
⏸️ BLOCKS HERE (UI freezes)
    ↓
Backend processes entire PDF synchronously:
- Extract text from all pages
- Generate embeddings for all chunks
- Save to FAISS
- Save to SQLite
    ↓
⏸️ STILL BLOCKED (no progress updates)
    ↓
Processing completes → "完成！"
    ↓
Progress modal shows final results
```

**User Experience**:
- ❌ Progress bar stays at 5% ("開始處理...")
- ❌ No intermediate updates for minutes
- ❌ Cannot tell if system is working or frozen
- ❌ Bad UX for large PDFs (1000+ pages)

---

## 🔍 Root Cause: Synchronous Processing

### Current Implementation (`skills.py` Line 1150+)

```python
async def process_pdf_for_skill_streaming(...):
    """
    Process PDF with SSE streaming (but actually BLOCKING!)
    """
    # ❌ BLOCKING: All processing happens synchronously

    # 1. Extract text (BLOCKS for entire PDF)
    pdf_reader = PyPDF2.PdfReader(pdf_path)
    for page_num, page in enumerate(pdf_reader.pages):
        text = page.extract_text()
        all_text += text

    # 2. Generate embeddings (BLOCKS for all chunks)
    embeddings = embedding_provider.embed_batch(chunks)  # GPU blocks here

    # 3. Save to FAISS (BLOCKS)
    vector_provider.save_vectors(...)

    # 4. Only after EVERYTHING completes, yield events
    yield sse_event("complete", {...})
```

**Why It Blocks**:
- Python's `async/await` doesn't help with CPU-bound operations
- GPU inference (`encode()`) is blocking
- File I/O (PDF reading) is blocking
- No true parallelism between reading & processing

---

## 📚 Reference: Producer-Consumer Pattern

### Theory (from `how_to_show_task_progress_correctly.md`)

```
❌ Synchronous (Current):
UI Thread: [Read PDF 100%] → [Embed 100%] → [Save 100%] → Done
Progress:  [0%           ] → [0%         ] → [100%     ]
           ↑ FROZEN HERE ↑

✅ Producer-Consumer (Goal):
Producer Thread:  [Read Page 1] → [Read Page 2] → [Read Page 3] → ...
                       ↓              ↓              ↓
                    [Queue]       [Queue]       [Queue]
                       ↓              ↓              ↓
Consumer Thread:  [Embed Batch 1] → [Embed Batch 2] → [Embed Batch 3]
                       ↓              ↓              ↓
Progress Updates:  [20%]          [40%]          [60%]        [100%]
```

**Key Benefits**:
1. **Decoupling**: Reading doesn't wait for embedding
2. **Real Progress**: UI updates after each batch
3. **Backpressure**: Queue prevents RAM explosion
4. **Responsiveness**: GPU works while CPU prepares next batch

---

## 🛠️ Solution Design: Apply Producer-Consumer to FastAPI SSE

### Architecture Overview

```
Frontend (skill_config.html)
    ↓ (HTTP POST with file)
Backend API (/upload-source-stream)
    ↓ (Save file to disk)
    ↓
generate_sse_events() ← SSE Generator
    ↓
    ├─→ Producer Thread: _pdf_reader_loop()
    │   - Reads PDF pages
    │   - Chunks text
    │   - Puts batches into Queue
    │   - Yields SSE: "checkpoint" events
    │
    └─→ Consumer (Main Thread): _embedding_loop()
        - Gets batches from Queue
        - Calls model.encode() (GPU)
        - Saves to FAISS/SQLite
        - Yields SSE: "progress" events
```

### Implementation Plan

#### Step 1: Add Threading Infrastructure

**File**: `app/api/v1/endpoints/skills.py`

```python
import asyncio
import threading
import queue
from typing import AsyncGenerator

# Global queue for producer-consumer
batch_queue = queue.Queue(maxsize=10)  # Buffer 10 batches max
```

#### Step 2: Refactor into Producer Function

```python
def _producer_loop(pdf_path: Path, batch_size: int = 12):
    """
    Producer Thread: Reads PDF and queues text batches.
    Runs in separate thread to not block main event loop.
    """
    import PyPDF2

    try:
        pdf_reader = PyPDF2.PdfReader(pdf_path)
        total_pages = len(pdf_reader.pages)

        text_buffer = []
        page_buffer = []

        for page_num, page in enumerate(pdf_reader.pages):
            text = page.extract_text()

            # Split into chunks
            chunks = split_text(text, chunk_size=1000)

            for chunk in chunks:
                text_buffer.append(chunk)
                page_buffer.append(page_num + 1)

                # When buffer full, put to queue
                if len(text_buffer) >= batch_size:
                    batch_queue.put({
                        'texts': list(text_buffer),
                        'pages': list(page_buffer),
                        'batch_num': page_num // batch_size
                    })
                    text_buffer.clear()
                    page_buffer.clear()

        # Flush remaining
        if text_buffer:
            batch_queue.put({
                'texts': list(text_buffer),
                'pages': list(page_buffer),
                'batch_num': total_pages // batch_size
            })

        # Sentinel value (end of stream)
        batch_queue.put(None)

    except Exception as e:
        batch_queue.put({'error': str(e)})
```

#### Step 3: Consumer as Async Generator

```python
async def process_pdf_for_skill_streaming(...) -> AsyncGenerator:
    """
    Main Consumer: Embeds batches and yields SSE events.
    """
    # 1. Start Producer Thread
    producer_thread = threading.Thread(
        target=_producer_loop,
        args=(pdf_path,),
        daemon=True
    )
    producer_thread.start()

    # Yield start event
    yield create_upload_sse_event("start", {...})

    # 2. Consumer Loop (Main Thread)
    batch_num = 0
    total_chunks = 0

    while True:
        # Non-blocking get with timeout
        try:
            batch = await asyncio.to_thread(batch_queue.get, timeout=1.0)
        except queue.Empty:
            # Yield heartbeat to keep connection alive
            yield create_upload_sse_event("heartbeat", {
                "timestamp": datetime.now().isoformat()
            })
            continue

        # Check for end of stream
        if batch is None:
            break

        # Check for errors
        if 'error' in batch:
            yield create_upload_sse_event("error", {
                "message": batch['error']
            })
            break

        # Process batch (GPU embedding)
        batch_texts = batch['texts']
        batch_pages = batch['pages']

        # ✅ This yields progress WHILE processing
        yield create_upload_sse_event("batch_start", {
            "batch_num": batch_num,
            "batch_size": len(batch_texts),
            "pages": f"{batch_pages[0]}-{batch_pages[-1]}"
        })

        # GPU embedding (still blocks, but only for THIS batch)
        embeddings = embedding_provider.embed_batch(batch_texts)

        # Save to FAISS/SQLite
        vector_provider.save_vectors(...)
        metadata_provider.save_chunks(...)

        total_chunks += len(batch_texts)
        batch_num += 1

        # ✅ Yield progress after EACH batch
        yield create_upload_sse_event("checkpoint", {
            "batch_num": batch_num,
            "total_chunks": total_chunks,
            "percent": calculate_progress(batch_num, total_batches),
            "pages_processed": batch_pages[-1]
        })

    # Final event
    yield create_upload_sse_event("complete", {
        "total_chunks": total_chunks,
        ...
    })
```

---

## 📊 Expected Improvements

### Before (Synchronous)

```
Time  | Action                    | Progress UI
------|---------------------------|-------------
0s    | Start processing          | 5% "開始處理..."
0-60s | Read + Embed + Save ALL   | 5% (FROZEN)
60s   | Complete                  | 100% "完成！"
```

**UX Issues**:
- User sees no updates for 60 seconds
- Cannot tell if processing or crashed
- Cancellation doesn't work

### After (Producer-Consumer)

```
Time  | Action                    | Progress UI
------|---------------------------|-------------
0s    | Start processing          | 5% "開始處理..."
2s    | Producer reads pages 1-10 | 10% "批次 1/10"
4s    | Consumer embeds batch 1   | 15% "已處理 10 頁"
6s    | Producer reads pages 11-20| 20% "批次 2/10"
8s    | Consumer embeds batch 2   | 25% "已處理 20 頁"
...   | ...                       | ...
60s   | Complete                  | 100% "完成！"
```

**UX Improvements**:
- ✅ Progress updates every 2-4 seconds
- ✅ User knows system is working
- ✅ Can estimate completion time
- ✅ Cancellation works properly

---

## 🚧 Implementation Challenges

### Challenge 1: asyncio + Threading

**Problem**: FastAPI uses `asyncio`, but threading blocks event loop

**Solution**: Use `asyncio.to_thread()` for blocking operations

```python
# ❌ This blocks event loop
batch = batch_queue.get()

# ✅ This doesn't block
batch = await asyncio.to_thread(batch_queue.get, timeout=1.0)
```

### Challenge 2: Queue Size (Backpressure)

**Problem**: Producer reads faster than consumer → RAM explosion

**Solution**: Bounded queue with backpressure

```python
batch_queue = queue.Queue(maxsize=10)  # Max 10 batches in RAM

# Producer will BLOCK when queue is full
batch_queue.put(batch)  # Blocks if queue.full()
```

**Trade-off**:
- Small queue (5): Less RAM, more blocking
- Large queue (20): More RAM, less blocking
- **Recommendation**: 10 batches (~120 chunks ~ 120KB)

### Challenge 3: Error Handling

**Problem**: Exception in producer thread doesn't propagate to consumer

**Solution**: Put error dict in queue

```python
try:
    # Producer logic
    ...
except Exception as e:
    batch_queue.put({'error': str(e), 'traceback': traceback.format_exc()})
```

### Challenge 4: Graceful Shutdown

**Problem**: User cancels upload mid-processing

**Solution**: Sentinel value + thread cleanup

```python
# Producer sends sentinel when done
batch_queue.put(None)

# Consumer checks for sentinel
if batch is None:
    break

# Frontend closes EventSource
eventSource.close()
```

---

## 📁 Files to Modify

| File | Lines | Changes |
|------|-------|---------|
| `app/api/v1/endpoints/skills.py` | 1150-1500 | Add `_producer_loop()`, refactor `process_pdf_for_skill_streaming()` |
| `template/skill_config.html` | 1913-2050 | Update SSE event handlers (already good!) |

---

## 🧪 Testing Plan

### Test 1: Small PDF (10 pages)

**Expected**:
- Progress updates every 1-2 seconds
- "批次 1/2" → "批次 2/2" → "完成"

### Test 2: Medium PDF (100 pages)

**Expected**:
- Progress updates every 3-5 seconds
- Linear progress from 5% → 100%
- No freezing

### Test 3: Large PDF (1000 pages)

**Expected**:
- Progress updates every 5-10 seconds
- Steady throughput (not stuck)
- Memory usage stays bounded

### Test 4: Cancellation

**Expected**:
- User clicks "取消"
- Producer stops reading
- Consumer finishes current batch
- Modal closes cleanly

---

## 🎓 Key Learnings from Reference Code

### From `producer_consumer_ui.py`:

1. **Daemon Thread**: `daemon=True` ensures thread dies with main process
2. **Sentinel Pattern**: `queue.put(None)` signals end of stream
3. **Progress Bar**: Track consumer progress (embedding), not producer (reading)
4. **Backpressure**: Queue blocks producer when full

### From `how_to_show_task_progress_correctly.md`:

1. **Why Not asyncio?**: GPU operations (`model.encode()`) block event loop
2. **Threading vs Multiprocessing**: Threading sufficient (GIL released during I/O and GPU calls)
3. **Dual Progress Bars**: Optional - show both reading & embedding progress

---

## ✅ Success Criteria

- [ ] Progress updates appear every 2-5 seconds (not just start & end)
- [ ] Progress bar advances smoothly (not stuck at 5%)
- [ ] Log messages show batch processing
- [ ] Memory usage stays bounded (no RAM explosion)
- [ ] Cancellation works properly (thread cleanup)
- [ ] Error handling propagates from producer to consumer

---

## 🚀 Next Steps

1. **Implement `_producer_loop()`** - Separate thread for PDF reading
2. **Refactor `process_pdf_for_skill_streaming()`** - Consumer with queue
3. **Test with PDFs** - Small, medium, large
4. **Monitor RAM usage** - Ensure queue size is appropriate
5. **User testing** - Validate UX improvements

---

*SuperClaude Framework - Evidence-Based Architecture*
*Generated: 2025-12-06*
