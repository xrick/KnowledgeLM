<!-- claudedocs/DEMO_MANUAL.md -->
# DocAI Skill-Based RAG System - Demo 操作手冊

> **版本**: 1.0
> **日期**: 2025-11-26
> **Demo 日期**: 下周一、二
> **作者**: DocAI Team

---

## 📋 目錄

1. [系統概覽](#1-系統概覽)
2. [Demo 前置準備 (前一天)](#2-demo-前置準備-前一天)
3. [Demo 當天啟動流程](#3-demo-當天啟動流程)
4. [Skill 測試注意事項與 Fallback](#4-skill-測試注意事項與-fallback)
5. [現場建立新技能 (Live Demo)](#5-現場建立新技能-live-demo)
6. [常見問題排解](#6-常見問題排解)
7. [緊急聯絡與備援](#7-緊急聯絡與備援)

---

## 1. 系統概覽

### 1.1 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                    DocAI Skill-Based RAG                    │
├─────────────────────────────────────────────────────────────┤
│  Frontend (skill_demo.html)                                 │
│    ├── Skill 選擇器                                          │
│    ├── 查詢介面                                              │
│    └── 結果展示                                              │
├─────────────────────────────────────────────────────────────┤
│  Backend (FastAPI)                                          │
│    ├── /api/v1/skills/demo        - 列出所有技能              │
│    ├── /api/v1/skills/demo/query  - 技能查詢                  │
│    └── /skill-demo                - Demo 頁面                │
├─────────────────────────────────────────────────────────────┤
│  Core Components                                            │
│    ├── BGE-M3 Embedding (1024 維度)                          │
│    ├── FAISS Vector Store                                   │
│    └── SQLite Metadata DB                                   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 可用技能

| 技能名稱 | 類別 | Chunks | 用途 | 推薦查詢 |
|---------|------|--------|------|---------|
| 六法全書-刑法 | Legal-Criminal | 272 | 刑事法律查詢 | 詐欺、竊盜、傷害罪 |
| 六法全書-民法 | Legal-Civil | 533 | 民事法律查詢 | 契約、債權、繼承 |
| LLM | AI-LLM | 1268 | AI 技術查詢 | attention, fine-tune, RAG |

---

## 2. Demo 前置準備 (前一天)

### 2.1 系統檢查清單

```bash
# ✅ 進入專案目錄
cd /home/mapleleaf/LCJRepos/gitprjs/DocAI

# ✅ 檢查 Git 狀態
git status
git branch  # 應該在 beta_skill_v0.1

# ✅ 檢查資料庫
sqlite3 data/skill_metadata.db "SELECT skill_name, json_extract(metadata, '$.total_chunks') FROM skill_metadata;"

# ✅ 檢查 FAISS 索引
ls -la data/faiss_indices/skills/

# ✅ 檢查虛擬環境
ls -la docaienv/bin/python
```

### 2.2 測試系統啟動

```bash
# 啟動系統
./start_system.sh

# 等待 10 秒後檢查
curl http://localhost:8000/health

# 檢查 Skill API
curl http://localhost:8000/api/v1/skills/demo | jq

# 停止系統
./stop_system.sh
```

### 2.3 預先測試所有 Skills

```bash
# 執行完整測試
docaienv/bin/python scripts/test_all_skills_demo.py
```

### 2.4 準備備份

```bash
# 備份資料庫
cp data/skill_metadata.db data/skill_metadata.db.backup

# 備份 FAISS 索引
tar -czvf faiss_backup.tar.gz data/faiss_indices/skills/
```

---

## 3. Demo 當天啟動流程

### 3.1 開機步驟 (約 5 分鐘)

#### Step 1: 開啟終端機
```bash
# 開啟終端機，進入專案目錄
cd /home/mapleleaf/LCJRepos/gitprjs/DocAI
```

#### Step 2: 檢查系統狀態
```bash
# 確認沒有殘留進程
lsof -i :8000  # 應該沒有輸出

# 確認 GPU 狀態 (若使用 GPU)
nvidia-smi  # 可選
```

#### Step 3: 啟動系統
```bash
# 一鍵啟動
./start_system.sh
```

**預期輸出:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  前置條件檢查
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Python 3.11.x 已安裝
✅ uv 套件管理工具已安裝
✅ 虛擬環境存在
...
✅ FastAPI 服務器已啟動
✅ 服務可用: http://localhost:8000
```

#### Step 4: 驗證系統
```bash
# 健康檢查
curl http://localhost:8000/health

# Skill 系統檢查
curl http://localhost:8000/api/v1/skills/demo/health
```

**預期輸出:**
```json
{
  "status": "healthy",
  "database": "ok",
  "embedding_model": "BGE-M3 (1024d)",
  "faiss_indices": 3
}
```

#### Step 5: 開啟瀏覽器
```bash
# 開啟 Demo 頁面
xdg-open http://localhost:8000/skill-demo
```

### 3.2 快速啟動指令 (緊急情況)

如果需要快速重啟：

```bash
# 一行指令：停止 → 啟動 → 開啟瀏覽器
./stop_system.sh && sleep 2 && ./start_system.sh && xdg-open http://localhost:8000/skill-demo
```

---

## 4. Skill 測試注意事項與 Fallback

### 4.1 六法全書-刑法 ⚖️

#### 推薦查詢
| 查詢 | 預期結果 |
|-----|---------|
| 詐欺罪的構成要件 | 刑法第339條相關內容 |
| 竊盜罪 | 刑法第320條 |
| 傷害罪的刑責 | 刑法第277條 |

#### 測試步驟
1. 在 Demo 頁面選擇「六法全書-刑法」
2. 輸入：`詐欺罪`
3. 確認結果顯示刑法條文

#### ⚠️ 可能問題與 Fallback

**問題 1: 查詢無結果**
- **原因**: FAISS 索引未載入
- **Fallback**:
  ```bash
  # 重新載入索引
  docaienv/bin/python -c "
  import faiss
  idx = faiss.read_index('data/faiss_indices/skills/skill_legal-criminal_20251126_031501_4fdb3e9b/index.faiss')
  print(f'Index loaded: {idx.ntotal} vectors')
  "
  ```
- **備用說法**: 「讓我們切換到另一個技能來展示」

**問題 2: 結果不相關**
- **原因**: 查詢詞太模糊
- **Fallback**: 使用備用查詢「傷害罪的刑事責任」
- **備用說法**: 「讓我用更精確的法律術語」

### 4.2 六法全書-民法 📜

#### 推薦查詢
| 查詢 | 預期結果 |
|-----|---------|
| 契約的成立要件 | 民法債編相關內容 |
| 繼承權 | 民法繼承編 |
| 物權移轉 | 民法物權編 |

#### 測試步驟
1. 選擇「六法全書-民法」
2. 輸入：`契約成立`
3. 確認結果包含民法條文

#### ⚠️ 可能問題與 Fallback

**問題 1: 回應緩慢**
- **原因**: 533 chunks 較多，搜尋時間較長
- **Fallback**: 減少 top_k 值
- **備用說法**: 「民法內容較豐富，搜尋中...」

### 4.3 LLM 技術文件 🤖

#### 推薦查詢
| 查詢 | 預期結果 |
|-----|---------|
| What is attention mechanism | Transformer self-attention 解釋 |
| How to fine-tune LLM | Fine-tuning 步驟與技巧 |
| RAG architecture | RAG 系統架構說明 |

#### 測試步驟
1. 選擇「LLM」
2. 輸入：`attention mechanism`
3. 確認結果來自 Manning/Packt 書籍

#### ⚠️ 可能問題與 Fallback

**問題 1: 英文查詢無結果**
- **原因**: BGE-M3 支援多語言，但英文效果最佳
- **Fallback**: 切換中文查詢「注意力機制」

**問題 2: 結果分散**
- **原因**: 1268 chunks 分布於 3 本書
- **備用說法**: 「結果來自多本專業書籍，顯示系統的跨文件搜尋能力」

### 4.4 通用 Fallback 策略

#### 情況 1: API 無回應
```bash
# 快速診斷
curl http://localhost:8000/health

# 重啟服務
./stop_system.sh && ./start_system.sh
```

#### 情況 2: 所有 Skill 都無法使用
1. **備用演示**: 使用預先準備的螢幕截圖
2. **說法**: 「讓我展示系統的架構設計...」
3. **切換話題**: 展示程式碼架構

#### 情況 3: 頁面無法載入
1. 檢查端口: `lsof -i :8000`
2. 直接訪問 API: `curl http://localhost:8000/api/v1/skills/demo`
3. 使用 Postman 演示 API

---

## 5. 現場建立新技能 (Live Demo)

### 5.1 情境說明

> 「各位長官好，接下來我要展示如何在系統中建立一個全新的技能。
> 這個功能可以讓使用者快速將新的文件集合轉換為可查詢的知識庫。」

### 5.2 準備工作 (Demo 前)

確保以下文件存在：
```bash
# 檢查示範文件
ls -la refData/rawdata/demo/
# 應該有 1-2 個小型 PDF 文件 (< 5 頁)
```

**如果沒有示範文件，建立測試文件：**
```bash
mkdir -p refData/rawdata/demo
# 複製一個小型 PDF 作為示範
cp refData/rawdata/LLM/Decoding_Large_Language_Models_packt_2024.pdf refData/rawdata/demo/sample.pdf
```

### 5.3 現場建立步驟

#### Step 1: 展示空白狀態
```bash
# 顯示目前的技能列表
curl http://localhost:8000/api/v1/skills/demo | jq '.[].name'
```

**說法**: 「目前系統中有 3 個技能」

#### Step 2: 執行建立腳本
```bash
# 執行快速建立腳本 (約 30-60 秒)
docaienv/bin/python scripts/create_demo_skill_live.py
```

**預期輸出**:
```
======================================================================
🎯 Live Demo: Creating New Skill
======================================================================
📁 Source: refData/rawdata/demo/
🔧 Embedding: BAAI/bge-m3 (1024d)
======================================================================

🚀 Step 1: Extracting PDF content...
   ✅ Extracted 5 pages

🚀 Step 2: Generating embeddings...
   ✅ Generated 5 embeddings (dim=1024)

🚀 Step 3: Creating FAISS index...
   ✅ FAISS index created

🚀 Step 4: Saving to database...
   ✅ Skill metadata saved

======================================================================
✅ SUCCESS - New Skill Created!
======================================================================
   Skill ID: skill_demo_live_20251126_xxxxxx
   Skill Name: Live Demo
   Chunks: 5
   Time: 45 seconds
======================================================================
```

#### Step 3: 驗證新技能
```bash
# 重新查詢技能列表
curl http://localhost:8000/api/v1/skills/demo | jq '.[].name'
```

**說法**: 「您可以看到新的技能已經出現在列表中」

#### Step 4: 測試查詢
1. 重新整理 Demo 頁面
2. 選擇新建立的技能
3. 進行查詢

### 5.4 快速建立腳本

```bash
# scripts/create_demo_skill_live.py 的內容已預先準備
# 執行時間約 30-60 秒
```

### 5.5 ⚠️ Live Demo Fallback

**問題 1: 建立失敗**
- **Fallback**: 展示預先錄製的影片
- **說法**: 「由於時間關係，讓我展示預錄的演示」

**問題 2: 建立太慢 (> 2 分鐘)**
- **Fallback**:
  ```bash
  # 使用預先準備的技能
  cp -r data/faiss_indices/skills/skill_demo_backup data/faiss_indices/skills/skill_demo_live
  ```
- **說法**: 「為節省時間，讓我直接展示結果」

**問題 3: BGE-M3 模型載入失敗**
- **Fallback**: 已有其他 3 個正常技能可演示
- **說法**: 「讓我們先看看現有的技能...」

---

## 6. 常見問題排解

### 6.1 系統無法啟動

| 錯誤訊息 | 原因 | 解決方案 |
|---------|------|---------|
| `Address already in use` | Port 8000 被佔用 | `lsof -i :8000 && kill -9 <PID>` |
| `No module named 'xxx'` | 依賴缺失 | `docaienv/bin/pip install xxx` |
| `Permission denied` | 權限問題 | `chmod +x start_system.sh` |

### 6.2 查詢無回應

```bash
# 診斷步驟
# 1. 檢查服務狀態
curl http://localhost:8000/health

# 2. 檢查日誌
tail -50 logs/server.log

# 3. 檢查 FAISS 索引
ls -la data/faiss_indices/skills/
```

### 6.3 結果顯示異常

```bash
# 重新載入頁面
# 按 Ctrl+Shift+R 強制重新整理

# 檢查 API 回應
curl -X POST http://localhost:8000/api/v1/skills/demo/query \
  -H "Content-Type: application/json" \
  -d '{"skill_id":"skill_legal-criminal_20251126_031501_4fdb3e9b","query":"詐欺","top_k":5}'
```

---

## 7. 緊急聯絡與備援

### 7.1 緊急處理步驟

1. **保持冷靜** - 技術問題很常見
2. **切換話題** - 展示架構設計或程式碼
3. **使用備份** - 預先準備的螢幕截圖/影片
4. **說明情況** - 「讓我稍後展示這部分」

### 7.2 備用展示材料

準備以下材料在 `claudedocs/demo_backup/` 目錄：
- [ ] 系統架構圖
- [ ] 查詢成功的螢幕截圖
- [ ] 技能建立過程的影片
- [ ] API 文件

### 7.3 Demo 結束檢查

```bash
# Demo 結束後
./stop_system.sh

# 恢復備份 (如有需要)
cp data/skill_metadata.db.backup data/skill_metadata.db
```

---

## 📝 Demo 當天檢查表

### 開始前 (30 分鐘)
- [ ] 電腦已充電/接電源
- [ ] 網路連線正常
- [ ] 終端機已開啟
- [ ] 瀏覽器已開啟

### 系統啟動
- [ ] 進入專案目錄
- [ ] 執行 `./start_system.sh`
- [ ] 確認 health check 通過
- [ ] 開啟 Demo 頁面

### 技能測試
- [ ] 六法全書-刑法 查詢成功
- [ ] 六法全書-民法 查詢成功
- [ ] LLM 查詢成功

### Live Demo 準備
- [ ] 示範文件已就位
- [ ] 建立腳本已測試
- [ ] Fallback 方案已準備

### 結束後
- [ ] 停止系統
- [ ] 儲存任何修改
- [ ] 記錄問題

---

**祝 Demo 成功！** 🎉

> 記住：技術問題不可怕，重要的是展示我們的專業態度和解決問題的能力。
