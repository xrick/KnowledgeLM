## Solutions for SQLite Issues

### 1. Write Concurrency

**Queue-based writes**
```python
import queue
import threading

class SQLiteWriteQueue:
    def __init__(self, db_path):
        self.queue = queue.Queue()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.worker = threading.Thread(target=self._process, daemon=True)
        self.worker.start()
    
    def _process(self):
        while True:
            sql, params, event = self.queue.get()
            try:
                self.conn.execute(sql, params)
                self.conn.commit()
            finally:
                event.set()
    
    def execute(self, sql, params=()):
        event = threading.Event()
        self.queue.put((sql, params, event))
        event.wait()  # Block until write completes
```

**Batch writes**
```python
def batch_insert(conn, chunks, batch_size=1000):
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        conn.executemany(
            "INSERT INTO chunks (doc_id, content, embedding) VALUES (?, ?, ?)",
            batch
        )
        conn.commit()
```

**Retry with exponential backoff**
```python
import time
import sqlite3

def execute_with_retry(conn, sql, params=(), max_retries=5):
    for attempt in range(max_retries):
        try:
            conn.execute(sql, params)
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < max_retries - 1:
                time.sleep((2 ** attempt) * 0.1)  # 0.1, 0.2, 0.4, 0.8, 1.6s
            else:
                raise
```

---

### 2. WAL Mode Configuration

```python
def configure_sqlite(db_path):
    conn = sqlite3.connect(db_path)
    
    # Enable WAL mode - allows concurrent reads during writes
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Sync less frequently (faster, slightly less durable)
    conn.execute("PRAGMA synchronous=NORMAL")
    
    # Increase cache size (negative = KB, positive = pages)
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    
    # Store temp tables in memory
    conn.execute("PRAGMA temp_store=MEMORY")
    
    # Increase busy timeout (ms) - wait instead of failing immediately
    conn.execute("PRAGMA busy_timeout=5000")
    
    # Auto-checkpoint when WAL reaches 1000 pages
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    
    return conn
```

**Manual WAL checkpointing** (for maintenance windows)
```python
def checkpoint_wal(conn):
    # TRUNCATE mode: checkpoint and truncate WAL file
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
```

---

### 3. Connection Pooling

**Using SQLAlchemy**
```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    "sqlite:///rag.db",
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_pre_ping=True,  # Verify connections before use
    connect_args={
        "check_same_thread": False,
        "timeout": 30
    }
)

# Usage
with engine.connect() as conn:
    result = conn.execute("SELECT * FROM chunks WHERE doc_id = ?", (doc_id,))
```

**Simple thread-safe pool**
```python
import sqlite3
from contextlib import contextmanager
from queue import Queue

class ConnectionPool:
    def __init__(self, db_path, pool_size=5):
        self.pool = Queue(maxsize=pool_size)
        for _ in range(pool_size):
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            self.pool.put(conn)
    
    @contextmanager
    def get_connection(self):
        conn = self.pool.get()
        try:
            yield conn
        finally:
            self.pool.put(conn)

# Usage
pool = ConnectionPool("rag.db")
with pool.get_connection() as conn:
    cursor = conn.execute("SELECT content FROM chunks WHERE id = ?", (chunk_id,))
```

---

### 4. File Locking / NFS Issues

**Solution A: Avoid NFS entirely**
```python
import tempfile
import shutil

# Use local storage, sync to NFS periodically
LOCAL_DB = "/tmp/rag_local.db"
NFS_DB = "/mnt/nfs/rag.db"

def sync_to_nfs():
    shutil.copy2(LOCAL_DB, NFS_DB)
```

**Solution B: Use URI with immutable flag (read-only on NFS)**
```python
# For read-only access on NFS
conn = sqlite3.connect("file:/mnt/nfs/rag.db?mode=ro&immutable=1", uri=True)
```

**Solution C: Locking mode for single-process access**
```python
conn = sqlite3.connect("rag.db")
conn.execute("PRAGMA locking_mode=EXCLUSIVE")  # Hold lock for session lifetime
```

**Solution D: Use a proper client-server DB if NFS is required**
```python
# If you must use network storage with concurrent writers,
# migrate to PostgreSQL or MySQL
from sqlalchemy import create_engine

# PostgreSQL handles network/concurrent access properly
engine = create_engine("postgresql://user:pass@host/ragdb")
```

---

### Quick Reference

| Issue | Best Solution |
|-------|---------------|
| Write concurrency | Write queue + WAL mode |
| Performance | WAL + cache_size + busy_timeout |
| Multi-threaded app | Connection pool (SQLAlchemy) |
| NFS/network storage | Avoid, or migrate to PostgreSQL |
