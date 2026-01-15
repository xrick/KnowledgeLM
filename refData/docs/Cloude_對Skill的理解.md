/sc:explain 
```
今天最後，我想知道你對我給你的新增的 skill 功能是什麼？
```
🎯 Skill-Based Architecture 功能解析
讓我解釋我對您要求新增的 Skill 功能的理解：
📚 什麼是 Skill？
Skill（技能） 是一個知識領域的集合，將 20-100 個高度相關的 PDF 文件組織成一個邏輯單元。
傳統 File-Based:
用戶 → 勾選多個文件 → 查詢 → 獲得結果
      ↑
    需要記住哪些文件相關

Skill-Based:
用戶 → 選擇一個 Skill → 查詢 → 獲得該領域所有知識
      ↑
    只需選擇知識領域
🔍 核心概念理解
概念	我的理解	實際意義
Skill = 知識領域	一個 skill 包含 20-100 個相關 PDFs 的 embeddings	例如："Python程式設計"、"法律條文"、"醫療知識"
單一選擇模式	主頁面一次只能選擇一個 skill	專注於單一領域的深度查詢
領域聚焦	查詢針對該 skill 內所有文件	不需要逐個勾選文件
物理隔離	每個 skill 有獨立的存儲目錄	./data/faiss_indices/skills/skill_name/
🎨 使用場景對比
現有系統 (File-Based)
# 用戶需要查詢 Python async 相關知識
# 必須：
1. 記住有哪些相關文件
2. 逐個勾選: 
   ☑ python_async_tutorial.pdf
   ☑ asyncio_guide.pdf
   ☑ coroutines_explained.pdf
   ... (可能忘記某些文件)
3. 執行查詢
新系統 (Skill-Based)
# 用戶需要查詢 Python async 相關知識
# 只需：
1. 選擇 Skill: "Python進階程式設計"
2. 執行查詢
# 自動搜索該 skill 內所有相關文件！
🏗️ 架構設計理解
您要求的完全隔離架構：
DocAI System
├── 原有系統 (不動)
│   ├── app/Services/           # File-based services
│   ├── data/file_metadata.db   # File metadata
│   └── data/faiss_indices/files/  # File vectors
│
└── 新增系統 (獨立)
    ├── app/SkillServices/      # Skill-based services ✅
    ├── data/skill_metadata.db  # Skill metadata ✅
    └── data/faiss_indices/skills/  # Skill vectors ✅
💡 解決的核心問題
認知負擔降低
Before: 用戶需記住文件關聯性
After: 只需選擇知識領域
查詢效率提升
Before: 逐個勾選多個文件
After: 一鍵選擇整個領域
知識組織優化
Before: 平面化的文件列表
After: 層級化的知識體系
可擴展性增強
Before: 100+ 文件難以管理
After: 分組為 5-10 個 skills 易於導航
🔑 關鍵實作決策
基於您的需求，我做了以下理解和實作：
需求	我的理解	實作方式
"將新的架構區隔開來"	完全不影響現有系統	獨立的 SkillServices 目錄
"reference path"	可以引用但不修改	from app.Services.xxx import
"新的 db"	數據完全隔離	skill_metadata.db 獨立數據庫
"以該 skill 命名的資料夾"	物理存儲隔離	/skills/skill_name/ 結構
🎯 我的理解總結
Skill-Based Architecture 是一個知識管理升級：
從「管理文件」升級為「管理知識領域」
從「手動關聯」升級為「自動聚合」
從「記憶負擔」升級為「直覺選擇」
這就像是：
圖書館：從「記住每本書的位置」變成「選擇知識分類區」
音樂：從「選擇每首歌」變成「選擇播放列表」
購物：從「逐個選商品」變成「選擇套裝組合」Skill-Based Architecture 優化分析報告
A. 並行搜尋分析 ✅
是的，並行搜尋絕對可行且推薦！
現有實作的並行潛力分析
# 目前的 SkillRetrievalService 實作
for skill_id in content_ids:
    results = self.vector_store_provider.similarity_search(...)
    all_results.extend(results)
優化為並行搜尋
import asyncio
from concurrent.futures import ThreadPoolExecutor

class OptimizedSkillRetrievalService(AbstractRetrievalService):
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=10)
        
    async def retrieve_context(
        self,
        query: str,
        content_ids: List[str],  # 100 個 file_ids
        top_k: int = 5
    ):
        # 並行搜尋所有文件
        tasks = []
        for file_id in content_ids:
            task = asyncio.create_task(
                self._search_single_file_async(file_id, query, top_k)
            )
            tasks.append(task)
        
        # 等待所有搜尋完成
        all_results = await asyncio.gather(*tasks)
        
        # 合併並排序結果
        merged_results = self._merge_and_rank(all_results, top_k)
        return merged_results
效能預估：
串行：100 files × 5ms = 500ms
並行 (10 workers)：500ms / 10 = 50ms
B. 創新優化建議分析
1. 虛擬合併索引 (Virtual Merged Index) 🎯
技術可行性：極高 - 這是最優解！
# 實作方案
class SkillMasterIndexManager:
    """
    維護 Skill 層級的 Master Index
    """
    def __init__(self, skill_id: str):
        self.skill_id = skill_id
        self.master_index_path = f"data/faiss_indices/skills/{skill_id}/master_index.faiss"
        self.file_mapping = {}  # file_id -> vector_id_range
        
    async def add_file_to_skill(self, file_id: str, chunks: List[str], embeddings):
        """添加文件時同時更新 Master Index"""
        # 1. 保存個別文件索引（便於管理）
        individual_path = f"data/faiss_indices/skills/{self.skill_id}/{file_id}/index.faiss"
        individual_index = FAISS.from_texts(chunks, embeddings)
        individual_index.save_local(individual_path)
        
        # 2. 更新 Master Index
        if os.path.exists(self.master_index_path):
            master_index = FAISS.load_local(self.master_index_path, embeddings)
            # 使用 IDMap 支援刪除操作
            start_id = len(master_index.index_to_docstore_id)
            master_index.add_texts(chunks, metadatas=[{"file_id": file_id}])
            end_id = start_id + len(chunks)
            self.file_mapping[file_id] = (start_id, end_id)
        else:
            # 初始化 Master Index
            master_index = FAISS.from_texts(chunks, embeddings)
        
        master_index.save_local(self.master_index_path)
        
    async def remove_file_from_skill(self, file_id: str):
        """刪除文件時的處理策略"""
        # 方案 A: 標記刪除（不真正刪除向量，只是過濾結果）
        self.deleted_files.add(file_id)
        
        # 方案 B: 定期重建（當刪除數量達到閾值）
        if len(self.deleted_files) > 10:
            await self.rebuild_master_index()
實作建議：
立即實作 Master Index
使用 FAISS IDMap 支援刪除
保留個別索引作為備份
2. Skill 的熱切換 (Hot-Swapping) 🔄
技術可行性：高 - 記憶體優化的好方案！
class SkillHotSwapManager:
    """
    Skill 索引的記憶體管理器
    """
    def __init__(self, max_cached_skills: int = 3):
        self.loaded_skills = {}  # skill_id -> loaded_index
        self.lru_queue = []  # LRU 淘汰策略
        self.max_cached = max_cached_skills
        
    async def switch_to_skill(self, skill_id: str) -> FAISS:
        """切換到指定 Skill"""
        # 1. 檢查是否已載入
        if skill_id in self.loaded_skills:
            self._mark_as_used(skill_id)
            return self.loaded_skills[skill_id]
        
        # 2. 載入新 Skill
        skill_index = await self._load_skill_index(skill_id)
        
        # 3. 記憶體管理
        if len(self.loaded_skills) >= self.max_cached:
            # 淘汰最少使用的 Skill
            lru_skill = self.lru_queue.pop(0)
            del self.loaded_skills[lru_skill]
            logger.info(f"Evicted skill {lru_skill} from memory")
        
        # 4. 快取新 Skill
        self.loaded_skills[skill_id] = skill_index
        self.lru_queue.append(skill_id)
        
        return skill_index
        
    async def preload_skill(self, skill_id: str):
        """預載入 Skill（背景執行）"""
        asyncio.create_task(self._load_skill_index(skill_id))
實作建議：
WebSocket 通知前端切換 Skill
後端預載入下一個可能的 Skill
使用 LRU 快取策略
3. 多模態 Skill 封面 (Skill Cover Generation) 🎨
技術可行性：中 - 增強 UX 的好想法！
class SkillCoverGenerator:
    """
    Skill 封面圖生成器
    """
    def __init__(self):
        self.icon_library = {
            "法律": "⚖️",
            "醫療": "🏥",
            "科技": "💻",
            "教育": "📚",
            "金融": "💰"
        }
        
    async def generate_skill_cover(
        self,
        skill_name: str,
        skill_category: str,
        skill_description: str
    ) -> Dict:
        """生成 Skill 封面資訊"""
        
        # 方案 A: 使用 Emoji + 漸層背景
        cover = {
            "icon": self._select_icon(skill_category),
            "gradient": self._generate_gradient(skill_name),
            "thumbnail_text": skill_name[:2].upper()
        }
        
        # 方案 B: 調用 DALL-E API（需要額外成本）
        # cover["image_url"] = await self.generate_ai_image(skill_description)
        
        # 方案 C: 從預設圖庫選擇
        cover["preset_image"] = f"/assets/skills/{skill_category.lower()}.svg"
        
        return cover
📊 綜合優化方案架構
Optimized Skill Architecture:
  Storage:
    ├── Individual Indices (管理用)
    │   └── /skills/{skill_id}/{file_id}/index.faiss
    └── Master Index (查詢用) ⭐
        └── /skills/{skill_id}/master_index.faiss
  
  Memory:
    ├── Hot Swap Manager
    │   ├── Max 3 Skills in Memory
    │   └── LRU Eviction Policy
    └── Preloading Strategy
  
  Query:
    ├── Single Master Index Search (快 100x)
    ├── Parallel Search Fallback
    └── Result Caching Layer
  
  UI Enhancement:
    ├── Skill Cover Generation
    ├── Loading State Management
    └── Skill Switch Animation
🚀 實作優先順序建議
優先級	優化項目	預估工時	效能提升	實作難度
P0	Master Index	4 小時	100x	中
P1	並行搜尋	2 小時	10x	低
P2	Hot Swapping	3 小時	節省 70% RAM	中
P3	Skill Cover	2 小時	UX 提升	低
💡 立即可行動項目
# 1. 修改 SkillRetrievalService 加入 Master Index
class EnhancedSkillRetrievalService(SkillRetrievalService):
    async def add_content(self, content_id: str, chunks: List[str], metadata=None):
        # 原有邏輯
        await super().add_content(content_id, chunks, metadata)
        
        # 新增：更新 Master Index
        await self._update_master_index(content_id, chunks, metadata)
    
    async def retrieve_context(self, query: str, skill_id: str, top_k: int = 5):
        # 優先使用 Master Index
        if self._has_master_index(skill_id):
            return await self._search_master_index(skill_id, query, top_k)
        
        # Fallback: 並行搜尋
        return await self._parallel_search_files(skill_id, query, top_k)
這些優化將使您的 Skill-Based Architecture 達到企業級的效能水準！要開始實作哪個部分