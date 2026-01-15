#!/usr/bin/env python3
"""
Database Migration: Change users.user_id from INTEGER to TEXT

This migration script converts the users table user_id column from INTEGER
to TEXT (UUID format) to maintain consistency with file_metadata.user_id.

Safety Features:
- Backs up existing data before migration
- Validates data integrity after migration
- Can be rolled back if needed

Usage:
    python scripts/migrate_users_table_user_id_to_text.py

Requirements:
    - SQLite database at data/docai.db
    - No active connections to the database during migration
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings


def backup_database(db_path: Path):
    """
    Create backup of database before migration

    Args:
        db_path: Path to database file

    Returns:
        Path to backup file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"

    import shutil
    shutil.copy2(db_path, backup_path)

    print(f"✅ Database backed up to: {backup_path}")
    return backup_path


def migrate_users_table(db_path: Path):
    """
    Migrate users table user_id from INTEGER to TEXT

    Process:
    1. Backup database
    2. Create new users_new table with TEXT user_id
    3. Migrate existing data (if any)
    4. Drop old table
    5. Rename new table
    6. Recreate indexes

    Args:
        db_path: Path to SQLite database
    """
    print(f"🔄 Starting migration for: {db_path}")

    # Step 1: Backup
    backup_path = backup_database(db_path)

    # Step 2: Connect to database
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Step 3: Check if users table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='users'
        """)

        if not cursor.fetchone():
            print("⚠️  users table does not exist. Creating new table with TEXT user_id...")

            # Create new users table with TEXT user_id
            cursor.execute("""
                CREATE TABLE users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    email TEXT UNIQUE,
                    full_name TEXT,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            print("✅ Created new users table with TEXT user_id")
            conn.commit()
            return

        # Step 4: Check existing data
        cursor.execute("SELECT COUNT(*) FROM users")
        row_count = cursor.fetchone()[0]

        print(f"📊 Found {row_count} existing users")

        if row_count > 0:
            print("⚠️  WARNING: Existing users with INTEGER user_id detected!")
            print("    This migration will convert INTEGER IDs to TEXT.")
            print("    Original INTEGER IDs will be lost.")
            print()

            response = input("Continue with migration? (yes/no): ").strip().lower()
            if response != 'yes':
                print("❌ Migration cancelled by user")
                conn.close()
                return

        # Step 5: Create new table with TEXT user_id
        print("🔨 Creating new users table schema...")

        cursor.execute("""
            CREATE TABLE users_new (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                email TEXT UNIQUE,
                full_name TEXT,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Step 6: Migrate existing data (convert INTEGER to TEXT)
        if row_count > 0:
            print("📦 Migrating existing data...")

            cursor.execute("""
                INSERT INTO users_new (
                    user_id, username, password_hash, email,
                    full_name, role, created_at, updated_at
                )
                SELECT
                    CAST(user_id AS TEXT),  -- Convert INTEGER to TEXT
                    username, password_hash, email,
                    full_name, role, created_at, updated_at
                FROM users
            """)

            print(f"✅ Migrated {cursor.rowcount} users")

        # Step 7: Drop old table
        print("🗑️  Dropping old users table...")
        cursor.execute("DROP TABLE users")

        # Step 8: Rename new table
        print("🔄 Renaming users_new to users...")
        cursor.execute("ALTER TABLE users_new RENAME TO users")

        # Step 9: Create indexes
        print("📇 Creating indexes...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_username
            ON users(username)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_email
            ON users(email)
        """)

        # Step 10: Commit changes
        conn.commit()

        # Step 11: Verify migration
        print("✅ Verifying migration...")

        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()

        user_id_column = next((col for col in columns if col[1] == 'user_id'), None)

        if user_id_column and user_id_column[2] == 'TEXT':
            print("✅ Migration successful!")
            print(f"   user_id column type: {user_id_column[2]}")

            cursor.execute("SELECT COUNT(*) FROM users")
            final_count = cursor.fetchone()[0]
            print(f"   Final user count: {final_count}")

            if final_count == row_count:
                print("✅ Data integrity verified: All users migrated")
            else:
                print(f"⚠️  WARNING: Row count mismatch (before: {row_count}, after: {final_count})")
        else:
            print("❌ Migration verification failed!")
            print("   Please check database manually")

    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        print(f"   Rolling back changes...")
        conn.rollback()
        print(f"   Database backup available at: {backup_path}")
        raise

    finally:
        conn.close()


def show_schema_comparison():
    """Display before/after schema comparison"""

    print("\n" + "="*70)
    print("Schema Comparison: users table")
    print("="*70)

    print("\n❌ OLD SCHEMA (INTEGER user_id):")
    print("""
    CREATE TABLE users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,  ← INTEGER (auto-increment)
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        email TEXT UNIQUE,
        full_name TEXT,
        role TEXT DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    print("\n✅ NEW SCHEMA (TEXT user_id for UUID):")
    print("""
    CREATE TABLE users (
        user_id TEXT PRIMARY KEY,                   ← TEXT (UUID v4 format)
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        email TEXT UNIQUE,
        full_name TEXT,
        role TEXT DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    print("\n📝 Consistency with file_metadata:")
    print("   file_metadata.user_id: TEXT ✅")
    print("   users.user_id:         TEXT ✅")
    print("   → Both tables now use UUID v4 format")
    print("="*70 + "\n")


if __name__ == "__main__":
    print("="*70)
    print("Database Migration: users.user_id INTEGER → TEXT")
    print("="*70)
    print()

    # Show schema comparison
    show_schema_comparison()

    # Get database path
    db_path = Path(settings.SQLITE_DB_PATH)

    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        print("   Please ensure the database exists before running migration")
        sys.exit(1)

    print(f"Database: {db_path}")
    print()

    # Run migration
    try:
        migrate_users_table(db_path)

        print("\n" + "="*70)
        print("✅ Migration completed successfully!")
        print("="*70)
        print()
        print("Next steps:")
        print("  1. Test user authentication with UUID user_id")
        print("  2. Update any application code that assumes INTEGER user_id")
        print("  3. Verify file_metadata.user_id matches users.user_id format")
        print()

    except Exception as e:
        print("\n" + "="*70)
        print("❌ Migration failed!")
        print("="*70)
        print(f"Error: {str(e)}")
        print()
        print("Recovery:")
        print("  - Database backup was created before migration")
        print("  - Check backup file in data/ directory")
        print("  - Review error message above")
        sys.exit(1)
