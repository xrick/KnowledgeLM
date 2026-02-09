sqlite3 /home/mapleleaf/LCJRepos/gitprjs/DocAI/data/skill_metadata.db ".schema" 

CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE skill_metadata (
                skill_id TEXT PRIMARY KEY,
                skill_name TEXT NOT NULL,
                skill_description TEXT,
                skill_category TEXT,
                skill_level TEXT DEFAULT 'intermediate',
                tags TEXT,
                related_skills TEXT,
                total_chunks INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            , embedding_model TEXT DEFAULT 'text-embedding-ada-002', embedding_dimension INTEGER DEFAULT 1536, parent_skill_id TEXT DEFAULT 'root', source_name TEXT DEFAULT NULL, head_id TEXT REFERENCES skill_heads(head_id), processing_status TEXT DEFAULT 'completed', indexed_chunks INTEGER DEFAULT 0, last_error TEXT DEFAULT NULL, processing_started_at TEXT DEFAULT NULL, processing_completed_at TEXT DEFAULT NULL);
CREATE TABLE skill_overviews (
                skill_id TEXT PRIMARY KEY,
                overview TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
            );
CREATE TABLE skill_document_mapping (
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                relevance_score REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, document_name TEXT, document_path TEXT, total_pages INTEGER DEFAULT 0,
                FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
            );
CREATE TABLE skill_chunk_metadata (
                chunk_id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                document_name TEXT NOT NULL,
                page_number INTEGER,
                chunk_index INTEGER,
                chunk_text TEXT,
                embedding_model TEXT DEFAULT 'text-embedding-ada-002',
                embedding_dimension INTEGER DEFAULT 1536,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
            );
CREATE TABLE embedding_models (
                model_name TEXT PRIMARY KEY,
                model_type TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                max_sequence_length INTEGER,
                language_support TEXT,
                configuration TEXT,
                is_active BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
CREATE TABLE skill_heads (
                head_id TEXT PRIMARY KEY,
                skill_name TEXT NOT NULL UNIQUE,
                description TEXT,
                category TEXT DEFAULT 'General',
                display_order INTEGER DEFAULT 0,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
CREATE TABLE processing_jobs (
    job_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    head_id TEXT,
    pdf_path TEXT NOT NULL,
    pdf_filename TEXT,
    pdf_size_bytes INTEGER,
    total_pages INTEGER DEFAULT 0,
    last_processed_page INTEGER DEFAULT 0,
    total_chunks INTEGER DEFAULT 0,
    processed_chunks INTEGER DEFAULT 0,
    batch_size INTEGER DEFAULT 12,
    status TEXT DEFAULT 'pending',
    dirty_batches TEXT,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    error_stack TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    completed_at TEXT,
    processing_time_seconds REAL,
    avg_page_time_ms REAL,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id),
    FOREIGN KEY (head_id) REFERENCES skill_heads(head_id)
);
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,
    username TEXT DEFAULT 'default_user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_default BOOLEAN DEFAULT 0
);
CREATE TABLE lost_and_found(rootpgno INTEGER, pgno INTEGER, nfield INTEGER, id INTEGER, c0, c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13, c14, c15, c16, c17, c18, c19, c20);
CREATE INDEX idx_skill_category
            ON skill_metadata(skill_category)
        ;
CREATE INDEX idx_skill_name
            ON skill_metadata(skill_name)
        ;
CREATE INDEX idx_skill_level
            ON skill_metadata(skill_level)
        ;
CREATE INDEX idx_skill_doc_mapping_skill
            ON skill_document_mapping(skill_id)
        ;
CREATE INDEX idx_skill_doc_mapping_file
            ON skill_document_mapping(file_id)
        ;
CREATE INDEX idx_chunk_skill_page
            ON skill_chunk_metadata(skill_id, document_name, page_number)
        ;
CREATE INDEX idx_parent_skill_id ON skill_metadata(parent_skill_id);
CREATE INDEX idx_skill_head_id
            ON skill_metadata(head_id)
        ;
CREATE INDEX idx_pj_status ON processing_jobs(status);
CREATE INDEX idx_pj_skill ON processing_jobs(skill_id);
CREATE INDEX idx_pj_created ON processing_jobs(created_at);
CREATE INDEX idx_processing_status ON skill_metadata(processing_status);