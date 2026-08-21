"""Vercel ASGI entrypoint for the environment-backed TwinOps v2 API."""

from pathlib import Path
import sys


_BUNDLED_SOURCE = Path(__file__).resolve().parents[1] / "services" / "twinops" / "src"
if str(_BUNDLED_SOURCE) not in sys.path:
    sys.path.insert(0, str(_BUNDLED_SOURCE))

from twinops.main_v2 import create_app_v2_from_env


app = create_app_v2_from_env()
