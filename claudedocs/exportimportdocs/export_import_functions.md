
/sc:brainstorm  --think-hard
please make plan first, and donot modify any code without my permission.
<system-instruction>
You are an experienced Full-Stack RAG Developer. 
You are proficient in Python (Backend), SQL, Faiss vector database, and [Insert Frontend Framework, e.g., Vue3/React].
Your code should be robust, modular, and include error handling.
</system-instruction>

<context>
We need to implement "Export Skill" and "Import Skill" functionalities for our RAG system.
Current Architecture:
- Database: SQLite
- Vector Store: Faiss (stored in `data/faiss_indices/skills/{skill_id}`)
- Backend Framework: [Insert Framework, e.g., FastAPI]
- Frontend Framework: [Insert Framework, only Javascript + Html + CSS]
</context>

<task>
Please implement the Backend APIs and Frontend UI changes based on the following specifications:

### 1. Backend: Export Skill
**Endpoint:** `GET /api/skills/{skill_id}/export`
**Logic:**
1.  **Prepare Metadata (manifest.json):** Create a JSON file containing:
    -   `skill_name`
    -   `export_date`
    -   `source_skill_id`
    -   `file_list` (list of included CSVs and Faiss files)
2.  **Export SQLite Data:** Query specific tables filtered by `skill_id` and save them as CSV files. 
    -   Tables: `skill_chunk_metadata`, `skill_document_mapping`, `skill_heads`, `skill_metadata`, `skill_overviews`.
3.  **Export Faiss Index:** Locate `index.faiss` and `index.pkl` from `data/faiss_indices/skills/{skill_id}`.
4.  **Compression:** -   Create a temporary folder named after the skill.
    -   Move the JSON manifest, CSV files, and Faiss files into this folder.
    -   Zip the folder.
    -   Return the Zip file as a downloadable response (Filename: `{skill_name}.zip`).

### 2. Backend: Import Skill
**Endpoint:** `POST /api/skills/import`
**Logic:**
1.  **Upload & Extract:** Receive the Zip file, extract it to a temporary location.
2.  **Read Manifest:** Parse `manifest.json` to validate the structure.
3.  **ID Management (Crucial):** -   Generate a NEW `skill_id` (UUID) for the imported skill to avoid conflicts.
    -   Update the `skill_id` in all extracted CSV data (Foreign Keys) to match this new ID.
4.  **Database Transaction:** -   Use a SQL transaction context.
    -   Insert data from CSVs into the respective SQLite tables.
    -   If any error occurs, ROLLBACK changes.
5.  **Faiss Setup:**
    -   Create directory `data/faiss_indices/skills/{new_skill_id}`.
    -   Move/Copy the Faiss files (`index.faiss`, `index.pkl`) to this new directory.
6.  **Cleanup:** Delete temporary files.

### 3. Frontend: UI Changes
**Page:** `skill/config`
1.  **Export Button:**
    -   Location: In the data table row for each skill, after the "+" button.
    -   Action: Clicking triggers the Export API and downloads the file.
2.  **Import Button:**
    -   Location: To the left of the existing [Add Skill] button at the top.
    -   Action: Opens a file selection dialog (accepts .zip). Upon selection, uploads the file to the Import API. Refresh the list upon success.
</task>

<constraints>
- Use Python's built-in `zipfile`, `csv`, and `sqlite3` (or ORM) libraries.
- Ensure proper logging for each step.
- Handle edge cases: What if the Faiss file is missing? What if the Zip is corrupted?
</constraints>