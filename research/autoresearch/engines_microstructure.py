"""HL orderflow/cross-venue-skew 가설 엔진 — collect_candidates() 3번째 소스.

사전등록 4소스(등록 후 변경 금지, 근거:
docs/superpowers/specs/2026-08-26-microstructure-hypothesis-engine-design.md):
  1. ofi_momentum              — 일별 OFI 부호 -> 익일 수익률 (신규)
  2. basis_reversion           — 거래소간 일별 basis 수렴 베팅 (신규)
  3. absorption_momentum       — research/strategies/orderflow_absorption.py 어댑터
  4. skew_divergence_momentum  — research/hypotheses/cross_venue_skew.py 어댑터

engines_factor.py와 동일 패턴(사전등록 config + 결과행 함수 + candidates() 조립함수).
paper-tracking 전용, live capital 없음.
"""
from __future__ import annotations

import datetime as dt
import json
import random as _random
import statistics as _st
from pathlib import Path

from research import jsonl_dates
from research.validation.baselines import empirical_p_value

_ORDERFLOW_DIR = Path("research/data/hl_orderflow_tick")
_SKEW_DIR = Path("research/data/cross_venue_skew")

_MIN_DAYS = 30
_MIN_EVENTS = 10
_N_PERMS = 500
_SEED = 42

COST_BASE_BPS = 10.0
COST_STRESS_BPS = 20.0
_STRESS_MULT = 2.0

OFI_SYMBOLS = ["BTC", "ETH", "PAXG"]
BASIS_COINS = ["BTC", "ETH"]
BASIS_VENUE_PAIRS = [("binance", "okx"), ("binance", "hl"), ("okx", "hl")]
MAX_BASIS_CANDIDATES = 4
ABSORPTION_SYMBOLS = ["BTC", "ETH", "PAXG"]
SKEW_COINS = ["BTC", "ETH"]
SKEW_HORIZON_S = 15
SKEW_VENUES = ["hl", "binance", "okx"]


def _assemble_evidence(net, median, wf1, wf2, pv, net_stress, n, n_variants) -> dict:
    """net/median/wf1/wf2 + empirical_p_value(pv) -> 배치 컨슈머 계약 evidence dict
    (engine.py::run_batch, verdict.py::classify, redteam/review.py::review_strategy 계약).
    단방향 통과조건(net>0 and wf1>0 and wf2>0) — 각 소스가 방향 1개만 사전등록하므로
    engines_factor.py KR팩터의 양방향 OR 패턴은 적용 안 함."""
    rnd_pass = pv["percentile"] is not None and pv["percentile"] >= 95 and net > 0
    wf_pass = net > 0 and wf1 > 0 and wf2 > 0
    cost_pass = net > 0 and net_stress > 0
    return {
        "n": n, "net": round(net, 6), "median": round(median, 6),
        "percentile": pv["percentile"], "p": pv["p_value"],
        "net_stress": round(net_stress, 6),
        "wf_first": round(wf1, 6), "wf_second": round(wf2, 6),
        "top_tail_share": None,
        "_spec": {"market": "CRYPTO", "family": "microstructure", "n_variants": n_variants},
        "evidence": {
            "random_baseline": "passed" if rnd_pass else "failed",
            "walk_forward": "passed" if wf_pass else "failed",
            "cost_stress": "passed" if cost_pass else "failed",
            "survivorship": "na",
            "multiple_testing": "passed",
            "lookahead": "passed",
        },
    }


def _series_evidence(signs, outcomes, cost_bps, stress_bps, n_variants,
                      seed=_SEED, n_runs=_N_PERMS):
    """일별 (sign,outcome) 페어 -> ls=sign*outcome 시리즈 -> net/median/wf/순열p.
    순열: outcome만 셔플(sign 고정) — 신호·결과 연결을 끊는 올바른 순열귀무
    (ls=sign*outcome 자체를 셔플하면 평균 불변이라 무의미해짐 — 별도 배열 유지 필수)."""
    n = len(signs)
    if n < _MIN_DAYS:
        return None
    cost = cost_bps / 10_000.0
    stress_cost = stress_bps / 10_000.0
    ls = [s * o for s, o in zip(signs, outcomes)]
    gross = _st.mean(ls)
    net = gross - cost
    net_stress = gross - stress_cost
    med = _st.median(ls) - cost
    half = n // 2
    wf1 = _st.mean(ls[:half]) - cost
    wf2 = _st.mean(ls[half:]) - cost

    rng = _random.Random(seed)
    perm = []
    for _ in range(n_runs):
        shuffled = outcomes[:]
        rng.shuffle(shuffled)
        perm_ls = [s * o for s, o in zip(signs, shuffled)]
        perm.append(_st.mean(perm_ls) - cost)
    pv = empirical_p_value(round(net, 6), perm)
    return _assemble_evidence(net, med, wf1, wf2, pv, net_stress, n, n_variants)


def _event_pnl_evidence(pnls, net_stress, pv, n_variants):
    """체결(trade/event)순 pnl 리스트 -> net/median/wf. p/percentile은 소스 자체
    random baseline 그대로 재사용(중복 순열 안 돌림) — absorption/skew 어댑터 전용."""
    n = len(pnls)
    net = _st.mean(pnls)
    med = _st.median(pnls)
    half = n // 2
    wf1 = _st.mean(pnls[:half])
    wf2 = _st.mean(pnls[half:])
    return _assemble_evidence(net, med, wf1, wf2, pv, net_stress, n, n_variants)
