"""
String Parsing-based Intent Detection Strategy.

This strategy uses tokenization and word analysis to detect intent.
Currently provides interface definition for future implementation.

Future implementation will use:
- jieba for Chinese word segmentation
- Part-of-speech tagging to identify quantity words
- Token pattern analysis
"""

from .base import IntentDetectionStrategy, MultiFileIntentResult


class StringParsingStrategy(IntentDetectionStrategy):
    """
    Intent detection using string parsing and tokenization.

    FUTURE IMPLEMENTATION - Currently returns NotImplementedError.

    Planned approach:
    1. Tokenize query using jieba
    2. Identify quantity words and units
    3. Detect parallel structures
    4. Analyze word combinations
    """

    def __init__(self):
        super().__init__(name="StringParsing")
        self.logger.warning(
            f"[{self.name}] Strategy not yet implemented. "
            "Use RegexPatternStrategy instead."
        )

    def detect_multi_file_intent(
        self,
        query: str,
        file_count: int
    ) -> MultiFileIntentResult:
        """
        Detect multi-file intent using string parsing.

        FUTURE IMPLEMENTATION.

        Args:
            query: User's query string
            file_count: Number of files selected

        Returns:
            MultiFileIntentResult

        Raises:
            NotImplementedError: This strategy is not yet implemented
        """
        raise NotImplementedError(
            "StringParsingStrategy is not yet implemented. "
            "Please use RegexPatternStrategy or wait for future release."
        )

    def _tokenize_query(self, query: str) -> list:
        """
        Tokenize query into words (future implementation).

        Args:
            query: Query string

        Returns:
            List of tokens

        Future implementation:
            import jieba
            return jieba.lcut(query)
        """
        raise NotImplementedError("Tokenization not yet implemented")

    def _identify_quantity_words(self, tokens: list) -> list:
        """
        Identify quantity words from tokens (future implementation).

        Args:
            tokens: List of word tokens

        Returns:
            List of quantity words found

        Future implementation will check:
        - Part-of-speech tagging (NUM, M)
        - Quantity word patterns
        - Unit words
        """
        raise NotImplementedError("Quantity word identification not yet implemented")


# Example usage (for future reference):
"""
from app.Services.query_intent_detection import IntentDetectorFactory

# This will raise NotImplementedError until implemented
try:
    detector = IntentDetectorFactory.create_detector('string_parsing')
    result = detector.detect_multi_file_intent("三份文件", 3)
except NotImplementedError as e:
    print(f"Strategy not ready: {e}")
    # Fallback to regex strategy
    detector = IntentDetectorFactory.create_detector('regex')
"""
