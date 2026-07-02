"""실험 registry — 돌린 가설·결과·폐기이유 기록(JSONL). 같은 실패 반복 방지.
자율 에이전트 아님. 수동 실험에도 필요한 연구 장부."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

REGISTRY = os.path.join(os.path.dirname(__file__), "experiment_registry.jsonl")


def log_experiment(entry: dict) -> None:
    """append-only. entry에 timestamp 자동 추가."""
    entry = {"timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **entry}
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    with open(REGISTRY, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def load_all() -> list[dict]:
    if not os.path.exists(REGISTRY):
        return []
    with open(REGISTRY) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def already_tested(hypothesis_id: str) -> list[dict]:
    """같은 가설 과거 결과. 제안 전 조회 → 반복 방지."""
    return [e for e in load_all() if e.get("hypothesis_id") == hypothesis_id]
