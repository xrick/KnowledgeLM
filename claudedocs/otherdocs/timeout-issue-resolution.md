# RAG Pipeline Timeout Issue - Root Cause & Resolution

## Issue Summary

**Error Messages:**
```
[DocAI] Stream timeout after 5 minutes
[DocAI] Stream reading error: AbortError: BodyStreamBuffer was aborted
Chat error: Error: Request timeout after 5 minutes - LLM may be loading model
```

**Date Resolved:** 2024-11-22

---

## Root Cause Analysis

### The Problem

The iterative query expansion service was making **5+ sequential LLM calls** before the actual RAG retrieval and response generation even started:

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1: Query Expansion (BEFORE FIX)                          │
│                                                                 │
│  LLM Call 1: Round 1 Expansion      ~30-60s                    │
│  LLM Call 2: Round 1 Scoring        ~30-60s                    │
│  LLM Call 3: Round 2 Refinement     ~30-60s                    │
│  LLM Call 4: Round 2 Scoring        ~30-60s                    │
│  LLM Call 5: Best Query Selection   ~30-60s                    │
│                                                                 │
│  Total: 2.5 - 5 minutes (JUST FOR EXPANSION!)                  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2-5: Retrieval + Generation                              │
│  (Never reached due to timeout)                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Why It Happened

1. **Default configuration was too aggressive:**
   - `ITERATIVE_EXPANSION_ROUNDS = 2` (two full expansion rounds)
   - `ENABLE_EXPANSION_SCORING = True` (LLM scoring after each round)
   - `EXPANSION_STRATEGY_MODE = "adaptive"` (could choose multi-round)

2. **No timeout protection:**
   - Each LLM call had no individual timeout
   - No overall time budget for expansion phase
   - No fallback mechanism when expansion took too long

3. **Cold LLM start:**
   - First request to Ollama can take 30-60s to load model
   - Subsequent calls also slow if model swaps out of memory

### Time Budget Before Fix

| Operation | Time (Cold LLM) | Time (Warm LLM) |
|-----------|-----------------|-----------------|
| Round 1 Expansion | 30-60s | 10-20s |
| Round 1 Scoring | 30-60s | 10-20s |
| Round 2 Refinement | 30-60s | 10-20s |
| Round 2 Scoring | 30-60s | 10-20s |
| Best Selection | 30-60s | 10-20s |
| **Total Expansion** | **2.5-5 min** | **50s-1.7min** |
| Retrieval | 1-2s | 1-2s |
| Response Generation | 30-60s | 10-30s |
| **Grand Total** | **3-6 min** | **1-2 min** |

The 5-minute frontend timeout was being hit during the expansion phase alone.

---

## Solution Implementation

### 1. Added Timeout Constants

**File:** `app/Services/iterative_query_expansion_service.py`

```python
# Timeout settings for expansion operations (seconds)
EXPANSION_CALL_TIMEOUT = 30.0  # Max time per LLM call
EXPANSION_TOTAL_TIMEOUT = 60.0  # Max total time for all expansion
```

### 2. Per-Call Timeout Protection

Each expansion round now has `asyncio.wait_for` protection:

```python
try:
    round1_queries = await asyncio.wait_for(
        self._expand_round1(query),
        timeout=EXPANSION_CALL_TIMEOUT
    )
except asyncio.TimeoutError:
    logger.warning(f"Round 1 expansion timeout, using original query")
    return self._create_fallback_result(query, "Round 1 timeout")
```

### 3. Total Time Budget Check

A helper function checks if total expansion time exceeded:

```python
def check_timeout() -> bool:
    elapsed = time.time() - start_time
    if elapsed > EXPANSION_TOTAL_TIMEOUT:
        logger.warning(f"Expansion timeout after {elapsed:.1f}s, using fallback")
        return True
    return False
```

### 4. Graceful Fallback

When timeout occurs, the system falls back to using the original query:

```python
def _create_fallback_result(self, query: str, reason: str) -> ExpansionResult:
    """Create a fallback result when expansion fails or times out"""
    return ExpansionResult(
        original_query=query,
        best_query=query,  # Use original query
        final_queries=[query],
        expansion_tree={query: []},
        quality_scores={},
        total_rounds=0,
        strategy_used="fallback",
        reasoning=reason
    )
```

### 5. Optimized Default Configuration

**File:** `app/core/config.py`

| Setting | Before | After | Impact |
|---------|--------|-------|--------|
| `ITERATIVE_EXPANSION_ROUNDS` | 2 | 1 | -50% LLM calls |
| `ENABLE_EXPANSION_SCORING` | True | False | -2 LLM calls |
| `EXPANSION_STRATEGY_MODE` | "adaptive" | "single" | Predictable fast path |

### 6. Removed LLM Scoring

LLM-based query scoring was removed from the fast path because:
- Each scoring call takes 30s+ on cold LLM
- Simple heuristic selection (first expanded query) works well enough
- Quality improvement from scoring doesn't justify 2x time cost

---

## Performance Comparison

### Before Fix

```
Cold LLM:  5+ minutes → TIMEOUT
Warm LLM:  ~2 minutes → Sometimes works
```

### After Fix

```
Cold LLM:  ~60s max (with fallback)
Warm LLM:  ~30s total
Timeout:   Uses original query (graceful degradation)
```

### Time Budget After Fix

| Operation | Time (Cold LLM) | Time (Warm LLM) |
|-----------|-----------------|-----------------|
| Round 1 Expansion | 30s max | 10-20s |
| **Total Expansion** | **30s max** | **10-20s** |
| Retrieval | 1-2s | 1-2s |
| Response Generation | 30-60s | 10-30s |
| **Grand Total** | **~1.5 min** | **~30-50s** |

---

## Configuration Options

Users can tune the behavior via `.env` or `config.py`:

```python
# Fast mode (default after fix)
EXPANSION_STRATEGY_MODE = "single"
ITERATIVE_EXPANSION_ROUNDS = 1
ENABLE_EXPANSION_SCORING = False

# Quality mode (more LLM calls, slower)
EXPANSION_STRATEGY_MODE = "iterative"
ITERATIVE_EXPANSION_ROUNDS = 2
ENABLE_EXPANSION_SCORING = True  # Not recommended for slow LLMs
```

---

## Files Modified

| File | Changes |
|------|---------|
| `app/Services/iterative_query_expansion_service.py` | Added timeout constants, `asyncio.wait_for`, fallback logic |
| `app/core/config.py` | Changed defaults to fast mode |

---

## Monitoring

Watch for these log messages:

```
# Normal operation
[Round 1] Generated 3 expanded queries in 15.2s

# Timeout triggered (fallback used)
Round 1 expansion timeout, using original query
Using fallback result: Round 1 timeout

# Total timeout (partial results used)
Expansion timeout after 62.1s, using fallback
```

---

## Future Improvements

1. **Parallel LLM calls** - Run expansion and scoring in parallel where possible
2. **Caching** - Cache expansion results for repeated queries
3. **Adaptive timeout** - Adjust timeout based on LLM response times
4. **Stream expansion** - Start retrieval as soon as first expanded query is ready

---

*Resolution documented: 2024-11-22*
