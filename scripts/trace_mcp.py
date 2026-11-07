#!/usr/bin/env python3
"""Launch the local read-only research trace tools from any working directory."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brochure.trace_tools import main

if __name__ == '__main__':
    main()
