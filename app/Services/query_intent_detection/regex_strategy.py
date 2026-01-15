"""
Regular Expression Pattern-based Intent Detection Strategy.

This strategy uses regex patterns to detect multi-file query intent through:
1. Quantity patterns (e.g., "三份", "4個")
2. High-confidence verbs (e.g., "比較", "對比")
3. Scope + content word combinations (e.g., "所有" + "內容")
"""

import re
from typing import List, Tuple
from .base import IntentDetectionStrategy, MultiFileIntentResult


class RegexPatternStrategy(IntentDetectionStrategy):
    """
    Intent detection using regular expression patterns.

    This strategy implements a multi-layer detection approach:
    - Layer 1: High-confidence keywords (fastest)
    - Layer 2: Quantity patterns (regex)
    - Layer 3: Scope + content combinations (logic)
    """

    def __init__(self):
        super().__init__(name="RegexPattern")

        # Layer 1: High-confidence keywords (exact match, fastest)
        self.high_confidence_keywords = [
            "比較", "對比", "差異", "異同",
            "各別", "分別", "每份", "每一份"
        ]

        # Layer 2: Regex patterns for quantity detection
        # Pattern: [Chinese number][unit]
        self.chinese_quantity_pattern = re.compile(
            r'[二兩三四五六七八九十百千多幾][份篇個本張支檔文件]'
        )

        # Pattern: [Arabic number][unit]
        self.numeric_quantity_pattern = re.compile(
            r'\d+[份篇個本張支檔文件]'
        )

        # Layer 3: Scope + content combinations
        self.scope_words = ["所有", "這些", "全部", "整體"]
        self.content_words = ["內容", "資料", "資訊", "文章"]

        # Additional: Summary intent keywords
        self.summary_keywords = ["摘要", "總結", "概述", "彙整"]

        # Multi-file hint keywords
        self.multi_file_hints = ["多份", "多篇", "多個", "不同文件"]

    def detect_multi_file_intent(
        self,
        query: str,
        file_count: int
    ) -> MultiFileIntentResult:
        """
        Detect multi-file intent using regex patterns and keyword combinations.

        Detection layers (in order):
        1. High-confidence keywords
        2. Quantity patterns (Chinese + Arabic numbers)
        3. Scope + content word combinations
        4. Multi-file hints

        Args:
            query: User's query string
            file_count: Number of files selected

        Returns:
            MultiFileIntentResult with detection details
        """
        # Validate input
        early_result = self._validate_input(query, file_count)
        if early_result:
            return early_result

        matched_patterns = []

        # Layer 1: High-confidence keywords (100% confidence)
        for keyword in self.high_confidence_keywords:
            if keyword in query:
                matched_patterns.append(f"high_confidence:{keyword}")
                result = MultiFileIntentResult(
                    is_multi_file=True,
                    confidence=1.0,
                    matched_patterns=matched_patterns,
                    detection_layer="layer1_high_confidence"
                )
                self.log_result(result, query)
                return result

        # Layer 2: Quantity patterns (95% confidence)
        # Check Chinese number + unit pattern
        chinese_match = self.chinese_quantity_pattern.search(query)
        if chinese_match:
            matched_patterns.append(f"quantity_chinese:{chinese_match.group()}")
            result = MultiFileIntentResult(
                is_multi_file=True,
                confidence=0.95,
                matched_patterns=matched_patterns,
                detection_layer="layer2_quantity_pattern"
            )
            self.log_result(result, query)
            return result

        # Check Arabic number + unit pattern
        numeric_match = self.numeric_quantity_pattern.search(query)
        if numeric_match:
            matched_patterns.append(f"quantity_numeric:{numeric_match.group()}")
            result = MultiFileIntentResult(
                is_multi_file=True,
                confidence=0.95,
                matched_patterns=matched_patterns,
                detection_layer="layer2_quantity_pattern"
            )
            self.log_result(result, query)
            return result

        # Layer 3: Scope + content combinations (85% confidence)
        has_scope = any(word in query for word in self.scope_words)
        has_content = any(word in query for word in self.content_words)

        if has_scope and has_content:
            matched_patterns.append(
                f"scope_content:{[w for w in self.scope_words if w in query]}+"
                f"{[w for w in self.content_words if w in query]}"
            )
            result = MultiFileIntentResult(
                is_multi_file=True,
                confidence=0.85,
                matched_patterns=matched_patterns,
                detection_layer="layer3_scope_content"
            )
            self.log_result(result, query)
            return result

        # Layer 4: Multi-file hints (75% confidence)
        for hint in self.multi_file_hints:
            if hint in query:
                matched_patterns.append(f"multi_file_hint:{hint}")
                result = MultiFileIntentResult(
                    is_multi_file=True,
                    confidence=0.75,
                    matched_patterns=matched_patterns,
                    detection_layer="layer4_multi_file_hint"
                )
                self.log_result(result, query)
                return result

        # No patterns matched - likely single file query
        result = MultiFileIntentResult(
            is_multi_file=False,
            confidence=0.9,  # High confidence it's NOT multi-file
            matched_patterns=[],
            detection_layer="no_match"
        )
        self.log_result(result, query)
        return result

    def get_pattern_info(self) -> dict:
        """
        Get information about configured patterns.

        Returns:
            Dictionary containing pattern configuration details
        """
        return {
            "strategy_name": self.name,
            "layers": [
                {
                    "name": "layer1_high_confidence",
                    "type": "exact_match",
                    "confidence": 1.0,
                    "keywords": self.high_confidence_keywords
                },
                {
                    "name": "layer2_quantity_pattern",
                    "type": "regex",
                    "confidence": 0.95,
                    "patterns": [
                        self.chinese_quantity_pattern.pattern,
                        self.numeric_quantity_pattern.pattern
                    ]
                },
                {
                    "name": "layer3_scope_content",
                    "type": "combination",
                    "confidence": 0.85,
                    "scope_words": self.scope_words,
                    "content_words": self.content_words
                },
                {
                    "name": "layer4_multi_file_hint",
                    "type": "exact_match",
                    "confidence": 0.75,
                    "keywords": self.multi_file_hints
                }
            ]
        }
