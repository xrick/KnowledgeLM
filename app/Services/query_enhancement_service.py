# app/Services/query_enhancement_service.py
"""
Query Enhancement Service - Strategy 2: Question Expansion

Two-stage prompt system for enhanced retrieval through query decomposition.

Stage 1 (Prompt1): Analyze user query and expand into 3-5 sub-questions
Stage 2 (Prompt2): Use expanded questions for comprehensive retrieval and answering
"""

import logging
import json
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class QueryEnhancementService:
    """
    Query Enhancement Service implementing Strategy 2

    Workflow:
    1. Receive original user query
    2. Send to LLM with Prompt1 (query analysis)
    3. Parse LLM response to extract expanded questions
    4. Return structured expansion result for retrieval phase
    5. In answering phase, use Prompt2 to integrate all results

    Benefits:
    - Broader retrieval coverage through multiple perspectives
    - Better handling of ambiguous queries
    - More comprehensive answers
    - Query intent detection (summary, question, analysis)
    """

    # Summary detection keywords
    SUMMARY_KEYWORDS = ["摘要", "總結", "概述", "summary", "summarize", "overview", "概括", "簡述", "歸納"]

    # =========================================================================
    # Prompt Templates (Strategy 2)
    # =========================================================================

    QUERY_EXPANSION_PROMPT = """你是一位專業的查詢分析師。請將用戶的查詢分解為3-5個相關的子問題，以幫助更全面地檢索信息。

[原始查詢]
{original_query}

請以 JSON 格式回應：
{{
  "original_query": "{original_query}",
  "intent": "查詢意圖描述",
  "expanded_questions": [
    "子問題1的具體描述",
    "子問題2的具體描述",
    "子問題3的具體描述"
  ],
  "reasoning": "分解邏輯說明"
}}

要求：
1. 子問題應該涵蓋原始查詢的不同角度
2. 每個子問題應該清晰且具體
3. 保持子問題之間的邏輯關聯性
4. 子問題總數控制在3-5個之間"""

    PROMPT_2_QUESTION_EXPANSION = """[原始查詢]
{original_query}

[擴展的子問題]
我們已經將您的問題分解為以下幾個子問題：
{expanded_questions_formatted}

[檢索到的相關文檔片段]
{retrieved_context}

[您的任務]
請基於以上檢索到的文檔片段，完整回答用戶的原始查詢。

**核心原則：這些文檔片段來自用戶在側邊欄勾選的文檔，是你直接而且必須參考的主要資料。**

指導原則：
1. **優先引用文檔**：優先使用檢索到的文檔片段信息，並明確標註來源
2. **智能補充說明**：當需要補充背景知識或專業解釋時，可以使用你的知識，但要明確區分：
   - 文檔內容：「根據您的文檔...」、「文檔中提到...」
   - 補充說明：「補充說明...」、「相關背景...」
3. **整合多個角度**：整合多個子問題的答案，形成完整連貫的回應
4. **誠實評估**：如果文檔片段不足以完整回答，可以：
   - 明確說明：「在您勾選的文檔中，關於XX部分的信息較少」
   - 提供建議：「基於一般理解，我可以補充...」或「建議您勾選其他相關文檔」
5. **準確性優先**：不要編造文檔中不存在的內容

回答時請：
- 先總結主要觀點（基於文檔）
- 提供具體細節（引用文檔來源）
- 必要時補充專業背景知識（明確標註）
- 使用條列式說明提升可讀性

請根據以上檢索結果回答用戶問題："""

    def __init__(self, llm_provider_client, expansion_count: Optional[int] = None):
        """
        Initialize Query Enhancement Service

        Args:
            llm_provider_client: LLM provider client instance
            expansion_count: Number of sub-questions to generate (default from settings)
        """
        from app.core.config import settings

        self.llm_client = llm_provider_client
        self.expansion_count = expansion_count or settings.EXPANSION_COUNT
        self.expansion_temperature = settings.EXPANSION_TEMPERATURE

        logger.info(
            f"Query Enhancement Service initialized "
            f"(expansion_count={self.expansion_count}, temp={self.expansion_temperature})"
        )

    async def expand_query(
        self,
        query: str,
        cache_provider = None
    ) -> Dict[str, Any]:
        """
        Expand user query into sub-questions using LLM

        Stage 1: Query Analysis

        Args:
            query: Original user query
            cache_provider: Optional cache provider for caching expansions

        Returns:
            Dict with keys:
            - original_query: Original query
            - intent: Identified intent
            - expanded_questions: List of sub-questions
            - reasoning: Explanation for expansion

        Example:
            >>> result = await service.expand_query("What is RAG?")
            >>> print(result['expanded_questions'])
            ['What does RAG stand for?', 'How does RAG work?', ...]
        """
        # Check cache first
        if cache_provider:
            cached_result = await cache_provider.get_query_expansion(query)

            if cached_result:
                logger.info(f"Cache hit for query expansion: {query[:50]}...")
                return cached_result

        # Format prompt with user query
        prompt = self.QUERY_EXPANSION_PROMPT.format(original_query=query)

        # Call LLM for query expansion
        messages = [
            {"role": "system", "content": "You are a query analysis expert."},
            {"role": "user", "content": prompt}
        ]

        try:
            response = await self.llm_client.get_chat_completion(
                messages=messages,
                temperature=self.expansion_temperature
            )

            # Parse LLM response
            llm_output = response['choices'][0]['message']['content']

            # Extract JSON from response (handle markdown code blocks)
            expansion_result = self._parse_json_response(llm_output)

            # Validate structure
            if not expansion_result.get("expanded_questions"):
                logger.warning(f"No expanded questions in LLM response, using original query")
                expansion_result = {
                    "original_query": query,
                    "intent": "direct_query",
                    "expanded_questions": [query],
                    "reasoning": "Failed to expand query, using original"
                }

            # Limit number of questions
            if len(expansion_result["expanded_questions"]) > self.expansion_count:
                expansion_result["expanded_questions"] = expansion_result["expanded_questions"][:self.expansion_count]

            logger.info(
                f"Query expansion complete: {query[:50]}... "
                f"-> {len(expansion_result['expanded_questions'])} questions"
            )

            # Cache result
            if cache_provider:
                await cache_provider.set_query_expansion(query, expansion_result)

            return expansion_result

        except Exception as e:
            logger.error(f"Error in query expansion: {str(e)}")

            # Fallback: return original query
            return {
                "original_query": query,
                "intent": "error_fallback",
                "expanded_questions": [query],
                "reasoning": f"Query expansion failed: {str(e)}"
            }

    def _parse_json_response(self, llm_output: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response

        Handles markdown code blocks and extracts JSON content

        Args:
            llm_output: Raw LLM response

        Returns:
            Dict: Parsed JSON object
        """
        # Remove markdown code blocks if present
        content = llm_output.strip()

        if content.startswith("```"):
            # Extract content between ``` markers
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

        # Parse JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {content[:200]}...")
            raise ValueError(f"Invalid JSON response from LLM: {str(e)}")

    def format_expanded_questions(self, expanded_questions: List[str]) -> str:
        """
        Format expanded questions for display in Prompt2

        Args:
            expanded_questions: List of sub-questions

        Returns:
            str: Formatted list of questions
        """
        formatted = []
        for i, question in enumerate(expanded_questions, start=1):
            formatted.append(f"{i}. {question}")

        return "\n".join(formatted)

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

    def get_query_metadata(self, query: str) -> Dict[str, Any]:
        """
        Extract metadata about the query intent

        Args:
            query: User query

        Returns:
            Dict with metadata:
            - is_summary: bool - Whether query asks for summary
            - intent_type: str - "summary", "question", "analysis"
        """
        is_summary = self.detect_summary_intent(query)

        return {
            "is_summary": is_summary,
            "intent_type": "summary" if is_summary else "question"
        }


# Dependency injection helper
def get_query_enhancement_service(llm_client=None):
    """
    FastAPI dependency for Query Enhancement Service

    Args:
        llm_client: LLM provider client (will be injected by FastAPI)

    Returns:
        QueryEnhancementService: Initialized service instance
    """
    from app.Providers.llm_provider.client import get_llm_provider

    if llm_client is None:
        llm_client = get_llm_provider()

    return QueryEnhancementService(llm_client)
