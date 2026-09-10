"""자본 청구 엔벨로프 — 사람이 사전 설정한 한도. 이 안에서만 AI 자율승인 가능.

미설정(파일 없음) = 한도 0 = 자율승인 전면 불가(fail-safe). LIVE 전략의 한도는 여기서
관리하지 않는다 — `jarvis.execution.arm.arm()`의 `capital_limit`이 이미 그 역할(사람만 설정,
이중 게이트). 여기는 PAPER 전략 + 전체 풀 상한만 다룬다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from jarvis.audit import record
from jarvis.config import state_path
from jarvis.permissions import Level, PermissionDenied, Principal, require

_ENVELOPE = "capital_envelope.json"


def get_envelope() -> dict:
    p = state_path(_ENVELOPE)
    if not os.path.exists(p):
        return {"pool_limit": 0.0, "default_paper_limit": 0.0, "per_strategy_paper_limit": {}}
    with open(p) as f:
        return json.load(f)


def set_envelope(human: Principal, pool_limit: float, default_paper_limit: float = 0.0,
                  per_strategy_paper_limit: dict[str, float] | None = None) -> dict:
    require(human, "modify_capital_envelope")
    row = {"pool_limit": pool_limit, "default_paper_limit": default_paper_limit,
           "per_strategy_paper_limit": per_strategy_paper_limit or {},
           "set_by": human.name,
           "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with open(state_path(_ENVELOPE), "w") as f:
        json.dump(row, f, ensure_ascii=False)
    record({"layer": "capital_envelope", "action": "set_envelope", "set_by": human.name,
            "pool_limit": pool_limit, "result": "recorded"})
    return row


def paper_limit_for(strategy_id: str) -> float:
    env = get_envelope()
    return env["per_strategy_paper_limit"].get(strategy_id, env["default_paper_limit"])
