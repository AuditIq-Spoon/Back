"""
Netlify Function — FastAPI via Mangum (AWS Lambda–compatible).

Après réécriture Netlify, le chemin ASGI peut être
``/.netlify/functions/auditiq/...`` au lieu de ``/api/...`` ou ``/health`` :
on retire ce préfixe pour que le routeur FastAPI corresponde aux endpoints.

Local: utiliser ``uvicorn app.main:app`` (ce fichier n'est pas importé).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Racine du dépôt Back/
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mangum import Mangum
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.main import app

# Doit matcher le nom du fichier → URL ``/.netlify/functions/auditiq``
_NETLIFY_FN_PREFIX = "/.netlify/functions/auditiq"


class _StripNetlifyFunctionPath(BaseHTTPMiddleware):
    """Normalise le path pour Mangum + redirect Netlify → FastAPI."""

    async def dispatch(self, request: Request, call_next):
        scope = request.scope
        if scope["type"] != "http":
            return await call_next(request)
        path = scope.get("path") or ""
        if path == _NETLIFY_FN_PREFIX or path.startswith(_NETLIFY_FN_PREFIX + "/"):
            new_path = path[len(_NETLIFY_FN_PREFIX) :] or "/"
            if not new_path.startswith("/"):
                new_path = "/" + new_path
            scope["path"] = new_path
            scope["raw_path"] = new_path.encode("utf-8")
        return await call_next(request)


# Une seule fois (évite d’empiler le middleware si le module est rechargé).
if not getattr(app.state, "auditiq_netlify_path_strip", False):
    app.add_middleware(_StripNetlifyFunctionPath)
    app.state.auditiq_netlify_path_strip = True

handler = Mangum(app)
