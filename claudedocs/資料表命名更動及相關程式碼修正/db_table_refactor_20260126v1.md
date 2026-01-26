# 資料庫表格重構紀錄 v1

**日期**: 2026-01-26
**資料庫**: `data/skill_metadata.db`
**備份**: `data/skill_metadata.db.backup_before_rename`
**執行者**: Claude (SuperClaude Framework)
**狀態**: 進行中（僅完成資料庫改動，程式碼尚未修改）

---

## 重構目標

將系統從 `skill` 為核心的命名體系，重構為以 `knowledge`（知識層）和 `doc`（文件層）為核心的命名體系。

### 核心概念映射

| 舊概念 | 新概念 | 說明 |
|--------|--------|------|
| `skill` (技能) | `knowledge` (知識) | 頂層概念重命名 |
| `head` (頭/群組) | `knowledge` (知識) | 群組層概念合併到 knowledge |
| `skill_id` (文件層) | `doc_id` | 文件層用 `doc` 表示 |

### 值前綴映射

| 用途 | 舊前綴 | 新前綴 |
|------|--------|--------|
| 知識群組 ID | `head_` | `knowledge_` |
| 文件 ID | `skill_` | `doc_` |
| 父層參照 | `skill_` | `knowledge_` |

---

## 變更紀錄

### 1. `skill_heads` → `knowledge_info`

#### 1.1 欄位值前綴修改

```sql
UPDATE skill_heads SET head_id = REPLACE(head_id, 'head_', 'knowledge_') WHERE head_id LIKE 'head_%';
```

| 改動前 | 改動後 |
|--------|--------|
| `head_20260108_035814_2a43e5ac` | `knowledge_20260108_035814_2a43e5ac` |
| `head_20260113_141642_4209c143` | `knowledge_20260113_141642_4209c143` |

#### 1.2 欄位名修改

```sql
ALTER TABLE skill_heads RENAME COLUMN head_id TO knowledge_id;
ALTER TABLE skill_heads RENAME COLUMN skill_name TO knowledge_name;
```

| 舊欄位名 | 新欄位名 |
|----------|----------|
| `head_id` | `knowledge_id` |
| `skill_name` | `knowledge_name` |

#### 1.3 表名修改

```sql
ALTER TABLE skill_heads RENAME TO knowledge_info;
```

#### 1.4 最終 Schema

```sql
CREATE TABLE knowledge_info (
    knowledge_id TEXT PRIMARY KEY,
    knowledge_name TEXT NOT NULL UNIQUE,
    description TEXT,
    category TEXT DEFAULT 'General',
    display_order INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 2. `skill_metadata` → `knowledge_metadata`

#### 2.1 欄位值前綴修改

```sql
-- skill_id 值: skill_ → doc_
UPDATE skill_metadata SET skill_id = REPLACE(skill_id, 'skill_', 'doc_') WHERE skill_id LIKE 'skill_%';

-- head_id 值: head_ → knowledge_
UPDATE skill_metadata SET head_id = REPLACE(head_id, 'head_', 'knowledge_') WHERE head_id LIKE 'head_%';

-- parent_skill_id 值: skill_ → knowledge_
UPDATE skill_metadata SET parent_skill_id = REPLACE(parent_skill_id, 'skill_', 'knowledge_') WHERE parent_skill_id LIKE 'skill_%';
```

| 欄位 | 舊值範例 | 新值範例 |
|------|---------|---------|
| `skill_id` | `skill_20251126_104421_4fdb3e9b` | `doc_20251126_104421_4fdb3e9b` |
| `head_id` | `head_20260108_035814_2a43e5ac` | `knowledge_20260108_035814_2a43e5ac` |
| `parent_skill_id` | `skill_20251203_071733_2a43e5ac` | `knowledge_20251203_071733_2a43e5ac` |
| `parent_skill_id` | `root` | `root`（不變） |

#### 2.2 欄位名修改

```sql
ALTER TABLE skill_metadata RENAME COLUMN skill_id TO doc_id;
ALTER TABLE skill_metadata RENAME COLUMN skill_name TO knowledge_name;
ALTER TABLE skill_metadata RENAME COLUMN skill_description TO knowledge_description;
ALTER TABLE skill_metadata RENAME COLUMN skill_category TO knowledge_type;
ALTER TABLE skill_metadata RENAME COLUMN skill_level TO knowledge_level;
ALTER TABLE skill_metadata RENAME COLUMN head_id TO knowledge_id;
ALTER TABLE skill_metadata RENAME COLUMN parent_skill_id TO parent_knowledge_id;
ALTER TABLE skill_metadata RENAME COLUMN related_skills TO related_knowledge;
```

| 舊欄位名 | 新欄位名 |
|----------|----------|
| `skill_id` | `doc_id` |
| `skill_name` | `knowledge_name` |
| `skill_description` | `knowledge_description` |
| `skill_category` | `knowledge_type` |
| `skill_level` | `knowledge_level` |
| `head_id` | `knowledge_id` |
| `parent_skill_id` | `parent_knowledge_id` |
| `related_skills` | `related_knowledge` |

#### 2.3 表名修改

```sql
-- 第一次改名
ALTER TABLE skill_metadata RENAME TO doc_metadata;
-- 第二次改名（最終）
ALTER TABLE doc_metadata RENAME TO knowledge_metadata;
```

#### 2.4 Index 重建

```sql
-- 第一輪 index 重命名 (skill_ → doc_)
DROP INDEX idx_skill_category;
DROP INDEX idx_skill_name;
DROP INDEX idx_skill_level;
DROP INDEX idx_parent_skill_id;
DROP INDEX idx_skill_head_id;

CREATE INDEX idx_doc_knowledge_type ON doc_metadata(knowledge_type);
CREATE INDEX idx_doc_knowledge_name ON doc_metadata(knowledge_name);
CREATE INDEX idx_doc_knowledge_level ON doc_metadata(knowledge_level);
CREATE INDEX idx_doc_parent_knowledge_id ON doc_metadata(parent_knowledge_id);
CREATE INDEX idx_doc_knowledge_id ON doc_metadata(knowledge_id);

-- 第二輪 index 重命名 (去掉 doc_ 前綴)
DROP INDEX idx_doc_knowledge_type;
DROP INDEX idx_doc_knowledge_name;
DROP INDEX idx_doc_knowledge_level;
DROP INDEX idx_doc_parent_knowledge_id;
DROP INDEX idx_doc_knowledge_id;

CREATE INDEX idx_knowledge_type ON knowledge_metadata(knowledge_type);
CREATE INDEX idx_knowledge_name ON knowledge_metadata(knowledge_name);
CREATE INDEX idx_knowledge_level ON knowledge_metadata(knowledge_level);
CREATE INDEX idx_parent_knowledge_id ON knowledge_metadata(parent_knowledge_id);
CREATE INDEX idx_knowledge_id ON knowledge_metadata(knowledge_id);
```

| 舊 Index | 新 Index |
|----------|----------|
| `idx_skill_category` | `idx_knowledge_type` |
| `idx_skill_name` | `idx_knowledge_name` |
| `idx_skill_level` | `idx_knowledge_level` |
| `idx_parent_skill_id` | `idx_parent_knowledge_id` |
| `idx_skill_head_id` | `idx_knowledge_id` |
| `idx_processing_status` | `idx_processing_status`（未改） |

#### 2.5 最終 Schema

```sql
CREATE TABLE knowledge_metadata (
    doc_id TEXT PRIMARY KEY,
    knowledge_name TEXT NOT NULL,
    knowledge_description TEXT,
    knowledge_type TEXT,
    knowledge_level TEXT DEFAULT 'intermediate',
    tags TEXT,
    related_knowledge TEXT,
    total_chunks INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,
    embedding_model TEXT DEFAULT 'text-embedding-ada-002',
    embedding_dimension INTEGER DEFAULT 1536,
    parent_knowledge_id TEXT DEFAULT 'root',
    source_name TEXT DEFAULT NULL,
    knowledge_id TEXT REFERENCES knowledge_info(knowledge_id),
    processing_status TEXT DEFAULT 'completed',
    indexed_chunks INTEGER DEFAULT 0,
    last_error TEXT DEFAULT NULL,
    processing_started_at TEXT DEFAULT NULL,
    processing_completed_at TEXT DEFAULT NULL
);

-- Indexes
CREATE INDEX idx_knowledge_type ON knowledge_metadata(knowledge_type);
CREATE INDEX idx_knowledge_name ON knowledge_metadata(knowledge_name);
CREATE INDEX idx_knowledge_level ON knowledge_metadata(knowledge_level);
CREATE INDEX idx_parent_knowledge_id ON knowledge_metadata(parent_knowledge_id);
CREATE INDEX idx_knowledge_id ON knowledge_metadata(knowledge_id);
CREATE INDEX idx_processing_status ON knowledge_metadata(processing_status);
```

---

## 目前資料庫全貌

### 表格狀態

| 表名 | 狀態 | 說明 |
|------|------|------|
| `knowledge_info` | ✅ 已完成 | 原 `skill_heads` |
| `knowledge_metadata` | ✅ 已完成 | 原 `skill_metadata` |
| `skill_chunk_metadata` | ⏳ 尚未改 | |
| `skill_document_mapping` | ⏳ 尚未改 | |
| `skill_overviews` | ⏳ 尚未改 | |
| `embedding_models` | — | 無需改 |
| `processing_jobs` | — | 無需改 |
| `lost_and_found` | — | 無需改 |
| `users` | — | 無需改 |

### `skill_document_mapping` 的 `file_id` 分析

**結論**: `file_id` 在查詢路徑上未被使用，僅有寫入操作。

- `file_id` 是 PDF 檔案的 hash ID（如 `doc_1a408b9f`）
- `skill_id` 是知識系統的記錄 ID（如 `skill_20251126_104421_4fdb3e9b`）
- 兩者語義不同，但部分 rebuild 腳本直接 `file_id=skill_id` 導致重疊
- 目前無任何程式碼路徑透過 `file_id` 進行查詢

**待決定**: 保留並改名 / 移除 / 暫不處理

---

## 待完成項目

1. `skill_chunk_metadata` 表的欄位與表名重構
2. `skill_document_mapping` 表的欄位與表名重構（含 `file_id` 決策）
3. `skill_overviews` 表的欄位與表名重構
4. 程式碼端對應修改（需用戶授權後進行）

---

## 回滾方案

```bash
# 還原備份
cp data/skill_metadata.db.backup_before_rename data/skill_metadata.db
```

備份檔案: `data/skill_metadata.db.backup_before_rename`（重構前完整備份）
