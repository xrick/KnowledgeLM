#!/usr/bin/env python3
"""
Skill Export/Import Automated Test Suite
Smoke Test (Phase 1): Test-01, Test-02, Test-05
"""

import os
import sys
import time
import json
import sqlite3
import requests
import tempfile
import zipfile
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple

# Configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"
TEST_RESULTS_DIR = Path("claudedocs/exportimportdocs/test_results")
TEST_DOCS_DIR = Path("claudedocs/exportimportdocs/test_docs")
DB_PATH = Path("data/skill_metadata.db")

# Ensure directories exist
TEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
TEST_DOCS_DIR.mkdir(parents=True, exist_ok=True)

class TestResult:
    """Test result container"""
    def __init__(self, test_id: str, test_name: str):
        self.test_id = test_id
        self.test_name = test_name
        self.status = "PENDING"
        self.start_time = None
        self.end_time = None
        self.steps = []
        self.errors = []
        self.data = {}

    def start(self):
        self.start_time = datetime.now()
        self.status = "RUNNING"

    def add_step(self, step: str, result: str, details: str = ""):
        self.steps.append({
            "step": step,
            "result": result,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def add_error(self, error: str):
        self.errors.append(error)

    def complete(self, status: str):
        self.end_time = datetime.now()
        self.status = status
        self.data["duration_seconds"] = (self.end_time - self.start_time).total_seconds()

    def to_dict(self) -> Dict:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "status": self.status,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.data.get("duration_seconds", 0),
            "steps": self.steps,
            "errors": self.errors,
            "data": self.data
        }


def wait_for_service(max_wait=30) -> bool:
    """Wait for DocAI service to be ready"""
    print(f"⏳ Waiting for service to start (max {max_wait}s)...")

    for i in range(max_wait):
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=2)
            if response.status_code == 200:
                print(f"✅ Service ready after {i+1}s")
                return True
        except Exception:
            pass
        time.sleep(1)

    print(f"❌ Service not ready after {max_wait}s")
    return False


def get_available_skills() -> List[Dict]:
    """Get list of available skills for testing"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT h.head_id, h.skill_name,
               COUNT(m.skill_id) as doc_count,
               SUM(m.total_chunks) as total_chunks
        FROM skill_heads h
        LEFT JOIN skill_metadata m ON h.head_id = m.head_id
        GROUP BY h.head_id
        HAVING doc_count > 0
        ORDER BY total_chunks ASC
    """)

    skills = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return skills


def calculate_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def verify_zip_structure(zip_path: Path) -> Tuple[bool, List[str]]:
    """Verify ZIP file structure"""
    required_files = [
        "manifest.json",
        "skill_heads.csv",
        "skill_metadata.csv",
        "skill_chunk_metadata.csv",
        "skill_document_mapping.csv",
        "skill_overviews.csv",
        "index.faiss",
        "index.pkl"
    ]

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zip_files = zf.namelist()

            # Check for skill folder
            if not zip_files:
                return False, ["ZIP file is empty"]

            # Get skill folder name (first directory in ZIP)
            skill_folder = zip_files[0].split('/')[0]

            missing_files = []
            for required in required_files:
                expected_path = f"{skill_folder}/{required}"
                if expected_path not in zip_files:
                    missing_files.append(required)

            if missing_files:
                return False, [f"Missing files: {', '.join(missing_files)}"]

            return True, []

    except Exception as e:
        return False, [f"ZIP verification error: {str(e)}"]


def compare_databases(source_head_id: str, imported_head_id: str) -> Dict[str, Any]:
    """Compare source and imported database records"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    comparison = {
        "match": True,
        "details": {}
    }

    # Compare document counts
    source_docs = conn.execute(
        "SELECT COUNT(*) FROM skill_metadata WHERE head_id = ?",
        (source_head_id,)
    ).fetchone()[0]

    imported_docs = conn.execute(
        "SELECT COUNT(*) FROM skill_metadata WHERE head_id = ?",
        (imported_head_id,)
    ).fetchone()[0]

    comparison["details"]["document_count"] = {
        "source": source_docs,
        "imported": imported_docs,
        "match": source_docs == imported_docs
    }

    if source_docs != imported_docs:
        comparison["match"] = False

    # Compare chunk counts
    source_chunks = conn.execute("""
        SELECT COUNT(*) FROM skill_chunk_metadata
        WHERE skill_id IN (SELECT skill_id FROM skill_metadata WHERE head_id = ?)
    """, (source_head_id,)).fetchone()[0]

    imported_chunks = conn.execute("""
        SELECT COUNT(*) FROM skill_chunk_metadata
        WHERE skill_id IN (SELECT skill_id FROM skill_metadata WHERE head_id = ?)
    """, (imported_head_id,)).fetchone()[0]

    comparison["details"]["chunk_count"] = {
        "source": source_chunks,
        "imported": imported_chunks,
        "match": source_chunks == imported_chunks
    }

    if source_chunks != imported_chunks:
        comparison["match"] = False

    # Sample chunk text comparison (first 10 chunks)
    source_texts = conn.execute("""
        SELECT chunk_text FROM skill_chunk_metadata
        WHERE skill_id IN (SELECT skill_id FROM skill_metadata WHERE head_id = ?)
        ORDER BY chunk_index
        LIMIT 10
    """, (source_head_id,)).fetchall()

    imported_texts = conn.execute("""
        SELECT chunk_text FROM skill_chunk_metadata
        WHERE skill_id IN (SELECT skill_id FROM skill_metadata WHERE head_id = ?)
        ORDER BY chunk_index
        LIMIT 10
    """, (imported_head_id,)).fetchall()

    matching_texts = sum(1 for s, t in zip(source_texts, imported_texts) if s[0] == t[0])

    comparison["details"]["chunk_text_sample"] = {
        "sampled": len(source_texts),
        "matching": matching_texts,
        "match_percentage": (matching_texts / len(source_texts) * 100) if source_texts else 0
    }

    if matching_texts < len(source_texts):
        comparison["match"] = False

    conn.close()

    return comparison


# =========================================================================
# Test-01: Export Single Document Skill
# =========================================================================

def test_01_export_single_skill() -> TestResult:
    """Test-01: Export a single-document Skill"""
    result = TestResult("TEST-01", "Export Single Document Skill")
    result.start()

    try:
        # Step 1: Select test skill
        skills = get_available_skills()
        test_skill = next((s for s in skills if s['doc_count'] == 1), None)

        if not test_skill:
            result.add_error("No single-document skill found for testing")
            result.complete("FAILED")
            return result

        head_id = test_skill['head_id']
        skill_name = test_skill['skill_name']

        result.add_step(
            "Select test skill",
            "SUCCESS",
            f"Selected: {skill_name} (head_id: {head_id}, chunks: {test_skill['total_chunks']})"
        )
        result.data["head_id"] = head_id
        result.data["skill_name"] = skill_name
        result.data["total_chunks"] = test_skill['total_chunks']

        # Step 2: Call export API
        export_url = f"{API_BASE}/config/skills/export/{head_id}"

        result.add_step("Call export API", "IN_PROGRESS", f"URL: {export_url}")

        response = requests.get(export_url, timeout=120, stream=True)

        if response.status_code != 200:
            result.add_error(f"Export API failed: HTTP {response.status_code}")
            result.add_step("Call export API", "FAILED", f"HTTP {response.status_code}")
            result.complete("FAILED")
            return result

        result.add_step("Call export API", "SUCCESS", f"HTTP {response.status_code}")

        # Step 3: Save ZIP file
        export_file = TEST_RESULTS_DIR / f"test01_export_{head_id}.zip"

        with open(export_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        file_size_mb = export_file.stat().st_size / 1024 / 1024

        result.add_step(
            "Save ZIP file",
            "SUCCESS",
            f"Saved: {export_file.name} ({file_size_mb:.2f} MB)"
        )
        result.data["export_file"] = str(export_file)
        result.data["file_size_mb"] = file_size_mb

        # Step 4: Verify ZIP structure
        is_valid, errors = verify_zip_structure(export_file)

        if not is_valid:
            result.add_error(f"ZIP structure invalid: {', '.join(errors)}")
            result.add_step("Verify ZIP structure", "FAILED", str(errors))
            result.complete("FAILED")
            return result

        result.add_step("Verify ZIP structure", "SUCCESS", "All required files present")

        # Step 5: Calculate checksum
        checksum = calculate_checksum(export_file)
        result.add_step("Calculate checksum", "SUCCESS", f"SHA256: {checksum[:16]}...")
        result.data["checksum"] = checksum

        result.complete("PASSED")

    except Exception as e:
        result.add_error(f"Unexpected error: {str(e)}")
        result.complete("FAILED")

    return result


# =========================================================================
# Test-02: Import Single Document Skill
# =========================================================================

def test_02_import_single_skill(export_file: Path) -> TestResult:
    """Test-02: Import a single-document Skill"""
    result = TestResult("TEST-02", "Import Single Document Skill")
    result.start()

    try:
        # Step 1: Verify export file exists
        if not export_file.exists():
            result.add_error(f"Export file not found: {export_file}")
            result.complete("FAILED")
            return result

        result.add_step("Verify export file", "SUCCESS", f"File: {export_file.name}")
        result.data["export_file"] = str(export_file)

        # Step 2: Call import API
        import_url = f"{API_BASE}/config/skills/import"

        result.add_step("Call import API", "IN_PROGRESS", f"URL: {import_url}")

        with open(export_file, 'rb') as f:
            files = {'file': (export_file.name, f, 'application/zip')}
            response = requests.post(import_url, files=files, timeout=180)

        if response.status_code != 200:
            result.add_error(f"Import API failed: HTTP {response.status_code}")
            try:
                error_detail = response.json()
                result.add_step("Call import API", "FAILED", json.dumps(error_detail, indent=2))
            except:
                result.add_step("Call import API", "FAILED", response.text)
            result.complete("FAILED")
            return result

        import_response = response.json()
        result.add_step("Call import API", "SUCCESS", json.dumps(import_response, indent=2))

        # Step 3: Extract imported skill info
        new_head_id = import_response.get("new_head_id")
        skill_name = import_response.get("skill_name")

        if not new_head_id:
            result.add_error("new_head_id not found in response")
            result.complete("FAILED")
            return result

        result.add_step(
            "Extract imported info",
            "SUCCESS",
            f"new_head_id: {new_head_id}, skill_name: {skill_name}"
        )
        result.data["new_head_id"] = new_head_id
        result.data["skill_name"] = skill_name
        result.data["import_response"] = import_response

        # Step 4: Verify imported skill in database
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        head_row = conn.execute(
            "SELECT * FROM skill_heads WHERE head_id = ?",
            (new_head_id,)
        ).fetchone()

        if not head_row:
            result.add_error(f"Imported skill head not found in database: {new_head_id}")
            result.add_step("Verify in database", "FAILED", "Skill head not found")
            conn.close()
            result.complete("FAILED")
            return result

        doc_count = conn.execute(
            "SELECT COUNT(*) FROM skill_metadata WHERE head_id = ?",
            (new_head_id,)
        ).fetchone()[0]

        chunk_count = conn.execute("""
            SELECT COUNT(*) FROM skill_chunk_metadata
            WHERE skill_id IN (SELECT skill_id FROM skill_metadata WHERE head_id = ?)
        """, (new_head_id,)).fetchone()[0]

        conn.close()

        result.add_step(
            "Verify in database",
            "SUCCESS",
            f"Found: {doc_count} documents, {chunk_count} chunks"
        )
        result.data["imported_doc_count"] = doc_count
        result.data["imported_chunk_count"] = chunk_count

        # Step 5: Verify FAISS index
        faiss_base_dir = Path("data/faiss_indices/skills")

        # Get skill_ids for imported skill
        conn = sqlite3.connect(str(DB_PATH))
        skill_ids = conn.execute(
            "SELECT skill_id FROM skill_metadata WHERE head_id = ?",
            (new_head_id,)
        ).fetchall()
        conn.close()

        faiss_found = 0
        for (skill_id,) in skill_ids:
            faiss_dir = faiss_base_dir / skill_id
            if (faiss_dir / "index.faiss").exists() and (faiss_dir / "index.pkl").exists():
                faiss_found += 1

        if faiss_found == 0:
            result.add_error("No FAISS indices found for imported skill")
            result.add_step("Verify FAISS index", "FAILED", "No indices found")
            result.complete("FAILED")
            return result

        result.add_step(
            "Verify FAISS index",
            "SUCCESS",
            f"Found {faiss_found} FAISS indices"
        )
        result.data["faiss_indices_count"] = faiss_found

        result.complete("PASSED")

    except Exception as e:
        result.add_error(f"Unexpected error: {str(e)}")
        result.complete("FAILED")

    return result


# =========================================================================
# Test-05: Round-trip Verification
# =========================================================================

def test_05_roundtrip_verification(source_head_id: str, imported_head_id: str) -> TestResult:
    """Test-05: Verify Export → Import data consistency"""
    result = TestResult("TEST-05", "Round-trip Verification")
    result.start()

    try:
        result.data["source_head_id"] = source_head_id
        result.data["imported_head_id"] = imported_head_id

        # Step 1: Compare database records
        result.add_step("Compare database", "IN_PROGRESS", "Comparing records...")

        comparison = compare_databases(source_head_id, imported_head_id)

        if comparison["match"]:
            result.add_step("Compare database", "SUCCESS", json.dumps(comparison["details"], indent=2))
        else:
            result.add_step("Compare database", "FAILED", json.dumps(comparison["details"], indent=2))
            result.add_error("Database comparison failed")

        result.data["database_comparison"] = comparison

        # Step 2: Verify chunk text consistency
        doc_match = comparison["details"]["document_count"]["match"]
        chunk_match = comparison["details"]["chunk_count"]["match"]
        text_match_pct = comparison["details"]["chunk_text_sample"]["match_percentage"]

        result.add_step(
            "Verify data consistency",
            "SUCCESS" if (doc_match and chunk_match and text_match_pct == 100) else "FAILED",
            f"Documents: {doc_match}, Chunks: {chunk_match}, Text: {text_match_pct}%"
        )

        # Step 3: Overall assessment
        if comparison["match"] and text_match_pct == 100:
            result.add_step("Overall assessment", "SUCCESS", "✅ Round-trip successful: All data matches")
            result.complete("PASSED")
        else:
            result.add_step("Overall assessment", "FAILED", "❌ Round-trip failed: Data mismatch detected")
            result.complete("FAILED")

    except Exception as e:
        result.add_error(f"Unexpected error: {str(e)}")
        result.complete("FAILED")

    return result


# =========================================================================
# Test Documentation Generator
# =========================================================================

def generate_test_document(result: TestResult):
    """Generate test document in markdown format"""
    doc_file = TEST_DOCS_DIR / f"{result.test_id.lower().replace('-', '_')}_result.md"

    content = f"""# {result.test_id}: {result.test_name}

**Test Date**: {result.start_time.strftime('%Y-%m-%d %H:%M:%S')}
**Test Status**: {result.status}
**Duration**: {result.data.get('duration_seconds', 0):.2f} seconds

---

## Test Steps

"""

    for i, step in enumerate(result.steps, 1):
        status_emoji = "✅" if step["result"] == "SUCCESS" else "❌" if step["result"] == "FAILED" else "⏳"
        content += f"""### Step {i}: {step['step']}

**Status**: {status_emoji} {step['result']}

**Details**:
```
{step['details']}
```

"""

    content += """---

## Test Result

"""

    if result.status == "PASSED":
        content += f"✅ **PASSED** - {result.test_name} completed successfully.\n\n"
    else:
        content += f"❌ **FAILED** - {result.test_name} did not complete successfully.\n\n"

    if result.errors:
        content += "**Errors**:\n"
        for error in result.errors:
            content += f"- {error}\n"
        content += "\n"

    content += """---

## Test Description

"""

    # Add test-specific description
    if result.test_id == "TEST-01":
        content += """### Purpose
Verify that the Export API can successfully export a single-document Skill as a ZIP file.

### Test Data
"""
        content += f"- **Skill Name**: {result.data.get('skill_name', 'N/A')}\n"
        content += f"- **Head ID**: {result.data.get('head_id', 'N/A')}\n"
        content += f"- **Total Chunks**: {result.data.get('total_chunks', 'N/A')}\n"
        content += f"- **Export File**: {result.data.get('export_file', 'N/A')}\n"
        content += f"- **File Size**: {result.data.get('file_size_mb', 0):.2f} MB\n"

        content += """
### Result Explanation
"""
        if result.status == "PASSED":
            content += """The export operation completed successfully:
1. ✅ API responded with HTTP 200
2. ✅ ZIP file was created and saved
3. ✅ ZIP contains all required files (manifest, CSVs, FAISS indices)
4. ✅ File structure is valid

This confirms that the Export API is working correctly for single-document skills.
"""
        else:
            content += f"""The export operation failed. Please review the errors above:
{chr(10).join(f'- {error}' for error in result.errors)}

This indicates an issue with the Export API or data preparation.
"""

    elif result.test_id == "TEST-02":
        content += """### Purpose
Verify that the Import API can successfully import a Skill from an exported ZIP file.

### Test Data
"""
        content += f"- **Export File**: {result.data.get('export_file', 'N/A')}\n"
        content += f"- **New Head ID**: {result.data.get('new_head_id', 'N/A')}\n"
        content += f"- **Skill Name**: {result.data.get('skill_name', 'N/A')}\n"
        content += f"- **Imported Documents**: {result.data.get('imported_doc_count', 'N/A')}\n"
        content += f"- **Imported Chunks**: {result.data.get('imported_chunk_count', 'N/A')}\n"
        content += f"- **FAISS Indices**: {result.data.get('faiss_indices_count', 'N/A')}\n"

        content += """
### Result Explanation
"""
        if result.status == "PASSED":
            content += """The import operation completed successfully:
1. ✅ API responded with HTTP 200
2. ✅ Skill was created in database with new head_id
3. ✅ All documents and chunks were imported
4. ✅ FAISS indices were created

This confirms that the Import API is working correctly and can restore exported skills.
"""
        else:
            content += f"""The import operation failed. Please review the errors above:
{chr(10).join(f'- {error}' for error in result.errors)}

This indicates an issue with the Import API, data validation, or database operations.
"""

    elif result.test_id == "TEST-05":
        content += """### Purpose
Verify data consistency between the original skill and the imported skill (Export → Import round-trip).

### Test Data
"""
        content += f"- **Source Head ID**: {result.data.get('source_head_id', 'N/A')}\n"
        content += f"- **Imported Head ID**: {result.data.get('imported_head_id', 'N/A')}\n"

        if "database_comparison" in result.data:
            comp = result.data["database_comparison"]["details"]
            content += f"- **Document Count Match**: {comp['document_count']['match']}\n"
            content += f"- **Chunk Count Match**: {comp['chunk_count']['match']}\n"
            content += f"- **Text Match Percentage**: {comp['chunk_text_sample']['match_percentage']}%\n"

        content += """
### Result Explanation
"""
        if result.status == "PASSED":
            content += """The round-trip verification passed:
1. ✅ Document counts match exactly
2. ✅ Chunk counts match exactly
3. ✅ Chunk text content is identical (100% match on sampled data)

This confirms that Export → Import preserves data integrity completely.
"""
        else:
            content += f"""The round-trip verification failed. Data mismatch detected:

"""
            if "database_comparison" in result.data:
                comp = result.data["database_comparison"]["details"]

                if not comp["document_count"]["match"]:
                    content += f"❌ **Document Count Mismatch**: Source={comp['document_count']['source']}, Imported={comp['document_count']['imported']}\n\n"

                if not comp["chunk_count"]["match"]:
                    content += f"❌ **Chunk Count Mismatch**: Source={comp['chunk_count']['source']}, Imported={comp['chunk_count']['imported']}\n\n"

                if comp["chunk_text_sample"]["match_percentage"] < 100:
                    content += f"❌ **Text Content Mismatch**: Only {comp['chunk_text_sample']['match_percentage']}% of sampled chunks match\n\n"

            content += """This indicates data loss or corruption during the Export/Import process.
"""

    content += """---

## Additional Information

### Test Environment
- **Database**: `data/skill_metadata.db`
- **FAISS Indices**: `data/faiss_indices/skills/`
- **API Base URL**: `http://localhost:8000/api/v1`

### Related Tests
"""

    if result.test_id == "TEST-01":
        content += "- **Next Test**: TEST-02 (Import Single Document Skill)\n"
        content += "- **Related Test**: TEST-05 (Round-trip Verification)\n"
    elif result.test_id == "TEST-02":
        content += "- **Previous Test**: TEST-01 (Export Single Document Skill)\n"
        content += "- **Related Test**: TEST-05 (Round-trip Verification)\n"
    elif result.test_id == "TEST-05":
        content += "- **Depends on**: TEST-01 and TEST-02\n"
        content += "- **Validates**: Complete Export → Import workflow\n"

    content += f"""
---

**Generated**: {datetime.now().isoformat()}
**Test Framework**: Automated Python Test Suite
**Test Phase**: Smoke Test (Phase 1)
"""

    with open(doc_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"📄 Test document saved: {doc_file}")


# =========================================================================
# Main Test Runner
# =========================================================================

def main():
    """Main test runner"""
    print("=" * 80)
    print("Skill Export/Import - Smoke Test (Phase 1)")
    print("=" * 80)
    print()

    # Wait for service
    if not wait_for_service():
        print("❌ Cannot proceed: Service not available")
        sys.exit(1)

    print()

    # Initialize test results
    all_results = []

    # Test-01: Export
    print("🧪 Running TEST-01: Export Single Document Skill...")
    test01_result = test_01_export_single_skill()
    all_results.append(test01_result)
    generate_test_document(test01_result)
    print(f"   Status: {test01_result.status} ({test01_result.data.get('duration_seconds', 0):.2f}s)")
    print()

    if test01_result.status != "PASSED":
        print("❌ TEST-01 failed. Cannot proceed with TEST-02.")
        save_summary(all_results)
        sys.exit(1)

    export_file = Path(test01_result.data["export_file"])
    source_head_id = test01_result.data["head_id"]

    # Test-02: Import
    print("🧪 Running TEST-02: Import Single Document Skill...")
    test02_result = test_02_import_single_skill(export_file)
    all_results.append(test02_result)
    generate_test_document(test02_result)
    print(f"   Status: {test02_result.status} ({test02_result.data.get('duration_seconds', 0):.2f}s)")
    print()

    if test02_result.status != "PASSED":
        print("❌ TEST-02 failed. Cannot proceed with TEST-05.")
        save_summary(all_results)
        sys.exit(1)

    imported_head_id = test02_result.data["new_head_id"]

    # Test-05: Round-trip
    print("🧪 Running TEST-05: Round-trip Verification...")
    test05_result = test_05_roundtrip_verification(source_head_id, imported_head_id)
    all_results.append(test05_result)
    generate_test_document(test05_result)
    print(f"   Status: {test05_result.status} ({test05_result.data.get('duration_seconds', 0):.2f}s)")
    print()

    # Save summary
    save_summary(all_results)

    # Final report
    print("=" * 80)
    print("SMOKE TEST COMPLETE")
    print("=" * 80)

    passed = sum(1 for r in all_results if r.status == "PASSED")
    failed = sum(1 for r in all_results if r.status == "FAILED")

    print(f"✅ Passed: {passed}/{len(all_results)}")
    print(f"❌ Failed: {failed}/{len(all_results)}")
    print()

    for result in all_results:
        status_emoji = "✅" if result.status == "PASSED" else "❌"
        print(f"{status_emoji} {result.test_id}: {result.test_name} - {result.status}")

    print()
    print(f"📄 Test documents: {TEST_DOCS_DIR}")
    print(f"📊 Test results: {TEST_RESULTS_DIR}")

    if failed > 0:
        sys.exit(1)


def save_summary(results: List[TestResult]):
    """Save test summary"""
    summary_file = TEST_RESULTS_DIR / "smoke_test_summary.json"

    summary = {
        "test_phase": "Smoke Test (Phase 1)",
        "test_date": datetime.now().isoformat(),
        "total_tests": len(results),
        "passed": sum(1 for r in results if r.status == "PASSED"),
        "failed": sum(1 for r in results if r.status == "FAILED"),
        "results": [r.to_dict() for r in results]
    }

    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"📊 Summary saved: {summary_file}")


if __name__ == "__main__":
    main()
