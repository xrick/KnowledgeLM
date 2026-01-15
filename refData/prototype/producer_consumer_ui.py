"""
Project: BGE-M3 PDF Embedder (Threaded Version)
Description: High-performance pipeline with Producer-Consumer architecture.
- Producer Thread: Reads PDF & splits text (CPU/IO Bound).
- Consumer (Main) Thread: Embeds with BGE-M3 & saves to DB (GPU Bound).
"""

import os
import sys
import time
import sqlite3
import threading
import queue
import fitz  # PyMuPDF
import faiss
from tqdm import tqdm
from FlagEmbedding import BGEM3FlagModel

# Configuration
CONFIG = {
    "pdf_path": "your_large_file.pdf",      
    "model_name": "BAAI/bge-m3",            
    "batch_size": 12,                       
    "chunk_size": 1000,                     
    "overlap": 100,                         
    "output_dir": "output_knowledge_base",  
    "use_fp16": True,
    "queue_size": 10  # How many batches to buffer in RAM
}

class PDFEmbedder:
    def __init__(self, config):
        self.config = config
        self.ensure_directories()
        
        # 1. Initialize Database
        self.db_path = os.path.join(config["output_dir"], "knowledge.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.setup_db()
        
        # 2. Initialize Model
        print(f"Loading Model: {config['model_name']} (FP16={config['use_fp16']})...")
        self.model = BGEM3FlagModel(
            config['model_name'], 
            use_fp16=config['use_fp16']
        )
        print("Model loaded.")

        # 3. Initialize FAISS
        self.vector_dim = 1024
        self.index = faiss.IndexFlatIP(self.vector_dim)
        
        # 4. Threading Queue
        # Items in queue will be tuples: (batch_texts, batch_metas)
        self.batch_queue = queue.Queue(maxsize=config['queue_size'])
        self.total_pages = 0

    def ensure_directories(self):
        if not os.path.exists(self.config["output_dir"]):
            os.makedirs(self.config["output_dir"])

    def setup_db(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                page_number INTEGER,
                text_content TEXT,
                source_file TEXT
            )
        ''')
        self.cursor.execute('DELETE FROM chunks')
        self.conn.commit()

    def split_text(self, text):
        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = start + self.config["chunk_size"]
            chunk = text[start:end]
            chunks.append(chunk)
            start += (self.config["chunk_size"] - self.config["overlap"])
        return chunks

    def _producer_loop(self):
        """
        Runs in a separate thread.
        Reads PDF -> Chunks -> Aggregates to Batch -> Puts to Queue
        """
        pdf_path = self.config["pdf_path"]
        doc = fitz.open(pdf_path)
        self.total_pages = len(doc)
        
        text_buffer = []
        meta_buffer = []
        
        # We iterate pages, but we push BATCHES of chunks
        for page_num, page in enumerate(doc):
            text = page.get_text()
            if not text.strip():
                continue
                
            chunks = self.split_text(text)
            
            for chunk in chunks:
                text_buffer.append(chunk)
                meta_buffer.append({"page": page_num + 1})
                
                if len(text_buffer) >= self.config["batch_size"]:
                    # Put a copy of the buffer into queue
                    # This blocks if queue is full (backpressure)
                    self.batch_queue.put((list(text_buffer), list(meta_buffer)))
                    text_buffer.clear()
                    meta_buffer.clear()
        
        # Push remaining items
        if text_buffer:
            self.batch_queue.put((list(text_buffer), list(meta_buffer)))
            
        # Sentinel value to indicate "Done"
        self.batch_queue.put(None)
        doc.close()

    def _process_batch(self, batch_texts, batch_metas):
        """Perform GPU inference and DB write"""
        # A. Encode
        embeddings = self.model.encode(
            batch_texts, 
            batch_size=len(batch_texts), 
            max_length=8192
        )['dense_vecs']

        # B. Normalize
        faiss.normalize_L2(embeddings)

        # C. Add to Index
        self.index.add(embeddings)

        # D. Add to DB
        current_id = self.cursor.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
        data_rows = []
        for i, (text, meta) in enumerate(zip(batch_texts, batch_metas)):
            data_rows.append((
                current_id + i,
                meta['page'],
                text,
                self.config['pdf_path']
            ))
        
        self.cursor.executemany('INSERT INTO chunks VALUES (?, ?, ?, ?)', data_rows)
        self.conn.commit()

    def run(self):
        if not os.path.exists(self.config["pdf_path"]):
            print("PDF not found.")
            return

        # 1. Start Producer Thread
        producer_thread = threading.Thread(target=self._producer_loop, daemon=True)
        producer_thread.start()
        
        # Wait briefly for producer to open file and set total_pages
        time.sleep(0.5) 
        
        print(f"Processing: {self.config['pdf_path']} ({self.total_pages} pages)")
        print("Pipeline Started. Progress indicates 'Vectors Embedded'.")

        # 2. Main Consumer Loop (Progress bar tracks VECTORS, not pages, for accuracy)
        # Using a manual pbar update because we don't know total vectors yet
        with tqdm(desc="Embedding Vectors", unit="vec") as pbar:
            while True:
                # Get batch from queue
                item = self.batch_queue.get()
                
                # Check for sentinel (End of Stream)
                if item is None:
                    break
                
                batch_texts, batch_metas = item
                
                # Process
                self._process_batch(batch_texts, batch_metas)
                
                # Update progress
                pbar.update(len(batch_texts))
                
                # Show current page in status
                current_page = batch_metas[-1]['page']
                pbar.set_postfix({"Page": f"{current_page}/{self.total_pages}"})

        # 3. Cleanup
        self.save_artifacts()
        print("\n--- Done ---")
        print(f"Total Vectors: {self.index.ntotal}")

    def save_artifacts(self):
        index_path = os.path.join(self.config["output_dir"], "vector.index")
        faiss.write_index(self.index, index_path)
        self.conn.close()

if __name__ == "__main__":
    target_pdf = sys.argv[1] if len(sys.argv) > 1 else "demo.pdf"
    
    if not os.path.exists(target_pdf) and target_pdf == "demo.pdf":
        print("Creating dummy demo.pdf...")
        doc = fitz.open()
        for i in range(50): # 50 pages dummy
            doc.new_page(pno=-1, text=f"This is page {i+1} content for testing embedding.")
        doc.save("demo.pdf")
        doc.close()

    CONFIG["pdf_path"] = target_pdf
    embedder = PDFEmbedder(CONFIG)
    embedder.run()