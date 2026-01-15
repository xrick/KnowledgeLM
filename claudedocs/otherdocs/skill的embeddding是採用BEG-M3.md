<!-- claudedocs/skill的embeddding是採用BEG-M3.md -->
claudedocs/skill的embeddding是採用BEG-M

✅ 是的，文檔和查詢都使用 BGE-M3
根據我的程式碼分析，兩者都使用 BGE-M3 模型：
📊 Embedding 使用架構
┌─────────────────────────────────────────────────────────────────┐
│                      BGE-M3 Embedding Flow                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📄 Document Indexing (建立索引)                                │
│  ────────────────────────────────                               │
│  scripts/rebuild_skills.py:                                     │
│     embedding = self.embedding_provider.embed_single(page_text) │
│                          ↓                                      │
│     BGEEmbeddingProvider (BAAI/bge-m3, 1024 dim)               │
│                                                                 │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  🔍 Query Embedding (使用者查詢)                                │
│  ────────────────────────────────                               │
│  FAISS store 使用 EmbeddingWrapper:                             │
│     class EmbeddingWrapper:                                     │
│         def embed_query(self, text):                            │
│             return self._provider.embed_single(text).tolist()   │
│                          ↓                                      │
│     BGEEmbeddingProvider (同一模型)                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
🔑 關鍵程式碼證據
1. Document Embedding (rebuild_skills.py:165-166)
# 生成 embedding
embedding = self.embedding_provider.embed_single(page_text)
2. Query Embedding (rebuild_skills.py:226-231)
# Create embedding wrapper for query compatibility
class EmbeddingWrapper:
    def __init__(self, provider):
        self._provider = provider
    def embed_query(self, text):
        return self._provider.embed_single(text).tolist()
3. BGE-M3 Provider (bge_embedding_provider.py:21)
def __init__(self, model_name: str = "BAAI/bge-m3", device: str = None):
    self.model_name = model_name
    self.dimension = 1024  # BGE-M3 has 1024 dimensions
📋 模型規格
屬性	值
模型名稱	BAAI/bge-m3
維度	1024
最大序列長度	8192 tokens
語言支援	Multilingual (中文優化)
用途	Document + Query embedding
💡 為什麼這很重要？
使用相同的 embedding 模型對於 RAG 系統至關重要：
✅ 向量空間一致性 - 確保 query 和 documents 在同一向量空間
✅ 相似度計算準確 - L2 距離計算有意義
✅ 檢索品質保證 - 避免維度或語義不匹配