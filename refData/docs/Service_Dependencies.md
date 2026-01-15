## 1. Service Dependencies Map

### 1.1 Core Service Dependencies

```
RetrievalService
├── Dependencies:
│   ├── EmbeddingProvider (Providers layer)
│   ├── VectorStoreProvider (Providers layer)
│   └── Config: settings.CHUNK_SIZE, CHUNK_OVERLAP
├── Purpose: Vector similarity search and context retrieval
├── Key Methods:
│   ├── add_document_chunks() → Add chunks to FAISS
│   ├── retrieve_context() → Vector search with fair_distribution mode
│   ├── retrieve_context_text() → Concatenated context string
│   └── delete_document() → Remove vector store
└── File-based paradigm: Operates on file_ids

DocumentOverviewService
├── Dependencies:
│   ├── LLMProviderClient (Providers layer)
│   ├── FileMetadataProvider (Providers layer)
│   └── Config: OVERVIEW_CHUNK_LIMIT, OVERVIEW_MAX_CHARS
├── Purpose: Generate and store document-level overviews
├── Key Methods:
│   ├── generate_overview() → LLM-based document summary
│   ├── store_overview() → SQLite persistence
│   ├── get_overview() → Retrieve single overview
│   └── get_multiple_overviews() → Batch retrieval
└── File-based paradigm: Stores overviews in document_overviews table

QueryEnhancementService
├── Dependencies:
│   ├── LLMProviderClient (Providers layer)
│   ├── CacheProvider (optional, Providers layer)
│   └── Config: EXPANSION_COUNT, EXPANSION_TEMPERATURE
├── Purpose: Query expansion (Strategy 2: sub-question decomposition)
├── Key Methods:
│   ├── expand_query() → LLM-based query expansion
│   ├── detect_summary_intent() → Summary keyword detection
│   └── get_query_metadata() → Intent classification
└── Query-agnostic: Can work with any retrieval paradigm

IterativeQueryExpansionService
├── Dependencies:
│   ├── LLMProviderClient (Providers layer)
│   ├── IntentDetectorFactory (query_intent_detection submodule)
│   ├── CacheProvider (optional)
│   └── Config: EXPANSION_ROUNDS, EXPANSION_COUNT
├── Purpose: Advanced multi-round query expansion with quality scoring
├── Key Methods:
│   ├── expand_query_iterative() → Multi-round expansion
│   ├── detect_multi_file_intent() → Multi-file query detection (NEW)
│   └── score_queries() → LLM-based quality evaluation
└── Query-agnostic: Can work with any retrieval paradigm

InputDataHandleService
├── Dependencies:
│   ├── ChunkingStrategyFactory (Services layer)
│   ├── FileMetadataProvider (Providers layer)
│   └── Config: CHUNK_SIZE, CHUNK_OVERLAP, ALLOWED_EXTENSIONS
├── Purpose: File extraction and text chunking
├── Key Methods:
│   ├── validate_file() → File type/size validation
│   ├── extract_text() → PDF/DOCX/TXT extraction
│   ├── chunk_text() → Strategy-based chunking
│   ├── generate_unique_file_id() → Collision-resistant ID generation
│   └── process_file() → Complete ingestion workflow
└── File-based paradigm: Generates file_ids and file metadata

PromptService
├── Dependencies:
│   └── Config: System prompt templates
├── Purpose: Prompt template management and context assembly
├── Key Methods:
│   ├── build_rag_prompt() → Standard RAG prompt with context
│   ├── build_multi_file_summary_prompt() → Multi-file specialized prompt
│   └── format_context_for_display() → Debug formatting
└── Retrieval-agnostic: Works with any context source
```

### 1.2 Submodule: query_intent_detection

```
query_intent_detection/ (Strategy Pattern implementation)
├── base.py
│   ├── IntentDetectionStrategy (ABC)
│   └── MultiFileIntentResult (dataclass)
├── regex_strategy.py
│   └── RegexPatternStrategy (implemented)
├── string_parsing_strategy.py
│   └── StringParsingStrategy (stub)
├── nlp_strategy.py
│   └── NLPBasedStrategy (stub)
├── factory.py
│   └── IntentDetectorFactory (Factory Method)
└── integration.py
    └── Integration layer for IterativeQueryExpansionService

Purpose: Detect multi-file intent queries (e.g., "請分別說明各別文件")
Pattern: Strategy + Factory Method
Dependencies: None (standalone)