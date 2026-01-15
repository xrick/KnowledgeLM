"""
NLP-based Intent Detection Strategy.

This strategy uses NLP tools (spaCy) for linguistic rule-based detection.
Currently provides interface definition for future implementation.

Future implementation will use:
- spaCy for Chinese NLP processing
- Part-of-speech tagging
- Dependency parsing
- Named entity recognition
"""

from .base import IntentDetectionStrategy, MultiFileIntentResult


class NLPBasedStrategy(IntentDetectionStrategy):
    """
    Intent detection using NLP linguistic analysis.

    FUTURE IMPLEMENTATION - Currently returns NotImplementedError.

    Planned approach:
    1. Load spaCy Chinese model (zh_core_web_sm)
    2. Analyze POS tags (NUM for numbers, M for measure words)
    3. Parse dependency relations (conj for parallel structures)
    4. Detect distributive patterns ("每", "各", etc.)
    """

    def __init__(self):
        super().__init__(name="NLPBased")
        self.logger.warning(
            f"[{self.name}] Strategy not yet implemented. "
            "Use RegexPatternStrategy instead."
        )
        self.nlp_model = None

    def detect_multi_file_intent(
        self,
        query: str,
        file_count: int
    ) -> MultiFileIntentResult:
        """
        Detect multi-file intent using NLP analysis.

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
            "NLPBasedStrategy is not yet implemented. "
            "Please use RegexPatternStrategy or wait for future release."
        )

    def _load_nlp_model(self):
        """
        Load spaCy Chinese NLP model (future implementation).

        Future implementation:
            import spacy
            self.nlp_model = spacy.load("zh_core_web_sm")
        """
        raise NotImplementedError("NLP model loading not yet implemented")

    def _analyze_pos_tags(self, query: str) -> dict:
        """
        Analyze part-of-speech tags (future implementation).

        Args:
            query: Query string

        Returns:
            Dictionary with POS analysis results

        Future implementation will detect:
        - NUM: Numeric tokens
        - M: Measure words (量詞)
        - VERB: Action verbs
        """
        raise NotImplementedError("POS tagging not yet implemented")

    def _parse_dependencies(self, query: str) -> dict:
        """
        Parse dependency relations (future implementation).

        Args:
            query: Query string

        Returns:
            Dictionary with dependency analysis results

        Future implementation will detect:
        - conj: Conjunctions (並列)
        - cc: Coordinating conjunctions
        - nmod: Nominal modifiers
        """
        raise NotImplementedError("Dependency parsing not yet implemented")


# Example usage (for future reference):
"""
from app.Services.query_intent_detection import IntentDetectorFactory

# This will raise NotImplementedError until implemented
try:
    detector = IntentDetectorFactory.create_detector('nlp')
    result = detector.detect_multi_file_intent("比較這三份文件", 3)
except NotImplementedError as e:
    print(f"Strategy not ready: {e}")
    # Fallback to regex strategy
    detector = IntentDetectorFactory.create_detector('regex')
"""
