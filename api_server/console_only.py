"""Lightweight launcher that serves ONLY the /console router.

Use this when the full ``api_server.main`` app cannot start on a machine
(e.g. heavy trading dependencies such as nautilus_trader are unavailable or
incompatible with the local Python). The console endpoints import their
heavy dependencies lazily, so this thin app boots without them and powers
the Research / Investment OS / Intelligence dashboard screens.

Run:
    uvicorn api_server.console_only:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_server.console_api import router as console_router

app = FastAPI(title="Seokminal Console API (lite)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(console_router)


@app.get("/")
def _root() -> dict:
    return {"ok": True, "service": "console-lite", "routes": len(app.routes)}


@app.get("/healthz")
def _healthz() -> dict:
    return {"ok": True}
