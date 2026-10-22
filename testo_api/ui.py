"""Serve the built React UI from the API process (the team server image does this).

Set ``TESTO_UI_DIR`` to a ``npm run build`` output (``frontend/dist``, built
with ``VITE_API_BASE_URL=""`` so it calls the API on its own origin). The UI is
then mounted at ``/``, after every API route, and unknown paths fall back to
``index.html`` so client-side routes like ``/runs/<id>`` load on refresh.
"""

from __future__ import annotations

import os
from pathlib import Path

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

UI_DIR_ENV = "TESTO_UI_DIR"


def ui_dir() -> Path | None:
    """The configured UI build directory, or None when unset or not a build."""
    raw = (os.environ.get(UI_DIR_ENV) or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser().resolve()
    return path if (path / "index.html").is_file() else None


class SpaStaticFiles(StaticFiles):
    """Static files with a single-page-app fallback to ``index.html``."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # API and report paths keep their real 404; only UI routes fall back.
            if exc.status_code != 404 or path.startswith(("api/", "history/")):
                raise
            return await super().get_response("index.html", scope)
