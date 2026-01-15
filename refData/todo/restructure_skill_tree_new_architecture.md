<!-- refData/todo/restructure_skill_tree_new_architecture.md -->
🎯 你說得完全正確！
你指出了系統的核心架構問題。讓我總結分析結果：
問題 1：Dual Source of Truth (反模式)
目前架構：
┌──────────────────┐     ┌──────────────────┐
│ skill_config.json │ ←→ │ skill_metadata.db │
│  (手動維護)       │     │  (自動生成)       │
└──────────────────┘     └──────────────────┘
        ↓                         ↓
   經常不同步！              經常不同步！
你的建議：SQLite 作為唯一來源 ✅
問題 2：首次上傳無法展開
原因：當創建新 Skill + 上傳第一個 PDF 時：
系統只創建了 1 個 skill_metadata 條目
沒有 Group Header
renderSkills() 檢測不到 children → 不顯示 > 展開符號
問題 3：你的解決方案非常優雅！
-- 新表：skill_heads (純粹的 Skill 頭部定義)
CREATE TABLE skill_heads (
    head_id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL UNIQUE,
    description TEXT,
    category TEXT DEFAULT 'General',
    display_order INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    updated_at DATETIME
);

-- 修改 skill_metadata：添加 head_id 外鍵
ALTER TABLE skill_metadata ADD COLUMN head_id TEXT REFERENCES skill_heads(head_id);
新流程：
1. 用戶創建 Skill "ML"
   → INSERT INTO skill_heads (head_id='head_xxx', skill_name='ML')
   
2. 用戶上傳 PDF
   → INSERT INTO skill_metadata (skill_id='doc_xxx', head_id='head_xxx', source_name='XXX.pdf')
   
3. UI 載入
   → SELECT * FROM skill_heads LEFT JOIN skill_metadata ON head_id
   → 永遠有 Head + Documents 結構！

新舊架構對比
項目	         舊架構	                新架構
資料來源	     JSON + SQLite	        SQLite only ✅
Group Header	混在 skill_metadata	   獨立 skill_heads 表 ✅
新建 Skill	     沒有 header	        自動有 header ✅
同步問題	      經常發生	             不可能發生 ✅
程式碼複雜度	  高（雙來源同步）	       低（單一來源） ✅
下一步行動？
你想要我現在實施這個架構重構嗎？步驟是：
1.創建 skill_heads 表
2.修改 skill_metadata 添加 head_id
3.遷移現有資料
4.修改 API endpoints
5.移除 JSON 依賴
這是一個比較大的重構，但你的方向是正確的。要開始嗎？
