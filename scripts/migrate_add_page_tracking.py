#!/usr/bin/env python3
"""
Migration script to add page tracking for Skill chunks
Adds support for BGE-M3 embeddings and page-based citations
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Add page tracking tables and columns for legal document Skills"""

    db_path = Path("data/skill_metadata.db")
    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Create new table for chunk metadata with page tracking
        logger.info("Creating skill_chunk_metadata table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skill_chunk_metadata (
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
            )
        """)

        # Create index for efficient page-based queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunk_skill_page
            ON skill_chunk_metadata(skill_id, document_name, page_number)
        """)

        # Add embedding_model column to skill_metadata if not exists
        cursor.execute("""
            SELECT COUNT(*) FROM pragma_table_info('skill_metadata')
            WHERE name='embedding_model'
        """)
        if cursor.fetchone()[0] == 0:
            logger.info("Adding embedding_model column to skill_metadata...")
            cursor.execute("""
                ALTER TABLE skill_metadata
                ADD COLUMN embedding_model TEXT DEFAULT 'text-embedding-ada-002'
            """)
            cursor.execute("""
                ALTER TABLE skill_metadata
                ADD COLUMN embedding_dimension INTEGER DEFAULT 1536
            """)

        # Update skill_document_mapping to include document names
        cursor.execute("""
            SELECT COUNT(*) FROM pragma_table_info('skill_document_mapping')
            WHERE name='document_name'
        """)
        if cursor.fetchone()[0] == 0:
            logger.info("Adding document_name to skill_document_mapping...")
            cursor.execute("""
                ALTER TABLE skill_document_mapping
                ADD COLUMN document_name TEXT
            """)
            cursor.execute("""
                ALTER TABLE skill_document_mapping
                ADD COLUMN document_path TEXT
            """)
            cursor.execute("""
                ALTER TABLE skill_document_mapping
                ADD COLUMN total_pages INTEGER DEFAULT 0
            """)

        # Create table for storing BGE-M3 model configuration
        logger.info("Creating embedding_models table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embedding_models (
                model_name TEXT PRIMARY KEY,
                model_type TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                max_sequence_length INTEGER,
                language_support TEXT,
                configuration TEXT,
                is_active BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert BGE-M3 configuration
        cursor.execute("""
            INSERT OR IGNORE INTO embedding_models
            (model_name, model_type, dimension, max_sequence_length, language_support, configuration, is_active)
            VALUES
            ('BAAI/bge-m3', 'BGE-M3', 1024, 8192, 'multilingual',
             '{"normalize": true, "use_fp16": true, "device": "cpu"}', 1)
        """)

        # Keep existing models for compatibility
        cursor.execute("""
            INSERT OR IGNORE INTO embedding_models
            (model_name, model_type, dimension, max_sequence_length, language_support, configuration, is_active)
            VALUES
            ('text-embedding-ada-002', 'OpenAI', 1536, 8191, 'multilingual',
             '{"api_based": true}', 0),
            ('all-MiniLM-L6-v2', 'SentenceTransformer', 384, 512, 'english',
             '{"normalize": true}', 0)
        """)

        conn.commit()
        logger.info("✅ Database migration completed successfully!")

        # Display current schema info
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        logger.info(f"Current tables: {[t[0] for t in tables]}")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = migrate_database()
    if success:
        print("✅ Migration completed successfully!")
    else:
        print("❌ Migration failed! Check logs for details.")