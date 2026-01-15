<!-- refData/docs/large_files_processing/Embed1000+ Solution.md -->
Innovate:

基於研究階段的分析，我為您構思了一個專門針對「大規模 PDF」+「BGE-M3」+「高效能」的解決方案。

這裡有幾個創新的優化點，旨在突破常規寫法的效能瓶頸：

核心架構思路 (Architecture Design)
I/O 瓶頸突破：使用 PyMuPDF (fitz) + 生成器 (Generator)

傳統做法：一次性讀取整個 PDF 到記憶體，然後切分。對於 1000 頁雖然可行，但若遇到 10000 頁就會爆記憶體。

創新做法：採用 Lazy Loading。雖然 Embedding 階段需要 Batch，但我們可以先將文本提取做成流式處理，大幅降低初始記憶體峰值。

計算瓶頸突破：BGE-M3 專屬優化 (FP16 + Batching)

BGE-M3 是一個龐大的模型。單條處理是效能殺手。

我們將實作一個 Dynamic Batching 機制。

關鍵優化：如果device是cuda or mps則啟用 use_fp16=True，在不損失檢索精度的情況下，這能讓 Embedding 速度提升約 2-3 倍，並減少 VRAM 佔用。否則就使用CPU，use_fp16=False. 

儲存架構：分離式設計 (FAISS + Metadata Store)

FAISS 原生只存向量 (Vectors) 和 ID。如果不存對應的文字 (Text)，這些向量就沒有意義。

方案：

vector.index: 純 FAISS 索引檔。

向量引擎 (FAISS): 專注於數學計算。

儲存: id -> vector (1024維 Dense Vector)

檔案: index.faiss

資料引擎 (SQLite): 專注於內容儲存。

儲存: id -> text, metadata

關鍵邏輯: SQLite 中的 Primary Key (id) 必須與 FAISS 中的索引順序（0, 1, 2...）嚴格對應。

可視化體驗：tqdm 雙層進度條

外層顯示總體進度。

內層（選用）顯示當前 Batch 的處理速度 (it/s)。

擬定使用的技術堆疊
PDF 解析: pymupdf (極速)

模型推論: FlagEmbedding (官方庫，支援 BGE-M3 完整特性)

向量庫: faiss-gpu (若無 GPU 則自動降級 faiss-cpu)

流程控制: tqdm

擬定程式邏輯流程
初始化: 檢查 CUDA，載入 BGE-M3 模型 (半精度模式)。

預處理:

快速掃描 PDF，提取文本。

進行 Sliding Window 切分 (Chunking)，例如每塊 1024 tokens (BGE-M3 支援長文本，我們可以切大一點減少碎片)。

向量化 (The Loop):

將 Chunks 打包成 Batches (例如 batch_size=12)。

送入 GPU 進行 Encoding。

獲取 dense_vecs (BGE-M3 輸出包含多種向量，我們只取 Dense 用於 FAISS)。

L2 Normalize (為了 Cosine Similarity)。

寫入:

向量 add 到 FAISS Index。

文本寫入 sqlite。

更新進度條。

保存: 輸出最終檔案。
---
plan:
根據我們在 INNOVATE 階段確定的「雙引擎架構（FAISS + SQLite）」，我制定了以下的詳細實作計畫。這個計畫將確保在處理 1000+ 頁 PDF 時，既能保持極高的速度（GPU + Batch），又能保證數據的完整性與可檢索性。

架構規格 (Technical Specifications)
PDF 處理器 (PDF Processor)

庫: pymupdf (fitz)

邏輯: 使用 yield 生成器逐頁讀取，避免記憶體爆炸。

切分: 簡單的滑動窗口 (Sliding Window)，因為 BGE-M3 支援長文本，我們設定 Chunk Size 為 512-1024 之間，保留上下文。

Embedding 引擎

庫: FlagEmbedding

模型: BAAI/bge-m3

配置: use_fp16=True (關鍵加速), device='cuda'。

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
reference codes:

```python
"""
Project: BGE-M3 PDF Embedder
Description: High-performance pipeline to embed large PDFs (1000+ pages) into FAISS + SQLite.
Key Features:
- Stream Processing (Lazy Loading) to minimize RAM usage.
- GPU Batch Processing with FP16 for speed.
- Dual Storage: FAISS for vectors, SQLite for text/metadata.
- Real-time Progress Tracking (Pages & Batches).
"""

import os
import sys
import time
import sqlite3
import numpy as np
import fitz  # PyMuPDF
import faiss
from tqdm import tqdm
from FlagEmbedding import BGEM3FlagModel

# Configuration
CONFIG = {
    "pdf_path": "your_large_file.pdf",      # Target PDF file
    "model_name": "BAAI/bge-m3",            # Model name
    "batch_size": 12,                       # GPU Batch size (Increase if VRAM > 16GB)
    "chunk_size": 1000,                     # Characters per chunk
    "overlap": 100,                         # Overlap characters
    "output_dir": "output_knowledge_base",  # Output directory
    "use_fp16": True                        # Enable FP16 for 2x speed
}

class PDFEmbedder:
    def __init__(self, config):
        self.config = config
        self.ensure_directories()
        
        # 1. Initialize Database (SQLite)
        self.db_path = os.path.join(config["output_dir"], "knowledge.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.setup_db()
        
        # 2. Initialize Model (BGE-M3)
        print(f"Loading Model: {config['model_name']} (FP16={config['use_fp16']})...")
        self.model = BGEM3FlagModel(
            config['model_name'], 
            use_fp16=config['use_fp16']
        )
        print("Model loaded successfully.")

        # 3. Initialize FAISS Index
        self.vector_dim = 1024  # BGE-M3 dense dimension
        self.index = faiss.IndexFlatIP(self.vector_dim) # Inner Product for Normalized Vectors
        
        # Buffer for batch processing
        self.text_buffer = []
        self.meta_buffer = []

    def ensure_directories(self):
        if not os.path.exists(self.config["output_dir"]):
            os.makedirs(self.config["output_dir"])

    def setup_db(self):
        # Create table to store text content mapping
        # ID in SQLite corresponds to ID in FAISS (row number)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                page_number INTEGER,
                text_content TEXT,
                source_file TEXT
            )
        ''')
        # Clear existing data for a fresh run
        self.cursor.execute('DELETE FROM chunks')
        self.conn.commit()

    def split_text(self, text):
        """Simple sliding window splitter"""
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + self.config["chunk_size"]
            chunk = text[start:end]
            chunks.append(chunk)
            start += (self.config["chunk_size"] - self.config["overlap"])
            
        return chunks

    def flush_batch(self):
        """Encode buffered texts and save to storage"""
        if not self.text_buffer:
            return

        # A. GPU Encoding
        # BGE-M3 returns a dictionary, we need 'dense_vecs'
        embeddings = self.model.encode(
            self.text_buffer, 
            batch_size=len(self.text_buffer), 
            max_length=8192 # BGE-M3 supports up to 8192
        )['dense_vecs']

        # B. Normalize for Cosine Similarity (IndexFlatIP)
        faiss.normalize_L2(embeddings)

        # C. Write to FAISS
        self.index.add(embeddings)

        # D. Write to SQLite
        # Calculate starting ID for this batch
        current_id = self.cursor.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
        
        data_rows = []
        for i, (text, meta) in enumerate(zip(self.text_buffer, self.meta_buffer)):
            # id, page_number, text_content, source_file
            data_rows.append((
                current_id + i,
                meta['page'],
                text,
                self.config['pdf_path']
            ))
        
        self.cursor.executemany(
            'INSERT INTO chunks VALUES (?, ?, ?, ?)', 
            data_rows
        )
        self.conn.commit()

        # Clear buffers
        self.text_buffer = []
        self.meta_buffer = []

    def run(self):
        pdf_path = self.config["pdf_path"]
        if not os.path.exists(pdf_path):
            print(f"Error: File {pdf_path} not found.")
            return

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        print(f"Target: {pdf_path} | Total Pages: {total_pages}")
        print("Starting pipeline...")

        # Progress bar based on Pages
        with tqdm(total=total_pages, desc="Processing PDF", unit="page") as pbar:
            for page_num, page in enumerate(doc):
                # 1. Extract Text
                text = page.get_text()
                
                if not text.strip():
                    pbar.update(1)
                    continue

                # 2. Split Text
                chunks = self.split_text(text)

                # 3. Add to Buffer
                for chunk in chunks:
                    self.text_buffer.append(chunk)
                    self.meta_buffer.append({"page": page_num + 1})

                    # 4. Trigger Batch Processing if buffer is full
                    if len(self.text_buffer) >= self.config["batch_size"]:
                        self.flush_batch()
                
                # Update progress bar
                pbar.update(1)
                
                # Optional: Show current status in description
                pbar.set_postfix({"Vectors": self.index.ntotal})

        # Process remaining items in buffer
        self.flush_batch()
        
        self.save_artifacts()
        print("\n--- Processing Complete ---")
        print(f"Total Vectors: {self.index.ntotal}")
        print(f"Saved to: {self.config['output_dir']}")

    def save_artifacts(self):
        # Save FAISS index
        index_path = os.path.join(self.config["output_dir"], "vector.index")
        faiss.write_index(self.index, index_path)
        
        # Close DB
        self.conn.close()
