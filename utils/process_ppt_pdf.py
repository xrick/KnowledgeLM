# utils/process_ppt_pdf.py

import os
from langchain_community.document_loaders import PyMuPDFLoader
def create_page_based_embedding(pdf_path):
    """
    讀取 PDF 並建立以頁為單位的 Embedding
    """
    # 1. 載入 PDF
    # PyMuPDFLoader 會自動將每一頁視為一個 Document
    loader = PyMuPDFLoader(pdf_path)
    pages = loader.load()

    print(f"共讀取到 {len(pages)} 頁簡報。")

    # 檢視一下第一頁的 Metadata，確認有頁碼資訊
    # output 範例: {'source': 'sample.pdf', 'file_path': 'sample.pdf', 'page': 0, ...}
    print(f"第一頁 Metadata 範例: {pages[0].metadata}")

    # 2. 資料清理 (可選)
    # PPT 轉出的 PDF 有時會有頁碼或重複的頁首頁尾，可以在這裡簡單處理
    for page in pages:
        # 簡單去除頭尾空白
        page.page_content = page.page_content.strip()
        
        # 技巧：將 PPT 的檔名或標題加進內容中，增加搜尋的上下文關聯
        # page.page_content = f"簡報來源: {page.metadata['source']}\n內容: {page.page_content}"

    # 3. 建立 Embedding 與 Vector Store