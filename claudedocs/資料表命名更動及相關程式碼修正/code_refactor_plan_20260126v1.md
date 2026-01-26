# 程式碼重構計畫：資料庫命名同步

**日期**: 2026-01-26
**前置作業**: 資料庫表格已完成重構（見 `db_table_refactor_20260126v1.md`）
**規則**: 所有程式碼修改需經用戶許可方可執行

---

## 命名映射總表

### 表名映射
| 舊表名 | 新表名 |
|--------|--------|
| `skill_heads` | `knowledge_info` |
| `skill_metadata` | `knowledge_metadata` |
| `skill_chunk_metadata` | `knowledge_chunk_metadata` |
| `skill_document_mapping` | `knowledge_document_mapping` |
| `skill_overviews` | `knowledge_overviews` |

### 欄位名映射
| 舊欄位名 | 新欄位名 |
|----------|----------|
| `head_id` | `knowledge_id` |
| `skill_id` | `doc_id` |
| `skill_name` | `knowledge_name` |
| `skill_description` | `knowledge_description` |
| `skill_category` | `knowledge_type` |
| `skill_level` | `knowledge_level` |
| `parent_skill_id` | `parent_knowledge_id` |
| `related_skills` | `related_knowledge` |

### 值前綴映射
| 舊前綴 | 新前綴 |
|--------|--------|
| `head_` (ID 值) | `knowledge_` |
| `skill_` (ID 值) | `doc_` |

---

## 修改計畫（按優先級分 Phase）

---

### Phase 1: 核心 Provider（最高優先）

資料存取層 — 所有上層程式碼都依賴此層。

#### 檔案 1-1: `app/Providers/skill_metadata_provider/client.py`
**影響等級**: 🔴 CRITICAL | **預估改動**: 300+ 處

**SQL 表名修改:**
| 行號範圍 | 改動項目 |
|----------|----------|
| 132 | `CREATE TABLE IF NOT EXISTS skill_metadata` → `knowledge_metadata` |
| 165 | `CREATE TABLE IF NOT EXISTS skill_overviews` → `knowledge_overviews` |
| 175 | `CREATE TABLE IF NOT EXISTS skill_document_mapping` → `knowledge_document_mapping` |
| 222 | `CREATE TABLE IF NOT EXISTS skill_heads` → `knowledge_info` |
| 226 | `ALTER TABLE skill_metadata ADD COLUMN head_id TEXT REFERENCES skill_heads(head_id)` → `knowledge_metadata ... knowledge_id TEXT REFERENCES knowledge_info(knowledge_id)` |
| 235 | `idx_skill_head_id ON skill_metadata(head_id)` → `idx_knowledge_id ON knowledge_metadata(knowledge_id)` |
| 193-218 | 所有 CREATE INDEX 語句中的表名和欄位名 |
| 261-262 | processing_jobs 的 FOREIGN KEY references |
| 614 | `DELETE FROM skill_metadata WHERE skill_id = ?` → `knowledge_metadata WHERE doc_id = ?` |
| 717-727 | `skill_overviews` 相關 INSERT/SELECT |
| 794-835 | `skill_document_mapping` 相關 INSERT/SELECT |
| 1497-1519 | cascade delete 中的所有表名引用 |

**SQL 欄位名修改（CREATE TABLE 內）:**
| 行號 | 舊欄位 | 新欄位 |
|------|--------|--------|
| 132 | `skill_id TEXT PRIMARY KEY` | `doc_id TEXT PRIMARY KEY` |
| 133 | `skill_name TEXT NOT NULL` | `knowledge_name TEXT NOT NULL` |
| 134 | `skill_description TEXT` | `knowledge_description TEXT` |
| 135 | `skill_category TEXT` | `knowledge_type TEXT` |
| 136 | `skill_level TEXT` | `knowledge_level TEXT` |
| 138 | `related_skills TEXT` | `related_knowledge TEXT` |
| 166 | `skill_id TEXT PRIMARY KEY` (overviews) | `doc_id TEXT PRIMARY KEY` |
| 178 | `skill_id TEXT NOT NULL` (doc_mapping) | `doc_id TEXT NOT NULL` |
| 223 | `head_id TEXT PRIMARY KEY, skill_name TEXT` (heads) | `knowledge_id TEXT PRIMARY KEY, knowledge_name TEXT` |

**Python 函數參數名修改:**
| 行號 | 函數 | 舊參數 | 新參數 |
|------|------|--------|--------|
| 279 | `create_skill()` | `skill_id, skill_name, skill_description, skill_category, skill_level, related_skills, parent_skill_id, head_id` | `doc_id, knowledge_name, knowledge_description, knowledge_type, knowledge_level, related_knowledge, parent_knowledge_id, knowledge_id` |
| 347 | `get_skill()` | `skill_id` | `doc_id` |
| 437 | `list_skills()` | `skill_category`, `skill_level` 過濾 | `knowledge_type`, `knowledge_level` |
| 564 | `update_skill()` | `skill_id` | `doc_id` |
| 609 | `delete_skill()` | `skill_id` | `doc_id` |
| 711 | `store_overview()` | `skill_id` | `doc_id` |
| 745 | `get_overview()` | `skill_id` | `doc_id` |
| 769 | `get_multiple_overviews()` | `skill_ids` | `doc_ids` |
| 788 | `link_skill_to_document()` | `skill_id` | `doc_id` |
| 810 | `get_documents_for_skill()` | `skill_id` | `doc_id` |
| 829 | `get_skills_for_document()` | return dict `skill_id` key | `doc_id` key |
| 763 | `create_skill_head()` | `head_id, skill_name` | `knowledge_id, knowledge_name` |
| 806 | `get_skill_head()` | `head_id` | `knowledge_id` |
| 833 | `get_skill_head_by_name()` | `skill_name` | `knowledge_name` |
| 854 | `list_skill_heads()` | SELECT 中的 `head_id, skill_name` | `knowledge_id, knowledge_name` |
| 870 | `update_skill_head()` | `head_id` | `knowledge_id` |
| 897 | `delete_skill_head()` | `head_id` | `knowledge_id` |

**Python 回傳 dict key 修改:**
| 行號範圍 | 舊 key | 新 key |
|----------|--------|--------|
| 363-384 | `skill_id`, `skill_name`, `skill_description`, `skill_category`, `skill_level`, `parent_skill_id`, `related_skills` | `doc_id`, `knowledge_name`, `knowledge_description`, `knowledge_type`, `knowledge_level`, `parent_knowledge_id`, `related_knowledge` |
| 489-493 | 同上 | 同上 |
| 774 | `row["skill_id"]` | `row["doc_id"]` |
| 835 | `row["skill_id"]` | `row["doc_id"]` |

**日誌訊息修改:**
| 行號 | 舊訊息 | 新訊息 |
|------|--------|--------|
| 231 | `"Added head_id column to skill_metadata"` | `"Added knowledge_id column to knowledge_metadata"` |
| 339 | `f"Created skill metadata: {skill_id}"` | `f"Created knowledge metadata: {doc_id}"` |
| 601 | `f"Updated skill metadata: {skill_id}"` | `f"Updated knowledge metadata: {doc_id}"` |
| 621 | `f"Deleted skill metadata: {skill_id}"` | `f"Deleted knowledge metadata: {doc_id}"` |
| 730 | `f"Stored overview for skill: {skill_id}"` | `f"Stored overview for knowledge: {doc_id}"` |
| 803 | `f"Linked skill {skill_id}"` | `f"Linked knowledge {doc_id}"` |

#### 檔案 1-2: `app/Providers/skill_metadata_provider/__init__.py`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 5 處

- Docstring 中的 `skill metadata` → `knowledge metadata`
- Docstring 中的 `skill overviews` → `knowledge overviews`
- Docstring 中的 `skill-document mappings` → `knowledge-document mappings`

#### 檔案 1-3: `app/Providers/db_utils.py`
**影響等級**: 🟢 RECOMMENDED | **預估改動**: 5 處

- Line 50-53: Docstring 範例中的 `skill_chunk_metadata` → `knowledge_chunk_metadata`
- Line 52: 範例中的 `skill_id` → `doc_id`

---

### Phase 2: API Endpoints

API 路由層 — 前端直接呼叫的介面。

#### 檔案 2-1: `app/api/v1/endpoints/skills.py`
**影響等級**: 🔴 CRITICAL | **預估改動**: 95-115 處

**SQL 表名修改 (15-20 處):**
| 行號範圍 | 舊表名 | 新表名 |
|----------|--------|--------|
| 785-800 | `INSERT INTO skill_chunk_metadata` | `knowledge_chunk_metadata` |
| 773-780 | `INSERT INTO skill_document_mapping` | `knowledge_document_mapping` |
| 1020+ | `SELECT FROM skill_metadata` | `knowledge_metadata` |
| 1030+ | `DELETE FROM skill_chunk_metadata` | `knowledge_chunk_metadata` |
| 1032+ | `DELETE FROM skill_document_mapping` | `knowledge_document_mapping` |
| 1035+ | `DELETE FROM skill_overviews` | `knowledge_overviews` |
| 1038+ | `DELETE FROM skill_metadata` | `knowledge_metadata` |
| 1384+ | `INSERT OR REPLACE INTO skill_document_mapping` | `knowledge_document_mapping` |
| 1395+ | `INSERT OR REPLACE INTO skill_chunk_metadata` | `knowledge_chunk_metadata` |
| 1944+ | `INSERT OR REPLACE INTO skill_document_mapping` | `knowledge_document_mapping` |
| 2387+ | `DELETE FROM skill_document_mapping` | `knowledge_document_mapping` |
| 3374-3376 | `DELETE FROM skill_document_mapping` | `knowledge_document_mapping` |
| 4270-4384 | Export 中的表名引用 | 全部更新 |
| 4861-5101 | Import 中的表名引用 | 全部更新 |

**SQL 欄位名修改 (20-25 處):**
- 所有 SQL 語句中的 `skill_id` → `doc_id`
- 所有 SQL 語句中的 `skill_name` → `knowledge_name`
- 所有 SQL 語句中的 `head_id` → `knowledge_id`

**Python 參數/變數名修改 (25-30 處):**
- 函數參數 `skill_id` → `doc_id`
- 函數參數 `head_id` → `knowledge_id`
- 函數參數 `skill_name` → `knowledge_name`
- 函數參數 `skill_category` → `knowledge_type`
- 函數參數 `skill_description` → `knowledge_description`
- 函數參數 `skill_level` → `knowledge_level`
- 函數參數 `parent_skill_id` → `parent_knowledge_id`

**ID 生成邏輯修改:**
- Line 663+: `skill_id = f"skill_{timestamp}_{hash}"` → `doc_id = f"doc_{timestamp}_{hash}"`
- Line 1009+: 同上

**Provider 方法呼叫修改 (10-15 處):**
- `await provider.create_skill()` → 對應新參數
- `await provider.list_skill_heads()` → 對應新方法名
- `await metadata_provider.delete_skill_head()` → 對應新方法名
- `await provider.update_skill_head()` → 對應新方法名

**Pydantic Model 修改:**
- Lines 360-395: `SkillResponse` 的欄位名

---

### Phase 3: SkillServices 層

業務邏輯層 — 處理 PDF 入庫、向量檢索等。

#### 檔案 3-1: `app/SkillServices/pdf_skill_ingestion_service.py`
**影響等級**: 🔴 CRITICAL | **預估改動**: 50+ 處

- SQL 表名: `skill_chunk_metadata` (5 處)、`skill_document_mapping` (3 處)
- SQL 欄位: `skill_id` → `doc_id` (15+ 處)
- 函數參數: `skill_id`, `skill_name`, `skill_description`, `skill_category` (10+ 處)
- 變數名: `skill_id` (10+ 處)

#### 檔案 3-2: `app/SkillServices/skill_ingestion_service.py`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 20 處

- 無直接 SQL 表名引用
- 函數參數/變數: `skill_id`, `skill_name`, `skill_category`, `skill_level` (20 處)
- Metadata dict key: `skill_id`, `skill_name`, `skill_category`, `skill_level`

#### 檔案 3-3: `app/SkillServices/skill_retrieval_service.py`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 15 處

- 函數參數: `skill_id` (5 處)、`skill_ids` (2 處)
- 變數名和日誌中的 `skill_id` (8 處)

#### 檔案 3-4: `app/SkillServices/base_retrieval.py`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 15 處

- Docstring 中的 `skill_id` (5 處)
- `get_metadata_fields()` 方法中: `skill_id`, `skill_name`, `skill_category` (6 處)

#### 檔案 3-5: `app/SkillServices/index_integrity.py`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 10 處

- 函數參數和變數中的 `skill_id` (10 處)

#### 檔案 3-6: `app/SkillServices/background_integrity_checker.py`
**影響等級**: 🟢 RECOMMENDED | **預估改動**: 10 處

- 變數名和日誌中的 `skill_id` (10 處)

#### 檔案 3-7: `app/SkillServices/progressive_skill_streaming/progressive_streaming.py`
**影響等級**: 🟢 RECOMMENDED | **預估改動**: 5 處

- 參數名中的 `skill_id` (5 處)

#### 檔案 3-8: `app/SkillServices/progressive_skill_streaming/phase2_skill_retrieval.py`
**影響等級**: 🟢 RECOMMENDED | **預估改動**: 10 處

- 參數名和變數中的 `skill_id` (10 處)

---

### Phase 4: 前端 Templates

使用者介面層。

#### 檔案 4-1: `template/skill_config.html`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 20+ 處

- JavaScript 中的 API 回應欄位名: `head_id`, `skill_name`, `skill_id`
- Modal 文字中的表名引用
- 函數中操作 `head_id`, `skill_name` 等欄位的邏輯

#### 檔案 4-2: `template/skill_main.html`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 30+ 處

- JavaScript 中的 API 回應欄位名: `skill_id`, `skill_name`, `head_id`, `parent_skill_id`
- 建構 skill tree 時使用的欄位名
- 查詢 API 時送出的參數名

#### 檔案 4-3: `template/skill_demo.html`
**影響等級**: 🟢 RECOMMENDED | **預估改動**: 5 處

- API 請求中的 `skill_id` 參數

#### 檔案 4-4: `static/i18n/ui_translations.json`
**影響等級**: 🟢 RECOMMENDED | **預估改動**: 多處

- UI 文字中的「技能」→「知識」（中文）
- UI 文字中的 "Skill" → "Knowledge"（英文）

---

### Phase 5: Scripts（工具腳本）

#### 檔案 5-1: `scripts/init_docai_windows.py`
**影響等級**: 🔴 CRITICAL | **預估改動**: 80+ 處

- 完整的 CREATE TABLE 語句（5 個表）
- 所有 CREATE INDEX 語句
- 初始資料 INSERT 語句
- 欄位名、表名全面修改

#### 檔案 5-2: `scripts/rebuild_skills.py`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 50+ 處

- SQL INSERT 中的表名和欄位名
- 函數參數和變數中的 `skill_id`, `skill_name` 等

#### 檔案 5-3: `scripts/skill_data/rebuild_from_config.py`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 100+ 處

- SQL 語句中的表名（4 處）
- 大量的 `skill_id`, `skill_name`, `skill_description`, `skill_category`, `parent_skill_id` 引用

#### 檔案 5-4: `scripts/fix_faiss_db_id_mismatch.py`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 60+ 處

- SQL 查詢中的表名（4 處）
- 大量的 `skill_id` 引用

#### 檔案 5-5: `scripts/fix_missing_chunk_metadata.py`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 40+ 處

- `skill_chunk_metadata` 表名（3 處）
- `skill_id` 欄位（多處）

#### 檔案 5-6: `scripts/migrate_add_page_tracking.py`
**影響等級**: 🟡 IMPORTANT | **預估改動**: 30+ 處

- `skill_chunk_metadata`, `skill_metadata`, `skill_document_mapping` 表名
- 欄位名引用

#### 檔案 5-7: `scripts/test_skill_heads_migration.py`
**影響等級**: 🟢 RECOMMENDED | **預估改動**: 15 處

- `skill_heads`, `skill_metadata` 表名
- `head_id`, `skill_name` 欄位

#### 檔案 5-8~5-14: 其他 test/load 腳本
**影響等級**: 🟢 RECOMMENDED | **預估改動**: 各 5-30 處

| 檔案 | 預估改動 |
|------|----------|
| `scripts/test_export_import.py` | 50 處 |
| `scripts/load_demo_skills.py` | 20 處 |
| `scripts/load_legal_skills.py` | 25 處 |
| `scripts/load_civil_law_skill.py` | 30 處 |
| `scripts/test_legal_skills.py` | 10 處 |
| `scripts/test_batch_embedding.py` | 5 處 |
| `scripts/test_direct_faiss.py` | 5 處 |
| `scripts/test_gorgon_retrieval.py` | 5 處 |
| `scripts/test_opmp_fixed.py` | 15 處 |
| `test_api_query.py` (根目錄) | 3 處 |
| `test_opmp_fixed.py` (根目錄) | 5 處 |

---

### Phase 6: 其他檔案

#### 檔案 6-1: `app/models/schemas.py`
**影響等級**: 🟢 RECOMMENDED | **預估改動**: 5 處

- Pydantic model 中的 `file_id` 相關欄位（此為 File-Based 系統，可能不需改動）

#### 檔案 6-2: `template/bak/` 目錄下的備份檔
**影響等級**: ⚪ OPTIONAL | **預估改動**: 不改

- 這些是備份檔案，不影響系統運行，建議不改動

#### 檔案 6-3: JSON 測試結果檔（`claudedocs/` 下）
**影響等級**: ⚪ OPTIONAL | **預估改動**: 不改

- 這些是歷史測試紀錄，不影響系統運行

---

## 執行順序建議

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6
(Provider)  (API)     (Services) (Frontend) (Scripts)  (Others)
```

**原因**: 底層 Provider 先改，確保資料存取正確；再改 API 層；再改業務邏輯層；最後改前端和工具腳本。

---

## 統計總覽

| Phase | 檔案數 | 預估改動總數 | 優先級 |
|-------|--------|------------|--------|
| Phase 1: Provider | 3 | ~310 | 🔴 CRITICAL |
| Phase 2: API | 1 | ~115 | 🔴 CRITICAL |
| Phase 3: Services | 8 | ~135 | 🟡 IMPORTANT |
| Phase 4: Templates | 4 | ~60 | 🟡 IMPORTANT |
| Phase 5: Scripts | 14 | ~370 | 🟡~🟢 |
| Phase 6: Others | 3 | ~10 | 🟢 OPTIONAL |
| **合計** | **33** | **~1000** | |

---

## 風險評估

| 風險 | 說明 | 緩解措施 |
|------|------|----------|
| API 回應格式變更 | 前端依賴 API 回應的 key 名稱 | Phase 2 和 Phase 4 必須同步修改 |
| 外鍵參照完整性 | 值前綴已在 DB 層改完，但 code 生成新 ID 時需用新前綴 | 確保 ID 生成邏輯同步更新 |
| Export/Import 功能 | 匯出檔案格式包含表名和欄位名 | 需處理向後相容或同步更新 |
| 備份還原 | 舊備份的 DB 與新 code 不相容 | 保留備份 `skill_metadata.db.backup_before_rename` |

---

## 回滾方案

1. **資料庫**: `cp data/skill_metadata.db.backup_before_rename data/skill_metadata.db`
2. **程式碼**: `git stash` 或 `git checkout .`（如已 commit 則 `git revert`）

---

*計畫產出日期: 2026-01-26*
*需經用戶許可方可開始執行*
