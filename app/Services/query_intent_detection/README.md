# Query Intent Detection Module

靈活的查詢意圖偵測系統，採用 **Strategy Pattern** 和 **Factory Method** 設計模式。

## 目錄

- [功能特性](#功能特性)
- [架構設計](#架構設計)
- [快速開始](#快速開始)
- [使用範例](#使用範例)
- [偵測策略](#偵測策略)
- [向後相容性](#向後相容性)
- [未來擴展](#未來擴展)

---

## 功能特性

✅ **多策略支援**: 使用 Strategy Pattern 支援多種偵測方法
✅ **工廠模式**: Factory Method 簡化策略選擇和建立
✅ **向後相容**: 不影響現有的單文件和多文件查詢功能
✅ **可擴展**: 預留未來實作 NLP-based 和 String Parsing 策略的介面
✅ **詳細結果**: 提供信心度、匹配模式、觸發層級等詳細資訊

---

## 架構設計

```
query_intent_detection/
├── __init__.py                    # 模組初始化
├── base.py                        # 抽象基類 (Strategy Pattern)
├── regex_strategy.py              # Regex-based 策略 (已實作) ✅
├── string_parsing_strategy.py     # String parsing 策略 (未來實作) 🔮
├── nlp_strategy.py                # NLP-based 策略 (未來實作) 🔮
├── factory.py                     # Factory Method
├── integration.py                 # 整合層 (向後相容)
└── README.md                      # 本文件
```

### 設計模式

#### 1. Strategy Pattern

```python
# 抽象策略
class IntentDetectionStrategy(ABC):
    @abstractmethod
    def detect_multi_file_intent(query, file_count) -> MultiFileIntentResult:
        pass

# 具體策略
class RegexPatternStrategy(IntentDetectionStrategy):
    def detect_multi_file_intent(query, file_count):
        # Regex-based implementation
        ...

class StringParsingStrategy(IntentDetectionStrategy):
    def detect_multi_file_intent(query, file_count):
        # Future implementation
        ...
```

#### 2. Factory Method

```python
class IntentDetectorFactory:
    @classmethod
    def create_detector(strategy_type='regex'):
        # Create appropriate strategy instance
        ...
```

---

## 快速開始

### 基本使用（向後相容）

```python
# 最簡單的方式 - 完全向後相容
from app.Services.query_intent_detection.integration import detect_multi_file_intent

# 偵測多文件意圖
is_multi = detect_multi_file_intent("比較三份文件", file_count=3)
print(is_multi)  # True

is_single = detect_multi_file_intent("解釋這個文件", file_count=1)
print(is_single)  # False
```

### 使用工廠創建策略

```python
from app.Services.query_intent_detection import IntentDetectorFactory

# 創建 Regex 策略（預設）
detector = IntentDetectorFactory.create_detector('regex')

# 偵測意圖
result = detector.detect_multi_file_intent("產生四份文件的摘要", file_count=4)
print(result)
# MultiFileIntent(is_multi=True, confidence=0.95,
#                 layer=layer2_quantity_pattern, patterns=['quantity_chinese:四份'])
```

### 獲取詳細結果

```python
from app.Services.query_intent_detection.integration import detect_multi_file_intent_detailed

# 獲取詳細偵測資訊
result = detect_multi_file_intent_detailed("所有文件的內容", file_count=5)
print(result)
# {
#     'is_multi_file': True,
#     'confidence': 0.85,
#     'matched_patterns': ['scope_content:[所有]+[內容]'],
#     'detection_layer': 'layer3_scope_content'
# }
```

---

## 使用範例

### 範例 1: Demo 使用（Regex Strategy）

```python
from app.Services.query_intent_detection import IntentDetectorFactory

# 創建 Regex 策略
detector = IntentDetectorFactory.create_detector('regex')

# 測試各種查詢
test_queries = [
    ("比較三份文件", 3),           # Layer 1: 高信心關鍵字
    ("產生四份文件的摘要", 4),      # Layer 2: 數量模式
    ("所有文件的內容", 5),         # Layer 3: 範圍詞 + 內容詞
    ("給我10個檔案的資料", 10),    # Layer 2: 阿拉伯數字
    ("解釋這個文件", 1),           # 單文件 (file_count < 2)
]

for query, file_count in test_queries:
    result = detector.detect_multi_file_intent(query, file_count)
    print(f"Query: {query}")
    print(f"  → {result}")
    print()
```

**輸出**:
```
Query: 比較三份文件
  → MultiFileIntent(is_multi=True, confidence=1.00, layer=layer1_high_confidence, patterns=['high_confidence:比較'])

Query: 產生四份文件的摘要
  → MultiFileIntent(is_multi=True, confidence=0.95, layer=layer2_quantity_pattern, patterns=['quantity_chinese:四份'])

Query: 所有文件的內容
  → MultiFileIntent(is_multi=True, confidence=0.85, layer=layer3_scope_content, patterns=['scope_content:[所有]+[內容]'])

Query: 給我10個檔案的資料
  → MultiFileIntent(is_multi=True, confidence=0.95, layer=layer2_quantity_pattern, patterns=['quantity_numeric:10個'])

Query: 解釋這個文件
  → MultiFileIntent(is_multi=False, confidence=1.00, layer=validation, patterns=[])
```

### 範例 2: 全域配置

```python
from app.Services.query_intent_detection.integration import IntentDetectorManager

# 在應用程式啟動時配置策略
IntentDetectorManager.configure(strategy_type='regex')

# 之後所有的 detect_multi_file_intent 呼叫都會使用這個策略
from app.Services.query_intent_detection.integration import detect_multi_file_intent

is_multi = detect_multi_file_intent("三篇文章的差異", 3)
```

### 範例 3: 查詢策略資訊

```python
from app.Services.query_intent_detection.integration import get_current_strategy_info
from app.Services.query_intent_detection import IntentDetectorFactory

# 查看當前策略
info = get_current_strategy_info()
print(info)
# {
#     'strategy_type': 'regex',
#     'strategy_name': 'RegexPattern',
#     'available_strategies': {
#         'regex': 'available',
#         'string_parsing': 'not_implemented',
#         'nlp': 'not_implemented'
#     }
# }

# 查看可用策略
strategies = IntentDetectorFactory.get_available_strategies()
print(strategies)
```

### 範例 4: 獲取模式資訊（用於調試）

```python
from app.Services.query_intent_detection import RegexPatternStrategy

# 創建策略
detector = RegexPatternStrategy()

# 查看配置的模式
pattern_info = detector.get_pattern_info()
print(pattern_info)
# {
#     'strategy_name': 'RegexPattern',
#     'layers': [
#         {
#             'name': 'layer1_high_confidence',
#             'type': 'exact_match',
#             'confidence': 1.0,
#             'keywords': ['比較', '對比', '差異', ...]
#         },
#         ...
#     ]
# }
```

---

## 偵測策略

### RegexPatternStrategy (已實作) ✅

**採用多層偵測架構**：

#### Layer 1: 高信心關鍵字 (信心度: 1.0)
- 關鍵字: `比較`, `對比`, `差異`, `異同`, `各別`, `分別`, `每份`, `每一份`
- 速度: 極快 (精確匹配)
- 適用: 明確的多文件查詢

#### Layer 2: 數量模式 (信心度: 0.95)
- **中文數字 + 量詞**: `[二三四五六七八九十百千多幾][份篇個本張支檔文件]`
  - 範例: `三份`, `四篇`, `五個`, `七本`
- **阿拉伯數字 + 量詞**: `\d+[份篇個本張支檔文件]`
  - 範例: `3份`, `10個`, `100篇`
- 速度: 快 (正則表達式)
- 適用: 明確指定數量的查詢

#### Layer 3: 範圍詞 + 內容詞組合 (信心度: 0.85)
- **範圍詞**: `所有`, `這些`, `全部`, `整體`
- **內容詞**: `內容`, `資料`, `資訊`, `文章`
- 條件: 範圍詞 AND 內容詞都出現
- 範例: `所有文件的內容`, `這些資料的資訊`
- 速度: 快 (關鍵字組合)
- 適用: 隱含多文件意圖的查詢

#### Layer 4: 多文件暗示 (信心度: 0.75)
- 關鍵字: `多份`, `多篇`, `多個`, `不同文件`
- 速度: 極快 (精確匹配)
- 適用: 使用「多」字表達的查詢

#### 保護機制
```python
if file_count < 2:
    return False  # 單文件自動回傳 False，不受關鍵字影響
```

### StringParsingStrategy (未來實作) 🔮

**規劃方法**：
- 使用 jieba 進行中文分詞
- 詞性標註識別數量詞
- 分析並列結構和分配詞

**預期優勢**：
- 可處理更複雜的語言結構
- 更精確的詞邊界識別

### NLPBasedStrategy (未來實作) 🔮

**規劃方法**：
- 使用 spaCy 中文模型
- 依存句法分析
- 命名實體識別

**預期優勢**：
- 語言學規則為基礎
- 可偵測複雜語法結構
- 高度可解釋性

---

## 向後相容性

### 不影響現有功能

本模組設計為**完全向後相容**，可以無縫整合到現有系統：

```python
# ✅ 現有程式碼無需修改
from app.Services.query_intent_detection.integration import detect_multi_file_intent

# 這個函數簽名和返回值與原有的 keyword-based 檢測完全相同
is_multi = detect_multi_file_intent(query, file_count)  # Returns: bool
```

### 整合到 iterative_query_expansion_service.py

**選項 1: 保持現有程式碼不變**
```python
# iterative_query_expansion_service.py 無需修改
# 繼續使用現有的 hard-coded MULTI_FILE_KEYWORDS
```

**選項 2: 漸進式遷移**
```python
# 在 iterative_query_expansion_service.py 中
from app.Services.query_intent_detection.integration import detect_multi_file_intent

def detect_multi_file_summary_intent(self, query: str, file_count: int) -> bool:
    # 替換原有的 keyword matching
    return detect_multi_file_intent(query, file_count)
```

**選項 3: 雙軌並行（A/B 測試）**
```python
# 同時使用兩種方法，記錄差異
old_result = any(kw in query for kw in MULTI_FILE_KEYWORDS)
new_result = detect_multi_file_intent(query, file_count)

if old_result != new_result:
    logger.info(f"Detection mismatch: old={old_result}, new={new_result}, query={query}")

return new_result  # 或 old_result，取決於想使用哪個
```

---

## 未來擴展

### 實作 StringParsingStrategy

```python
# string_parsing_strategy.py
import jieba

class StringParsingStrategy(IntentDetectionStrategy):
    def __init__(self):
        super().__init__(name="StringParsing")
        # 載入分詞模型

    def detect_multi_file_intent(self, query, file_count):
        # 分詞
        tokens = jieba.lcut(query)

        # 識別數量詞
        quantity_words = self._identify_quantity_words(tokens)

        # 分析組合
        ...
```

### 實作 NLPBasedStrategy

```python
# nlp_strategy.py
import spacy

class NLPBasedStrategy(IntentDetectionStrategy):
    def __init__(self):
        super().__init__(name="NLPBased")
        self.nlp = spacy.load("zh_core_web_sm")

    def detect_multi_file_intent(self, query, file_count):
        # NLP 分析
        doc = self.nlp(query)

        # 檢查詞性標註
        for token in doc:
            if token.pos_ == "NUM":  # 數字
                # 檢查下一個詞是否為量詞
                ...
```

### 註冊自訂策略

```python
from app.Services.query_intent_detection import IntentDetectorFactory

class CustomStrategy(IntentDetectionStrategy):
    def detect_multi_file_intent(self, query, file_count):
        # 自訂實作
        ...

# 註冊策略
IntentDetectorFactory.register_strategy('custom', CustomStrategy)

# 使用
detector = IntentDetectorFactory.create_detector('custom')
```

---

## API 參考

### IntentDetectorFactory

- `create_detector(strategy_type='regex', fallback=True)`: 創建策略實例
- `get_available_strategies()`: 獲取可用策略資訊
- `register_strategy(name, strategy_class)`: 註冊自訂策略

### IntentDetectionStrategy

- `detect_multi_file_intent(query, file_count)`: 偵測多文件意圖

### Integration Functions

- `detect_multi_file_intent(query, file_count)`: 簡單布林回傳
- `detect_multi_file_intent_detailed(query, file_count)`: 詳細資訊回傳
- `get_current_strategy_info()`: 獲取當前策略資訊

---

## 開發者備註

### 為什麼使用 Strategy Pattern？

1. **靈活性**: 可以輕鬆切換不同的偵測方法
2. **可擴展性**: 新增策略不影響現有程式碼
3. **可測試性**: 每個策略可以獨立測試
4. **關注點分離**: 偵測邏輯與業務邏輯分離

### 為什麼使用 Factory Method？

1. **簡化建立過程**: 隱藏策略實例化細節
2. **統一介面**: 提供一致的創建方式
3. **容錯處理**: 自動 fallback 到可用策略
4. **配置管理**: 集中管理策略選擇邏輯

---

## 版本歷史

- **v1.0.0** (2025-11-25)
  - ✅ 實作 RegexPatternStrategy
  - ✅ 實作 Factory Method
  - ✅ 提供向後相容的整合層
  - 🔮 定義未來策略介面

---

**維護者**: Claude (SuperClaude Framework)
**最後更新**: 2025-11-25
