"""검토(REVIEW) 엔진.

LAB 라이브 루프(evaluate) = 실데이터 경로만: blocked / real_registry / real_event.
evaluate_real_event가 실 KRX PIT event_study + 레드팀으로 판정한다.

evaluate_synthetic = LAB 루프가 아니라 **jarvis 배치 파이프라인**(BH-FDR 데모/테스트
하네스)이 직접 호출하는 합성 백테스트. per-event iid 모델(edge+noise vs edge=0 random)로
진짜 empirical p-value를 내지만 데이터는 합성 → synthetic_demo 배지. LAB 루프는 이 경로로
절대 오지 않는다(evaluate가 raise).
"""
from __future__ import annotations

import random as _random

from research.lab.hypotheses import Hypothesis
from research.validation.baselines import empirical_p_value

NOTIONAL = 1000.0       # 이벤트당 명목(100원 * 10주 근사)
EVENT_SIGMA = 0.025     # 이벤트 forward 수익 노이즈(홀드 구간 2.5%)


def _event_returns(n: int, edge: float, sigma: float, rng: _random.Random) -> list[float]:
    return [edge + rng.gauss(0.0, sigma) for _ in range(n)]


def _net(returns: list[float], cost_bps: float) -> float:
    cost = NOTIONAL * (cost_bps / 10_000.0)   # 편도 비용(익일 시가 진입 청산 근사)
    return round(sum(NOTIONAL * r - cost for r in returns), 6)


def evaluate_synthetic(h: Hypothesis, cost_bps: float | None = None, n_runs: int = 500) -> dict:
    """[jarvis 배치/테스트 전용] 전략 이벤트(edge 포함) net vs 매칭 random(edge=0) 분포.
    진짜 empirical p-value지만 데이터는 합성. LAB 라이브 루프는 이 함수를 쓰지 않는다."""
    cost = h.cost_bps if cost_bps is None else cost_bps
    n = h.n_trades
    edge = h.edge_bps / 10_000.0
    rng = _random.Random(h.seed or 42)

    strat_rets = _event_returns(n, edge, EVENT_SIGMA, rng)
    strat_net = _net(strat_rets, cost)

    # 매칭 random: 동일 이벤트수·동일 노이즈·동일 비용, edge=0
    rand_rng = _random.Random((h.seed or 42) + 999)
    rand_nets = [_net(_event_returns(n, 0.0, EVENT_SIGMA, rand_rng), cost) for _ in range(n_runs)]
    ev = empirical_p_value(strat_net, rand_nets)

    audit = {"ok": True, "n_bars": n, "events": n,
             "note": "합성 데모 — 진짜 empirical p-value, 데이터만 합성"}

    # walk-forward 2분할(이벤트 절반씩)
    mid = n // 2
    wf_first = _net(strat_rets[:mid], cost) if mid else 0.0
    wf_second = _net(strat_rets[mid:], cost) if n - mid else 0.0

    powered = n >= 30
    pct = ev["percentile"] or 0.0
    p = ev["p_value"] or 1.0
    passed = strat_net > 0 and pct >= 95 and p < 0.05 and wf_first > 0 and wf_second > 0
    weak = strat_net > 0 and pct >= 80
    if not powered:
        status, verdict = "underpowered_demo", "UNDERPOWERED — 표본<30(더 긴 데이터 필요)"
    elif passed:
        status, verdict = "watchlist_demo", "WATCHLIST(데모) — random·비용·WF 통과 (합성)"
    elif weak:
        status, verdict = "weak_demo", "WEAK — random 80~95pct, 확신 부족"
    else:
        status, verdict = "reject_demo", "REJECT — 매칭 random·비용 못 넘음"

    return {
        "data_mode": "synthetic_demo",
        "audit": audit,
        "backtest": {"strategy_net": strat_net, "n_trades": n, "hold": h.holding[0] if h.holding else 0, "cost_bps": cost},
        "random": {"percentile": ev["percentile"], "p_value": ev["p_value"],
                   "random_median": ev["random_median"], "n_runs": n_runs, "beating": ev["random_beating"]},
        "walk_forward": {"first": wf_first, "second": wf_second,
                         "both_positive": wf_first > 0 and wf_second > 0},
        "verdict": verdict,
        "status": status,
        "powered": powered,
    }


def evaluate_blocked(h: Hypothesis) -> dict:
    """데이터 게이트 — 실제로 파이프 미구축이면 BLOCKED_BY_DATA."""
    return {
        "data_mode": "blocked",
        "audit": {"ok": False, "note": h.kill,
                  "missing": ["release↔issuance linkage", "미상환 잔액(remaining balance) 재구성"]},
        "backtest": None, "random": None, "walk_forward": None,
        "verdict": "BLOCKED_BY_DATA — 검토 불가(데이터 게이트)",
        "status": "blocked_by_data", "powered": False,
    }


def evaluate_precomputed(h: Hypothesis) -> dict:
    """이미 검증난 실험 리플레이(진짜 registry 값)."""
    from research.agents.experiment_registry import already_tested
    rows = already_tested(h.precomputed_id or h.id)
    e = rows[-1] if rows else {}
    return {
        "data_mode": "real_registry",
        "audit": {"ok": True, "note": e.get("data_quality", "registry"),
                  "n_bars": e.get("n_rebal") or e.get("n_events")},
        "backtest": {"strategy_net": e.get("net_pnl"), "sharpe": e.get("sharpe"),
                     "ann_return": e.get("ann_return")},
        "random": {"percentile": e.get("random_pct"), "p_value": e.get("p")},
        "walk_forward": {"first": e.get("wf_first"), "second": e.get("wf_second"),
                         "both_positive": (e.get("wf_first") or 0) > 0 and (e.get("wf_second") or 0) > 0},
        "verdict": e.get("verdict", "(registry)"),
        "status": e.get("status", "unknown"),
        "powered": True,
    }


def evaluate(h: Hypothesis) -> dict:
    """LAB 라이브 루프 디스패처 — 실데이터 경로만. 합성은 여기로 오지 않는다
    (합성은 jarvis 배치 파이프라인이 evaluate_synthetic을 직접 호출)."""
    if h.data_mode == "blocked":
        return evaluate_blocked(h)
    if h.data_mode == "real_registry":
        return evaluate_precomputed(h)
    if h.data_mode == "real_event":
        return evaluate_real_event(h)
    raise ValueError(f"LAB 루프는 실데이터 경로만 처리: 알 수 없는 data_mode={h.data_mode!r}")


def evaluate_real_event(h: Hypothesis) -> dict:
    """실 이벤트 family 검증 — event_study(실 KRX PIT) + 레드팀 통제. 합성 아님.
    Auto-Research 실엔진을 LAB 루프에 연결. h.precomputed_id = family id."""
    from research.data.kr_dart_events import load_events
    from research.scanner.event_study import event_study, load_series
    from research.scanner.families import FAMILIES, redteam_spec
    from jarvis.redteam.review import review_strategy

    fam_id = h.precomputed_id or ""
    fam = FAMILIES.get(fam_id)
    ev = load_events(fam_id)
    if fam is None or len(ev) < 30:
        return {"data_mode": "real_event", "powered": False, "status": "underpowered",
                "audit": {"ok": False, "note": f"이벤트 {len(ev)}건 <30 — 데이터 부족/커버리지",
                          "missing": ["더 긴 PIT 데이터 또는 피드 커버리지"]},
                "backtest": None, "random": None, "walk_forward": None,
                "verdict": "UNDERPOWERED — 표본<30(실데이터 부족)"}

    series = load_series()
    res = event_study(ev, series, fam["direction"])
    if res.get("verdict") == "UNDERPOWERED" or res.get("p") is None:
        return {"data_mode": "real_event", "powered": False, "status": "underpowered",
                "audit": {"ok": False, "note": f"매칭 {res.get('n')}건 — UNDERPOWERED"},
                "backtest": None, "random": None, "walk_forward": None,
                "verdict": "UNDERPOWERED — 매칭 표본 부족"}

    rt = review_strategy(redteam_spec(fam_id, fam), res["evidence"])
    net, pct, p = res["net"], res["percentile"], res["p"]
    wf1, wf2 = res["wf_first"], res["wf_second"]
    redteam_ok = rt["verdict"] == "CLEARED"
    if not redteam_ok:
        status, verdict = "reject_real", f"REJECT — 레드팀 통제 실패: {','.join(rt.get('failed', []))}"
    elif net > 0 and (pct or 0) >= 95 and (p or 1) < 0.05 and wf1 > 0 and wf2 > 0:
        status, verdict = "candidate_real", "CANDIDATE — random·비용·WF·레드팀 전부 통과 (실데이터)"
    elif net > 0 and (pct or 0) >= 80:
        status, verdict = "watchlist_real", f"WATCHLIST — 양수·pct {pct}, 확신 부족(옐로)"
    else:
        status, verdict = "reject_real", "REJECT — 매칭 random·비용 못 넘음"

    return {
        "data_mode": "real_event",
        "audit": {"ok": True, "note": f"실 KRX PIT · survivorship-free · 이벤트 {res['n']}건",
                  "n_bars": res["n"], "events": res["n"]},
        "backtest": {"strategy_net": net, "n_trades": res["n"], "hold": 20, "cost_bps": h.cost_bps,
                     "median": res.get("median"), "top_tail": res.get("top_tail_share")},
        "random": {"percentile": pct, "p_value": p, "random_median": res.get("median"),
                   "n_runs": "perm", "beating": None},
        "walk_forward": {"first": wf1, "second": wf2, "both_positive": wf1 > 0 and wf2 > 0},
        "verdict": verdict, "status": status, "powered": True,
        "redteam": rt["verdict"], "redteam_failed": rt.get("failed", []),
    }
