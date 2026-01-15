#!/usr/bin/env python3
"""
FAISS/DB ID Mismatch Repair Tool

此腳本用於修復資料庫 skill_id 與 FAISS 目錄名稱不一致的問題。

問題根源：
- 部分程式碼使用 datetime.now() (本地時間)
- 部分程式碼使用 datetime.now(timezone.utc) (UTC 時間)
- 在 UTC+8 時區環境下產生 8 小時的 timestamp 差異

使用方式：
    # 掃描模式（只檢測不修復）
    python scripts/fix_faiss_db_id_mismatch.py --scan

    # 修復模式（自動修復所有不匹配）
    python scripts/fix_faiss_db_id_mismatch.py --fix

    # 指定資料庫路徑
    python scripts/fix_faiss_db_id_mismatch.py --scan --db-path /path/to/skill_metadata.db

"""

import argparse
import hashlib
import pickle
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import faiss
except ImportError:
    print("警告: faiss 未安裝，部分功能可能受限")
    faiss = None


def get_project_root() -> Path:
    """取得專案根目錄"""
    script_path = Path(__file__).resolve()
    return script_path.parent.parent


def scan_mismatches(
    db_path: str, faiss_base_path: str, verbose: bool = True
) -> List[Dict]:
    """
    掃描資料庫與 FAISS 目錄的不匹配

    Returns:
        List of mismatch records with repair suggestions
    """
    mismatches = []

    db_path = Path(db_path)
    faiss_base = Path(faiss_base_path)

    if not db_path.exists():
        print(f"❌ 資料庫不存在: {db_path}")
        return mismatches

    if not faiss_base.exists():
        print(f"❌ FAISS 目錄不存在: {faiss_base}")
        return mismatches

    # 1. 取得資料庫中所有 skill_id
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT skill_id,
               (SELECT document_name FROM skill_chunk_metadata WHERE skill_id = m.skill_id LIMIT 1) as doc_name,
               (SELECT COUNT(*) FROM skill_chunk_metadata WHERE skill_id = m.skill_id) as chunk_count
        FROM skill_metadata m
    """)
    db_skills = {
        row[0]: {"doc_name": row[1], "chunk_count": row[2]} for row in cursor.fetchall()
    }

    # 2. 取得 FAISS 目錄中所有 skill_id
    faiss_skills = {}
    for faiss_dir in faiss_base.iterdir():
        if faiss_dir.is_dir() and faiss_dir.name.startswith("skill_"):
            pkl_path = faiss_dir / "index.pkl"
            faiss_path = faiss_dir / "index.faiss"

            if pkl_path.exists() and faiss_path.exists():
                # 讀取 pkl 取得 metadata
                try:
                    with open(pkl_path, "rb") as f:
                        pkl_data = pickle.load(f)

                    if isinstance(pkl_data, tuple) and len(pkl_data) >= 2:
                        docstore = pkl_data[0]
                        if hasattr(docstore, "_dict"):
                            docs = list(docstore._dict.values())
                            if docs:
                                doc_name = docs[0].metadata.get(
                                    "document_name", "Unknown"
                                )
                                vector_count = len(docs)

                                # 讀取 FAISS index 確認向量數
                                if faiss:
                                    index = faiss.read_index(str(faiss_path))
                                    vector_count = index.ntotal

                                faiss_skills[faiss_dir.name] = {
                                    "doc_name": doc_name,
                                    "vector_count": vector_count,
                                    "path": faiss_dir,
                                }
                except Exception as e:
                    if verbose:
                        print(f"⚠️ 無法讀取 {faiss_dir.name}: {e}")

    if verbose:
        print(f"\n📊 掃描結果:")
        print(f"   資料庫 skill 數量: {len(db_skills)}")
        print(f"   FAISS 目錄數量: {len(faiss_skills)}")

    # 3. 比對並找出不匹配
    for db_skill_id, db_info in db_skills.items():
        if db_skill_id in faiss_skills:
            # 完全匹配
            continue

        # 嘗試找到對應的 FAISS（根據 hash 後綴匹配）
        # skill_id 格式: skill_{timestamp}_{name_hash}_{file_hash}
        parts = db_skill_id.split("_")
        if len(parts) >= 4:
            hash_suffix = "_".join(parts[3:])  # name_hash_file_hash

            # 尋找具有相同 hash 後綴的 FAISS 目錄
            matching_faiss = None
            for faiss_id, faiss_info in faiss_skills.items():
                faiss_parts = faiss_id.split("_")
                if len(faiss_parts) >= 4:
                    faiss_hash_suffix = "_".join(faiss_parts[3:])
                    if faiss_hash_suffix == hash_suffix:
                        # 進一步驗證 document_name
                        if faiss_info["doc_name"] == db_info["doc_name"]:
                            matching_faiss = faiss_id
                            break

            if matching_faiss:
                mismatch = {
                    "db_skill_id": db_skill_id,
                    "faiss_skill_id": matching_faiss,
                    "doc_name": db_info["doc_name"],
                    "db_chunks": db_info["chunk_count"],
                    "faiss_vectors": faiss_skills[matching_faiss]["vector_count"],
                    "hash_suffix": hash_suffix,
                    "status": "mismatch_found",
                }
                mismatches.append(mismatch)

                if verbose:
                    print(f"\n🔍 發現不匹配:")
                    print(f"   資料庫: {db_skill_id}")
                    print(f"   FAISS:  {matching_faiss}")
                    print(f"   文件:   {db_info['doc_name']}")
                    print(
                        f"   數量:   DB={db_info['chunk_count']}, FAISS={faiss_skills[matching_faiss]['vector_count']}"
                    )
            else:
                # 沒有找到匹配的 FAISS
                mismatch = {
                    "db_skill_id": db_skill_id,
                    "faiss_skill_id": None,
                    "doc_name": db_info["doc_name"],
                    "db_chunks": db_info["chunk_count"],
                    "faiss_vectors": 0,
                    "status": "faiss_missing",
                }
                mismatches.append(mismatch)

                if verbose:
                    print(f"\n⚠️ FAISS 目錄缺失:")
                    print(f"   資料庫: {db_skill_id}")
                    print(f"   文件:   {db_info['doc_name']}")

    # 4. 檢查孤立的 FAISS 目錄
    for faiss_id, faiss_info in faiss_skills.items():
        if faiss_id not in db_skills:
            # 檢查是否已經被映射
            already_mapped = any(
                m.get("faiss_skill_id") == faiss_id for m in mismatches
            )
            if not already_mapped:
                mismatch = {
                    "db_skill_id": None,
                    "faiss_skill_id": faiss_id,
                    "doc_name": faiss_info["doc_name"],
                    "db_chunks": 0,
                    "faiss_vectors": faiss_info["vector_count"],
                    "status": "db_missing",
                }
                mismatches.append(mismatch)

                if verbose:
                    print(f"\n⚠️ 資料庫記錄缺失:")
                    print(f"   FAISS:  {faiss_id}")
                    print(f"   文件:   {faiss_info['doc_name']}")

    conn.close()
    return mismatches


def verify_content_match(
    db_path: str,
    faiss_base_path: str,
    db_skill_id: str,
    faiss_skill_id: str,
    sample_pages: List[int] = [1, 10, 50, 100],
) -> Tuple[bool, str]:
    """
    驗證資料庫與 FAISS 的內容是否一致

    Returns:
        (is_match, message)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 讀取 FAISS pkl
    pkl_path = Path(faiss_base_path) / faiss_skill_id / "index.pkl"
    with open(pkl_path, "rb") as f:
        pkl_data = pickle.load(f)

    docstore = pkl_data[0]
    faiss_docs = {
        doc.metadata.get("page_number"): doc for doc in docstore._dict.values()
    }

    mismatched_pages = []

    for page_num in sample_pages:
        cursor.execute(
            """
            SELECT chunk_text FROM skill_chunk_metadata
            WHERE skill_id = ? AND page_number = ?
        """,
            (db_skill_id, page_num),
        )
        result = cursor.fetchone()

        if result and page_num in faiss_docs:
            db_text = result[0][:500] if result[0] else ""
            faiss_text = faiss_docs[page_num].page_content[:500]

            if db_text.strip() != faiss_text.strip():
                mismatched_pages.append(page_num)

    conn.close()

    if mismatched_pages:
        return False, f"內容不匹配於頁面: {mismatched_pages}"
    return True, "內容驗證通過"


def fix_mismatch(
    db_path: str, old_skill_id: str, new_skill_id: str, dry_run: bool = False
) -> bool:
    """
    修復單一 skill_id 不匹配

    Args:
        db_path: 資料庫路徑
        old_skill_id: 資料庫中的舊 skill_id
        new_skill_id: FAISS 目錄的 skill_id（目標）
        dry_run: 只顯示將執行的操作，不實際修改

    Returns:
        True if successful
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if dry_run:
        print(f"\n🔄 [DRY RUN] 將修復: {old_skill_id} → {new_skill_id}")

        # 顯示將影響的記錄數
        tables = [
            ("skill_metadata", "skill_id"),
            ("skill_chunk_metadata", "skill_id"),
            ("skill_document_mapping", "skill_id"),
            ("skill_overviews", "skill_id"),
        ]

        for table, column in tables:
            cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (old_skill_id,)
            )
            count = cursor.fetchone()[0]
            print(f"   {table}: {count} rows")

        cursor.execute(
            f"SELECT COUNT(*) FROM skill_chunk_metadata WHERE chunk_id LIKE ?",
            (f"{old_skill_id}%",),
        )
        count = cursor.fetchone()[0]
        print(f"   chunk_id updates: {count} rows")

        conn.close()
        return True

    try:
        conn.execute("BEGIN TRANSACTION")

        # 1. 更新 skill_metadata
        cursor.execute(
            """
            UPDATE skill_metadata SET skill_id = ? WHERE skill_id = ?
        """,
            (new_skill_id, old_skill_id),
        )
        r1 = cursor.rowcount

        # 2. 更新 skill_chunk_metadata 的 skill_id
        cursor.execute(
            """
            UPDATE skill_chunk_metadata SET skill_id = ? WHERE skill_id = ?
        """,
            (new_skill_id, old_skill_id),
        )
        r2 = cursor.rowcount

        # 3. 更新 skill_chunk_metadata 的 chunk_id
        cursor.execute(
            """
            UPDATE skill_chunk_metadata
            SET chunk_id = REPLACE(chunk_id, ?, ?)
            WHERE chunk_id LIKE ?
        """,
            (old_skill_id, new_skill_id, f"{old_skill_id}%"),
        )
        r3 = cursor.rowcount

        # 4. 更新 skill_document_mapping
        cursor.execute(
            """
            UPDATE skill_document_mapping SET skill_id = ? WHERE skill_id = ?
        """,
            (new_skill_id, old_skill_id),
        )
        r4 = cursor.rowcount

        # 5. 更新 skill_overviews
        cursor.execute(
            """
            UPDATE skill_overviews SET skill_id = ? WHERE skill_id = ?
        """,
            (new_skill_id, old_skill_id),
        )
        r5 = cursor.rowcount

        conn.commit()

        print(f"✅ 修復完成: {old_skill_id} → {new_skill_id}")
        print(
            f"   skill_metadata: {r1}, skill_chunk_metadata: {r2}+{r3}, "
            f"skill_document_mapping: {r4}, skill_overviews: {r5}"
        )

        return True

    except Exception as e:
        conn.rollback()
        print(f"❌ 修復失敗: {e}")
        return False

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="FAISS/DB ID Mismatch Repair Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
    # 掃描模式
    python fix_faiss_db_id_mismatch.py --scan

    # 修復模式（會自動備份）
    python fix_faiss_db_id_mismatch.py --fix

    # 只顯示將執行的操作
    python fix_faiss_db_id_mismatch.py --fix --dry-run

    # 指定路徑
    python fix_faiss_db_id_mismatch.py --scan \\
        --db-path /data/skill_metadata.db \\
        --faiss-path /data/faiss_indices/skills
        """,
    )

    parser.add_argument("--scan", action="store_true", help="掃描模式：只檢測不修復")
    parser.add_argument(
        "--fix", action="store_true", help="修復模式：自動修復所有不匹配"
    )
    parser.add_argument("--dry-run", action="store_true", help="只顯示將執行的操作")
    parser.add_argument("--no-backup", action="store_true", help="不建立備份（不建議）")
    parser.add_argument("--db-path", type=str, help="資料庫路徑")
    parser.add_argument("--faiss-path", type=str, help="FAISS 基礎目錄路徑")
    parser.add_argument(
        "--skip-verify", action="store_true", help="跳過內容驗證（加快速度）"
    )

    args = parser.parse_args()

    if not args.scan and not args.fix:
        parser.print_help()
        print("\n❌ 請指定 --scan 或 --fix")
        sys.exit(1)

    # 設定路徑
    project_root = get_project_root()
    db_path = args.db_path or str(project_root / "data" / "skill_metadata.db")
    faiss_path = args.faiss_path or str(
        project_root / "data" / "faiss_indices" / "skills"
    )

    print("=" * 70)
    print("FAISS/DB ID Mismatch Repair Tool")
    print("=" * 70)
    print(f"資料庫路徑: {db_path}")
    print(f"FAISS 路徑: {faiss_path}")
    print(f"模式: {'掃描' if args.scan else '修復'}")
    if args.fix:
        print(f"Dry Run: {'是' if args.dry_run else '否'}")
    print("=" * 70)

    # 掃描不匹配
    mismatches = scan_mismatches(db_path, faiss_path, verbose=True)

    # 統計
    mismatch_found = [m for m in mismatches if m["status"] == "mismatch_found"]
    faiss_missing = [m for m in mismatches if m["status"] == "faiss_missing"]
    db_missing = [m for m in mismatches if m["status"] == "db_missing"]

    print(f"\n📊 摘要:")
    print(f"   可修復的不匹配: {len(mismatch_found)}")
    print(f"   FAISS 缺失: {len(faiss_missing)}")
    print(f"   資料庫缺失: {len(db_missing)}")

    if args.scan:
        if not mismatches:
            print("\n✅ 沒有發現不匹配")
        return

    # 修復模式
    if not mismatch_found:
        print("\n✅ 沒有需要修復的不匹配")
        return

    # 備份
    if not args.no_backup and not args.dry_run:
        backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(db_path, backup_path)
        print(f"\n📦 備份完成: {backup_path}")

    # 執行修復
    success_count = 0
    fail_count = 0

    for mismatch in mismatch_found:
        old_id = mismatch["db_skill_id"]
        new_id = mismatch["faiss_skill_id"]

        # 內容驗證
        if not args.skip_verify and not args.dry_run:
            is_match, msg = verify_content_match(db_path, faiss_path, old_id, new_id)
            if not is_match:
                print(f"⚠️ 跳過 {old_id}: {msg}")
                continue

        # 修復
        if fix_mismatch(db_path, old_id, new_id, dry_run=args.dry_run):
            success_count += 1
        else:
            fail_count += 1

    print(f"\n📊 修復結果:")
    print(f"   成功: {success_count}")
    print(f"   失敗: {fail_count}")

    if success_count > 0 and not args.dry_run:
        print("\n✅ 修復完成！建議執行 --scan 確認結果")


if __name__ == "__main__":
    main()
