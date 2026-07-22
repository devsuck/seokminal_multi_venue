"""Fusion 신호 원장 — append-only. write는 FUSION_AGENT 권한 필수. 삭제/재작성 없음."""
from __future__ import annotations

import json
import os

from jarvis.agents import FUSION_AGENT
from jarvis.audit import record
from jarvis.config import state_path
from jarvis.fusion.types import FusionSignal
from jarvis.permissions import require

_LEDGER = "fusion_signals.jsonl"


def write_signals(fusion_signals: list[FusionSignal], scheme: str) -> int:
    """합성신호 append. 반환=기록 수. 권한: write_fusion_signal(PAPER_ONLY)."""
    require(FUSION_AGENT, "write_fusion_signal", scheme)
    path = state_path(_LEDGER)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = 0
    with open(path, "a") as f:
        for fs in fusion_signals:
            f.write(json.dumps(fs.to_dict(), ensure_ascii=False, default=str) + "\n")
            n += 1
    record({"layer": "fusion", "action": "write_signals", "scheme": scheme,
            "n_signals": n, "result": "written"})
    return n


def read_all() -> list[dict]:
    path = state_path(_LEDGER)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def read_latest(limit: int = 50) -> list[dict]:
    return read_all()[-limit:]
