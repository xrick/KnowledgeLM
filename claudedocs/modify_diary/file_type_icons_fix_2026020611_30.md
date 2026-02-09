# 修改日記: 文件類型圖示修復

**日期時間**: 2026-02-06 11:30
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟢 低

## 修改摘要
修復 skill/config 頁面的文件類型圖示功能，讓不同類型的文件顯示對應的彩色圖示（PDF=紅色, DOCX=藍色, PPTX=橘色等）

## 問題根因
資料庫中的 `source_name` 欄位不包含副檔名（因 Python `Path().stem` 移除），導致前端 `getFileTypeIcon()` 函數無法判斷文件類型，所有文件都顯示預設的灰色圖示。

## 解決方案
1. 修改後端 SQL 查詢，將 `metadata` 欄位加入返回資料
2. 前端從 `metadata.source_file` 提取完整路徑（包含副檔名）來判斷文件類型

## 修改檔案
| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| app/Providers/skill_metadata_provider/client.py | 修改 | Line 1384: SQL SELECT 加入 `metadata` 欄位 |
| template/skill_config.html | 修改 | Lines 2552-2562: 從 metadata.source_file 提取副檔名 |

## 程式碼變更

### 後端 (client.py)
```sql
-- 修改前
SELECT skill_id, skill_name, skill_description, skill_category,
       total_chunks, source_name, parent_skill_id, head_id,
       created_at, updated_at
FROM skill_metadata

-- 修改後
SELECT skill_id, skill_name, skill_description, skill_category,
       total_chunks, source_name, parent_skill_id, head_id,
       created_at, updated_at, metadata  -- 新增 metadata
FROM skill_metadata
```

### 前端 (skill_config.html)
```javascript
// 修改前
const fileIcon = getFileTypeIcon(doc.source_name);

// 修改後
let sourceFileForIcon = doc.source_name || "";
if (doc.metadata) {
    try {
        const meta = typeof doc.metadata === 'string' ? JSON.parse(doc.metadata) : doc.metadata;
        if (meta.source_file) {
            sourceFileForIcon = meta.source_file;
        }
    } catch (e) { /* use fallback */ }
}
const fileIcon = getFileTypeIcon(sourceFileForIcon);
```

## 影響分析
- 影響範圍: skill/config 頁面的文件列表顯示
- 向後相容: 是（若 metadata 不存在則 fallback 到 source_name）
- 需要測試: 刷新 skill/config 頁面，展開 skill 卡片確認文件圖示正確顯示

## 回滾方案
1. 後端: 將 `metadata` 從 SELECT 語句中移除
2. 前端: 將 Lines 2552-2562 還原為單行 `const fileIcon = getFileTypeIcon(doc.source_name);`

## 驗證結果
- [x] 後端 SQL 語法正確
- [x] 前端 JavaScript 語法正確
- [ ] 手動驗證 - 需重啟服務後在瀏覽器確認

## 圖示對照表
| 副檔名 | 圖示 | 顏色 |
|--------|------|------|
| .pdf | fa-file-pdf | 紅色 #ef4444 |
| .doc/.docx | fa-file-word | 藍色 #3b82f6 |
| .ppt/.pptx | fa-file-powerpoint | 橘色 #f97316 |
| .xls/.xlsx | fa-file-excel | 綠色 #22c55e |
| .txt/.md | fa-file-lines | 灰色 #6b7280 |
| 其他 | fa-file | 灰色 #6b7280 |
