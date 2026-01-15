# app/Services/iterative_query_expansion_service.py
"""
Iterative Query Expansion Service - Advanced Multi-Round Expansion Strategy

Professional RAG query expansion implementing:
1. Multi-round iterative expansion (configurable 1-3 rounds)
2. Query quality scoring with multiple dimensions
3. Best query selection via LLM-based evaluation
4. Expansion tree pruning to avoid explosion
5. Semantic diversity optimization

Strategy:
- Round 1: Initial expansion (3-5 queries)
- Round 2: Selected expansion (top queries expanded further)
- Round 3 (optional): Final refinement and selection
- Selection: LLM-based scoring to choose best final query

Benefits over single-round:
- Better handling of vague/ambiguous queries
- Multi-perspective exploration
- Higher quality final queries through iterative refinement
- Semantic diversity through controlled expansion
"""

import logging
import json
import asyncio
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Timeout settings for expansion operations (seconds)
EXPANSION_CALL_TIMEOUT = 30.0  # Max time per LLM call
EXPANSION_TOTAL_TIMEOUT = 60.0  # Max total time for all expansion


class ExpansionStrategy(Enum):
    """Query expansion strategy types"""
    SINGLE = "single"           # Original single-round expansion
    ITERATIVE = "iterative"     # Multi-round iterative expansion
    ADAPTIVE = "adaptive"       # Auto-select based on query complexity


@dataclass
class ExpandedQuery:
    """Represents an expanded query with metadata"""
    text: str
    round_number: int
    parent_query: Optional[str] = None
    quality_score: float = 0.0
    dimensions: Dict[str, float] = field(default_factory=dict)
    reasoning: str = ""

    def __hash__(self):
        return hash(self.text)

    def __eq__(self, other):
        if isinstance(other, ExpandedQuery):
            return self.text == other.text
        return False


@dataclass
class ExpansionResult:
    """Result of iterative query expansion"""
    original_query: str
    best_query: str
    final_queries: List[str]
    expansion_tree: Dict[str, List[str]]
    quality_scores: Dict[str, float]
    total_rounds: int
    strategy_used: str
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class IterativeQueryExpansionService:
    """
    Advanced Iterative Query Expansion Service

    Implements professional multi-round query expansion with:
    - Configurable expansion rounds (1-3)
    - Quality-based pruning at each round
    - LLM-based best query selection
    - Semantic diversity optimization
    - Summary/question intent detection
    - Caching for efficiency

    This is the single consolidated query enhancement service.

    NEW: Integrated with regex-based pattern detection for multi-file intent
    """

    # =========================================================================
    # FEATURE FLAG: Toggle between new regex-based and legacy hard-coded detection
    # Rollback: Set to False to use original hard-coded keywords
    # =========================================================================
    USE_NEW_INTENT_DETECTION = True  # ← Set to False for rollback

    # =========================================================================
    # Summary Detection Keywords
    # =========================================================================
    SUMMARY_KEYWORDS = [
        "摘要", "總結", "概述", "summary", "summarize", "overview",
        "概括", "簡述", "歸納", "重點", "要點", "大意"
    ]

    # =========================================================================
    # Multi-File Intent Detection Keywords
    # =========================================================================
    MULTI_FILE_KEYWORDS = [
        "各別", "分別", "每份", "每一份", "所有文件", "這些文件",
        "二份", "兩份", "三份", "四份", "五份", "六份",  # 增加具體數量
        "二篇", "兩篇", "三篇", "四篇", "五篇", "六篇",  # 增加「篇」
        "二個", "兩個", "三個", "四個", "五個", "六個",  # 增加「個」
        "多份", "多篇", "多個", "各自", "各個", "不同文件",
        "說明", "介紹", "比較", "對比", "差異", "異同",
        "內容", "資料", "資訊", "文章"  # 增加內容相關關鍵字
    ]

    # =========================================================================
    # Prompt Templates
    # =========================================================================

    ROUND1_EXPANSION_PROMPT = """你是一位專業的RAG查詢優化專家。請將用戶的原始查詢擴展為多個更具體、更精確的查詢。

[原始查詢]
{original_query}

[任務]
生成 {expansion_count} 個擴展查詢，每個查詢應該：
1. 從不同角度探索原始問題
2. 更加具體和明確
3. 適合用於向量檢索
4. 還原代名詞與指代對象：如果問題中包含「它」、「這份文件」、「前者」等代名詞，請根據對話歷史將其替換為具體的名詞或文件名稱。（例如：將「關於成本它怎麼說？」改寫為「Q3 財報中關於營運成本的描述是什麼？」）
5. 補全上下文：如果使用者的問題是延續上一題的追問（例如：「那行銷部門呢？」），請將省略的主詞或背景資訊補全（改寫為：「Q3 財報中關於行銷部門的預算分配為何？」）。
6. 保留核心意圖：不要改變使用者的原始意圖或關鍵字。
7. 輸出限制：直接輸出重寫後的查詢字串即可，**嚴禁**輸出任何解釋、前言或結語。

請以 JSON 格式回應：
{{
  "expanded_queries": [
    {{
      "query": "擴展查詢1",
      "perspective": "此查詢的角度說明",
      "specificity": "high/medium/low"
    }},
    ...
  ],
  "original_intent": "原始查詢的核心意圖",
  "complexity_assessment": "simple/moderate/complex"
}}

要求：
- 每個查詢應該能獨立用於檢索
- 覆蓋不同的信息需求維度
- 避免過於籠統或重複的查詢"""

    ROUND2_REFINEMENT_PROMPT = """你是一位專業的RAG查詢優化專家。請基於第一輪擴展結果，進一步細化和優化查詢。

[原始查詢]
{original_query}

[第一輪擴展查詢]
{round1_queries}

[任務]
從每個第一輪查詢中，選擇最有價值的進行進一步細化。
對於每個選中的查詢，生成 2 個更精確的子查詢。

請以 JSON 格式回應：
{{
  "refined_queries": [
    {{
      "parent_query": "來源的第一輪查詢",
      "refined_versions": [
        "細化查詢1",
        "細化查詢2"
      ],
      "refinement_reasoning": "細化的邏輯說明"
    }},
    ...
  ],
  "pruned_queries": ["被排除的查詢及原因"]
}}

細化原則：
1. 更具體的術語和概念
2. 更明確的信息需求
3. 更適合向量檢索的表述
4. 保持與原始意圖的關聯"""

    QUERY_SCORING_PROMPT = """你是一位專業的RAG查詢質量評估專家。請對以下查詢進行質量評分。

[原始用戶查詢]
{original_query}

[待評估查詢列表]
{queries_to_score}

[評分維度]
1. **相關性 (relevance)**: 與原始意圖的匹配程度 (0-1)
2. **具體性 (specificity)**: 查詢的具體和明確程度 (0-1)
3. **檢索適配度 (retrieval_fit)**: 適合向量檢索的程度 (0-1)
4. **信息覆蓋度 (coverage)**: 能獲取全面信息的程度 (0-1)

請以 JSON 格式回應：
{{
  "scored_queries": [
    {{
      "query": "查詢文本",
      "scores": {{
        "relevance": 0.85,
        "specificity": 0.90,
        "retrieval_fit": 0.80,
        "coverage": 0.75
      }},
      "overall_score": 0.825,
      "reasoning": "評分理由"
    }},
    ...
  ],
  "best_query": "最佳查詢文本",
  "selection_reasoning": "選擇最佳查詢的理由"
}}

評分標準：
- 0.9-1.0: 優秀，非常適合檢索
- 0.7-0.9: 良好，適合使用
- 0.5-0.7: 一般，可能需要改進
- 0.0-0.5: 較差，建議修改"""

    BEST_QUERY_SELECTION_PROMPT = """你是一位專業的RAG查詢選擇專家。請從候選查詢中選擇最佳的最終查詢。

[原始用戶查詢]
{original_query}

[候選查詢及其評分]
{candidate_queries}

[任務]
選擇一個最佳查詢作為最終檢索查詢。如果需要，可以綜合多個查詢的優點創建一個優化版本。

請以 JSON 格式回應：
{{
  "selected_query": "最終選擇的查詢",
  "is_synthesized": true/false,
  "source_queries": ["來源查詢1", "來源查詢2"],
  "selection_reasoning": "選擇理由",
  "confidence": 0.95
}}

選擇原則：
1. 最能代表用戶原始意圖
2. 最適合向量檢索
3. 具體且信息量豐富
4. 避免過於籠統或過於狹窄"""

    def __init__(
        self,
        llm_provider_client,
        max_rounds: int = 2,
        queries_per_round: int = 3,
        pruning_threshold: float = 0.6,
        enable_scoring: bool = True
    ):
        """
        Initialize Iterative Query Expansion Service

        Args:
            llm_provider_client: LLM provider client instance
            max_rounds: Maximum expansion rounds (1-3, default: 2)
            queries_per_round: Number of queries to generate per round
            pruning_threshold: Minimum score to keep a query (0-1)
            enable_scoring: Whether to enable LLM-based scoring
        """
        from app.core.config import settings

        self.llm_client = llm_provider_client
        self.max_rounds = min(max(max_rounds, 1), 3)  # Clamp to 1-3
        self.queries_per_round = queries_per_round
        self.pruning_threshold = pruning_threshold
        self.enable_scoring = enable_scoring
        self.expansion_temperature = getattr(settings, 'EXPANSION_TEMPERATURE', 0.3)

        logger.info(
            f"Iterative Query Expansion Service initialized "
            f"(max_rounds={self.max_rounds}, queries_per_round={self.queries_per_round}, "
            f"pruning_threshold={self.pruning_threshold})"
        )

    """
    Multi-round iterative query expansion
    """
    async def expand_iteratively(
        self,
        query: str,
        strategy: ExpansionStrategy = ExpansionStrategy.ITERATIVE,
        cache_provider = None
    ) -> ExpansionResult:
        """
        Perform iterative multi-round query expansion

        Args:
            query: Original user query
            strategy: Expansion strategy to use
            cache_provider: Optional cache provider

        Returns:
            ExpansionResult with best query and expansion tree
        """
        start_time = time.time()

        # Note: Cache support for iterative expansion can be added later
        # by extending CacheProvider with get_iterative_expansion() method
        # For now, we skip caching to avoid interface mismatch

        # Determine actual strategy based on query complexity
        if strategy == ExpansionStrategy.ADAPTIVE:
            strategy = await self._assess_query_complexity(query)

        if strategy == ExpansionStrategy.SINGLE:
            return await self._single_round_expansion_with_timeout(query, start_time)

        # Multi-round iterative expansion with timeout protection
        expansion_tree: Dict[str, List[str]] = {query: []}
        all_queries: List[ExpandedQuery] = []

        # Helper to check timeout
        def check_timeout() -> bool:
            elapsed = time.time() - start_time
            if elapsed > EXPANSION_TOTAL_TIMEOUT:
                logger.warning(f"Expansion timeout after {elapsed:.1f}s, using fallback")
                return True
            return False

        # =====================================================================
        # Round 1: Initial Expansion
        # =====================================================================
        logger.info(f"[Round 1] Starting initial expansion for: {query[:50]}...")

        try:
            round1_queries = await asyncio.wait_for(
                self._expand_round1(query),
                timeout=EXPANSION_CALL_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"Round 1 expansion timeout, using original query")
            return self._create_fallback_result(query, "Round 1 timeout")

        if check_timeout():
            return self._create_fallback_result(query, "Total timeout after Round 1")

        expansion_tree[query] = [q.text for q in round1_queries]
        all_queries.extend(round1_queries)

        logger.info(f"[Round 1] Generated {len(round1_queries)} expanded queries in {time.time() - start_time:.1f}s")

        if self.max_rounds == 1:
            # Single round, skip scoring for speed - just use first query
            return ExpansionResult(
                original_query=query,
                best_query=round1_queries[0].text if round1_queries else query,
                final_queries=[q.text for q in round1_queries] if round1_queries else [query],
                expansion_tree=expansion_tree,
                quality_scores={},
                total_rounds=1,
                strategy_used="single",
                reasoning="Single round expansion (fast mode)"
            )

        # =====================================================================
        # Round 2: Refinement Expansion (with timeout protection)
        # =====================================================================
        logger.info(f"[Round 2] Starting refinement expansion...")

        if check_timeout():
            # Timeout - skip Round 2, return Round 1 results
            return ExpansionResult(
                original_query=query,
                best_query=round1_queries[0].text if round1_queries else query,
                final_queries=[q.text for q in round1_queries[:3]],
                expansion_tree=expansion_tree,
                quality_scores={},
                total_rounds=1,
                strategy_used="iterative_partial",
                reasoning="Timeout before Round 2, using Round 1 results"
            )

        # Skip scoring to save time - just take top 2 queries by position
        # (LLM scoring adds 30s+ per call)
        top_queries = round1_queries[:2]

        try:
            round2_queries = await asyncio.wait_for(
                self._expand_round2(query, top_queries),
                timeout=EXPANSION_CALL_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"Round 2 expansion timeout, using Round 1 results")
            return ExpansionResult(
                original_query=query,
                best_query=round1_queries[0].text if round1_queries else query,
                final_queries=[q.text for q in round1_queries[:3]],
                expansion_tree=expansion_tree,
                quality_scores={},
                total_rounds=1,
                strategy_used="iterative_partial",
                reasoning="Round 2 timeout, using Round 1 results"
            )

        for q in round2_queries:
            if q.parent_query:
                if q.parent_query not in expansion_tree:
                    expansion_tree[q.parent_query] = []
                expansion_tree[q.parent_query].append(q.text)

        all_queries.extend(round2_queries)
        logger.info(f"[Round 2] Generated {len(round2_queries)} refined queries in {time.time() - start_time:.1f}s total")

        if self.max_rounds == 2:
            # Skip final scoring/selection for speed - use first refined query
            best = round2_queries[0].text if round2_queries else (round1_queries[0].text if round1_queries else query)
            return ExpansionResult(
                original_query=query,
                best_query=best,
                final_queries=[q.text for q in round2_queries[:3]] + [q.text for q in round1_queries[:2]],
                expansion_tree=expansion_tree,
                quality_scores={},
                total_rounds=2,
                strategy_used="iterative",
                reasoning="Two-round expansion (fast mode, no scoring)"
            )

        # =====================================================================
        # Round 3: Final Refinement (optional, with timeout protection)
        # =====================================================================
        logger.info(f"[Round 3] Starting final refinement...")

        if check_timeout():
            # Timeout - skip Round 3, return Round 2 results
            best = round2_queries[0].text if round2_queries else query
            return ExpansionResult(
                original_query=query,
                best_query=best,
                final_queries=[q.text for q in round2_queries[:3]] + [q.text for q in round1_queries[:2]],
                expansion_tree=expansion_tree,
                quality_scores={},
                total_rounds=2,
                strategy_used="iterative_partial",
                reasoning="Timeout before Round 3, using Round 2 results"
            )

        # Skip scoring, take top 2 from round 2
        top_round2 = round2_queries[:2]

        try:
            round3_queries = await asyncio.wait_for(
                self._expand_round2(query, top_round2),  # Reuse round2 logic
                timeout=EXPANSION_CALL_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"Round 3 expansion timeout, using Round 2 results")
            best = round2_queries[0].text if round2_queries else query
            return ExpansionResult(
                original_query=query,
                best_query=best,
                final_queries=[q.text for q in round2_queries[:3]],
                expansion_tree=expansion_tree,
                quality_scores={},
                total_rounds=2,
                strategy_used="iterative_partial",
                reasoning="Round 3 timeout, using Round 2 results"
            )

        for q in round3_queries:
            q.round_number = 3
            if q.parent_query:
                if q.parent_query not in expansion_tree:
                    expansion_tree[q.parent_query] = []
                expansion_tree[q.parent_query].append(q.text)

        all_queries.extend(round3_queries)
        logger.info(f"[Round 3] Generated {len(round3_queries)} final refined queries in {time.time() - start_time:.1f}s total")

        # Return without final scoring for speed
        best = round3_queries[0].text if round3_queries else (round2_queries[0].text if round2_queries else query)
        return ExpansionResult(
            original_query=query,
            best_query=best,
            final_queries=[q.text for q in round3_queries[:2]] + [q.text for q in round2_queries[:2]] + [q.text for q in round1_queries[:1]],
            expansion_tree=expansion_tree,
            quality_scores={},
            total_rounds=3,
            strategy_used="iterative",
            reasoning="Three-round expansion (fast mode, no scoring)"
        )

    async def _expand_round1(self, query: str) -> List[ExpandedQuery]:
        """Perform round 1 expansion - initial query decomposition"""
        prompt = self.ROUND1_EXPANSION_PROMPT.format(
            original_query=query,
            expansion_count=self.queries_per_round
        )

        messages = [
            {"role": "system", "content": "You are an expert RAG query optimizer."},
            {"role": "user", "content": prompt}
        ]

        try:
            response = await self.llm_client.get_chat_completion(
                messages=messages,
                temperature=self.expansion_temperature
            )

            llm_output = response['choices'][0]['message']['content']
            result = self._parse_json_response(llm_output)

            expanded_queries = []
            for item in result.get("expanded_queries", []):
                expanded_queries.append(ExpandedQuery(
                    text=item.get("query", ""),
                    round_number=1,
                    parent_query=query,
                    reasoning=item.get("perspective", "")
                ))

            return expanded_queries

        except Exception as e:
            logger.error(f"Error in round 1 expansion: {str(e)}")
            return [ExpandedQuery(text=query, round_number=1, parent_query=None)]

    async def _expand_round2(
        self,
        original_query: str,
        parent_queries: List[ExpandedQuery]
    ) -> List[ExpandedQuery]:
        """Perform round 2 expansion - refinement of selected queries"""
        round1_queries_text = "\n".join([
            f"- {q.text}" for q in parent_queries
        ])

        prompt = self.ROUND2_REFINEMENT_PROMPT.format(
            original_query=original_query,
            round1_queries=round1_queries_text
        )

        messages = [
            {"role": "system", "content": "You are an expert RAG query optimizer."},
            {"role": "user", "content": prompt}
        ]

        try:
            response = await self.llm_client.get_chat_completion(
                messages=messages,
                temperature=self.expansion_temperature
            )

            llm_output = response['choices'][0]['message']['content']
            result = self._parse_json_response(llm_output)

            refined_queries = []
            for item in result.get("refined_queries", []):
                parent = item.get("parent_query", "")
                for refined in item.get("refined_versions", []):
                    refined_queries.append(ExpandedQuery(
                        text=refined,
                        round_number=2,
                        parent_query=parent,
                        reasoning=item.get("refinement_reasoning", "")
                    ))

            return refined_queries

        except Exception as e:
            logger.error(f"Error in round 2 expansion: {str(e)}")
            return parent_queries  # Return parent queries as fallback

    async def _score_queries(
        self,
        original_query: str,
        queries: List[ExpandedQuery]
    ) -> List[ExpandedQuery]:
        """Score queries using LLM-based evaluation"""
        queries_text = "\n".join([
            f"{i+1}. {q.text}" for i, q in enumerate(queries)
        ])

        prompt = self.QUERY_SCORING_PROMPT.format(
            original_query=original_query,
            queries_to_score=queries_text
        )

        messages = [
            {"role": "system", "content": "You are an expert query quality evaluator."},
            {"role": "user", "content": prompt}
        ]

        try:
            response = await self.llm_client.get_chat_completion(
                messages=messages,
                temperature=0.3  # Low temperature for consistent scoring
            )

            llm_output = response['choices'][0]['message']['content']
            result = self._parse_json_response(llm_output)

            # Update query scores
            scored_items = result.get("scored_queries", [])
            query_map = {q.text: q for q in queries}

            for item in scored_items:
                query_text = item.get("query", "")
                if query_text in query_map:
                    query_map[query_text].quality_score = item.get("overall_score", 0.5)
                    query_map[query_text].dimensions = item.get("scores", {})
                    query_map[query_text].reasoning = item.get("reasoning", "")

            # Sort by score
            return sorted(queries, key=lambda x: x.quality_score, reverse=True)

        except Exception as e:
            logger.error(f"Error scoring queries: {str(e)}")
            return queries  # Return unsorted

    async def _select_best_query(
        self,
        original_query: str,
        candidates: List[ExpandedQuery]
    ) -> Tuple[str, str]:
        """Select the best query from candidates using LLM"""
        candidates_text = "\n".join([
            f"- Query: {q.text}\n  Score: {q.quality_score:.2f}\n  Reasoning: {q.reasoning}"
            for q in candidates[:5]  # Limit to top 5
        ])

        prompt = self.BEST_QUERY_SELECTION_PROMPT.format(
            original_query=original_query,
            candidate_queries=candidates_text
        )

        messages = [
            {"role": "system", "content": "You are an expert query selection specialist."},
            {"role": "user", "content": prompt}
        ]

        try:
            response = await self.llm_client.get_chat_completion(
                messages=messages,
                temperature=0.3
            )

            llm_output = response['choices'][0]['message']['content']
            result = self._parse_json_response(llm_output)

            selected = result.get("selected_query", candidates[0].text if candidates else original_query)
            reasoning = result.get("selection_reasoning", "")

            return selected, reasoning

        except Exception as e:
            logger.error(f"Error selecting best query: {str(e)}")
            # Fallback to highest scored
            if candidates:
                return candidates[0].text, "Selected by highest score (fallback)"
            return original_query, "Using original query (fallback)"

    async def _finalize_expansion(
        self,
        original_query: str,
        all_queries: List[ExpandedQuery],
        expansion_tree: Dict[str, List[str]],
        total_rounds: int
    ) -> ExpansionResult:
        """Finalize expansion and select best query"""
        # Score all queries if not already scored
        if self.enable_scoring:
            all_queries = await self._score_queries(original_query, all_queries)

        # Select best query
        best_query, selection_reasoning = await self._select_best_query(
            original_query,
            all_queries
        )

        # Get final queries (top N by score)
        final_queries = [q.text for q in all_queries[:5]]
        if best_query not in final_queries:
            final_queries.insert(0, best_query)

        # Build quality scores dict
        quality_scores = {q.text: q.quality_score for q in all_queries}

        logger.info(
            f"Expansion finalized: {total_rounds} rounds, "
            f"{len(all_queries)} total queries, "
            f"best query score: {quality_scores.get(best_query, 0):.2f}"
        )

        return ExpansionResult(
            original_query=original_query,
            best_query=best_query,
            final_queries=final_queries,
            expansion_tree=expansion_tree,
            quality_scores=quality_scores,
            total_rounds=total_rounds,
            strategy_used="iterative",
            reasoning=selection_reasoning,
            metadata={
                "total_expanded": len(all_queries),
                "pruning_threshold": self.pruning_threshold
            }
        )

    def _create_fallback_result(self, query: str, reason: str) -> ExpansionResult:
        """Create a fallback result when expansion fails or times out"""
        logger.info(f"Using fallback result: {reason}")
        return ExpansionResult(
            original_query=query,
            best_query=query,
            final_queries=[query],
            expansion_tree={query: []},
            quality_scores={},
            total_rounds=0,
            strategy_used="fallback",
            reasoning=reason
        )

    async def _single_round_expansion_with_timeout(self, query: str, start_time: float) -> ExpansionResult:
        """Single-round expansion with timeout protection (fast mode)"""
        try:
            queries = await asyncio.wait_for(
                self._expand_round1(query),
                timeout=EXPANSION_CALL_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"Single round expansion timeout, using original query")
            return self._create_fallback_result(query, "Single round expansion timeout")

        # Skip scoring for speed in fast mode
        return ExpansionResult(
            original_query=query,
            best_query=queries[0].text if queries else query,
            final_queries=[q.text for q in queries] if queries else [query],
            expansion_tree={query: [q.text for q in queries]} if queries else {query: []},
            quality_scores={},
            total_rounds=1,
            strategy_used="single",
            reasoning="Single-round expansion (fast mode, no scoring)"
        )

    async def _single_round_expansion(self, query: str) -> ExpansionResult:
        """Fallback to single-round expansion for simple queries (legacy)"""
        queries = await self._expand_round1(query)

        # Skip scoring for speed
        return ExpansionResult(
            original_query=query,
            best_query=queries[0].text if queries else query,
            final_queries=[q.text for q in queries],
            expansion_tree={query: [q.text for q in queries]},
            quality_scores={},
            total_rounds=1,
            strategy_used="single",
            reasoning="Single-round expansion used"
        )

    async def _assess_query_complexity(self, query: str) -> ExpansionStrategy:
        """Assess query complexity to determine expansion strategy"""
        # Simple heuristics for now
        query_length = len(query)
        word_count = len(query.split())

        # Short, simple queries benefit from iterative expansion
        if word_count <= 5 or query_length <= 30:
            return ExpansionStrategy.ITERATIVE

        # Very long, detailed queries may not need much expansion
        if word_count > 30 or query_length > 200:
            return ExpansionStrategy.SINGLE

        return ExpansionStrategy.ITERATIVE

    # =========================================================================
    # Summary/Intent Detection Methods (consolidated from query_enhancement_service)
    # =========================================================================

    def detect_summary_intent(self, query: str) -> bool:
        """
        Detect if the query is asking for a summary

        Args:
            query: User query

        Returns:
            bool: True if summary intent detected
        """
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in self.SUMMARY_KEYWORDS)

    def detect_multi_file_intent_legacy(self, query: str) -> bool:
        """
        [LEGACY] Detect if the query is asking about multiple files using hard-coded keywords

        This is the original implementation preserved for rollback capability.

        Args:
            query: User query

        Returns:
            bool: True if multi-file intent detected
        """
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in self.MULTI_FILE_KEYWORDS)

    def detect_multi_file_intent(self, query: str) -> bool:
        """
        Detect if the query is asking about multiple files

        This is kept for backward compatibility but now calls legacy method directly.
        Should not be used for file_count aware detection - use detect_multi_file_summary_intent instead.

        Args:
            query: User query

        Returns:
            bool: True if multi-file intent detected
        """
        return self.detect_multi_file_intent_legacy(query)

    def detect_multi_file_summary_intent(self, query: str, file_count: int) -> bool:
        """
        Detect if this is a multi-file summary request that should use overview shortcut

        This is for the "brute force" solution: when user asks to summarize/explain
        multiple files, we skip FAISS and directly use document overviews from SQLite.

        NEW: Now supports regex-based pattern detection with feature flag control

        Args:
            query: User query
            file_count: Number of files selected

        Returns:
            bool: True if should use overview shortcut
        """
        # Protection: Single file always returns False
        if file_count < 2:
            return False

        # Summary intent detection (always use legacy for stability)
        is_summary = self.detect_summary_intent(query)

        # Multi-file intent detection (controlled by feature flag)
        if self.USE_NEW_INTENT_DETECTION:
            # =========================================================
            # NEW: Use regex-based pattern detection
            # =========================================================
            try:
                from app.Services.query_intent_detection.integration import (
                    detect_multi_file_intent,
                    detect_multi_file_intent_detailed
                )

                # Get detailed result for logging
                detailed_result = detect_multi_file_intent_detailed(query, file_count)
                is_multi_file = detailed_result['is_multi_file']

                # Log detection details for monitoring
                if is_multi_file:
                    logger.info(
                        f"[NEW_INTENT_DETECTION] Multi-file detected | "
                        f"Query: '{query[:50]}...' | "
                        f"Layer: {detailed_result['detection_layer']} | "
                        f"Confidence: {detailed_result['confidence']:.2f} | "
                        f"Patterns: {detailed_result['matched_patterns']}"
                    )

                # Optional: Log comparison with legacy method for monitoring
                if logger.isEnabledFor(logging.DEBUG):
                    legacy_result = self.detect_multi_file_intent_legacy(query)
                    if legacy_result != is_multi_file:
                        logger.warning(
                            f"[INTENT_MISMATCH] Query: '{query}' | "
                            f"Legacy: {legacy_result}, New: {is_multi_file}"
                        )

            except Exception as e:
                # =========================================================
                # Automatic fallback to legacy if new system fails
                # =========================================================
                logger.error(
                    f"[NEW_INTENT_DETECTION_ERROR] Failed to use new detection: {e}. "
                    f"Falling back to legacy method."
                )
                is_multi_file = self.detect_multi_file_intent_legacy(query)

        else:
            # =========================================================
            # LEGACY: Use hard-coded keywords (for rollback)
            # =========================================================
            is_multi_file = self.detect_multi_file_intent_legacy(query)
            logger.debug(f"[LEGACY_DETECTION] Using hard-coded keywords | Result: {is_multi_file}")

        # Trigger shortcut if: (summary keywords) OR (multi-file keywords with 2+ files)
        return is_summary or is_multi_file

    def get_query_metadata(self, query: str, file_count: int = 1) -> Dict[str, Any]:
        """
        Extract metadata about the query intent

        Args:
            query: User query
            file_count: Number of files selected (default 1)

        Returns:
            Dict with metadata:
            - is_summary: bool - Whether query asks for summary
            - is_multi_file_summary: bool - Whether to use overview shortcut
            - intent_type: str - "summary", "multi_file_summary", "question"
        """
        is_summary = self.detect_summary_intent(query)
        is_multi_file_summary = self.detect_multi_file_summary_intent(query, file_count)

        # Determine intent type
        if is_multi_file_summary:
            intent_type = "multi_file_summary"
        elif is_summary:
            intent_type = "summary"
        else:
            intent_type = "question"

        return {
            "is_summary": is_summary,
            "is_multi_file_summary": is_multi_file_summary,
            "intent_type": intent_type
        }

    def _parse_json_response(self, llm_output: str) -> Dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code blocks"""
        content = llm_output.strip()

        # Remove markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            json_lines = []
            in_code_block = False

            for line in lines:
                if line.strip().startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block or (not line.strip().startswith("```")):
                    json_lines.append(line)

            content = "\n".join(json_lines)

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {content[:200]}...")
            # Try to extract JSON from mixed content
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except:
                    pass
            return {}


# =========================================================================
# Dependency Injection Helper
# =========================================================================

def get_iterative_query_expansion_service(
    llm_client=None,
    max_rounds: int = None,
    queries_per_round: int = None
) -> IterativeQueryExpansionService:
    """
    FastAPI dependency for Iterative Query Expansion Service

    Args:
        llm_client: LLM provider client (will be injected by FastAPI)
        max_rounds: Override max rounds from settings
        queries_per_round: Override queries per round from settings

    Returns:
        IterativeQueryExpansionService: Initialized service instance
    """
    from app.Providers.llm_provider.client import get_llm_provider
    from app.core.config import settings

    if llm_client is None:
        llm_client = get_llm_provider()

    return IterativeQueryExpansionService(
        llm_provider_client=llm_client,
        max_rounds=max_rounds or getattr(settings, 'ITERATIVE_EXPANSION_ROUNDS', 2),
        queries_per_round=queries_per_round or getattr(settings, 'EXPANSION_COUNT', 3),
        pruning_threshold=getattr(settings, 'EXPANSION_PRUNING_THRESHOLD', 0.6),
        enable_scoring=getattr(settings, 'ENABLE_EXPANSION_SCORING', True)
    )
