"""
Netlify Function entrypoint — wraps the FastAPI ASGI app with Mangum (AWS Lambda–style).

Local development: continue using `uvicorn app.main:app` (this file is not used).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Project root = Back/ (parent of netlify/)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mangum import Mangum

from app.main import app

handler = Mangum(app)
