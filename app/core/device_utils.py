# app/core/device_utils.py
"""
Device Detection Utilities

Hardware acceleration detection for embedding models:
- CUDA (NVIDIA GPUs)
- MPS (Apple Silicon)
- CPU fallback
"""

import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def detect_available_device() -> Tuple[str, dict]:
    """
    Detect available hardware acceleration device

    Priority:
    1. CUDA (NVIDIA GPU) - cuda:0
    2. MPS (Apple Silicon) - mps
    3. CPU (fallback) - cpu

    Returns:
        Tuple[str, dict]: (device_name, device_info)
            - device_name: "cuda:0", "mps", or "cpu"
            - device_info: Dict with detailed device information

    Example:
        >>> device, info = detect_available_device()
        >>> print(f"Using device: {device}")
        >>> print(f"Device info: {info}")
    """
    device_info = {
        "cuda_available": False,
        "cuda_device_count": 0,
        "cuda_device_name": None,
        "mps_available": False,
        "selected_device": "cpu",
        "acceleration": "none"
    }

    try:
        import torch

        # Check CUDA (NVIDIA GPU)
        if torch.cuda.is_available():
            device_info["cuda_available"] = True
            device_info["cuda_device_count"] = torch.cuda.device_count()
            device_info["cuda_device_name"] = torch.cuda.get_device_name(0)
            device_info["selected_device"] = "cuda:0"
            device_info["acceleration"] = "cuda"

            logger.info(
                f"CUDA detected: {device_info['cuda_device_name']} "
                f"({device_info['cuda_device_count']} device(s))"
            )
            return "cuda:0", device_info

        # Check MPS (Apple Silicon)
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            device_info["mps_available"] = True
            device_info["selected_device"] = "mps"
            device_info["acceleration"] = "mps"

            logger.info("MPS (Apple Silicon) detected")
            return "mps", device_info

        # Fallback to CPU
        logger.info("No GPU acceleration available, using CPU")
        device_info["selected_device"] = "cpu"
        device_info["acceleration"] = "none"
        return "cpu", device_info

    except ImportError:
        logger.warning("PyTorch not available, defaulting to CPU")
        device_info["selected_device"] = "cpu"
        device_info["acceleration"] = "none"
        return "cpu", device_info
    except Exception as e:
        logger.error(f"Error detecting device: {str(e)}")
        device_info["selected_device"] = "cpu"
        device_info["acceleration"] = "none"
        device_info["error"] = str(e)
        return "cpu", device_info


def get_device_for_embedding(preferred_device: Optional[str] = None) -> str:
    """
    Get device for embedding model with preference override

    Args:
        preferred_device: User-specified device ("cuda:0", "mps", "cpu")
                         If None, auto-detect optimal device

    Returns:
        str: Device to use for embedding model

    Example:
        >>> device = get_device_for_embedding()  # Auto-detect
        >>> device = get_device_for_embedding("cuda:0")  # Force CUDA
        >>> device = get_device_for_embedding("cpu")  # Force CPU
    """
    # Auto-detect if not specified
    if preferred_device is None or preferred_device == "auto":
        device, info = detect_available_device()
        logger.info(f"Auto-detected device: {device} (acceleration: {info['acceleration']})")
        return device

    # Validate preferred device
    if preferred_device == "cpu":
        logger.info("Using CPU as specified")
        return "cpu"

    if preferred_device.startswith("cuda"):
        try:
            import torch
            if torch.cuda.is_available():
                logger.info(f"Using {preferred_device} as specified")
                return preferred_device
            else:
                logger.warning(f"CUDA requested but not available, falling back to CPU")
                return "cpu"
        except ImportError:
            logger.warning("PyTorch not available, falling back to CPU")
            return "cpu"

    if preferred_device == "mps":
        try:
            import torch
            if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                logger.info("Using MPS as specified")
                return "mps"
            else:
                logger.warning("MPS requested but not available, falling back to CPU")
                return "cpu"
        except ImportError:
            logger.warning("PyTorch not available, falling back to CPU")
            return "cpu"

    # Unknown device, fallback to CPU
    logger.warning(f"Unknown device '{preferred_device}', falling back to CPU")
    return "cpu"


def print_device_info():
    """
    Print detailed device information (for debugging/startup)

    Example:
        >>> print_device_info()
        Device Detection Summary
        ========================
        CUDA Available: True
        CUDA Devices: 1 (NVIDIA GeForce RTX 3090)
        MPS Available: False
        Selected Device: cuda:0
        Acceleration: cuda
    """
    device, info = detect_available_device()

    print("\n" + "="*50)
    print("Device Detection Summary")
    print("="*50)
    print(f"CUDA Available: {info['cuda_available']}")
    if info['cuda_available']:
        print(f"CUDA Devices: {info['cuda_device_count']} ({info['cuda_device_name']})")
    print(f"MPS Available: {info['mps_available']}")
    print(f"Selected Device: {info['selected_device']}")
    print(f"Acceleration: {info['acceleration']}")
    print("="*50 + "\n")

    return device, info
