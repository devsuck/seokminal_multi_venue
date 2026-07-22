"""Production 감사 (P6.1) — 기존 audit 로거 사용(append-only). 삭제/재작성 없음."""
from __future__ import annotations

from jarvis.audit import read_all, record


def record_production(entry: dict) -> dict:
    return record({"layer": "production", **entry})


def read_production_events() -> list[dict]:
    return [a for a in read_all() if a.get("layer") == "production"]
