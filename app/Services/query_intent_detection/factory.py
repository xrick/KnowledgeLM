"""
Factory for creating intent detection strategy instances.

Implements Factory Method pattern to create appropriate strategy based on type.
"""

from typing import Optional
import logging
from .base import IntentDetectionStrategy
from .regex_strategy import RegexPatternStrategy
from .string_parsing_strategy import StringParsingStrategy
from .nlp_strategy import NLPBasedStrategy

logger = logging.getLogger(__name__)


class IntentDetectorFactory:
    """
    Factory class for creating intent detection strategy instances.

    Supported strategies:
    - 'regex': RegexPatternStrategy (default, recommended for production)
    - 'string_parsing': StringParsingStrategy (future implementation)
    - 'nlp': NLPBasedStrategy (future implementation)

    Usage:
        # Create default strategy (regex)
        detector = IntentDetectorFactory.create_detector()

        # Create specific strategy
        detector = IntentDetectorFactory.create_detector('regex')

        # Auto-fallback to regex if strategy not implemented
        detector = IntentDetectorFactory.create_detector('nlp', fallback=True)
    """

    # Strategy registry mapping strategy names to classes
    _STRATEGY_REGISTRY = {
        'regex': RegexPatternStrategy,
        'string_parsing': StringParsingStrategy,
        'nlp': NLPBasedStrategy,
    }

    # Default strategy
    _DEFAULT_STRATEGY = 'regex'

    @classmethod
    def create_detector(
        cls,
        strategy_type: str = 'regex',
        fallback: bool = True
    ) -> IntentDetectionStrategy:
        """
        Create an intent detection strategy instance.

        Args:
            strategy_type: Type of strategy to create
                - 'regex': Regular expression pattern-based (default)
                - 'string_parsing': String parsing-based (not yet implemented)
                - 'nlp': NLP-based linguistic analysis (not yet implemented)
            fallback: Whether to fallback to default strategy if requested
                strategy is not available. Default is True.

        Returns:
            IntentDetectionStrategy instance

        Raises:
            ValueError: If strategy_type is unknown and fallback is False
            NotImplementedError: If strategy exists but is not implemented
                and fallback is False

        Examples:
            >>> # Create default regex strategy
            >>> detector = IntentDetectorFactory.create_detector()

            >>> # Create specific strategy
            >>> detector = IntentDetectorFactory.create_detector('regex')

            >>> # Try NLP strategy with automatic fallback to regex
            >>> detector = IntentDetectorFactory.create_detector('nlp', fallback=True)
            >>> # Will log warning and return regex strategy

            >>> # Strict mode - raise error if not available
            >>> detector = IntentDetectorFactory.create_detector('nlp', fallback=False)
            >>> # Raises NotImplementedError
        """
        # Validate strategy type
        if strategy_type not in cls._STRATEGY_REGISTRY:
            error_msg = (
                f"Unknown strategy type: '{strategy_type}'. "
                f"Available strategies: {list(cls._STRATEGY_REGISTRY.keys())}"
            )
            if fallback:
                logger.warning(
                    f"{error_msg}. Falling back to '{cls._DEFAULT_STRATEGY}'."
                )
                strategy_type = cls._DEFAULT_STRATEGY
            else:
                raise ValueError(error_msg)

        # Get strategy class
        strategy_class = cls._STRATEGY_REGISTRY[strategy_type]

        # Try to instantiate strategy
        try:
            strategy_instance = strategy_class()
            logger.info(f"Created intent detector: {strategy_type}")
            return strategy_instance

        except NotImplementedError as e:
            error_msg = (
                f"Strategy '{strategy_type}' is not yet implemented: {e}"
            )
            if fallback:
                logger.warning(
                    f"{error_msg}. Falling back to '{cls._DEFAULT_STRATEGY}'."
                )
                fallback_class = cls._STRATEGY_REGISTRY[cls._DEFAULT_STRATEGY]
                return fallback_class()
            else:
                raise NotImplementedError(error_msg)

    @classmethod
    def get_available_strategies(cls) -> dict:
        """
        Get information about available strategies.

        Returns:
            Dictionary mapping strategy names to their status

        Example:
            >>> strategies = IntentDetectorFactory.get_available_strategies()
            >>> print(strategies)
            {
                'regex': 'available',
                'string_parsing': 'not_implemented',
                'nlp': 'not_implemented'
            }
        """
        strategies = {}
        for name, strategy_class in cls._STRATEGY_REGISTRY.items():
            try:
                # Try to create instance
                instance = strategy_class()
                # Try to call detect method with dummy data
                instance.detect_multi_file_intent("test", 2)
                strategies[name] = 'available'
            except NotImplementedError:
                strategies[name] = 'not_implemented'
            except Exception as e:
                strategies[name] = f'error: {str(e)}'

        return strategies

    @classmethod
    def register_strategy(cls, name: str, strategy_class: type):
        """
        Register a custom strategy class.

        This allows users to add their own custom detection strategies.

        Args:
            name: Strategy name (must be unique)
            strategy_class: Strategy class (must inherit from IntentDetectionStrategy)

        Raises:
            ValueError: If name already exists or class is invalid

        Example:
            >>> class CustomStrategy(IntentDetectionStrategy):
            ...     def detect_multi_file_intent(self, query, file_count):
            ...         # Custom implementation
            ...         pass
            >>>
            >>> IntentDetectorFactory.register_strategy('custom', CustomStrategy)
            >>> detector = IntentDetectorFactory.create_detector('custom')
        """
        if name in cls._STRATEGY_REGISTRY:
            raise ValueError(f"Strategy '{name}' is already registered")

        if not issubclass(strategy_class, IntentDetectionStrategy):
            raise ValueError(
                f"Strategy class must inherit from IntentDetectionStrategy"
            )

        cls._STRATEGY_REGISTRY[name] = strategy_class
        logger.info(f"Registered custom strategy: {name}")
