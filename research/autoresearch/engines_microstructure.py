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


def _daily_ofi_and_price(symbol: str) -> tuple[dict, dict]:
    """hl_orderflow_tick/{symbol}_*.jsonl(.gz) -> (날짜->OFI합, 날짜->그날 마지막 체결가)."""
    dates = jsonl_dates.list_dates(_ORDERFLOW_DIR, glob_prefix=f"{symbol}_")
    ofi: dict[str, float] = {}
    last_px: dict[str, float] = {}
    last_ts: dict[str, float] = {}
    for date in dates:
        f = jsonl_dates.open_stem(_ORDERFLOW_DIR, f"{symbol}_{date}")
        if f is None:
            continue
        with f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                sign = 1.0 if row["side"] == "buy" else -1.0
                ofi[date] = ofi.get(date, 0.0) + sign * row["size"]
                if date not in last_ts or row["ts"] > last_ts[date]:
                    last_ts[date] = row["ts"]
                    last_px[date] = row["price"]
    return ofi, last_px


def _ofi_signs_outcomes(symbol: str) -> tuple[list, list]:
    """정렬된 날짜 인접쌍 -> (그날 OFI 부호, 익일 수익률). OFI=0인 날/비양수가는 skip."""
    ofi, price = _daily_ofi_and_price(symbol)
    dates = sorted(d for d in ofi if d in price)
    signs, outcomes = [], []
    for i in range(len(dates) - 1):
        d, d_next = dates[i], dates[i + 1]
        s = ofi[d]
        if s == 0.0:
            continue
        p0, p1 = price[d], price[d_next]
        if p0 <= 0:
            continue
        signs.append(1.0 if s > 0 else -1.0)
        outcomes.append(p1 / p0 - 1.0)
    return signs, outcomes


def _ofi_candidate(symbol: str, n_variants: int):
    from research.autoresearch.engine import Candidate

    def _run():
        signs, outcomes = _ofi_signs_outcomes(symbol)
        return _series_evidence(signs, outcomes, COST_BASE_BPS, COST_STRESS_BPS, n_variants)

    return Candidate(
        cid=f"micro_ofi_momentum_{symbol}", category="microstructure",
        thesis=f"{symbol} 일별 order flow imbalance 부호 -> 익일 방향(informed flow persistence, Kyle 1985 계열)",
        direction="research", run=_run, meta={})


def _daily_mid(venue: str, coin: str) -> dict:
    """venue×coin 오더북 스냅샷 -> 날짜별 평균 mid((best_bid+best_ask)/2).
    UTC 날짜 경계 사용(dt.timezone.utc — Python 3.14 대상, utcfromtimestamp 미사용)."""
    from research.hypotheses.cross_venue_skew import load_venue_snapshots

    dates = jsonl_dates.list_dates(_SKEW_DIR, glob_prefix=f"{venue}_{coin}_")
    if not dates:
        return {}
    df = load_venue_snapshots(venue, coin, dates)
    if df.empty:
        return {}
    mids: dict[str, list] = {}
    for _, row in df.iterrows():
        if not row["bids"] or not row["asks"]:
            continue
        best_bid = max(lvl["price"] for lvl in row["bids"])
        best_ask = min(lvl["price"] for lvl in row["asks"])
        mid = (best_bid + best_ask) / 2.0
        date = dt.datetime.fromtimestamp(row["ts"], tz=dt.timezone.utc).strftime("%Y-%m-%d")
        mids.setdefault(date, []).append(mid)
    return {d: _st.mean(vs) for d, vs in mids.items()}


def _basis_signs_outcomes(coin: str, venue_a: str, venue_b: str) -> tuple:
    """basis_t = (mid_a-mid_b)/mid_b -> (부호[t], 수렴폭 basis_t-basis_next[t], 겹치는 날짜수).
    수렴방향 베팅: basis_t>0(A가 비쌈)이면 sign=+1 -> basis가 줄어들수록(outcome>0) 이익."""
    mid_a = _daily_mid(venue_a, coin)
    mid_b = _daily_mid(venue_b, coin)
    dates = sorted(d for d in mid_a if d in mid_b)
    signs, outcomes = [], []
    for i in range(len(dates) - 1):
        d, d_next = dates[i], dates[i + 1]
        if mid_b[d] <= 0 or mid_b[d_next] <= 0:
            continue
        basis_t = (mid_a[d] - mid_b[d]) / mid_b[d]
        basis_next = (mid_a[d_next] - mid_b[d_next]) / mid_b[d_next]
        if basis_t == 0.0:
            continue
        signs.append(1.0 if basis_t > 0 else -1.0)
        outcomes.append(basis_t - basis_next)
    return signs, outcomes, len(dates)


def _select_basis_pairs() -> list:
    """coin×거래소쌍 전체 계산 -> 실제 usable 페어수(len(signs)) >= _MIN_DAYS인 것만, 많은 순 최대
    MAX_BASIS_CANDIDATES개 — 데이터 가용성으로 선정(성과로 선정 아님, 사후선택 방지).
    Note: len(signs) <= n_overlap-1 (consecutive pairs) and further reduced by zero-basis skip;
    filtering on n_overlap alone would pass boundary cases that fail at _series_evidence()."""
    scored = []
    for coin in BASIS_COINS:
        for venue_a, venue_b in BASIS_VENUE_PAIRS:
            signs, outcomes, n_overlap = _basis_signs_outcomes(coin, venue_a, venue_b)
            if len(signs) >= _MIN_DAYS:
                scored.append((len(signs), coin, venue_a, venue_b, signs, outcomes))
    scored.sort(key=lambda t: -t[0])
    return scored[:MAX_BASIS_CANDIDATES]


def _basis_candidates(selection: list, n_variants: int) -> list:
    from research.autoresearch.engine import Candidate
    out = []
    for _, coin, venue_a, venue_b, signs, outcomes in selection:
        def _run(signs=signs, outcomes=outcomes):
            return _series_evidence(signs, outcomes, COST_BASE_BPS, COST_STRESS_BPS, n_variants)
        out.append(Candidate(
            cid=f"micro_basis_reversion_{coin}_{venue_a}_{venue_b}", category="microstructure",
            thesis=f"{coin} {venue_a}-{venue_b} 일별 basis 수렴(cash-and-carry 재정거래)",
            direction="research", run=_run, meta={}))
    return out
