"""
Base classes for intent detection strategies.

Defines the abstract interface that all intent detection strategies must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class MultiFileIntentResult:
    """
    Result of multi-file intent detection.

    Attributes:
        is_multi_file: Whether the query intends to process multiple files
        confidence: Confidence score (0.0 to 1.0)
        matched_patterns: List of patterns that matched
        detection_layer: Which detection layer triggered (for debugging)
    """
    is_multi_file: bool
    confidence: float
    matched_patterns: List[str]
    detection_layer: str

    def __str__(self):
        return (
            f"MultiFileIntent(is_multi={self.is_multi_file}, "
            f"confidence={self.confidence:.2f}, "
            f"layer={self.detection_layer}, "
            f"patterns={self.matched_patterns})"
        )


class IntentDetectionStrategy(ABC):
    """
    Abstract base class for intent detection strategies.

    All concrete strategies must implement the detect_multi_file_intent method.
    """

    def __init__(self, name: str):
        """
        Initialize the strategy.

        Args:
            name: Strategy name for logging and debugging
        """
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    def detect_multi_file_intent(
        self,
        query: str,
        file_count: int
    ) -> MultiFileIntentResult:
        """
        Detect whether the query intends to process multiple files.

        Args:
            query: User's query string
            file_count: Number of files selected by user

        Returns:
            MultiFileIntentResult containing detection results
        """
        pass

    def _validate_input(self, query: str, file_count: int) -> Optional[MultiFileIntentResult]:
        """
        Validate input parameters and return early result if applicable.

        Args:
            query: User's query string
            file_count: Number of files selected

        Returns:
            MultiFileIntentResult if validation determines result early,
            None if detection should proceed
        """
        # Protection: Single file always returns False
        if file_count < 2:
            self.logger.debug(f"[{self.name}] File count < 2, skipping detection")
            return MultiFileIntentResult(
                is_multi_file=False,
                confidence=1.0,
                matched_patterns=[],
                detection_layer="validation"
            )

        # Empty query
        if not query or not query.strip():
            self.logger.debug(f"[{self.name}] Empty query")
            return MultiFileIntentResult(
                is_multi_file=False,
                confidence=1.0,
                matched_patterns=[],
                detection_layer="validation"
            )

        return None

    def log_result(self, result: MultiFileIntentResult, query: str):
        """Log detection result for debugging."""
        self.logger.info(
            f"[{self.name}] Query: '{query[:50]}...' → {result}"
        )
