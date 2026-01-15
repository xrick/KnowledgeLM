# Demo Easy-to-Achieve Approach
## 下周一、二 Demo 快速實現方案

**截止日期**: 下周一、二 (2-3天內)
**策略**: 最小改動，最大效果，確保穩定
**原則**: Demo First, Refactor Later

---

## 🎯 Demo 核心需求

1. **展示Skill概念**: 用戶看到"技能"而非"文件"
2. **多文件搜尋**: 一個Skill包含20-100個相關PDF
3. **切換能力**: 可在不同Skill間切換
4. **查詢效果**: 能從Skill中找到相關內容
5. **視覺區分**: UI上明確顯示Skill模式

---

## 🚀 最快實現路徑 (6小時完成)

### Step 1: 簡單UI切換 (1小時)
```javascript
// frontend/src/components/ModeSelector.jsx
function ModeSelector({ mode, onModeChange }) {
  return (
    <div className="mode-selector">
      <label>
        <input
          type="radio"
          value="file"
          checked={mode === 'file'}
          onChange={(e) => onModeChange(e.target.value)}
        />
        檔案模式 (File Mode)
      </label>
      <label>
        <input
          type="radio"
          value="skill"
          checked={mode === 'skill'}
          onChange={(e) => onModeChange(e.target.value)}
        />
        技能模式 (Skill Mode) 🆕
      </label>
    </div>
  );
}
```

### Step 2: 預載入Demo Skills (2小時)
```python
# scripts/prepare_demo_skills.py
"""預先準備3個Demo用的Skills"""

demo_skills = [
    {
        "skill_id": "skill_ai_research",
        "skill_name": "AI研究論文集",
        "description": "包含最新AI研究論文",
        "files": ["paper1.pdf", "paper2.pdf", ...],  # 20-30個文件
        "icon": "🤖"
    },
    {
        "skill_id": "skill_python_docs",
        "skill_name": "Python開發文檔",
        "description": "Python相關技術文檔",
        "files": ["django.pdf", "fastapi.pdf", ...],  # 20-30個文件
        "icon": "🐍"
    },
    {
        "skill_id": "skill_business_reports",
        "skill_name": "商業分析報告",
        "description": "市場分析與商業報告",
        "files": ["report1.pdf", "report2.pdf", ...],  # 20-30個文件
        "icon": "📊"
    }
]

async def prepare_demo_skills():
    """一鍵準備Demo資料"""
    for skill in demo_skills:
        print(f"準備 {skill['skill_name']}...")

        # 1. 創建Skill metadata
        await skill_metadata_provider.create_skill(
            skill_id=skill['skill_id'],
            skill_name=skill['skill_name'],
            skill_description=skill['description']
        )

        # 2. 處理每個文件
        for file_path in skill['files']:
            # 使用現有的ingestion流程
            chunks = extract_and_chunk(file_path)

            # 存入Skill向量庫
            await skill_retrieval_service.add_content(
                content_id=f"{skill['skill_id']}_{file_path}",
                chunks=chunks,
                metadata={'skill_id': skill['skill_id']}
            )

        print(f"✅ {skill['skill_name']} 準備完成")

if __name__ == "__main__":
    asyncio.run(prepare_demo_skills())
```

### Step 3: 簡單API端點 (1小時)
```python
# app/api/v1/endpoints/skills_demo.py
"""Demo用的簡化Skill端點"""

@router.get("/demo/skills")
async def list_demo_skills():
    """列出預設的Demo Skills"""
    return {
        "skills": [
            {
                "id": "skill_ai_research",
                "name": "AI研究論文集",
                "fileCount": 25,
                "icon": "🤖",
                "status": "ready"
            },
            {
                "id": "skill_python_docs",
                "name": "Python開發文檔",
                "fileCount": 30,
                "icon": "🐍",
                "status": "ready"
            },
            {
                "id": "skill_business_reports",
                "name": "商業分析報告",
                "fileCount": 20,
                "icon": "📊",
                "status": "ready"
            }
        ]
    }

@router.post("/demo/skills/query")
async def query_skill_demo(
    skill_id: str,
    query: str,
    top_k: int = 10
):
    """簡單的Skill查詢"""
    # 直接使用並行搜尋 (Level 1優化)
    file_ids = await get_skill_files(skill_id)

    # 並行搜尋所有文件
    tasks = []
    for file_id in file_ids[:10]:  # Demo限制前10個文件
        task = retrieval_service.retrieve_context(
            query=query,
            content_ids=[file_id],
            top_k=3  # 每個文件取3個結果
        )
        tasks.append(task)

    # 合併結果
    all_results = await asyncio.gather(*tasks)
    merged_results = []
    for results in all_results:
        merged_results.extend(results)

    # 簡單排序
    merged_results.sort(key=lambda x: x.get('score', 0))

    return {
        "skill_id": skill_id,
        "query": query,
        "results": merged_results[:top_k]
    }
```

### Step 4: 前端整合 (1.5小時)
```javascript
// frontend/src/pages/SkillDemo.jsx
function SkillDemoPage() {
  const [selectedSkill, setSelectedSkill] = useState(null);
  const [skills, setSkills] = useState([]);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  // 載入Skills
  useEffect(() => {
    fetch('/api/v1/demo/skills')
      .then(res => res.json())
      .then(data => setSkills(data.skills));
  }, []);

  // 查詢處理
  const handleQuery = async () => {
    if (!selectedSkill || !query) return;

    setLoading(true);
    try {
      const response = await fetch('/api/v1/demo/skills/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          skill_id: selectedSkill.id,
          query: query
        })
      });

      const data = await response.json();
      setResults(data.results);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="skill-demo-container">
      <h2>🎯 Skill-Based RAG Demo</h2>

      {/* Skill選擇 */}
      <div className="skill-selector">
        <h3>選擇技能 (Select Skill):</h3>
        {skills.map(skill => (
          <div
            key={skill.id}
            className={`skill-card ${selectedSkill?.id === skill.id ? 'selected' : ''}`}
            onClick={() => setSelectedSkill(skill)}
          >
            <span className="skill-icon">{skill.icon}</span>
            <span className="skill-name">{skill.name}</span>
            <span className="file-count">({skill.fileCount} 檔案)</span>
          </div>
        ))}
      </div>

      {/* 查詢輸入 */}
      {selectedSkill && (
        <div className="query-section">
          <h3>查詢 {selectedSkill.name}:</h3>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="輸入您的問題..."
            onKeyPress={(e) => e.key === 'Enter' && handleQuery()}
          />
          <button onClick={handleQuery} disabled={loading}>
            {loading ? '搜尋中...' : '搜尋'}
          </button>
        </div>
      )}

      {/* 結果顯示 */}
      {results.length > 0 && (
        <div className="results-section">
          <h3>搜尋結果:</h3>
          {results.map((result, idx) => (
            <div key={idx} className="result-item">
              <div className="result-header">
                <span>相關度: {(1 - result.score).toFixed(3)}</span>
                <span>來源: {result.metadata?.filename}</span>
              </div>
              <div className="result-content">
                {result.content}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

### Step 5: 快速測試腳本 (0.5小時)
```bash
#!/bin/bash
# scripts/demo_test.sh
# 快速測試Demo功能

echo "🎯 測試Skill Demo功能"

# 1. 準備Demo資料
echo "準備Demo Skills..."
python scripts/prepare_demo_skills.py

# 2. 啟動服務
echo "啟動服務..."
./start_system.sh

# 3. 測試API
echo "測試API..."
curl -X GET http://localhost:8001/api/v1/demo/skills

# 4. 測試查詢
echo "測試查詢..."
curl -X POST http://localhost:8001/api/v1/demo/skills/query \
  -H "Content-Type: application/json" \
  -d '{
    "skill_id": "skill_ai_research",
    "query": "什麼是深度學習"
  }'

echo "✅ Demo測試完成"
```

---

## 🎨 Demo 視覺增強 (可選，0.5小時)

### 1. Skill卡片動畫
```css
.skill-card {
  transition: all 0.3s ease;
  border: 2px solid transparent;
}

.skill-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 5px 15px rgba(0,0,0,0.1);
}

.skill-card.selected {
  border-color: #4CAF50;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}
```

### 2. Loading動畫
```javascript
// 搜尋時顯示骨架屏
{loading && (
  <div className="skeleton-loader">
    <div className="skeleton-line"></div>
    <div className="skeleton-line"></div>
    <div className="skeleton-line"></div>
  </div>
)}
```

### 3. 結果高亮
```javascript
// 高亮查詢關鍵字
function highlightQuery(text, query) {
  const regex = new RegExp(`(${query})`, 'gi');
  return text.replace(regex, '<mark>$1</mark>');
}
```

---

## 📋 Demo 檢查清單

### 必須完成 ✅
- [ ] Mode切換UI
- [ ] 3個預設Skills
- [ ] 基本查詢功能
- [ ] 結果顯示
- [ ] 並行搜尋優化

### 建議完成 🎯
- [ ] Skill圖標和描述
- [ ] Loading動畫
- [ ] 結果排序
- [ ] 關鍵字高亮
- [ ] 響應式設計

### 可選增強 ✨
- [ ] Skill統計信息
- [ ] 查詢歷史
- [ ] 結果導出
- [ ] 性能指標顯示

---

## 🚨 風險控制

### 風險1: 時間不足
**對策**: 只實現必須功能，UI可以簡化

### 風險2: 資料準備
**對策**: 提前準備好Demo PDFs，確保內容相關

### 風險3: 性能問題
**對策**: Demo限制每個Skill 20-30個文件

### 風險4: 查詢品質
**對策**: 精心選擇Demo查詢，準備標準答案

---

## 📅 時間安排 (週末2天)

### 週六 (Day 1)
- 上午: Steps 1-2 (UI切換 + Demo資料準備)
- 下午: Step 3 (API端點)
- 晚上: 測試和除錯

### 週日 (Day 2)
- 上午: Step 4 (前端整合)
- 下午: Step 5 (測試) + 視覺優化
- 晚上: Demo演練和準備

### 週一早上
- 最終檢查
- Demo環境準備
- 備份方案確認

---

## 💡 Demo 話術要點

1. **開場**: "我們開發了創新的Skill-Based架構，將相關文檔組織成技能單元"

2. **展示流程**:
   - 展示傳統File模式的限制
   - 切換到Skill模式
   - 選擇AI研究Skill
   - 查詢"深度學習的最新進展"
   - 展示整合的結果

3. **技術亮點**:
   - "使用並行搜尋，性能提升3-5倍"
   - "完全隔離的雙架構設計"
   - "支援20-100個文件的大型Skill"

4. **未來規劃**:
   - "下一階段將實現主索引優化，性能再提升10倍"
   - "計劃加入Skill自動生成和管理功能"

---

## 🔧 緊急修復指令

```bash
# 如果Demo當機
./scripts/emergency_restart.sh

# 如果資料損壞
./scripts/restore_demo_data.sh

# 如果搜尋太慢
export SKILL_FILE_LIMIT=10  # 限制文件數量
```

---

## ✅ 最終確認

**記住**:
1. Demo成功 > 完美實現
2. 穩定運行 > 性能極致
3. 視覺效果 > 程式碼品質
4. 用戶體驗 > 技術細節

**Demo後立即**:
- 收集反饋
- 記錄問題
- 規劃重構

---

*最後更新: 2025-11-25*
*Demo日期: 下周一、二*
*策略: Easy-to-Achieve First!*