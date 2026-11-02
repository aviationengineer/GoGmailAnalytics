#!/usr/bin/env python3
"""Entry point. Use the project venv: .venv-gmail-intel/bin/python main.py ..."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from gmail_intel.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
