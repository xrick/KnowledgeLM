<!-- claudedocs/Analysis_LLM 回答說看不到用戶選擇的文件.md -->
<!-- claudedocs/ANALYSIS_LLM_NOT_SEEING_FILES.md -->
# Analysis: LLM 回答說看不到用戶選擇的文件

## 問題描述

**用戶報告**: 上傳並選擇了兩個 PDF 文件，但系統回答說看不到文件。

**LLM 回答**:
```
對不起，但似乎有一些誤解。你所提到的「使用者點擊了以下文獻」並沒有在我的視野中顯現。
我目前只處於文本模式，無法直接查看或引用外部文件中的內容。
如果你能提供這些文章的大概內容，我將很樂意幫助您解釋它們的主要內容和討論主題。
```

## 截圖分析

### 觀察到的事實

1. **文件已正確選擇** ✓
   - 左側邊欄顯示兩個 PDF 已勾選
   - Back_propagation_Appli... ✓
   - 2021_OpenAI_Learning T... ✓

2. **系統處理正常** ✓
   - Console 顯示完整的 5-phase pipeline
   - `context_count: 7` - 檢索了 7 個 context chunks
   - `expanded_questions: Array(2)` - Query 擴展成 2 個子問題
   - Streaming 正常完成

3. **用戶的 Query**:
   ```
   "歡迎使用 DocAI 系統，這裡可以上傳您的文件並進行智慧問答"
   ```
   - 這是系統歡迎訊息，**不是一個問題**

4. **LLM 的誤解**:
   - LLM 回答提到"你所提到的「使用者點擊了以下文獻」"
   - 這個措辭不在用戶當前的 query 中
   - 表示可能來自 **chat history** 或 **context 中的內容**

## 根本原因分析

### 可能的原因

#### 1. **用戶的 Query 不是真正的問題** (最可能)

**證據**:
- 用戶輸入: "歡迎使用 DocAI 系統，這裡可以上傳您的文件並進行智慧問答"
- 這是陳述句，不是疑問句
- 沒有明確詢問文件相關的問題

**系統行為**:
- 檢索服務嘗試找到相關 context (找到了 7 個 chunks)
- 但這些 chunks 可能與"歡迎訊息"無關
- LLM 基於不相關的 context 給出了困惑的回答

**解決方案**: 用戶需要提出具體問題，例如：
- "請總結這兩份文件的核心內容"
- "這兩份文件討論了什麼主題？"
- "Back propagation 和 OpenAI Learning 有什麼關聯？"

#### 2. **Chat History 中的誤導信息**

**證據**:
- LLM 提到"你所提到的「使用者點擊了以下文獻」"
- 這個表述不在當前 query 中

**可能性**:
- 之前的對話中用戶提到了"點擊文獻"
- Chat history 被傳遞給 LLM
- LLM 基於 history 回答，而不是當前 context

**驗證方法**:
- 檢查 `session_id: session_1762335444937_wz2hd3r` 的 chat history
- 查看是否有之前的對話

#### 3. **Context 質量問題** (較不可能)

**證據**:
- `context_count: 7` 表示檢索了 7 個 chunks
- 但 chunks 的相關性未知

**可能性**:
- 檢索到的 7 個 chunks 與用戶的"歡迎訊息"無關
- LLM 看到 context，但認為不相關，所以說"看不到"

**驗證方法**:
- 記錄並檢查實際檢索到的 context chunks 內容
- 確認是否與用戶選擇的兩個 PDF 相關

#### 4. **LLM Model 能力限制** (較不可能)

**使用的 Model**: `phi4-mini:3.8b`

**可能問題**:
- 小型 model 可能對複雜的 system prompt 遵循度不足
- 可能忽略了 system prompt 中的指示
- 可能無法正確理解 RAG context 的用途

**驗證方法**:
- 使用更大的 model 測試（如 phi4:14b 或 llama3:8b）
- 簡化 system prompt
- 增強 context 的標記（例如更明顯的分隔符）

## 系統設計檢查

### System Prompt 設計 ✅ (正確)

**檔案**: `app/Services/prompt_service.py:30-50`

```python
SYSTEM_PROMPT_TEMPLATE = """你是一位專業的文檔問答助手。

**核心原則：下方的「上下文」來自用戶在側邊欄（sidebar）中勾選的文檔，
用戶嚴格要求你參考的資料。**

回答策略：
1. **優先引用文檔**：回答時應優先使用下方上下文中的信息
2. **智能補充說明**：可以使用你的知識，但要明確區分文檔內容和補充說明
3. **誠實評估**：如果文檔中沒有相關信息，明確說明
4. **準確性優先**：不要編造文檔中不存在的內容

---
[用戶勾選的文檔內容]
{context}
---
```

**評估**: ✅ 設計良好，明確告訴 LLM context 的來源和用途

### Context Assembly ✅ (正確)

**檔案**: `app/Services/prompt_service.py:136-155`

```python
def _assemble_context(self, context_chunks: List[str]) -> str:
    if not context_chunks:
        return "[無可用上下文]"

    context_str = "\n\n".join([
        f"[文檔片段 {i+1}]\n{chunk}"
        for i, chunk in enumerate(context_chunks)
    ])

    return context_str
```

**評估**: ✅ 正確組裝 context，有清晰的分隔符

### Retrieval Service (需驗證)

**檢索了 7 個 chunks** 但質量未知

**需要驗證**:
1. 這 7 個 chunks 是否來自用戶選擇的兩個 PDF？
2. Chunks 的相關性評分如何？
3. 是否正確使用了 `file_ids` 進行過濾？

## 建議的診斷步驟

### 1. 立即測試 - 使用具體問題

**測試用例**:
```
選擇相同的兩個 PDF
輸入具體問題："請總結這兩份文件的核心內容"
觀察回答是否改善
```

### 2. 啟用調試日誌

**修改位置**: `app/Services/prompt_service.py:133`

```python
logger.info(f"Built RAG prompt with {len(context_chunks)} context chunks")
logger.debug(f"Context preview: {context_str[:500]}...")  # 添加這行
logger.debug(f"Final messages: {messages}")  # 添加這行
```

**檢查**:
```bash
tail -f logs/server.log | grep -A 5 "Context preview"
```

### 3. 檢查 Chat History

**查詢數據庫**:
```python
# 檢查 session_id 的 history
session_id = "session_1762335444937_wz2hd3r"
# 查看是否有之前的對話導致誤解
```

### 4. 驗證 File IDs 過濾

**檢查位置**: `app/Services/retrieval_service.py`

確認檢索時是否正確使用了 `file_ids` 參數來過濾只從選擇的 PDF 中檢索。

### 5. 測試不同的 LLM Model

**嘗試**:
- phi4:14b (更大更聰明)
- llama3:8b (更好的指令遵循)
- qwen2.5:7b (中文優化)

## 推薦的修復方案

### 短期方案 (用戶側)

**1. 使用具體問題而非陳述句**

❌ 錯誤示例:
```
"歡迎使用 DocAI 系統，這裡可以上傳您的文件並進行智慧問答"
```

✅ 正確示例:
```
"請總結這兩份文件的核心內容"
"這兩份文件討論了什麼主題？"
"請比較 Back propagation 和 OpenAI Learning 的異同"
```

**2. 開始新會話**

如果 chat history 包含誤導信息：
- 點擊"新增來源"按鈕
- 開始全新的對話
- 提出明確的問題

### 中期方案 (系統改進)

**1. 增強 Context 可見性**

修改 system prompt，使 context 更明顯：

```python
SYSTEM_PROMPT_TEMPLATE = """你是一位專業的文檔問答助手。

**重要：下方用 === 包圍的內容是用戶在側邊欄勾選的文檔內容。
這些是用戶嚴格要求你參考的資料。你必須基於這些內容回答問題。**

===== 用戶勾選的文檔內容開始 =====
{context}
===== 用戶勾選的文檔內容結束 =====

請仔細閱讀上方的文檔內容，並基於這些內容回答用戶的問題。
```

**2. 添加 Context 存在性檢查**

```python
# 在 build_rag_prompt 中添加
if not context_chunks:
    logger.warning("No context chunks provided - user may not have selected any files")
    # 返回提示用戶選擇文件的 prompt
```

**3. 記錄完整 Prompt 用於調試**

```python
logger.debug(f"Complete system prompt:\n{system_prompt}")
logger.debug(f"User query: {query}")
logger.debug(f"Chat history length: {len(chat_history) if chat_history else 0}")
```

### 長期方案 (架構改進)

**1. Query 驗證**

在處理前驗證 query 是否為有效問題：
- 檢測疑問詞
- 檢測疑問句式
- 如果是陳述句，提示用戶輸入問題

**2. Context 質量評估**

在檢索後評估 context 相關性：
- 計算 relevance score
- 如果所有 chunks score < threshold，警告用戶
- 建議用戶重新表述問題或選擇其他文件

**3. Prompt 優化針對小型 Model**

為 phi4-mini 等小型 model 使用簡化的 prompt：
- 更簡潔的指示
- 更清晰的格式標記
- 減少複雜的策略說明

## 總結

**最可能的原因**: 用戶輸入的是陳述句而非問題

**立即行動**:
1. 提示用戶使用具體問題重新測試
2. 觀察使用真實問題後的回答質量

**需要驗證**:
1. Chat history 是否包含誤導信息
2. 檢索到的 7 個 chunks 的實際內容和相關性
3. File IDs 過濾是否正確工作

**系統改進優先級**:
1. 🔴 高優先級: 添加調試日誌查看實際 context
2. 🟡 中優先級: 增強 system prompt 的清晰度
3. 🟢 低優先級: Query 驗證和 context 質量評估

---

**建議下一步**: 請用戶使用具體問題重新測試，例如 "請總結這兩份文件的核心內容"，並觀察回答是否改善。
