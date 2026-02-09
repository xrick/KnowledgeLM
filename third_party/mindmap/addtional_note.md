💡 額外建議
結構化輸出 (Structured Output)： 我們的 mindmap_engine.py 使用了 as_structured_llm。對於開源模型來說，有時候嚴格的 JSON 格式會比較難遵循。

如果執行時發現報錯（例如 JSON 解析錯誤），請確認你的 gpt-oss:20b 是否足夠聰明能理解 Pydantic 的 Schema。

如果模型一直失敗，可以在 MindMapGenerator 裡把 prompt 改得更明確，強調「只輸出純 JSON，不要有任何 Markdown 格式或額外文字」。

如果是使用 OpenAI 相容 API (vLLM / LM Studio)： 如果你不是用 Ollama，而是用 vLLM 架設的伺服器，請改用 OpenAILike：
```python
from llama_index.llms.openai_like import OpenAILike

local_llm = OpenAILike(
    model="gpt-oss:20b",
    api_base="http://localhost:8000/v1",  # 你的 API 網址
    api_key="fake-key",
    is_chat_model=True
)
