"""
Netlify Function — FastAPI via Mangum (AWS Lambda–compatible).

Local: utiliser `uvicorn app.main:app` depuis la racine Back/.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Racine du dépôt Back/
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mangum import Mangum

from app.main import app

handler = Mangum(app)
