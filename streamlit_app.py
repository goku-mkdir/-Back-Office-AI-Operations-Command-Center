"""Root entrypoint for Streamlit Community Cloud deployment.

Adds `src/` to `sys.path` and launches the OpsPilot AI Executive Control Plane.
Works both standalone (embedded LangGraph runtime on Streamlit Cloud) and
connected to the FastAPI backend when running locally or via Docker Compose.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = str(ROOT / "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

runpy.run_path(str(ROOT / "src" / "backoffice_agent" / "dashboard" / "app.py"), run_name="__main__")
