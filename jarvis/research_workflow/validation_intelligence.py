"""Automated Validation Intelligence (P187) — Backtest/Paper/Forward 결과 비교. **분석만, 실행 없음.**

생성: Validation Report. 분석 5개 갭: performance·risk·cost·regime·behavioral.
분류: ROBUST · QUESTIONABLE · FAILED. 실패 이유 자동 분류.

**재사용**: validation_gap(P105)·paper_validation(P103). 새 엔진 없음.
원칙(문서 §Constitution, §P187): 통합·조율만 · 결정적 · 자문 전용 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _gap(a, b):
    na, nb = _num(a), _num(b)
    if na is None or nb is None:
        return None
    return round(na - nb, 4)


def _five_gaps(backtest, paper, forward):
    """5개 갭(결정적). 값 없으면 None(정직한 결측)."""
    bm = (backtest or {}).get("metrics") or backtest or {}
    pm = (paper or {}).get("metrics") or paper or {}
    fm = (forward or {}).get("metrics") or forward or {}
    ref = pm or fm
    return {
        "performance_gap": _gap(bm.get("sharpe"), ref.get("sharpe")),
        "risk_gap": _gap(bm.get("max_drawdown"), ref.get("max_drawdown")),
        "cost_gap": _gap(bm.get("return"), ref.get("return")),
        "regime_gap": _gap(bm.get("out_of_sample"), bm.get("walk_forward")),
        "behavioral_gap": _gap(bm.get("win_rate"), ref.get("win_rate")),
    }


def _classify(gaps, gap_analysis):
    """ROBUST/QUESTIONABLE/FAILED(결정적) + 실패 이유."""
    perf = gaps.get("performance_gap")
    regime = gaps.get("regime_gap")
    reasons = []
    # 큰 성능/레짐 붕괴 → FAILED
    if perf is not None and perf >= 0.5:
        reasons.append("백테스트가 페이퍼 대비 과대(overfit 신호)")
    if regime is not None and regime <= -0.5:
        reasons.append("OOS 가 워크포워드 대비 붕괴(레짐 취약)")
    # validation_gap 이 실패 신호를 주면 반영
    vg_flag = str((gap_analysis or {}).get("classification")
                  or (gap_analysis or {}).get("verdict") or "").upper()
    if "FAIL" in vg_flag or "BACKTEST_SUCCESS_PAPER_FAILURE" in str(gap_analysis):
        reasons.append("validation_gap: 백테스트 성공·페이퍼 실패 패턴")
    if reasons:
        return "FAILED", reasons
    # 갭이 대부분 결측이거나 중간 → QUESTIONABLE
    known = [v for v in gaps.values() if v is not None]
    if len(known) < 2:
        return "QUESTIONABLE", ["검증 데이터 부족 — 페이퍼/포워드 결과 필요"]
    if any(abs(v) >= 0.3 for v in known):
        return "QUESTIONABLE", ["일부 갭이 큼 — 추가 검증 필요"]
    return "ROBUST", []


def build_validation_report(backtest: dict, paper: dict | None = None, *,
                            forward: dict | None = None, spec: dict | None = None) -> dict:
    """Backtest/Paper/Forward 비교 → Validation Report(5갭 + 분류 + 실패이유). 결정적·읽기전용."""
    gaps = _five_gaps(backtest, paper or {}, forward or {})
    gap_analysis = _safe(lambda: __import__("jarvis.research_workflow.validation_gap",
                                            fromlist=["analyze_gap"]
                                            ).analyze_gap(backtest or {}, paper or {}, spec=spec), {}) or {}
    paper_check = _safe(lambda: __import__("jarvis.research_workflow.paper_validation",
                                           fromlist=["validate"]).validate(backtest or {}, paper or {}),
                        {}) or {}
    classification, reasons = _classify(gaps, gap_analysis)
    return {"classification": classification, "failure_reasons": reasons,
            "gaps": gaps,
            "gap_analysis": {k: gap_analysis.get(k) for k in
                             ("classification", "verdict", "gap_score", "dimensions") if k in gap_analysis},
            "paper_validation": {k: paper_check.get(k) for k in
                                 ("status", "verdict", "difference") if k in paper_check},
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Automated Validation Intelligence(읽기전용) — 5갭 비교 + ROBUST/QUESTIONABLE/FAILED. "
                     "validation_gap·paper_validation 재사용. 새 엔진 없음. 사람이 결정.")}
