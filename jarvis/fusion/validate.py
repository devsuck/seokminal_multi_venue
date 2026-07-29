"""가중 스킴 결정적 속성검사 — 각 버전은 이걸 통과해야 'passed'.

research.validation 철학과 동형: 스킴은 사전고정 속성을 만족해야 승격.
순수 함수(원장/네트워크 무관). CLI `python -m jarvis.fusion validate`가 호출.
"""
from __future__ import annotations

from jarvis.fusion.fusion import FusionEngine
from jarvis.fusion.performance import perf_from_returns
from jarvis.fusion.types import StrategySignal
from jarvis.fusion.weighting import get_scheme


def _perf(sid: str, returns: list[float]):
    return perf_from_returns(sid, returns, "synthetic")


def validate_scheme(scheme_name: str = "v1_risk_adjusted") -> dict:
    """스킴 속성검사. 반환: {scheme, implemented, passed, checks:[{name,ok,detail}]}."""
    scheme = get_scheme(scheme_name)
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    if not scheme.implemented:
        return {"scheme": scheme_name, "implemented": False, "passed": False,
                "checks": [{"name": "implemented", "ok": False, "detail": "pending 스킴 — 미구현"}]}

    # 합성 성과: 강한 양(+Sharpe), 약한 양, 손실(-Sharpe), 소표본.
    strong = _perf("STRONG", [0.02, 0.03, 0.025, 0.015, 0.028] * 8)   # n=40, +Sharpe
    weak = _perf("WEAK", [0.001, 0.002, -0.001, 0.0015, 0.0005] * 8)  # n=40, 약 +
    losing = _perf("LOSE", [-0.02, -0.01, -0.03, -0.015, -0.02] * 8)  # n=40, -Sharpe
    small = _perf("SMALL", [0.02, 0.03, 0.025])                        # n=3, 소표본

    # 1) 가중합 = 1 (양 score 존재 시)
    w = scheme.weights({"STRONG": strong, "WEAK": weak})
    add("weights_sum_to_one", abs(sum(w.values()) - 1.0) < 1e-9, f"sum={sum(w.values()):.6f}")

    # 2) 단조성 — 높은 score가 더 큰 가중
    add("monotonic_in_score", w["STRONG"] >= w["WEAK"],
        f"STRONG={w['STRONG']:.4f} WEAK={w['WEAK']:.4f}")

    # 3) 손실전략 = 0표
    w2 = scheme.weights({"STRONG": strong, "LOSE": losing})
    add("losing_gets_zero_weight", w2.get("LOSE", 0.0) == 0.0, f"LOSE={w2.get('LOSE'):.4f}")

    # 4) 소표본 수축 — 같은 수익률형태라도 n 작으면 score 작음
    add("underpowered_shrinks_score", small.score < strong.score and small.underpowered,
        f"small.score={small.score} strong.score={strong.score}")

    # 5) degenerate — 전부 0표면 크래시 없이 flat
    eng = FusionEngine(scheme_name)
    fs0 = eng.fuse([StrategySignal("LOSE", "AAA", 1)], {"LOSE": losing})
    add("degenerate_no_crash", fs0 and fs0[0].direction == 0 and fs0[0].confidence == 0.0,
        f"dir={fs0[0].direction} conf={fs0[0].confidence}")

    # 6) 방향정합 — 단일 롱(양 score) → 합성 +1, confidence 1
    fs1 = eng.fuse([StrategySignal("STRONG", "BBB", 1)], {"STRONG": strong})
    add("direction_correct_long", fs1[0].direction == 1 and abs(fs1[0].confidence - 1.0) < 1e-9,
        f"dir={fs1[0].direction} conf={fs1[0].confidence}")

    # 7) 상쇄 — 같은 가중 롱/숏이면 net 0
    fs2 = eng.fuse([StrategySignal("A", "CCC", 1), StrategySignal("B", "CCC", -1)],
                   {"A": strong, "B": _perf("B", [0.02, 0.03, 0.025, 0.015, 0.028] * 8)})
    add("opposing_nets_out", fs2[0].direction == 0, f"score={fs2[0].score}")

    passed = all(c["ok"] for c in checks)
    return {"scheme": scheme_name, "implemented": True, "passed": passed, "checks": checks}
