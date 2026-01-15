# 向量檢索問題診斷報告 - document_ids 參數錯誤

**日期**: 2025-12-06  
**問題**: 用戶查詢「請說明大語言模型的預訓練」時，即使將 RETRIEVAL_TOP_K 設為 50，系統仍回覆「找不到相關內容」

---

## 🎯 根本原因 (Root Cause)

前端只傳遞 **Head ID** 而非**子文件 IDs**，導致後端嘗試讀取不存在的 FAISS 索引。

### 問題流程

```
用戶選擇「大語言模型大全」
    ↓
前端: selectedSkills = [{ id: "skill_20251203_071733_2a43e5ac" }]  ← Head ID
    ↓
前端: document_ids = ["skill_20251203_071733_2a43e5ac"]  ❌ 只有 Head
    ↓
POST /api/v1/skills/{skill_id}/chat/stream
    body: { "document_ids": ["skill_20251203_071733_2a43e5ac"] }
    ↓
Phase 2: 嘗試讀取 /data/faiss_indices/skills/{head_id}/index.faiss
    ↓
❌ 路徑不存在！真正的索引在 _src_00 ~ _src_08
    ↓
返回: chunks = []
    ↓
LLM: "找不到相關內容"
```

---

## 📊 診斷結果

### 資料庫狀態 ✅

```sql
SELECT skill_id, parent_skill_id, total_chunks
FROM skill_metadata
WHERE skill_name = '大語言模型大全';
```

| skill_id | parent_skill_id | total_chunks |
|----------|-----------------|--------------|
| skill_20251203_071733_2a43e5ac | root | 3685 |
| skill_..._src_00 | skill_20251203_071733_2a43e5ac | 370 |
| skill_..._src_01 | skill_20251203_071733_2a43e5ac | 385 |
| ... (共 9 個子文件) | ... | ... |

✅ **資料庫完整**: 1 個 Head + 9 個子文件，總計 3685 chunks

### FAISS 索引狀態 ✅

```bash
ls /data/faiss_indices/skills/ | grep skill_20251203_071733_2a43e5ac
```

```
skill_20251203_071733_2a43e5ac_src_00/  ✅ 有 index.faiss
skill_20251203_071733_2a43e5ac_src_01/  ✅ 有 index.faiss
...
skill_20251203_071733_2a43e5ac_src_08/  ✅ 有 index.faiss
```

⚠️ **問題**: `skill_20251203_071733_2a43e5ac/` 目錄不存在（Head 無索引）

### 前端參數 ❌

**檔案**: `template/skill_main.html` Line 2281

```javascript
const skillIds = selectedSkills.map(s => s.id);  // ❌ 只取 Head ID
// skillIds = ["skill_20251203_071733_2a43e5ac"]
```

**應該改為**:
```javascript
// ✅ 展開子文件
const documentIds = selectedSkills.flatMap(skill => 
    skill.children?.map(c => c.id) || [skill.id]
);
// documentIds = ["..._src_00", "..._src_01", ..., "..._src_08"]
```

---

## 🔧 解決方案

### 方案 1: 前端展開子文件 (推薦，15 分鐘)

**修改檔案**: `template/skill_main.html`  
**位置**: Lines 2274-2334 (`sendProgressiveQuery` 函數)

```javascript
async function sendProgressiveQuery(query) {
    isLoading = true;
    const button = document.getElementById('send-button');
    button.classList.add('loading');
    button.disabled = true;

    try {
        // ✅ 展開所有選中的文件（包含子文件）
        const documentIds = [];

        for (const skill of selectedSkills) {
            if (skill.children && skill.children.length > 0) {
                // 有子文件 → 添加所有子文件 ID
                documentIds.push(...skill.children.map(child => child.id));
            } else {
                // 無子文件 → 添加自身 ID
                documentIds.push(skill.id);
            }
        }

        console.log(`📄 Document IDs: ${documentIds.length} docs`, documentIds);

        const skillId = selectedSkills[0].id;

        // ... 其餘代碼不變 ...

        startProgressiveChat(
            query,
            `/api/v1/skills/${skillId}/chat/stream`,
            `#${containerId}`,
            `#${progressId} .progress-bar`,
            documentIds,  // ✅ 傳遞展開後的 IDs
            onStreamComplete
        );

    } catch (error) {
        // ... 錯誤處理 ...
    }
}
```

**預期效果**:
- 修復前: `document_ids = ["skill_..._2a43e5ac"]` (1 個 Head)
- 修復後: `document_ids = ["..._src_00", "..._src_01", ..., "..._src_08"]` (9 個文件)

---

### 方案 2: 後端自動展開 (備用，30 分鐘)

**修改檔案**: `app/SkillServices/progressive_skill_streaming/phase2_skill_retrieval.py`

```python
async def retrieve(
    self,
    query: str,
    document_ids: List[str],
    top_k: int = 5,
    use_cache: bool = True
) -> AsyncGenerator[Dict[str, Any], None]:
    """執行並行檢索"""
    
    # ✅ 自動展開 Head IDs
    expanded_ids = await self._expand_head_ids(document_ids)
    logger.info(f"Expanded {len(document_ids)} → {len(expanded_ids)} documents")
    
    # 使用展開後的 IDs
    search_results = await self._parallel_search(
        query_embedding,
        expanded_ids,  # ✅
        top_k
    )
    # ...

async def _expand_head_ids(self, document_ids: List[str]) -> List[str]:
    """展開 Head IDs 為所有子文件 IDs"""
    expanded = []
    
    for doc_id in document_ids:
        skill = await self.metadata_provider.get_skill(doc_id)
        
        if skill and skill.get('parent_skill_id') == 'root':
            # Head → 查詢子文件
            children = await self.metadata_provider.get_children(doc_id)
            if children:
                expanded.extend([c['skill_id'] for c in children])
            else:
                expanded.append(doc_id)
        else:
            # 已是子文件
            expanded.append(doc_id)
    
    return expanded
```

**需要新增 Provider 方法** (`app/Providers/skill_metadata_provider/client.py`):

```python
async def get_children(self, parent_skill_id: str) -> List[Dict]:
    """獲取某 skill 的所有子文件"""
    query = """
        SELECT skill_id, skill_name, source_name, total_chunks
        FROM skill_metadata
        WHERE parent_skill_id = ?
    """
    cursor = self.conn.execute(query, (parent_skill_id,))
    rows = cursor.fetchall()
    
    return [
        {
            'skill_id': row[0],
            'skill_name': row[1],
            'source_name': row[2],
            'total_chunks': row[3]
        }
        for row in rows
    ]
```

---

### 方案 3: 臨時應急 (2 分鐘)

**修改檔案**: `template/skill_main.html` Line 1138

```javascript
// 臨時切換到 Traditional Query (無 SSE，但查詢正常)
const USE_PROGRESSIVE_STREAMING = false;  // ✅
```

**影響**:
- ❌ 失去 SSE 串流
- ❌ 失去進度條
- ✅ 查詢功能正常

---

## ✅ 驗證清單

### 測試步驟

1. **實施方案 1** (前端展開)
2. **重啟服務器** (如果需要)
3. **選擇「大語言模型大全」**
4. **查詢「大語言模型的預訓練」**
5. **檢查前端 Console**:
   ```
   📄 Document IDs: 9 docs ["..._src_00", "..._src_01", ...]
   ```
6. **檢查後端日誌**:
   ```
   Phase 2: Searching 9 documents...
   Retrieved 37 chunks from ..._src_00
   Retrieved 42 chunks from ..._src_01
   ...
   Total: 215 chunks retrieved
   ```
7. **驗證回答** (應包含預訓練知識)

### 預期修復

**修復前**:
```
Phase 2: FAISS index not found
Retrieved 0 chunks
Response: "找不到相關內容"
```

**修復後**:
```
Phase 2: Expanded 1 → 9 documents
Retrieved 215 chunks from 9 documents
Response: "大語言模型的預訓練分為以下階段：..."
```

---

## 📝 總結

| 項目 | 狀態 | 說明 |
|------|------|------|
| 資料庫 | ✅ | 9 個子文件，3685 chunks |
| FAISS 索引 | ✅ | 每個子文件有完整索引 |
| RETRIEVAL_TOP_K | ✅ | 正確設為 50 |
| 前端參數 | ❌ | 只傳 Head ID，未展開 |
| 後端處理 | ⚠️ | 無展開邏輯 |

**建議執行順序**:
1. 🔴 **立即**: 方案 3 (切換 Traditional) - 2 分鐘
2. 🟡 **今天**: 方案 1 (前端展開) - 15 分鐘
3. 🟢 **本周**: 方案 2 (後端展開) - 30 分鐘

---

*SuperClaude Framework - Evidence-Based Diagnosis*  
*Generated: 2025-12-06*
