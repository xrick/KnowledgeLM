我們已經確定了核心技術堆疊（BGE-M3 on GPU + SQLite + FAISS），現在我要將這些組件組裝成一個工業級的流水線（Pipeline）。

針對 1000+ 頁 PDF 的處理，單純的「寫程式」是不夠的，我們需要設計一個具備容錯能力的系統。

核心創新設計：流式批次處理管線 (Stream-Batch-Persist Pipeline)
為了達到極致的效率與穩定性，我構思了以下的資料流架構：

1. 生產者 (Producer): 惰性加載 (Lazy Loading)
我們不一次讀入整個 PDF。我們創建一個 Generator，它一次只讀取一頁，解析文字，進行切分，然後 yield 切分好的 Chunks。

優勢: 記憶體佔用極低，無論 PDF 是 1000 頁還是 10000 頁，RAM 消耗幾乎不變。

2. 緩衝區 (Buffer): 動態批次 (Dynamic Batching)
我們設立一個大小為 batch_size (例如 12 或 16) 的緩衝區。

當 Generator 產出的 Chunks 填滿緩衝區時，觸發一次 GPU 推論。

這確保 GPU 永遠是滿載運作（High Utility），而不是處理零碎數據。

3. 消費者 (Consumer): 原子化寫入 (Atomic Persistence)
這是最關鍵的設計。在一次循環中，我們同時做兩件事：

FAISS: index.add(vectors)

SQLite: INSERT INTO chunks ...

Checkpoint: 記錄目前處理到的「頁碼」。

創新點：中斷續傳 (Resumability) 如果程式跑到第 500 頁崩潰了（例如停電），下次啟動時，程式會檢查 SQLite 中的 last_processed_page，直接從第 501 頁開始解析。這對於處理大型文件至關重要。

預計採用的具體策略
ID 同步策略:

為了簡單且高效，我們不依賴 FAISS 的 IndexIDMap (速度稍慢)。

我們使用隱式 ID (Implicit ID)：

FAISS 的第 0 個向量對應 SQLite id=0 的 row。

FAISS 的第 N 個向量對應 SQLite id=N 的 row。

這要求我們嚴格保證寫入順序一致，這在單線程 Pipeline 中很容易達成。

進度條設計:

使用 tqdm 顯示「已處理頁數 / 總頁數」。

因為 Embedding 是以 Chunk 為單位，但使用者理解是以 Page 為單位。我們在後台累積 Chunks，但在前台更新 Page 進度。  

輸出檔案結構:依目前系統的資料儲存架構儲存。

---
根據我們在 INNOVATE 階段確定的「雙引擎架構（FAISS + SQLite）」，我制定了以下的詳細實作計畫。這個計畫將確保在處理 1000+ 頁 PDF 時，既能保持極高的速度（GPU + Batch），又能保證數據的完整性與可檢索性。

架構規格 (Technical Specifications)
PDF 處理器 (PDF Processor)

庫: pymupdf (fitz)

邏輯: 使用 yield 生成器逐頁讀取，避免記憶體爆炸。

切分: 簡單的滑動窗口 (Sliding Window)，因為 BGE-M3 支援長文本，我們設定 Chunk Size 為 512-1024 之間，保留上下文。

Embedding 引擎

庫: FlagEmbedding

模型: BAAI/bge-m3

配置: use_fp16=True (關鍵加速), device='cuda' or 'mps'。(若cuda跟mps都沒有，採cpu,一樣use_fp16=True)

儲存層 (Storage Layer)

向量庫: faiss.IndexFlatIP (內積，搭配正規化向量 = Cosine Similarity)。

資料庫: SQLite3。表結構: (id INTEGER PRIMARY KEY, page_num INTEGER, text TEXT)。

流程控制 (Flow Control)

批次大小 (Batch Size): 預設 12 (根據典型 16GB-24GB VRAM 顯卡優化)。

進度條: tqdm 綁定 PDF 頁數，即時顯示「目前處理到第 X 頁 / 總共 Y 頁」。

實作清單 (Implementation Checklist)
IMPLEMENTATION CHECKLIST:
1. 環境準備: 匯入必要庫 (pymupdf, faiss, sqlite3, FlagEmbedding, tqdm, numpy)。
2. 資料庫初始化: 建立 SQLite 連線與 Table (id, page, text)。
3. 模型載入: 初始化 BGE-M3 模型，開啟 FP16 模式並確認 GPU 狀態。
4. 索引初始化: 建立 FAISS IndexFlatIP (維度 1024)。
5. 定義生成器: 撰寫 PDF 逐頁讀取與文字切分函式。
6. 主循環 (Main Loop):
   a. 遍歷 PDF 頁面。
   b. 累積 Chunks 到緩衝區 (Buffer)。
   c. 當 Buffer >= Batch Size，執行 GPU 編碼。
   d. 進行 L2 Normalize。
   e. 寫入 FAISS 與 SQLite。
   f. 更新進度條。
7. 剩餘處理: 循環結束後，處理緩衝區中剩餘的 Chunks。
8. 檔案保存: 將 FAISS 索引寫入硬碟 (`index.faiss`) 並關閉 SQLite 連線。
9. 驗證: 輸出最終統計數據 (總頁數、總向量數、檔案大小)。

---  
  
Reference Codes (**you can adopt the codes, however you need to think how to integrate to existed codes**)

```python
