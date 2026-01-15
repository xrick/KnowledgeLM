📈 時間成本估算
設定	預估生成時間	LLM API 成本
目前 (1000 tokens)	~3-5 秒	低
選項 B (1500 tokens)	~5-8 秒	+50%
結論：如果你願意多等 2-3 秒，選項 B 會產生更完整的 overview。
/sc:explain 
```
max_token 和 overview_max_chars 各代表什麼意思 
```
📖 MAX_TOKENS vs OVERVIEW_MAX_CHARS 解釋
簡單比喻
想像你在寫一封信：
概念	比喻	參數
MAX_TOKENS	你最多可以寫幾個「單詞」	LLM 輸出限制
OVERVIEW_MAX_CHARS	信封最多能裝幾個「字母」	儲存/顯示限制
🔤 MAX_TOKENS = 1000
什麼是 Token？
Token 是 LLM 處理文字的最小單位，不等於字元或單詞：
┌─────────────────────────────────────────────────────────────────┐
│  英文範例: "Hello world"                                         │
│  → Tokens: ["Hello", " world"]  = 2 tokens                      │
│                                                                 │
│  中文範例: "你好世界"                                             │
│  → Tokens: ["你", "好", "世", "界"]  = 4 tokens (大約)           │
│                                                                 │
│  程式碼: "function getName()"                                    │
│  → Tokens: ["function", " get", "Name", "()"]  = 4 tokens       │
└─────────────────────────────────────────────────────────────────┘
Token 與字元的換算（約略）
語言	1 Token ≈
英文	4 字元
中文	1-2 字元
所以 MAX_TOKENS = 1000 大約等於：
英文：~4000 字元
中文：~1000-2000 字元
作用位置
response = await self.llm_client.get_chat_completion(
    messages=messages,
    temperature=0.3,
    max_tokens=MAX_TOKENS  # ← LLM 最多回應 1000 tokens
)
這是給 LLM 的指令：「你的回答不能超過 1000 tokens」
📏 OVERVIEW_MAX_CHARS = 2000
什麼是 Chars（字元）？
字元就是每一個字，包括空格和標點：
"你好世界" = 4 字元
"Hello!"  = 6 字元（包含 !）
作用位置
if len(overview) > OVERVIEW_MAX_CHARS:
    overview = overview[:OVERVIEW_MAX_CHARS] + "..."  # ← 截斷到 2000 字元
這是後處理：「不管 LLM 回多少，存進資料庫前截斷到 2000 字元」
🔄 兩者的關係
┌─────────────────────────────────────────────────────────────────┐
│                        處理流程                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [LLM 生成]                                                    │
│       │                                                         │
│       ├─ MAX_TOKENS = 1000                                      │
│       │  → LLM 最多輸出 ~1000-2000 中文字元                      │
│       │                                                         │
│       ▼                                                         │
│   [後處理截斷]                                                   │
│       │                                                         │
│       ├─ OVERVIEW_MAX_CHARS = 2000                              │
│       │  → 超過 2000 字元就截斷                                  │
│       │                                                         │
│       ▼                                                         │
│   [存入資料庫]                                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
實際情況
情況	MAX_TOKENS 產出	OVERVIEW_MAX_CHARS 結果
A	800 tokens → ~1200 字元	1200 字元（不截斷）
B	1000 tokens → ~1800 字元	1800 字元（不截斷）
C	1000 tokens → ~2500 字元	2000 字元 + "..."（截斷）
⚠️ 參數協調建議
目前設定：
MAX_TOKENS = 1000        # LLM 最多 ~1500-2000 中文字元
OVERVIEW_MAX_CHARS = 2000  # 儲存最多 2000 字元
結論：兩個參數目前大致協調，OVERVIEW_MAX_CHARS 略大於 MAX_TOKENS 的預期輸出，所以大部分情況下不會截斷。 如果你想要更長的 overview：
MAX_TOKENS = 1500        # ← 主要調這個
OVERVIEW_MAX_CHARS = 2500  # ← 配合調整
