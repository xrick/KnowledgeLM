# Debug Testing Guide - LLM 看不到文件問題

## 系統狀態

✅ **已完成的修復**:
1. httpx streaming error 修復
2. SSE line ending 修復
3. LLM URL auto-correction 修復
4. 調試日誌已啟用 (LOG_LEVEL=DEBUG)

✅ **調試功能已添加**:
1. Prompt Service - 記錄 context chunks 和 system prompt preview
2. Retrieval Service - 記錄檢索到的 chunks 和 file_ids
3. 完整的 DEBUG level logging 已啟用

## 測試步驟

### 第 1 步：準備測試

1. **確認系統運行**:
   ```bash
   curl -s http://localhost:8000/api/health
   ```
   應該返回 `{"status":"healthy"}`

2. **清空舊的 logs**:
   ```bash
   > logs/server.log  # 清空日誌以便更容易找到新的測試記錄
   ```

### 第 2 步：執行測試

1. **訪問** http://localhost:8000

2. **上傳兩個 PDF 文件**
   - 確認上傳成功（綠色勾勾）
   - 確認兩個文件都有勾選（checkbox checked）

3. **點擊"新增來源"按鈕** (開始新會話，避免 chat history 干擾)

4. **提出具體問題**（非常重要！）

   ✅ **好的問題示例**:
   ```
   "請總結這兩份文件的核心內容"
   "這兩份文件討論了什麼主題？"
   "請列出這兩份文件的主要觀點"
   ```

   ❌ **避免的輸入**:
   ```
   "歡迎使用 DocAI 系統..." (陳述句)
   "Hello" (問候語)
   "test" (測試用語)
   ```

5. **觀察回答**:
   - 是否正確引用文件內容？
   - 是否還說"看不到文件"？
   - Streaming 是否正常？

### 第 3 步：收集診斷信息

執行以下命令收集調試信息：

```bash
# 1. 檢查調試日誌
tail -200 logs/server.log > debug_output.txt

# 2. 檢查 Prompt 相關日誌
grep -A 10 "Built RAG prompt" logs/server.log >> debug_output.txt
echo "---" >> debug_output.txt

# 3. 檢查 Context 預覽
grep "Context chunks count\|First context chunk\|Context string length" logs/server.log >> debug_output.txt
echo "---" >> debug_output.txt

# 4. 檢查 Retrieval 詳情
grep "Retrieval details\|Chunk [0-9]:" logs/server.log >> debug_output.txt
echo "---" >> debug_output.txt

# 5. 檢查 System Prompt 預覽
grep "System prompt preview" logs/server.log >> debug_output.txt
echo "---" >> debug_output.txt

# 6. 檢查 User Query
grep "User query:" logs/server.log | tail -5 >> debug_output.txt

echo "✅ Debug output saved to debug_output.txt"
```

### 第 4 步：分析 debug_output.txt

查看 `debug_output.txt` 文件，檢查：

1. **Context Chunks**:
   ```
   Context chunks count: X  # 應該 > 0
   First context chunk preview: ...  # 應該包含文件內容
   Context string length: YYYY chars  # 應該 > 0
   ```

2. **File IDs**:
   ```
   Retrieval details - file_ids: ['file_xxx', 'file_yyy']  # 應該有兩個 file_ids
   ```

3. **Retrieved Chunks**:
   ```
   Chunk 1: file_id=file_xxx, preview=...  # 確認 file_id 正確
   Chunk 2: file_id=file_yyy, preview=...
   ```

4. **System Prompt**:
   ```
   System prompt preview: 你是一位專業的文檔問答助手...  # 確認包含 context
   ```

5. **User Query**:
   ```
   User query: 請總結這兩份文件的核心內容  # 確認是有效問題
   ```

## 問題診斷矩陣

### 情況 1: Context chunks count = 0

**症狀**: `Context chunks count: 0`

**可能原因**:
- Vector store 中沒有該 file_id 的數據
- Embedding 失敗
- Retrieval service 錯誤

**檢查**:
```bash
# 檢查 embedding 狀態
grep "Embeddings generated" logs/server.log | tail -5

# 檢查 vector store 錯誤
grep "Store not found\|Error searching in store" logs/server.log | tail -10
```

**解決方案**:
- 重新上傳文件
- 檢查 Milvus 服務是否運行
- 查看完整 logs 尋找 embedding 錯誤

### 情況 2: Context chunks > 0 但 LLM 說看不到

**症狀**:
- `Context chunks count: 7`
- Context preview 有內容
- 但 LLM 回答 "我看不到文件"

**可能原因**:
- Context 與問題不相關
- Model 能力不足 (phi4-mini:3.8b 太小)
- System prompt 沒有被正確理解

**檢查 Context 相關性**:
```bash
# 查看實際檢索到的 chunks
grep -A 1 "Chunk [0-9]:" logs/server.log | tail -20
```

檢查 chunks 是否與用戶問題相關。

**解決方案 A - 更換 Model**:
```bash
# 下載更大更強的 model
ollama pull phi4:14b

# 或使用中文優化的 model
ollama pull qwen2.5:7b
```

然後在 `.env` 中修改:
```
DEFAULT_LLM_MODEL=phi4:14b
# 或
DEFAULT_LLM_MODEL=qwen2.5:7b
```

**解決方案 B - 增強 System Prompt**:

暫時測試用，可以嘗試更明確的 prompt（需要修改代碼）。

### 情況 3: File IDs 不正確

**症狀**:
- `Retrieval details - file_ids: []` (空)
- 或 file_ids 與選擇的文件不符

**可能原因**:
- Frontend 沒有正確傳遞 file_ids
- Request payload 格式錯誤

**檢查 Frontend**:
開啟 Browser Developer Tools → Network tab → 查看實際發送的請求:
```json
{
  "query": "...",
  "session_id": "...",
  "file_ids": ["file_xxx", "file_yyy"],  // 確認這裡有兩個 IDs
  "top_k": 10
}
```

**解決方案**:
- 確保文件已勾選（checkbox checked）
- 檢查 JavaScript console 是否有錯誤
- 查看 `[DocAI] Selected file IDs:` log 在 console

### 情況 4: Chunks 來自錯誤的文件

**症狀**:
```
Retrieval details - file_ids: ['file_aaa', 'file_bbb']
Chunk 1: file_id=file_ccc, preview=...  # ❌ 不在請求的 file_ids 中
```

**可能原因**:
- Retrieval service bug
- Vector store metadata 錯誤

**需要深度調試**: 這種情況需要檢查 retrieval_service.py 的實現。

## 預期的正常輸出

正常情況下，`debug_output.txt` 應該包含類似這樣的內容：

```
Built RAG prompt with 7 context chunks and 3 messages

Context chunks count: 7
First context chunk preview: Back propagation is a fundamental algorithm in neural networks... (前150字符)
Context string length: 5234 chars

System prompt preview: 你是一位專業的文檔問答助手。

**核心原則：下方的「上下文」來自用戶在側邊欄（sidebar）中勾選的文檔，用戶嚴格要求你參考的資料。**

回答策略：
1. **優先引用文檔**：回答時應優先使用下方上下文中的信息，並明確標註引用來源
...

User query: 請總結這兩份文件的核心內容

Retrieval details - file_ids: ['file_1762332584_1cc01351_0a7a9601', 'file_1762333131_35578167_880e354f']

Chunk 1: file_id=file_1762332584_1cc01351_0a7a9601, preview=Transformers have become the dominant architecture in deep learning...
Chunk 2: file_id=file_1762333131_35578167_880e354f, preview=Agentic context engineering refers to...
Chunk 3: file_id=file_1762332584_1cc01351_0a7a9601, preview=Layer normalization is a technique...
```

## 測試完成後

1. **如果問題解決**:
   - 記錄是什麼原因（更換 model？更好的問題？）
   - 可以將 LOG_LEVEL 改回 INFO 以提高性能

2. **如果問題仍然存在**:
   - 將 `debug_output.txt` 提供給開發者
   - 提供截圖（包含 console messages）
   - 說明測試時使用的具體問題

## 快速命令參考

```bash
# 重啟系統
./stop_system.sh && sleep 2 && ./start_system.sh

# 清空日誌
> logs/server.log

# 實時查看日誌
tail -f logs/server.log

# 查看 DEBUG 訊息
tail -f logs/server.log | grep DEBUG

# 搜尋特定關鍵字
tail -100 logs/server.log | grep "Context chunks"

# 檢查系統健康
curl http://localhost:8000/api/health

# 列出可用的 models
ollama list

# 查看當前 LOG_LEVEL
grep LOG_LEVEL .env
```

## 聯絡開發者

如果需要進一步協助，請提供：

1. `debug_output.txt` 文件內容
2. 瀏覽器 console screenshot
3. 您使用的具體問題（query）
4. 兩個 PDF 文件的名稱
5. 使用的 LLM model (檢查 `.env` 中的 `DEFAULT_LLM_MODEL`)

---

**文件版本**: 1.0
**建立日期**: 2025-11-05
**用途**: 診斷 "LLM 看不到用戶選擇的文件" 問題
