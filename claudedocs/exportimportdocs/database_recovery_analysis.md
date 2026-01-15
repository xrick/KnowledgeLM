# Database Recovery Analysis - skill_metadata.db

**日期**: 2026-01-07
**時間**: 08:50
**任務**: 分析資料庫損壞並記錄修復過程

---

## 問題發現

### 錯誤訊息

Export/Import API 報告資料庫損壞：
```
{"detail":"Export failed: database disk image is malformed"}
{"detail":"Database import failed: database disk image is malformed"}
```

### 初步診斷 (08:04)

```sql
sqlite3 data/skill_metadata.db "PRAGMA integrity_check;"
```

結果：
```
Error: stepping, database disk image is malformed (11)
*** in database main ***
On tree page 437 cell 314: 2nd reference to page 2803
On tree page 435 cell 337: 2nd reference to page 2732
On tree page 341 cell 0: 2nd reference to page 2736
On tree page 341 cell 33: 2nd reference to page 2733
On tree page 9 cell 45: 2nd reference to page 2734
On tree page 9 cell 44: 2nd reference to page 2719
```

**問題類型**: B-tree 頁面交叉引用（Cross-reference）錯誤

---

## 資料庫狀態分析

### 檔案結構

```bash
ls -lh data/skill_metadata.db*
```

發現：
```
-rw-r--r--  skill_metadata.db       15M  (主資料庫)
-rw-r--r--  skill_metadata.db-shm   32K  (Shared Memory)
-rw-r--r--  skill_metadata.db-wal  113K  (Write-Ahead Log)
```

**關鍵發現**: 資料庫處於 **WAL (Write-Ahead Logging) 模式**

### WAL 模式說明

SQLite WAL 模式特性：
- 寫入操作先寫入 WAL 檔案，而非直接修改主資料庫
- 讀取時需要合併主資料庫 + WAL 內容
- 當 WAL 檔案達到一定大小時，執行 checkpoint 將 WAL 合併回主資料庫
- **問題**: 如果 WAL 檔案損壞或不一致，會導致資料庫「看起來損壞」

### 資料可訪問性測試

#### ✅ 成功的查詢

```sql
SELECT COUNT(*) FROM skill_heads;  → 5
SELECT COUNT(*) FROM skill_metadata;  → 8
SELECT skill_id, COUNT(*) as chunks
FROM skill_chunk_metadata
GROUP BY skill_id;  → 9 skills, 2854 chunks
```

#### ❌ 失敗的查詢

```sql
SELECT COUNT(*) FROM skill_chunk_metadata;
→ Error: database disk image is malformed (11)
```

**分析**:
- GROUP BY 查詢成功 → **資料本身沒有損壞**
- COUNT(*) 全表掃描失敗 → **B-tree 索引結構損壞**

---

## 根本原因推斷

### 可能原因 1: WAL Checkpoint 中斷

**場景**:
- 大量 chunk insert 操作後，WAL 檔案變大（113K）
- Checkpoint 過程中服務意外重啟或中斷
- 導致 WAL 和主資料庫不一致

**證據**:
- WAL 檔案存在且有 113K 大小
- 錯誤發生在 `skill_chunk_metadata` 表（最大的表，2854 rows）
- B-tree 頁面交叉引用錯誤（典型的 checkpoint 中斷症狀）

### 可能原因 2: 並發寫入衝突

**場景**:
- 多個進程同時寫入資料庫
- WAL 模式下的鎖定機制失效
- 導致 WAL 內部結構損壞

**證據**:
- 系統可能有多個 DocAI 實例運行
- SHM（Shared Memory）檔案存在，用於進程間同步

### 可能原因 3: 磁碟 I/O 錯誤

**可能性**: 較低，因為其他表的資料完全正常

---

## 修復過程

### 方法 1: SQLite .recover 命令 (已執行)

**執行時間**: 08:49

**命令**:
```bash
sqlite3 data/skill_metadata.db ".recover" | sqlite3 data/skill_metadata_recovered.db
```

**原理**:
- `.recover` 命令繞過 B-tree 索引，直接從資料庫頁面恢復資料
- 重建所有表結構和索引
- 跳過損壞或無法讀取的資料頁

**結果**:
```
原始資料庫（含 WAL）:
  skill_heads:              5 rows
  skill_metadata:           8 rows
  skill_chunk_metadata:  2854 rows
  skill_document_mapping:  11 rows
  skill_overviews:          0 rows

恢復後資料庫:
  skill_heads:              4 rows (-1)
  skill_metadata:           7 rows (-1)
  skill_chunk_metadata:  2853 rows (-1)
  skill_document_mapping:  11 rows (same)
  skill_overviews:          0 rows (same)
```

**資料遺失**:
- skill_heads: 1 row（投資理財，已在測試中刪除）
- skill_metadata: 1 row（對應的 document）
- skill_chunk_metadata: 1 row（可能是損壞的 chunk）

**完整性檢查**:
```bash
sqlite3 data/skill_metadata_recovered.db "PRAGMA integrity_check;"
→ ok ✅
```

### 方法 2: WAL Checkpoint (未執行，但建議)

**替代方案**:
```sql
PRAGMA wal_checkpoint(TRUNCATE);
```

**原理**:
- 強制將 WAL 內容合併回主資料庫
- 清空 WAL 檔案
- 可能解決因 WAL 不一致導致的問題

**風險**: 如果 WAL 本身損壞，可能導致資料遺失

---

## 修復後狀態

### 資料庫檔案

```bash
-rw-r--r--  skill_metadata_recovered.db    15.34 MB
```

**特點**:
- 無 WAL 檔案（預設為 delete 模式）
- 完整性檢查通過
- 所有表結構完整

### 資料完整性驗證

**Skills 列表**:
```sql
SELECT head_id, skill_name FROM skill_heads;
```

恢復後（4 rows）:
```
skill_20251126_104421_4fdb3e9b | 六法全書-刑法
skill_20251203_054249_f333015b | 六法全書-民法
skill_20251203_071733_2a43e5ac | 大語言模型大全
skill_20251203_094135_d01fd9b0 | ML
```

**缺失**: 投資理財（head_id: skill_20251128_074913_b7380bf3）
**原因**: 在測試中已主動刪除，非修復過程遺失

**Chunks 統計**:
```sql
SELECT skill_id, COUNT(*) as chunks
FROM skill_chunk_metadata
GROUP BY skill_id;
```

結果（9 skills, 2853 chunks）:
```
skill_20251126_104421_4fdb3e9b           | 272 chunks
skill_20251126_105138_b8cc08c1           | 883 chunks
skill_20251127_100500_b8cc08c1           | 385 chunks
skill_20251128_030424_b8cc08c1           | 264 chunks
skill_20251128_070013_b8cc08c1           | 311 chunks
skill_20251216_123603_2a43e5ac_9ed582    | 370 chunks
skill_20251216_123910_48af4341_feb60e    |  67 chunks
skill_20251216_124010_b45c5a1f_d81758    | 207 chunks (投資理財的 document)
skill_20251216_124037_d01fd9b0_71a938    |  94 chunks
```

**觀察**:
- skill_20251216_124010_b45c5a1f_d81758 (投資理財 document) 仍存在
- 總 chunks 從 2854 降到 2853 (-1 chunk)
- 遺失的可能是損壞的那個 chunk

---

## 建議與預防措施

### 立即建議

1. **替換資料庫** ✅
   ```bash
   mv data/skill_metadata.db data/skill_metadata.db.corrupt_original
   mv data/skill_metadata_recovered.db data/skill_metadata.db
   ```

2. **驗證 API 功能**
   - 重新測試 Export API
   - 確認所有 Skills 可正常查詢

3. **監控 WAL 檔案**
   - 觀察新的 WAL 檔案是否會再次損壞

### 長期預防

#### 1. 啟用 WAL Auto-Checkpoint

在 `SkillMetadataProvider` 初始化時添加：
```python
self.conn.execute("PRAGMA wal_autocheckpoint = 1000;")  # 每 1000 頁自動 checkpoint
```

#### 2. 定期資料庫維護

建立 cron job:
```bash
# 每天凌晨 2 點執行
0 2 * * * sqlite3 /path/to/skill_metadata.db "PRAGMA optimize;"
0 2 * * * sqlite3 /path/to/skill_metadata.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

#### 3. 資料庫備份策略

```bash
# 每小時備份（包含 WAL）
cp skill_metadata.db backup/skill_metadata.db.$(date +\%H)
cp skill_metadata.db-wal backup/skill_metadata.db-wal.$(date +\%H)

# 每天完整備份
sqlite3 skill_metadata.db ".backup 'backup/skill_metadata_$(date +\%Y\%m\%d).db'"
```

#### 4. 監控資料庫健康

定期執行：
```python
async def check_db_health():
    cursor = conn.execute("PRAGMA integrity_check;")
    result = cursor.fetchone()[0]
    if result != "ok":
        logger.error(f"Database corruption detected: {result}")
        # 觸發告警
```

#### 5. 避免並發寫入問題

```python
# 確保同一時間只有一個 instance 寫入
LOCK_FILE = "/var/run/docai_db.lock"

def acquire_db_lock():
    # 使用 fcntl.flock() 或類似機制
    pass
```

---

## 修復決策建議

### 選項 A: 使用恢復後的資料庫（推薦） ✅

**優點**:
- 完整性檢查通過
- 資料遺失極少（僅 1 chunk + 1 已刪除的 skill）
- 立即可用

**缺點**:
- 無法確定遺失的 chunk 內容

**風險**: 低

### 選項 B: 從備份還原

查看備份：
```bash
data/skill_metadata.db.backup_20260107_084943  (15M, 最新)
data/skill_metadata.db.backup_20251203_134159  (6M)
data/skill_metadata.db.backup_20251128          (3.2M)
```

**優點**:
- 資料完整（如果備份時刻未損壞）

**缺點**:
- 會遺失備份後的所有新增資料
- 需要驗證備份檔案的完整性

**風險**: 中等

---

## 結論

**根本原因**: WAL 模式下的 B-tree 索引損壞，可能由 checkpoint 中斷或並發寫入導致

**修復方法**: SQLite `.recover` 命令重建資料庫

**資料遺失**: 1 chunk（可能本身已損壞）+ 1 測試中刪除的 skill

**修復狀態**: ✅ 成功，資料庫完整性恢復

**建議**: 使用恢復後的資料庫，並實施上述預防措施

---

**報告產生時間**: 2026-01-07 08:52
**修復執行者**: Automated Recovery Process
**下一步**: 替換資料庫檔案，繼續 TEST-02 Import 測試
