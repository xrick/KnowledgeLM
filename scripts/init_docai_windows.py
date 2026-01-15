#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
DocAI Windows 環境初始化腳本
=============================================================================

此腳本用於在 Windows 環境下初始化 DocAI 所需的所有資料儲存：
1. SQLite - skill_metadata.db 及所有表格
2. FAISS - 向量索引目錄結構
3. MongoDB - docai 資料庫和 chat_sessions 集合
4. Redis - 初始化配置和 key patterns

使用方式:
    python scripts/init_docai_windows.py [options]

選項:
    --all          初始化所有資料儲存 (預設)
    --sqlite       只初始化 SQLite
    --faiss        只初始化 FAISS 目錄
    --mongodb      只初始化 MongoDB
    --redis        只初始化 Redis
    --force        強制重建（覆蓋現有資料）
    --verbose      顯示詳細輸出

作者: SuperClaude Framework
日期: 2026-01-14
相容性: Windows 10/11, Python 3.9+
=============================================================================
"""

import argparse
import json
import logging
import os
import pickle
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# =============================================================================
# 顏色輸出（Windows 相容）
# =============================================================================


class Colors:
    """Windows 相容的終端顏色"""

    # 啟用 Windows ANSI 支援
    if sys.platform == "win32":
        os.system("")  # 啟用 ANSI escape codes

    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"


def print_header(title: str):
    """印出區塊標題"""
    print(f"\n{Colors.BLUE}{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}{Colors.RESET}\n")


def print_success(msg: str):
    """印出成功訊息"""
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")


def print_warning(msg: str):
    """印出警告訊息"""
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")


def print_error(msg: str):
    """印出錯誤訊息"""
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")


def print_info(msg: str):
    """印出資訊訊息"""
    print(f"{Colors.CYAN}ℹ️  {msg}{Colors.RESET}")


# =============================================================================
# SQLite 初始化模組
# =============================================================================


class SQLiteInitializer:
    """SQLite skill_metadata.db 初始化器"""

    # 完整 Schema SQL
    SCHEMA_SQL = """
-- =============================================================================
-- DocAI Skill Metadata Database Schema
-- Version: 1.0 | Created: 2026-01-14
-- =============================================================================

-- 啟用 WAL 模式（提升並發性能）
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=10000;
PRAGMA temp_store=MEMORY;
PRAGMA busy_timeout=5000;
PRAGMA wal_autocheckpoint=1000;

-- =============================================================================
-- Table 1: skill_heads - Skill 定義（單一真相來源）
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_heads (
    head_id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL UNIQUE,
    description TEXT,
    category TEXT DEFAULT 'General',
    display_order INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Table 2: skill_metadata - Skill 文件/來源資料
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_metadata (
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
    metadata TEXT,
    parent_skill_id TEXT DEFAULT 'root',
    source_name TEXT,
    head_id TEXT,
    processing_status TEXT DEFAULT 'pending',
    indexed_chunks INTEGER DEFAULT 0,
    last_error TEXT,
    processing_started_at TIMESTAMP,
    processing_completed_at TIMESTAMP,
    FOREIGN KEY (head_id) REFERENCES skill_heads(head_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 3: skill_overviews - LLM 生成的摘要
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_overviews (
    skill_id TEXT PRIMARY KEY,
    overview TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 4: skill_document_mapping - Skill 與文件的關聯
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_document_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    relevance_score REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 5: skill_chunk_metadata - Chunk 級別元數據
-- =============================================================================
CREATE TABLE IF NOT EXISTS skill_chunk_metadata (
    chunk_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT,
    page_number INTEGER,
    faiss_index INTEGER,
    embedding_model TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,
    FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
);

-- =============================================================================
-- Table 6: processing_jobs - PDF 處理任務追蹤
-- =============================================================================
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

-- =============================================================================
-- 索引 - 提升查詢效能
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_skill_category ON skill_metadata(skill_category);
CREATE INDEX IF NOT EXISTS idx_skill_name ON skill_metadata(skill_name);
CREATE INDEX IF NOT EXISTS idx_skill_level ON skill_metadata(skill_level);
CREATE INDEX IF NOT EXISTS idx_skill_head_id ON skill_metadata(head_id);
CREATE INDEX IF NOT EXISTS idx_skill_parent ON skill_metadata(parent_skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_status ON skill_metadata(processing_status);
CREATE INDEX IF NOT EXISTS idx_skill_doc_mapping_skill ON skill_document_mapping(skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_doc_mapping_file ON skill_document_mapping(file_id);
CREATE INDEX IF NOT EXISTS idx_chunk_skill ON skill_chunk_metadata(skill_id);
CREATE INDEX IF NOT EXISTS idx_chunk_index ON skill_chunk_metadata(skill_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_pj_status ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_pj_skill ON processing_jobs(skill_id);
CREATE INDEX IF NOT EXISTS idx_pj_created ON processing_jobs(created_at);
"""

    def __init__(self, db_path: Path, force: bool = False, verbose: bool = False):
        self.db_path = db_path
        self.force = force
        self.verbose = verbose
        self.backup_dir = db_path.parent / "backups"

    def initialize(self) -> bool:
        """執行 SQLite 初始化"""
        print_header("SQLite skill_metadata.db 初始化")

        try:
            # 檢查現有資料庫
            if self.db_path.exists():
                if self.force:
                    self._backup_and_remove()
                else:
                    print_warning(f"資料庫已存在: {self.db_path}")
                    print_info("使用 --force 參數強制重建")

                    # 驗證現有資料庫
                    if self._verify_existing():
                        print_success("現有資料庫結構完整")
                        return True
                    else:
                        print_error("現有資料庫結構不完整，請使用 --force 重建")
                        return False

            # 確保目錄存在
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # 創建資料庫
            print_info(f"創建資料庫: {self.db_path}")
            conn = sqlite3.connect(str(self.db_path))

            # 執行 Schema
            conn.executescript(self.SCHEMA_SQL)

            # 插入初始化測試記錄
            conn.execute(
                """
                INSERT INTO skill_heads (head_id, skill_name, description, category, display_order, enabled)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    "head_init_test",
                    "_system_init_test",
                    "Database initialization test record - can be safely deleted",
                    "System",
                    999,
                    False,
                ),
            )

            conn.commit()
            conn.close()

            # 驗證
            if self._verify_database():
                print_success("skill_metadata.db 初始化成功")
                self._show_summary()
                return True
            else:
                print_error("資料庫驗證失敗")
                return False

        except Exception as e:
            print_error(f"SQLite 初始化失敗: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False

    def _backup_and_remove(self):
        """備份並移除現有資料庫"""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        backup_name = f"skill_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = self.backup_dir / backup_name

        print_info(f"備份現有資料庫到: {backup_path}")
        shutil.copy2(self.db_path, backup_path)

        # 移除 WAL 和 SHM 文件
        self.db_path.unlink()
        wal_path = self.db_path.with_suffix(".db-wal")
        shm_path = self.db_path.with_suffix(".db-shm")
        if wal_path.exists():
            wal_path.unlink()
        if shm_path.exists():
            shm_path.unlink()

        print_success("備份完成")

    def _verify_existing(self) -> bool:
        """驗證現有資料庫結構"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # 檢查所有必要表格
            required_tables = [
                "skill_heads",
                "skill_metadata",
                "skill_overviews",
                "skill_document_mapping",
                "skill_chunk_metadata",
                "processing_jobs",
            ]

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}

            conn.close()

            missing = set(required_tables) - existing_tables
            if missing:
                print_warning(f"缺少表格: {missing}")
                return False

            return True

        except Exception as e:
            print_error(f"驗證失敗: {e}")
            return False

    def _verify_database(self) -> bool:
        """驗證新建資料庫"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # 完整性檢查
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]

            if result != "ok":
                print_error(f"完整性檢查失敗: {result}")
                conn.close()
                return False

            print_success("完整性檢查: 通過")
            conn.close()
            return True

        except Exception as e:
            print_error(f"驗證失敗: {e}")
            return False

    def _show_summary(self):
        """顯示資料庫摘要"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            print_info("已創建的表格:")
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            for row in cursor.fetchall():
                print(f"  📋 {row[0]}")

            print()
            print_info("已創建的索引:")
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            )
            for row in cursor.fetchall():
                print(f"  🔍 {row[0]}")

            conn.close()

        except Exception as e:
            if self.verbose:
                print_warning(f"顯示摘要失敗: {e}")


# =============================================================================
# FAISS 初始化模組
# =============================================================================


class FAISSInitializer:
    """FAISS 向量索引目錄初始化器"""

    def __init__(self, base_path: Path, force: bool = False, verbose: bool = False):
        self.base_path = base_path
        self.force = force
        self.verbose = verbose

        # FAISS 目錄結構
        self.dirs = {
            "files": base_path / "faiss_indices",  # 檔案模式索引
            "skills": base_path / "faiss_indices" / "skills",  # Skill 模式索引
        }

    def initialize(self) -> bool:
        """執行 FAISS 目錄初始化"""
        print_header("FAISS 向量索引目錄初始化")

        try:
            created = []
            existing = []

            for name, path in self.dirs.items():
                if path.exists():
                    existing.append(name)
                    if self.verbose:
                        print_info(f"目錄已存在: {path}")
                else:
                    path.mkdir(parents=True, exist_ok=True)
                    created.append(name)
                    print_success(f"創建目錄: {path}")

            # 創建 README.md 說明文件
            readme_path = self.dirs["files"] / "README.md"
            if not readme_path.exists() or self.force:
                self._create_readme(readme_path)

            # 顯示結構
            self._show_structure()

            print_success("FAISS 目錄初始化完成")
            return True

        except Exception as e:
            print_error(f"FAISS 初始化失敗: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False

    def _create_readme(self, path: Path):
        """創建說明文件"""
        content = """# FAISS 向量索引目錄

此目錄存放 DocAI 系統的 FAISS 向量索引。

## 目錄結構

```
faiss_indices/
├── file_XXXXXXXX_XXXXXXXX_XXXXXXXX/    # 檔案模式索引
│   ├── index.faiss                     # FAISS 向量索引
│   └── index.pkl                       # 對應的文字 chunks
└── skills/                             # Skill 模式索引
    └── skill_YYYYMMDD_HHMMSS_XXX/
        ├── index.faiss
        └── index.pkl
```

## 檔案說明

- `index.faiss`: FAISS 向量索引二進位檔
- `index.pkl`: Pickle 序列化的文字 chunks 和元資料

## 注意事項

1. 請勿手動修改或刪除這些檔案
2. 備份時請完整備份整個目錄
3. 還原時確保檔案配對完整（.faiss + .pkl）
"""
        path.write_text(content, encoding="utf-8")
        print_success(f"創建說明文件: {path}")

    def _show_structure(self):
        """顯示目錄結構"""
        print()
        print_info("FAISS 目錄結構:")
        for name, path in self.dirs.items():
            # 計算現有索引數量
            count = 0
            if path.exists():
                count = len([d for d in path.iterdir() if d.is_dir()])
            print(f"  📁 {path}")
            if count > 0:
                print(f"     └── 現有索引: {count} 個")


# =============================================================================
# MongoDB 初始化模組
# =============================================================================


class MongoDBInitializer:
    """MongoDB 資料庫初始化器"""

    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        database: str = "docai",
        verbose: bool = False,
    ):
        self.uri = uri
        self.database = database
        self.verbose = verbose

    def initialize(self) -> bool:
        """執行 MongoDB 初始化"""
        print_header("MongoDB 資料庫初始化")

        try:
            # 嘗試導入 pymongo
            try:
                from pymongo import MongoClient
                from pymongo.errors import (
                    ConnectionFailure,
                    ServerSelectionTimeoutError,
                )
            except ImportError:
                print_error("pymongo 未安裝")
                print_info("請執行: pip install pymongo")
                return False

            # 連接 MongoDB
            print_info(f"連接到 MongoDB: {self.uri}")
            client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)

            # 測試連接
            try:
                client.admin.command("ping")
                print_success("MongoDB 連接成功")
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                print_error(f"無法連接到 MongoDB: {e}")
                print_info("請確認 MongoDB 服務正在運行")
                return False

            # 選擇資料庫
            db = client[self.database]
            print_info(f"使用資料庫: {self.database}")

            # 創建 chat_sessions 集合
            self._create_chat_sessions_collection(db)

            # 創建索引
            self._create_indexes(db)

            # 插入測試文檔
            self._insert_test_document(db)

            # 驗證
            self._verify_and_show_stats(db)

            client.close()
            print_success("MongoDB 初始化完成")
            return True

        except Exception as e:
            print_error(f"MongoDB 初始化失敗: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False

    def _create_chat_sessions_collection(self, db):
        """創建 chat_sessions 集合（含 schema validation）"""
        collection_name = "chat_sessions"

        if collection_name in db.list_collection_names():
            print_info(f"集合 {collection_name} 已存在")
            return

        # 創建帶有 schema validation 的集合
        validator = {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["session_id", "created_at", "updated_at", "messages"],
                "properties": {
                    "session_id": {
                        "bsonType": "string",
                        "description": "Unique session identifier - required",
                    },
                    "user_id": {
                        "bsonType": ["string", "null"],
                        "description": "Optional user identifier",
                    },
                    "file_ids": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"},
                        "description": "Files associated with this session",
                    },
                    "created_at": {
                        "bsonType": "date",
                        "description": "Session creation timestamp - required",
                    },
                    "updated_at": {
                        "bsonType": "date",
                        "description": "Last update timestamp - required",
                    },
                    "messages": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["role", "content", "timestamp"],
                            "properties": {
                                "role": {
                                    "enum": ["user", "assistant", "system"],
                                    "description": "Message role - required",
                                },
                                "content": {
                                    "bsonType": "string",
                                    "description": "Message content - required",
                                },
                                "timestamp": {
                                    "bsonType": "date",
                                    "description": "Message timestamp - required",
                                },
                                "metadata": {
                                    "bsonType": "object",
                                    "description": "Optional message metadata",
                                },
                            },
                        },
                        "description": "Array of chat messages - required",
                    },
                    "metadata": {
                        "bsonType": "object",
                        "description": "Optional session-level metadata",
                    },
                },
            }
        }

        db.create_collection(
            collection_name,
            validator=validator,
            validationLevel="moderate",
            validationAction="warn",
        )
        print_success(f"創建集合: {collection_name}")

    def _create_indexes(self, db):
        """創建索引"""
        collection = db["chat_sessions"]

        indexes = [
            {
                "keys": [("session_id", 1)],
                "unique": True,
                "name": "idx_session_id_unique",
            },
            {"keys": [("user_id", 1)], "name": "idx_user_id"},
            {"keys": [("created_at", -1)], "name": "idx_created_at"},
            {"keys": [("updated_at", -1)], "name": "idx_updated_at"},
            {"keys": [("file_ids", 1)], "name": "idx_file_ids"},
            {"keys": [("user_id", 1), ("updated_at", -1)], "name": "idx_user_recent"},
        ]

        existing_indexes = {idx["name"] for idx in collection.list_indexes()}

        for idx in indexes:
            if idx["name"] in existing_indexes:
                if self.verbose:
                    print_info(f"索引已存在: {idx['name']}")
                continue

            collection.create_index(
                idx["keys"], unique=idx.get("unique", False), name=idx["name"]
            )
            print_success(f"創建索引: {idx['name']}")

    def _insert_test_document(self, db):
        """插入測試文檔"""
        collection = db["chat_sessions"]

        test_doc = {
            "session_id": "docai_init_test",
            "user_id": "system",
            "file_ids": [],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "messages": [
                {
                    "role": "system",
                    "content": "DocAI MongoDB schema initialized successfully",
                    "timestamp": datetime.now(timezone.utc),
                    "metadata": {"init_script": True, "version": "1.0"},
                }
            ],
            "metadata": {
                "init_version": "1.0",
                "init_date": datetime.now(timezone.utc).isoformat(),
                "description": "Initialization test document - can be safely deleted",
            },
        }

        existing = collection.find_one({"session_id": "docai_init_test"})
        if existing:
            collection.update_one(
                {"session_id": "docai_init_test"},
                {"$set": {"updated_at": datetime.now(timezone.utc)}},
            )
            print_info("測試文檔已存在，已更新時間戳")
        else:
            collection.insert_one(test_doc)
            print_success("插入測試文檔: docai_init_test")

    def _verify_and_show_stats(self, db):
        """驗證並顯示統計"""
        collection = db["chat_sessions"]

        print()
        print_info("MongoDB 狀態:")
        print(f"  📁 資料庫: {self.database}")
        print(f"  📁 集合: chat_sessions")

        # 索引數
        index_count = len(list(collection.list_indexes()))
        print(f"  🔍 索引數: {index_count}")

        # 文檔數
        doc_count = collection.count_documents({})
        print(f"  📄 文檔數: {doc_count}")


# =============================================================================
# Redis 初始化模組
# =============================================================================


class RedisInitializer:
    """Redis 初始化器"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        verbose: bool = False,
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.verbose = verbose

    def initialize(self) -> bool:
        """執行 Redis 初始化"""
        print_header("Redis 初始化")

        try:
            # 嘗試導入 redis
            try:
                import redis
            except ImportError:
                print_error("redis 套件未安裝")
                print_info("請執行: pip install redis")
                return False

            # 連接 Redis
            print_info(f"連接到 Redis: {self.host}:{self.port}")
            client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True,
                socket_connect_timeout=5,
            )

            # 測試連接
            try:
                client.ping()
                print_success("Redis 連接成功")
            except redis.ConnectionError as e:
                print_error(f"無法連接到 Redis: {e}")
                print_info("請確認 Redis 服務正在運行")
                return False

            # 設置初始化配置
            self._set_init_config(client)

            # 顯示 Key 模式說明
            self._show_key_patterns()

            # 顯示狀態
            self._show_status(client)

            client.close()
            print_success("Redis 初始化完成")
            return True

        except Exception as e:
            print_error(f"Redis 初始化失敗: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False

    def _set_init_config(self, client):
        """設置初始化配置"""
        init_time = datetime.now(timezone.utc).isoformat()

        # 設置初始化標記
        client.set("docai:init", init_time)
        print_success(f"設置初始化時間: {init_time}")

        # 設置版本
        client.set("docai:version", "1.0.0")
        print_success("設置版本: 1.0.0")

        # 設置 TTL 配置
        client.hset(
            "docai:config",
            mapping={
                "embedding_ttl": "86400",  # 24 hours
                "query_expansion_ttl": "3600",  # 1 hour
                "search_results_ttl": "1800",  # 30 minutes
                "file_metadata_ttl": "21600",  # 6 hours
            },
        )
        print_success("設置 TTL 配置")

    def _show_key_patterns(self):
        """顯示 Key 模式說明"""
        print()
        print_info("DocAI Redis Key 模式:")
        print(
            f"{Colors.CYAN}┌──────────────────────────────────────────────────────────────────┐{Colors.RESET}"
        )
        print(
            f"{Colors.CYAN}│{Colors.RESET} Key Pattern            │ TTL      │ Description               {Colors.CYAN}│{Colors.RESET}"
        )
        print(
            f"{Colors.CYAN}├──────────────────────────────────────────────────────────────────┤{Colors.RESET}"
        )
        print(
            f"{Colors.CYAN}│{Colors.RESET} emb:{{text_hash}}        │ 24h      │ Embedding 向量快取        {Colors.CYAN}│{Colors.RESET}"
        )
        print(
            f"{Colors.CYAN}│{Colors.RESET} qexp:{{query_hash}}      │ 1h       │ 查詢擴展結果快取          {Colors.CYAN}│{Colors.RESET}"
        )
        print(
            f"{Colors.CYAN}│{Colors.RESET} search:{{hash}}          │ 30min    │ 搜尋結果快取              {Colors.CYAN}│{Colors.RESET}"
        )
        print(
            f"{Colors.CYAN}│{Colors.RESET} file:{{file_id}}         │ 6h       │ 文件元數據快取            {Colors.CYAN}│{Colors.RESET}"
        )
        print(
            f"{Colors.CYAN}│{Colors.RESET} docai:init             │ -        │ 初始化時間戳              {Colors.CYAN}│{Colors.RESET}"
        )
        print(
            f"{Colors.CYAN}│{Colors.RESET} docai:version          │ -        │ 系統版本                  {Colors.CYAN}│{Colors.RESET}"
        )
        print(
            f"{Colors.CYAN}│{Colors.RESET} docai:config           │ -        │ TTL 配置 (Hash)           {Colors.CYAN}│{Colors.RESET}"
        )
        print(
            f"{Colors.CYAN}└──────────────────────────────────────────────────────────────────┘{Colors.RESET}"
        )

    def _show_status(self, client):
        """顯示 Redis 狀態"""
        print()
        print_info("Redis 服務狀態:")

        # 版本
        info = client.info()
        print(f"  Redis 版本: {info.get('redis_version', 'unknown')}")

        # 記憶體
        print(f"  已使用記憶體: {info.get('used_memory_human', 'unknown')}")

        # 連接數
        print(f"  連接客戶端數: {info.get('connected_clients', 'unknown')}")

        # Key 數量
        dbsize = client.dbsize()
        print(f"  Key 總數: {dbsize}")


# =============================================================================
# 主程式
# =============================================================================


def parse_args():
    """解析命令列參數"""
    parser = argparse.ArgumentParser(
        description="DocAI Windows 環境初始化腳本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
    python init_docai_windows.py                    # 初始化所有資料儲存
    python init_docai_windows.py --sqlite           # 只初始化 SQLite
    python init_docai_windows.py --mongodb --redis  # 初始化 MongoDB 和 Redis
    python init_docai_windows.py --force            # 強制重建所有資料
        """,
    )

    # 選擇性初始化
    parser.add_argument("--all", action="store_true", help="初始化所有資料儲存（預設）")
    parser.add_argument("--sqlite", action="store_true", help="只初始化 SQLite")
    parser.add_argument("--faiss", action="store_true", help="只初始化 FAISS 目錄")
    parser.add_argument("--mongodb", action="store_true", help="只初始化 MongoDB")
    parser.add_argument("--redis", action="store_true", help="只初始化 Redis")

    # 選項
    parser.add_argument(
        "--force", "-f", action="store_true", help="強制重建（覆蓋現有資料）"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="顯示詳細輸出")

    # 配置覆寫
    parser.add_argument("--data-dir", type=str, default="./data", help="資料目錄路徑")
    parser.add_argument(
        "--mongodb-uri",
        type=str,
        default="mongodb://localhost:27017",
        help="MongoDB URI",
    )
    parser.add_argument(
        "--redis-host", type=str, default="localhost", help="Redis 主機"
    )
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis 端口")

    return parser.parse_args()


def main():
    """主函數"""
    args = parse_args()

    # 設定 logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    print(f"{Colors.BOLD}")
    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║          DocAI Windows 環境初始化工具 v1.0                        ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}")

    # 決定要初始化哪些組件
    init_sqlite = (
        args.sqlite
        or args.all
        or not any([args.sqlite, args.faiss, args.mongodb, args.redis])
    )
    init_faiss = (
        args.faiss
        or args.all
        or not any([args.sqlite, args.faiss, args.mongodb, args.redis])
    )
    init_mongodb = (
        args.mongodb
        or args.all
        or not any([args.sqlite, args.faiss, args.mongodb, args.redis])
    )
    init_redis = (
        args.redis
        or args.all
        or not any([args.sqlite, args.faiss, args.mongodb, args.redis])
    )

    data_dir = Path(args.data_dir)
    results = {}

    # SQLite 初始化
    if init_sqlite:
        sqlite_init = SQLiteInitializer(
            db_path=data_dir / "skill_metadata.db",
            force=args.force,
            verbose=args.verbose,
        )
        results["SQLite"] = sqlite_init.initialize()

    # FAISS 初始化
    if init_faiss:
        faiss_init = FAISSInitializer(
            base_path=data_dir, force=args.force, verbose=args.verbose
        )
        results["FAISS"] = faiss_init.initialize()

    # MongoDB 初始化
    if init_mongodb:
        mongodb_init = MongoDBInitializer(
            uri=args.mongodb_uri, database="docai", verbose=args.verbose
        )
        results["MongoDB"] = mongodb_init.initialize()

    # Redis 初始化
    if init_redis:
        redis_init = RedisInitializer(
            host=args.redis_host, port=args.redis_port, verbose=args.verbose
        )
        results["Redis"] = redis_init.initialize()

    # 顯示總結
    print_header("初始化結果總結")

    all_success = True
    for component, success in results.items():
        if success:
            print_success(f"{component}: 成功")
        else:
            print_error(f"{component}: 失敗")
            all_success = False

    print()
    if all_success:
        print_success("所有組件初始化完成！")
        print()
        print_info("下一步:")
        print("  1. 確認 .env 環境變數已正確設置")
        print("  2. 啟動 DocAI: python main.py")
        print("  3. 訪問 http://localhost:8000 開始使用")
    else:
        print_warning("部分組件初始化失敗，請檢查上方錯誤訊息")

    return 0 if all_success else 1


if __name__ == "__main__":
    sys.exit(main())
