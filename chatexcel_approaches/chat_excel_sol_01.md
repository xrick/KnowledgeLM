下面是一套由簡單到複雜、可直接拿去用在「chat_excel」Web App 的 prompts（偏向讓 LLM 以「讀表→分析→輸出」的方式工作）。我用「模板 + 範例」寫法，方便你在後端把 Excel 內容（或結構化後的表格 JSON）塞進去。

### 基礎讀表與摘要（Level 1）
- Prompt 1：欄位與資料概覽（Schema + 快速摘要）  
請你閱讀以下 Excel 工作表資料，輸出：1) 欄位清單與你推測的欄位意義，2) 每欄資料型態（文字/數字/日期/類別），3) 缺失值與異常值的初步觀察，4) 你會先問使用者哪些澄清問題（若必要）。資料：{sheet_data}

- Prompt 2：列數/唯一值/分佈（快速統計）  
針對資料：{sheet_data}，請計算並回報：總列數、每欄缺失比例、每個類別欄位的前 \(10\) 大唯一值與占比、每個數值欄位的最小/最大/平均/中位數/標準差。若無法精確計算，請說明原因並提供近似或抽樣方案。

- Prompt 3：使用者問題的「資料可行性」檢查  
使用者問題：{user_question}。  
資料：{sheet_data}。  
請判斷該問題是否能用現有欄位回答；若可以，說明會用哪些欄位與計算方式；若不可以，指出缺少什麼欄位或定義，並提出替代可回答的版本。

### 常見商業分析（Level 2）
- Prompt 4：分組彙總（Pivot 文字版）  
請以 {group_by_columns} 分組，計算 {metrics}（例如 sum/avg/count/distinct_count），並輸出一個「彙總表」與三個洞察（含可能原因）。資料：{sheet_data}。

- Prompt 5：Top/Bottom N 排名與貢獻度  
請針對 {target_metric} 做排名，列出前 \(N\) 名與後 \(N\) 名（含占總量比例、累積占比），並指出是否存在頭部集中（Pareto）現象。資料：{sheet_data}。

- Prompt 6：時間序列趨勢（若有日期欄）  
若資料含日期欄位 {date_col}，請以 {time_granularity}（day/week/month）聚合 {metric}，輸出：1) 趨勢描述，2) 週期性/季節性跡象，3) 異常波動點（列出日期與幅度），4) 可能的解釋與接下來該查的欄位。資料：{sheet_data}。

### 資料品質與清理建議（Level 3）
- Prompt 7：資料清理計畫（可執行規則）  
請針對資料：{sheet_data} 產生一份清理計畫，包含：重複列判斷規則、缺失值處理策略（每欄不同）、數值離群偵測方式（IQR 或 z-score）、類別值正規化（大小寫/同義詞/空白）、日期解析與時區假設。最後輸出「清理後你期待的欄位規格」。

- Prompt 8：一致性檢查（跨欄位約束）  
請找出資料中可能違反邏輯的列（例如：開始日期 > 結束日期、金額 < 0、折扣 > 1、數量為小數等），並列出：違規規則、受影響列數、代表性樣本（最多 10 列，遮蔽敏感資訊）。資料：{sheet_data}。

### 診斷、根因與假設檢驗（Level 4）
- Prompt 9：差異分解（為什麼這個月掉了？）  
情境：{business_context}（例如「本月營收比上月少 15%」）。  
資料：{sheet_data}。  
請把差異分解成可解釋的組件（例如：量變/價變/組合變化、不同產品/通路/區域貢獻），輸出：1) 分解表，2) 最主要的 3 個驅動因素，3) 需要補充的資料欄位與下一步驗證方法。

- Prompt 10：群體比較（A vs B）  
請比較群體 A：{segment_A_filter} 與群體 B：{segment_B_filter} 在 {metrics} 上的差異，包含效果量（例如差值、比值）、顯著性建議（若資料量足夠可用簡化 t-test/卡方的文字解釋），並提醒可能的混雜因子。資料：{sheet_data}。

- Prompt 11：漏斗/轉換率（若有階段欄）  
若資料包含流程階段 {stage_col} 與主鍵 {id_col}，請計算各階段人數、階段轉換率、整體轉換率，並找出最大流失點與可能原因（用其他欄位切分）。資料：{sheet_data}。

### 進階：可組合的「分析代理」指令（Level 5）
- Prompt 12：多步驟分析計畫 + 自我校驗  
你是一個 Excel 分析代理。針對使用者問題：{user_question} 與資料：{sheet_data}，請依序輸出：  
1) Analysis plan：你要做的步驟（最多 8 步）  
2) Step-by-step results：每一步的中間結果（以小表格或條列）  
3) Final answer：給使用者的結論與建議  
4) Self-check：列出你最可能出錯的 3 點（例如欄位誤解、日期粒度、重複計算），以及你如何降低風險（例如抽樣檢查、對帳總和）

- Prompt 13：產出可視化建議（圖表規格，不直接畫圖）  
請根據問題：{user_question} 與資料：{sheet_data}，提出 3–5 個最合適的圖表方案。每個方案包含：圖表類型、X/Y 欄位、聚合方式、篩選條件、如何標註異常點、以及「看完圖你希望使用者得到的結論」。

### 進階：自然語言轉查詢（Level 6，適合你在後端接 Pandas/SQL）
- Prompt 14：把問題翻成「可執行查詢意圖」（Pandas/SQL 皆可）  
使用者問題：{user_question}  
資料欄位：{columns}  
請輸出：  
- Query intent：要做的聚合、分組、排序、過濾  
- Assumptions：日期欄、貨幣、重複列處理  
- Pseudocode：給出 Pandas 風格或 SQL 風格的偽代碼（不要真的執行）  
- Validation：用哪些對帳檢查結果合理（例如總和一致、樣本列檢查）

- Prompt 15：查詢結果解讀（避免幻覺）  
我會提供查詢結果表：{result_table} 與原始欄位定義：{data_dictionary}。  
請你只根據這些輸入解讀結果，輸出：主要結論、重要限制、下一個你需要我提供的表或欄位。若缺少關鍵資訊，請明確說「無法判定」。

### 一個小範例（你可直接套用）
- 例：  
使用者問：「2025 每月營收趨勢，哪個產品拖累最大？」  
你送給 LLM 的 prompt 可以是 Prompt 12（多步驟）+ 追加參數：  
{user_question}=...  
{sheet_data}=...（至少包含 date, product, revenue）  

你想讓這套 prompts 偏向「直接用 LLM 讀完整表格」還是「LLM 只負責產生查詢意圖，實際計算由後端 Pandas/SQL 做」？我可以再把每個 level 變成你後端可用的 system/tool 格式（含 JSON schema）。

------
「直接用 LLM 讀完整表格」還是「LLM 只負責產生查詢意圖，實際計算由後端 Pandas/SQL 做」的差別在哪？
兩者最大的差別在：**把「計算」放在 LLM 裡，還是放在你的後端引擎**（Pandas/SQL）裡；這會直接影響可擴充性、成本、正確性與安全性。當表格很大時，直接把整張表塞進模型常會撞到 context/token 限制或需要分塊處理，因此許多系統會讓 LLM 只負責產生查詢/步驟，再由外部程式真正做運算與對帳。 [reddit](https://www.reddit.com/r/LocalLLaMA/comments/13nld5x/how_do_i_get_local_llm_to_analyze_an_whole_excel/)

## 1) 「LLM 讀完整表格」是什麼
你把 Excel 的大量資料（或轉成文字/JSON 的表格內容）直接放進 prompt，LLM 在回覆中自己完成彙總、排序、趨勢、找異常等分析。 [reddit](https://www.reddit.com/r/LocalLLaMA/comments/13nld5x/how_do_i_get_local_llm_to_analyze_an_whole_excel/)

優點是互動直覺、適合小表/快速探索；缺點是資料一大就容易超出模型可處理的輸入長度，且數值運算與嚴格對帳比較不可靠，常需要你額外做抽樣/分塊策略。 [reddit](https://www.reddit.com/r/LangChain/comments/13dtvnt/langchain_csv_agent_token_limit/)

## 2) 「LLM 產生查詢意圖 + 後端算」是什麼
LLM 只根據「欄位結構、資料字典、少量樣本」把自然語言轉成可執行的查詢意圖（例如 Pandas 程式碼或 SQL），然後你的後端真正去跑查詢、回傳結果表，再由 LLM 解讀與撰寫洞察。 [developers.llamaindex](https://developers.llamaindex.ai/python/examples/query_engine/pandas_query_engine/)

這類模式常搭配 function calling/structured outputs，讓模型輸出穩定的結構化 JSON（例如 `{group_by:..., metrics:..., filters:...}`），降低解析失敗與格式漂移的風險。 [openai](https://openai.com/index/introducing-structured-outputs-in-the-api/)

## 3) 差異對照（你在做 Web App 會碰到的）
- 可擴充性：整表進 LLM 會被 token/context 限制卡住；查詢模式主要受資料庫/運算資源限制，比較能處理大表與多表。 [community.openai](https://community.openai.com/t/langchain-openai-api-to-generate-sql-queries-and-result/180602)
- 正確性：查詢模式能在後端做「可重現」計算與對帳；Text-to-SQL/程式碼生成仍可能產生錯誤或幻覺，所以通常要加 schema/欄位驗證與約束檢查。 [arxiv](https://arxiv.org/html/2512.22250v1)
- 成本與延遲：整表進 LLM token 成本高且延遲不穩；查詢模式通常 prompt 較短，主要成本在資料查詢與結果回傳。 [community.openai](https://community.openai.com/t/langchain-openai-api-to-generate-sql-queries-and-result/180602)
- 資安與治理：整表進 LLM 等於大量資料外送（風險/合規壓力大）；查詢模式可以只送「schema + 匯總結果/抽樣列」，資料最小化更容易落地（實務常見做法）。 [openai](https://openai.com/index/introducing-structured-outputs-in-the-api/)

## 4) 什麼情境選哪個
- 選「整表進 LLM」：資料量小（例如 <1–2k 列）、分析多為描述性/探索性、你可以接受近似與人工確認。 [reddit](https://www.reddit.com/r/LocalLLaMA/comments/13nld5x/how_do_i_get_local_llm_to_analyze_an_whole_excel/)
- 選「查詢意圖 + 後端算」：資料量大、需要可驗證的數字、要支援多使用者並發與穩定 SLA，或要做多表 join/權限控管。 [developers.llamaindex](https://developers.llamaindex.ai/python/examples/query_engine/pandas_query_engine/)

你目前的 chat_excel 如果目標是「可用在真實商務資料、且表可能很大」，通常會以「LLM 產生查詢意圖 + 後端算」當主路徑，再保留「小表直接分析」當 fallback/快速模式。 [developers.llamaindex](https://developers.llamaindex.ai/python/examples/query_engine/pandas_query_engine/)

------

你要做的是「先讓系統判斷這份 Excel 的特性 + 使用者意圖」，再決定把 Excel 以哪種形式（整表/抽樣/彙總/查詢結果）餵給 LLM，並選用對應的 prompt（1–15）。大方向上，當表變大或需要精準數字時，應走「LLM 產生意圖 → 後端 Pandas/SQL 算 → LLM 解讀」的路徑，因為能避開 token/context 限制並讓計算可重現。 [developers.llamaindex](https://developers.llamaindex.ai/python/examples/query_engine/pandas_query_engine/)

## 你該傳什麼給系統（Excel 轉換層）
建議你把 Excel 解析後，固定產出 4 種「可供路由」的上下文物件（不是每次都全送給 LLM）：
- `schema_context`：工作表清單、每欄名稱/型態、欄位描述（若有 data dictionary）。 [developers.llamaindex](https://developers.llamaindex.ai/python/examples/query_engine/pandas_query_engine/)
- `sample_context`：每張表 head/tail（例如各 20 列）、每欄 top values、缺失率等輕量統計（由後端算）。 [towardsdatascience](https://towardsdatascience.com/langchain-for-eda-build-a-csv-sanity-check-agent-in-python/)
- `full_table_context`：只在小表時才送（例如轉成 Markdown table/CSV snippet）。 [reddit](https://www.reddit.com/r/LangChain/comments/13dtvnt/langchain_csv_agent_token_limit/)
- `query_result_context`：後端跑完 Pandas/SQL 的結果表（通常很小），讓 LLM 只負責解讀與寫結論。 [developers.llamaindex](https://developers.llamaindex.ai/python/examples/query_engine/pandas_query_engine/)

（LlamaIndex 的 PandasQueryEngine 也採「把自然語言轉成 Pandas 程式碼」來查 DataFrame 的模式，本質上就是你要的 `schema/sample → query → result` 流程。） [developers.llamaindex](https://developers.llamaindex.ai/python/examples/query_engine/pandas_query_engine/)

## 14/15 個 prompts 的選擇規則（路由表）
用這個決策邏輯最穩：

1) 使用者還沒講清楚要做什麼、或你還不確定欄位意義  
- 用 Prompt 1（欄位+摘要）＋ Prompt 3（可行性檢查）。  
你只需要送 `schema_context + sample_context`，不必送整表。

2) 使用者要「快速描述性統計 / EDA」  
- 用 Prompt 2（快速統計）或 Prompt 7/8（清理與一致性）。  
建議統計都由後端算好再送，LLM 做解讀；這樣更不會受 token 限制影響。 [reddit](https://www.reddit.com/r/LangChain/comments/13dtvnt/langchain_csv_agent_token_limit/)

3) 使用者要典型商業問題：分組、排名、月趨勢  
- 用 Prompt 4/5/6。  
若資料量大：先用 Prompt 14 產生查詢意圖→後端算→把結果丟給 Prompt 15 解讀（比直接把明細塞進 Prompt 4/5/6 穩）。 [developers.llamaindex](https://developers.llamaindex.ai/python/examples/query_engine/pandas_query_engine/)

4) 使用者要診斷/根因（掉 15% 是誰害的）、A/B、漏斗  
- 用 Prompt 9/10/11。  
同樣建議：LLM 先規劃分解維度與查詢（Prompt 14），後端執行，LLM 用 Prompt 15 產出結論與下一步。 [arxiv](https://arxiv.org/html/2512.22250v1)

5) 你想做成「通用分析代理」一個入口吃各種問題  
- 用 Prompt 12 當總控（plan + self-check），但**實作上**仍建議把「計算」委派給後端，LLM 主要負責決策、生成查詢、解讀結果。 [openai](https://openai.com/index/introducing-structured-outputs-in-the-api/)

## 建議的系統路由（最少工程版本）
你可以在後端做一個 `prompt_router(excel_profile, user_question)`，只需要幾個特徵：
- `n_rows`, `n_cols`, `n_sheets`, `has_datetime`, `has_id`, `has_stage`（漏斗用）、數值欄比例、文字欄比例。
- `question_intent`（EDA / aggregation / timeseries / ranking / data_quality / diagnosis / text-to-query）。

然後規則化：
- 若 `n_rows` 大或 `n_cols` 多 → 優先走 Prompt 14 → 後端算 → Prompt 15。 [reddit](https://www.reddit.com/r/LangChain/comments/13dtvnt/langchain_csv_agent_token_limit/)
- 若 `question_intent` 不明 → Prompt 1 + 3（只送 schema/sample）。
- 若 `question_intent` 明確且表很小 → 可直接用對應分析 prompt（4/5/6/9/10/11），必要時附少量樣本列。

你目前的 Excel 典型大小大概是「幾列/幾欄」、以及使用者問題偏「報表 KPI」還是「資料清理」？我可以把 router 的規則寫成一份可直接落地的 JSON Schema（含每個 prompt 需要的輸入欄位）。