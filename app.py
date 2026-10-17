"""Launch the canonical PRISM dashboard with Google Cloud integration."""
from pathlib import Path
import runpy
import sys

REFERENCE = Path(__file__).resolve().parent / "prism_reference"
if str(REFERENCE) not in sys.path:
    sys.path.insert(0, str(REFERENCE))
runpy.run_path(str(REFERENCE / "dashboard" / "app.py"), run_name="__main__")
