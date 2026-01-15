# utils/detect_file_type.py
import fitz  # PyMuPDF

def detect_document_type(pdf_path):
    """
    判斷 PDF 是一般文檔還是 PPT 簡報。
    回傳值: 'PPT' 或 'General_Document'
    """
    try:
        doc = fitz.open(pdf_path)
        
        # --- 判斷指標 1: Metadata 檢查 (最快) ---
        metadata = doc.metadata
        creator = metadata.get('creator', '').lower()
        producer = metadata.get('producer', '').lower()
        
        # 如果製作軟體明確寫著 PowerPoint，直接判定
        if 'powerpoint' in creator or 'powerpoint' in producer:
            print(f"[檢測結果] 依據 Metadata 判定為 PPT (來源: {creator})")
            return 'PPT'

        # --- 判斷指標 2: 頁面方向 (最穩) ---
        # 檢查前 3 頁就好 (避免有些文件封面是直的，內容是橫的)
        check_pages = min(3, len(doc))
        landscape_count = 0
        
        for i in range(check_pages):
            page = doc.load_page(i)
            rect = page.rect  # 取得頁面尺寸
            if rect.width > rect.height:
                landscape_count += 1
        
        # 如果大部分檢查的頁面都是橫向，極大機率是 PPT
        if landscape_count > (check_pages / 2):
            print("[檢測結果] 依據頁面長寬比判定為 PPT (橫向)")
            return 'PPT'
            
        # --- 判斷指標 3: (選用) 字數密度 ---
        # 如果前面兩關都沒過，通常就是直向的一般文檔
        # 但如果你想更謹慎，可以加一段檢查字數是否極少...
        
        print("[檢測結果] 判定為 一般文檔 (直向/非PPT來源)")
        return 'General_Document'

    except Exception as e:
        print(f"讀取 PDF 發生錯誤: {e}")
        return 'General_Document' # 遇到錯誤保守處理，視為一般文檔