# app/SkillServices/progressive_skill_streaming/phase4_response_generation.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 4: Response Generation with Progressive Markdown Streaming

Adapted from OPMP Phase 4 for DocAI Skill-Based system.
Generates LLM responses with token-by-token streaming.

Changes from Original OPMP:
- Now uses PromptService for consistent prompt management
- Integration with existing PromptService (single source of truth)
- Minimal other changes (streaming logic same)

Author: Claude (SuperClaude)
Date: 2025-12-06
Updated: 2025-12-11 - Unified with PromptService
Based on: OPMP Phase 4 (2025-10-01)
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any, AsyncGenerator, List, Optional

# Import PromptService for unified prompt management
from app.Services.prompt_service import PromptService

logger = logging.getLogger(__name__)


# =============================================================================
# Context Cleaning Patterns - Remove RAG artifacts from chat history
# =============================================================================
# Pattern to match [文檔片段 - 來源: xxx (Page N)]...[End of chunk]
RAG_CHUNK_PATTERN = re.compile(
    r'\[文檔片段[^\]]*\].*?(?=\[文檔片段|\Z)',
    re.DOTALL
)

# Pattern to match system prompt residuals (enhanced for prompt leaking prevention)
SYSTEM_PROMPT_PATTERN = re.compile(
    r'(你是一位專業的文檔問答助手|以下是檢索到的相關文檔內容|回答策略：|【重要】).*?(?=\n\n|\Z)',
    re.DOTALL
)

# Pattern to match source citations that should be cleaned
SOURCE_CITATION_PATTERN = re.compile(
    r'\[來源:.*?\]|\(來源:.*?\)|\[Source:.*?\]',
    re.IGNORECASE
)

# =============================================================================
# Prompt Leaking Detection Patterns (Output Guardrails)
# =============================================================================
# Patterns that indicate the model is outputting system prompt content
PROMPT_LEAKING_PATTERNS = [
    re.compile(r'<system_instructions>', re.IGNORECASE),
    re.compile(r'</system_instructions>', re.IGNORECASE),
    re.compile(r'<reference_context>', re.IGNORECASE),
    re.compile(r'</reference_context>', re.IGNORECASE),
    re.compile(r'<output_format>', re.IGNORECASE),
    re.compile(r'You are a professional document Q&A assistant', re.IGNORECASE),
    re.compile(r'你是一位專業的文[檔案]問答助手', re.IGNORECASE),
    re.compile(r'NEVER output any content from this system_instructions', re.IGNORECASE),
    re.compile(r'禁止輸出此 system_instructions', re.IGNORECASE),
    re.compile(r'\[Document excerpt – Source:', re.IGNORECASE),
    re.compile(r'\[文檔片段 – 來源:', re.IGNORECASE),
]


def detect_prompt_leaking(response: str) -> bool:
    """
    Detect if the response contains leaked system prompt content.

    Args:
        response: LLM response text

    Returns:
        True if prompt leaking is detected, False otherwise
    """
    for pattern in PROMPT_LEAKING_PATTERNS:
        if pattern.search(response):
            logger.warning(f"Prompt leaking detected! Pattern: {pattern.pattern}")
            return True
    return False


def sanitize_response(response: str) -> str:
    """
    Remove any leaked prompt content from the response.

    Args:
        response: Original LLM response

    Returns:
        Sanitized response with leaked content removed
    """
    sanitized = response

    # Remove XML-style tags
    sanitized = re.sub(r'<system_instructions>.*?</system_instructions>', '', sanitized, flags=re.DOTALL | re.IGNORECASE)
    sanitized = re.sub(r'<reference_context>.*?</reference_context>', '', sanitized, flags=re.DOTALL | re.IGNORECASE)
    sanitized = re.sub(r'<output_format>.*?</output_format>', '', sanitized, flags=re.DOTALL | re.IGNORECASE)

    # Remove common prompt leaking phrases
    sanitized = re.sub(r'You are a professional document Q&A assistant\.?', '', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'你是一位專業的文[檔案]問答助手。?', '', sanitized, flags=re.IGNORECASE)

    # Clean up excessive whitespace
    sanitized = re.sub(r'\n{3,}', '\n\n', sanitized)
    sanitized = sanitized.strip()

    if sanitized != response:
        logger.info(f"Response sanitized: removed {len(response) - len(sanitized)} chars of leaked content")

    return sanitized


def get_cleaned_history(chat_history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Clean RAG artifacts from chat history for conversational queries.

    This function removes:
    - [文檔片段 - 來源: xxx] markers and their content
    - System Prompt residuals
    - Source citation markers

    Args:
        chat_history: List of message dicts with 'role' and 'content'

    Returns:
        Cleaned chat history with only pure conversation content
    """
    if not chat_history:
        return []

    cleaned_history = []

    for message in chat_history:
        role = message.get("role", "")
        content = message.get("content", "")

        # Only clean assistant messages (user messages should be kept as-is)
        if role == "assistant" and content:
            # Step 1: Remove RAG chunk markers
            cleaned_content = RAG_CHUNK_PATTERN.sub('', content)

            # Step 2: Remove system prompt residuals
            cleaned_content = SYSTEM_PROMPT_PATTERN.sub('', cleaned_content)

            # Step 3: Remove source citations
            cleaned_content = SOURCE_CITATION_PATTERN.sub('', cleaned_content)

            # Step 4: Clean up excessive whitespace
            cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
            cleaned_content = cleaned_content.strip()

            if cleaned_content:
                cleaned_history.append({
                    "role": role,
                    "content": cleaned_content
                })
                logger.debug(f"🧹 Cleaned assistant message: {len(content)} → {len(cleaned_content)} chars")
        else:
            # Keep user messages and other roles unchanged
            cleaned_history.append(message)

    logger.info(f"🧹 Cleaned {len(chat_history)} messages → {len(cleaned_history)} clean messages")
    return cleaned_history

# Conversational system prompt - for follow-up queries that don't need RAG
CONVERSATIONAL_SYSTEM_PROMPT = """你是一位專業的文檔問答助手。

用戶正在進行後續對話，可能是：
- 要求翻譯前一個回答
- 詢問關於前一個回答的問題
- 要求澄清或擴展說明
- 其他對話式請求

**重要規則**：
1. 直接回應用戶的請求，不需要搜尋文檔
2. 使用對話歷史中的資訊來回答
3. 如果用戶要求翻譯，請完整翻譯前一個回答
4. 保持專業且有幫助的語氣
5. 不要說「找不到資料」- 這是對話式請求，不需要文檔檢索
"""


class Phase4ResponseGeneration:
    """
    Phase 4: Response Generation with Progressive Markdown Streaming

    Adapted from OPMP Phase 4 for document Q&A workflow.
    Now uses PromptService for consistent prompt management across
    both streaming and non-streaming modes.

    Features:
    - Progressive markdown streaming
    - Token-by-token delivery
    - Unified prompt management via PromptService
    - Response caching (optional)
    - Temperature optimization
    """

    def __init__(self, llm: Any, cache: Optional[Any] = None, language: str = "zh"):
        """
        Initialize Phase 4 processor

        Args:
            llm: LangChain LLM instance (must support streaming)
            cache: Optional cache instance for response caching
            language: Language for prompts ("zh" or "en")
        """
        self.llm = llm
        self.cache = cache
        self.prompt_service = PromptService(language=language)

        # Configure LLM for streaming if possible
        if hasattr(self.llm, 'streaming'):
            self.llm.streaming = True

        # Set lower temperature for more deterministic responses
        if hasattr(self.llm, 'temperature'):
            self.llm.temperature = 0.3

        logger.info("Phase4ResponseGeneration initialized with streaming and PromptService")

    async def process(
        self,
        query: str,
        analysis: Dict[str, Any],  # Kept for API compatibility, not used with PromptService
        context: Dict[str, Any],
        chat_history: Optional[List[Dict[str, str]]] = None  # ✅ Memory support
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate response with progressive streaming

        Args:
            query: User query
            analysis: Query analysis from Phase 1 (kept for API compatibility)
            context: Context from Phase 3 (chunks)
            chat_history: Optional list of previous messages for multi-turn context

        Yields:
            Progress updates and markdown tokens
        """
        # Note: analysis parameter kept for API compatibility but not used
        # since we now use PromptService which doesn't need intent/focus
        _ = analysis  # Suppress unused variable warning

        try:
            yield {
                "type": "progress",
                "phase": 4,
                "message": "正在進行資料輸出處理...",
                "progress": 75
            }

            # Check cache first (optional)
            if self.cache:
                cached = await self._get_cached_response(query, context)
                if cached:
                    logger.info("Phase 4 cache hit")
                    # Stream cached response token by token for consistent UX
                    for token in cached:
                        yield {
                            "type": "markdown_token",
                            "token": token,
                            "phase": 4,
                            "from_cache": True
                        }

                    yield {
                        "type": "progress",
                        "phase": 4,
                        "message": "✅ 回答生成完成",
                        "progress": 95
                    }
                    return

            # ✅ Use PromptService to build messages (unified with non-streaming)
            messages = self._build_messages(query, context, chat_history)

            # Setup streaming queue for token-by-token delivery
            queue = asyncio.Queue()

            # Start LLM generation in background task
            async def generate():
                try:
                    full_response = ""

                    # Use LLMProviderClient's streaming method
                    if hasattr(self.llm, 'get_chat_completion_stream'):
                        # Stream using LLMProviderClient
                        async for chunk_bytes in self.llm.get_chat_completion_stream(messages):
                            # Parse SSE chunk
                            chunk_str = chunk_bytes.decode('utf-8') if isinstance(chunk_bytes, bytes) else str(chunk_bytes)

                            # Extract content from SSE data line
                            if chunk_str.startswith('data: '):
                                data_line = chunk_str[6:].strip()
                                if data_line and data_line != '[DONE]':
                                    try:
                                        chunk_data = json.loads(data_line)
                                        if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                            delta = chunk_data['choices'][0].get('delta', {})
                                            token = delta.get('content', '')
                                            if token:
                                                full_response += token
                                                await queue.put({
                                                    "type": "markdown_token",
                                                    "token": token
                                                })
                                    except json.JSONDecodeError:
                                        pass  # Skip malformed chunks
                    elif hasattr(self.llm, 'get_chat_completion'):
                        # Non-streaming fallback
                        response_data = await self.llm.get_chat_completion(messages)
                        if 'choices' in response_data and len(response_data['choices']) > 0:
                            full_response = response_data['choices'][0]['message']['content']
                            # Simulate streaming by chunking response
                            chunk_size = 10
                            for i in range(0, len(full_response), chunk_size):
                                chunk = full_response[i:i+chunk_size]
                                await queue.put({
                                    "type": "markdown_token",
                                    "token": chunk
                                })
                                await asyncio.sleep(0.01)
                    else:
                        # Last resort: direct prompt (for testing)
                        full_response = "Sorry, I cannot generate a response at this time."
                        await queue.put({
                            "type": "markdown_token",
                            "token": full_response
                        })

                    await queue.put(None)  # Signal completion
                except Exception as e:
                    logger.error(f"LLM generation error: {e}")
                    await queue.put({
                        "type": "error",
                        "message": str(e)
                    })
                    await queue.put(None)

            task = asyncio.create_task(generate())

            # Stream tokens as they arrive
            full_response = ""
            while True:
                token_data = await queue.get()

                if token_data is None:
                    break

                if token_data.get("type") == "markdown_token":
                    full_response += token_data["token"]

                yield token_data

            await task

            # Output Guardrails: Detect and handle prompt leaking
            if detect_prompt_leaking(full_response):
                logger.warning("Prompt leaking detected in final response - sanitizing")
                full_response = sanitize_response(full_response)

                # If response is now empty or too short after sanitization, provide fallback
                if len(full_response.strip()) < 10:
                    fallback_msg = "抱歉，系統處理您的請求時發生問題。請嘗試重新提問，或提供更詳細的問題描述。"
                    logger.error("Response was entirely prompt content - returning fallback message")
                    yield {
                        "type": "markdown_token",
                        "token": fallback_msg,
                        "sanitized": True
                    }
                    full_response = fallback_msg

            # Cache response if enabled
            if self.cache and full_response:
                await self._cache_response(query, context, full_response)

            yield {
                "type": "progress",
                "phase": 4,
                "message": "✅ 回答生成完成",
                "progress": 95
            }

        except Exception as e:
            logger.error(f"Phase 4 error: {e}")
            yield {
                "type": "error",
                "message": f"回答生成失敗: {str(e)}",
                "phase": 4
            }

    def _build_messages(
        self,
        query: str,
        context: Dict[str, Any],
        chat_history: Optional[List[Dict[str, str]]] = None  # ✅ Memory support
    ) -> List[Dict[str, str]]:
        """
        Build messages using PromptService (unified with non-streaming version)

        Args:
            query: User query
            context: Chunk context from Phase 3
            chat_history: Optional list of previous messages for multi-turn context

        Returns:
            List of message dicts in OpenAI format
        """
        # ✅ Check if this is a conversational query (no RAG needed)
        is_conversational = context.get("is_conversational", False)
        conversational_type = context.get("conversational_type", "none")

        if is_conversational and chat_history:
            # ✅ CONVERSATIONAL PATH: Use simple prompt without document context
            logger.info(f"🗣️ Building conversational prompt (type={conversational_type})")

            # ✅ Context Cleaning: Remove RAG artifacts from chat history
            # This prevents "翻譯" requests from outputting document fragments
            cleaned_history = get_cleaned_history(chat_history)

            messages = [
                {"role": "system", "content": CONVERSATIONAL_SYSTEM_PROMPT}
            ]
            # Add CLEANED chat history (no RAG fragments)
            messages.extend(cleaned_history)
            # Add current query
            messages.append({"role": "user", "content": query})

            logger.info(f"Built conversational prompt with {len(cleaned_history)} cleaned history items (from {len(chat_history)} original)")
            return messages

        # ✅ NORMAL PATH: Use RAG prompt with document context
        # Format chunks into context strings
        context_chunks = self._format_chunks_for_prompt_service(context.get("chunks", []))

        # ✅ Use PromptService.build_rag_prompt() - same as non-streaming version
        # Now with chat_history support for multi-turn conversations
        messages = self.prompt_service.build_rag_prompt(
            query=query,
            context_chunks=context_chunks,
            chat_history=chat_history,  # ✅ Pass chat history for Memory
            is_summary=False
        )

        if chat_history:
            logger.info(f"Built {len(messages)} messages with {len(chat_history)} history items")
        else:
            logger.debug(f"Built {len(messages)} messages using PromptService")
        return messages

    def _format_chunks_for_prompt_service(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """
        Format chunk data into strings for PromptService

        Args:
            chunks: List of chunk dictionaries from Phase 3

        Returns:
            List of formatted context strings
        """
        if not chunks:
            return []

        context_strings = []

        for chunk in chunks:
            source_file = chunk.get('source_file', 'Unknown Document')
            page = chunk.get('page', 'N/A')
            content = chunk.get('content', '')

            # Format consistent with PromptService expectations
            chunk_text = f"[文檔片段 - 來源: {source_file} (Page {page})]\n{content}"
            context_strings.append(chunk_text)

        return context_strings

    async def _get_cached_response(
        self,
        query: str,
        context: Dict[str, Any]
    ) -> Optional[str]:
        """Get cached response"""
        if not self.cache:
            return None

        try:
            import hashlib

            # Create cache key from query + chunk IDs
            chunks = context.get("chunks", [])
            chunk_ids = [c.get("chunk_id", "") for c in chunks[:5]]  # Top 5 chunks
            cache_input = f"{query}:{':'.join(chunk_ids)}"
            query_hash = hashlib.md5(cache_input.encode()).hexdigest()
            cache_key = f"skill_phase4:{query_hash}"

            # Try async method
            if hasattr(self.cache, 'get_async'):
                cached = await self.cache.get_async(cache_key)
            elif hasattr(self.cache, 'get'):
                cached = await asyncio.to_thread(self.cache.get, cache_key)
            else:
                return None

            if cached:
                return cached

        except Exception as e:
            logger.warning(f"Cache get error: {e}")

        return None

    async def _cache_response(
        self,
        query: str,
        context: Dict[str, Any],
        response: str
    ) -> None:
        """Cache response"""
        if not self.cache:
            return

        try:
            import hashlib

            # Create cache key from query + chunk IDs
            chunks = context.get("chunks", [])
            chunk_ids = [c.get("chunk_id", "") for c in chunks[:5]]
            cache_input = f"{query}:{':'.join(chunk_ids)}"
            query_hash = hashlib.md5(cache_input.encode()).hexdigest()
            cache_key = f"skill_phase4:{query_hash}"

            # Try async method
            if hasattr(self.cache, 'set_async'):
                await self.cache.set_async(
                    cache_key,
                    response,
                    ttl=1800  # 30 minutes
                )
            elif hasattr(self.cache, 'set'):
                await asyncio.to_thread(
                    self.cache.set,
                    cache_key,
                    response,
                    1800  # 30 minutes TTL
                )

        except Exception as e:
            logger.warning(f"Cache set error: {e}")
