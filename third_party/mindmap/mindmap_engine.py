import json
import os
import uuid
from typing import List, Optional, Union

from llama_index.core.llms import LLM, ChatMessage
from llama_index.llms.openai import OpenAI
from pydantic import BaseModel, Field, model_validator
from pyvis.network import Network

# --- 資料結構 (Data Models) ---


class Node(BaseModel):
    id: str
    content: str


class Edge(BaseModel):
    from_id: str
    to_id: str


class MindMap(BaseModel):
    """
    定義心智圖的結構，用於強制 LLM 輸出特定格式的 JSON。
    """

    nodes: List[Node] = Field(
        description="心智圖的節點列表，每個節點包含 id 和簡短的內容 (不超過 5 個字)。"
    )
    edges: List[Edge] = Field(
        description="連接節點的邊列表，包含來源 (from_id) 和目標 (to_id)。"
    )

    @model_validator(mode="after")
    def validate_mind_map(self):
        all_nodes = {el.id for el in self.nodes}
        all_edges = {el.from_id for el in self.edges} | {el.to_id for el in self.edges}

        # 檢查是否有邊連接到不存在的節點
        if not all_edges.issubset(all_nodes):
            raise ValueError("邊 (Edges) 引用了不存在的節點 ID")
        return self


# --- 核心邏輯 (Core Logic) ---


class MindMapGenerator:
    def __init__(self, llm: Optional[LLM] = None, output_dir: str = "output"):
        """
        初始化生成器。

        Args:
            llm: 傳入已設定好的 LlamaIndex LLM 物件。如果為 None，預設使用 GPT-4o-mini。
            output_dir: 生成的 HTML 檔案存放目錄。
        """
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # 設定 LLM，預設使用 OpenAI
        if llm is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("未提供 LLM 且未設定 OPENAI_API_KEY 環境變數。")
            base_llm = OpenAI(model="gpt-4o-mini", api_key=api_key)
        else:
            base_llm = llm

        # 將 LLM 轉換為結構化輸出模式 (Structured LLM)
        self.structured_llm = base_llm.as_structured_llm(MindMap)

    async def generate(self, summary: str, highlights: List[str]) -> str:
        """
        生成心智圖並回傳 HTML 檔案路徑。
        """
        try:
            # 1. 準備 Prompt
            keypoints = "\n- ".join(highlights)
            prompt = (
                f"請根據這份文件摘要和重點，生成一個心智圖結構：\n\n"
                f"摘要：{summary}\n\n"
                f"重點：\n- {keypoints}"
            )

            messages = [ChatMessage(role="user", content=prompt)]

            # 2. 呼叫 LLM 生成結構化資料
            response = await self.structured_llm.achat(messages=messages)

            # 解析 JSON (LlamaIndex 的 structured_llm 會自動處理，這裡直接讀取內容)
            # 注意：as_structured_llm 回傳的 message.content 通常已經是 JSON 字串
            mindmap_data = json.loads(response.message.content)

            # 3. 使用 PyVis 繪圖
            return self._create_visualization(mindmap_data)

        except Exception as e:
            print(f"心智圖生成失敗: {e}")
            raise e

    def _create_visualization(self, data: dict) -> str:
        """
        內部函式：將 JSON 資料轉換為 HTML 視覺化圖表
        """
        net = Network(directed=True, height="750px", width="100%")

        # 設定物理引擎選項，讓圖表穩定一點
        net.set_options("""
        var options = {
            "physics": {
                "enabled": false,
                "hierarchicalRepulsion": {
                    "nodeDistance": 150
                }
            },
            "layout": {
                "hierarchical": {
                    "enabled": true,
                    "direction": "UD",
                    "sortMethod": "directed"
                }
            }
        }
        """)

        # 加入節點
        for node in data["nodes"]:
            net.add_node(
                n_id=node["id"], label=node["content"], shape="box", color="#97C2FC"
            )

        # 加入邊
        for edge in data["edges"]:
            net.add_edge(source=edge["from_id"], to=edge["to_id"])

        # 輸出檔案
        filename = f"mindmap_{uuid.uuid4()}.html"
        filepath = os.path.join(self.output_dir, filename)

        # PyVis 的 save_graph 有時會有路徑問題，建議切換目錄或使用絕對路徑
        # 這裡簡單處理：
        current_dir = os.getcwd()
        os.chdir(self.output_dir)
        net.save_graph(filename)
        os.chdir(current_dir)

        return filepath
