# Strix Halo Query Fix - Testing Guide

## 🎯 Quick Test Steps

### Test 1: Correct Skill Selection (Should Work)

1. **啟動系統**:
   ```bash
   ./start_system.sh
   ```

2. **前往頁面**:
   ```
   http://localhost:8000/skill
   ```

3. **選擇正確的 Skill**:
   - 點擊左側技能樹
   - 展開 "📁 AMD"
   - 選擇 "📎 Strix Halo Engineering Interlock - February 2025 Released 1"

4. **執行查詢**:
   - 輸入: `strix halo`
   - 點擊搜尋

5. **預期結果** ✅:
   ```
   根據您的文檔，Strix Halo 是 AMD 的新一代處理器平台...

   參考來源：
   [Strix Halo Engineering Interlock - February 2025 Released 1-第12頁]
   [Strix Halo Engineering Interlock - February 2025 Released 1-第41頁]
   ...
   ```

---

### Test 2: Wrong Skill Selection (Should Show Suggestions)

1. **選擇錯誤的 Skill**:
   - 點擊左側技能樹
   - 選擇 "📁 大語言模型大全"

2. **執行查詢**:
   - 輸入: `strix halo`
   - 點擊搜尋

3. **預期結果** ✅:
   ```
   抱歉，我在您選擇的文檔「大語言模型大全」中沒有找到與「strix halo」相關的資訊。

   💡 建議：以下文檔可能包含相關內容：
     • 📁 AMD - Strix Halo Engineering Interlock - February 2025 Released 1 (67 chunks)

   請在左側技能樹中選擇相應的文檔重新搜尋。
   ```

4. **Follow-up Action**:
   - 根據建議，選擇 "📁 AMD" skill
   - 重新執行查詢
   - 應該成功檢索到內容

---

### Test 3: Multi-Skill Search

1. **選擇多個 Skills**:
   - 使用 checkbox 勾選:
     - ☑ AMD - Strix Halo...
     - ☑ 大語言模型大全

2. **執行查詢**:
   - 輸入: `strix halo`
   - 點擊搜尋

3. **預期結果** ✅:
   ```
   根據您的文檔，Strix Halo 是 AMD 的新一代處理器平台...

   📚 搜尋了 2 個知識庫

   參考來源：
   [Strix Halo Engineering Interlock - February 2025 Released 1-第12頁]
   ...
   ```

---

## 🐛 Troubleshooting

### Issue: Server Not Starting
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill existing process
pkill -f uvicorn

# Restart
./start_system.sh
```

### Issue: No Suggestions Shown
**Possible Causes**:
1. Query keyword too short (< 3 chars) - system ignores it
2. No matching skills in database
3. Backend error - check logs

**Solution**:
```bash
# Check logs
tail -f logs/app.log

# Test with longer keyword
Query: "strix halo engineering"
```

### Issue: Still Says "找不到"
**Check**:
1. ✅ Is AMD skill selected?
2. ✅ Is server restarted after fix?
3. ✅ Are FAISS indices present?

```bash
# Verify FAISS index
ls -lh data/faiss_indices/skills/skill_20251211_161308_48af4341_feb60e/

# Should show:
# index.faiss (268KB)
# index.pkl (62KB)
```

---

## 📊 Success Criteria

| Test | Expected | Status |
|------|----------|--------|
| Test 1: Correct Selection | ✅ Results with citations | ⏳ Pending |
| Test 2: Wrong Selection | ✅ Suggestions shown | ⏳ Pending |
| Test 3: Multi-Skill | ✅ Search both, find in AMD | ⏳ Pending |

---

## 🎓 Understanding the Fix

### Before Fix
```
Query "strix halo" with wrong skill
   ↓
No results found
   ↓
LLM: "抱歉，我沒有找到..."
   ↓
User confused 😕 (Which skill should I use?)
```

### After Fix
```
Query "strix halo" with wrong skill
   ↓
No results found
   ↓
System: Search all skills for keyword "strix" or "halo"
   ↓
Found: AMD - Strix Halo Engineering Interlock...
   ↓
Response: "抱歉，在當前文檔中找不到。💡 建議：AMD - Strix Halo..."
   ↓
User guided 😊 (Oh, I should use AMD skill!)
```

---

## 📝 Notes

- Suggestions are case-insensitive
- Keywords < 3 chars are ignored (avoid false positives)
- Max 3 suggestions shown (top matches)
- Suggestions ranked by keyword match count

---

*Testing Guide - Quick Reference*
*Last Updated: 2025-12-12*
