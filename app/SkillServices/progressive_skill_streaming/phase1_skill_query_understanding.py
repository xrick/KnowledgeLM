#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 1: Skill Query Understanding & Concept Extraction

Adapted from OPMP Phase 1 for DocAI Skill-Based system.
Analyzes user queries for document Q&A instead of product search.

Changes from Original OPMP:
- Product extraction → Document concept extraction
- Model types → Document keywords
- Key features → Key topics/concepts
- User focus → Query intent (explanation, comparison, specific fact)

Update 2025-12-26:
- Added conversational intent detection (LLM-based)
- Support for detecting translation, follow-up, and summarization requests
- Skip RAG retrieval for conversational queries that reference chat history

Author: Claude (SuperClaude)
Date: 2025-12-06
Updated: 2025-12-26 - Conversational intent detection
Based on: OPMP Phase 1 (2025-10-01)
"""

import json
import logging
import re
from typing import Dict, Any, AsyncGenerator, List, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)


# =============================================================================
# Conversational Intent Detection Prompt (LLM-based, not rule-based)
# =============================================================================
CONVERSATIONAL_INTENT_PROMPT = """Analyze if this query is a conversational request that refers to previous chat history, or a document query that needs RAG retrieval.

User Query: {user_query}
Has Chat History: {has_history}

**Conversational requests** (is_conversational=true) include:
- Translation requests: 翻譯, translate, 用英文, 用中文, in English, in Chinese
- References to previous response: 上一個, 前一個, 剛才, previous, last response, what you said
- Follow-up questions: 繼續, 再說, 詳細一點, more about that, elaborate, continue
- Summarization of previous: 總結剛才, summarize what you said, recap
- Clarification requests: 什麼意思, 再解釋, what do you mean, explain again

**Document queries** (is_conversational=false) include:
- Questions about document content: What is X? How does Y work?
- Requests for specific information from documents
- New topics not referencing previous conversation

Important: If has_history is false but query seems conversational, set is_conversational=false (no history to refer to).

Respond with JSON only:
{{
  "is_conversational": true/false,
  "conversational_type": "translation|follow_up|summarize|clarify|none",
  "confidence": 0.0-1.0,
  "reason": "brief explanation"
}}
"""


# Prompt template for Skill Query Understanding
SKILL_QUERY_UNDERSTANDING_PROMPT = """You are an expert document analysis assistant. Analyze the following user query for document Q&A.

User Query: {user_query}
Selected Documents: {selected_documents}

Respond in JSON format with the following fields:
{{
  "intent": "explanation|comparison|fact_query|general_inquiry",
  "key_concepts": ["concept1", "concept2", "concept3"],
  "document_keywords": ["keyword1", "keyword2"],
  "query_focus": "definition|how-to|why|comparison|specific_data",
  "complexity": "simple|medium|complex"
}}

Only respond with JSON, no other explanation.
"""


class SkillQueryUnderstanding:
    """
    Phase 1: Skill Query Understanding & Concept Extraction

    Adapted from OPMP Phase 1 for document Q&A workflow.

    Extracts:
    - Intent (explanation, comparison, fact_query, general_inquiry)
    - Key concepts from the query
    - Document keywords for enhanced retrieval
    - Query focus (definition, how-to, why, comparison, specific_data)
    - Query complexity (simple, medium, complex)

    Features:
    - Fast-path keyword extraction (no LLM for simple queries)
    - LLM-based analysis for complex queries
    - In-memory LRU cache (fallback to Redis if available)
    - Progressive streaming of results
    """

    def __init__(self, llm: Any = None, cache: Optional[Any] = None):
        """
        Initialize Phase 1 processor

        Args:
            llm: LangChain LLM instance (optional, only for complex queries)
            cache: Optional cache instance (Redis or in-memory LRU)
        """
        self.llm = llm
        self.cache = cache

        # Regex patterns for fast-path extraction
        self.concept_patterns = {
            "definition": re.compile(
                r'(什麼是|什么是|定義|定义|meaning|definition|what is|explain)',
                re.IGNORECASE
            ),
            "comparison": re.compile(
                r'(比較|比较|差異|差异|對比|对比|vs|versus|difference|compare)',
                re.IGNORECASE
            ),
            "how_to": re.compile(
                r'(如何|怎麼|怎么|how to|how do|步驟|步骤|method|way to)',
                re.IGNORECASE
            ),
            "why": re.compile(
                r'(為什麼|为什么|原因|why|reason|because)',
                re.IGNORECASE
            ),
            "list": re.compile(
                r'(列出|列举|哪些|which|list|enumerate|種類|种类|types)',
                re.IGNORECASE
            )
        }

        # Conversational intent patterns (fast-path detection before LLM)
        self.conversational_patterns = {
            "translation": re.compile(
                r'(翻譯|翻译|translate|用英文|用中文|in english|in chinese|英譯|中譯)',
                re.IGNORECASE
            ),
            "previous_reference": re.compile(
                r'(上一個|前一個|剛才|剛剛|previous|last response|what you said|你說的|你剛才)',
                re.IGNORECASE
            ),
            "follow_up": re.compile(
                r'(繼續|再說|詳細一點|more about|elaborate|continue|go on|展開|深入)',
                re.IGNORECASE
            ),
            "summarize": re.compile(
                r'(總結|摘要|summarize|recap|sum up|歸納)',
                re.IGNORECASE
            ),
            "clarify": re.compile(
                r'(什麼意思|再解釋|what do you mean|explain again|不懂|clarify)',
                re.IGNORECASE
            )
        }

        logger.info("SkillQueryUnderstanding initialized (OPMP Phase 1 adapted + conversational detection)")

    async def process(
        self,
        query: str,
        selected_documents: List[str],
        has_chat_history: bool = False  # NEW: For conversational intent detection
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process query and extract understanding

        Args:
            query: User query string
            selected_documents: List of selected document names
            has_chat_history: Whether chat history is available (for conversational detection)

        Yields:
            Progress updates and final phase result
        """
        try:
            # Progress update
            yield {
                "type": "progress",
                "phase": 1,
                "message": "正在分析您的查詢...",
                "progress": 10
            }

            # =========================================================
            # NEW: Detect conversational intent FIRST (before RAG)
            # =========================================================
            conversational_result = await self._detect_conversational_intent(
                query,
                has_chat_history
            )
            is_conversational = conversational_result.get("is_conversational", False)
            conversational_type = conversational_result.get("conversational_type", "none")

            if is_conversational:
                logger.info(f"🗣️ Conversational query detected: type={conversational_type}, query={query[:30]}")

            # Check cache first (in-memory LRU or Redis)
            if self.cache:
                cached = await self._get_cached_analysis(query)
                if cached:
                    # Merge conversational detection with cached result
                    cached["is_conversational"] = is_conversational
                    cached["conversational_type"] = conversational_type

                    logger.info(f"Phase 1 cache hit for query: {query[:30]}")
                    yield {
                        "type": "progress",
                        "phase": 1,
                        "message": "解析問題中...",
                        "progress": 20
                    }
                    yield {
                        "type": "phase_result",
                        "phase": 1,
                        "data": cached,
                        "progress": 20,
                        "from_cache": True
                    }
                    return

            # Try fast path first (keyword-based extraction, no LLM)
            fast_result = self._fast_path_analysis(query, selected_documents)

            # If fast path gives high confidence, use it
            if fast_result and fast_result.get("confidence") == "high":
                # Merge conversational detection
                fast_result["is_conversational"] = is_conversational
                fast_result["conversational_type"] = conversational_type

                logger.info(f"Phase 1 fast path success for query: {query[:30]}")
                yield {
                    "type": "progress",
                    "phase": 1,
                    "message": "解析問題中...",
                    "progress": 20
                }

                # Cache result
                if self.cache:
                    await self._cache_analysis(query, fast_result)

                yield {
                    "type": "phase_result",
                    "phase": 1,
                    "data": fast_result,
                    "progress": 20
                }
                return

            # LLM-based extraction (only for complex queries)
            if self.llm and (not fast_result or fast_result.get("complexity") == "complex"):
                logger.info(f"Phase 1 using LLM for query: {query[:30]}")
                llm_result = await self._llm_analysis(query, selected_documents)

                # Merge conversational detection
                llm_result["is_conversational"] = is_conversational
                llm_result["conversational_type"] = conversational_type

                yield {
                    "type": "progress",
                    "phase": 1,
                    "message": "解析問題中...",
                    "progress": 20
                }

                # Cache result
                if self.cache:
                    await self._cache_analysis(query, llm_result)

                yield {
                    "type": "phase_result",
                    "phase": 1,
                    "data": llm_result,
                    "progress": 20
                }
                return

            # Fallback: Use fast path result even if low confidence
            final_result = fast_result or self._fallback_analysis(query)
            # Merge conversational detection
            final_result["is_conversational"] = is_conversational
            final_result["conversational_type"] = conversational_type

            yield {
                "type": "progress",
                "phase": 1,
                "message": "解析問題中...",
                "progress": 20
            }

            yield {
                "type": "phase_result",
                "phase": 1,
                "data": final_result,
                "progress": 20
            }

        except Exception as e:
            logger.error(f"Phase 1 error: {e}")
            # Return fallback result
            fallback_result = self._fallback_analysis(query)
            fallback_result["is_conversational"] = False
            fallback_result["conversational_type"] = "none"
            yield {
                "type": "phase_result",
                "phase": 1,
                "data": fallback_result,
                "progress": 20,
                "error": str(e)
            }

    def _fast_path_analysis(
        self,
        query: str,
        selected_documents: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Fast path analysis using keyword patterns (no LLM)

        Args:
            query: User query
            selected_documents: Selected document names

        Returns:
            Analysis result or None if fast path not applicable
        """
        # Determine query focus from patterns
        query_focus = "general"
        intent = "general_inquiry"

        if self.concept_patterns["definition"].search(query):
            query_focus = "definition"
            intent = "explanation"
        elif self.concept_patterns["comparison"].search(query):
            query_focus = "comparison"
            intent = "comparison"
        elif self.concept_patterns["how_to"].search(query):
            query_focus = "how-to"
            intent = "explanation"
        elif self.concept_patterns["why"].search(query):
            query_focus = "why"
            intent = "explanation"
        elif self.concept_patterns["list"].search(query):
            query_focus = "list"
            intent = "fact_query"

        # Extract key concepts (nouns/keywords)
        key_concepts = self._extract_keywords(query)

        # Determine complexity
        complexity = "simple"
        query_length = len(query)
        if query_length > 100 or len(key_concepts) > 5:
            complexity = "complex"
        elif query_length > 50 or len(key_concepts) > 3:
            complexity = "medium"

        result = {
            "intent": intent,
            "key_concepts": key_concepts[:5],  # Top 5 concepts
            "document_keywords": key_concepts[:3],  # Top 3 for retrieval
            "query_focus": query_focus,
            "complexity": complexity,
            "selected_documents": selected_documents,
            "confidence": "high" if query_focus != "general" else "medium"
        }

        return result

    @lru_cache(maxsize=100)
    def _extract_keywords(self, query: str) -> List[str]:
        """
        Extract keywords from query using simple heuristics

        Args:
            query: User query string

        Returns:
            List of extracted keywords
        """
        # Remove common question words
        stop_words = {
            "什麼", "什么", "如何", "怎麼", "怎么", "為什麼", "为什么",
            "是", "的", "了", "嗎", "吗", "呢", "啊", "吧",
            "what", "how", "why", "is", "are", "the", "a", "an"
        }

        # Split into words and filter
        words = re.findall(r'[\w]+', query, re.UNICODE)
        keywords = [
            w for w in words
            if len(w) > 1 and w not in stop_words
        ]

        return keywords[:10]  # Return top 10

    async def _llm_analysis(
        self,
        query: str,
        selected_documents: List[str]
    ) -> Dict[str, Any]:
        """
        LLM-based analysis for complex queries

        Args:
            query: User query
            selected_documents: Selected document names

        Returns:
            Analysis result
        """
        # Prepare prompt
        prompt = SKILL_QUERY_UNDERSTANDING_PROMPT.format(
            user_query=query,
            selected_documents=", ".join(selected_documents[:10])
        )

        # Call LLM
        try:
            import asyncio
            response = await asyncio.to_thread(self.llm.invoke, prompt)

            # Parse response
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)

            # Extract JSON from response
            analysis = self._parse_json_response(response_text)

            if analysis:
                # Add selected documents
                analysis["selected_documents"] = selected_documents
                return analysis
            else:
                logger.warning("Failed to parse LLM response, using fallback")
                return self._fallback_analysis(query)

        except Exception as e:
            logger.error(f"LLM analysis error: {e}")
            return self._fallback_analysis(query)

    def _parse_json_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response"""
        try:
            # Try direct JSON parsing
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

            # Try to find JSON object in text
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass

        return None

    def _fallback_analysis(self, query: str) -> Dict[str, Any]:
        """
        Fallback analysis when all methods fail

        Args:
            query: User query

        Returns:
            Basic analysis result
        """
        return {
            "intent": "general_inquiry",
            "key_concepts": self._extract_keywords(query)[:3],
            "document_keywords": self._extract_keywords(query)[:2],
            "query_focus": "general",
            "complexity": "medium",
            "selected_documents": [],
            "confidence": "low"
        }

    async def _get_cached_analysis(self, query: str) -> Optional[Dict[str, Any]]:
        """Get cached analysis from cache (Redis or in-memory)"""
        if not self.cache:
            return None

        try:
            import hashlib
            query_hash = hashlib.md5(query.encode()).hexdigest()
            cache_key = f"skill_phase1:{query_hash}"

            # Try Redis async method
            if hasattr(self.cache, 'get_async'):
                cached = await self.cache.get_async(cache_key)
            # Try synchronous method (wrap in asyncio.to_thread)
            elif hasattr(self.cache, 'get'):
                import asyncio
                cached = await asyncio.to_thread(self.cache.get, cache_key)
            else:
                return None

            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")

        return None

    async def _cache_analysis(self, query: str, analysis: Dict[str, Any]) -> None:
        """Cache analysis to Redis or in-memory"""
        if not self.cache:
            return

        try:
            import hashlib
            query_hash = hashlib.md5(query.encode()).hexdigest()
            cache_key = f"skill_phase1:{query_hash}"

            # Try Redis async method
            if hasattr(self.cache, 'set_async'):
                await self.cache.set_async(
                    cache_key,
                    json.dumps(analysis, ensure_ascii=False),
                    ttl=300  # 5 minutes
                )
            # Try synchronous method (wrap in asyncio.to_thread)
            elif hasattr(self.cache, 'set'):
                import asyncio
                await asyncio.to_thread(
                    self.cache.set,
                    cache_key,
                    json.dumps(analysis, ensure_ascii=False),
                    300  # 5 minutes TTL
                )
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    # =========================================================================
    # Conversational Intent Detection (LLM-based, not rule-based)
    # =========================================================================

    async def _detect_conversational_intent(
        self,
        query: str,
        has_chat_history: bool
    ) -> Dict[str, Any]:
        """
        Detect if query is conversational (references chat history, not documents)

        Uses a hybrid approach:
        1. Fast-path: Regex patterns for common conversational keywords
        2. LLM-based: For ambiguous cases, use LLM to determine intent

        Args:
            query: User query
            has_chat_history: Whether chat history is available

        Returns:
            Dict with is_conversational, conversational_type, confidence
        """
        # Default result
        default_result = {
            "is_conversational": False,
            "conversational_type": "none",
            "confidence": 0.0,
            "reason": "no conversational patterns detected"
        }

        # If no chat history, can't be conversational (nothing to refer to)
        if not has_chat_history:
            return default_result

        # =====================================================================
        # Fast-path: Check regex patterns first (no LLM call needed)
        # =====================================================================
        detected_type = None
        for pattern_type, pattern in self.conversational_patterns.items():
            if pattern.search(query):
                detected_type = pattern_type
                break

        # If fast-path detected conversational pattern with high confidence
        if detected_type:
            # Map pattern types to conversational types
            type_mapping = {
                "translation": "translation",
                "previous_reference": "follow_up",
                "follow_up": "follow_up",
                "summarize": "summarize",
                "clarify": "clarify"
            }

            logger.info(f"🗣️ Fast-path conversational detection: {detected_type}")
            return {
                "is_conversational": True,
                "conversational_type": type_mapping.get(detected_type, "follow_up"),
                "confidence": 0.9,
                "reason": f"fast-path pattern match: {detected_type}"
            }

        # =====================================================================
        # LLM-based detection (for ambiguous cases)
        # =====================================================================
        if self.llm:
            try:
                llm_result = await self._llm_conversational_detection(query, has_chat_history)
                if llm_result:
                    return llm_result
            except Exception as e:
                logger.warning(f"LLM conversational detection error: {e}")

        return default_result

    async def _llm_conversational_detection(
        self,
        query: str,
        has_chat_history: bool
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to detect conversational intent (for ambiguous queries)

        Args:
            query: User query
            has_chat_history: Whether chat history exists

        Returns:
            Detection result or None if failed
        """
        try:
            prompt = CONVERSATIONAL_INTENT_PROMPT.format(
                user_query=query,
                has_history=has_chat_history
            )

            # Use LLM's get_chat_completion if available (faster, lower cost)
            if hasattr(self.llm, 'get_chat_completion'):
                response = await self.llm.get_chat_completion([
                    {"role": "user", "content": prompt}
                ])
                if 'choices' in response and len(response['choices']) > 0:
                    response_text = response['choices'][0]['message']['content']
                else:
                    return None
            else:
                # Fallback to invoke
                import asyncio
                response = await asyncio.to_thread(self.llm.invoke, prompt)
                response_text = response.content if hasattr(response, 'content') else str(response)

            # Parse JSON response
            result = self._parse_json_response(response_text)
            if result and "is_conversational" in result:
                logger.info(f"🗣️ LLM conversational detection: {result}")
                return result

        except Exception as e:
            logger.warning(f"LLM conversational detection error: {e}")

        return None
