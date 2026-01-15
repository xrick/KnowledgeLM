<!-- QUICKSTART.md -->
# DocAI RAG Application - Quick Start Guide

## 系統現況 ✅

已就緒：
- ✅ Code implementation 完成
- ✅ Ollama 正在運行 (9 models 可用)
- ✅ Redis 正在運行
- ✅ `.env` 已配置

需要處理：
- ❌ Python dependencies (PyPDF2, pymongo 等)
- ❌ MongoDB 服務未啟動

---

## Step-by-Step 啟動指南

### Step 1: 安裝 Python Dependencies (1-2 分鐘)

```bash
# 方式 A: 只安裝缺失的核心套件 (快速)
pip install PyPDF2 pymongo

# 方式 B: 完整安裝 (推薦，5-10 分鐘)
pip install -r requirements.txt
```

**預期輸出**：
```
Successfully installed PyPDF2-3.0.1 pymongo-4.6.1 ...
```

---

### Step 2: 啟動 MongoDB (30 秒)

```bash
# 方式 A: Docker (推薦)
docker run -d -p 27017:27017 --name mongodb mongo:latest

# 方式 B: 系統服務
sudo systemctl start mongodb

# 驗證
nc -zv localhost 27017
# 預期輸出: Connection to localhost 27017 port [tcp/*] succeeded!
```

---

### Step 3: 啟動 DocAI Application

```bash
# 從專案根目錄執行
python main.py
```

**預期輸出**：
```
INFO:     🚀 Starting DocAI v1.0.0
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

### Step 4: 測試系統 (1 分鐘)

#### 4.1 健康檢查
```bash
curl http://localhost:8000/health
```
預期回應: `{"status":"ok"}`

#### 4.2 打開前端
瀏覽器訪問: http://localhost:8000

預期看到: DocAI 上傳介面

#### 4.3 測試 PDF 上傳
```bash
# 準備測試 PDF (或使用你自己的 PDF)
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@test.pdf"
```

預期回應:
```json
{
  "file_id": "file_abc123...",
  "filename": "test.pdf",
  "status": "success"
}
```

#### 4.4 測試 Chat (SSE Streaming)
```bash
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "query": "這份文件在講什麼？",
    "file_ids": ["file_abc123..."],
    "session_id": "test_session"
  }'
```

預期輸出: Server-Sent Events stream with markdown tokens

---

## Troubleshooting 快速參考

### 問題 1: ImportError: No module named 'PyPDF2'
**解決**: `pip install PyPDF2`

### 問題 2: MongoDB connection failed
**檢查**: `nc -zv localhost 27017`
**解決**: `docker run -d -p 27017:27017 mongo:latest`

### 問題 3: Ollama model not found
**檢查可用 models**: `curl http://localhost:11434/api/tags`
**修改 .env**: `LLM_MODEL_NAME=deepseek-r1:7b` (你有這個 model)

### 問題 4: Port 8000 already in use
**解決**: 修改 `.env` 中的 `PORT=8001`

---

## 系統架構速覽

```
用戶上傳 PDF
    ↓
[upload.py] → InputDataHandleService
    ↓         (extract → chunk → hierarchical indexing)
    ↓
VectorStore (FAISS/Milvus)
    ↓
用戶提問
    ↓
[chat.py] → 5-Phase RAG Pipeline
    ├─ Phase 1: Query Understanding (Question Expansion)
    ├─ Phase 2: Parallel Retrieval (Multi-query)
    ├─ Phase 3: Context Assembly
    ├─ Phase 4: Response Generation (OPMP streaming)
    └─ Phase 5: Post Processing (save history)
    ↓
SSE Stream → Frontend OPMP Client → Progressive Markdown Rendering
```

---

## 可用的 Ollama Models (已安裝)

從檢查結果，你有以下 models 可用：

1. **zephyr:7b** ← .env 預設使用
2. **deepseek-r1:7b** (推薦，7.6B 參數)
3. **deepseek-r1:latest** (8.2B)
4. **phi4-mini-reasoning:3.8b** (推理增強)
5. **codellama:7b** (程式碼專用)
6. **deepseek-coder-v2:16b** (大型程式碼模型)
7. **gpt-oss:20b** (20B 大模型)

修改 `.env` 的 `LLM_MODEL_NAME` 即可切換。

---

## 新功能：智能摘要生成 (2025-11-22 更新)

系統現已支持自動偵測摘要請求並生成結構化摘要：

**支持關鍵字**：
- 中文：摘要、總結、概述、概括、簡述、歸納
- 英文：summary, summarize, overview

**摘要特點**：
- 每份文件 150-200 字精簡概括
- 結構化呈現：主題 → 方法 → 結論
- 多文件獨立摘要並清楚標示
- 自動套用專業術語和格式
- **公平檢索策略**：多文件摘要時自動啟用公平分配，確保每份文件都被檢索和摘要

**測試範例**：
```bash
上傳 2 份 PDF 後，輸入：
"請個別產生這二份文件的摘要"

預期輸出：
**文件 1: [主題]**
本文研究...主要方法包括...研究發現...

**文件 2: [主題]**
本文探討...核心貢獻...實驗結果...
```

---

## 下一步

系統啟動後：

1. 上傳測試 PDF 文件
2. 測試 chat streaming (觀察 5 phase progress indicators)
3. **測試智能摘要功能**：上傳多份 PDF 並輸入「摘要」查詢
4. 檢查 MongoDB chat history 是否正確儲存
5. 觀察 OPMP progressive rendering 效果

詳細文檔：
- 完整估算報告: `claudedocs/estimation_report_20251029.md`
- 架構說明: `claudedocs/core_logic_service_to_endpoint_chat.md`
- Implementation summary: `claudedocs/implementation_summary_20251029.md`

---

**Last Updated**: 2025-10-29
**Status**: ✅ Ready to run (after Step 1-2)
