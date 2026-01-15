# utils/remove_image_bg.py
from rembg import remove
from PIL import Image
import io

# 設定輸入與輸出路徑
input_path = './new_logo.png'
output_path = './new_logo_transparent.png'

try:
    print(f"正在處理: {input_path} ...")
    
    # 開啟圖片
    input_image = Image.open(input_path)
    
    # 執行去背
    output_image = remove(input_image)
    
    # 儲存結果 (PNG格式支援透明背景)
    output_image.save(output_path)
    
    print(f"✅ 去背完成！已儲存為: {output_path}")

except Exception as e:
    print(f"❌ 發生錯誤: {e}")