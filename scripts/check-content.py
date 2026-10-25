#!/usr/bin/env python3
"""Content CLI. API and CLI share schemas and rules in api.content_validation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))
from api.content_validation import *  # noqa: F403,E402 (existing CLI test interface)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
