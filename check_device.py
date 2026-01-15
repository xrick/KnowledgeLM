# check_device.py
#!/usr/bin/env python3
"""
Device Detection Script

Standalone script to check hardware acceleration availability.
Can be used in shell scripts for system checks.
"""

import sys
import json


def main():
    try:
        from app.core.device_utils import detect_available_device, print_device_info

        # Print detailed info
        device, info = print_device_info()

        # Output JSON for shell script parsing
        print("\nJSON Output (for script parsing):")
        print(json.dumps(info, indent=2))

        # Exit code based on acceleration
        # 0: GPU acceleration available
        # 1: CPU only
        if info["acceleration"] != "none":
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
