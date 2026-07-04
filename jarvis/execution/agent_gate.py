"""트레이딩 에이전트 ↔ 전략 registry 게이트.

시스템 최대 모순 해소: 연구 트랙은 BH-FDR·레드팀 통과해야 페이퍼로 가는데,
트레이딩 에이전트는 registry 무관한 교과서 신호(intraday_score·모멘텀)로
실계좌 매매 가능했음. 규칙:

  - 에이전트 전략이 registry 검증 상태가 아니면 → live 주문 차단, 페이퍼 강제.
  - 매핑은 명시적으로만(PROFILE_TO_STRATEGY) — 암묵 매칭 금지.
  - 지금은 매핑이 비어 있음 = 모든 에이전트 미검증 = live 전부 차단(정직한 현주소).
    검증된 전략을 에이전트로 돌리려면 여기 매핑 추가 + registry 상태가 증명해야 함.
"""
from __future__ import annotations

# 에이전트 profile 이름 → registry strategy_id. 검증된 전략만 등록할 것.
# (등록해도 live는 registry 상태 + Lv6 + 사람 arm 게이트가 별도로 막음)
PROFILE_TO_STRATEGY: dict[str, str] = {}

# registry에서 "검증됨"으로 인정하는 상태 — paper 단계 이상(사전등록 게이트 통과분)
_VALIDATED_STATUSES = {
    "paper_candidate", "paper_candidate_forward_test_required",
    "paper_active", "micro_live", "live",
}


def validation_of(agent: dict) -> dict:
    """에이전트의 전략 검증 상태. 반환: {validated, strategy_id, reason}."""
    profile_name = str((agent.get("profile") or {}).get("name")
                       or agent.get("style") or agent.get("profile_name") or "")
    sid = PROFILE_TO_STRATEGY.get(profile_name)
    if not sid:
        return {"validated": False, "strategy_id": None,
                "reason": "registry 미등록 전략(교과서 신호) — 검증 트랙 통과 이력 없음"}
    try:
        from jarvis.registry import StrategyRegistry
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

    반환: (paper 최종값, 차단 사유 또는 None). 감사 로그는 호출부가 남김.
    """
    paper = bool(agent.get("paper", True))
    if paper:
        return True, None
    v = validation_of(agent)
    if v["validated"]:
        return False, None
    return True, f"live 차단 → 페이퍼 강제: {v['reason']}"
