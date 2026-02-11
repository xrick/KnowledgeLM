<!-- claudedocs/modify_diary/batch_upload_ui_2026021116_30.md -->
# 修改日記: 批次上傳 UI 改版

**日期時間**: 2026-02-11 16:30
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟡 中

## 修改摘要
改版 Skill Config 頁面的檔案上傳介面，支援多檔選擇、目錄選擇、格式過濾、批次上傳與批次進度追蹤。

## 修改檔案
| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| template/skill_config.html | 修改 | CSS: 新增 ~200 行批次上傳相關樣式 |
| template/skill_config.html | 修改 | HTML: 改版 add-source-modal → 多檔+目錄選擇+格式 chips+樹狀檔案列表 |
| template/skill_config.html | 修改 | HTML: 改版 upload-progress-modal → 總進度條+檔案表格+可收合日誌+取消確認 |
| template/skill_config.html | 修改 | JS: 新增檔案選擇邏輯 (~250 行) — buildFileTree, renderTreeNode, toggleFormatFilter 等 |
| template/skill_config.html | 修改 | JS: 新增批次上傳邏輯 (~350 行) — batchState, processNextFile, handleBatchSSEEvent 等 |
| template/skill_config.html | 修改 | JS: 改版 addSource() → 使用批次上傳流程 |
| template/skill_config.html | 修改 | JS: 改版 showAddSourceModal() → 重設多檔狀態 |
| template/skill_config.html | 修改 | JS: 改版 resetUploadModal() → 適配批次進度 modal |
| static/i18n/ui_translations.json | 修改 | 新增 ~30 個批次上傳相關翻譯 key (中/英) |

## 為什麼這樣設計
- **前端 Queue + 復用現有 API**: 完全復用 `upload-source-stream` 單檔 API，後端零改動
- **樹狀目錄顯示**: 使用 `webkitRelativePath` 重建目錄結構
- **格式過濾 Chips**: 可視化的格式開關，預設全開
- **取消確認 Dialog**: 防止誤操作，已完成檔案保留

## 影響分析
- 影響範圍: Skill Config 頁面的檔案上傳流程
- 向後相容: 是 — 選擇 1 個檔案時行為與改版前一致
- 後端改動: 無 — 完全復用現有 API
- 需要測試:
  1. 單檔上傳（向下相容）
  2. 多檔選擇+上傳
  3. 目錄選擇+格式過濾
  4. 批次處理中取消
  5. 單檔失敗不中斷批次

## 回滾方案
```bash
git checkout -- template/skill_config.html static/i18n/ui_translations.json
```

## 驗證結果
- [x] CSS 樣式完整（樹狀列表、格式 chips、批次表格、狀態 badges、取消 dialog）
- [x] HTML Modal 結構正確（add-source-modal、upload-progress-modal）
- [x] 檔案選擇邏輯完整（多檔、目錄、格式過濾、勾選/取消）
- [x] 批次上傳邏輯完整（queue-based、SSE 分流、進度追蹤）
- [x] 取消功能完整（確認 dialog、中斷 SSE、狀態更新）
- [x] i18n 翻譯完整（中英文）
- [ ] 手動驗證通過（需啟動服務器測試）

## 新增功能清單
| 功能 | 說明 |
|------|------|
| 多檔選擇 | 點擊「選擇檔案」可同時選取多個檔案 |
| 目錄選擇 | 點擊「選擇目錄」選取整個資料夾 |
| 格式過濾 Chips | PDF/DOCX/PPTX/XLSX/XLS/CSV/MD/TXT 可視化開關 |
| 樹狀檔案列表 | 目錄選擇時以樹狀結構顯示，可展開/收合 |
| 全選/取消目錄 | 勾選目錄 checkbox 自動勾選子項目 |
| 不支援格式標示 | 不合規檔案以刪除線+⚠顯示 |
| 批次進度表格 | 每檔獨立顯示檔名、大小、狀態 badge、進度條 |
| 總進度條 | 綜合所有檔案的加權進度 |
| 可收合日誌 | 點擊展開/收合處理日誌 |
| 取消確認 Dialog | 取消時顯示已完成/未處理檔案數，確認後才取消 |
| 失敗不中斷 | 單檔失敗標記為「失敗」，自動處理下一檔 |
