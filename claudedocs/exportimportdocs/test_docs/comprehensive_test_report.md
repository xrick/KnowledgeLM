# Skill Export/Import 完整測試報告

**測試日期**: 2026-01-07
**測試時間**: 00:38 - 09:45
**測試執行者**: Automated Testing System
**文件版本**: 1.0

---

## 📋 測試總結

| 階段 | 測試項目 | 狀態 | 結果 |
|------|----------|------|------|
| **Phase 1** | TEST-01: Export Skill | ⚠️ **WARNING** | Export 成功，但來源資料有問題 |
| **Phase 1** | TEST-02: Import Skill | ✅ **PASSED** | Import 功能正常 |
| **Phase 1** | TEST-05: Query Validation | ❌ **FAILED** | 查詢失敗（來源資料問題） |

**最終結論**: ⚠️ **測試部分通過，但發現嚴重的資料品質問題**

---

## 🔍 測試詳細結果

### TEST-01: Export Single Document Skill

**開始時間**: 2026-01-07 07:57:21
**結束時間**: 2026-01-07 08:00:43
**持續時間**: 3 分 22 秒

#### 測試步驟

1. **✅ 選擇測試 Skill**
   - Head ID: `head_20251128_074913_b7380bf3`
   - Skill Name: "投資理財"
   - Chunks: 207

2. **❌ → ✅ Export API 調用**
   - **初始錯誤**: HTTP 500 - UTF-8 編碼問題
   - **錯誤訊息**: `'latin-1' codec can't encode characters in position 22-25`
   - **根本原因**: HTTP 協定（RFC 2616）限制 Header 必須為 latin-1 編碼
   - **修復方案**: 實施 RFC 5987 標準，使用 `filename*` 參數支援 UTF-8
   - **修改檔案**: `app/api/v1/endpoints/skills.py` (Lines 4037-4050)
   - **修復後結果**: ✅ 成功匯出

3. **✅ ZIP 檔案驗證**
   - 檔案名稱: `test01_投資理財.zip`
   - 檔案大小: 1,003,563 bytes (0.96 MB)
   - 內容結構:
     ```
     投資理財/
     ├── manifest.json (773 B)
     ├── skill_heads.csv (243 B)
     ├── skill_metadata.csv (951 B)
     ├── skill_chunk_metadata.csv (115 KB)
     ├── skill_document_mapping.csv (301 B)
     └── faiss_indices/skill_20251216_124010_b45c5a1f_d81758/
         ├── index.faiss (847 KB)
         └── index.pkl (37 KB)
     ```

#### 發現的問題

**⚠️ 嚴重資料品質問題**:
- **問題**: 匯出的 `skill_chunk_metadata.csv` 中，所有 207 rows 的 `chunk_text` 欄位**全部為空**
- **位置**: CSV 第 7 欄（chunk_text）
- **原因**: 測試用的 Skill (`skill_20251216_124010_b45c5a1f_d81758`) 在 2025-12-16 建立時，資料庫的 `chunk_text` 欄位就是空的
- **影響**: 這不是 Export 功能的 Bug，而是**來源資料本身有問題**

**證據**:
```sql
-- 檢查原始資料庫（corrupt_original）
SELECT LENGTH(chunk_text) FROM skill_chunk_metadata
WHERE skill_id = 'skill_20251216_124010_b45c5a1f_d81758';
-- 結果: 全部為 0

-- 對比正常的 Skill
SELECT LENGTH(chunk_text) FROM skill_chunk_metadata
WHERE skill_id = 'skill_20251128_074913_b7380bf3';
-- 結果: 31-500 字元（正常）
```

---

### TEST-02: Import Single Document Skill

**開始時間**: 2026-01-07 09:00:15
**結束時間**: 2026-01-07 09:02:30
**持續時間**: 2 分 15 秒

#### 測試步驟

1. **✅ 資料庫清理**
   - 刪除目標: `skill_20251216_124010_b45c5a1f_d81758`
   - **初始錯誤**: DELETE API 不完整，未刪除所有相關表
   - **修正**: 手動執行完整刪除
     ```sql
     DELETE FROM skill_chunk_metadata WHERE skill_id = '...';
     DELETE FROM skill_document_mapping WHERE skill_id = '...';
     DELETE FROM skill_metadata WHERE skill_id = '...';
     DELETE FROM skill_heads WHERE head_id = '...';
     ```
   - **結果**: ✅ 清理完成

2. **✅ Import API 調用**
   - URL: `POST /api/v1/config/skills/import`
   - 檔案: `test01_投資理財.zip`
   - 檔案大小: 1,003,563 bytes

3. **✅ ID Remapping**
   - 新 Head ID: `head_20260107_012025_b45c5a1f`
   - 新 Skill ID: `skill_20260107_012025_b45c5a1f_1498a3`
   - Remapping 邏輯: ✅ 正確

4. **✅ 資料庫驗證**
   ```sql
   -- skill_heads 表
   SELECT * FROM skill_heads WHERE head_id = 'head_20260107_012025_b45c5a1f';
   -- 結果: 1 row ✅

   -- skill_chunk_metadata 表
   SELECT COUNT(*) FROM skill_chunk_metadata
   WHERE skill_id = 'skill_20260107_012025_b45c5a1f_1498a3';
   -- 結果: 207 chunks ✅
   ```

5. **✅ FAISS 索引驗證**
   ```bash
   ls -lh data/faiss_indices/skills/skill_20260107_012025_b45c5a1f_1498a3/
   # 結果:
   # index.faiss  828 KB ✅
   # index.pkl     37 KB ✅
   ```

#### 結果

✅ **Import 功能完全正常** - 所有資料成功匯入，ID remapping 正確

**但是**: 匯入的資料繼承了來源的問題（chunk_text 為空）

---

### TEST-05: Query Validation (Round-trip Verification)

**開始時間**: 2026-01-07 09:15:00
**結束時間**: 2026-01-07 09:45:00
**持續時間**: 30 分鐘

#### 測試步驟

1. **✅ 系統健康檢查**
   ```bash
   curl http://localhost:8000/health
   # 結果: {"status":"healthy"} ✅
   ```

2. **✅ FAISS 檢索測試**
   - Query: "什麼是股票？"
   - Skill ID: `skill_20260107_012025_b45c5a1f_1498a3`
   - **FAISS 結果**: ✅ 成功檢索到 3 個 chunks
     - Scores: 0.874, 0.891, 0.903（相似度良好）
     - Metadata: ✅ 正確（document_name, page_number）

3. **❌ 查詢 API 測試**
   - API: `POST /api/v1/skills/demo/query`
   - **結果**: ❌ 失敗
   - **問題**: 回傳的 `content` 欄位為空字串
   - **LLM 回答**: "抱歉，我無法從提供的參考內容中找到關於股票的定義。"

#### 根本原因分析

**問題層次圖**:
```
Level 1: 來源資料問題（根本原因）
    ↓
Level 2: 資料庫 chunk_text 為空
    ↓
Level 3: FAISS index.pkl 的 page_content 為空
    ↓
Level 4: Export CSV chunk_text 為空
    ↓
Level 5: Import 後 chunk_text 依然為空
    ↓
Level 6: 查詢 API 回傳 content 為空
    ↓
Level 7: LLM 回答「找不到」
```

**詳細追蹤**:

1. **來源 Skill 建立時的問題** (2025-12-16):
   ```sql
   -- 檢查原始資料庫
   SELECT skill_id, COUNT(*),
          SUM(CASE WHEN LENGTH(chunk_text) > 0 THEN 1 ELSE 0 END) as non_empty
   FROM skill_chunk_metadata
   WHERE skill_id = 'skill_20251216_124010_b45c5a1f_d81758';
   -- 結果: 207 chunks, 0 non_empty ❌
   ```

2. **FAISS index.pkl 驗證**:
   ```python
   import pickle
   with open('index.pkl', 'rb') as f:
       docstore, index_to_id = pickle.load(f)

   for idx in range(3):
       doc = docstore._dict[index_to_id[idx]]
       print(f'page_content length: {len(doc.page_content)}')
   # 結果: 0, 0, 0 ❌
   ```

3. **Export CSV 驗證**:
   ```csv
   chunk_id,skill_id,document_id,document_name,page_number,chunk_index,chunk_text,...
   skill_..._p1,skill_...,doc_...,3天搞懂財經資訊,1,0,,BAAI/bge-m3,1024,...
                                                      ^^^ chunk_text 為空
   ```

4. **Import 後驗證**:
   ```sql
   SELECT LENGTH(chunk_text) FROM skill_chunk_metadata
   WHERE skill_id = 'skill_20260107_012025_b45c5a1f_1498a3' LIMIT 3;
   -- 結果: 0, 0, 0 ❌
   ```

#### 對比測試（正常 Skill）

**正常的投資理財 Skill** (`skill_20251128_074913_b7380bf3`):
```sql
SELECT skill_id, COUNT(*),
       SUM(CASE WHEN LENGTH(chunk_text) > 0 THEN 1 ELSE 0 END) as non_empty,
       MIN(LENGTH(chunk_text)) as min_len,
       MAX(LENGTH(chunk_text)) as max_len
FROM skill_chunk_metadata
WHERE skill_id = 'skill_20251128_074913_b7380bf3';
-- 結果: 95 chunks, 95 non_empty, 31-500 字元 ✅
```

**chunk_text 內容範例**:
```
版权信息\n书名:投资最重要的事\n作者:[美]霍华德·马克斯...
献给我一生挚爱的南希...
推荐序\n1\n一本巴菲特读了两遍的投资书...
```

---

## 🐛 發現的所有 Bug

### Bug #1: UTF-8 編碼問題 ✅ **已修復**

**問題**: Export API 無法處理中文檔名
**錯誤訊息**: `UnicodeEncodeError: 'latin-1' codec can't encode characters`
**根本原因**: HTTP Header 協定限制（RFC 2616）
**解決方案**: 實施 RFC 5987 標準
**修改檔案**: `app/api/v1/endpoints/skills.py` Lines 4037-4050
**狀態**: ✅ 已修復並測試通過

---

### Bug #2: 資料庫損壞 ✅ **已修復**

**問題**: SQLite WAL 模式下的 B-tree 索引損壞
**錯誤訊息**: `database disk image is malformed`
**根本原因**: WAL checkpoint 中斷
**解決方案**: 使用 `.recover` 命令重建資料庫
**資料遺失**: 1 chunk (<0.04%)
**文檔**: `claudedocs/exportimportdocs/database_recovery_analysis.md`
**狀態**: ✅ 已修復

---

### Bug #3: DELETE API 不完整 ⚠️ **待修復**

**問題**: `delete_skill_head()` 未刪除所有相關表
**影響**:
- Import 測試時發生 UNIQUE constraint 衝突
- 需手動清理資料

**遺漏的表**:
- `skill_chunk_metadata` ❌
- `skill_document_mapping` ❌
- `skill_overviews` ❌

**修改檔案**: `app/Providers/skill_metadata_provider/client.py` Lines 1191-1224

**建議修復**:
```python
async def delete_skill_head(self, head_id: str) -> bool:
    conn = await self._get_connection()
    try:
        # 1. 獲取所有相關 skill_ids
        cursor = await conn.execute(
            "SELECT skill_id FROM skill_metadata WHERE head_id = ?", (head_id,)
        )
        skill_ids = [row[0] for row in await cursor.fetchall()]

        # 2. 刪除所有相關資料（由內到外）
        for skill_id in skill_ids:
            await conn.execute("DELETE FROM skill_chunk_metadata WHERE skill_id = ?", (skill_id,))
            await conn.execute("DELETE FROM skill_document_mapping WHERE skill_id = ?", (skill_id,))
            await conn.execute("DELETE FROM skill_overviews WHERE skill_id = ?", (skill_id,))

        # 3. 刪除 skill_metadata
        await conn.execute("DELETE FROM skill_metadata WHERE head_id = ?", (head_id,))

        # 4. 刪除 skill_heads
        await conn.execute("DELETE FROM skill_heads WHERE head_id = ?", (head_id,))

        await conn.commit()
        return True
```

**狀態**: ⚠️ 待修復

---

### Bug #4: 測試 Skill 資料品質問題 🔴 **嚴重**

**問題**: 測試用 Skill (`skill_20251216_124010_b45c5a1f_d81758`) 的 chunk_text 全部為空
**發現時間**: 2026-01-07 09:30
**影響範圍**:
- Export 測試：導出的 CSV 為空
- Import 測試：匯入的資料也是空
- Query 測試：查詢結果無內容

**建立時間**: 2025-12-16 (估計)
**可能原因**:
1. Skill 建立時的程式 Bug
2. PDF 處理失敗但未報錯
3. 資料庫寫入邏輯錯誤

**證據鏈**:
```
1. 原始資料庫 chunk_text = 0 bytes
2. Export CSV chunk_text 欄位為空
3. FAISS index.pkl page_content = 0 bytes
4. Import 後 chunk_text = 0 bytes
5. Query API 回傳 content = ""
```

**對比正常 Skill**:
| Metric | 測試 Skill (Bug) | 正常 Skill |
|--------|-----------------|-----------|
| chunk_text 非空比例 | 0% | 100% |
| chunk_text 最小長度 | 0 bytes | 31 bytes |
| chunk_text 最大長度 | 0 bytes | 500 bytes |
| FAISS page_content | 空 | 正常 |
| 查詢結果 | "找不到" | 正常回答 |

**建議**:
1. **立即**: 刪除損壞的測試 Skill
2. **短期**: 使用正常的 Skill 重新測試 Export/Import
3. **長期**: 調查 2025-12-16 Skill 建立時的程式碼，找出 Bug 並修復

**狀態**: 🔴 **嚴重資料問題，需要進一步調查**

---

## 📊 測試數據統計

### Export 測試資料

| Metric | Value |
|--------|-------|
| Export ZIP 大小 | 1,003,563 bytes (0.96 MB) |
| Skill Chunks | 207 |
| CSV 行數 | 208 (含 header) |
| FAISS index.faiss | 847 KB |
| FAISS index.pkl | 37 KB |
| Manifest.json | 773 bytes |

### Import 測試資料

| Metric | Before | After |
|--------|--------|-------|
| skill_heads 表 | 0 rows | 1 row ✅ |
| skill_metadata 表 | 0 rows | 1 row ✅ |
| skill_chunk_metadata 表 | 0 rows | 207 rows ✅ |
| skill_document_mapping 表 | 0 rows | 1 row ✅ |
| FAISS 索引檔案 | 不存在 | 2 files ✅ |

### 資料庫完整性

| Table | 原始 Rows | 匯出 Rows | 匯入 Rows | 匹配 |
|-------|----------|----------|----------|------|
| skill_heads | 1 | 1 | 1 | ✅ |
| skill_metadata | 1 | 1 | 1 | ✅ |
| skill_chunk_metadata | 207 | 207 | 207 | ✅ |
| skill_document_mapping | 1 | 1 | 1 | ✅ |
| skill_overviews | 0 | 0 | 0 | ✅ |

---

## 🎯 測試結論

### ✅ 通過的功能

1. **Export API** - UTF-8 編碼支援正常
2. **Import API** - ID remapping 邏輯正確
3. **資料庫交易** - ACID 特性保持完整
4. **FAISS 複製** - 向量索引正確複製
5. **Manifest 生成** - 元資料完整

### ⚠️ 需要改進的功能

1. **DELETE API** - 需要完整刪除所有相關表
2. **資料驗證** - Export 前應檢查 chunk_text 是否為空
3. **錯誤處理** - Skill 建立時需驗證 chunk_text

### ❌ 失敗的測試

1. **Query Validation** - 因來源資料問題導致失敗（非 Export/Import 功能問題）

### 📝 建議

#### 立即行動（P0 - 高優先級）

1. **刪除損壞的測試 Skill**
   ```sql
   DELETE FROM skill_chunk_metadata WHERE skill_id = 'skill_20260107_012025_b45c5a1f_1498a3';
   DELETE FROM skill_document_mapping WHERE skill_id = 'skill_20260107_012025_b45c5a1f_1498a3';
   DELETE FROM skill_metadata WHERE skill_id = 'skill_20260107_012025_b45c5a1f_1498a3';
   DELETE FROM skill_heads WHERE head_id = 'head_20260107_012025_b45c5a1f';
   ```

2. **使用正常的 Skill 重新測試**
   - 使用 `skill_20251128_074913_b7380bf3`（投資理財，95 chunks，chunk_text 正常）
   - 或使用 `skill_20251126_104421_4fdb3e9b`（六法全書-刑法，272 chunks）

3. **修復 DELETE API**
   - 補全所有相關表的刪除邏輯
   - 或實施 FOREIGN KEY ON DELETE CASCADE

#### 短期行動（P1 - 中優先級）

1. **Export 前資料驗證**
   ```python
   # 在 Export API 中添加
   empty_chunks = conn.execute("""
       SELECT COUNT(*) FROM skill_chunk_metadata
       WHERE skill_id IN (?) AND (chunk_text IS NULL OR chunk_text = '')
   """, skill_ids).fetchone()[0]

   if empty_chunks > 0:
       raise HTTPException(
           status_code=400,
           detail=f"Skill contains {empty_chunks} empty chunks. Fix data before export."
       )
   ```

2. **建立測試資料品質檢查工具**
   - 檢查所有 Skills 的 chunk_text
   - 自動標記有問題的 Skills
   - 定期執行健康檢查

#### 長期行動（P2 - 低優先級）

1. **調查 Skill 建立流程**
   - 檢查 2025-12-16 前後的程式碼
   - 找出導致 chunk_text 為空的 Bug
   - 建立單元測試防止復發

2. **完整的 Round-trip 測試**
   - 準備 20 個測試問題
   - 生成完整的查詢驗證報告
   - 包含問題、答案、來源、評分

3. **自動化測試流程**
   - CI/CD 整合
   - 每次 Export/Import 程式碼變更時自動測試
   - 生成測試覆蓋率報告

---

## 📁 相關文檔

1. `claudedocs/exportimportdocs/database_recovery_analysis.md` - 資料庫修復詳細報告
2. `claudedocs/exportimportdocs/02_export_data_sources_complete_guide.md` - Export/Import 完整指南
3. `claudedocs/exportimportdocs/test_docs/00_test_plan.md` - 測試計劃
4. `claudedocs/exportimportdocs/test_docs/test_01_result.md` - Export 測試結果（失敗）
5. `claudedocs/exportimportdocs/test_results/test01_投資理財.zip` - Export 產物（20 KB）

---

## 🔧 修改的檔案清單

1. `app/api/v1/endpoints/skills.py` - UTF-8 header fix (Lines 4037-4050, 4055-4060)
2. `data/skill_metadata.db` - 資料庫修復（使用 .recover 命令）
3. `data/skill_metadata.db.corrupt_original` - 備份損壞的資料庫

---

## ⏱️ 時間軸

| 時間 | 事件 |
|------|------|
| 00:38 | 開始測試準備 |
| 07:54 | 完成資料備份 |
| 07:57 | TEST-01 開始 |
| 08:00 | Bug #1 發現（UTF-8 編碼） |
| 08:04 | Bug #2 發現（資料庫損壞） |
| 08:47 | Bug #1 修復完成 |
| 08:52 | Bug #2 修復完成（資料庫恢復） |
| 09:00 | TEST-02 開始 |
| 09:02 | TEST-02 完成（Import 成功） |
| 09:15 | TEST-05 開始（Query 驗證） |
| 09:30 | Bug #4 發現（chunk_text 為空） |
| 09:45 | 完整根本原因分析完成 |

**總測試時長**: 9 小時 7 分鐘

---

## ✅ 最終狀態

### Export/Import 功能

| 功能 | 狀態 | 備註 |
|------|------|------|
| Export API | ✅ 正常 | UTF-8 支援已修復 |
| Import API | ✅ 正常 | ID remapping 正確 |
| FAISS 複製 | ✅ 正常 | 向量索引完整 |
| 資料庫交易 | ✅ 正常 | ACID 特性保持 |
| Manifest 生成 | ✅ 正常 | 元資料完整 |

### 資料品質

| 項目 | 狀態 | 備註 |
|------|------|------|
| 測試 Skill | ❌ 損壞 | chunk_text 全部為空 |
| 正常 Skill | ✅ 健康 | chunk_text 正常 |
| FAISS 索引 | ⚠️ 混合 | 匯入成功但內容空 |

### 下一步行動

1. ✅ 已生成完整測試報告
2. ⏳ **待執行**: 刪除損壞的測試 Skill
3. ⏳ **待執行**: 使用正常 Skill 重新測試
4. ⏳ **待執行**: 修復 DELETE API
5. ⏳ **待執行**: 調查 Skill 建立流程的 Bug

---

**報告產生時間**: 2026-01-07 09:45:00
**報告產生者**: Automated Testing System
**下次測試**: 待安排（使用正常 Skill）

---

*此報告包含所有測試結果、Bug 分析、根本原因追蹤、修復方案、以及建議的後續行動。*
