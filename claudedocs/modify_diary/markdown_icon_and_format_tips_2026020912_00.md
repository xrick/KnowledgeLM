# 修改日記: Markdown 圖示區分 + 格式提示

**日期時間**: 2026-02-09 12:00
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟢 低

## 修改摘要
1. 為 Markdown 文件設置專屬紫色圖示，與 TXT 灰色圖示區分
2. 在「新增文件來源」Modal 中加入支援格式圖示列和 Tooltip

## 修改檔案
| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| template/skill_config.html | 修改 | CSS: 新增 .md-icon 和 .format-icons-row 樣式 |
| template/skill_config.html | 修改 | JS: getFileTypeIcon() 分離 MD 和 TXT |
| template/skill_config.html | 修改 | HTML: Modal 新增格式圖示列 |

## 程式碼變更

### 1. CSS 新增 (Lines ~623-651)
```css
.source-icon.md-icon {
    color: #7c3aed; /* Purple for Markdown */
}

.format-icons-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: var(--card-bg, #f8fafc);
    border-radius: 6px;
    border: 1px solid var(--border-color, #e2e8f0);
}
.format-icon-item { ... }
.format-icon-item.pdf i { color: #ef4444; }
.format-icon-item.docx i { color: #3b82f6; }
.format-icon-item.pptx i { color: #f97316; }
.format-icon-item.md i { color: #7c3aed; }
.format-icon-item.txt i { color: #6b7280; }
```

### 2. JavaScript 修改 (getFileTypeIcon)
```javascript
// 修改前
case "txt":
case "md":
    return { icon: "fa-file-lines", iconClass: "txt-icon" };

// 修改後
case "md":
case "markdown":
    return { icon: "fa-file-code", iconClass: "md-icon" };
case "txt":
    return { icon: "fa-file-lines", iconClass: "txt-icon" };
```

### 3. HTML Modal 新增格式圖示列
```html
<div class="format-icons-row" title="支援的文件格式 / Supported file formats">
    <span>支援格式:</span>
    <span class="format-icon-item pdf"><i class="fa-solid fa-file-pdf"></i> PDF</span>
    <span class="format-icon-item docx"><i class="fa-solid fa-file-word"></i> DOCX</span>
    <span class="format-icon-item pptx"><i class="fa-solid fa-file-powerpoint"></i> PPTX</span>
    <span class="format-icon-item md"><i class="fa-solid fa-file-code"></i> MD</span>
    <span class="format-icon-item txt"><i class="fa-solid fa-file-lines"></i> TXT</span>
</div>
```

## 圖示對照表 (更新後)
| 副檔名 | 圖示 | 顏色 | 說明 |
|--------|------|------|------|
| .pdf | fa-file-pdf | 紅色 #ef4444 | PDF 文件 |
| .doc/.docx | fa-file-word | 藍色 #3b82f6 | Word 文件 |
| .ppt/.pptx | fa-file-powerpoint | 橘色 #f97316 | PowerPoint |
| .xls/.xlsx | fa-file-excel | 綠色 #22c55e | Excel |
| .md/.markdown | fa-file-code | **紫色 #7c3aed** | Markdown ⬅️ 新增 |
| .txt | fa-file-lines | 灰色 #6b7280 | 純文字 |

## 影響分析
- 影響範圍: skill/config 頁面的文件列表 + 新增文件 Modal
- 向後相容: 是
- 需要測試: 刷新頁面確認 Markdown 文件顯示紫色圖示，Modal 顯示格式提示

## 回滾方案
還原 `template/skill_config.html` 中的以下變更：
1. 移除 `.md-icon` 和 `.format-icons-row` 相關 CSS
2. 將 `getFileTypeIcon()` 中的 `md` case 合併回 `txt`
3. 移除 Modal 中的 `format-icons-row` div

## 驗證結果
- [x] CSS 語法正確
- [x] JavaScript 語法正確
- [x] HTML 結構正確
- [ ] 手動驗證 - 需刷新瀏覽器確認

## UI 預覽
```
┌─────────────────────────────────────────┐
│ 新增文件來源                              │
├─────────────────────────────────────────┤
│ Skill: [ML                            ] │
│                                         │
│ 選擇文件:                                │
│ [📄 Choose File] No file chosen         │
│ ┌─────────────────────────────────────┐ │
│ │ 支援格式: 📕PDF 📘DOCX 📙PPTX 💜MD 📄TXT │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ 描述: [                               ] │
│                                         │
│           [取消]  [新增來源]             │
└─────────────────────────────────────────┘
```
