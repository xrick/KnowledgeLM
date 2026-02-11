# 批次上傳與批次處理 UI 改版設計規劃

**日期**: 2026-02-11 16:00
**設計者**: Claude (SuperClaude Framework)
**狀態**: 規劃中 — 待用戶核准後方可實施
**設計參考圖**:
- `refData/design/add_multifiles_modified.png` → 新增檔案介面
- `refData/design/processing_multiple_files_UI.jpg` → 批次處理進度介面

---

## 1. 需求摘要

| 需求 | 說明 |
|------|------|
| 多檔選擇 | 使用者可同時選擇多個檔案 |
| 目錄選擇 | 使用者可選擇整個目錄，系統自動遍歷其中檔案 |
| 格式過濾 | 僅處理合規格式（PDF/DOCX/PPTX/TXT/MD），不符則略過並提示 |
| 批次上傳 | 逐檔上傳並處理，每檔顯示個別進度 |
| 總進度追蹤 | 顯示整體完成百分比、各檔案狀態與個別進度 |
| 處理日誌 | 可展開/收合的即時處理日誌（與現有 terminal style 一致） |

---

## 2. 現有架構盤點

### 2.1 前端 — skill_config.html

| 元件 | 位置 (行號) | 現狀 | 需變更 |
|------|------------|------|--------|
| `add-source-modal` | L1202-1314 | 單檔選擇 `<input type="file">` 無 `multiple` | ✅ 需改為多檔+目錄 |
| `upload-progress-modal` | L1684-1861 | 單檔進度（檔名/大小/進度條/日誌） | ✅ 需改為批次進度表格 |
| `addSource()` | L3165-3311 | `files[0]` 只取第一檔，單一 SSE 連線 | ✅ 需改為 queue-based 循序處理 |
| `handleSSEEvent()` | L3313-3560+ | 處理單檔 SSE 事件 | ✅ 需增加 file-level 事件分流 |
| `showAddSourceModal()` | L2870-2883 | 重設單檔輸入 | ✅ 需重設多檔列表 |

### 2.2 後端 — app/api/v1/endpoints/skills.py

| Endpoint | 行號 | 現狀 | 需變更 |
|----------|------|------|--------|
| `upload_source_to_skill_stream` | L2412-2519 | `file: UploadFile = File(...)` 單檔 | ❌ 不改 |
| `upload_source_to_skill` | L2522-2647 | 同上 | ❌ 不改 |
| `create_upload_sse_event` | — | SSE event formatter | ❌ 不改 |

### 2.3 檔案格式驗證

| 層級 | 位置 | 格式 |
|------|------|------|
| 後端 (settings) | `app/core/config.py:99-101` | `["pdf", "docx", "pptx", "txt", "md"]` |
| 前端 (addSource) | `skill_config.html:3181-3187` | `[".pdf", ".docx", ".pptx", ".txt", ".md"]` |
| HTML accept | `skill_config.html:1239` | `accept=".pdf,.docx,.pptx,.txt,.md"` |

---

## 3. 設計決策

### 3.1 核心策略：前端 Queue + 復用現有單檔 API

```
方案A ✅ 前端循序呼叫現有 API（選擇此方案）
方案B ❌ 新增 batch upload endpoint

選擇理由：
1. 完全復用現有 upload-source-stream API → 後端零改動
2. SSE pipeline 已穩定運行 → 不需重新設計
3. 前端 queue-based 批次是業界常見模式
4. 符合 reuse_codes_prompt.md「不修改後端」原則
```

### 3.2 批次處理流程

```
使用者選擇多檔/目錄
    ↓
前端過濾不合規格式 → 提示被略過的檔案
    ↓
顯示檔案清單（含 checkbox），使用者確認
    ↓
開始批次上傳 → 開啟批次進度 Modal
    ↓
對每個檔案循序執行：
    ├── 更新檔案狀態為「處理中」
    ├── 呼叫 /upload-source-stream (FormData)
    ├── 接收 SSE 事件 → 更新該檔個別進度
    ├── 完成 → 更新狀態為「完成」，推進至下一檔
    └── 錯誤 → 標記為「失敗」，繼續下一檔
    ↓
全部完成 → 更新總進度為 100%，啟用「完成」按鈕
```

---

## 4. UI 設計規格

### 4.1 新增檔案 Modal（改版 add-source-modal）

參照 `add_multifiles_modified.png`：

```
┌─────────────────────────────────────────────┐
│  新增文件來源                             ✕  │
├─────────────────────────────────────────────┤
│                                             │
│  技能:  [ 大語言模型大全        ] (readonly) │
│                                             │
│  選擇文件:                                  │
│  ┌─────────────┐ ┌──────────────┐          │
│  │ 📁 選擇檔案  │ │ 📂 選擇目錄   │          │
│  └─────────────┘ └──────────────┘          │
│                                             │
│  格式過濾:                                  │
│  [✓ PDF] [✓ DOCX] [✓ PPTX] [ MD] [ TXT]   │
│                                             │
│  ── Upload Files List ──────────────────    │
│  │ ☑ Building_LLMs.pdf         5.98MB  │   │
│  │ ☑ Data_Analysis.pdf         2.1MB   │   │
│  │ ☑ ML_Specs.docx             1.4MB   │   │
│  │ ☐ readme.txt                12KB    │   │
│  │ ⚠ image.jpg (不支援格式)            │   │
│  ─────────────────────────────────────     │
│  已選: 3 個檔案 | 略過: 1 個不支援格式      │
│                                             │
├─────────────────────────────────────────────┤
│                    [ 取消 ] [ 開始上傳 ]      │
└─────────────────────────────────────────────┘
```

**HTML 元件規格：**

| 元件 | ID | 說明 |
|------|-----|------|
| 多檔選擇 input | `multi-file-input` | `<input type="file" multiple accept="...">` |
| 目錄選擇 input | `dir-file-input` | `<input type="file" webkitdirectory>` |
| 格式過濾 chips | `format-filter-{ext}` | checkbox chips，預設全選 |
| 檔案列表容器 | `upload-file-list` | 動態生成的檔案清單 |
| 已選統計 | `selected-files-summary` | "已選 N 個檔案 \| 略過 M 個" |
| 開始上傳按鈕 | `btn-start-batch-upload` | disabled when 0 files selected |

**JavaScript 函數：**

| 函數 | 說明 |
|------|------|
| `handleMultiFileSelected()` | 處理多檔選擇，過濾格式，更新列表 |
| `handleDirSelected()` | 處理目錄選擇，遞歸列出檔案，過濾格式 |
| `toggleFormatFilter(ext)` | 切換格式過濾 chip，重新篩選列表 |
| `toggleFileSelection(index)` | 切換單一檔案的選取狀態 |
| `updateFileListUI()` | 重新渲染檔案列表與統計 |
| `getSelectedFiles()` | 回傳被勾選的 File 物件陣列 |

### 4.2 批次處理進度 Modal（改版 upload-progress-modal）

參照 `processing_multiple_files_UI.jpg`：

```
┌──────────────────────────────────────────────────┐
│  ☁ 批次上傳處理 - 大語言模型大全              ✕   │
├──────────────────────────────────────────────────┤
│                                                  │
│  總進度: 45%                              100%   │
│  [████████████░░░░░░░░░░░░░░░]                   │
│                                                  │
│  ┌────────────────┬──────┬───────┬────────┐     │
│  │ 檔案名稱        │ 大小  │ 狀態   │ 進度    │     │
│  ├────────────────┼──────┼───────┼────────┤     │
│  │ Building_LLMs  │5.98MB│ 處理中 │ ████ 60%│     │
│  │ Data_Analysis  │2.1MB │ 排隊中 │ ░░░░  0%│     │
│  │ ML_Specs.docx  │1.4MB │ 排隊中 │ ░░░░  0%│     │
│  └────────────────┴──────┴───────┴────────┘     │
│                                                  │
│  ▶ 處理日誌 - Building_LLMs_for_Production.pdf   │
│  ┌──────────────────────────────────────────┐   │
│  │ [15:45:10] Chunk 365/608: Processing...  │   │
│  │ [15:45:11] Chunk 360/608: Processing...  │   │
│  │ [15:45:12] Chunk 375/608: Processing...  │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
├──────────────────────────────────────────────────┤
│       ⏱ 經過時間: 5m 8s           [ ✓ 完成 ]     │
└──────────────────────────────────────────────────┘
```

**HTML 元件規格：**

| 元件 | ID | 說明 |
|------|-----|------|
| 標題 | `batch-progress-title` | "批次上傳處理 - {SkillName}" |
| 總進度百分比 | `batch-overall-percent` | "總進度: 45%" |
| 總進度條 | `batch-overall-bar` | 整體完成百分比 |
| 檔案表格 | `batch-file-table` | 動態生成的 `<table>` |
| 日誌標題 | `batch-log-header` | 可點擊展開/收合 |
| 日誌內容 | `batch-logs` | 與現有 terminal style 一致 |
| 經過時間 | `batch-elapsed` | 總經過時間 |
| 完成按鈕 | `btn-batch-complete` | 全部完成後才 enabled |

**檔案狀態定義：**

| 狀態 | Badge 樣式 | 說明 |
|------|-----------|------|
| `排隊中` | 灰底灰字 | 等待處理 |
| `處理中` | 藍底白字 | 正在上傳+處理 |
| `完成` | 綠底白字 | 處理成功 |
| `失敗` | 紅底白字 | 處理失敗 |
| `已略過` | 黃底黑字 | 格式不支援被略過 |

**JavaScript 函數：**

| 函數 | 說明 |
|------|------|
| `startBatchUpload(skillName, files)` | 初始化批次流程，開啟 Modal |
| `processNextFile()` | 從 queue 取出下一個檔案，呼叫 API |
| `updateFileRow(index, status, progress)` | 更新表格中特定檔案的狀態與進度 |
| `updateOverallProgress()` | 計算並更新總進度 |
| `handleBatchSSEEvent(fileIndex, data)` | SSE 事件分流到對應檔案 |
| `toggleBatchLogs()` | 展開/收合處理日誌 |
| `finalizeBatch()` | 全部完成後的收尾工作 |

---

## 5. 核心邏輯設計

### 5.1 批次上傳 State Machine

```javascript
// 批次上傳狀態管理
const batchState = {
    skillName: "",
    files: [],           // { file: File, status, progress, error }
    currentIndex: -1,     // 當前處理中的檔案索引
    startTime: null,
    isComplete: false,
    isCancelled: false,
};
```

### 5.2 總進度計算公式

```
overallProgress = (completedFiles * 100 + currentFileProgress) / totalFiles

例：3 個檔案，第 1 個完成(100%)，第 2 個進行中(60%)，第 3 個排隊(0%)
= (1 * 100 + 60) / 3
= 160 / 3
= 53%
```

### 5.3 目錄選擇的檔案過濾

```javascript
function handleDirSelected(event) {
    const allFiles = Array.from(event.target.files);
    const allowedExts = getActiveFormatFilters(); // 從 chips 取得

    const validFiles = [];
    const skippedFiles = [];

    for (const file of allFiles) {
        const ext = "." + file.name.split(".").pop().toLowerCase();
        if (allowedExts.includes(ext)) {
            validFiles.push(file);
        } else {
            skippedFiles.push({ name: file.name, reason: "不支援的格式" });
        }
    }

    // 更新 UI
    updateFileListUI(validFiles, skippedFiles);
}
```

### 5.4 循序上傳流程（復用現有 API）

```javascript
async function processNextFile() {
    if (batchState.isCancelled) return;

    batchState.currentIndex++;
    if (batchState.currentIndex >= batchState.files.length) {
        finalizeBatch();
        return;
    }

    const fileItem = batchState.files[batchState.currentIndex];
    fileItem.status = "處理中";
    updateFileRow(batchState.currentIndex, "處理中", 0);

    const formData = new FormData();
    formData.append("file", fileItem.file);

    try {
        const safeSkillName = encodeURIComponent(batchState.skillName);
        // ★ 復用現有 upload-source-stream API
        const response = await fetch(
            `/api/v1/skills/config/skills/${safeSkillName}/upload-source-stream`,
            { method: "POST", body: formData }
        );

        // 讀取 SSE stream，更新個別檔案進度
        const reader = response.body.getReader();
        // ... (復用現有 SSE 解析邏輯)

        fileItem.status = "完成";
        fileItem.progress = 100;
    } catch (e) {
        fileItem.status = "失敗";
        fileItem.error = e.message;
    }

    updateFileRow(batchState.currentIndex, fileItem.status, fileItem.progress);
    updateOverallProgress();

    // 處理下一個
    processNextFile();
}
```

---

## 6. 修改檔案清單

| 檔案 | 變更類型 | 範圍 | 說明 |
|------|----------|------|------|
| `template/skill_config.html` | 修改 | Modal HTML | 改版 add-source-modal → 多檔+目錄選擇+檔案列表 |
| `template/skill_config.html` | 修改 | Modal HTML | 改版 upload-progress-modal → 批次進度表格+日誌 |
| `template/skill_config.html` | 修改 | JavaScript | 改版 addSource() → startBatchUpload() + processNextFile() |
| `template/skill_config.html` | 修改 | JavaScript | 新增多檔/目錄選擇 handler functions |
| `template/skill_config.html` | 修改 | CSS | 新增批次表格樣式、格式過濾 chips 樣式 |
| `app/api/v1/endpoints/skills.py` | **不改** | — | 完全復用現有 upload-source-stream API |
| `app/core/config.py` | **不改** | — | ALLOWED_EXTENSIONS 不變 |

---

## 7. 不需修改的部分（復用清單）

| 元件 | 位置 | 復用說明 |
|------|------|---------|
| `upload-source-stream` API | skills.py:2412 | 逐檔呼叫，復用整個 SSE pipeline |
| `process_pdf_for_skill_streaming()` | skills.py | PDF 處理流程完全復用 |
| `process_document_for_skill_streaming()` | skills.py | DOCX/TXT/MD 處理流程完全復用 |
| `create_upload_sse_event()` | skills.py | SSE 格式化完全復用 |
| `handleSSEEvent()` 內部邏輯 | skill_config.html:3313 | 事件解析邏輯復用，只加一層 file-index 分流 |
| `ALLOWED_EXTENSIONS` | config.py:99 | 格式驗證規則復用 |
| `appendUploadLog()` | skill_config.html | 日誌追加函數復用 |
| `formatFileSize()` | skill_config.html | 檔案大小格式化復用 |
| `startElapsedTimer()` / `stopElapsedTimer()` | skill_config.html | 計時器復用 |

---

## 8. 實作順序（階段規劃）

### Phase 1: 多檔選擇 Modal（僅前端）

```
1. 修改 add-source-modal HTML → 加入 multiple input + directory input
2. 新增格式過濾 chips 的 HTML + CSS
3. 新增 Upload Files List 的 HTML
4. 實作 handleMultiFileSelected() / handleDirSelected()
5. 實作 updateFileListUI() / toggleFileSelection()
6. 實作 getSelectedFiles() — 回傳勾選的 File[]
```

### Phase 2: 批次進度 Modal（僅前端）

```
1. 改版 upload-progress-modal HTML → 總進度條 + 檔案表格 + 可展開日誌
2. 新增檔案表格 CSS（狀態 badges、進度條）
3. 實作 startBatchUpload() — 初始化 batchState
4. 實作 updateFileRow() / updateOverallProgress()
5. 實作 toggleBatchLogs() — 展開/收合日誌
```

### Phase 3: 批次上傳流程（前端邏輯）

```
1. 實作 processNextFile() — queue-based 循序處理
2. 將 handleSSEEvent() 包裝為 handleBatchSSEEvent(fileIndex, data)
3. 實作 finalizeBatch() — 全部完成後的收尾
4. 實作取消功能（中斷當前 SSE + 清理 queue）
5. 錯誤處理：單檔失敗不中斷批次
```

### Phase 4: 整合測試

```
1. 單檔上傳（向下相容）
2. 多檔選擇 + 上傳
3. 目錄選擇 + 格式過濾
4. 混合格式（含不支援格式）
5. 大檔批次（SSE 進度正確性）
6. 錯誤復原（單檔失敗→繼續下一檔）
```

---

## 9. 風險評估

| 風險 | 等級 | 緩解措施 |
|------|------|---------|
| SSE 連線中斷 | 🟡 中 | 每檔獨立 SSE 連線，一個中斷不影響其他 |
| 大量檔案 memory | 🟡 中 | 前端持有 File 物件 reference，不一次讀入所有內容 |
| 目錄選擇瀏覽器相容性 | 🟢 低 | `webkitdirectory` 已被 Chrome/Edge/Firefox 支援 |
| 向下相容（單檔流程） | 🟢 低 | 選擇 1 個檔案時等同現有流程 |

---

## 10. 限制與約束

- ✅ **後端零改動**：完全復用 `upload-source-stream` API
- ✅ **格式驗證雙重保障**：前端 chips + 後端 ALLOWED_EXTENSIONS
- ✅ **不支援格式處理**：略過並在列表中標示 ⚠️，不強制處理
- ✅ **目錄中的子目錄**：`webkitdirectory` 會自動遞歸列出所有檔案
- ✅ **向下相容**：選擇 1 個檔案時行為與現有完全一致

---

## 11. 補充設計（用戶確認項目）

### 11.1 樹狀目錄結構顯示（圖1 檔案列表）

**確認結果**：選擇目錄後，檔案列表需顯示「樹狀目錄結構」。

**實作方式**：利用 `webkitRelativePath` 重建樹狀：

```javascript
// webkitdirectory 回傳的 File 物件含有 webkitRelativePath
// 例: "Work Documents/sub/report.pdf"

function buildFileTree(files) {
    const tree = {};
    for (const file of files) {
        const parts = file.webkitRelativePath.split("/");
        let node = tree;
        for (let i = 0; i < parts.length - 1; i++) {
            // 建立目錄節點
            if (!node[parts[i]]) {
                node[parts[i]] = { _isDir: true, _children: {} };
            }
            node = node[parts[i]]._children;
        }
        // 掛載檔案
        node[parts[parts.length - 1]] = {
            _isDir: false,
            _file: file,
            _ext: "." + file.name.split(".").pop().toLowerCase(),
        };
    }
    return tree;
}
```

**UI 渲染**：

```
── Upload Files List ───────────────────────
│ 📂 Work Documents                        │  ← 目錄節點（可展開/收合）
│   ├ ☑ 📄 Functional Specifications.pdf   │  ← 檔案節點
│   ├ ☑ 📄 Feature Schedule.docx           │
│   ├ ☑ 📄 Overall Project Plan.pdf        │
│   ├ ☐ 📄 Paint Color Scheme.txt          │
│   └ ⚠ 🚫 logo.jpg (不支援格式)           │  ← 不合規顯示
│ 📂 另一個目錄                              │
│   └ ☑ 📄 report.pdf                      │
────────────────────────────────────────────
已選: 4 個檔案 | 略過: 1 個不支援格式
```

**新增 JavaScript 函數：**

| 函數 | 說明 |
|------|------|
| `buildFileTree(files)` | 從 webkitRelativePath 建構樹狀結構 |
| `renderFileTree(tree, container, depth)` | 遞歸渲染樹狀 HTML（含縮排） |
| `toggleDirNode(dirPath)` | 展開/收合目錄節點 |
| `selectAllInDir(dirPath, checked)` | 勾選/取消目錄下所有檔案 |

**新增 CSS：**

```css
.file-tree-item {
    display: flex;
    align-items: center;
    padding: 0.375rem 0.5rem;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
}
.file-tree-item:hover {
    background: rgba(59, 130, 246, 0.05);
}
.file-tree-dir {
    font-weight: 600;
    color: var(--text);
}
.file-tree-indent {
    /* 每層縮排 1.25rem */
    padding-left: calc(var(--depth, 0) * 1.25rem);
}
.file-tree-skipped {
    opacity: 0.5;
    text-decoration: line-through;
}
```

**目錄勾選行為**：
- 勾選目錄 checkbox → 自動勾選目錄下所有合規檔案
- 取消目錄 checkbox → 自動取消目錄下所有檔案
- 部分勾選時 → 目錄 checkbox 顯示 indeterminate 狀態

---

### 11.2 取消+確認 Dialog（圖2 批次處理中）

**確認結果**：需要取消功能，且取消時彈出確認 Dialog。

**UI 行為設計**：

```
處理進行中時：
┌──────────────────────────────────────────────────┐
│  Footer:                                         │
│  ⏱ 經過時間: 5m 8s    [ ✖ 取消 ] [ ✓ 完成(disabled) ] │
└──────────────────────────────────────────────────┘

全部完成後：
┌──────────────────────────────────────────────────┐
│  Footer:                                         │
│  ⏱ 經過時間: 12m 30s          [ ✓ 完成(enabled) ] │
└──────────────────────────────────────────────────┘
```

**取消確認 Dialog：**

```
┌────────────────────────────────────────┐
│  ⚠️ 確定取消批次處理？                  │
├────────────────────────────────────────┤
│                                        │
│  已完成的檔案（2/5）將保留，不受影響。  │
│  尚未處理的 3 個檔案將跳過。            │
│  正在處理中的檔案將中斷。               │
│                                        │
├────────────────────────────────────────┤
│          [ 繼續處理 ] [ 確定取消 ]       │
└────────────────────────────────────────┘
```

**取消流程：**

```javascript
function requestCancelBatch() {
    const completed = batchState.files.filter(f => f.status === "完成").length;
    const remaining = batchState.files.filter(f => f.status === "排隊中").length;
    const total = batchState.files.length;

    // 顯示確認 Dialog
    showConfirmDialog({
        title: "確定取消批次處理？",
        messages: [
            `已完成的檔案（${completed}/${total}）將保留，不受影響。`,
            `尚未處理的 ${remaining} 個檔案將跳過。`,
            `正在處理中的檔案將中斷。`,
        ],
        confirmText: "確定取消",
        cancelText: "繼續處理",
        onConfirm: executeCancelBatch,
    });
}

function executeCancelBatch() {
    batchState.isCancelled = true;

    // 中斷當前 SSE reader (如果有)
    if (batchState.currentReader) {
        batchState.currentReader.cancel();
    }

    // 將排隊中的檔案標為「已取消」
    for (const fileItem of batchState.files) {
        if (fileItem.status === "排隊中") {
            fileItem.status = "已取消";
            updateFileRow(fileItem.index, "已取消", 0);
        }
        if (fileItem.status === "處理中") {
            fileItem.status = "已中斷";
            updateFileRow(fileItem.index, "已中斷", fileItem.progress);
        }
    }

    updateOverallProgress();
    stopElapsedTimer();

    // 切換按鈕：隱藏取消，顯示完成
    document.getElementById("btn-batch-cancel").style.display = "none";
    document.getElementById("btn-batch-complete").style.display = "inline-flex";
    document.getElementById("btn-batch-complete").disabled = false;
}
```

**新增檔案狀態（更新 §4.2 表格）：**

| 狀態 | Badge 樣式 | 說明 |
|------|-----------|------|
| `排隊中` | 灰底灰字 | 等待處理 |
| `處理中` | 藍底白字 | 正在上傳+處理 |
| `完成` | 綠底白字 | 處理成功 |
| `失敗` | 紅底白字 | 處理出錯 |
| `已略過` | 黃底黑字 | 格式不支援 |
| `已取消` | 灰底橙字 | 用戶取消，未處理 |
| `已中斷` | 橙底白字 | 用戶取消，處理中斷 |

**右上角 X 按鈕行為**：
- 處理進行中 → 觸發 `requestCancelBatch()`（與取消按鈕相同）
- 處理已完成 → 直接關閉 Modal

---

### 11.3 更新實作順序

Phase 1 新增：
```
+ 1.7 實作 buildFileTree() — 從 webkitRelativePath 建構樹狀
+ 1.8 實作 renderFileTree() — 遞歸渲染樹狀 HTML
+ 1.9 實作 toggleDirNode() / selectAllInDir()
+ 1.10 新增 .file-tree-* CSS 樣式
```

Phase 3 新增：
```
+ 3.6 實作 requestCancelBatch() — 取消確認 Dialog
+ 3.7 實作 executeCancelBatch() — 中斷 SSE + 更新狀態
+ 3.8 X 按鈕行為：處理中→取消確認 / 已完成→直接關閉
```

Phase 4 新增測試項：
```
+ 4.7 目錄選擇 → 樹狀結構正確顯示
+ 4.8 目錄 checkbox → 全選/取消子項目
+ 4.9 批次處理中取消 → 確認 Dialog → 正確中斷
+ 4.10 取消後已完成檔案保留驗證
```

---

*本設計文件待用戶核准後方可開始實施。未經允許不修改任何現有程式碼。*
*v1.1 — 2026-02-11 更新：加入樹狀結構 + 取消確認 Dialog 設計。*
