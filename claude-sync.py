#!/usr/bin/env python
"""
Entry point for claude-sync CLI
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.cli import cli

if __name__ == '__main__':
    cli()