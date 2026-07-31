"""Prediction Capture Hook (P202-2) — 연구 산출을 예측 레지스트리로 흘려보내는 **최소 인터페이스**. **전달만.**

목적: committee·agent·hypothesis 산출 → `capture_prediction()`. "누가 생성했나 · confidence · thesis ·
invalidation" 만 뽑아 registry 에 전달. **의도적으로 최소** — scoring·evaluation·ranking·dashboard 없음.

'나중에 붙이자'로 미루면 시계가 안 돈다 → 인터페이스는 지금 확정, 완성형 연결은 나중.
**재사용**: prediction_registry(P201). 새 원장 없음.
원칙(§Constitution): 통합·조율만 · 결정적 · 자문 전용 · 거래·집행 없음 · 사람이 결정.
"""
from __future__ import annotations

_CONF_MAP = {"HIGH": "HIGH", "MEDIUM": "MEDIUM", "MED": "MEDIUM", "LOW": "LOW"}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _norm_conf(v) -> str:
    """confidence 를 HIGH/MEDIUM/LOW 로 정규화(문자열 또는 0~1 점수)."""
    if isinstance(v, (int, float)):
        return "HIGH" if v >= 0.66 else ("MEDIUM" if v >= 0.4 else "LOW")
    return _CONF_MAP.get(str(v or "").strip().upper(), "MEDIUM")


def _capture(**kw):
    from jarvis.research_workflow.prediction_registry import capture_prediction
    return capture_prediction(**kw)


def _evidence_from_committee(p: dict) -> list:
    """supporting_evidence(dict: evidence/arguments/bull_case) → 실제 근거 텍스트 최대 5개.

    build_committee_packet() 이 반환하는 supporting_evidence 는 카테고리별 dict — 리스트가 아니다.
    bull_case.evidence[].text(개별 실험 근거) 우선, 없으면 arguments[].rationale(렌즈별 논거),
    그래도 없으면 evidence.sources(카테고리명)로 폴백.
    """
    se = p.get("supporting_evidence")
    if isinstance(se, list):
        return [str(e) for e in se][:5]
    se = se or {}
    out = []
    for e in (se.get("bull_case") or {}).get("evidence", []) or []:
        text = e.get("text") if isinstance(e, dict) else str(e)
        if text:
            out.append(str(text))
    for a in se.get("arguments") or []:
        if isinstance(a, dict) and a.get("rationale"):
            out.append(f"{a.get('lens', '')}: {a['rationale']}".strip(": "))
    if not out:
        out = [str(s) for s in (se.get("evidence") or {}).get("sources", []) or []]
    return out[:5]


def capture_from_committee(packet: dict, *, strategy_id: str = "", strategy_family: str = "",
                           now: str = "", commit: bool = False) -> dict:
    """Investment Committee packet → 예측 사전등록. thesis=research_summary, source=committee."""
    p = packet or {}
    thesis = str(p.get("research_summary") or p.get("summary") or "")
    limitations = p.get("limitations") or []
    invalidation = str(limitations[0]) if limitations else ""
    return _capture(thesis=thesis, strategy_id=strategy_id, strategy_family=strategy_family,
                    confidence=_norm_conf(p.get("confidence")), source="committee",
                    invalidation_condition=invalidation,
                    evidence_used=_evidence_from_committee(p),
                    now=now, commit=commit)


def capture_from_agent(workflow: dict, *, strategy_id: str = "", strategy_family: str = "",
                       now: str = "", commit: bool = False) -> dict:
    """multi_agent_workflow / collaborative_research 산출 → 예측 사전등록. source=agent."""
    w = workflow or {}
    report = w.get("report") or {}
    review = w.get("review") or {}
    thesis = str(report.get("thesis") or w.get("objective") or w.get("hypothesis") or "")
    return _capture(thesis=thesis, strategy_id=strategy_id, strategy_family=strategy_family,
                    confidence=_norm_conf(report.get("confidence")), source="agent",
                    invalidation_condition=str(review.get("verdict") or ""),
                    now=now, commit=commit)


def capture_from_hypothesis(research_hypothesis: dict, *, strategy_family: str = "",
                            now: str = "", commit: bool = False) -> dict:
    """P183 Research Hypothesis / discovery 산출 → 예측 사전등록. source=automatic_discovery."""
    h = research_hypothesis or {}
    return _capture(thesis=str(h.get("question") or h.get("statement") or ""),
                    strategy_id=str(h.get("hypothesis_id") or ""),
                    strategy_family=strategy_family,
                    confidence=_norm_conf(h.get("confidence")),
                    source="automatic_discovery",
                    invalidation_condition=str((h.get("required_test") or [""])[0]
                                               if h.get("required_test") else ""),
                    evidence_used=[str(e) for e in (h.get("supporting_evidence") or [])][:5],
                    expected_horizon=str(h.get("expected_horizon") or ""),
                    now=now, commit=commit)


def capture_research_output(source: str, *, thesis: str, confidence="MEDIUM", strategy_id: str = "",
                            strategy_family: str = "", invalidation_condition: str = "",
                            evidence_used=None, expected_horizon: str = "", expected_return=None,
                            expected_risk=None, now: str = "", commit: bool = False) -> dict:
    """범용 훅 — human/writer 등 임의 소스. 필드만 전달(정규화). scoring/eval/dashboard 없음."""
    src = str(source or "human_hypothesis")
    src = src if src in ("committee", "agent", "human_hypothesis", "automatic_discovery") else "human_hypothesis"
    return _capture(thesis=thesis, strategy_id=strategy_id, strategy_family=strategy_family,
                    confidence=_norm_conf(confidence), source=src,
                    invalidation_condition=invalidation_condition, evidence_used=evidence_used,
                    expected_horizon=expected_horizon, expected_return=expected_return,
                    expected_risk=expected_risk, now=now, commit=commit)
