# 分析報告: PPT/PPTX 文件支援實作規劃 (Skill-Based 系統)

**日期時間**: 2026-01-20 20:45
**分析者**: Claude (SuperClaude Framework)
**風險等級**: 🟡 中
**報告類型**: 程式碼分析與實作規劃
**範圍**: 僅 Skill-Based 系統 (File-Based 系統已棄用)

---

## 1. 摘要

本報告分析 DocAI Skill-Based 系統中文件上傳類型的限制位置，並規劃新增 PPT/PPTX 支援所需的修改。

---

## 2. 目前支援的文件類型

### 2.1 設定檔定義

| 檔案 | 位置 | 目前設定 |
|------|------|----------|
| `app/core/config.py` | Line 101 | `ALLOWED_EXTENSIONS: List[str] = ["pdf"]` |

### 2.2 前端限制 (Skill Config 頁面)

| 檔案 | 位置 | 限制內容 |
|------|------|----------|
| `template/skill_config.html` | Line 1190 | `accept=".pdf"` |
| `template/skill_config.html` | Line 3068 | `file.name.toLowerCase().endsWith(".pdf")` |

### 2.3 後端驗證 (Skill API)

| 檔案 | 函數 | 位置 | 驗證邏輯 |
|------|------|------|----------|
| `app/api/v1/endpoints/skills.py` | `upload_source_to_skill()` | Line 2139 | `file.filename.lower().endswith(".pdf")` |
| `app/api/v1/endpoints/skills.py` | `upload_source_to_skill_stream()` | Line 2040 | `file.filename.lower().endswith(".pdf")` |

---

## 3. Skill-Based PDF 處理流程架構

```
┌─────────────────────────────────────────────────────────────────┐
│                   Skill-Based 文件上傳流程                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │   Frontend   │ →  │   Skill API  │ →  │  Skill Ingestion │   │
│  │skill_config  │    │  skills.py   │    │    Service       │   │
│  └──────────────┘    └──────────────┘    └──────────────────┘   │
│         ↓                   ↓                     ↓              │
│  - accept=".pdf"     upload_source_to    PDFSkillIngestion       │
│  - JS validation     _skill_stream()     Service                 │
│                      - .endswith()       - _extract_pdf_pages()  │
│                                          - PyPDF2                │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 Skill 專用 PDF 處理服務

**檔案**: `app/SkillServices/pdf_skill_ingestion_service.py`

- 類別: `PDFSkillIngestionService`
- 使用: PyPDF2 提取文字
- 關鍵方法:
  - `_extract_pdf_pages()` - 逐頁提取 PDF 文字
  - `process_pdf_streaming()` - 串流處理大型 PDF
  - `_store_embeddings()` - 儲存至 FAISS

### 3.2 處理流程函數

**檔案**: `app/api/v1/endpoints/skills.py`

```python
async def process_pdf_for_skill_streaming(
    pdf_path: Path,
    skill_name: str,
    skill_description: str,
    head_id: str,
    ...
)
```

此函數負責:
1. 提取 PDF 文字
2. 分割成 chunks
3. 生成 embeddings
4. 儲存至 FAISS + SQLite

---

## 4. PPT/PPTX 支援實作規劃

### 4.1 需要新增的依賴套件

```txt
# requirements.txt 新增
python-pptx>=0.6.21
```

### 4.2 需要修改的檔案清單 (僅 Skill-Based)

| 優先級 | 檔案 | 修改類型 | 說明 |
|--------|------|----------|------|
| 🔴 HIGH | `requirements.txt` | 新增 | 新增 python-pptx 依賴 |
| 🔴 HIGH | `app/core/config.py` | 修改 | 新增 ppt, pptx 到 ALLOWED_EXTENSIONS |
| 🔴 HIGH | `app/SkillServices/pdf_skill_ingestion_service.py` | 重構 | 擴展為通用 DocumentIngestionService |
| 🔴 HIGH | `app/api/v1/endpoints/skills.py` | 修改 | 修改驗證 + 處理函數 |
| 🟡 MED | `template/skill_config.html` | 修改 | 修改 accept 屬性和 JS 驗證 |

### 4.3 詳細修改內容

#### 4.3.1 `requirements.txt`

**新增**:
```txt
python-pptx>=0.6.21
```

#### 4.3.2 `app/core/config.py` (Line 101)

**變更前**:
```python
ALLOWED_EXTENSIONS: List[str] = Field(default_factory=lambda: ["pdf"])
```

**變更後**:
```python
ALLOWED_EXTENSIONS: List[str] = Field(default_factory=lambda: ["pdf", "ppt", "pptx"])
```

#### 4.3.3 `app/SkillServices/pdf_skill_ingestion_service.py`

**選項 A: 擴展現有服務 (建議)**

重命名並擴展:
- `PDFSkillIngestionService` → `DocumentSkillIngestionService`
- 新增 `_extract_pptx_slides()` 方法
- 修改處理入口根據副檔名選擇提取器

**新增方法**:
```python
async def _extract_pptx_slides(self, pptx_path: Path) -> List[str]:
    """
    Extract text from each slide of a PPTX file
    
    Args:
        pptx_path: Path to PPTX file
        
    Returns:
        List of slide texts
    """
    from pptx import Presentation
    
    slides = []
    prs = Presentation(str(pptx_path))
    
    for slide_num, slide in enumerate(prs.slides, 1):
        slide_text = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                slide_text.append(shape.text.strip())
        
        if slide_text:
            # 格式化為類似 PDF 頁面的結構
            text = f"[Slide {slide_num}]\n" + "\n".join(slide_text)
            slides.append(text)
    
    return slides
```

**修改 `process_pdf_streaming()` 或新建通用方法**:
```python
async def process_document_streaming(self, doc_path: Path, ...):
    """通用文件處理方法"""
    file_ext = doc_path.suffix.lower()
    
    if file_ext == '.pdf':
        pages = await self._extract_pdf_pages(doc_path)
    elif file_ext in ['.ppt', '.pptx']:
        pages = await self._extract_pptx_slides(doc_path)
    else:
        raise ValueError(f"Unsupported file type: {file_ext}")
    
    # 後續 chunking, embedding, storage 邏輯不變
    ...
```

#### 4.3.4 `app/api/v1/endpoints/skills.py`

**修改 1: 驗證邏輯 (Lines 2040, 2139)**

**變更前**:
```python
if not file.filename.lower().endswith(".pdf"):
    raise HTTPException(status_code=400, detail="Only PDF files are allowed")
```

**變更後**:
```python
ALLOWED_DOC_EXTENSIONS = ('.pdf', '.ppt', '.pptx')
if not file.filename.lower().endswith(ALLOWED_DOC_EXTENSIONS):
    raise HTTPException(
        status_code=400, 
        detail=f"Unsupported file type. Allowed: PDF, PPT, PPTX"
    )
```

**修改 2: 處理函數重命名**

將 `process_pdf_for_skill_streaming()` 重命名或建立包裝:
```python
async def process_document_for_skill_streaming(
    doc_path: Path,  # 改為通用名稱
    skill_name: str,
    ...
):
    """處理文件 (PDF/PPT/PPTX) 並生成 embeddings"""
    ...
```

#### 4.3.5 `template/skill_config.html`

**HTML Input (Line 1190)**:
```html
<!-- 變更前 -->
<input type="file" id="pdf-file-input" accept=".pdf" ...>

<!-- 變更後 -->
<input type="file" id="doc-file-input" accept=".pdf,.ppt,.pptx" ...>
```

**JavaScript 驗證 (Line 3068)**:
```javascript
// 變更前
if (!file.name.toLowerCase().endsWith(".pdf")) {
    alert("Please select a PDF file");
    return;
}

// 變更後
const allowedExtensions = ['.pdf', '.ppt', '.pptx'];
const fileExt = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
if (!allowedExtensions.includes(fileExt)) {
    alert("請選擇 PDF、PPT 或 PPTX 檔案");
    return;
}
```

**UI 文字更新** (可選):
- "Add PDF" → "Add Document"
- "PDF Sources" → "Document Sources"

---

## 5. 實作步驟建議

### Phase 1: 依賴與設定 (5 分鐘)

1. ✅ 安裝 `python-pptx` 依賴
2. ✅ 修改 `app/core/config.py` - ALLOWED_EXTENSIONS

### Phase 2: 核心服務擴展 (30 分鐘)

3. ✅ 新增 `_extract_pptx_slides()` 方法到 IngestionService
4. ✅ 建立通用 `process_document_streaming()` 入口

### Phase 3: API 端點更新 (15 分鐘)

5. ✅ 修改 `skills.py` 驗證邏輯 (2 處)
6. ✅ 更新處理函數呼叫

### Phase 4: 前端更新 (10 分鐘)

7. ✅ 修改 HTML accept 屬性
8. ✅ 修改 JavaScript 驗證

---

## 6. 測試計劃

| 測試項目 | 驗證內容 |
|----------|----------|
| 單元測試 | `_extract_pptx_slides()` 正確提取投影片文字 |
| API 測試 | `/api/v1/skills/.../upload-source-stream` 接受 pptx |
| E2E 測試 | 前端上傳 pptx → 後端處理 → FAISS 儲存 → 可查詢 |
| 回歸測試 | PDF 上傳功能不受影響 |

---

## 7. 風險評估

| 風險 | 機率 | 影響 | 緩解措施 |
|------|------|------|----------|
| PPT 文字提取品質不佳 | 中 | 中 | 提供上傳後預覽讓用戶確認 |
| 舊版 .ppt 格式不支援 | 中 | 低 | python-pptx 僅支援 .pptx，可考慮使用 unoconv 轉換 |
| 投影片圖片中的文字無法提取 | 高 | 中 | 未來可整合 OCR (如 pytesseract) |

### 7.1 .ppt 格式處理建議

python-pptx **不支援**舊版 .ppt 格式。選項:

1. **僅支援 .pptx**: 最簡單，在 UI 提示用戶轉換格式
2. **使用 LibreOffice 轉換**: 安裝 libreoffice，用 subprocess 轉換
3. **使用 Aspose 套件**: 商業方案，支援完整格式

**建議**: 先僅支援 .pptx，在錯誤訊息中提示用戶將 .ppt 轉存為 .pptx

---

## 8. 結論

新增 PPT/PPTX 支援 (Skill-Based 系統) 需要修改 **5 個檔案**：

| 層級 | 檔案 | 修改量 |
|------|------|--------|
| 依賴 | `requirements.txt` | ~1 行 |
| 設定 | `app/core/config.py` | ~1 行 |
| 服務 | `app/SkillServices/pdf_skill_ingestion_service.py` | ~40 行 |
| API | `app/api/v1/endpoints/skills.py` | ~15 行 (2-3 處) |
| 前端 | `template/skill_config.html` | ~10 行 (2 處) |

**預估總修改**: ~70 行程式碼
**預估工時**: 1-2 小時

---

## 9. 修改檔案快速索引

```
需要修改的檔案:
├── requirements.txt                              # 新增 python-pptx
├── app/
│   ├── core/config.py                           # Line 101: ALLOWED_EXTENSIONS
│   ├── SkillServices/
│   │   └── pdf_skill_ingestion_service.py       # 新增 _extract_pptx_slides()
│   └── api/v1/endpoints/
│       └── skills.py                            # Lines 2040, 2139: 驗證邏輯
└── template/
    └── skill_config.html                        # Lines 1190, 3068: 前端驗證
```

---

*報告生成時間: 2026-01-20 20:45 (Updated)*
*SuperClaude Framework v2.0.1*
*範圍: Skill-Based System Only*
