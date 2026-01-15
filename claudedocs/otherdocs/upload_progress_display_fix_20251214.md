# Upload Progress Display Fix - 2025-12-14

## 🐛 Problems

### Issue 1: Unwanted "(xxx chunks)" in Progress Messages
**Visual**: `✓ 檢查點: 第 114 頁 (114 chunks)` ← "(114 chunks)" should be removed

### Issue 2: "undefined 頁" in Some Messages
**Visual**: `✓ 檢查點: 第 undefined 頁 (undefined chunks)` ← Shows "undefined"

## 🔍 Root Cause Analysis

### Backend SSE Event Structure

The backend sends **TWO different checkpoint events** with the same event type:

#### 1. Checkpoint Type 1: `batch_start` (Line 1523)
```python
yield create_upload_sse_event("checkpoint", {
    "phase": "batch_start",
    "message": f"📄 處理批次 {batch_num} (頁面 {batch_pages[0]}-{batch_pages[-1]})",
    "batch_num": batch_num,
    "batch_size": len(batch_texts),
    "pages": f"{batch_pages[0]}-{batch_pages[-1]}",  # ✅ Has 'pages' (range)
    # ❌ NO 'page' field
    # ❌ NO 'total_chunks' field
})
```

#### 2. Checkpoint Type 2: `batch_complete` (Line 1606)
```python
yield create_upload_sse_event("checkpoint", {
    "phase": "batch_complete",
    "message": f"✅ 批次 {batch_num} 完成 (累計 {len(all_chunks)} chunks)",
    "batch_num": batch_num,
    "total_chunks": len(all_chunks),       # ✅ Has 'total_chunks'
    "page": total_pages,                   # ✅ Has 'page' (single number)
    "pages_processed": total_pages,
})
```

### Frontend Issue (Before Fix)

**Old Code** (Line 1959-1965):
```javascript
case 'checkpoint':
    // ❌ Treats both phases the same!
    appendUploadLog(`✓ 檢查點: 第 ${data.page} 頁 (${data.total_chunks} chunks)`, 'success');
    //                              ^^^^^^^^          ^^^^^^^^^^^^^^^^^
    //                              undefined         undefined
    //                              (for batch_start) (for batch_start)
```

**Problem**:
- When `phase: "batch_start"` arrives, `data.page` and `data.total_chunks` are `undefined`
- Frontend displays: `✓ 檢查點: 第 undefined 頁 (undefined chunks)`

## 🔧 Solution Applied

### Modified File: `template/skill_config.html` (Lines 1959-1971)

**After Fix**:
```javascript
case 'checkpoint':
    // ✅ Distinguish between two phases
    if (data.phase === 'batch_start') {
        // Starting a batch - show page range
        appendUploadLog(`🔄 處理批次 ${data.batch_num}: 頁 ${data.pages}`, 'info');
    } else if (data.phase === 'batch_complete') {
        // Batch complete - show page number (without chunks count)
        appendUploadLog(`✓ 檢查點: 第 ${data.page || '?'} 頁`, 'success');
        //                                              ^^^^^^ ✅ Removed chunks count!
        if (progressPercent !== undefined) {
            updateUploadProgress(progressPercent, `已處理 ${data.page || '?'} 頁...`);
        }
    }
    break;
```

## ✅ Expected Behavior (After Fix)

### Upload Progress Log Display

**Before** (WRONG ❌):
```
✓ 檢查點: 第 undefined 頁 (undefined chunks)
✓ 檢查點: 第 114 頁 (114 chunks)
✓ 檢查點: 第 undefined 頁 (undefined chunks)
✓ 檢查點: 第 120 頁 (120 chunks)
```

**After** (CORRECT ✅):
```
🔄 處理批次 1: 頁 1-19
✓ 檢查點: 第 19 頁
🔄 處理批次 2: 頁 20-38
✓ 檢查點: 第 38 頁
🔄 處理批次 3: 頁 39-57
✓ 檢查點: 第 57 頁
```

### Key Improvements

1. ✅ **No more "undefined 頁"** - `batch_start` events now show page range instead of undefined page number
2. ✅ **No more "(xxx chunks)"** - `batch_complete` events only show page number
3. ✅ **Clearer distinction** - Different icons (🔄 vs ✓) for start vs complete
4. ✅ **Better semantics** - "處理批次 X: 頁 1-19" is more informative than "檢查點: 第 undefined 頁"

## 📝 Technical Details

### SSE Event Flow

```
Upload Start
    ↓
Producer reads PDF pages in batches
    ↓
For each batch:
    ├─→ Event 1: checkpoint (phase: batch_start)
    │   └─→ Frontend: "🔄 處理批次 X: 頁 A-B"
    │
    ├─→ Embedding generation
    │
    └─→ Event 2: checkpoint (phase: batch_complete)
        └─→ Frontend: "✓ 檢查點: 第 B 頁"
```

### Why Two Checkpoint Events?

**Design Rationale**:
- **batch_start**: Informs user processing has begun (good for UX feedback)
- **batch_complete**: Confirms batch was successfully embedded and saved (checkpoint for resume)

**Resume Capability**: If upload fails, system can resume from last `batch_complete` checkpoint.

## 🧪 Testing Checklist

- [ ] Upload a PDF with 100+ pages
- [ ] Verify "🔄 處理批次 X: 頁 A-B" appears (batch_start)
- [ ] Verify "✓ 檢查點: 第 X 頁" appears (batch_complete)
- [ ] No "undefined" in any messages
- [ ] No "(xxx chunks)" in checkpoint messages
- [ ] Progress bar updates correctly with page numbers

## 📚 Related Files

| File | Lines | Description |
|------|-------|-------------|
| `template/skill_config.html` | 1959-1971 | Frontend SSE event handler (FIXED) |
| `app/api/v1/endpoints/skills.py` | 1523-1531 | Backend: batch_start checkpoint |
| `app/api/v1/endpoints/skills.py` | 1606-1616 | Backend: batch_complete checkpoint |

---

**Status**: ✅ Fixed
**Date**: 2025-12-14
**Impact**: Medium (UI/UX clarity improvement)
**Risk**: Low (Display logic only, no backend changes)
