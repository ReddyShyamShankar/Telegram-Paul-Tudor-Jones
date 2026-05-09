"""Pytest bootstrap. Adds `src/` to sys.path so tests can `import tsg.*`
without depending on the editable pth file (macOS Python 3.13 auto-hides
.pth files in site-packages, which breaks pip's editable-install path).
"""
import sys
from pathlib import Path

_SRC = Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
