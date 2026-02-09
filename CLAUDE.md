# CLAUDE.md - SuperClaude Framework for DocAI

## Project Context
This is a DocAI RAG system implementing Skill-Based Architecture with complete isolation from the existing file-based system.

## Core Directives
- **Demo Priority**: 下周一、二就要demo - Focus on easy-to-achieve solutions first
- **Post-Demo**: Enterprise-grade refactoring after demo success
- **Isolation**: Complete separation of Skill-Based and File-Based systems
- **Evidence-Based**: All solutions must be tested and validated

---

## 📝 Modification Diary System (修改日記規則)

**強制規則**: 每次對程式碼進行修改，都必須記錄在修改日記中。

### 日記位置
`claudedocs/modify_diary/`

### 檔名格式
`{簡短描述}_{YYYYMMDDHH_mm}.md`

**範例**:
- `sqlite_wal_optimization_2025011015_30.md`
- `skill_api_bugfix_2025011209_45.md`
- `frontend_scroll_fix_2025011114_20.md`

### 日記內容模板
```markdown
# 修改日記: {標題}

**日期時間**: YYYY-MM-DD HH:mm
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟢 低 / 🟡 中 / 🔴 高

## 修改摘要
{一句話描述這次修改的目的}

## 修改檔案
| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| path/to/file.py | 新增/修改/刪除 | 具體描述 |

## 影響分析
- 影響範圍: {哪些功能會受影響}
- 向後相容: 是/否
- 需要測試: {測試步驟}

## 回滾方案
{如何還原這次修改}

## 驗證結果
- [ ] 單元測試通過
- [ ] 整合測試通過
- [ ] 手動驗證通過
```

### 使用時機
1. ✅ 修改任何 `.py`, `.js`, `.html`, `.css` 檔案
2. ✅ 修改設定檔 (`.json`, `.yaml`, `.toml`)
3. ✅ 修改資料庫結構
4. ❌ 不需記錄: 純文檔更新 (README, CLAUDE.md 等)

---

## 🚨 Known Issues / 已知問題

### 🔴 ISSUE-001: Skill 選擇後查詢失敗 (P0 最高優先級) - 2026-01-23

**優先級**: 🔴 **最高 (P0)**  
**狀態**: ✅ 已修復  
**詳細文檔**: `claudedocs/top_issues/ISSUE_001_skill_selection_empty_query.md`

**問題描述**：
用戶在 Skill Chat 頁面選擇任何 Skill 後進行查詢，系統總是回答「抱歉，我無法回答此問題，因為缺少相關文檔內容」。

**根本原因**：
前端 `handleSkillGroupClick` 和 `selectSkillGroupFromTree` 函數在處理**舊架構 Skill**（`skill.documents = []`）時，沒有設置 `selectedSkills`，導致查詢無法發送或發送空的 skill_id。

**影響範圍**：
- 所有舊架構 Skill（六法全書-刑法、投資理財原版等）
- 任何 `documents` 陣列為空的 Skill

**解決方案**：
在選擇函數中增加 `else` 分支，當 `skill.documents` 為空時，直接使用 `headId` 作為 skill_id：

```javascript
if (skill.documents && skill.documents.length > 0) {
    // 新架構：選擇所有子文檔
    skill.documents.forEach(doc => { selectedSkills.push({...}); });
} else {
    // ✅ 修復：舊架構 fallback - 使用 head_id
    selectedSkills.push({ id: headId, isHead: true, ... });
}
```

**修改檔案**：
- `template/skill_main.html` - Lines ~3740, ~4010

**偵測方法**：
1. Console 檢查：選擇 Skill 後應看到 `with X documents` 而非 `with 0 documents`
2. 瀏覽器 Network tab：檢查 `/demo/query` 請求的 skill_id 是否正確

**預防措施**：
1. 統一架構：為所有舊架構 Skill 創建對應的 document 記錄
2. 前端防禦性編程：統一選擇函數，確保 `selectedSkills` 永不為空
3. API 層 fallback：當 documents 為空時嘗試直接使用 head_id

---

### ✅ 聊天介面捲動問題 (SOLVED) - 2025-12-16

**問題描述**：
在 `skill_main.html` 聊天介面中，當用戶輸入新的 query 時，舊的訊息（包含前一個 query 和 AI 回答）無法自動向上捲動出畫面，直到只剩下新的 query 顯示在畫面上。

**解決方案**：
重寫 `scrollMessageToTop()` 函數，使用以下技術：
1. **強制 100vh padding** - 確保有足夠的捲動空間
2. **setTimeout + 雙重 RAF** - 確保 DOM 完全更新後再計算位置
3. **getBoundingClientRect()** - 最可靠的位置計算方法，不受 offsetParent 影響
4. **直接 scrollTop 賦值** - 比 scrollTo() 更可靠

**修改檔案**：
- `template/skill_main.html` - `scrollMessageToTop()` 函數 (lines ~2500-2540)

**詳細文檔**：`claudedocs/scroll_to_new_query_fix_20251216.md`

---

## 📅 Session Update - 2025-12-05 (SSE Upload Progress & Delete Source)

### 🎯 SSE 上傳進度修復 ✅ 完成

#### 問題分析

上傳 PDF 時進度視窗有以下問題：
1. 進度條一直停在 0%
2. 狀態徽章不更新
3. 按鈕沒從「取消」切換為「完成」
4. Modal 關閉後頁面不刷新

#### 根本原因

| Bug | 原因 | 修復 |
|-----|------|------|
| 進度條 0% | 前端只解析 `data:` 行，忽略 `event:` 行 | 添加 `currentEventType` 追蹤 |
| 欄位不匹配 | 後端發送 `percent`，前端期望 `progress` | 同時檢查兩個欄位 |
| 完成欄位 | 後端 `total_chunks`，前端 `chunks_created` | 支援兩種命名 |
| 不刷新 | SSE 結束後沒調用 `loadConfig()` | 添加自動刷新邏輯 |

#### 修改檔案

**template/skill_config.html**:
- Lines 1708: 添加 `currentEventType` 追蹤 SSE event type
- Lines 1718-1734: 改進 SSE 解析邏輯（同時處理 `event:` 和 `data:`）
- Lines 1738-1747: 添加串流結束後的自動資料刷新
- Lines 1749-1835: 重寫 `handleSSEEvent()` 函數，支援階段性進度映射

#### 進度映射

```
5%   → 開始處理
8%   → 檔案已保存
10%  → 開始提取文字
40%  → 文字提取完成 / 開始向量嵌入
80%  → 向量嵌入完成 / 開始 FAISS 儲存
90%  → FAISS 完成 / 開始元資料儲存
95%  → 元資料儲存完成
100% → 完成
```

---

### 🎯 刪除來源功能移植 ✅ 完成

#### 需求

將「刪除來源」功能從 skill/chat 頁面移至 skill/config 頁面。

#### 實作內容

| 元素 | 位置 | 說明 |
|------|------|------|
| **刪除按鈕** | 文件列末端 | 🗑️ 圖示，hover 時變紅 |
| **確認 Modal** | delete-source-modal | 顯示來源名稱、chunks 數、警告訊息 |
| **Toast 通知** | 右下角 | 刪除成功後的滑入提示 |

#### 修改檔案

**template/skill_config.html**:
- Lines 482-501: `.btn-delete-source` 按鈕樣式
- Lines 628-636: Toast 動畫 `slideIn`/`slideOut`
- Lines 1082-1121: 刪除確認 Modal HTML
- Lines 1391-1394: 文件列刪除按鈕
- Lines 1543-1612: JavaScript 函數
  - `showDeleteSourceModal(skillId, sourceName, chunks)`
  - `confirmDeleteSource()`
  - `showToast(message, type)`

#### 刪除 API

```
DELETE /api/v1/skills/{skill_id}

刪除項目：
1. FAISS 向量索引
2. PDF 原始檔案
3. SQLite 元資料 (skill_metadata, skill_document_mapping, skill_chunk_metadata)
```

#### 使用流程

```
1. 前往 skill-config 頁面
2. 展開 Skill 卡片
3. 文件列末端出現 🗑️ 按鈕（hover 顯示）
4. 點擊 → 確認 Modal
5. 確認刪除 → API 調用 → Toast 通知 → 自動刷新
```

---

### 📝 UI 文字修改指南

新增 `名稱修改.txt` 檔案，記錄系統中所有 UI 文字的定義位置：

- **主要位置**: `static/i18n/ui_translations.json`
- **Skill Config**: `template/skill_config.html`
- **Skill Main**: `template/skill_main.html`

---

## 📅 Session Update - 2025-12-04 (Architecture Refactoring Complete)

### 🎯 核心架構重構：skill_heads 表 ✅ 完成

#### 問題 1：Dual Source of Truth (反模式) → 已解決

**舊架構問題**（已廢棄）：
```
┌──────────────────┐     ┌──────────────────┐
│ skill_config.json │ ←→ │ skill_metadata.db │
│  (手動維護)       │     │  (自動生成)       │
└──────────────────┘     └──────────────────┘
        ↓                         ↓
   經常不同步！              經常不同步！
```

**新架構**（已實施）：
```
┌──────────────────────────────────────────┐
│            skill_metadata.db              │
│  ┌────────────┐    ┌─────────────────┐   │
│  │skill_heads │ ←→ │ skill_metadata  │   │
│  │(定義層)    │    │ (文件層)        │   │
│  └────────────┘    └─────────────────┘   │
│         Single Source of Truth ✅        │
└──────────────────────────────────────────┘
```

#### 新流程（已生效）

```
1. 用戶創建 Skill "ML"
   → POST /heads → INSERT INTO skill_heads (head_id='head_xxx', skill_name='ML')

2. 用戶上傳 PDF
   → POST /upload-source → 從 skill_heads 獲取 head_id
   → INSERT INTO skill_metadata (skill_id='doc_xxx', head_id='head_xxx')

3. UI 載入
   → GET /tree → SELECT FROM skill_heads LEFT JOIN skill_metadata
   → 永遠有 Head + Documents 結構！
```

#### 實施步驟（全部完成）

1. ✅ 創建 `skill_heads` 表
2. ✅ 修改 `skill_metadata` 添加 `head_id`
3. ✅ 遷移現有資料 (5 heads, 17 documents)
4. ✅ 新增 API endpoints (/heads, /tree, /migrate)
5. ✅ 移除 JSON 依賴
6. ✅ 更新前端 (skill_config.html, skill_main.html)
7. ✅ 封存 skill_config.json

**封存位置**：`scripts/skill_data/archive/skill_config.json.deprecated`

#### 遷移測試結果

```
✅ skill_heads table exists
✅ head_id column exists in skill_metadata
✅ Migrated heads: 5
✅ Updated documents: 17
📁 ML (1 docs, 462 chunks)
📁 六法全書-刑法 (1 docs, 172 chunks)
📁 六法全書-民法 (5 docs, 533 chunks)
📁 大語言模型大全 (9 docs, 3685 chunks)
📁 投資理財 (1 docs, 95 chunks)
```

#### 新增 API Endpoints

| Endpoint | Method | 說明 |
|----------|--------|------|
| `/api/v1/skills/heads` | GET | 列出所有 skill heads |
| `/api/v1/skills/heads` | POST | 創建新 skill head |
| `/api/v1/skills/heads/{head_id}` | GET | 獲取單一 skill head |
| `/api/v1/skills/heads/{head_id}` | PUT | 更新 skill head |
| `/api/v1/skills/heads/{head_id}` | DELETE | 刪除 skill head |
| `/api/v1/skills/tree` | GET | 獲取完整技能樹 |
| `/api/v1/skills/migrate` | POST | 執行資料遷移 |

#### 新增 Provider 方法

```python
# SkillMetadataProvider 新增方法
create_skill_head()
get_skill_head()
get_skill_head_by_name()
list_skill_heads()
update_skill_head()
delete_skill_head()
get_documents_for_head()
get_skill_tree()
migrate_existing_data()
```

### 其他完成項目

#### ✅ ML Skill Per-PDF 架構重建

- 成功使用 Per-PDF 架構重建 ML skill
- Group Header: `skill_20251203_094135_d01fd9b0`
- Child: `skill_20251203_094135_d01fd9b0_src_00`
- 與「投資理財」結構一致

#### ✅ process_pdf_for_skill() 修正

**問題**: 新上傳時 `source_name` 為 NULL

**修正** (`app/api/v1/endpoints/skills.py` Lines 883-904):
```python
source_name = pdf_path.stem  # 取 PDF 檔名（不含副檔名）
await metadata_provider.create_skill(
    ...,
    source_name=source_name  # ✅ Per-PDF: Set the PDF filename
)
```

---

## 📅 Session Update - 2025-11-28 Afternoon (Skill Name Sync & UI Polish)

### 完成項目 (Completed This Session)

#### 1. ✅ Skill Names Sync Fix

**問題**: Config page 和 Chat page sidebar 的 skill 名稱不一致

| Config Page (舊) | Chat Page Sidebar | Config Page (新) |
|------------------|-------------------|------------------|
| LLM | 大語言模型大全 | 大語言模型大全 ✅ |
| Investment | 投資理財 | 投資理財 ✅ |

**修復**:
- 更新 `skill_config.json` skill names 以符合資料庫
- 更新資料庫 instant attachments 的 `skill_name` 欄位

```sql
UPDATE skill_metadata SET skill_name = '大語言模型大全'
WHERE skill_name = 'LLM' AND parent_skill_id <> 'root';
```

#### 2. ✅ Rebuild Button Fix

**問題**: 更新 skill 名稱後 Rebuild 按鈕消失

**原因**: `attachmentCounts["LLM"] = 5` 但查詢 `attachmentCounts["大語言模型大全"]` 為 0

**解決**: 同步資料庫 instant attachments 的 skill_name

#### 3. ✅ Icon Mapping Updates

**檔案**: `template/skill_config.html`

```javascript
const icons = {
    '大語言模型大全': '✨', 'LLM': '✨', 'AI': '🤖',
    '民法': '📜', '刑法': '⚔️', '法': '⚖️', 'Legal': '⚖️',
    '投資理財': '💰', 'Investment': '💰', '投資': '💰'
    // ...
};
```

#### 4. ✅ Re-Build ALL Skills 確認 Modal

**變更**: Sidebar "Rebuild Skills" → "Re-Build ALL Skills" + 新增確認 Modal

**Modal 功能**:
- ⚠️ 警告圖示與說明文字
- 列出將執行的操作（清除索引、重新處理 PDF、重新生成嵌入）
- 顯示統計資訊（Skills 數、PDF 數、Attachments 數）
- 紅色「是的，進行完全重建」按鈕 + 「取消」按鈕

```javascript
// 新增函數
showRebuildConfirmModal()  // 顯示確認 Modal
executeFullRebuild()       // 執行完全重建 (force_all: true)
```

#### 5. ✅ start_system.sh - Milvus 檢查禁用

**原因**: 12/1, 12/2 Demo 使用 FAISS，不需要 Milvus

**變更**:
```bash
# Milvus Check - DISABLED for Demo (12/1, 12/2)
# Currently using FAISS for vector storage
print_info "向量儲存後端: FAISS (Demo 模式)"
print_success "FAISS 向量儲存已就緒"
```

### 修改的檔案

| 檔案 | 變更 |
|------|------|
| `scripts/skill_data/skill_config.json` | LLM → 大語言模型大全, Investment → 投資理財 |
| `template/skill_config.html` | getSkillIcon() 映射, Re-Build Modal, executeFullRebuild() |
| `data/skill_metadata.db` | instant attachments skill_name 更新 |
| `start_system.sh` | Milvus 檢查禁用，改用 FAISS Demo 模式 |

---

## 📅 Session Update - 2025-11-28 Morning (3-Level Tree UI & Multi-Select)

### 完成項目 (Completed This Session)

#### 1. ✅ Database Schema Enhancement

**變更**: 新增 `parent_skill_id` 欄位到 `skill_metadata` 表

```sql
ALTER TABLE skill_metadata ADD COLUMN parent_skill_id TEXT DEFAULT 'root';
CREATE INDEX idx_parent_skill_id ON skill_metadata(parent_skill_id);
```

**資料結構**:

| Skill | parent_skill_id | Type |
|-------|-----------------|------|
| LLM (883 chunks) | root | Main Skill |
| LLM (385 chunks) | skill_20251126_105138_b8cc08c1 | Instant Attachment |
| LLM (264 chunks) | skill_20251126_105138_b8cc08c1 | Instant Attachment |

#### 2. ✅ 3-Level Tree UI Implementation

**檔案**: `template/skill_main.html`

**功能**:

- 使用 `parent_skill_id` 建立正確階層結構
- Instant Attachments 顯示實際文件名（CSS揭秘、Decoding_Large_Language_Models）
- Group Header 顯示總 chunks 數（Main + Attachments）

**UI 結構**:

```text
📁 Skill Tree
├── 🧠 LLM (1532)
│   ├── 📚 Main (883)
│   ├── 📎 CSS揭秘 (264)
│   └── 📎 Decoding_Large_Language_Models (385)
├── 📜 六法全書-民法 (533)
└── ⚔️ 六法全書-刑法 (272)
```

#### 3. ✅ Multi-Select Query Functionality

**變更**:

- API `/demo/query` 支援 `skill_ids` array 參數
- 前端 `selectedSkills` 改為 array 支援多選
- 點擊 Group Header → 選擇 Main + 所有 Attachments
- 並行搜尋多個 skill indices

**測試結果**:

```text
Query: "CSS是什麼？"
Selected: LLM (3 項)
Result: 成功從 CSS揭秘 檢索相關內容
Footer: "📚 搜尋了 3 個知識庫"
```

#### 4. ✅ Source Name Fix

**問題**: 查詢結果顯示 "Unknown" 而非文件名

**解決**:

- API 建立 `skill_names` dict 映射 skill_id → 文件名
- 從 metadata.source_file 提取文件名
- 前端使用 `s.source_name` 顯示來源

### 修改的檔案

| 檔案 | 變更 |
|------|------|
| `app/Providers/skill_metadata_provider/client.py` | 新增 `parent_skill_id`, `source_name` |
| `app/api/v1/endpoints/skills.py` | Multi-skill query, citation 修正 |
| `template/skill_main.html` | 3-level tree, multi-select UI |
| `data/skill_metadata.db` | 新增 `parent_skill_id` 欄位 |

---

## 📅 Session Update - 2025-11-27 Evening (PDF Processing Pipeline)

### 完成項目 (Completed This Session)

#### 1. ✅ PDF Upload + Processing Pipeline
**問題**: 上傳 PDF 後只存檔，沒有進行文字提取、embedding 生成、FAISS 儲存。
**解決**:
- 新增 `process_pdf_for_skill()` helper function (lines 628-821)
- 修改 `upload_source_to_skill()` endpoint 自動觸發處理流程
- 完整流程：Save PDF → Extract Text (PyPDF2) → Generate Embeddings (BGE-M3) → Store FAISS → Store SQLite

**測試結果**:
```json
{
  "pages_extracted": 385,
  "chunks_created": 385,
  "embedding_model": "BAAI/bge-m3",
  "status": "success"
}
```

#### 2. ✅ Chat Functionality Verified
**測試**: Query "What is the difference between LLM pre-training and fine-tuning?"
**結果**: 成功從新上傳的 PDF 中檢索相關內容並回答

#### 3. ✅ UI Toggle Already Exists
**發現**: File/Skill 模式切換按鈕已存在
- `skill_main.html`: "切換至檔案模式" → `/SinglePDFQuery`
- `index.html`: "返回 Skill 模式" → `/skill`

#### 4. 📎 Instant Attachment Workflow

**說明**: 上傳 PDF 到既有 Skill 時，系統建立 Instant Attachment（非重複 skill）
**詳情**: 見 `claudedocs/instant_attachment_workflow_20251127.md`

| Skill | Chunks | Documents |
|-------|--------|-----------|
| LLM (Main) | 883 | Build_a_Large_Language_Model, LLM_Engineers_Handbook |
| LLM (Instant) | 385 | Decoding_Large_Language_Models |

**設計概念**: 三層架構 (Skill → Instant Attachments → Files)

```text
📁 Skill Tree
  └── 🧠 LLM (883 chunks - main)
        └── 📎 Instant Attachments
              └── Decoding_Large_Language_Models.pdf (385 chunks)
```

**Workflow**:

1. Upload PDF → Create Instant Attachment → Searchable Immediately
2. Accumulate 5-10 attachments → Trigger Full Skill Rebuild (避免碎片化)

---

## 🚀 Current Status & Next Steps

### Status

- **PDF Upload Pipeline**: ✅ Complete (extract → embed → store)
- **Chat Query**: ✅ Working with new skills
- **UI Toggle**: ✅ Already implemented
- **3-Level Tree UI**: ✅ Implemented (2025-11-28)
- **Multi-Select Query**: ✅ Implemented (2025-11-28)
- **Source Name Display**: ✅ Fixed (2025-11-28)

### Post-Demo Roadmap

1. ~~**Week 1**: Implement instant_attachments 3-level hierarchy~~ ✅ Done
2. ~~**Week 2**: Merged query (main skill + instant attachments)~~ ✅ Done
3. **Week 3**: Full OPMP integration for Skill system

---

## 📅 Session Update - 2025-11-27 Morning (Demo Prep)

### 完成項目 (Completed)

#### 1. ✅ Demo Scripts Fix
**問題**: `load_demo_skills.py` 執行失敗，出現 `ModuleNotFoundError`。
**解決**: 修正 `app.Providers` 引用與 `SkillIngestionService` 使用方式。

#### 2. ✅ Frontend UX Fix - PDF Upload
**問題**: `skill_config.html` 中點擊 "Add PDF" 無反應（檔案選取視窗未出現）。
**解決**:
- 移除有 Bug 的 Custom Drag & Drop UI。
- 改用原生 `<input type="file">`。
- 修正 Skill Name 轉義問題。

#### 3. ✅ Functional Fix - PDF Not Found
**問題**: 上傳 PDF 時後端報錯 400，因前端僅傳檔名而非檔案實體。
**解決**:
- **Frontend**: 改用 `FormData` 進行二進位上傳。
- **Backend**: 新增 `/upload-source` API 接收檔案並存檔。

#### 4. ✅ Documentation - GEMINI.md
**內容**: 建立專案上下文文件，定義 Dual RAG 架構與 RIPER-5 協議。

---

## 📅 Session Update - 2025-11-26 Evening

### 完成項目 (Completed Tonight)

#### 1. ✅ UI Enhancement - Loading Spinner
**檔案**: `template/skill_main.html`

**實作內容**:
- 新增全螢幕載入遮罩（Loading Overlay）
- 旋轉動畫 spinner
- 主文字：「正在進行搜尋......」
- 副文字：「系統正在檢索相關內容...」

**技術細節**:
```css
/* CSS 樣式 (Lines 519-578) */
.loading-overlay {
    display: none;
    position: fixed;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(4px);
    z-index: 9999;
}

.loading-spinner {
    width: 50px;
    height: 50px;
    border: 4px solid var(--input-bg);
    border-top: 4px solid var(--primary);
    animation: spin 1s linear infinite;
}
```

**JavaScript 控制** (Lines 832-867):
```javascript
// Show loading overlay before query
showLoading();

try {
    // Query processing...
} finally {
    hideLoading();
}
```

**使用者體驗**:
- 提交查詢 → 立即顯示載入動畫
- 背景模糊效果提升專注度
- 查詢完成 → 動畫消失，顯示結果

---

#### 2. ✅ Prompt Fix - "找不到資料" 誤判問題

**問題描述**:
系統在回答時第一句總是說「找不到相關內容」，但緊接著又提供正確答案。

**範例問題**:
- 問：「請說明LLM訓練分成哪幾個階段」
- 答：「在您目前選擇的文檔中，我沒有找到關於 LLM...」（然後提供完整答案）

**根本原因**:
`app/Services/prompt_service.py` 的系統提示詞中，「誠實評估」指令被 LLM 誤解為應該先執行「找不到」判斷，即使有相關內容。

**解決方案** (Lines 42-52):
```python
回答策略：
1. **直接使用上方文檔**：...
2. **優先引用文檔**：...
3. **智能補充說明**：...
4. **準確性優先**：不要編造文檔中不存在的內容
5. **重要：不要開頭就說「找不到」**：
   - ❌ 錯誤示範：「在您的文檔中，我沒有找到...（但實際內容如下）」
   - ✅ 正確做法：如果上方文檔有相關內容，直接回答問題並引用來源
   - 只有在上方文檔真的完全沒有任何相關資訊時，才說明找不到
```

**關鍵改進**:
1. 移除模糊的「誠實評估」指令
2. 明確禁止錯誤行為（❌ 和 ✅ 示範）
3. 調整指令順序，將警告放在最後強調

**影響範圍**:
- 修改檔案：`app/Services/prompt_service.py` (中英文版本)
- 重啟服務器：PID 33313
- 健康檢查：✅ Passed

**文檔**:
- 詳細報告：`claudedocs/prompt_response_fix_20251126.md`
- 處理機制分析：`claudedocs/no_data_found_handling_analysis.md`

---

#### 3. 📚 Documentation - "找不到資料" 處理機制分析

**檔案**: `claudedocs/no_data_found_handling_analysis.md`

**內容涵蓋**:
1. **四層處理架構**:
   - Level 1: Vector 檢索層（FAISS）
   - Level 2: Context 組裝層（PromptService）
   - Level 3: LLM 判斷層（System Prompt）
   - Level 4: API 錯誤處理層

2. **三種情境處理**:
   - 情境 A: 完全沒有資料
   - 情境 B: 有資料但不相關
   - 情境 C: 有相關資料

3. **完整流程圖**:
```
用戶提問
    ↓
Vector Retrieval (FAISS)
    ↓
    ├─→ 空結果 → "[無可用上下文]" → LLM: "找不到相關資訊"
    ├─→ 不相關 → 低品質chunks → LLM: 分析後判斷「找不到」
    └─→ 有相關 → 高品質chunks → LLM: 直接回答（不說「找不到」）
```

4. **Post-Demo 改進建議**:
   - 向量相似度閾值過濾
   - 前端相關度指示器
   - 智能知識庫推薦系統

---

#### 4. 🔍 OPMP 系統分析與未來計畫

**問題**: 用戶詢問過去常用的 OPMP 為何這次沒有使用

**OPMP 定義**:
- **全名**: Optimistic Progressive Markdown Parsing
- **位置**: `refData/Codes/opmp_kernel/`
- **用途**: File-Based 系統的 5 階段 RAG 管道

**5 階段架構**:
```
Phase 1: Query Understanding      # 問題理解與擴展
Phase 2: Parallel Retrieval       # 並行向量檢索
Phase 3: Context Assembly         # 上下文組裝
Phase 4: Response Generation      # 逐字串流輸出
Phase 5: Post Processing          # 後處理與歷史記錄
```

**OPMP 特色**:
- ✅ SSE (Server-Sent Events) 即時串流
- ✅ 進度追蹤（每階段顯示百分比）
- ✅ Token-by-token 輸出
- ✅ 查詢擴展（自動將問題擴展為多個子問題）
- ✅ 視覺化階段指示器

**為何未使用的原因**:

| 原因 | 說明 |
|------|------|
| **Demo 優先** | OPMP 複雜度高，不適合快速 demo |
| **系統分離** | Skill-Based 與 File-Based 完全隔離 |
| **時程考量** | 下周一、二就要 demo，採用簡化方案 |
| **複雜度** | 需要 SSE、5 階段協調、前端 EventSource 等 |

**當前對比**:

| Feature | File-Based (有 OPMP) | Skill-Based (當前) |
|---------|---------------------|-------------------|
| Endpoint | `/api/v1/chat` | `/api/v1/skills/demo/query` |
| Response | SSE Stream | Simple JSON |
| Progress | 5-phase tracking | Loading spinner only |
| Query Expansion | Yes | No |
| Token Streaming | Yes | No |

---

## 🚀 未來計畫 (Post-Demo Roadmap)

### Phase 1: 基礎串流 (Demo 後立即, Week 1)

**目標**: 為 Skill 系統增加基本 SSE 串流

**實作**:
```python
# New endpoint: /api/v1/skills/{skill_id}/chat/stream
@router.post("/skills/{skill_id}/chat/stream")
async def stream_skill_chat(...):
    async def event_generator():
        # Token-by-token streaming
        async for token in llm_client.stream_chat(...):
            yield {"event": "token", "data": token}

    return EventSourceResponse(event_generator())
```

**前端改動**:
```javascript
# Replace fetch with EventSource
const eventSource = new EventSource('/api/v1/skills/{skill_id}/chat/stream');

eventSource.addEventListener('token', (e) => {
    const token = JSON.parse(e.data);
    appendToken(token);  # 逐字顯示
});
```

**預期效果**:
- 使用者體驗提升（逐字顯示答案）
- 更接近 ChatGPT 的互動方式
- 減少等待焦慮感

---

### Phase 2: 進度追蹤 (Week 2)

**目標**: 增加 3 階段簡化版進度追蹤

**階段設計**:
```
Phase 1: Retrieval  (0-33%)   # 檢索相關 chunks
Phase 2: Generation (34-99%)  # 生成答案
Phase 3: Complete   (100%)    # 完成
```

**前端 UI**:
```javascript
# Progress bar
eventSource.addEventListener('progress', (e) => {
    const data = JSON.parse(e.data);
    updateProgressBar(data.phase, data.progress);
    updatePhaseLabel(data.phase_name);
});
```

**視覺設計**:
```
[████████░░░░░░░░] 33% - 正在檢索相關內容...
[████████████████] 99% - 正在生成答案...
[████████████████] 100% - 完成！
```

---

### Phase 3: 完整 OPMP 整合 (Week 3-4)

**目標**: 將完整 5 階段系統整合到 Skill

**階段規劃**:
1. **Phase 1: Query Understanding**
   - 問題意圖分析
   - 自動查詢擴展（1 個問題 → 3-5 個子問題）
   - 關鍵詞提取

2. **Phase 2: Parallel Retrieval**
   - 並行搜尋多個 skills
   - 智能分數排序
   - 去重合併

3. **Phase 3: Context Assembly**
   - 上下文優化排序
   - 相關度過濾
   - Citation 標註

4. **Phase 4: Response Generation**
   - Token-by-token 串流
   - Markdown 即時渲染
   - 引用來源標註

5. **Phase 5: Post Processing**
   - 儲存聊天歷史
   - 使用統計記錄
   - 自動改進建議

**技術挑戰**:
- SSE 連接穩定性
- 並行檢索效能優化
- 前端狀態管理
- 錯誤恢復機制

**預期時程**:
- Week 3: Phase 1-3 實作
- Week 4: Phase 4-5 實作 + 整合測試

---

### Phase 4: 企業級功能 (Month 2+)

**功能列表**:

1. **Master Index 優化**:
   ```python
   # 單一 skill 使用 merged index
   skill_master_index = merge_faiss_indices(file_indices)
   faiss.write_index(skill_master_index, f"skills/{skill_id}/master.index")
   ```

2. **Memory Management**:
   ```python
   # LRU cache for loaded indices
   @lru_cache(maxsize=5)
   def get_skill_index(skill_id: str):
       return faiss.read_index(f"skills/{skill_id}/master.index")
   ```

3. **向量相似度閾值過濾**:
   ```python
   RELEVANCE_THRESHOLD = 0.7  # 低於此值視為不相關

   filtered_results = [
       r for r in context_results
       if r.get('score', 1.0) < RELEVANCE_THRESHOLD
   ]
   ```

4. **前端相關度指示器**:
   ```javascript
   // 顯示檢索結果的相關度
   const relevance = (1 - score) * 100;
   const relevanceClass = relevance > 70 ? 'high' :
                          relevance > 50 ? 'medium' : 'low';
   ```

5. **智能知識庫推薦**:
   ```python
   def suggest_alternatives(query: str, available_skills: List[str]) -> List[str]:
       """根據問題內容，推薦可能相關的知識庫"""
       # 使用關鍵字匹配或 embedding 相似度
   ```

6. **並行搜尋優化**:
   - Asyncio 並行檢索多個 skills
   - 智能結果合併與去重
   - 分數正規化與排序

---

## Current Architecture Status

### Completed (95%)
✅ SkillMetadataProvider - SQLite persistence (725 lines)
✅ SkillIngestionService - Content processing (338 lines)
✅ AbstractRetrievalService - Polymorphic interface (182 lines)
✅ VectorStoreProvider - Modified for store_type isolation
✅ SkillRetrievalService - FAISS retrieval (145 lines)
✅ Directory structure and isolation
✅ API Endpoints - /api/v1/endpoints/skills.py with demo endpoints
✅ Pre-loaded Demo Skills - scripts/load_demo_skills.py
✅ Simple UI Toggle - template/skill_demo.html
✅ Demo Test Script - scripts/test_skill_demo.sh
✅ **Loading Spinner UI** - template/skill_main.html (NEW)
✅ **Prompt Response Fix** - app/Services/prompt_service.py (NEW)

### Pending (5%)
⏳ UnifiedRetrievalService - Orchestrator for file+skill
⏳ Feature Flags - Enable/disable skill system
⏳ Unit Tests - Core functionality validation

---

## Demo Approach (Easy-to-Achieve)

### Phase 1: Demo Ready (下周一、二) ✅ 已完成
1. ✅ **Simple UI Toggle**: Radio button for File vs Skill mode
2. ✅ **Pre-loaded Skills**: 2-3 demo skills with pre-generated embeddings
3. ✅ **Basic Query**: Direct skill search via `/api/v1/skills/chat`
4. ✅ **Fixed Configuration**: Hardcoded settings for demo stability
5. ✅ **Loading Spinner**: User-friendly loading animation (NEW)
6. ✅ **Prompt Fix**: 修正「找不到資料」誤判問題 (NEW)

### Demo 已就緒 🎉
- UI 體驗完整（loading animation + 清晰回答）
- Prompt 優化完成（不再誤報「找不到」）
- 系統穩定運行（Server PID: 33313）

---

## 📋 今晚修改的檔案清單

1. **template/skill_main.html**
   - 新增 loading overlay CSS (Lines 519-578)
   - 新增 loading overlay HTML (Lines 646-652)
   - 新增 showLoading/hideLoading 函數 (Lines 936-945)
   - 整合到 sendQuery 流程 (Lines 832-867)

2. **app/Services/prompt_service.py**
   - 修改系統提示詞 - 中文版 (Lines 42-52)
   - 修改系統提示詞 - 英文版 (Lines 147-157)
   - 重點：明確禁止「有資料時說找不到」的行為

3. **claudedocs/prompt_response_fix_20251126.md** (NEW)
   - 問題描述與根本原因分析
   - 解決方案詳細說明
   - 實施步驟與驗證結果
   - 預期效果與測試建議

4. **claudedocs/no_data_found_handling_analysis.md** (NEW)
   - 四層處理機制完整分析
   - 三種情境的處理邏輯
   - 完整流程圖
   - Post-Demo 改進建議

---

## Critical Files

### Skill Services
- `app/SkillServices/base_retrieval.py` - Abstract interface
- `app/SkillServices/skill_ingestion_service.py` - Content processing
- `app/SkillServices/skill_retrieval_service.py` - Vector retrieval

### Providers
- `app/Providers/skill_metadata_provider/client.py` - SQLite provider
- `app/Providers/vector_store_provider/client.py` - Modified for isolation

### Database
- `./data/skill_metadata.db` - Isolated skill metadata
- `./data/docai.db` - Original file metadata (untouched)

### FAISS Storage
- `/data/faiss_indices/files/` - File embeddings
- `/data/faiss_indices/skills/` - Skill embeddings

### Templates
- `template/skill_main.html` - Skill chat interface (含 loading spinner)

### Services
- `app/Services/prompt_service.py` - RAG prompt engineering (已修正)

### OPMP System (Future Integration)
- `refData/Codes/opmp_kernel/phase1_query_understanding.py`
- `refData/Codes/opmp_kernel/phase2_parallel_retrieval.py`
- `refData/Codes/opmp_kernel/phase3_context_assembly.py`
- `refData/Codes/opmp_kernel/phase4_response_generation.py`
- `refData/Codes/opmp_kernel/phase5_postprocessing.py`
- `app/api/v1/endpoints/chat.py` - File-Based system with OPMP

---

## Performance Optimization (Post-Demo)

### Master Index Strategy
```python
# Merge all file indices into single skill index
skill_master_index = merge_faiss_indices(file_indices)
faiss.write_index(skill_master_index, f"skills/{skill_id}/master.index")
```

### Memory Management
```python
# LRU cache for loaded skill indices
@lru_cache(maxsize=5)
def get_skill_index(skill_id: str):
    return faiss.read_index(f"skills/{skill_id}/master.index")
```

### Relevance Filtering (NEW)
```python
# Filter out low-relevance results
RELEVANCE_THRESHOLD = 0.7

filtered_results = [
    r for r in context_results
    if r.get('score', 1.0) < RELEVANCE_THRESHOLD
]

if not filtered_results:
    # Trigger "no relevant data found" flow
    context_chunks = []
```

---

## Key Design Decisions

1. **Physical Isolation**: Separate directories and databases
2. **Store Type Parameter**: "file" vs "skill" for FAISS isolation
3. **Larger Chunks**: 1000 chars for skills vs 500 for files
4. **ID Format**: `skill_{timestamp}_{uuid}_{hash}` for uniqueness
5. **Multi-Layer Data Processing**: Vector → Context → LLM → API (4 layers)
6. **Prompt Engineering**: Clear guidance to prevent false negatives

---

## Session Management

### Current Working Directory
```
/Users/xrickliao/WorkSpaces/Work/Projects/DocAI
```

### Git Branch
```
beta_skills_v01
```

### Active Server
```
PID: 33313
Status: Healthy ✅
Last Restart: 2025-11-26 22:46
```

---

## Quality Standards

- **Testing**: Never skip tests or validation
- **Evidence**: All claims must be verifiable
- **Isolation**: Never mix skill and file systems
- **Documentation**: Update claudedocs/ for all decisions
- **User Experience**: Loading feedback, clear error messages
- **Prompt Accuracy**: LLM must not fabricate "找不到" messages

---

## Communication Protocol

- Response in Traditional Chinese (技術術語保持原文)
- Focus on implementation over explanation
- Track progress with TodoWrite
- Save important decisions to claudedocs/

---

## 📚 相關文檔

### 今晚新增
- `claudedocs/prompt_response_fix_20251126.md` - Prompt 修正報告
- `claudedocs/no_data_found_handling_analysis.md` - 資料處理機制分析

### 既有文檔
- `claudedocs/RAG_prompt_best_practices_20251103.md` - Prompt 設計最佳實踐
- `claudedocs/dev_diary/20251125/retrieval_score_ranking_fix_20251125.md` - 檢索分數修復
- `claudedocs/skill_architecture_implementation_20251125.md` - Skill 架構實作

---

*SuperClaude Framework v2.0.1 for DocAI Project*
*Last Updated: 2025-11-28 (3-Level Tree UI & Multi-Select)*
*Demo Status: ✅ Ready for 下周一、二*
*Priority: Easy-to-achieve > Perfect solution*
*Next Phase: Post-Demo OPMP Integration*
