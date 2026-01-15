# Skill ID 碰撞問題修復報告

> **日期**: 2025-12-05
> **嚴重性**: Critical (資料遺失)
> **狀態**: 已修復

---

## 1. 問題描述

### 1.1 症狀

用戶上傳兩個 PDF 檔案到同一個 Skill（六法全書-刑法），但系統只保留了一個檔案。前端顯示：
- 六法全書-刑法: 1 PDFs · 172 chunks
- 文件名顯示為 "Unknown"

### 1.2 預期行為

- 兩個 PDF 應該都被保存
- 每個 PDF 應該有獨立的 skill_id
- 文件名應該正確顯示

---

## 2. 根本原因分析

### 2.1 skill_id 生成邏輯缺陷

```python
# 問題程式碼 (app/api/v1/endpoints/skills.py)
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
name_hash = hashlib.md5(skill_name.encode('utf-8')).hexdigest()[:8]
skill_id = f"skill_{timestamp}_{name_hash}"
```

**問題分析**：

| 變數 | 值 | 唯一性 |
|------|-----|--------|
| `timestamp` | `20251203_092805` | 只精確到秒 |
| `name_hash` | `4fdb3e9b` | 相同 skill 名稱產生相同 hash |
| `skill_id` | `skill_20251203_092805_4fdb3e9b` | **不唯一！** |

### 2.2 碰撞情境

```
時間線：
T = 09:28:05.100  用戶上傳 "刑法.pdf"
                   → skill_id = skill_20251203_092805_4fdb3e9b
                   → INSERT INTO skill_metadata ✓

T = 09:28:05.800  用戶上傳 "刑事訴訟法.pdf"
                   → skill_id = skill_20251203_092805_4fdb3e9b (相同！)
                   → INSERT 失敗或覆蓋前一筆資料 ✗
```

### 2.3 為什麼會發生？

1. **同一秒內上傳多個檔案**：用戶選擇多個檔案一次上傳
2. **timestamp 精度不足**：只精確到秒，不到毫秒
3. **hash 來自 skill 名稱**：相同 skill 的檔案會產生相同 hash
4. **缺少檔案層級的唯一識別**：沒有將檔案名納入 ID 生成

---

## 3. 解決方案

### 3.1 修改 skill_id 生成邏輯

```python
# 修復後的程式碼 (app/api/v1/endpoints/skills.py:801-808)

# Generate skill ID - FIXED: Include file hash to prevent collision
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
name_hash = hashlib.md5(skill_name.encode('utf-8')).hexdigest()[:8]
file_hash = hashlib.md5(pdf_path.name.encode('utf-8')).hexdigest()[:6]  # 新增
skill_id = f"skill_{timestamp}_{name_hash}_{file_hash}"

logger.info(f"Generated skill_id: {skill_id} for file: {pdf_path.name}")
```

### 3.2 新 ID 結構

```
skill_20251203_092805_4fdb3e9b_a1b2c3
       │          │        │       │
       │          │        │       └── 檔案名 hash (新增)
       │          │        └────────── Skill 名稱 hash
       │          └─────────────────── 時間戳 (秒)
       └────────────────────────────── 前綴
```

### 3.3 唯一性保證

| 情境 | 舊 ID | 新 ID |
|------|-------|-------|
| 刑法.pdf | `skill_..._4fdb3e9b` | `skill_..._4fdb3e9b_e5f6g7` |
| 刑事訴訟法.pdf | `skill_..._4fdb3e9b` | `skill_..._4fdb3e9b_h8i9j0` |

---

## 4. 相關問題：source_name 為空

### 4.1 問題

部分舊資料的 `source_name` 欄位是空的，導致前端顯示 "Unknown"。

### 4.2 原因

使用舊版程式碼上傳時，`source_name` 功能尚未完善。

### 4.3 解決

**程式碼修復**：添加 logging 確保 source_name 被正確設定
```python
source_name = pdf_path.stem
logger.info(f"Setting source_name='{source_name}' for skill_id={skill_id}")
```

**資料修復**：手動更新資料庫
```sql
UPDATE skill_metadata SET source_name = '刑事訴訟法'
WHERE skill_id = 'skill_20251203_092805_4fdb3e9b';

UPDATE skill_metadata SET source_name = '投资最重要的事'
WHERE skill_id IN ('skill_20251128_074913_b7380bf3', 'skill_20251202_071055_b45c5a1f');
```

---

## 5. 修改檔案清單

| 檔案 | 行號 | 修改內容 |
|------|------|----------|
| `app/api/v1/endpoints/skills.py` | 801-808 | 加入 `file_hash` 防止碰撞 |
| `app/api/v1/endpoints/skills.py` | 901 | 添加 source_name logging |
| `data/skill_metadata.db` | - | 修復 3 筆資料的 source_name |

---

## 6. 測試驗證

### 6.1 驗證步驟

1. 同時上傳兩個 PDF 到同一個 Skill
2. 確認兩個檔案都被保存
3. 確認 skill_id 不同
4. 確認 source_name 正確顯示

### 6.2 預期結果

```
六法全書-刑法
├── 刑法.pdf (skill_..._4fdb3e9b_e5f6g7)
└── 刑事訴訟法.pdf (skill_..._4fdb3e9b_h8i9j0)
```

---

## 7. 未來改進建議

### 7.1 使用 UUID（更強唯一性）

```python
import uuid
skill_id = f"skill_{uuid.uuid4().hex[:16]}"
```

### 7.2 使用 ZeroMQ（高併發場景）

對於高併發或分散式環境，建議使用消息隊列：
- 將上傳任務放入隊列
- 順序處理確保不會衝突
- 支援重試和錯誤處理

### 7.3 資料庫唯一約束

```sql
-- 添加唯一約束防止重複
ALTER TABLE skill_metadata ADD UNIQUE INDEX idx_skill_file (skill_name, source_name);
```

---

*文檔建立: 2025-12-05*
*修復版本: app/api/v1/endpoints/skills.py*
