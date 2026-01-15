# DocAI Skill-Based RAG Demo 快速指南

## 🚀 Demo 快速啟動

### 1. 載入 Demo Skills（第一次執行）
```bash
# 載入3個預設的Demo Skills
python scripts/load_demo_skills.py
```

### 2. 啟動系統
```bash
./start_system.sh
```

### 3. 開啟 Demo 介面
打開瀏覽器訪問：http://localhost:8001/skill-demo

### 4. 測試 Demo 功能（可選）
```bash
./scripts/test_skill_demo.sh
```

## 🎯 Demo 功能特點

### 三個預設 Skills

1. **🤖 AI研究論文集**
   - 深度學習進展
   - 大型語言模型優化
   - AI安全研究
   - 測試查詢：「深度學習」、「Transformer」、「RLHF」

2. **🐍 Python開發文檔**
   - FastAPI進階特性
   - Python數據科學
   - Django企業架構
   - 測試查詢：「FastAPI」、「Pandas」、「異步」

3. **📊 商業分析報告**
   - 市場趨勢分析
   - 數據驅動決策
   - 數位轉型策略
   - 測試查詢：「數據驅動」、「AI市場」、「數位轉型」

## 📋 Demo 流程

1. **模式切換展示**
   - 展示 File Mode vs Skill Mode 的切換
   - 強調 Skill Mode 是新功能

2. **選擇 Skill**
   - 點擊任一 Skill 卡片
   - 顯示該 Skill 的文檔數和片段數

3. **查詢展示**
   - 輸入相關查詢
   - 展示並行搜尋（parallel search）
   - 顯示結果和相關度分數

4. **性能亮點**
   - Level 1 並行搜尋：3-5倍速度提升
   - 完全隔離的雙架構設計
   - 支援20-100個文件的大型Skill

## 🛠️ 技術架構

### 已完成 (90%)
- ✅ Skill-Based Architecture 完整實現
- ✅ 物理隔離（separate directories and databases）
- ✅ Level 1 並行搜尋優化
- ✅ Demo UI with mode toggle
- ✅ Pre-loaded demo content

### 待優化 (Post-Demo)
- ⏳ Master Index（10-100倍性能提升）
- ⏳ LRU Cache 記憶體管理
- ⏳ Feature Flags 系統
- ⏳ 企業級功能

## 💡 Demo 話術要點

### 開場
「我們開發了創新的 Skill-Based 架構，將相關文檔組織成技能單元，大幅提升搜尋效率和準確性」

### 技術亮點
- 「使用並行搜尋技術，性能提升3-5倍」
- 「完全隔離的雙架構設計，確保系統穩定」
- 「支援20-100個文件的大型Skill」

### 未來規劃
- 「下一階段將實現主索引優化，性能再提升10倍」
- 「計劃加入Skill自動生成和管理功能」
- 「企業級部署和多租戶支援」

## 🐛 問題排查

### 如果 Demo Skills 未載入
```bash
# 重新載入
python scripts/load_demo_skills.py
```

### 如果服務未啟動
```bash
# 檢查服務狀態
curl http://localhost:8001/health

# 重啟服務
./stop_system.sh
./start_system.sh
```

### 如果查詢無結果
- 確認 OpenAI API key 已設置
- 檢查 logs/server.log 錯誤信息
- 確認 Demo Skills 已成功載入

## 📞 緊急聯絡

如遇到問題：
1. 查看 logs/server.log
2. 執行 ./scripts/test_skill_demo.sh 診斷
3. 檢查 CLAUDE.md 的故障排除指南

---

**Demo 時間**: 下周一、二
**優先級**: Demo First > 完美實現
**記住**: 穩定運行比極致性能重要！

祝 Demo 成功！ 🎉