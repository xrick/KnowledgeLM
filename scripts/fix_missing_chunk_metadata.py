#!/usr/bin/env python3
"""
Fix missing chunk metadata for existing skills.

This script reads the PDF file, extracts text by page, and inserts
chunk metadata into skill_chunk_metadata table.
"""

import sqlite3
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import PyPDF2

def fix_skill_chunks(skill_id: str, pdf_path: str, db_path: str = "data/skill_metadata.db"):
    """Fix missing chunk metadata for a skill."""

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"❌ PDF file not found: {pdf_path}")
        return False

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check current chunk count
    cursor.execute("SELECT COUNT(*) FROM skill_chunk_metadata WHERE skill_id = ?", (skill_id,))
    existing_count = cursor.fetchone()[0]
    print(f"📊 Existing chunks: {existing_count}")

    if existing_count > 0:
        print(f"⚠️  Skill already has {existing_count} chunks. Deleting and re-inserting...")
        cursor.execute("DELETE FROM skill_chunk_metadata WHERE skill_id = ?", (skill_id,))

    # Extract text from PDF
    print(f"📖 Reading PDF: {pdf_path}")
    with open(pdf_path, 'rb') as f:
        pdf_reader = PyPDF2.PdfReader(f)
        total_pages = len(pdf_reader.pages)
        print(f"📄 Total pages: {total_pages}")

        # Insert chunks
        doc_id = skill_id.split('_')[-1][:6]  # Get last part of skill_id

        for page_num, page in enumerate(pdf_reader.pages, 1):
            text = page.extract_text() or ""
            chunk_index = page_num - 1
            chunk_id = f"{skill_id}_{doc_id}_p{page_num}"

            chunk_metadata = {
                'chunk_id': chunk_id,
                'skill_id': skill_id,
                'document_id': doc_id,
                'document_name': pdf_file.stem,
                'page_number': page_num,
                'chunk_index': chunk_index,
                'embedding_model': 'BAAI/bge-m3',
                'embedding_dimension': 1024
            }

            cursor.execute("""
                INSERT OR REPLACE INTO skill_chunk_metadata
                (chunk_id, skill_id, document_id, document_name, page_number,
                 chunk_index, chunk_text, embedding_model, embedding_dimension, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk_id,
                skill_id,
                doc_id,
                pdf_file.stem,
                page_num,
                chunk_index,
                text[:2000],  # Store first 2000 chars
                'BAAI/bge-m3',
                1024,
                json.dumps(chunk_metadata)
            ))

            if page_num % 50 == 0:
                print(f"  ✅ Inserted {page_num}/{total_pages} chunks...")

    conn.commit()

    # Verify
    cursor.execute("SELECT COUNT(*) FROM skill_chunk_metadata WHERE skill_id = ?", (skill_id,))
    new_count = cursor.fetchone()[0]

    conn.close()

    print(f"✅ Done! Inserted {new_count} chunks for skill {skill_id}")
    return True


if __name__ == "__main__":
    # Fix the Build_a_Large_Language_Model book
    skill_id = "skill_20251212_053934_2a43e5ac_9ed582"
    pdf_path = "uploadfiles/pdf/Build_a_Large_Language_Model_From_Scratch_manning_2024.pdf"

    print("=" * 60)
    print("🔧 Fixing missing chunk metadata")
    print("=" * 60)
    print(f"Skill ID: {skill_id}")
    print(f"PDF Path: {pdf_path}")
    print("=" * 60)

    success = fix_skill_chunks(skill_id, pdf_path)

    if success:
        print("\n✅ Fix completed successfully!")
        print("Now you can query the book with: 什麼是大語言模型")
    else:
        print("\n❌ Fix failed!")
