#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 5: Post-processing & Formatting

Adapted from OPMP Phase 5 for DocAI Skill-Based system.
Handles final response formatting, metadata addition, and validation.

Changes from Original OPMP:
- products_analyzed → chunks_analyzed
- Product sources → Document chunk sources
- Keep markdown validation logic (same)

Author: Claude (SuperClaude)
Date: 2025-12-06
Based on: OPMP Phase 5 (2025-10-01)
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, AsyncGenerator, List, Optional

logger = logging.getLogger(__name__)


class Phase5Postprocessing:
    """
    Phase 5: Post-processing & Formatting

    Adapted from OPMP Phase 5 for document Q&A workflow.

    Handles:
    - Adding metadata to responses
    - Source citations for chunks analyzed
    - Markdown format validation
    - Response quality checks
    - Final formatting touches

    Features:
    - Metadata enrichment
    - Citation generation
    - Markdown validation and fixing
    - Quality assurance checks
    """

    def __init__(self, model_name: str = "gpt-oss:20b"):
        """
        Initialize Phase 5 processor

        Args:
            model_name: Model name for metadata
        """
        self.model_name = model_name
        logger.info("Phase5Postprocessing initialized")

    async def process(
        self,
        generated_response: str,
        context: Dict[str, Any],
        analysis: Dict[str, Any],
        query: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Post-process generated response

        Args:
            generated_response: Response from Phase 4
            context: Context from Phase 3 (chunks)
            analysis: Analysis from Phase 1
            query: Original user query

        Yields:
            Progress updates and final complete response
        """
        try:
            yield {
                "type": "progress",
                "phase": 5,
                "message": "正在完成最後修飾...",
                "progress": 97
            }

            # Build metadata
            metadata = self._build_metadata(context, analysis)

            # Generate source citations
            sources = self._generate_sources(context)

            # Validate and fix markdown
            validated_response = self._validate_and_fix_markdown(generated_response)

            # Build final response package
            response_package = {
                "response": validated_response,
                "metadata": metadata,
                "sources": sources,
                "query": query,
                "timestamp": datetime.now().isoformat()
            }

            # Quality check
            quality_report = self._quality_check(response_package)
            if quality_report.get("warnings"):
                logger.warning(f"Quality check warnings: {quality_report['warnings']}")

            response_package["quality"] = quality_report

            # Send final completion message
            yield {
                "type": "progress",
                "phase": 5,
                "message": "回覆資料輸出完成",
                "progress": 100
            }

            yield {
                "type": "complete",
                "phase": 5,
                "message": "回覆資料輸出完成",
                "data": response_package,
                "progress": 100
            }

        except Exception as e:
            logger.error(f"Phase 5 error: {e}")
            # Return minimal response on error
            yield {
                "type": "complete",
                "phase": 5,
                "data": {
                    "response": generated_response,
                    "metadata": {"error": str(e)},
                    "sources": [],
                    "timestamp": datetime.now().isoformat()
                },
                "progress": 100,
                "error": str(e)
            }

    def _build_metadata(
        self,
        context: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build metadata for response

        Args:
            context: Context from Phase 3 (chunks)
            analysis: Analysis from Phase 1

        Returns:
            Metadata dictionary
        """
        return {
            "chunks_analyzed": context.get("kept_count", 0),
            "context_tokens": context.get("token_count", 0),
            "truncation_applied": context.get("truncation_applied", False),
            "original_chunk_count": context.get("original_count", 0),
            "query_intent": analysis.get("intent", "unknown"),
            "query_complexity": analysis.get("complexity", "medium"),
            "query_focus": analysis.get("query_focus", "general"),
            "model": self.model_name,
            "timestamp": datetime.now().isoformat()
        }

    def _generate_sources(self, context: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Generate source citations from chunks

        Args:
            context: Context from Phase 3 (chunks)

        Returns:
            List of source dictionaries
        """
        sources = []
        chunks = context.get("chunks", [])

        # Group by document to avoid duplicates
        document_sources = {}

        for chunk in chunks:
            source_file = chunk.get("source_file", "Unknown Document")
            doc_id = chunk.get("document_id", "")

            if source_file not in document_sources:
                source = {
                    "document_id": doc_id,
                    "document_name": source_file,
                    "source_type": "document",
                    "chunks_used": 0
                }

                # Add relevance score if available
                if "relevance_score" in chunk:
                    source["relevance_score"] = round(chunk["relevance_score"], 2)

                document_sources[source_file] = source

            # Increment chunk count
            document_sources[source_file]["chunks_used"] += 1

        sources = list(document_sources.values())
        return sources

    def _validate_and_fix_markdown(self, markdown_text: str) -> str:
        """
        Validate and fix common markdown issues

        Common issues fixed:
        - Missing newlines before headers
        - Unclosed bold/italic markers
        - Broken table formatting
        - Extra whitespace

        Args:
            markdown_text: Raw markdown text

        Returns:
            Fixed markdown text
        """
        if not markdown_text:
            return markdown_text

        fixed = markdown_text

        # Fix 1: Ensure newlines before headers
        fixed = re.sub(r'([^\n])\n(#{1,6}\s)', r'\1\n\n\2', fixed)

        # Fix 2: Fix unclosed bold markers
        bold_count = fixed.count('**')
        if bold_count % 2 != 0:
            fixed += '**'
            logger.warning("Fixed unclosed bold marker")

        # Fix 3: Fix table formatting
        fixed = self._fix_table_formatting(fixed)

        # Fix 4: Remove excessive newlines (max 2 consecutive)
        fixed = re.sub(r'\n{3,}', '\n\n', fixed)

        # Fix 5: Trim leading/trailing whitespace
        fixed = fixed.strip()

        return fixed

    def _fix_table_formatting(self, text: str) -> str:
        """
        Fix markdown table formatting

        Args:
            text: Text with potential table

        Returns:
            Fixed text
        """
        lines = text.split('\n')
        in_table = False
        fixed_lines = []

        for line in lines:
            if '|' in line:
                if not in_table:
                    in_table = True

                # Ensure spaces around pipes
                line = re.sub(r'\|', ' | ', line)
                line = re.sub(r'\s+\|\s+', ' | ', line)

            else:
                in_table = False

            fixed_lines.append(line)

        return '\n'.join(fixed_lines)

    def _quality_check(self, response_package: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform quality checks on response

        Checks:
        - Response length (not too short, not too long)
        - Markdown syntax validity
        - Source citations present
        - Metadata completeness

        Args:
            response_package: Complete response package

        Returns:
            Quality report dictionary
        """
        warnings = []
        metrics = {}

        response = response_package.get("response", "")
        metadata = response_package.get("metadata", {})
        sources = response_package.get("sources", [])

        # Check 1: Response length
        response_length = len(response)
        metrics["response_length"] = response_length

        if response_length < 50:
            warnings.append("Response is very short (< 50 chars)")
        elif response_length > 10000:
            warnings.append("Response is very long (> 10K chars)")

        # Check 2: Markdown syntax
        has_header = bool(re.search(r'^#{1,6}\s', response, re.MULTILINE))
        has_bold = '**' in response
        has_table = '|' in response and '---' in response

        metrics["has_markdown_header"] = has_header
        metrics["has_markdown_bold"] = has_bold
        metrics["has_markdown_table"] = has_table

        # Check 3: Sources
        if not sources:
            warnings.append("No source citations")
        metrics["source_count"] = len(sources)

        # Check 4: Metadata
        required_metadata = ["chunks_analyzed", "query_intent", "model"]
        missing_metadata = [k for k in required_metadata if k not in metadata]
        if missing_metadata:
            warnings.append(f"Missing metadata: {missing_metadata}")

        # Overall quality score
        quality_score = 100.0
        quality_score -= len(warnings) * 10  # -10 points per warning

        if response_length < 50:
            quality_score -= 20
        if not has_header and not has_bold:
            quality_score -= 15

        quality_score = max(0, quality_score)

        return {
            "score": quality_score,
            "warnings": warnings,
            "metrics": metrics,
            "passed": quality_score >= 60
        }

    def _is_valid_markdown(self, text: str) -> bool:
        """
        Check if markdown is valid

        Basic validation:
        - Balanced bold markers
        - Balanced italic markers
        - Valid table syntax

        Args:
            text: Markdown text

        Returns:
            True if valid
        """
        # Check balanced bold
        if text.count('**') % 2 != 0:
            return False

        # Check balanced italic
        if text.count('_') % 2 != 0:
            return False

        # Check table syntax (if tables present)
        if '|' in text:
            lines = text.split('\n')
            table_lines = [l for l in lines if '|' in l]

            if len(table_lines) < 2:
                return False  # Need at least header + separator

            # Check separator line
            has_separator = any('---' in line for line in table_lines)
            if not has_separator:
                return False

        return True
