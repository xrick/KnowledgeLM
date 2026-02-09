import asyncio
import os

# 導入 LlamaIndex 的 Ollama 模組
from llama_index.llms.ollama import Ollama
from mindmap_engine import MindMapGenerator

# 模擬資料
doc_summary = (
    "羅馬帝國的衰亡是一個複雜的過程，涉及內部政治腐敗、經濟崩潰以及外部蠻族的入侵。"
)
doc_highlights = [
    "西元 476 年西羅馬帝國滅亡",
    "日耳曼民族的大遷徙",
    "軍隊過度依賴僱傭兵",
    "經濟通貨膨脹嚴重",
]


async def main():
    print(f"正在初始化模型: gpt-oss:20b ...")

    # 1. 設定本地 LLM (Ollama)
    # request_timeout: 設定長一點，因為 20b 模型生成速度可能較慢
    # json_mode: 建議開啟，幫助模型更穩定輸出 JSON 格式 (如果模型支援)
    local_llm = Ollama(model="gpt-oss:20b", request_timeout=360.0, json_mode=True)

    # 2. 初始化生成器，並「注入」你的本地模型
    # 這樣 MindMapGenerator 就會使用 gpt-oss:20b 而不是預設的 OpenAI
    generator = MindMapGenerator(llm=local_llm, output_dir="./static/mindmaps")

    print("正在生成心智圖 (這可能需要一點時間)...")

    # 3. 執行生成
    try:
        html_path = await generator.generate(
            summary=doc_summary, highlights=doc_highlights
        )
        print(f"✅ 生成成功！檔案位於: {html_path}")
    except Exception as e:
        print(f"❌ 生成失敗: {e}")


if __name__ == "__main__":
    asyncio.run(main())
