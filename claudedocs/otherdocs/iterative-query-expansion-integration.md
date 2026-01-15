# Iterative Query Expansion Service - Architecture & Integration

## Overview

The `IterativeQueryExpansionService` is the **single consolidated query enhancement service** for DocAI's RAG pipeline. It replaces the previous `QueryEnhancementService` to provide simplicity and robustness.

## Service Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     IterativeQueryExpansionService                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────┐     ┌─────────────────────┐                   │
│  │ Summary Detection   │     │ Query Expansion     │                   │
│  │                     │     │                     │                   │
│  │ - SUMMARY_KEYWORDS  │     │ - SINGLE mode       │                   │
│  │ - detect_summary()  │     │ - ITERATIVE mode    │                   │
│  │ - get_metadata()    │     │ - ADAPTIVE mode     │                   │
│  └─────────────────────┘     └─────────────────────┘                   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Multi-Round Expansion Engine                  │   │
│  │                                                                  │   │
│  │  Round 1: Initial Expansion                                     │   │
│  │  ├── Generate 3-5 expanded queries from different perspectives  │   │
│  │  └── Score queries (if enabled)                                 │   │
│  │                                                                  │   │
│  │  Round 2: Refinement (if max_rounds >= 2)                       │   │
│  │  ├── Select top queries above pruning threshold                 │   │
│  │  ├── Further refine each selected query                        │   │
│  │  └── Score refined queries                                      │   │
│  │                                                                  │   │
│  │  Round 3: Final Refinement (if max_rounds == 3)                 │   │
│  │  └── Additional refinement pass                                 │   │
│  │                                                                  │   │
│  │  Selection: LLM-based best query selection                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Configuration Settings

Located in `app/core/config.py`:

```python
# Query Enhancement Settings
ENABLE_QUERY_ENHANCEMENT: bool = True
ENHANCEMENT_STRATEGY: str = "question_expansion"
EXPANSION_COUNT: int = 3  # Queries per round
EXPANSION_TEMPERATURE: float = 0.3  # Lower for consistency

# Iterative Expansion Settings
ENABLE_ITERATIVE_EXPANSION: bool = True  # Enable multi-round
ITERATIVE_EXPANSION_ROUNDS: int = 2  # Number of rounds (1-3)
EXPANSION_PRUNING_THRESHOLD: float = 0.6  # Min quality score
ENABLE_EXPANSION_SCORING: bool = True  # LLM-based scoring
EXPANSION_STRATEGY_MODE: str = "adaptive"  # single/iterative/adaptive
```

## Expansion Strategies

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `SINGLE` | One expansion round only | Long, detailed queries |
| `ITERATIVE` | Multi-round with refinement | Short, vague queries |
| `ADAPTIVE` | Auto-select based on query | Default mode |

### Adaptive Strategy Logic

```python
def _assess_query_complexity(self, query: str) -> ExpansionStrategy:
    word_count = len(query.split())
    query_length = len(query)

    # Short queries → iterative expansion
    if word_count <= 5 or query_length <= 30:
        return ExpansionStrategy.ITERATIVE

    # Long queries → single round
    if word_count > 30 or query_length > 200:
        return ExpansionStrategy.SINGLE

    return ExpansionStrategy.ITERATIVE
```

## Integration with RAG Pipeline

### Complete Flow Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                          RAG PIPELINE FLOW                             │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  User Query: "請幫我摘要這份文件"                                      │
│       │                                                                │
│       ▼                                                                │
│  ╔════════════════════════════════════════════╗                       │
│  ║  PHASE 1: Query Understanding              ║                       │
│  ╠════════════════════════════════════════════╣                       │
│  ║                                            ║                       │
│  ║  IterativeQueryExpansionService            ║                       │
│  ║  │                                         ║                       │
│  ║  ├─► detect_summary_intent(query)          ║                       │
│  ║  │   └─► is_summary = True                 ║                       │
│  ║  │                                         ║                       │
│  ║  └─► expand_iteratively(query, strategy)   ║                       │
│  ║      │                                     ║                       │
│  ║      ├─► Round 1: 3 expanded queries       ║                       │
│  ║      ├─► Score & prune (threshold=0.6)     ║                       │
│  ║      ├─► Round 2: Refine top queries       ║                       │
│  ║      └─► Select best query via LLM         ║                       │
│  ║                                            ║                       │
│  ║  Output:                                   ║                       │
│  ║  - best_query: "請提供文件的核心摘要..."   ║                       │
│  ║  - final_queries: [q1, q2, q3, q4, q5]     ║                       │
│  ║  - expansion_rounds: 2                     ║                       │
│  ╚════════════════════════════════════════════╝                       │
│       │                                                                │
│       ▼                                                                │
│  ╔════════════════════════════════════════════╗                       │
│  ║  PHASE 2: Parallel Retrieval               ║                       │
│  ╠════════════════════════════════════════════╣                       │
│  ║                                            ║                       │
│  ║  RetrievalService                          ║                       │
│  ║  │                                         ║                       │
│  ║  ├─► For each query in final_queries:      ║                       │
│  ║  │   └─► Vector similarity search          ║                       │
│  ║  │                                         ║                       │
│  ║  ├─► fair_distribution = is_summary AND    ║                       │
│  ║  │   len(file_ids) > 1                     ║                       │
│  ║  │   (Balances chunks across files)        ║                       │
│  ║  │                                         ║                       │
│  ║  └─► Merge & deduplicate results           ║                       │
│  ║                                            ║                       │
│  ║  Output: context_chunks[]                  ║                       │
│  ╚════════════════════════════════════════════╝                       │
│       │                                                                │
│       ▼                                                                │
│  ╔════════════════════════════════════════════╗                       │
│  ║  PHASE 3: Context Assembly                 ║                       │
│  ╠════════════════════════════════════════════╣                       │
│  ║                                            ║                       │
│  ║  PromptService.build_rag_prompt()          ║                       │
│  ║  │                                         ║                       │
│  ║  ├─► SYSTEM_PROMPT_TEMPLATE                ║                       │
│  ║  │   ┌─────────────────────────────────┐   ║                       │
│  ║  │   │ 你是一位專業的文檔問答助手      │   ║                       │
│  ║  │   │ [用戶勾選的文檔內容]            │   ║                       │
│  ║  │   │ {context} ◄─ context_chunks     │   ║                       │
│  ║  │   └─────────────────────────────────┘   ║                       │
│  ║  │                                         ║                       │
│  ║  └─► if is_summary == True:                ║                       │
│  ║      └─► Append SUMMARY_INSTRUCTION_SUFFIX ║                       │
│  ║          ┌─────────────────────────────┐   ║                       │
│  ║          │ 【摘要生成要求】            │   ║                       │
│  ║          │ 1. 簡潔性：200-250字        │   ║                       │
│  ║          │ 2. 結構化：主題/方法/結論   │   ║                       │
│  ║          │ 3. 多文件處理：分別標示     │   ║                       │
│  ║          └─────────────────────────────┘   ║                       │
│  ║                                            ║                       │
│  ║  Output: messages[] (OpenAI format)        ║                       │
│  ╚════════════════════════════════════════════╝                       │
│       │                                                                │
│       ▼                                                                │
│  ╔════════════════════════════════════════════╗                       │
│  ║  PHASE 4: Response Generation              ║                       │
│  ╠════════════════════════════════════════════╣                       │
│  ║                                            ║                       │
│  ║  LLMProviderClient                         ║                       │
│  ║  │                                         ║                       │
│  ║  └─► get_chat_completion_stream(messages)  ║                       │
│  ║      └─► SSE streaming to frontend         ║                       │
│  ║                                            ║                       │
│  ║  Output: Final answer (streamed)           ║                       │
│  ╚════════════════════════════════════════════╝                       │
│       │                                                                │
│       ▼                                                                │
│  ╔════════════════════════════════════════════╗                       │
│  ║  PHASE 5: Post Processing                  ║                       │
│  ╠════════════════════════════════════════════╣                       │
│  ║                                            ║                       │
│  ║  ChatHistoryProvider                       ║                       │
│  ║  └─► Save user message & assistant response║                       │
│  ╚════════════════════════════════════════════╝                       │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

## Key Integration Points

### 1. Intent Detection → Retrieval

The `is_summary` flag from intent detection affects retrieval strategy:

```python
# In chat.py
query_metadata = iterative_expansion_service.get_query_metadata(request.query)
is_summary = query_metadata.get("is_summary", False)

# Affects retrieval
enable_fair_dist = is_summary and len(request.file_ids) > 1
retrieval_service.retrieve_context(..., fair_distribution=enable_fair_dist)
```

### 2. Intent Detection → Prompt Assembly

The `is_summary` flag affects prompt construction:

```python
# In chat.py
messages = prompt_service.build_rag_prompt(
    query=request.query,
    context_chunks=context_strings,
    is_summary=is_summary  # Adds SUMMARY_INSTRUCTION_SUFFIX
)
```

### 3. Expanded Queries → Parallel Retrieval

Multiple queries enable broader context retrieval:

```python
# In chat.py
retrieval_tasks = [
    retrieval_service.retrieve_context(query=question, ...)
    for question in expanded_questions  # final_queries from expansion
]
results = await asyncio.gather(*retrieval_tasks)
```

## Quality Scoring Dimensions

When `ENABLE_EXPANSION_SCORING = True`, queries are scored on:

| Dimension | Description | Weight |
|-----------|-------------|--------|
| `relevance` | Match to original intent | 0-1 |
| `specificity` | Clarity and precision | 0-1 |
| `retrieval_fit` | Suitability for vector search | 0-1 |
| `coverage` | Information breadth | 0-1 |

Queries below `EXPANSION_PRUNING_THRESHOLD` (default 0.6) are pruned between rounds.

## Summary Detection Keywords

```python
SUMMARY_KEYWORDS = [
    "摘要", "總結", "概述", "summary", "summarize", "overview",
    "概括", "簡述", "歸納", "重點", "要點", "大意"
]
```

## Data Flow Summary

```
User Query
    │
    ▼
┌───────────────────────────────────────────────┐
│ IterativeQueryExpansionService                │
│ ├─ detect_summary_intent() → is_summary       │
│ └─ expand_iteratively() → best_query,         │
│                            final_queries,     │
│                            expansion_rounds   │
└───────────────────────────────────────────────┘
    │
    │ is_summary ──────────────────┐
    │ final_queries                │
    ▼                              ▼
┌─────────────────┐    ┌─────────────────────────┐
│ RetrievalService│    │ PromptService           │
│ (fair_dist if   │    │ (SUMMARY_SUFFIX if      │
│  summary+multi) │    │  is_summary=True)       │
└─────────────────┘    └─────────────────────────┘
    │                              │
    └──────────── context ─────────┘
                   │
                   ▼
           ┌──────────────┐
           │ LLMProvider  │
           │ (Generate    │
           │  Response)   │
           └──────────────┘
                   │
                   ▼
            Final Answer
```

## File References

| File | Purpose |
|------|---------|
| `app/Services/iterative_query_expansion_service.py` | Main service implementation |
| `app/Services/prompt_service.py` | Prompt templates and assembly |
| `app/api/v1/endpoints/chat.py` | Pipeline orchestration |
| `app/core/config.py` | Configuration settings |

## API Response Fields

The chat endpoint returns expansion metadata:

```json
{
  "session_id": "...",
  "query": "original query",
  "answer": "LLM response",
  "context_count": 5,
  "expanded_questions": ["q1", "q2", "q3"],
  "best_query": "optimized query selected by LLM",
  "expansion_rounds": 2,
  "metadata": {
    "iterative_expansion_used": true
  }
}
```

---

*Generated: 2024-11-22 | DocAI RAG Pipeline Documentation*
