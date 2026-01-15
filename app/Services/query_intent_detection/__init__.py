"""
Query Intent Detection Module

This module provides a flexible intent detection system using Strategy Pattern
and Factory Method to support multiple detection approaches.

Supported strategies:
- RegexPatternStrategy: Pattern-based detection using regular expressions
- StringParsingStrategy: Token-based detection using string parsing (future)
- NLPBasedStrategy: Linguistic rule-based detection using NLP (future)

Usage:
    from app.Services.query_intent_detection import IntentDetectorFactory

    # Create detector with specific strategy
    detector = IntentDetectorFactory.create_detector('regex')

    # Detect intent
    is_multi_file = detector.detect_multi_file_intent(query, file_count)
"""

from .base import IntentDetectionStrategy, MultiFileIntentResult
from .regex_strategy import RegexPatternStrategy
from .string_parsing_strategy import StringParsingStrategy
from .nlp_strategy import NLPBasedStrategy
from .factory import IntentDetectorFactory

__all__ = [
    'IntentDetectionStrategy',
    'MultiFileIntentResult',
    'RegexPatternStrategy',
    'StringParsingStrategy',
    'NLPBasedStrategy',
    'IntentDetectorFactory',
]
