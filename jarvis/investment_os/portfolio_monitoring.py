"""Portfolio Monitoring — (페이퍼) 포트폴리오 모니터링. **관찰만, 실행 없음.**

추천 포트폴리오 vs 현재(페이퍼) 상태의 드리프트·노출·리스크예산 준수를 관찰. 실제 포지션 조회는
페이퍼/시뮬 상태만(브로커 미연결). 알림은 자문 — 사람이 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def monitor_portfolio(target: dict, current: dict | None = None) -> dict:
    """추천(target) vs 현재(current, 페이퍼) 드리프트·노출·리스크예산 관찰. 자문 알림. 실행 없음."""
    tw = (target or {}).get("weights") or {}
    cw = (current or {}).get("weights") or {}
    drift = {}
    for sym in sorted(set(tw) | set(cw)):
        d = round(float(tw.get(sym, 0.0)) - float(cw.get(sym, 0.0)), 4)
        if abs(d) > 1e-6:
            drift[sym] = d
    max_drift = max((abs(d) for d in drift.values()), default=0.0)
    rb = _safe(lambda: __import__("jarvis.investment_os.risk_budgeting",
                                  fromlist=["build_risk_budget"]).build_risk_budget(current or target), {}) or {}
    alerts = []
    if max_drift > 0.1:
        alerts.append({"type": "DRIFT", "detail": f"max drift {round(max_drift, 4)} > 0.1"})
    if not rb.get("within_budget", True):
        alerts.append({"type": "RISK_BUDGET", "detail": "risk contribution over cap"})
    return {"drift": drift, "max_drift": round(max_drift, 4),
            "within_risk_budget": rb.get("within_budget", True), "alerts": alerts,
            "is_paper_state": True, "reads_broker": False,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Portfolio Monitoring(관찰) — 드리프트·노출·리스크예산. 페이퍼 상태만(브로커 미연결). "
                     "알림은 자문, 사람이 결정. 실행 없음.")}
