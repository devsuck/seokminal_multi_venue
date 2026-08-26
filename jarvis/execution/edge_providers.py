"""전략별 arm_criteria 호환 edge 판정 프로바이더 — 명시 레지스트리.

fusion/adapters/__init__.py의 "암묵 매칭 금지, 명시적 매핑" 원칙과 동일.
edge provider 없는 전략은 항상 GO 거부(정직한 기본값).
"""
from __future__ import annotations

import datetime as _dt
from typing import Callable

EdgeProviderFn = Callable[[], tuple[dict, float]]  # -> (edge_dict, paper_months)
EDGE_PROVIDERS: dict[str, EdgeProviderFn] = {}

# venue 미등록 = live_router가 "unsupported_venue"로 거부(안전한 기본값).
# tsmom은 futures/32개 시장이라 단일 venue 없음 — 의도적으로 비워둠.
EDGE_PROVIDER_VENUE: dict[str, str] = {}

# 전략별 forward-cohort 시작일(YYYY-MM-DD) 조회 함수 — 각 config 모듈의 FROZEN_AT을
# 호출 시점에 그대로 읽는다(paper_months 계산과 동일한 방식 — 문자열로 박아두면 config
# monkeypatch/변경과 따로 놀아 검증이 어긋난다). arm_criteria_v2.evaluate가 이 날짜
# 이후 달만 forward OOS로 검증. 미등록 전략은 edge_go()가 항상 False(정직한 기본값).
EDGE_PROVIDER_COHORT_START: dict[str, Callable[[], str]] = {}


def _buyback_edge_provider() -> tuple[dict, float]:
    from research.paper import buyback_config as CFG
    from research.paper.buyback_edge import edge_status
    s = edge_status()
    months = (_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0
    return s, round(months, 1)


def _buyback_cohort_start() -> str:
    from research.paper import buyback_config as CFG
    return CFG.FROZEN_AT


EDGE_PROVIDERS["kr_dart_buyback_drift_v1"] = _buyback_edge_provider
EDGE_PROVIDER_VENUE["kr_dart_buyback_drift_v1"] = "KR"
EDGE_PROVIDER_COHORT_START["kr_dart_buyback_drift_v1"] = _buyback_cohort_start


def _tsmom_edge_provider() -> tuple[dict, float]:
    from research.paper import tsmom_config as CFG
    from research.paper.tsmom_edge import edge_status
    s = edge_status()
    months = (_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0
    return s, round(months, 1)


def _tsmom_cohort_start() -> str:
    from research.paper import tsmom_config as CFG
    return CFG.FROZEN_AT


EDGE_PROVIDERS["futures_tsmom_32mkt"] = _tsmom_edge_provider
EDGE_PROVIDER_COHORT_START["futures_tsmom_32mkt"] = _tsmom_cohort_start
# venue 의도적 미등록 — _kr_last_close/_kr_position_qty가 KR 종목코드 전제라 futures엔 불가.
# live_router._build_order()가 venue!="KR"이면 "unsupported_venue"로 거부(안전).


def _tom_edge_provider() -> tuple[dict, float]:
    from research.paper import tom_config as CFG
    from research.paper.tom_edge import edge_status
    s = edge_status()
    months = (_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0
    return s, round(months, 1)


def _tom_cohort_start() -> str:
    from research.paper import tom_config as CFG
    return CFG.FROZEN_AT


EDGE_PROVIDERS["kr_turn_of_month_v1_PORTFOLIO"] = _tom_edge_provider
EDGE_PROVIDER_VENUE["kr_turn_of_month_v1_PORTFOLIO"] = "KR"
EDGE_PROVIDER_COHORT_START["kr_turn_of_month_v1_PORTFOLIO"] = _tom_cohort_start


def _factor_edge_provider(fid: str):
    def _fn() -> tuple[dict, float]:
        from research.paper import factor_config as CFG
        from research.paper.factor_forward import generate
        cfg = CFG.CANDIDATES[fid]
        r = generate(fid, write=False)
        env, fwd, dev = r["backtest_envelope"], r["forward_months"], r["envelope_deviation"]
        oos = [{"month": m, "return": fwd[m], "in_envelope": dev[m] == "in_envelope"} for m in sorted(dev)]
        n_oos, n_in = len(oos), sum(1 for o in oos if o["in_envelope"])
        need = CFG.MIN_OBSERVATION_MONTHS
        if n_oos == 0:
            status = "no_oos_yet"
        elif n_in / n_oos < 0.5:
            status = "drifting"
        elif n_oos < need:
            status = "accumulating"
        else:
            status = "confirmed"
        s = {"status": status, "in_sample_months": env.get("n_months", 0),
             "envelope": {"p10": env.get("monthly_p10"), "avg": env.get("monthly_mean"), "p90": env.get("monthly_p90")},
             "oos_months": n_oos, "oos_in_envelope": n_in, "need_months": need, "oos": oos}
        months = (_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0
        return s, round(months, 1)
    return _fn


from research.paper import factor_config as _FCFG

for _fid, _cfg in _FCFG.CANDIDATES.items():
    EDGE_PROVIDERS[_cfg["version"]] = _factor_edge_provider(_fid)
    EDGE_PROVIDER_VENUE[_cfg["version"]] = "KR"
    EDGE_PROVIDER_COHORT_START[_cfg["version"]] = lambda: _FCFG.FROZEN_AT


def edge_go(strategy_id: str) -> bool:
    """arm_criteria v2 GO 여부(forward-cohort 검증 포함). provider 또는 cohort_start
    미등록 전략은 항상 False(정직한 기본값)."""
    fn = EDGE_PROVIDERS.get(strategy_id)
    cohort_start_fn = EDGE_PROVIDER_COHORT_START.get(strategy_id)
    if fn is None or cohort_start_fn is None:
        return False
    from jarvis.execution.arm_criteria_v2 import evaluate
    edge, months = fn()
    return evaluate(edge, months, cohort_start_fn()).get("decision") == "GO"
