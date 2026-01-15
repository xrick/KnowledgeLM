資料結構摘要

### SQLite Tables
```
skill_heads          → Skill 定義
skill_metadata       → 文件資料
skill_overviews      → LLM 摘要
skill_document_mapping → 關聯表
skill_chunk_metadata → Chunk 元資料
processing_jobs      → 任務追蹤
```

### FAISS 目錄
```
data/faiss_indices/
├── file_xxx/         → 檔案模式索引
└── skills/
    └── skill_xxx/    → Skill 模式索引
```

### MongoDB
```
docai.chat_sessions
├── session_id (unique)
├── user_id
├── messages[]
└── metadata
```

### Redis Keys
```
emb:{hash}     → Embedding 快取 (TTL: 24h)
qexp:{hash}    → 查詢擴展 (TTL: 1h)
search:{hash}  → 搜尋結果 (TTL: 30min)
docai:config   → TTL 配置
