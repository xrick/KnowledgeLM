# Skill Data Management System - 實作報告

**日期**: 2025-11-27
**版本**: 1.0
**狀態**: ✅ 完成

---

## 概述

本系統提供完整的 Skill 資料生命週期管理，包括：
1. **資料清除** - 安全刪除 skill 表格（保留 embedding_models）
2. **JSON 配置** - 描述 Skills 與 PDF 來源的對應關係
3. **資料重建** - 根據配置文件重建所有 Skills
4. **UI 管理介面** - 視覺化管理 Skills 與 PDF 組成

---

## 系統架構

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Skill Data Management System                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │   Scripts    │    │   Config     │    │     UI       │              │
│  ├──────────────┤    ├──────────────┤    ├──────────────┤              │
│  │ clean_skill  │◄──►│ skill_config │◄──►│ skill_config │              │
│  │ _tables.sh   │    │ .json        │    │ .html        │              │
│  │              │    │              │    │              │              │
│  │ rebuild_     │    │              │    │              │              │
│  │ skills.sh    │    │              │    │              │              │
│  │              │    │              │    │              │              │
│  │ rebuild_from │    │              │    │              │              │
│  │ _config.py   │    │              │    │              │              │
│  └──────────────┘    └──────────────┘    └──────────────┘              │
│         │                   │                   │                       │
│         ▼                   ▼                   ▼                       │
│  ┌─────────────────────────────────────────────────────────────┐       │
│  │                      API Endpoints                            │       │
│  │  GET  /api/v1/skills/config                                   │       │
│  │  GET  /api/v1/skills/config/skills                            │       │
│  │  POST /api/v1/skills/config/skills                            │       │
│  │  POST /api/v1/skills/config/skills/{name}/sources             │       │
│  │  DELETE /api/v1/skills/config/skills/{name}/sources           │       │
│  │  GET  /api/v1/skills/config/instant-attachments               │       │
│  │  POST /api/v1/skills/config/instant-attachments               │       │
│  │  DELETE /api/v1/skills/config/instant-attachments             │       │
│  │  POST /api/v1/skills/rebuild                                  │       │
│  │  GET  /api/v1/skills/rebuild/status                           │       │
│  └─────────────────────────────────────────────────────────────┘       │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────┐       │
│  │                      Data Layer                               │       │
│  │  SQLite: skill_metadata.db                                    │       │
│  │  FAISS:  data/faiss_indices/skills/                           │       │
│  └─────────────────────────────────────────────────────────────┘       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 新增檔案清單

### 1. Scripts

| 檔案 | 路徑 | 用途 |
|------|------|------|
| clean_skill_tables.sh | scripts/skill_data/ | 清除 skill 相關表格 |
| rebuild_skills.sh | scripts/skill_data/ | 重建 skills 的 wrapper |
| rebuild_from_config.py | scripts/skill_data/ | 根據 JSON 配置重建 |
| skill_config.json | scripts/skill_data/ | Skills 與 PDF 配置 |
| test_workflow.sh | scripts/skill_data/ | 測試工作流程 |

### 2. Templates

| 檔案 | 路徑 | 用途 |
|------|------|------|
| skill_config.html | template/ | Skill 配置管理 UI |

### 3. 修改的檔案

| 檔案 | 修改內容 |
|------|----------|
| app/api/v1/endpoints/skills.py | 新增 PDF 管理 API endpoints |
| main.py | 新增 /skill 和 /skill/config 路由 |
| template/skill_main.html | 新增配置管理入口連結 |

---

## 功能詳解

### 1. clean_skill_tables.sh

**功能**: 清除 skill_metadata.db 中的 skill 相關表格

**清除的表格**:
- skill_chunk_metadata
- skill_document_mapping
- skill_metadata
- skill_overviews

**保留的表格**:
- embedding_models ✅

**使用方式**:
```bash
# 互動模式（需確認）
./scripts/skill_data/clean_skill_tables.sh

# 強制模式（跳過確認）
./scripts/skill_data/clean_skill_tables.sh --force
```

**特色**:
- 自動備份資料庫
- 同時清除 FAISS 索引
- 顯示清除前後狀態

---

### 2. skill_config.json

**功能**: 定義 Skills 及其 PDF 來源

**結構**:
```json
{
    "version": "1.0",
    "skills": [
        {
            "skill_name": "LLM",
            "description": "Large Language Model 基礎知識",
            "category": "Technology",
            "enabled": true,
            "sources": [
                {
                    "path": "refData/rawdata/LLM/book.pdf",
                    "enabled": true,
                    "description": "書籍描述"
                }
            ]
        }
    ],
    "instant_attachments": [],
    "settings": {
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "embedding_model": "BAAI/bge-m3",
        "embedding_dimension": 1024,
        "rebuild_threshold": 5
    }
}
```

**特色**:
- 支援多 Skills
- 每個 PDF 可獨立啟用/停用
- Instant Attachments 用於臨時添加
- rebuild_threshold 達到後建議重建

---

### 3. rebuild_skills.sh

**功能**: 重建 Skills 的 Shell wrapper

**使用方式**:
```bash
# 完整重建（含清除）
./scripts/skill_data/rebuild_skills.sh --clean

# 只重建特定 skill
./scripts/skill_data/rebuild_skills.sh --skill "LLM"

# 使用自定義配置
./scripts/skill_data/rebuild_skills.sh --config /path/to/config.json

# 模擬執行
./scripts/skill_data/rebuild_skills.sh --dry-run
```

---

### 4. rebuild_from_config.py

**功能**: 根據 JSON 配置重建 Skills 的 Python 腳本

**流程**:
1. 載入 skill_config.json
2. 對每個啟用的 skill:
   - 提取 PDF 頁面文字
   - 使用 BGE-M3 生成 embeddings
   - 存儲到 FAISS
   - 存儲 metadata 到 SQLite
3. 輸出結果摘要

**特色**:
- 使用現有的 BGEEmbeddingProvider
- 使用現有的 SkillMetadataProvider
- 使用現有的 VectorStoreProvider
- 完整的日誌記錄

---

### 5. API Endpoints

#### 配置管理

| 方法 | 路徑 | 功能 |
|------|------|------|
| GET | /api/v1/skills/config | 獲取完整配置 |
| GET | /api/v1/skills/config/skills | 獲取 skills 清單 |
| POST | /api/v1/skills/config/skills | 新增 skill |
| POST | /api/v1/skills/config/skills/{name}/sources | 新增 PDF 來源 |
| DELETE | /api/v1/skills/config/skills/{name}/sources | 移除 PDF 來源 |

#### Instant Attachments

| 方法 | 路徑 | 功能 |
|------|------|------|
| GET | /api/v1/skills/config/instant-attachments | 獲取臨時附件清單 |
| POST | /api/v1/skills/config/instant-attachments | 新增臨時附件 |
| DELETE | /api/v1/skills/config/instant-attachments | 清除所有臨時附件 |

#### 重建

| 方法 | 路徑 | 功能 |
|------|------|------|
| POST | /api/v1/skills/rebuild | 觸發重建（背景執行） |
| GET | /api/v1/skills/rebuild/status | 查看重建日誌 |

---

### 6. skill_config.html

**功能**: 視覺化管理 Skills 與 PDF 組成

**URL**: http://localhost:8000/skill/config

**功能**:
- 查看所有 Skills 及其 PDF 來源
- 新增/移除 Skill
- 新增/移除 PDF 來源
- 查看 Instant Attachments
- 觸發重建
- 查看重建日誌

**入口**: skill_main.html 側邊欄新增 "Skill 配置管理" 連結

---

## 使用流程

### 場景 1: 完全重建

```bash
# 1. 清除現有資料
./scripts/skill_data/clean_skill_tables.sh --force

# 2. 編輯配置文件
vim scripts/skill_data/skill_config.json

# 3. 執行重建
./scripts/skill_data/rebuild_skills.sh --force
```

### 場景 2: 新增 PDF 到現有 Skill

```bash
# 方法 1: 編輯 JSON
vim scripts/skill_data/skill_config.json
# 在對應 skill 的 sources 陣列新增 PDF

# 方法 2: 使用 API
curl -X POST http://localhost:8000/api/v1/skills/config/skills/LLM/sources \
  -H "Content-Type: application/json" \
  -d '{"path": "refData/rawdata/LLM/new_book.pdf", "enabled": true}'

# 方法 3: 使用 UI
# 訪問 http://localhost:8000/skill/config
```

### 場景 3: 臨時添加 PDF

```bash
# 添加臨時附件
curl -X POST http://localhost:8000/api/v1/skills/config/instant-attachments \
  -H "Content-Type: application/json" \
  -d '{
    "skill_name": "LLM",
    "path": "refData/rawdata/LLM/temp_doc.pdf",
    "description": "臨時添加的文件"
  }'

# 當累積到 rebuild_threshold (預設 5) 時
# 系統會提示需要執行完整重建
```

---

## 測試結果

```
✅ 19/19 測試通過

1. File Existence Tests      ✓ 4/4
2. Configuration Tests       ✓ 3/3
3. Script Syntax Tests       ✓ 3/3
4. Database Tests            ✓ 3/3
5. API Tests                 ✓ 3/3
6. Template Tests            ✓ 3/3
```

---

## 注意事項

1. **服務器重啟**: 新增的 API endpoints 需要重啟服務器才能生效
2. **PDF 路徑**: 配置中的路徑是相對於專案根目錄
3. **Instant Attachments**: 累積到 threshold 後建議執行完整重建
4. **備份**: clean_skill_tables.sh 會自動備份資料庫

---

## 後續改進建議

1. **增量重建**: 支援只重建新增的 PDF，不需完整重建
2. **進度追蹤**: 重建過程的即時進度顯示
3. **檔案上傳**: UI 支援直接上傳 PDF
4. **驗證機制**: 重建後自動驗證資料完整性

---

*報告生成時間: 2025-11-27*
*Author: Claude Code (SuperClaude Framework)*
