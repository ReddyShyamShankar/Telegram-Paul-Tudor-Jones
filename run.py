"""Runtime bootstrap. Use `python run.py` instead of `python -m tsg`.

Why: macOS auto-hides pip's editable .pth files in site-packages, which
breaks `python -m tsg`. This wrapper prepends `src/` to sys.path so the
import always works regardless of pth state.
"""
import sys
from pathlib import Path

_SRC = Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tsg.main import run  # noqa: E402

if __name__ == "__main__":
    run()
