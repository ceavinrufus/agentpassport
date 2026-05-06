"""Ensure project root is on sys.path for demo imports."""

import sys
from pathlib import Path

root = Path(__file__).parent.parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
