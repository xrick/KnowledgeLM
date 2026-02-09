#!/usr/bin/env python3
"""
DocAI Database Schema Phase 1 Patch
====================================
日期: 2026-01-27
來源: claudedocs/modify_diary/db_schema_fixes_low_risk_2026012714_51.md
風險等級: 🟢 低

用途:
    在 production 機器上修補 skill_metadata.db 的 4 項低風險問題。
    此腳本只修補資料庫。程式碼檔案 (client.py, skills.py) 的修改
    請透過 git pull / deploy 流程同步。

修補項目:
    1. 補齊 skill_chunk_metadata 的 CREATE TABLE + 索引
    2. 清理 skill_document_mapping 中 9 筆孤兒記錄
    3. 修正 skill_metadata 中 1 筆 parent_skill_id 孤兒
    4. 統一 head_id 前綴 (skill_ → head_，六法全書-民法)

使用方式:
    # Dry-run 模式 (預設，只檢查不修改)
    python scripts/patch_db_schema_phase1.py

    # 實際執行
    python scripts/patch_db_schema_phase1.py --apply

    # 指定資料庫路徑
    python scripts/patch_db_schema_phase1.py --apply --db-path /path/to/skill_metadata.db

回滾方式:
    cp <backup_file> data/skill_metadata.db
    備份檔名格式: skill_metadata.db.backup_phase1_<timestamp>
"""

import argparse
import logging
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("patch_phase1")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OLD_HEAD_ID = "skill_20251203_054249_f333015b"
NEW_HEAD_ID = "head_20251203_054249_f333015b"

ORPHAN_MAPPING_IDS = [1, 2, 8, 9, 10, 11, 12, 15, 77]

ORPHAN_PARENT_SKILL_ID = "skill_20251203_071733_2a43e5ac"
ORPHAN_RECORD_SKILL_ID = "skill_20260108_035814_2a43e5ac_8f1f01"


# ---------------------------------------------------------------------------
# Patch Functions
# ---------------------------------------------------------------------------


def patch_1_create_chunk_table(conn: sqlite3.Connection, dry_run: bool) -> dict:
    """補齊 skill_chunk_metadata 的 CREATE TABLE + 2 索引"""
    result = {
        "name": "補齊 skill_chunk_metadata CREATE TABLE",
        "status": "skipped",
        "details": "",
    }

    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_chunk_metadata'"
    )
    table_exists = cursor.fetchone() is not None

    if table_exists:
        cursor.execute("SELECT COUNT(*) FROM skill_chunk_metadata")
        count = cursor.fetchone()[0]
        result["status"] = "already_exists"
        result["details"] = f"表已存在，共 {count} 筆記錄，跳過建立"
        logger.info(f"  [SKIP] skill_chunk_metadata 已存在 ({count} rows)")
        return result

    sql_create = """
        CREATE TABLE IF NOT EXISTS skill_chunk_metadata (
            chunk_id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            document_name TEXT NOT NULL,
            page_number INTEGER,
            chunk_index INTEGER,
            chunk_text TEXT,
            embedding_model TEXT DEFAULT 'BAAI/bge-m3',
            embedding_dimension INTEGER DEFAULT 1024,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (skill_id) REFERENCES skill_metadata(skill_id) ON DELETE CASCADE
        )
    """
    sql_idx1 = """
        CREATE INDEX IF NOT EXISTS idx_chunk_skill_id
        ON skill_chunk_metadata(skill_id)
    """
    sql_idx2 = """
        CREATE INDEX IF NOT EXISTS idx_chunk_document_id
        ON skill_chunk_metadata(document_id)
    """

    if dry_run:
        result["status"] = "dry_run"
        result["details"] = "將建立表 + 2 個索引"
        logger.info("  [DRY-RUN] 將建立 skill_chunk_metadata + 2 indexes")
    else:
        cursor.execute(sql_create)
        cursor.execute(sql_idx1)
        cursor.execute(sql_idx2)
        result["status"] = "applied"
        result["details"] = "已建立表 + 2 個索引"
        logger.info("  [APPLIED] skill_chunk_metadata + 2 indexes 已建立")

    return result


def patch_2_clean_orphan_mappings(conn: sqlite3.Connection, dry_run: bool) -> dict:
    """清理 skill_document_mapping 中 9 筆孤兒記錄"""
    result = {
        "name": "清理 skill_document_mapping 孤兒記錄",
        "status": "skipped",
        "details": "",
    }

    cursor = conn.cursor()

    # 先檢查這些 mapping_id 是否存在
    placeholders = ",".join("?" for _ in ORPHAN_MAPPING_IDS)
    cursor.execute(
        f"SELECT mapping_id FROM skill_document_mapping WHERE mapping_id IN ({placeholders})",
        ORPHAN_MAPPING_IDS,
    )
    found_ids = [row[0] for row in cursor.fetchall()]

    if not found_ids:
        result["status"] = "already_clean"
        result["details"] = "指定的 mapping_id 均不存在，已無需清理"
        logger.info("  [SKIP] 孤兒 mapping_id 均已不存在")
        return result

    # 二次驗證：確認這些記錄確實是孤兒（skill_id 不在 skill_metadata 中）
    actual_orphans = []
    for mid in found_ids:
        cursor.execute(
            """
            SELECT m.mapping_id, m.skill_id
            FROM skill_document_mapping m
            LEFT JOIN skill_metadata sm ON m.skill_id = sm.skill_id
            WHERE m.mapping_id = ? AND sm.skill_id IS NULL
            """,
            (mid,),
        )
        row = cursor.fetchone()
        if row:
            actual_orphans.append(row[0])

    if not actual_orphans:
        result["status"] = "no_orphans"
        result["details"] = (
            f"found_ids={found_ids}，但均非孤兒（有對應 skill_metadata），跳過"
        )
        logger.info(f"  [SKIP] {len(found_ids)} 筆存在但非孤兒，跳過")
        return result

    if dry_run:
        result["status"] = "dry_run"
        result["details"] = f"將刪除 {len(actual_orphans)} 筆孤兒: {actual_orphans}"
        logger.info(f"  [DRY-RUN] 將刪除 {len(actual_orphans)} 筆孤兒 mapping")
    else:
        ph = ",".join("?" for _ in actual_orphans)
        cursor.execute(
            f"DELETE FROM skill_document_mapping WHERE mapping_id IN ({ph})",
            actual_orphans,
        )
        result["status"] = "applied"
        result["details"] = f"已刪除 {cursor.rowcount} 筆孤兒記錄"
        logger.info(f"  [APPLIED] 已刪除 {cursor.rowcount} 筆孤兒 mapping")

    return result


def patch_3_fix_parent_orphan(conn: sqlite3.Connection, dry_run: bool) -> dict:
    """修正 skill_metadata 中 1 筆 parent_skill_id 孤兒"""
    result = {"name": "修正 parent_skill_id 孤兒", "status": "skipped", "details": ""}

    cursor = conn.cursor()
    cursor.execute(
        "SELECT skill_id, parent_skill_id, skill_name FROM skill_metadata WHERE skill_id = ?",
        (ORPHAN_RECORD_SKILL_ID,),
    )
    row = cursor.fetchone()

    if row is None:
        result["status"] = "record_not_found"
        result["details"] = f"skill_id={ORPHAN_RECORD_SKILL_ID} 不存在，跳過"
        logger.info(f"  [SKIP] 目標記錄不存在")
        return result

    current_parent = row[1]
    skill_name = row[2]

    if current_parent != ORPHAN_PARENT_SKILL_ID:
        result["status"] = "already_fixed"
        result["details"] = f"parent_skill_id 已是 '{current_parent}'（非孤兒值），跳過"
        logger.info(f"  [SKIP] parent_skill_id 已修正為 '{current_parent}'")
        return result

    if dry_run:
        result["status"] = "dry_run"
        result["details"] = (
            f"將修正 '{skill_name}' 的 parent_skill_id: "
            f"'{ORPHAN_PARENT_SKILL_ID}' → 'root'"
        )
        logger.info(f"  [DRY-RUN] 將修正 parent_skill_id → 'root'")
    else:
        cursor.execute(
            "UPDATE skill_metadata SET parent_skill_id = 'root' WHERE skill_id = ?",
            (ORPHAN_RECORD_SKILL_ID,),
        )
        result["status"] = "applied"
        result["details"] = f"已修正 '{skill_name}' 的 parent_skill_id → 'root'"
        logger.info(f"  [APPLIED] parent_skill_id → 'root'")

    return result


def patch_4_unify_head_id_prefix(conn: sqlite3.Connection, dry_run: bool) -> dict:
    """統一 head_id 前綴：六法全書-民法 skill_ → head_"""
    result = {
        "name": "統一 head_id 前綴 (六法全書-民法)",
        "status": "skipped",
        "details": "",
    }

    cursor = conn.cursor()

    # 檢查舊 head_id 是否仍存在於 skill_heads
    cursor.execute(
        "SELECT head_id, skill_name FROM skill_heads WHERE head_id = ?",
        (OLD_HEAD_ID,),
    )
    old_row = cursor.fetchone()

    # 檢查新 head_id 是否已存在
    cursor.execute(
        "SELECT head_id, skill_name FROM skill_heads WHERE head_id = ?",
        (NEW_HEAD_ID,),
    )
    new_row = cursor.fetchone()

    if new_row is not None and old_row is None:
        result["status"] = "already_fixed"
        result["details"] = f"'{NEW_HEAD_ID}' 已存在於 skill_heads ({new_row[1]})，跳過"
        logger.info(f"  [SKIP] head_id 前綴已統一")
        return result

    if old_row is None and new_row is None:
        result["status"] = "not_found"
        result["details"] = f"'{OLD_HEAD_ID}' 和 '{NEW_HEAD_ID}' 均不存在，跳過"
        logger.info(f"  [SKIP] 目標 head_id 不存在")
        return result

    if old_row is not None and new_row is not None:
        result["status"] = "conflict"
        result["details"] = f"新舊 head_id 同時存在，需要手動處理"
        logger.warning(f"  [CONFLICT] 新舊 head_id 同時存在!")
        return result

    # old_row exists, new_row does not → proceed with rename
    skill_name = old_row[1]

    # 統計受影響的記錄數
    cursor.execute(
        "SELECT COUNT(*) FROM skill_metadata WHERE head_id = ?", (OLD_HEAD_ID,)
    )
    metadata_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM skill_metadata WHERE parent_skill_id = ?", (OLD_HEAD_ID,)
    )
    parent_count = cursor.fetchone()[0]

    if dry_run:
        result["status"] = "dry_run"
        result["details"] = (
            f"將更新 '{skill_name}' 的 head_id: '{OLD_HEAD_ID}' → '{NEW_HEAD_ID}'\n"
            f"  影響: skill_heads=1, skill_metadata.head_id={metadata_count}, "
            f"skill_metadata.parent_skill_id={parent_count}"
        )
        logger.info(
            f"  [DRY-RUN] head_id 更名: 影響 skill_heads=1, "
            f"metadata.head_id={metadata_count}, metadata.parent_skill_id={parent_count}"
        )
    else:
        # 使用事務確保原子性
        cursor.execute(
            "UPDATE skill_heads SET head_id = ? WHERE head_id = ?",
            (NEW_HEAD_ID, OLD_HEAD_ID),
        )
        heads_updated = cursor.rowcount

        cursor.execute(
            "UPDATE skill_metadata SET head_id = ? WHERE head_id = ?",
            (NEW_HEAD_ID, OLD_HEAD_ID),
        )
        meta_updated = cursor.rowcount

        cursor.execute(
            "UPDATE skill_metadata SET parent_skill_id = ? WHERE parent_skill_id = ?",
            (NEW_HEAD_ID, OLD_HEAD_ID),
        )
        parent_updated = cursor.rowcount

        # processing_jobs 也可能有 head_id 引用
        try:
            cursor.execute(
                "UPDATE processing_jobs SET head_id = ? WHERE head_id = ?",
                (NEW_HEAD_ID, OLD_HEAD_ID),
            )
            jobs_updated = cursor.rowcount
        except sqlite3.OperationalError:
            # processing_jobs 可能沒有 head_id 欄位
            jobs_updated = 0

        result["status"] = "applied"
        result["details"] = (
            f"已更新 '{skill_name}' 的 head_id\n"
            f"  skill_heads: {heads_updated}, skill_metadata.head_id: {meta_updated}, "
            f"skill_metadata.parent_skill_id: {parent_updated}, processing_jobs: {jobs_updated}"
        )
        logger.info(
            f"  [APPLIED] heads={heads_updated}, meta.head_id={meta_updated}, "
            f"meta.parent={parent_updated}, jobs={jobs_updated}"
        )

    return result


# ---------------------------------------------------------------------------
# Post-patch Verification
# ---------------------------------------------------------------------------


def verify_database(conn: sqlite3.Connection) -> list:
    """驗證修補後的資料庫狀態"""
    issues = []
    cursor = conn.cursor()

    # 1. skill_chunk_metadata 存在
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_chunk_metadata'"
    )
    if cursor.fetchone() is None:
        issues.append("skill_chunk_metadata 表不存在")

    # 2. 無孤兒 mapping
    cursor.execute("""
        SELECT COUNT(*)
        FROM skill_document_mapping m
        LEFT JOIN skill_metadata sm ON m.skill_id = sm.skill_id
        WHERE sm.skill_id IS NULL
    """)
    orphan_count = cursor.fetchone()[0]
    if orphan_count > 0:
        issues.append(f"skill_document_mapping 仍有 {orphan_count} 筆孤兒")

    # 3. 無 parent_skill_id 孤兒 (排除 'root' 和指向 skill_heads 的)
    cursor.execute("""
        SELECT COUNT(*)
        FROM skill_metadata sm
        WHERE sm.parent_skill_id != 'root'
        AND sm.parent_skill_id NOT IN (SELECT head_id FROM skill_heads)
        AND sm.parent_skill_id NOT IN (SELECT skill_id FROM skill_metadata)
    """)
    parent_orphan = cursor.fetchone()[0]
    if parent_orphan > 0:
        issues.append(f"skill_metadata 仍有 {parent_orphan} 筆 parent_skill_id 孤兒")

    # 4. head_id 前綴統一
    cursor.execute("SELECT head_id FROM skill_heads WHERE head_id LIKE 'skill_%'")
    bad_prefix = cursor.fetchall()
    if bad_prefix:
        ids = [r[0] for r in bad_prefix]
        issues.append(f"skill_heads 中仍有 skill_ 前綴: {ids}")

    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="DocAI DB Schema Phase 1 Patch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="實際執行修補（預設為 dry-run 模式）",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="skill_metadata.db 路徑（預設: 專案根目錄/data/skill_metadata.db）",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="跳過自動備份（不建議）",
    )
    args = parser.parse_args()

    dry_run = not args.apply

    # Resolve DB path
    if args.db_path:
        db_path = Path(args.db_path)
    else:
        # Try to find project root
        script_dir = Path(__file__).resolve().parent
        project_root = script_dir.parent  # scripts/ → project root
        db_path = project_root / "data" / "skill_metadata.db"

    if not db_path.exists():
        logger.error(f"資料庫不存在: {db_path}")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("DocAI Database Schema Phase 1 Patch")
    logger.info("=" * 60)
    logger.info(f"資料庫路徑: {db_path}")
    logger.info(
        f"模式: {'DRY-RUN (只檢查不修改)' if dry_run else '⚠️  APPLY (實際修改)'}"
    )
    logger.info("")

    # Backup
    if not dry_run and not args.skip_backup:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = db_path.parent / f"{db_path.name}.backup_phase1_{timestamp}"
        shutil.copy2(db_path, backup_path)
        logger.info(f"已備份: {backup_path}")
        logger.info("")

    # Connect
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")  # 避免 FK 約束干擾修補

    results = []

    try:
        # Execute patches
        patches = [
            ("Patch 1/4", patch_1_create_chunk_table),
            ("Patch 2/4", patch_2_clean_orphan_mappings),
            ("Patch 3/4", patch_3_fix_parent_orphan),
            ("Patch 4/4", patch_4_unify_head_id_prefix),
        ]

        for label, patch_fn in patches:
            logger.info(f"[{label}] {patch_fn.__doc__.strip()}")
            r = patch_fn(conn, dry_run)
            results.append(r)
            logger.info("")

        if not dry_run:
            conn.commit()
            logger.info("所有修補已 COMMIT")
        else:
            logger.info("DRY-RUN 模式，未進行任何修改")

        # Verification
        logger.info("")
        logger.info("-" * 60)
        logger.info("驗證結果:")
        issues = verify_database(conn)
        if issues:
            for issue in issues:
                logger.warning(f"  ⚠️  {issue}")
        else:
            logger.info("  ✅ 所有驗證通過")

    except Exception as e:
        logger.error(f"修補失敗: {e}")
        if not dry_run:
            conn.rollback()
            logger.info("已 ROLLBACK")
        raise
    finally:
        conn.close()

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("修補摘要:")
    logger.info("=" * 60)
    for r in results:
        status_icon = {
            "applied": "✅",
            "dry_run": "🔍",
            "already_exists": "⏭️",
            "already_clean": "⏭️",
            "already_fixed": "⏭️",
            "not_found": "⏭️",
            "no_orphans": "⏭️",
            "conflict": "⚠️",
            "record_not_found": "⏭️",
        }.get(r["status"], "❓")
        logger.info(f"  {status_icon} [{r['status']}] {r['name']}")
        if r["details"]:
            for line in r["details"].split("\n"):
                logger.info(f"     {line}")

    if dry_run:
        logger.info("")
        logger.info("💡 這是 DRY-RUN 模式。確認無誤後，請加上 --apply 參數執行：")
        logger.info(f"   python {Path(__file__).name} --apply")

    # Also print code changes reminder
    logger.info("")
    logger.info("-" * 60)
    logger.info("📌 程式碼變更提醒 (需透過 git deploy 同步):")
    logger.info("  1. app/Providers/skill_metadata_provider/client.py")
    logger.info(
        "     → initialize_database() 新增 skill_chunk_metadata CREATE TABLE + 2 索引"
    )
    logger.info("  2. app/api/v1/endpoints/skills.py")
    logger.info(
        "     → delete_skill_by_name() 初始化 skill_head/head_id + 優先用 head_id 查找"
    )
    logger.info("-" * 60)


if __name__ == "__main__":
    main()
