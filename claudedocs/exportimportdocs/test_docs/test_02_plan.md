# TEST-02: 大語言模型大全 Export/Import 完整測試計劃

**建立日期**: 2026-01-08
**測試目標**: 使用健康資料驗證 Export/Import 完整流程
**測試 Skill**: 大語言模型大全

---

## 📊 測試 Skill 資訊

| 項目 | 值 |
|------|-----|
| **Skill Name** | 大語言模型大全 |
| **Head ID** | skill_20251203_071733_2a43e5ac |
| **Skill ID** | skill_20251216_123603_2a43e5ac_9ed582 |
| **Source Name** | Build_a_Large_Language_Model_From_Scratch_manning_2024 |
| **Chunks** | 369 |
| **Non-empty Chunks** | 369 (100%) ✅ |
| **資料品質** | 健康 ✅ |

---

## 📋 測試計劃

### Phase 0: 備份原始資料

**目的**: 保存測試前的完整資料狀態

**步驟**:
1. 建立 `claudedocs/exportimportdocs/original_data_backup/office/` 目錄
2. 複製 `data/skill_metadata.db` 到備份目錄
3. 複製 `data/faiss_indices/skills/skill_20251216_123603_2a43e5ac_9ed582/` 到備份目錄
4. 驗證備份完整性

**預期結果**:
- 備份目錄包含完整的 db 檔案
- 備份目錄包含 FAISS 索引檔案

---

### Phase 1: Export 大語言模型大全 Skill

**目的**: 驗證 Export API 能正確匯出健康的 Skill

**步驟**:
1. 呼叫 Export API: `GET /api/v1/skills/config/skills/export/skill_20251203_071733_2a43e5ac`
2. 儲存 ZIP 到 `claudedocs/exportimportdocs/test_results/test02_大語言模型大全.zip`
3. 記錄 HTTP 狀態碼和檔案大小

**預期結果**:
- HTTP 200
- ZIP 檔案大小 > 1MB（因有 369 chunks）
- 無錯誤訊息

---

### Phase 2: 驗證 Export ZIP 內容

**目的**: 確認 ZIP 內容完整且資料正確

**驗證項目**:
1. **manifest.json**
   - skill_name = "大語言模型大全"
   - total_chunks = 369
   - document_count = 1

2. **skill_chunk_metadata.csv**
   - 行數 = 370（369 + header）
   - chunk_text 欄位非空

3. **FAISS 索引**
   - index.faiss 存在
   - index.pkl 存在

**預期結果**:
- 所有 CSV 檔案格式正確
- chunk_text 欄位有實際內容
- FAISS 檔案完整

---

### Phase 3: 刪除原 Skill 並 Import

**目的**: 驗證 Import 能正確還原 Skill

**步驟**:
1. 記錄刪除前的資料庫狀態
2. 手動刪除原 Skill（所有 5 個相關表）：
   ```sql
   DELETE FROM skill_chunk_metadata WHERE skill_id = 'skill_20251216_123603_2a43e5ac_9ed582';
   DELETE FROM skill_document_mapping WHERE skill_id = 'skill_20251216_123603_2a43e5ac_9ed582';
   DELETE FROM skill_overviews WHERE skill_id = 'skill_20251216_123603_2a43e5ac_9ed582';
   DELETE FROM skill_metadata WHERE head_id = 'skill_20251203_071733_2a43e5ac';
   DELETE FROM skill_heads WHERE head_id = 'skill_20251203_071733_2a43e5ac';
   ```
3. 刪除 FAISS 目錄：`rm -rf data/faiss_indices/skills/skill_20251216_123603_2a43e5ac_9ed582`
4. 呼叫 Import API: `POST /api/v1/skills/config/skills/import`
5. 記錄新的 head_id 和 skill_id

**預期結果**:
- Import 成功（HTTP 200）
- 新 ID 與原 ID 不同（ID remapping 正確）
- 資料庫有新的記錄

---

### Phase 4: 驗證 Import 資料完整性

**目的**: 確認匯入的資料與原始資料一致

**驗證項目**:
1. **skill_heads 表**
   - 有新的 head_id 記錄
   - skill_name = "大語言模型大全"

2. **skill_metadata 表**
   - 有對應的 skill_id 記錄
   - source_name 正確

3. **skill_chunk_metadata 表**
   - COUNT = 369
   - chunk_text 非空數量 = 369

4. **FAISS 索引**
   - 新目錄存在
   - 檔案大小與原始相近

**預期結果**:
- 所有 369 chunks 完整匯入
- 所有 chunk_text 非空
- FAISS 索引可載入

---

### Phase 5: 執行 Query 功能測試

**目的**: 驗證匯入後的 Skill 可正常查詢

**測試問題**:
1. "什麼是 LLM?"
2. "如何訓練大語言模型?"
3. "Transformer 架構是什麼?"

**步驟**:
1. 取得新的 skill_id
2. 呼叫 Query API: `POST /api/v1/skills/demo/query`
3. 驗證回傳的 context 非空
4. 驗證 LLM 回答有引用來源

**預期結果**:
- Query API 返回 HTTP 200
- context 包含相關內容
- LLM 能基於內容回答問題

---

### Phase 6: 產生測試報告

**目的**: 記錄完整測試結果

**報告內容**:
1. 測試總結（Pass/Fail）
2. 各階段詳細結果
3. 資料完整性統計
4. 效能指標（時間、檔案大小）
5. 發現的問題與建議

---

## ⏱️ 預估時間

| Phase | 預估時間 |
|-------|----------|
| Phase 0 | 5 min |
| Phase 1 | 5 min |
| Phase 2 | 10 min |
| Phase 3 | 10 min |
| Phase 4 | 10 min |
| Phase 5 | 15 min |
| Phase 6 | 10 min |
| **總計** | **~65 min** |

---

## 🎯 成功標準

- [ ] Phase 0: 備份檔案完整
- [ ] Phase 1: Export 成功，ZIP 檔案 > 1MB
- [ ] Phase 2: CSV chunk_text 100% 非空
- [ ] Phase 3: Import 成功，新 ID 生成
- [ ] Phase 4: 369 chunks 完整匯入
- [ ] Phase 5: Query 返回相關內容
- [ ] Phase 6: 測試報告完成

---

## 🛡️ 風險與應對

| 風險 | 應對方案 |
|------|----------|
| Export 失敗 | 檢查 head_id 是否正確 |
| Import 衝突 | 確保完整刪除原資料 |
| Query 失敗 | 驗證 skill_id 是否正確 |
| 資料遺失 | 從 office 備份還原 |

---

**計劃狀態**: 待批准
**下一步**: 確認後開始執行 Phase 0
