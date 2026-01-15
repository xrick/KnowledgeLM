# DocAI RAG 系統 Prompt 設計最佳實踐

**日期**: 2025-11-03
**適用於**: RAG（Retrieval-Augmented Generation）系統開發

---

## 核心原則

### 1. 文檔優先，智能補充（Document-First, Intelligent Augmentation）

```python
# ✅ 推薦的 Prompt 結構
RECOMMENDED_PROMPT = """
**核心原則**：下方的上下文來自用戶勾選的文檔，是主要參考資料。

**回答策略**：
1. **優先引用文檔**：優先使用文檔內容，並明確標註來源
2. **智能補充說明**：當需要背景知識時，可以補充，但要明確區分：
   - 文檔內容：「根據您的文檔...」
   - 補充說明：「補充說明...」
3. **誠實評估**：如果文檔不足，明確說明並提供建議
4. **準確性優先**：不要編造文檔中不存在的內容

[上下文]
{context}
"""

# ❌ 避免過度嚴格
AVOID_TOO_STRICT = """
**重要約束**：你必須僅使用下方提供的上下文來回答。
絕對不能添加任何外部知識。  # ← 過於嚴格，用戶體驗差
"""

# ❌ 避免過度寬鬆
AVOID_TOO_LOOSE = """
根據你的知識回答問題，參考一下上下文。  # ← 過於寬鬆，可能偏離文檔
"""
```

---

## 實踐指南

### 2. 來源標註機制

#### 2.1 建議的回答格式

```markdown
## 標準回答模板

【文檔內容】
根據您的文檔，[引用文檔內容並標註來源]

【補充說明】
補充說明：[專業背景知識]

【建議】
[如果文檔不足，提供建議]
```

#### 2.2 Python 實現範例

```python
class ResponseFormatter:
    """格式化 RAG 回答，明確區分來源"""

    @staticmethod
    def format_response(
        document_content: str,
        supplement: Optional[str] = None,
        suggestions: Optional[str] = None
    ) -> str:
        """
        格式化回答，明確標註來源

        Args:
            document_content: 來自文檔的內容
            supplement: 補充的背景知識
            suggestions: 給用戶的建議

        Returns:
            格式化的回答
        """
        response = f"【文檔內容】\n{document_content}\n\n"

        if supplement:
            response += f"【補充說明】\n{supplement}\n\n"

        if suggestions:
            response += f"【建議】\n{suggestions}\n\n"

        return response

# 使用範例
formatter = ResponseFormatter()
answer = formatter.format_response(
    document_content="根據您的文檔，RAG 是一種結合檢索和生成的技術...",
    supplement="補充說明：RAG 在 2020 年由 Facebook AI 提出...",
    suggestions="建議您勾選關於 RAG 評估的文檔以獲得更完整的分析。"
)
```

---

### 3. 誠實評估機制

#### 3.1 文檔覆蓋度評估

```python
class DocumentCoverageEvaluator:
    """評估文檔對問題的覆蓋程度"""

    COVERAGE_LEVELS = {
        "full": "文檔完全覆蓋問題",
        "partial": "文檔部分覆蓋問題",
        "minimal": "文檔僅包含少量相關信息",
        "none": "文檔不包含相關信息"
    }

    @staticmethod
    def evaluate_coverage(
        question: str,
        retrieved_chunks: List[str]
    ) -> dict:
        """
        評估文檔覆蓋度

        Returns:
            {
                "level": "full|partial|minimal|none",
                "confidence": 0.0-1.0,
                "missing_aspects": List[str],
                "recommendation": str
            }
        """
        # 實現評估邏輯
        # 這裡可以使用 LLM 或啟發式方法
        pass

    @staticmethod
    def get_response_strategy(coverage_level: str) -> str:
        """根據覆蓋度決定回答策略"""
        strategies = {
            "full": "直接基於文檔回答，無需補充",
            "partial": "基於文檔回答主要部分，補充缺失部分（明確標註）",
            "minimal": "引用文檔中的有限信息，提供必要背景知識，建議勾選更多文檔",
            "none": "明確說明文檔不包含相關信息，詢問用戶是否需要一般性說明"
        }
        return strategies.get(coverage_level, "")
```

#### 3.2 Prompt 中的誠實評估指導

```python
HONEST_EVALUATION_GUIDE = """
**文檔不足時的處理策略**：

1. **完全覆蓋**（文檔有完整答案）：
   - 直接引用文檔內容
   - 明確標註來源
   - 無需額外補充

2. **部分覆蓋**（文檔有部分答案）：
   - 先引用文檔中的相關內容
   - 明確說明：「關於XX部分，您的文檔中信息較少」
   - 提供補充：「基於一般理解，XX是指...（補充說明）」

3. **最少覆蓋**（文檔僅有少量相關信息）：
   - 引用文檔中的有限信息
   - 說明：「您的文檔主要提到了XX，但關於YY和ZZ的詳細信息較少」
   - 建議：「建議您勾選關於YY和ZZ的文檔以獲得更完整的答案」

4. **無覆蓋**（文檔不包含相關信息）：
   - 明確說明：「在您勾選的文檔中，我沒有找到關於XX的直接信息」
   - 詢問：「您是否需要我提供一般性的說明，或者建議勾選其他相關文檔？」
"""
```

---

### 4. 質量控制機制

#### 4.1 回答質量評估指標

```python
class AnswerQualityMetrics:
    """RAG 回答質量評估指標"""

    @staticmethod
    def evaluate_answer(
        question: str,
        answer: str,
        document_chunks: List[str]
    ) -> dict:
        """
        評估回答質量

        Returns:
            {
                "faithfulness": 0.0-1.0,  # 對文檔的忠實度
                "relevance": 0.0-1.0,     # 回答的相關性
                "completeness": 0.0-1.0,  # 回答的完整性
                "clarity": 0.0-1.0,       # 來源標註的清晰度
                "helpfulness": 0.0-1.0    # 對用戶的幫助度
            }
        """
        return {
            "faithfulness": AnswerQualityMetrics._check_faithfulness(answer, document_chunks),
            "relevance": AnswerQualityMetrics._check_relevance(question, answer),
            "completeness": AnswerQualityMetrics._check_completeness(question, answer),
            "clarity": AnswerQualityMetrics._check_source_clarity(answer),
            "helpfulness": AnswerQualityMetrics._check_helpfulness(answer)
        }

    @staticmethod
    def _check_faithfulness(answer: str, document_chunks: List[str]) -> float:
        """檢查回答是否忠實於文檔"""
        # 實現忠實度檢查邏輯
        # 可以使用 NLI 模型或相似度計算
        pass

    @staticmethod
    def _check_source_clarity(answer: str) -> float:
        """檢查來源標註的清晰度"""
        # 檢查是否包含「根據您的文檔」、「補充說明」等標註
        document_markers = ["根據您的文檔", "文檔中提到", "文檔顯示"]
        supplement_markers = ["補充說明", "相關背景", "基於一般理解"]

        has_document_marker = any(marker in answer for marker in document_markers)
        has_supplement_marker = any(marker in answer for marker in supplement_markers)

        if has_document_marker and has_supplement_marker:
            return 1.0  # 清晰區分來源
        elif has_document_marker:
            return 0.7  # 標註了文檔來源
        else:
            return 0.3  # 缺少來源標註
```

#### 4.2 自動化質量檢查

```python
class PromptQualityChecker:
    """Prompt 質量檢查器"""

    ANTI_PATTERNS = {
        "too_strict": [
            "只使用",
            "僅使用",
            "必須僅",
            "不得添加",
            "絕對不能",
            "禁止使用"
        ],
        "too_loose": [
            "可以自由",
            "隨意使用",
            "不需要參考文檔"
        ],
        "missing_source_instruction": [
            # 缺少來源標註指導
        ]
    }

    @staticmethod
    def check_prompt(prompt_text: str) -> dict:
        """
        檢查 Prompt 是否符合最佳實踐

        Returns:
            {
                "is_valid": bool,
                "warnings": List[str],
                "suggestions": List[str]
            }
        """
        warnings = []
        suggestions = []

        # 檢查過度嚴格
        for pattern in PromptQualityChecker.ANTI_PATTERNS["too_strict"]:
            if pattern in prompt_text:
                warnings.append(f"發現過度嚴格的約束：「{pattern}」")
                suggestions.append("建議改用「優先使用文檔，必要時可補充」")

        # 檢查過度寬鬆
        for pattern in PromptQualityChecker.ANTI_PATTERNS["too_loose"]:
            if pattern in prompt_text:
                warnings.append(f"發現過度寬鬆的指導：「{pattern}」")
                suggestions.append("建議強調文檔優先原則")

        # 檢查是否包含來源標註指導
        has_source_instruction = any([
            "明確標註" in prompt_text,
            "區分來源" in prompt_text,
            "根據您的文檔" in prompt_text
        ])

        if not has_source_instruction:
            warnings.append("缺少來源標註指導")
            suggestions.append("建議添加明確的來源標註指導")

        return {
            "is_valid": len(warnings) == 0,
            "warnings": warnings,
            "suggestions": suggestions
        }

# 使用範例
checker = PromptQualityChecker()
result = checker.check_prompt(your_prompt_text)
if not result["is_valid"]:
    print("Prompt 質量警告：")
    for warning in result["warnings"]:
        print(f"  - {warning}")
    print("建議：")
    for suggestion in result["suggestions"]:
        print(f"  - {suggestion}")
```

---

### 5. A/B 測試框架

#### 5.1 Prompt 版本管理

```python
from typing import Dict, Callable
from dataclasses import dataclass
from enum import Enum

class PromptVersion(Enum):
    """Prompt 版本枚舉"""
    STRICT = "strict"           # 嚴格版本（只用文檔）
    BALANCED = "balanced"       # 平衡版本（推薦）
    FLEXIBLE = "flexible"       # 靈活版本（較多補充）

@dataclass
class PromptTemplate:
    """Prompt 模板數據類"""
    name: str
    version: PromptVersion
    template: str
    description: str
    created_at: str
    metrics: Dict[str, float]  # 性能指標

class PromptVersionManager:
    """Prompt 版本管理器"""

    def __init__(self):
        self.templates: Dict[PromptVersion, PromptTemplate] = {
            PromptVersion.STRICT: PromptTemplate(
                name="Strict Version",
                version=PromptVersion.STRICT,
                template=self._get_strict_template(),
                description="嚴格遵守文檔，不添加外部知識",
                created_at="2025-11-01",
                metrics={"user_satisfaction": 0.6, "completeness": 0.5}
            ),
            PromptVersion.BALANCED: PromptTemplate(
                name="Balanced Version",
                version=PromptVersion.BALANCED,
                template=self._get_balanced_template(),
                description="優先文檔，智能補充（推薦）",
                created_at="2025-11-03",
                metrics={"user_satisfaction": 0.85, "completeness": 0.9}
            ),
            PromptVersion.FLEXIBLE: PromptTemplate(
                name="Flexible Version",
                version=PromptVersion.FLEXIBLE,
                template=self._get_flexible_template(),
                description="靈活使用知識，參考文檔",
                created_at="2025-11-02",
                metrics={"user_satisfaction": 0.7, "completeness": 0.95}
            )
        }

    def get_template(self, version: PromptVersion = PromptVersion.BALANCED) -> str:
        """獲取指定版本的 Prompt 模板"""
        return self.templates[version].template

    def compare_versions(self) -> Dict[PromptVersion, Dict[str, float]]:
        """比較不同版本的性能指標"""
        return {
            version: template.metrics
            for version, template in self.templates.items()
        }

    @staticmethod
    def _get_strict_template() -> str:
        return """只使用下方文檔內容回答，不得添加外部知識。
[上下文]
{context}"""

    @staticmethod
    def _get_balanced_template() -> str:
        return """**核心原則**：優先使用下方文檔內容，必要時可補充專業知識（需明確區分）。

回答策略：
1. 優先引用文檔：「根據您的文檔...」
2. 智能補充：「補充說明...」
3. 誠實評估：說明文檔覆蓋度

[上下文]
{context}"""

    @staticmethod
    def _get_flexible_template() -> str:
        return """基於你的專業知識回答問題，參考下方文檔內容。
[上下文]
{context}"""

# 使用範例
manager = PromptVersionManager()

# 獲取推薦版本
recommended_prompt = manager.get_template(PromptVersion.BALANCED)

# 比較版本性能
comparison = manager.compare_versions()
print("版本性能比較：")
for version, metrics in comparison.items():
    print(f"{version.value}: 滿意度={metrics['user_satisfaction']}, 完整性={metrics['completeness']}")
```

#### 5.2 A/B 測試實現

```python
import random
from typing import Optional

class ABTestManager:
    """A/B 測試管理器"""

    def __init__(
        self,
        version_manager: PromptVersionManager,
        test_ratio: float = 0.2  # 20% 流量測試新版本
    ):
        self.version_manager = version_manager
        self.test_ratio = test_ratio
        self.results = {version: [] for version in PromptVersion}

    def get_prompt_for_user(
        self,
        user_id: str,
        test_version: Optional[PromptVersion] = None
    ) -> tuple[str, PromptVersion]:
        """
        為用戶分配 Prompt 版本

        Args:
            user_id: 用戶 ID
            test_version: 測試版本（如果指定）

        Returns:
            (prompt_text, version_used)
        """
        # 如果指定測試版本，直接使用
        if test_version:
            version = test_version
        else:
            # 否則根據測試比例分配
            if random.random() < self.test_ratio:
                version = PromptVersion.FLEXIBLE  # 測試版本
            else:
                version = PromptVersion.BALANCED   # 主版本

        prompt = self.version_manager.get_template(version)
        return prompt, version

    def record_feedback(
        self,
        user_id: str,
        version: PromptVersion,
        feedback: dict
    ):
        """
        記錄用戶反饋

        Args:
            user_id: 用戶 ID
            version: 使用的版本
            feedback: 反饋數據
                {
                    "helpful": bool,
                    "complete": bool,
                    "clear_sources": bool,
                    "rating": int  # 1-5
                }
        """
        self.results[version].append({
            "user_id": user_id,
            **feedback
        })

    def get_test_results(self) -> dict:
        """獲取 A/B 測試結果"""
        results = {}
        for version, feedbacks in self.results.items():
            if not feedbacks:
                continue

            results[version.value] = {
                "sample_size": len(feedbacks),
                "helpful_rate": sum(1 for f in feedbacks if f["helpful"]) / len(feedbacks),
                "complete_rate": sum(1 for f in feedbacks if f["complete"]) / len(feedbacks),
                "avg_rating": sum(f["rating"] for f in feedbacks) / len(feedbacks)
            }

        return results

# 使用範例
version_manager = PromptVersionManager()
ab_test = ABTestManager(version_manager, test_ratio=0.2)

# 為用戶分配版本
prompt, version = ab_test.get_prompt_for_user("user_123")
print(f"用戶使用版本：{version.value}")

# 記錄用戶反饋
ab_test.record_feedback(
    user_id="user_123",
    version=version,
    feedback={
        "helpful": True,
        "complete": True,
        "clear_sources": True,
        "rating": 5
    }
)

# 查看測試結果
results = ab_test.get_test_results()
print("A/B 測試結果：", results)
```

---

### 6. 監控和優化

#### 6.1 關鍵指標監控

```python
from dataclasses import dataclass
from datetime import datetime
from typing import List

@dataclass
class RAGMetrics:
    """RAG 系統關鍵指標"""
    timestamp: datetime
    user_satisfaction: float      # 用戶滿意度 (0-1)
    answer_completeness: float    # 回答完整性 (0-1)
    document_citation_rate: float # 文檔引用率 (0-1)
    supplement_rate: float        # 補充說明比例 (0-1)
    no_answer_rate: float         # 無法回答比例 (0-1)
    avg_response_time_ms: float   # 平均響應時間

class MetricsCollector:
    """指標收集器"""

    def __init__(self):
        self.metrics_history: List[RAGMetrics] = []

    def collect_metrics(self) -> RAGMetrics:
        """收集當前指標"""
        # 實現指標收集邏輯
        # 這裡應該從數據庫或日誌中獲取實際數據
        metrics = RAGMetrics(
            timestamp=datetime.now(),
            user_satisfaction=0.85,
            answer_completeness=0.9,
            document_citation_rate=0.95,
            supplement_rate=0.3,
            no_answer_rate=0.05,
            avg_response_time_ms=1500
        )
        self.metrics_history.append(metrics)
        return metrics

    def check_health(self, metrics: RAGMetrics) -> dict:
        """檢查系統健康狀況"""
        issues = []
        recommendations = []

        # 檢查用戶滿意度
        if metrics.user_satisfaction < 0.7:
            issues.append("用戶滿意度較低")
            recommendations.append("審查 Prompt 是否過於嚴格或過於寬鬆")

        # 檢查無法回答比例
        if metrics.no_answer_rate > 0.2:
            issues.append("無法回答的比例過高")
            recommendations.append("檢查 Prompt 是否允許適當的補充說明")

        # 檢查補充說明比例
        if metrics.supplement_rate > 0.5:
            issues.append("補充說明比例過高")
            recommendations.append("可能需要用戶上傳更多相關文檔")
        elif metrics.supplement_rate < 0.1:
            issues.append("補充說明比例過低")
            recommendations.append("確認是否應該提供更多背景知識")

        return {
            "is_healthy": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations
        }

# 使用範例
collector = MetricsCollector()
current_metrics = collector.collect_metrics()
health_check = collector.check_health(current_metrics)

if not health_check["is_healthy"]:
    print("系統健康檢查警告：")
    for issue in health_check["issues"]:
        print(f"  問題：{issue}")
    for rec in health_check["recommendations"]:
        print(f"  建議：{rec}")
```

---

## 實施檢查清單

### ✅ Prompt 設計檢查清單

- [ ] **平衡性檢查**
  - [ ] 是否明確「優先文檔」而非「僅用文檔」？
  - [ ] 是否允許智能補充並要求明確標註？
  - [ ] 是否包含誠實評估機制？

- [ ] **來源標註檢查**
  - [ ] 是否要求區分「文檔內容」和「補充說明」？
  - [ ] 是否提供了標註範例（如「根據您的文檔...」）？
  - [ ] 是否要求引用文檔來源？

- [ ] **用戶體驗檢查**
  - [ ] 文檔不足時是否有處理策略？
  - [ ] 是否避免簡單回覆「無法找到信息」？
  - [ ] 是否提供建議（如勾選其他文檔）？

- [ ] **安全性檢查**
  - [ ] 是否包含「不要編造內容」的約束？
  - [ ] 是否要求準確性優先？
  - [ ] 是否明確文檔的重要性？

### ✅ 實施檢查清單

- [ ] **代碼層面**
  - [ ] 更新所有 Prompt 模板
  - [ ] 實施來源標註機制
  - [ ] 添加質量評估指標
  - [ ] 實現 A/B 測試框架

- [ ] **測試層面**
  - [ ] 完全覆蓋場景測試
  - [ ] 部分覆蓋場景測試
  - [ ] 最少覆蓋場景測試
  - [ ] 無覆蓋場景測試

- [ ] **監控層面**
  - [ ] 設置用戶滿意度監控
  - [ ] 設置回答完整性監控
  - [ ] 設置補充說明比例監控
  - [ ] 設置無法回答比例監控

- [ ] **維護層面**
  - [ ] 建立定期審查機制（每月）
  - [ ] 建立用戶反饋收集機制
  - [ ] 建立 Prompt 版本管理系統
  - [ ] 建立性能優化流程

---

## 總結

### 關鍵要點

1. **RAG ≠ 嚴格限制**
   - RAG 的 "Augmented" 意味著增強，不是替代
   - 優秀的 RAG 系統應該結合檢索和生成的優勢

2. **平衡是關鍵**
   - 文檔優先 ≠ 完全限制
   - 智能補充 ≠ 自由發揮
   - 誠實評估 ≠ 簡單拒絕

3. **用戶體驗優先**
   - 用戶需要有用的回答，不是簡單的「沒找到」
   - 明確的來源標註比完全限制更重要
   - 提供建議和指導，幫助用戶獲得更好的結果

4. **持續優化**
   - 監控關鍵指標
   - 收集用戶反饋
   - A/B 測試優化
   - 定期審查和調整

---

**文檔結束**

更多資源：
- [完整修正報告](./prompt_fix_report_20251103_RAG_constraint.md)
- [RAG 系統資料流動分析](./RAG系統資料流動與提示詞分析報告.md)
- [Prompt 自訂指南](./prompt_customization_guide.md)
