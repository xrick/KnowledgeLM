# app/Providers/db_utils.py
"""
Database Utilities for SQLite Operations

Provides:
- Batch insert for high-volume operations
- Retry logic with exponential backoff
- WAL checkpoint management

Reference: refData/Codes/Sqlite/issues.md
"""

import asyncio
import logging
from typing import List, Tuple, Optional
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

    This is significantly faster than individual INSERT statements
    for large data volumes (e.g., PDF chunk ingestion).

    Args:
        conn: Database connection
        table: Table name
        columns: List of column names
        rows: List of tuples with values
        batch_size: Number of rows per batch (default 1000)

    Returns:
        Total number of rows inserted

    Example:
        >>> rows = [
        ...     ("skill_001", 0, "chunk text 1"),
        ...     ("skill_001", 1, "chunk text 2"),
        ...     # ... more rows
        ... ]
        >>> count = await batch_insert(
        ...     conn,
        ...     "skill_chunk_metadata",
        ...     ["skill_id", "chunk_index", "chunk_text"],
        ...     rows,
        ...     batch_size=500
        ... )
        >>> print(f"Inserted {count} rows")
    """
    if not rows:
        logger.debug("batch_insert called with empty rows list")
        return 0

    if not columns:
        raise ValueError("columns list cannot be empty")

    placeholders = ','.join(['?' for _ in columns])
    column_names = ','.join(columns)
    sql = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"

    total_inserted = 0
    total_batches = (len(rows) + batch_size - 1) // batch_size

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        batch_num = (i // batch_size) + 1

        try:
            await conn.executemany(sql, batch)
            await conn.commit()
            total_inserted += len(batch)
            logger.debug(f"Batch {batch_num}/{total_batches}: inserted {len(batch)} rows into {table}")
        except Exception as e:
            logger.error(f"Batch {batch_num}/{total_batches} failed: {str(e)}")
            raise

    logger.info(f"batch_insert complete: {total_inserted} rows into {table} in {total_batches} batches")
    return total_inserted


async def execute_with_retry(
    conn: aiosqlite.Connection,
    sql: str,
    params: Tuple = (),
    max_retries: int = 5,
    base_delay: float = 0.1
) -> None:
    """
    Execute SQL with exponential backoff retry on lock errors.

    When SQLite encounters a locked database, this function will
    retry with increasing delays: 0.1s, 0.2s, 0.4s, 0.8s, 1.6s

    Args:
        conn: Database connection
        sql: SQL statement
        params: Query parameters (default empty tuple)
        max_retries: Maximum retry attempts (default 5)
        base_delay: Base delay in seconds (default 0.1)

    Raises:
        aiosqlite.OperationalError: If all retries fail

    Example:
        >>> await execute_with_retry(
        ...     conn,
        ...     "UPDATE skill_metadata SET total_chunks = ? WHERE skill_id = ?",
        ...     (150, "skill_abc123")
        ... )
    """
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            await conn.execute(sql, params)
            await conn.commit()
            if attempt > 0:
                logger.info(f"SQL succeeded after {attempt + 1} attempts")
            return
        except aiosqlite.OperationalError as e:
            error_str = str(e).lower()
            if "locked" in error_str and attempt < max_retries - 1:
                wait_time = (2 ** attempt) * base_delay  # 0.1, 0.2, 0.4, 0.8, 1.6s
                logger.warning(
                    f"Database locked, retry {attempt + 1}/{max_retries} in {wait_time:.1f}s"
                )
                await asyncio.sleep(wait_time)
                last_error = e
            else:
                # Not a lock error or final retry - re-raise immediately
                raise

    # All retries exhausted
    logger.error(f"All {max_retries} retries failed for SQL: {sql[:100]}...")
    if last_error:
        raise last_error


async def checkpoint_wal(conn: aiosqlite.Connection, mode: str = "PASSIVE") -> dict:
    """
    Perform WAL checkpoint to clean up WAL file.

    Call during maintenance windows or when WAL file grows large.

    Checkpoint Modes:
    - PASSIVE: Checkpoint as many frames as possible without waiting
    - FULL: Wait for readers, then checkpoint all frames
    - RESTART: Like FULL, also restarts the WAL file
    - TRUNCATE: Like RESTART, also truncates the WAL file to zero bytes

    Args:
        conn: Database connection
        mode: Checkpoint mode (PASSIVE, FULL, RESTART, TRUNCATE)

    Returns:
        Dict with checkpoint results:
        - mode: The checkpoint mode used
        - busy: Number of frames that could not be checkpointed
        - log: Total number of frames in the WAL
        - checkpointed: Number of frames successfully checkpointed

    Example:
        >>> result = await checkpoint_wal(conn, "TRUNCATE")
        >>> print(f"Checkpointed {result['checkpointed']} frames")
    """
    valid_modes = {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}
    mode = mode.upper()

    if mode not in valid_modes:
        raise ValueError(f"Invalid checkpoint mode: {mode}. Valid modes: {valid_modes}")

    try:
        cursor = await conn.execute(f"PRAGMA wal_checkpoint({mode})")
        row = await cursor.fetchone()

        # wal_checkpoint returns: (busy, log, checkpointed)
        # busy: 0 if successful, 1 if could not run due to a conflicting lock
        # log: total number of frames in the WAL file
        # checkpointed: number of frames that were checkpointed

        result = {
            "mode": mode,
            "busy": row[0] if row else -1,
            "log": row[1] if row else -1,
            "checkpointed": row[2] if row else -1
        }

        if result["busy"] == 0:
            logger.info(
                f"WAL checkpoint ({mode}): {result['checkpointed']}/{result['log']} frames checkpointed"
            )
        else:
            logger.warning(
                f"WAL checkpoint ({mode}) was busy - some frames not checkpointed"
            )

        return result

    except Exception as e:
        logger.error(f"WAL checkpoint failed: {str(e)}")
        raise


async def get_wal_stats(conn: aiosqlite.Connection) -> dict:
    """
    Get WAL file statistics for monitoring.

    Useful for deciding when to run manual checkpoints.

    Args:
        conn: Database connection

    Returns:
        Dict with WAL statistics:
        - journal_mode: Current journal mode (should be "wal")
        - wal_autocheckpoint: Auto-checkpoint threshold (in pages)
        - page_size: Database page size in bytes

    Example:
        >>> stats = await get_wal_stats(conn)
        >>> if stats['journal_mode'] != 'wal':
        ...     print("WARNING: WAL mode not enabled!")
    """
    try:
        # Get journal mode
        cursor = await conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        journal_mode = row[0] if row else "unknown"

        # Get autocheckpoint setting
        cursor = await conn.execute("PRAGMA wal_autocheckpoint")
        row = await cursor.fetchone()
        autocheckpoint = row[0] if row else -1

        # Get page size
        cursor = await conn.execute("PRAGMA page_size")
        row = await cursor.fetchone()
        page_size = row[0] if row else -1

        return {
            "journal_mode": journal_mode,
            "wal_autocheckpoint": autocheckpoint,
            "page_size": page_size
        }

    except Exception as e:
        logger.error(f"Failed to get WAL stats: {str(e)}")
        raise
