具體實作建議
您可以修改 app/Services/iterative_query_expansion_service.py 中的 ROUND1_EXPANSION_PROMPT 與解析邏輯。

1. 修改 Prompt Template

將原本的 Prompt 修改為要求 LLM 輸出明確的 intent_category：

Python

# app/Services/iterative_query_expansion_service.py

## modify prompt
    ROUND1_EXPANSION_PROMPT = """你是一位專業的RAG查詢優化專家與意圖分析師。
[原始查詢]
{original_query}

[任務]
1. 分析用戶的原始意圖，將其分類為以下之一：
   - "summary": 用戶想要獲取文件摘要、大意或總結 (例如：這篇文章在說什麼？)
   - "multi_file_compare": 用戶想要比較多份文件或分別了解多份文件 (例如：比較這兩年份的財報)
   - "qa": 用戶針對特定細節提問 (例如：2023年的營收是多少？)
   - "general": 與文件無關的一般閒聊
2. 生成 {expansion_count} 個擴展查詢... (保留原有的擴展邏輯)

請以 JSON 格式回應：
{{
  "intent_category": "summary" | "multi_file_compare" | "qa" | "general",
  "intent_reasoning": "判斷理由...",
  "expanded_queries": [ ... ],
  "original_intent": "..."
}}
"""
2. 修改解析邏輯

接著，修改 _expand_round1 或新增一個方法來提取這個意圖，取代原本的關鍵字比對。

Python

# app/Services/iterative_query_expansion_service.py 的 _expand_round1 方法附近
```
    async def _expand_round1(self, query: str) -> dict: # 回傳型別可能需要調整以包含意圖
        # ... (LLM 呼叫代碼不變) ...
        
        try:
            # ... (取得回應) ...
            result = self._parse_json_response(llm_output)
            
            # 提取 LLM 判斷的意圖
            detected_intent = result.get("intent_category", "qa")
            
            # 您可以將此意圖存入 ExpansionResult 的 metadata 中
            # 或者回傳一個包含意圖與查詢的物件
            
            # ... (原本建立 ExpandedQuery 物件的邏輯) ...
```python
3. 更新對外接口

您原本的 get_query_metadata 方法 是透過關鍵字判斷。建議將流程改為：

在 chat.py 的 Phase 1 中，先呼叫 LLM 進行擴展（同時取得意圖）。

根據 LLM 回傳的 intent_category 來決定是否要走 overview_service 的 Shortcut 路徑（原本的 Summary Shortcut）。

優點分析：

語意理解：LLM 能理解「請分析兩者的異同」屬於 multi_file_compare，即使沒有命中硬編碼關鍵字。

零額外延遲：因為您本來就要做 Query Expansion，這只是在同一次 LLM 呼叫中多要一個欄位，不會增加 HTTP 請求次數。

彈性：您可以隨時在 Prompt 中增加新的意圖類別（例如 translation, explanation），而不需要維護繁瑣的關鍵字列表。

缺點與配套：

如果使用者選擇「關閉 Query Expansion (enable_expansion=False)」，這個機制就會失效。

配套措施：如果使用者關閉擴展，您可以保留原本的關鍵字偵測作為 Fallback，或者針對未開啟擴展的請求，使用一個極輕量模型（如 gpt-3.5-turbo 或 haiku）專門做一次快速的意圖分類。

這會比目前的 Hard-code 方式更符合 "AI-Native" 的設計原則。