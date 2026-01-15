# SQLite Issues Integration Plan

**Date**: 2025-01-10
**Reference**: `refData/Codes/Sqlite/issues.md`
**Status**: PLAN ONLY - Awaiting User Approval
**Impact Analysis**: ✅ COMPLETED - See "Detailed Impact Analysis" section below

---

## Executive Summary

Analyzed the SQLite best practices from `issues.md` against current DocAI implementation. Found several gaps that should be addressed to improve database resilience and performance.

---

## Current Implementation Status

### SkillMetadataProvider (`app/Providers/skill_metadata_provider/client.py`)

| Feature | Status | Details |
|---------|--------|---------|
| WAL Mode | ✅ Implemented | `PRAGMA journal_mode=WAL` |
| Synchronous | ✅ Implemented | `PRAGMA synchronous=NORMAL` |
| Cache Size | ✅ Implemented | `PRAGMA cache_size=10000` (10MB) |
| Temp Store | ✅ Implemented | `PRAGMA temp_store=MEMORY` |
| Connection Timeout | ✅ Implemented | `timeout=30.0` |
| Async Lock | ✅ Implemented | `self._lock = asyncio.Lock()` |
| busy_timeout PRAGMA | ❌ Missing | SQLite-level busy wait not configured |
| wal_autocheckpoint | ❌ Missing | Using SQLite default |
| Manual WAL Checkpoint | ❌ Missing | No maintenance function |
| Retry with Backoff | ❌ Missing | No retry on lock errors |
| Batch Insert | ❌ Missing | Uses individual INSERTs |

### FileMetadataProvider (`app/Providers/file_metadata_provider/client.py`)

| Feature | Status | Details |
|---------|--------|---------|
| WAL Mode | ❌ **MISSING** | Not enabled at all! |
| Synchronous | ❌ Missing | Not configured |
| Cache Size | ❌ Missing | Using SQLite default (2MB) |
| Temp Store | ❌ Missing | Not configured |
| Connection Timeout | ❌ Missing | Using default 5 seconds |
| busy_timeout PRAGMA | ❌ Missing | Not configured |
| wal_autocheckpoint | ❌ Missing | Not configured |

---

## Gap Analysis

### Critical Finding

**FileMetadataProvider has NONE of the optimizations** that were applied to SkillMetadataProvider during the 2025-12-16 "database is locked" fix. This means the file-based system is vulnerable to the same concurrency issues that were already solved for the skill-based system.

---

## Integration Plan

### Phase 1: Immediate Priority (Before Demo)

#### Task 1.1: Add WAL Mode to FileMetadataProvider

**File**: `app/Providers/file_metadata_provider/client.py`

**Current Code** (Lines ~55-60):
```python
async def _get_connection(self) -> aiosqlite.Connection:
    if self._connection is None:
        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row
    return self._connection
```

**Proposed Code**:
```python
async def _get_connection(self) -> aiosqlite.Connection:
    if self._connection is None:
        self._connection = await aiosqlite.connect(
            str(self.db_path),
            timeout=30.0,  # Increased from default 5.0s
            check_same_thread=False  # Allow async usage
        )
        self._connection.row_factory = aiosqlite.Row
        
        # Enable WAL mode for better concurrent read/write performance
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA synchronous=NORMAL")
        await self._connection.execute("PRAGMA cache_size=10000")
        await self._connection.execute("PRAGMA temp_store=MEMORY")
        await self._connection.execute("PRAGMA busy_timeout=5000")
        
        logger.info("Created file database connection with WAL mode")
    
    return self._connection
```

**Risk**: Low - Same changes that already work in SkillMetadataProvider
**Effort**: 15 minutes

---

#### Task 1.2: Add busy_timeout to SkillMetadataProvider

**File**: `app/Providers/skill_metadata_provider/client.py`

**Location**: After line ~85 (after `PRAGMA temp_store=MEMORY`)

**Add**:
```python
await self._connection.execute("PRAGMA busy_timeout=5000")  # 5 second busy wait
```

**Rationale**: The `timeout=30.0` in `aiosqlite.connect()` controls Python-level connection timeout, while `PRAGMA busy_timeout` controls SQLite-internal wait time when encountering a lock.

**Risk**: Very low
**Effort**: 5 minutes

---

### Phase 2: Post-Demo Improvements (Week 1-2)

#### Task 2.1: Create Database Utilities Module

**File**: New `app/Providers/db_utils.py`

```python
"""
Database Utilities for SQLite Operations

Provides:
- Batch insert for high-volume operations
- Retry logic with exponential backoff
- WAL checkpoint management
"""

import asyncio
import logging
from typing import List, Any, Tuple
import aiosqlite

logger = logging.getLogger(__name__)


async def batch_insert(
    conn: aiosqlite.Connection,
    table: str,
    columns: List[str],
    rows: List[Tuple],
    batch_size: int = 1000
) -> int:
    """
    Batch insert rows using executemany for better performance.
    
    Args:
        conn: Database connection
        table: Table name
        columns: List of column names
        rows: List of tuples with values
        batch_size: Number of rows per batch (default 1000)
    
    Returns:
        Total number of rows inserted
    
    Example:
        >>> rows = [(1, "text1"), (2, "text2"), ...]
        >>> count = await batch_insert(conn, "chunks", ["id", "text"], rows)
    """
    if not rows:
        return 0
    
    placeholders = ','.join(['?' for _ in columns])
    column_names = ','.join(columns)
    sql = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"
    
    total_inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        await conn.executemany(sql, batch)
        await conn.commit()
        total_inserted += len(batch)
        logger.debug(f"Batch inserted {len(batch)} rows into {table}")
    
    return total_inserted


async def execute_with_retry(
    conn: aiosqlite.Connection,
    sql: str,
    params: Tuple = (),
    max_retries: int = 5
) -> None:
    """
    Execute SQL with exponential backoff retry on lock errors.
    
    Args:
        conn: Database connection
        sql: SQL statement
        params: Query parameters
        max_retries: Maximum retry attempts (default 5)
    
    Raises:
        aiosqlite.OperationalError: If all retries fail
    
    Example:
        >>> await execute_with_retry(conn, "UPDATE ...", (value, id))
    """
    for attempt in range(max_retries):
        try:
            await conn.execute(sql, params)
            await conn.commit()
            return
        except aiosqlite.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 0.1  # 0.1, 0.2, 0.4, 0.8, 1.6s
                logger.warning(f"Database locked, retry {attempt + 1}/{max_retries} in {wait_time}s")
                await asyncio.sleep(wait_time)
            else:
                raise


async def checkpoint_wal(conn: aiosqlite.Connection) -> None:
    """
    Perform WAL checkpoint to clean up WAL file.
    
    Call during maintenance windows or when WAL file grows large.
    
    Args:
        conn: Database connection
    
    Example:
        >>> await checkpoint_wal(conn)
    """
    await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    logger.info("WAL checkpoint completed (TRUNCATE mode)")
```

**Risk**: Low - Utility functions with no side effects
**Effort**: 30 minutes

---

#### Task 2.2: Add WAL Autocheckpoint to Both Providers

**Files**: 
- `app/Providers/skill_metadata_provider/client.py`
- `app/Providers/file_metadata_provider/client.py`

**Add after other PRAGMAs**:
```python
await self._connection.execute("PRAGMA wal_autocheckpoint=1000")  # Checkpoint at 1000 pages
```

**Risk**: Very low
**Effort**: 10 minutes

---

#### Task 2.3: Refactor Skill Ingestion to Use Batch Insert

**File**: `app/SkillServices/pdf_skill_ingestion_service.py`

**Current Pattern** (individual inserts):
```python
for chunk in chunks:
    await conn.execute("INSERT INTO skill_chunk_metadata ...")
    await conn.commit()
```

**Proposed Pattern** (batch insert):
```python
from app.Providers.db_utils import batch_insert

# Prepare all rows
rows = [
    (chunk.skill_id, chunk.chunk_index, chunk.chunk_text, ...)
    for chunk in chunks
]

# Batch insert
await batch_insert(
    conn,
    "skill_chunk_metadata",
    ["skill_id", "chunk_index", "chunk_text", ...],
    rows,
    batch_size=500
)
```

**Impact**: 
- Large PDFs (1000+ pages) will insert much faster
- Reduces transaction overhead
- Improves FAISS index consistency

**Risk**: Medium - Requires testing with actual PDF processing
**Effort**: 1-2 hours

---

### Phase 3: Future Optimization (Week 2+)

#### Task 3.1: Add Manual WAL Checkpoint Methods to Providers

**Files**: Both providers

```python
async def checkpoint_wal(self) -> None:
    """
    Perform WAL checkpoint during maintenance.
    
    Call this:
    - During low-traffic periods
    - Before database backup
    - When WAL file exceeds expected size
    """
    conn = await self._get_connection()
    await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    logger.info("WAL checkpoint completed")
```

**Risk**: Very low
**Effort**: 15 minutes

---

#### Task 3.2: Add Retry Logic to Critical Write Operations

Apply `execute_with_retry` to:
- `create_skill()`
- `update_skill()`
- `delete_skill()`
- `add_file()`
- `update_embedding_status()`

**Risk**: Low - Graceful degradation
**Effort**: 1 hour

---

### NOT IMPLEMENTING (With Justification)

#### Connection Pooling (SQLAlchemy)

**Reason**: 
- Current singleton + WAL mode already handles concurrency well
- Adding SQLAlchemy would require significant refactoring
- aiosqlite doesn't need connection pooling like sync drivers
- The 2025-12-16 fix proved singleton + WAL is sufficient

**When to reconsider**: If we exceed 50+ concurrent requests consistently

#### NFS/Network Storage Considerations

**Reason**:
- Current deployment uses local storage
- SQLite is not recommended for network-mounted databases
- If needed, migrate to PostgreSQL instead

**When to reconsider**: If deploying to cloud with shared storage

---

## Implementation Summary

| Phase | Task | Priority | Effort | Risk |
|-------|------|----------|--------|------|
| 1 | FileMetadataProvider WAL Mode | 🔴 High | 15 min | Low |
| 1 | busy_timeout to SkillMetadataProvider | 🔴 High | 5 min | Very Low |
| 2 | Create db_utils.py | 🟡 Medium | 30 min | Low |
| 2 | WAL Autocheckpoint | 🟡 Medium | 10 min | Very Low |
| 2 | Batch Insert for Ingestion | 🟡 Medium | 1-2 hr | Medium |
| 3 | Manual WAL Checkpoint Methods | 🟢 Low | 15 min | Very Low |
| 3 | Retry Logic for Writes | 🟢 Low | 1 hr | Low |

---

## Verification Checklist

After implementation, verify:

### Phase 1 Verification
```bash
# Check WAL files exist for both databases
ls -lh data/*.db*

# Expected:
# data/docai.db
# data/docai.db-shm (WAL shared memory)
# data/docai.db-wal (WAL log)
# data/skill_metadata.db
# data/skill_metadata.db-shm
# data/skill_metadata.db-wal
```

### Concurrent Load Test
```bash
# Run 10 concurrent requests
for i in {1..10}; do
    curl -s http://localhost:8082/api/v1/files/list &
done
wait

# All should return 200, no "database is locked" errors
```

### Phase 2 Verification
```bash
# Test batch insert performance
time python -c "
import asyncio
from app.SkillServices.pdf_skill_ingestion_service import ...
# Process a 1000+ page PDF and measure time
"
```

---

---

## Detailed Impact Analysis (影響分析)

### 🔍 逐步思考：修改會不會影響現有功能？

經過詳細的依賴鏈分析和風險評估，以下是結論：

### Phase 1 Changes - 影響分析

#### Change 1.1: FileMetadataProvider 加入 WAL Mode

| 分析項目 | 風險評估 | 說明 |
|----------|----------|------|
| 現有資料 | ✅ 安全 | WAL 模式不改變資料，只改變日誌方式 |
| 連線行為 | ✅ 安全 | 同樣的 singleton 模式，只是更好的設定 |
| SQL 查詢 | ✅ 安全 | 不改變任何 SQL，只影響連線初始化 |
| 檔案系統 | ⚠️ 新增檔案 | WAL 會產生 `.db-wal` 和 `.db-shm` 檔案 |
| 回滾難度 | ✅ 簡單 | 還原程式碼，刪除 WAL 檔案即可 |

**關鍵證據**: 這與 SkillMetadataProvider 在 2025-12-16 已經成功運作的設定**完全相同**。
參見: `claudedocs/otherdocs/Sqlite_locked_solved_complete.md`

**結論**: 🟢 **低風險** - 已驗證的模式

---

#### Change 1.2: SkillMetadataProvider 加入 busy_timeout

| 分析項目 | 風險評估 | 說明 |
|----------|----------|------|
| 現有查詢 | ✅ 安全 | busy_timeout 只影響鎖定等待，不影響查詢結果 |
| 效能 | ✅ 安全/更好 | 允許 SQLite 等待 5 秒再失敗 |
| 連線行為 | ✅ 安全 | 不改變連線運作方式 |
| 資料完整性 | ✅ 安全 | 不修改任何資料 |

**結論**: 🟢 **極低風險** - 純粹新增一個 PRAGMA

---

### Phase 2 Changes - 影響分析

#### db_utils.py (新檔案)

| 分析項目 | 風險評估 | 說明 |
|----------|----------|------|
| 現有程式碼 | ✅ 安全 | 全新檔案，不接觸現有程式碼 |
| Import 系統 | ✅ 安全 | 只有明確使用時才會 import |
| 依賴項 | ✅ 安全 | 只使用已安裝的 aiosqlite |

**結論**: 🟢 **零風險** - 新的獨立模組

---

#### Batch Insert 重構

| 分析項目 | 風險評估 | 說明 |
|----------|----------|------|
| 資料完整性 | ⚠️ 中等 | 批次 commit vs 個別 commit |
| 錯誤處理 | ⚠️ 中等 | 批次失敗時，哪些 rows 已成功？ |
| 交易大小 | ⚠️ 中等 | 較大的交易 = 較長的鎖定時間 |
| 回滾行為 | ⚠️ 中等 | 部分批次失敗需要處理 |

**結論**: 🟡 **中等風險** - 需要完整測試，**不應在 Demo 前實作**

---

### 依賴鏈分析

#### FileMetadataProvider 被使用的位置：
```
app/api/v1/endpoints/files.py
app/api/v1/endpoints/chat.py
app/Services/file_service.py
app/Services/upload_service.py
```

**使用的方法**:
- `add_file()` → INSERT 操作 → ✅ SQL 不變
- `get_file()` → SELECT 操作 → ✅ SQL 不變
- `list_files()` → SELECT 操作 → ✅ SQL 不變
- `delete_file()` → DELETE 操作 → ✅ SQL 不變
- `update_embedding_status()` → UPDATE 操作 → ✅ SQL 不變

**結論**: 所有方法都透過 `_get_connection()` 使用連線。修改**只影響連線初始化方式**，不影響查詢執行。

---

### 風險矩陣總結

| 修改項目 | 風險等級 | 影響現有功能 | 回滾難度 |
|----------|----------|--------------|----------|
| FileMetadataProvider WAL | 🟢 低 | 無功能變更 | 簡單 |
| SkillMetadataProvider busy_timeout | 🟢 極低 | 無功能變更 | 簡單 |
| db_utils.py (新檔案) | 🟢 零 | 新的獨立檔案 | 刪除檔案 |
| wal_autocheckpoint | 🟢 極低 | 明確設定預設值 | 簡單 |
| Batch Insert 重構 | 🟡 中等 | 改變 ingestion 流程 | 中等 |

---

### 測試檢查清單

#### 修改前 (基準測試):
```bash
# 測試現有功能
curl http://localhost:8082/api/v1/files/list
curl http://localhost:8082/api/v1/skills/tree
# 兩者都應回傳 200 OK
```

#### 修改後 (驗證測試):
```bash
# 相同測試
curl http://localhost:8082/api/v1/files/list
curl http://localhost:8082/api/v1/skills/tree

# 驗證 WAL 檔案存在
ls -la data/*.db*
# 預期: docai.db, docai.db-wal, docai.db-shm
#       skill_metadata.db, skill_metadata.db-wal, skill_metadata.db-shm

# 並行負載測試
for i in {1..10}; do curl -s http://localhost:8082/api/v1/files/list & done
# 全部應成功，無 "database is locked" 錯誤
```

---

### 最終建議

✅ **Phase 1 可以安全實作**:
1. 與 SkillMetadataProvider 已驗證的設定完全相同
2. 不改變任何 SQL 查詢或業務邏輯
3. 只影響連線初始化（內部實作細節）
4. 有簡單的回滾方案
5. 自 2025-12-16 以來已在生產環境驗證

⚠️ **Batch Insert 重構應延後**:
直到有完整的測試基礎設施

---

## Approval Request

Please review this plan and approve:

- [ ] Phase 1 implementation (immediate, ~20 minutes)
- [ ] Phase 2 implementation (post-demo, ~2 hours)  
- [ ] Phase 3 implementation (future, ~1.5 hours)

Once approved, I will implement the changes in order of priority.

---

*Document Author: Claude (SuperClaude Framework)*
*Analysis Method: Sequential Thinking + Code Review*
