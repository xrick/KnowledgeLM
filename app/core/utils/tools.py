# app/core/utils/tools.py
import uuid
import time
import zlib

def genUniqueID():
        """
        根據一個三步驟演算法生成一個 32-bit 的類唯一 ID：
        1. 產生一個隨機 UUID。
        2. 結合 UUID 和一個高精度的奈秒 (nanosecond) 時間戳記。
        3. 將組合後的字串透過 CRC32 雜湊演算法轉換為一個 32-bit 整數。
        """
        
        # 步驟 1: 隨機演算法()運算邏輯 -> uuid
        # 我們使用 UUID v4，這是一個基於高品質隨機數生成的 128-bit 值。
        random_uuid = uuid.uuid4()
        
        # 步驟 2: uuid + timestamp = tmp_uuid
        # 我們使用 time.time_ns() 來獲取奈秒級的時間戳記，以最大化唯一性。
        # 結合 UUID 和時間戳記，建立一個高熵 (high-entropy) 的輸入字串。
        current_timestamp_ns = time.time_ns()
        
        # f-string 提供了最高效能的字串組合方式
        tmp_uuid_str = f"{random_uuid}-{current_timestamp_ns}"
        
        # 步驟 3: convert tmp_uuid to 32-bit integer -> return_uuid
        # 雜湊函數 (如 CRC32) 需要 'bytes' 類型的輸入，而不是 'str'。
        # 我們使用 'utf-8' 進行編碼。
        tmp_uuid_bytes = tmp_uuid_str.encode('utf-8')
        
        # zlib.crc32() 是一個高效、穩定且內建的函數，
        # 它可以將任意長度的位元組轉換為一個 32-bit (無符號) 整數。
        # 
        # 備註: 
        # 1. crc32 返回的是一個 0 到 2^32-1 之間的 "無符號 (unsigned)" 32-bit 整數。
        # 2. 加上 & 0xffffffff 是為了確保在所有 Python 環境 (32-bit/64-bit) 
        #    中，結果都保持在 32-bit 無符號整數的範圍內，這是一種良好的防禦性程式設計。
        return_uuid = zlib.crc32(tmp_uuid_bytes) & 0xffffffff    
        return return_uuid