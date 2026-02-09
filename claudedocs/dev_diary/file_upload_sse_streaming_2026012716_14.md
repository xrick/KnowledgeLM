# 修改日記: File-Based 系統新增 SSE 上傳進度串流

**日期時間**: 2026-01-27 16:14
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟡 中

## 修改摘要
為 File-Based 上傳系統（index.html）新增 SSE (Server-Sent Events) 串流進度功能，讓使用者上傳 PDF/DOCX/PPTX/TXT/MD 時能即時看到處理進度（文字提取→分塊→向量嵌入→儲存），參考 Skill-Based 系統已有的 SSE 實作模式。

## 修改檔案
| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| `app/api/v1/endpoints/upload.py` | 新增 | `create_upload_sse_event()` helper、`process_file_streaming()` async generator (7 phases)、`POST /api/v1/upload/stream` SSE endpoint |
| `static/js/docai-client.js` | 新增 | `uploadFileStream(file, onEvent)` 方法，使用 ReadableStreamReader 消費 SSE 事件 |
| `template/index.html` | 新增+修改 | CSS 進度 modal 樣式、HTML 進度 modal 結構、JavaScript SSE 事件處理 (`handleSSEEvent`) 與進度 UI 控制 |

## 詳細變更

### 1. upload.py — 後端 SSE Endpoint

**新增函數：**
- `create_upload_sse_event(event_type, data)` — SSE 事件格式化（與 skills.py 一致）
- `process_file_streaming()` — Async generator，7 個處理階段逐步 yield SSE 事件：
  - Phase 1: Validation (5%)
  - Phase 2: Text Extraction (10-25%)
  - Phase 3: Chunking (30-35%)
  - Phase 4: Metadata Storage (40%)
  - Phase 5: Embedding (45-80%)
  - Phase 6: File Save (85%)
  - Phase 7: Overview Generation (90%)
  - Complete (100%)

**新增 Endpoint：**
- `POST /api/v1/upload/stream` — 接收 file + X-User-ID，返回 `EventSourceResponse`

**Reuse：** `InputDataHandleService`（提取/分塊）、`RetrievalService`（嵌入儲存）、`FileMetadataProvider`（元資料）

### 2. docai-client.js — 前端 SSE Consumer

**新增方法：** `uploadFileStream(file, onEvent)`
- 使用 `fetch()` + `ReadableStreamReader` + `TextDecoder` 消費 SSE stream
- 解析 `event:` 和 `data:` 行，呼叫 `onEvent(eventType, parsedData)` callback
- 追蹤 `complete` 事件，存入 `uploadedFiles` map
- 遇到 `error` 事件則 throw Error

### 3. index.html — 進度 Modal UI

**CSS 新增（~170 行）：**
- `.upload-progress-overlay` 全螢幕遮罩
- `.upload-progress-modal` 進度視窗（header、file info、progress bar、logs、footer）
- `.prog-status-badge` 狀態標籤（處理中/完成/失敗三種樣式）

**HTML 新增：**
- 完整進度 modal 結構：標題列、檔案資訊區、進度條、處理日誌（暗色背景 monospace）、底部按鈕區

**JavaScript 修改：**
- `confirmUploadBtn` handler 從 `uploadFile()` 改為 `uploadFileStream()`
- 新增函數：`showProgressModal()`、`hideProgressModal()`、`appendLog()`、`updateProgress()`、`handleSSEEvent()`
- `handleSSEEvent()` 根據後端 event type（start/file_saved/progress/checkpoint/complete/error/warning）更新 UI
- 計時器顯示已經過時間
- 「取消」按鈕支援中斷上傳

## 事件類型對應表

| 後端 event type | 後端 data.phase | 前端 UI 顯示 |
|----------------|----------------|-------------|
| `start` | — | 開始處理... (2%) |
| `file_saved` | — | 檔案已接收 (5%) |
| `progress` | `validation` | 檔案驗證通過 (5%) |
| `progress` | `extraction` | 正在提取文字... (10%) |
| `progress` | `extraction_complete` | 文字提取完成 (25%) |
| `progress` | `chunking` | 正在分割文字... (30%) |
| `checkpoint` | `chunking_complete` | 文字分塊完成 (35%) |
| `progress` | `metadata` | 儲存檔案元資料... (40%) |
| `progress` | `embedding` | 正在生成向量嵌入... (45%) |
| `progress` | `embedding_complete` | 向量嵌入完成 (80%) |
| `progress` | `saving` | 儲存檔案到磁碟... (85%) |
| `progress` | `overview` | 生成文件摘要... (90%) |
| `complete` | — | 處理完成！ (100%) |
| `error` | — | 處理失敗 |

## 影響分析
- 影響範圍: File-Based 上傳系統（index.html 頁面）
- 向後相容: 是。原有 `uploadFile()` 方法未刪除，`POST /api/v1/upload` 原 endpoint 不變
- 需要測試: 上傳 PDF/DOCX/PPTX/TXT/MD 各一次，確認進度條正常更新

## 回滾方案
1. `template/index.html`: 還原 `confirmUploadBtn` handler 回使用 `uploadFile()` 即可
2. `static/js/docai-client.js`: 移除 `uploadFileStream()` 方法
3. `app/api/v1/endpoints/upload.py`: 移除 `create_upload_sse_event()`、`process_file_streaming()`、`upload_file_stream()` 三個函數

## 驗證結果
- [x] 後端 SSE event format 與 skills.py 一致
- [x] 前端 SSE 解析邏輯正確處理 event:/data: 行
- [x] handleSSEEvent 正確對應後端所有 event type（start/file_saved/progress/checkpoint/complete/error/warning）
- [x] 進度百分比來自後端 data.percent，非前端 hardcode
- [ ] 整合測試（需啟動服務後手動驗證）
