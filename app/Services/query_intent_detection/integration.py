"""
Integration layer for backward compatibility.

This module provides wrapper functions that match the existing API
used by iterative_query_expansion_service.py, ensuring no breaking changes.
"""

import logging
from typing import Optional
from .factory import IntentDetectorFactory
from .base import IntentDetectionStrategy

logger = logging.getLogger(__name__)


class IntentDetectorManager:
    """
    Manager class for intent detection with configuration support.

    This class maintains a singleton instance of the current detection strategy
    and provides methods to switch strategies at runtime without breaking
    existing code.

    Usage in existing code:
        # Option 1: Use default instance (no changes needed to existing code)
        from app.Services.query_intent_detection.integration import detect_multi_file_intent
        is_multi = detect_multi_file_intent(query, file_count)

        # Option 2: Configure strategy globally
        from app.Services.query_intent_detection.integration import IntentDetectorManager
        IntentDetectorManager.configure(strategy_type='regex')
    """

    _instance: Optional[IntentDetectionStrategy] = None
    _current_strategy_type: str = 'regex'

    @classmethod
    def get_instance(cls) -> IntentDetectionStrategy:
        """
        Get or create the current detector instance.

        Returns:
            Current IntentDetectionStrategy instance
        """
        if cls._instance is None:
            cls._instance = IntentDetectorFactory.create_detector(
                cls._current_strategy_type
            )
            logger.info(
                f"Initialized IntentDetectorManager with strategy: "
                f"{cls._current_strategy_type}"
            )

        return cls._instance

    @classmethod
    def configure(cls, strategy_type: str = 'regex'):
        """
        Configure the detection strategy globally.

        Args:
            strategy_type: Strategy type to use ('regex', 'string_parsing', 'nlp')

        Example:
            >>> # In your application startup or config
            >>> from app.Services.query_intent_detection.integration import IntentDetectorManager
            >>> IntentDetectorManager.configure(strategy_type='regex')
        """
        if strategy_type != cls._current_strategy_type:
            logger.info(
                f"Switching intent detection strategy from "
                f"'{cls._current_strategy_type}' to '{strategy_type}'"
            )
            cls._current_strategy_type = strategy_type
            cls._instance = IntentDetectorFactory.create_detector(strategy_type)

    @classmethod
    def reset(cls):
        """
        Reset to default configuration.

        Useful for testing or reinitialization.
        """
        cls._instance = None
        cls._current_strategy_type = 'regex'
        logger.info("Reset IntentDetectorManager to default configuration")


def detect_multi_file_intent(query: str, file_count: int) -> bool:
    """
    Detect whether the query intends to process multiple files.

    This is a backward-compatible wrapper function that can be used as a
    drop-in replacement for existing keyword-based detection.

    Args:
        query: User's query string
        file_count: Number of files selected by user

    Returns:
        True if query intends to process multiple files, False otherwise

    Example:
        >>> # This works exactly like the old function
        >>> from app.Services.query_intent_detection.integration import detect_multi_file_intent
        >>>
        >>> is_multi = detect_multi_file_intent("比較三份文件", 3)
        >>> print(is_multi)  # True
        >>>
        >>> is_single = detect_multi_file_intent("解釋這個文件", 1)
        >>> print(is_single)  # False
    """
    detector = IntentDetectorManager.get_instance()
    result = detector.detect_multi_file_intent(query, file_count)
    return result.is_multi_file


def detect_multi_file_intent_detailed(query: str, file_count: int) -> dict:
    """
    Detect multi-file intent and return detailed information.

    Unlike the simple boolean function above, this returns full detection
    details including confidence and matched patterns.

    Args:
        query: User's query string
        file_count: Number of files selected by user

    Returns:
        Dictionary containing:
        - is_multi_file: Boolean result
        - confidence: Confidence score (0.0 to 1.0)
        - matched_patterns: List of patterns that matched
        - detection_layer: Which detection layer triggered

    Example:
        >>> from app.Services.query_intent_detection.integration import detect_multi_file_intent_detailed
        >>>
        >>> result = detect_multi_file_intent_detailed("產生四份文件的摘要", 4)
        >>> print(result)
        {
            'is_multi_file': True,
            'confidence': 0.95,
            'matched_patterns': ['quantity_chinese:四份'],
            'detection_layer': 'layer2_quantity_pattern'
        }
    """
    detector = IntentDetectorManager.get_instance()
    result = detector.detect_multi_file_intent(query, file_count)

    return {
        'is_multi_file': result.is_multi_file,
        'confidence': result.confidence,
        'matched_patterns': result.matched_patterns,
        'detection_layer': result.detection_layer
    }


# Backward compatibility aliases
# These allow existing code to continue working without changes
is_multi_file_query = detect_multi_file_intent
check_multi_file_intent = detect_multi_file_intent


def get_current_strategy_info() -> dict:
    """
    Get information about the current detection strategy.

    Returns:
        Dictionary with strategy information

    Example:
        >>> from app.Services.query_intent_detection.integration import get_current_strategy_info
        >>> info = get_current_strategy_info()
        >>> print(info)
        {
            'strategy_type': 'regex',
            'strategy_name': 'RegexPattern',
            'available_strategies': {
                'regex': 'available',
                'string_parsing': 'not_implemented',
                'nlp': 'not_implemented'
            }
        }
    """
    detector = IntentDetectorManager.get_instance()

    return {
        'strategy_type': IntentDetectorManager._current_strategy_type,
        'strategy_name': detector.name,
        'available_strategies': IntentDetectorFactory.get_available_strategies()
    }
