<!-- claudedocs/exportimportdocs/00_original_requirements.md -->
# Export/Import Skill 功能 - 原始需求文檔

**建立日期**: 2025-12-25
**文檔類型**: 原始需求規格
**狀態**: 已轉換為實施計畫

---

## 📋 原始需求

### System Instruction

You are an experienced Full-Stack RAG Developer.
You are proficient in Python (Backend), SQL, Faiss vector database, and Frontend frameworks.
Your code should be robust, modular, and include error handling.

---

## 🏗️ 系統架構

### Current Architecture

- **Database**: SQLite
- **Vector Store**: Faiss (stored in `data/faiss_indices/skills/{skill_id}`)
- **Backend Framework**: FastAPI
- **Frontend Framework**: Pure JavaScript + HTML + CSS (No framework)

---

## 📦 功能需求

### 1. Backend: Export Skill

**Endpoint:** `GET /api/skills/{skill_id}/export`

#### 實施邏輯

**Step 1: Prepare Metadata (manifest.json)**

Create a JSON file containing:
- `skill_name`
- `export_date`
- `source_skill_id`
- `file_list` (list of included CSVs and Faiss files)

**Step 2: Export SQLite Data**

Query specific tables filtered by `skill_id` and save them as CSV files:
- `skill_chunk_metadata`
- `skill_document_mapping`
- `skill_heads`
- `skill_metadata`
- `skill_overviews`

**Step 3: Export Faiss Index**

Locate files from `data/faiss_indices/skills/{skill_id}`:
- `index.faiss`
- `index.pkl`

**Step 4: Compression**

- Create a temporary folder named after the skill
- Move the JSON manifest, CSV files, and Faiss files into this folder
- Zip the folder
- Return the Zip file as a downloadable response (Filename: `{skill_name}.zip`)

---

### 2. Backend: Import Skill

**Endpoint:** `POST /api/skills/import`

#### 實施邏輯

**Step 1: Upload & Extract**

Receive the Zip file, extract it to a temporary location.

**Step 2: Read Manifest**

Parse `manifest.json` to validate the structure.

**Step 3: ID Management (Crucial)**

- Generate a NEW `skill_id` (UUID) for the imported skill to avoid conflicts
- Update the `skill_id` in all extracted CSV data (Foreign Keys) to match this new ID

**Step 4: Database Transaction**

- Use a SQL transaction context
- Insert data from CSVs into the respective SQLite tables
- If any error occurs, ROLLBACK changes

**Step 5: Faiss Setup**

- Create directory `data/faiss_indices/skills/{new_skill_id}`
- Move/Copy the Faiss files (`index.faiss`, `index.pkl`) to this new directory

**Step 6: Cleanup**

Delete temporary files.

---

### 3. Frontend: UI Changes

**Page:** `skill/config`

#### Export Button

- **Location**: In the data table row for each skill, after the "+" button
- **Action**: Clicking triggers the Export API and downloads the file

#### Import Button

- **Location**: To the left of the existing [Add Skill] button at the top
- **Action**: Opens a file selection dialog (accepts .zip). Upon selection, uploads the file to the Import API. Refresh the list upon success.

---

## ⚠️ 約束條件

### Technical Constraints

- Use Python's built-in libraries:
  - `zipfile` - For compression/decompression
  - `csv` - For CSV file handling
  - `sqlite3` - For database operations (or ORM)

### Quality Requirements

- **Logging**: Ensure proper logging for each step
- **Error Handling**: Handle edge cases:
  - What if the Faiss file is missing?
  - What if the Zip is corrupted?
  - What if the database transaction fails?

---

## 📚 相關文檔

### 已產出的計畫文檔

1. **[skill_export_import_implementation_plan.md](skill_export_import_implementation_plan.md)**
   - 完整的實施計畫
   - 詳細的技術規格
   - 18-24 小時的時程估算

2. **[skill_export_pdf_inclusion_analysis.md](skill_export_pdf_inclusion_analysis.md)**
   - PDF 包含與否的深度分析
   - 決策矩陣與建議方案
   - 兩階段實施策略

### 設計決策

| 問題 | 決策 | 文檔 |
|------|------|------|
| **是否包含 PDF？** | Phase 1: 不包含<br>Phase 2: 選擇性包含 | pdf_inclusion_analysis.md |
| **head_id 處理？** | 總是新建 | implementation_plan.md |
| **Skill name 衝突？** | 自動重命名（加時間戳） | implementation_plan.md |
| **API 路徑？** | `/config/skills/export/{id}`<br>`/config/skills/import` | implementation_plan.md |

---

## 🎯 實施狀態

### 當前階段

- [x] 需求分析完成
- [x] 系統架構調查完成
- [x] 實施計畫制定完成
- [x] 設計決策確定完成
- [ ] Phase 1 實作（待開始）
- [ ] Phase 2 實作（待開始）
- [ ] 測試與驗證（待開始）

### 下一步

等待用戶確認設計決策後，開始實施 Phase 1：
1. Backend Export API（不含 PDF）
2. Backend Import API
3. Frontend UI 整合
4. 測試與除錯

---

**文檔版本**: 1.0
**建立日期**: 2025-12-25
**最後更新**: 2025-12-25
**狀態**: 原始需求（已轉換為實施計畫）
