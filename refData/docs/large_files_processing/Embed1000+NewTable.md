CREATE TABLE IF NOT EXISTS processing_jobs (
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

-- 索引
CREATE INDEX IF NOT EXISTS idx_pj_status ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_pj_skill ON processing_jobs(skill_id);
CREATE INDEX IF NOT EXISTS idx_pj_created ON processing_jobs(created_at);   