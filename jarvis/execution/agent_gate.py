"""트레이딩 에이전트 ↔ 전략 registry 게이트.

시스템 최대 모순 해소: 연구 트랙은 BH-FDR·레드팀 통과해야 페이퍼로 가는데,
트레이딩 에이전트는 registry 무관한 교과서 신호(intraday_score·모멘텀)로
실계좌 매매 가능했음. 규칙:

  - 에이전트 전략이 registry 검증 상태가 아니면 → live 주문 차단, 페이퍼 강제.
  - 매핑은 명시적으로만(register_validated_strategy) — 암묵 매칭 금지.
  - 사람 ADMIN만 매핑을 등록/해제할 수 있다(arm.py와 동일 게이트) — append-only
    jsonl(jarvis/_state/agent_strategy_mapping.jsonl)에 latest-wins로 기록.
  - 지금은 매핑이 비어 있음 = 모든 에이전트 미검증 = live 전부 차단(정직한 현주소).
    검증된 전략을 에이전트로 돌리려면 register_validated_strategy 호출 + registry
    상태가 증명해야 함.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from jarvis.audit import record
from jarvis.config import state_path
from jarvis.permissions import Level, PermissionDenied, Principal, require
from jarvis.registry import StrategyRegistry

_MAPPING = "agent_strategy_mapping.jsonl"

# registry에서 "검증됨"으로 인정하는 상태 — paper 단계 이상(사전등록 게이트 통과분)
_VALIDATED_STATUSES = {
    "paper_candidate", "paper_candidate_forward_test_required",
    "paper_active", "micro_live", "live",
}


def _rows() -> list[dict]:
    p = state_path(_MAPPING)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _append(row: dict) -> None:
    os.makedirs(os.path.dirname(state_path(_MAPPING)), exist_ok=True)
    with open(state_path(_MAPPING), "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _current_mapping() -> dict[str, str]:
    """최신 register/unregister 반영한 profile_name → strategy_id 매핑(latest-wins).
    상태 파일이 없으면 빈 딕셔너리 — 기존 PROFILE_TO_STRATEGY={}의 fail-safe 동작 그대로."""
    mapping: dict[str, str] = {}
    for r in _rows():
        name = r.get("profile_name")
        if r.get("action") == "register":
            mapping[name] = r.get("strategy_id")
        elif r.get("action") == "unregister":
            mapping.pop(name, None)
    return mapping


def register_validated_strategy(profile_name: str, strategy_id: str, human: Principal) -> dict:
    """사람 ADMIN만: 에이전트 profile 이름 → registry 전략 매핑 등록.

    등록 시점엔 registry에 strategy_id가 존재하는지만 확인한다(상태값 검증은
    안 함) — validation_of()가 호출 시점마다 실시간으로 상태를 재검증하므로."""
    if not human.is_human or human.level < Level.ADMIN_HUMAN_ONLY:
        record({"layer": "agent_gate", "action": "register_validated_strategy",
                "profile_name": profile_name, "strategy_id": strategy_id,
                "agent": human.name, "result": "denied", "reason": "not_human_admin"})
        raise PermissionDenied("register_validated_strategy는 사람 ADMIN만 가능")
    require(human, "approve_live_promotion", strategy_id)
    if StrategyRegistry().state(strategy_id) is None:
        record({"layer": "agent_gate", "action": "register_validated_strategy",
                "profile_name": profile_name, "strategy_id": strategy_id,
                "result": "denied", "reason": "strategy_not_registered"})
        return {"profile_name": profile_name, "strategy_id": strategy_id,
                "registered": False, "reason": "strategy_not_registered"}
    row = {"profile_name": profile_name, "strategy_id": strategy_id, "action": "register",
           "registered_by": human.name,
           "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _append(row)
    record({"layer": "agent_gate", "action": "register_validated_strategy",
            "profile_name": profile_name, "strategy_id": strategy_id,
            "registered_by": human.name, "result": "registered"})
    return {"profile_name": profile_name, "strategy_id": strategy_id, "registered": True}


def unregister_strategy(profile_name: str, human: Principal) -> dict:
    """사람만: 매핑 해제(대칭 롤백, arm.py의 disarm()과 동일하게 가벼운 게이트)."""
    if not human.is_human:
        raise PermissionDenied("unregister_strategy는 사람만")
    row = {"profile_name": profile_name, "strategy_id": None, "action": "unregister",
           "registered_by": human.name,
           "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _append(row)
    record({"layer": "agent_gate", "action": "unregister_strategy",
            "profile_name": profile_name, "registered_by": human.name, "result": "unregistered"})
    return {"profile_name": profile_name, "registered": False}


def validation_of(agent: dict) -> dict:
    """에이전트의 전략 검증 상태. 반환: {validated, strategy_id, reason}."""
    # agent["type"]이 유일한 실제 키(AGENT_PROFILES 인덱스와 동일) — profile.name/style/
    # profile_name은 어디서도 채워지지 않는 죽은 필드였음(항상 빈 문자열 → 매핑 영구 미스).
    profile_name = str(agent.get("type") or "")
    sid = _current_mapping().get(profile_name)
    if not sid:
        return {"validated": False, "strategy_id": None,
                "reason": "registry 미등록 전략(교과서 신호) — 검증 트랙 통과 이력 없음"}
    try:
        for r in StrategyRegistry().all_current():
            if r["strategy_id"] == sid:
                ok = r["status"] in _VALIDATED_STATUSES
                return {"validated": ok, "strategy_id": sid,
                        "reason": f"registry {r['status']}" + ("" if ok else " — 검증 상태 아님")}
    except Exception as exc:  # noqa: BLE001
        return {"validated": False, "strategy_id": sid, "reason": f"registry 조회 실패: {exc}"}
    return {"validated": False, "strategy_id": sid, "reason": "registry에 없음"}


def enforce_paper(agent: dict) -> tuple[bool, str | None]:
    """live 요청 에이전트가 미검증이면 페이퍼 강제.

    God Mode(agent["god_mode"]) 승급 에이전트는 registry 트랙과 무관한 별도
    3조건 실적 심사(api_server/god_mode.py)를 이미 통과했으므로 여기서 면제.

    반환: (paper 최종값, 차단 사유 또는 None). 감사 로그는 호출부가 남김.
    """
    paper = bool(agent.get("paper", True))
    if paper:
        return True, None
    if agent.get("god_mode"):
        return False, None
    v = validation_of(agent)
    if v["validated"]:
        return False, None
    return True, f"live 차단 → 페이퍼 강제: {v['reason']}"
