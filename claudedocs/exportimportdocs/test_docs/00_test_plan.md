# Skill Export/Import 測試計畫

**建立日期**: 2025-12-25
**測試類型**: 功能測試、整合測試、邊界測試
**測試環境**: DocAI Beta Skills System
**測試目標**: 驗證 Skill Export/Import 功能的完整性與可靠性

---

## 📋 測試目標

### 主要目標
1. ✅ 驗證 Export API 能正確匯出 Skill 資料
2. ✅ 驗證 Import API 能正確還原 Skill 資料
3. ✅ 驗證資料完整性（Export → Import 資料一致）
4. ✅ 驗證錯誤處理機制
5. ✅ 驗證邊界條件與異常情況

### 品質標準
- **資料完整性**: 100% (所有資料必須完整匯出/匯入)
- **功能正確性**: 100% (匯入後功能與原始 Skill 一致)
- **錯誤處理**: 所有錯誤情況都有適當的錯誤訊息
- **效能要求**: Export/Import 時間在可接受範圍內

---

## 🎯 測試範圍

### 包含的測試
1. **基本功能測試** (Test 01-05)
   - 單一文件 Skill 匯出/匯入
   - 多文件 Skill 匯出/匯入
   - 大型 Skill 匯出/匯入
   - 資料完整性驗證
   - 功能驗證

2. **邊界條件測試** (Test 06-10)
   - 空 Skill 處理
   - 超大 Skill 處理
   - 特殊字元處理
   - Skill name 衝突處理
   - FAISS 索引缺失處理

3. **錯誤處理測試** (Test 11-15)
   - 不存在的 head_id
   - 損壞的 ZIP 檔案
   - 無效的 manifest.json
   - Checksum 錯誤
   - 資料庫錯誤

4. **整合測試** (Test 16-20)
   - 跨系統匯入
   - 多次匯入同一 Skill
   - 匯入後查詢功能
   - 匯入後編輯功能
   - 備份與還原流程

### 不包含的測試
- ❌ Frontend UI 測試（本測試聚焦於 API）
- ❌ 效能壓測（需要專門的效能測試環境）
- ❌ 並發測試（需要專門的並發測試工具）

---

## 📊 測試分類

### Level 1: 基本功能測試 (Priority: 🔴 High)

| Test ID | 測試名稱 | 測試類型 | 預期時間 |
|---------|----------|----------|----------|
| Test-01 | 單一文件 Skill Export | 功能測試 | 5 min |
| Test-02 | 單一文件 Skill Import | 功能測試 | 5 min |
| Test-03 | 多文件 Skill Export | 功能測試 | 10 min |
| Test-04 | 多文件 Skill Import | 功能測試 | 10 min |
| Test-05 | Export-Import Round-trip | 整合測試 | 15 min |

**總計**: 45 minutes

### Level 2: 資料驗證測試 (Priority: 🔴 High)

| Test ID | 測試名稱 | 測試類型 | 預期時間 |
|---------|----------|----------|----------|
| Test-06 | Database 資料一致性 | 驗證測試 | 10 min |
| Test-07 | FAISS 索引完整性 | 驗證測試 | 10 min |
| Test-08 | Chunk 文字內容驗證 | 驗證測試 | 15 min |
| Test-09 | Metadata 正確性驗證 | 驗證測試 | 10 min |
| Test-10 | 查詢功能驗證 | 功能測試 | 15 min |

**總計**: 60 minutes

### Level 3: 邊界條件測試 (Priority: 🟡 Medium)

| Test ID | 測試名稱 | 測試類型 | 預期時間 |
|---------|----------|----------|----------|
| Test-11 | 空 Skill 處理 | 邊界測試 | 5 min |
| Test-12 | 超大 Skill (10000+ chunks) | 邊界測試 | 20 min |
| Test-13 | 特殊字元 Skill Name | 邊界測試 | 5 min |
| Test-14 | Skill Name 衝突 | 邊界測試 | 10 min |
| Test-15 | 部分 FAISS 缺失 | 邊界測試 | 10 min |

**總計**: 50 minutes

### Level 4: 錯誤處理測試 (Priority: 🟡 Medium)

| Test ID | 測試名稱 | 測試類型 | 預期時間 |
|---------|----------|----------|----------|
| Test-16 | 不存在的 head_id | 錯誤處理 | 5 min |
| Test-17 | 損壞的 ZIP 檔案 | 錯誤處理 | 10 min |
| Test-18 | 無效的 manifest.json | 錯誤處理 | 10 min |
| Test-19 | Checksum 不匹配 | 錯誤處理 | 10 min |
| Test-20 | 資料庫 Transaction 失敗 | 錯誤處理 | 15 min |

**總計**: 50 minutes

### Level 5: 進階場景測試 (Priority: 🟢 Low)

| Test ID | 測試名稱 | 測試類型 | 預期時間 |
|---------|----------|----------|----------|
| Test-21 | 跨系統匯入測試 | 整合測試 | 30 min |
| Test-22 | 多次匯入相同 Skill | 整合測試 | 15 min |
| Test-23 | 匯入後立即匯出 | 整合測試 | 10 min |
| Test-24 | 備份與還原流程 | 整合測試 | 20 min |
| Test-25 | ID 重新映射驗證 | 驗證測試 | 15 min |

**總計**: 90 minutes

---

## 🛠️ 測試環境準備

### 測試資料準備

```bash
# 1. 備份原始資料
mkdir -p claudedocs/exportimportdocs/original_data_backup
cp -r data/skill_metadata.db claudedocs/exportimportdocs/original_data_backup/
cp -r data/faiss_indices/skills claudedocs/exportimportdocs/original_data_backup/

# 2. 建立測試目錄
mkdir -p claudedocs/exportimportdocs/test_data
mkdir -p claudedocs/exportimportdocs/test_results

# 3. 準備測試 Skills
# - 小型 Skill: 六法全書-刑法 (~172 chunks)
# - 中型 Skill: 六法全書-民法 (~533 chunks)
# - 大型 Skill: 大語言模型大全 (~3685 chunks)
```

### 測試工具

| 工具 | 用途 | 命令範例 |
|------|------|----------|
| **curl** | API 測試 | `curl -X GET http://localhost:8000/api/v1/config/skills/export/{head_id}` |
| **sqlite3** | 資料庫驗證 | `sqlite3 data/skill_metadata.db "SELECT COUNT(*) FROM skill_metadata"` |
| **Python** | FAISS 索引驗證 | `python scripts/verify_faiss.py` |
| **diff** | 檔案比對 | `diff original.csv imported.csv` |

### 測試 API Endpoints

| Endpoint | Method | 用途 |
|----------|--------|------|
| `/api/v1/config/skills/export/{head_id}` | GET | 匯出 Skill |
| `/api/v1/config/skills/import` | POST | 匯入 Skill |
| `/api/v1/skills/tree` | GET | 驗證 Skill 結構 |
| `/api/v1/skills/demo/query` | POST | 驗證查詢功能 |

---

## 📝 測試執行流程

### 階段 1: 準備階段 (15 minutes)
1. ✅ 備份原始資料
2. ✅ 準備測試環境
3. ✅ 確認測試 Skills 存在
4. ✅ 啟動 DocAI 服務

### 階段 2: 基本功能測試 (45 minutes)
- 執行 Test-01 到 Test-05
- 記錄測試結果
- 驗證基本功能正常

### 階段 3: 資料驗證測試 (60 minutes)
- 執行 Test-06 到 Test-10
- 深度驗證資料完整性
- 確認功能正確性

### 階段 4: 邊界與錯誤測試 (100 minutes)
- 執行 Test-11 到 Test-20
- 測試邊界條件
- 驗證錯誤處理

### 階段 5: 進階場景測試 (90 minutes)
- 執行 Test-21 到 Test-25
- 整合測試
- 完整流程驗證

### 階段 6: 報告與總結 (30 minutes)
- 整理測試結果
- 生成測試報告
- 提出改進建議

**總測試時間**: ~5.5 hours

---

## 📊 測試成功標準

### 必須通過的測試 (Critical)
- ✅ Test-01 到 Test-05: 基本功能測試
- ✅ Test-06 到 Test-10: 資料驗證測試
- ✅ Test-16 到 Test-20: 錯誤處理測試

### 建議通過的測試 (Recommended)
- ✅ Test-11 到 Test-15: 邊界條件測試
- ✅ Test-21 到 Test-25: 進階場景測試

### 可接受的失敗
- ⚠️ Test-12: 超大 Skill 可能因為資源限制失敗
- ⚠️ Test-21: 跨系統測試可能因為環境差異失敗

---

## 🐛 Bug 追蹤

### 測試過程中發現的 Bug 將記錄在：
```
claudedocs/exportimportdocs/test_docs/bugs/
├── bug_001_description.md
├── bug_002_description.md
└── ...
```

### Bug 優先級定義

| 優先級 | 定義 | 範例 |
|--------|------|------|
| **P0 - Blocker** | 完全無法使用 | Export 失敗，無法生成 ZIP |
| **P1 - Critical** | 資料遺失或損壞 | Import 後 chunks 遺失 |
| **P2 - Major** | 功能受限但可繞過 | Skill name 衝突未處理 |
| **P3 - Minor** | UI 或體驗問題 | 錯誤訊息不清楚 |

---

## 📈 測試報告格式

每個測試的文檔將包含：

### 必要內容
1. **Test Steps**: 詳細的測試步驟
2. **Test Result**: 實際執行結果（Pass/Fail）
3. **Test Description**: 結果解釋與分析

### 可選內容
4. **Screenshots**: 重要步驟的截圖
5. **Logs**: 相關的系統日誌
6. **Metrics**: 效能指標（時間、檔案大小等）
7. **Recommendations**: 改進建議

---

## 🔄 測試執行順序

### 建議執行順序

```
Phase 1: Smoke Test (快速驗證基本功能)
├── Test-01: Export 單一文件 Skill
├── Test-02: Import 單一文件 Skill
└── Test-05: Round-trip 驗證

Phase 2: Core Functionality (核心功能深度測試)
├── Test-03: Export 多文件 Skill
├── Test-04: Import 多文件 Skill
├── Test-06: Database 一致性
├── Test-07: FAISS 完整性
├── Test-08: Chunk 內容驗證
├── Test-09: Metadata 驗證
└── Test-10: 查詢功能驗證

Phase 3: Edge Cases (邊界條件)
├── Test-11: 空 Skill
├── Test-12: 超大 Skill
├── Test-13: 特殊字元
├── Test-14: Name 衝突
└── Test-15: FAISS 缺失

Phase 4: Error Handling (錯誤處理)
├── Test-16: 不存在的 head_id
├── Test-17: 損壞的 ZIP
├── Test-18: 無效的 manifest
├── Test-19: Checksum 錯誤
└── Test-20: Transaction 失敗

Phase 5: Integration (整合測試)
├── Test-21: 跨系統匯入
├── Test-22: 多次匯入
├── Test-23: 匯入後匯出
├── Test-24: 備份還原
└── Test-25: ID 重新映射
```

---

## 📞 測試支援

### 測試執行者
- **主要負責人**: QA Team / Developer
- **協助者**: System Administrator (環境準備)

### 遇到問題時
1. 記錄詳細錯誤訊息
2. 保存相關 logs
3. 建立 Bug Report
4. 通知開發團隊

---

## 📚 相關文檔

| 文檔 | 位置 | 說明 |
|------|------|------|
| **需求文檔** | `00_original_requirements.md` | 原始需求 |
| **實施計畫** | `skill_export_import_implementation_plan.md` | 實施計畫 |
| **資料來源指南** | `02_export_data_sources_complete_guide.md` | 資料來源詳細說明 |
| **測試文檔** | `test_docs/test_*.md` | 各測試案例文檔 |
| **Bug 報告** | `test_docs/bugs/bug_*.md` | 測試發現的 Bug |

---

## ✅ 測試檢查清單

### 測試前檢查
- [ ] DocAI 服務正常運行
- [ ] 測試資料已備份
- [ ] 測試目錄已建立
- [ ] 測試工具已準備
- [ ] 測試 Skills 已確認存在

### 測試執行檢查
- [ ] 每個測試都有文檔記錄
- [ ] 測試結果已記錄（Pass/Fail）
- [ ] 失敗的測試已建立 Bug Report
- [ ] 測試資料已保存（ZIP 檔案、logs 等）

### 測試後檢查
- [ ] 測試報告已完成
- [ ] Bug 優先級已標記
- [ ] 改進建議已提出
- [ ] 測試環境已清理

---

**文檔版本**: 1.0
**建立日期**: 2025-12-25
**狀態**: 測試準備就緒
**下一步**: 開始執行 Test-01
