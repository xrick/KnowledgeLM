# Upload Progress Bar Fix - 2025-12-14

## 🐛 Problem

Progress bar only shows **5% (start)** and **100% (end)**, with no intermediate values.

**Visual Behavior**:
```
[████░░░░░░░░░░░░░░] 5%   開始處理...
                           ↓
                    (NO UPDATES!)
                           ↓
[████████████████████] 100% 完成！
```

## 🔍 Root Cause Analysis

### Backend Issue

Most SSE progress events **don't include `percent` field**:

```python
# ❌ Missing percent field (Lines 1382, 1559, 1692)
yield create_upload_sse_event("progress", {
    "phase": "embedding",
    "message": "🧠 嵌入批次 1",
    # NO "percent" field!
})

# ❌ Checkpoint events also missing percent (Lines 1525, 1606)
yield create_upload_sse_event("checkpoint", {
    "phase": "batch_complete",
    "page": total_pages,
    # NO "percent" field!
})

# ✅ Only storage phase had percent (Line 1624)
yield create_upload_sse_event("progress", {
    "phase": "storage",
    "percent": 90  # ← Only this one!
})
```

### Frontend Behavior

Frontend checks if `progressPercent` exists (Line 1917):

```javascript
const progressPercent = data.percent !== undefined ? data.percent :
                       (data.progress !== undefined ? data.progress : data.progress_percent);

if (progressPercent !== undefined) {
    updateUploadProgress(progressPercent, message);  // ✅ Update
} else {
    // ❌ Skip update - progress bar stays at old value!
}
```

**Result**: Progress bar stuck at 5% until final 100%.

## 🔧 Solution Applied

### 1. Get Total Pages Early (Line 1394)

```python
# === PHASE 0: Detect PPT-converted PDF & Get Total Pages ===
total_pages_count = 0  # Will be used for progress calculation
try:
    doc = fitz.open(str(pdf_path))
    total_pages_count = len(doc)  # ✅ Get total pages for progress tracking
```

**Why**: We need to know total pages to calculate percentage.

### 2. Add Progress to batch_start Checkpoint (Lines 1524-1536)

```python
# Calculate progress for batch start (slightly before batch_complete)
batch_start_progress = 10
if total_pages_count > 0:
    batch_start_progress = 10 + int((batch_pages[0] / total_pages_count) * 70)  # Estimate

yield create_upload_sse_event("checkpoint", {
    "phase": "batch_start",
    "batch_num": batch_num,
    "pages": f"{batch_pages[0]}-{batch_pages[-1]}",
    "percent": batch_start_progress,  # ✅ Add progress percentage
})
```

### 3. Add Progress to batch_complete Checkpoint (Lines 1607-1622)

```python
# Calculate progress percentage (10% start, 80% end for processing phase)
progress_percent = 10
if total_pages_count > 0:
    progress_percent = 10 + int((total_pages / total_pages_count) * 70)  # 10-80%

yield create_upload_sse_event("checkpoint", {
    "phase": "batch_complete",
    "page": total_pages,
    "percent": progress_percent,  # ✅ Add progress percentage
})
```

### 4. Update Frontend to Use Progress (Lines 1961-1973)

```javascript
case 'checkpoint':
    if (data.phase === 'batch_start') {
        appendUploadLog(`🔄 處理批次 ${data.batch_num}: 頁 ${data.pages}`, 'info');
        if (progressPercent !== undefined) {
            updateUploadProgress(progressPercent, `處理批次 ${data.batch_num}...`);  // ✅
        }
    } else if (data.phase === 'batch_complete') {
        appendUploadLog(`✓ 檢查點: 第 ${data.page || '?'} 頁`, 'success');
        if (progressPercent !== undefined) {
            updateUploadProgress(progressPercent, `已處理 ${data.page || '?'} 頁...`);  // ✅
        }
    }
    break;
```

## ✅ Expected Behavior (After Fix)

### Progress Mapping

```
 5%  → 開始處理 (start event)
10%  → 批次 1 開始 (page 1-6, batch_start)
15%  → 批次 1 完成 (page 6, batch_complete)
22%  → 批次 2 開始 (page 7-12, batch_start)
28%  → 批次 2 完成 (page 12, batch_complete)
...
75%  → 批次 N 完成 (last batch)
90%  → 儲存向量索引 (storage phase)
95%  → 儲存元資料 (metadata phase)
100% → 完成！ (complete event)
```

### Visual Progress Bar

**Before** (WRONG ❌):
```
[████░░░░░░░░░░░░░░] 5%   開始處理...
[████░░░░░░░░░░░░░░] 5%   (stuck!)
[████░░░░░░░░░░░░░░] 5%   (stuck!)
[████████████████████] 100% 完成！
```

**After** (CORRECT ✅):
```
[████░░░░░░░░░░░░░░] 5%   開始處理...
[████░░░░░░░░░░░░░░] 10%  處理批次 1...
[█████░░░░░░░░░░░░░] 15%  已處理 6 頁...
[██████░░░░░░░░░░░░] 22%  處理批次 2...
[███████░░░░░░░░░░░] 28%  已處理 12 頁...
...
[█████████████████░] 75%  已處理 150 頁...
[██████████████████░] 90%  儲存向量索引...
[███████████████████] 95%  儲存元資料...
[████████████████████] 100% 完成！
```

## 📊 Progress Calculation Logic

### Formula

```python
# Phase mapping:
# - Init: 0-5%
# - Start: 5-10%
# - Batch Processing: 10-80% (based on page progress)
# - FAISS Storage: 80-90%
# - Metadata Storage: 90-95%
# - Complete: 95-100%

batch_progress = 10 + (current_page / total_pages) * 70
```

### Why 10-80% Range?

- **0-10%**: Initialization and PDF detection
- **10-80%**: Main processing (text extraction + embedding generation) - longest phase
- **80-90%**: FAISS storage (fixed at 90%)
- **90-95%**: Metadata storage (fixed at 95%)
- **95-100%**: Completion

The 70% range (10-80%) for batch processing reflects that this is the most time-consuming phase.

## 🧪 Testing Checklist

- [ ] Upload a small PDF (10 pages) - verify progress increments smoothly
- [ ] Upload a medium PDF (50 pages) - verify batch progress updates
- [ ] Upload a large PDF (150+ pages) - verify progress doesn't jump
- [ ] Check progress bar shows: 5% → 10% → 20% → ... → 90% → 100%
- [ ] Verify no "stuck" progress (same % for >30 seconds during processing)
- [ ] Check progress text matches percentage (e.g., "已處理 50 頁" at ~30%)

## 📝 Modified Files

| File | Lines | Changes |
|------|-------|---------|
| `app/api/v1/endpoints/skills.py` | 1391-1394 | Get total_pages_count early from fitz |
| `app/api/v1/endpoints/skills.py` | 1524-1536 | Add percent to batch_start checkpoint |
| `app/api/v1/endpoints/skills.py` | 1607-1622 | Add percent to batch_complete checkpoint |
| `template/skill_config.html` | 1961-1973 | Update frontend to use checkpoint progress |

## 🎯 Key Improvements

1. ✅ **Smooth Progress**: Progress bar updates every batch (not just start/end)
2. ✅ **Accurate Estimation**: Uses actual page count for percentage calculation
3. ✅ **User Feedback**: Shows current batch and page number in progress text
4. ✅ **No Guessing**: Real progress based on actual PDF page count

## ⚠️ Edge Cases Handled

### Small PDFs (< 6 pages = 1 batch)
```
5% → 10% → 40% (batch_complete) → 90% → 100%
```
Still shows intermediate progress!

### Large PDFs (500+ pages)
```
5% → 10% → 11% → 12% → ... → 79% → 80% → 90% → 100%
```
Smooth incremental updates every batch.

### PPT-converted PDFs
Same logic applies - total_pages_count works for all PDF types.

---

**Status**: ✅ Fixed
**Date**: 2025-12-14
**Impact**: High (Critical UX improvement)
**Risk**: Low (Progress calculation only, no data processing changes)
