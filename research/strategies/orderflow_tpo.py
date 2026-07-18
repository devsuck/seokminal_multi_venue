"""가설: TPO(Time Price Opportunity/Market Profile) Value Area 이탈 페이드.

`/orderflow` 대시보드 `lib/orderflow-data.ts`의 `computeTpoProfile`/`computeValueArea`를
그대로 이식 — 30분 구간마다 어느 가격에 체결이 닿았는지(letters)를 기록해 구간수(터치
횟수)를 볼륨 대용으로 쓰는 표준 Market Profile 방식. POC(최다 터치 가격)에서 좌우로
탐욕 확장해 전체 터치의 70%(VALUE_AREA_PCT)를 덮는 [VAL, VAH] 구간을 얻는다.

가설: 종가가 VAH 위=SELL(페이드), VAL 아래=BUY(페이드) — day-VWAP 밴드 페이드
(`orderflow_tape_vwap.py`)와 동일한 "박스 밖 이탈은 평균회귀" 직관을 다른 지표축
(체결가격분포 vs VWAP표준편차)으로 재현한 것. 사전 직관일 뿐 검증된 적 없음.

이전에 "depth 데이터 부족으로 TPO 백테스트 불가"라고 판단했던 건 틀렸다 — TPO는
체결틱만 있으면 계산 가능(체결가 분포 문제, 잔량/호가창 무관). footprint_delta
(가격×60s버킷, `OrderflowAggregator.on_trade`)만 있으면 되고 이건 8일치 이미 있음.

⚠️ DORMANT 모듈 — 검증된 알파 아님. TPO_PERIOD_SEC=1800(프론트와 동일, CBOT 관례
30분), VALUE_AREA_PCT=0.7(프론트와 동일)은 프론트 값 그대로 가져온 것이라 튜닝 여지가
없다. MIN_WARMUP_PERIODS=4(하루 중 최소 2시간 경과, 구간 4개는 모여야 POC/VA가
의미 있다고 사전 판단)만 이 파일 작성 시점에 새로 정한 값 — 결과 보고 재조정 안 함.
day(UTC) 앵커, 프론트의 `anchor = min(bucketTs)`와 동일하게 그날 첫 체결 버킷을
0번 구간 시작점으로 잡는다(고정 자정 앵커가 아님, 원본 로직 그대로).
"""
from __future__ import annotations

import datetime as dt
import json

from research.reports.alpha_report import build_report
from research.validation.baselines import empirical_p_value, random_same_frequency
from research.validation.cost_model import hl_effective_cost_bps
from research.validation.engine import simulate_long_short
from research.validation.metrics import trade_metrics

TPO_PERIOD_SEC = 1800  # lib/orderflow-data.ts TPO_PERIOD_SEC과 동일 — 고정, 튜닝 안 함
VALUE_AREA_PCT = 0.7  # lib/orderflow-data.ts VALUE_AREA_PCT와 동일 — 고정, 튜닝 안 함
MIN_WARMUP_PERIODS = 4  # 사전 판단(2시간). absorption.py MIN_WARMUP_SAMPLES와 동일 원칙

TARGET_NOTIONAL_USD = 1000.0

DEFAULTS: dict = {}


def _day_key(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).strftime("%Y-%m-%d")


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2.0 if n % 2 == 0 else s[mid]


def _value_area(levels: list[tuple[float, int]], value_area_pct: float) -> dict | None:
    """levels: (price, periods_touched) 오름차순 정렬. 프론트 computeValueArea 이식 —
    POC=최다터치(동률시 오름차순 스캔에서 먼저 만난, 즉 최저가), 탐욕확장 시 동률이면
    위쪽(hi+1) 우선(`above >= below`)."""
    if not levels:
        return None
    total = sum(t for _, t in levels)
    if total <= 0:
        return None
    poc_idx = 0
    best = -1
    for i, (_, touched) in enumerate(levels):
        if touched > best:
            best = touched
            poc_idx = i
    target = total * value_area_pct
    lo = hi = poc_idx
    covered = levels[poc_idx][1]
    while covered < target:
        below = levels[lo - 1][1] if lo - 1 >= 0 else -1
        above = levels[hi + 1][1] if hi + 1 < len(levels) else -1
        if below < 0 and above < 0:
            break
        if above >= below:
            hi += 1
            covered += levels[hi][1]
        else:
            lo -= 1
            covered += levels[lo][1]
    return {"poc": levels[poc_idx][0], "val": levels[lo][0], "vah": levels[hi][0]}


def build_signals(deltas: list[dict], period_sec: int = TPO_PERIOD_SEC,
                   value_area_pct: float = VALUE_AREA_PCT,
                   min_warmup_periods: int = MIN_WARMUP_PERIODS) -> dict:
    """footprint_delta(가격×60s버킷, `OrderflowAggregator.on_trade` 결과) 순서대로 훑으며
    causal(그 시점까지 데이터만 사용) TPO Value Area를 굴리고 봉마감 페이드 신호를 낸다."""
    order: list[float] = []
    seen_buckets: set[float] = set()
    last_price: dict[float, float] = {}

    cur_day: str | None = None
    anchor: float | None = None
    periods_by_price: dict[float, set[int]] = {}
    periods_seen: set[int] = set()

    bucket_va: dict[float, dict | None] = {}
    bucket_warm: dict[float, bool] = {}

    for d in deltas:
        if d.get("type") != "footprint_delta":
            continue
        b = d["bucket_ts"]
        price = d["price"]
        if b not in seen_buckets:
            seen_buckets.add(b)
            order.append(b)
        last_price[b] = price

        day = _day_key(b)
        if day != cur_day:
            cur_day = day
            anchor = b
            periods_by_price = {}
            periods_seen = set()

        period_idx = int((b - anchor) // period_sec)
        periods_by_price.setdefault(price, set()).add(period_idx)
        periods_seen.add(period_idx)

        levels = sorted(
            ((p, len(periods)) for p, periods in periods_by_price.items()),
            key=lambda x: x[0],
        )
        bucket_va[b] = _value_area(levels, value_area_pct)
        bucket_warm[b] = len(periods_seen) >= min_warmup_periods

    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, b in enumerate(order):
        close = last_price[b]
        closes.append(close)
        sig = "HOLD"
        va = bucket_va.get(b)
        if bucket_warm.get(b) and va is not None:
            eligible.append(i)
            if close > va["vah"]:
                sig = "SELL"
            elif close < va["val"]:
                sig = "BUY"
        signals.append(sig)

    return {"closes": closes, "signals": signals, "eligible": eligible}


def _windowed_consistency(trades: list[dict], n_bars: int, n_windows: int = 5) -> dict:
    """orderflow_tape_vwap.py와 동일 대체 지표 — day-anchor causal 누적이라 구간별
    signal_fn 재계산 방식(walk_forward.py)과 안 맞아 진입 인덱스 기준 5구간 부호만 본다."""
    if n_bars < n_windows * 5 or not trades:
        return {"n_windows": 0, "consistency": None, "note": "표본 부족 또는 거래 없음"}
    wsize = n_bars // n_windows
    window_pnls = [0.0] * n_windows
    for t in trades:
        w = min(t["entry_idx"] // wsize, n_windows - 1)
        window_pnls[w] += t["pnl"]
    positive = sum(1 for p in window_pnls if p > 0)
    return {
        "n_windows": n_windows,
        "window_pnls": [round(p, 6) for p in window_pnls],
        "consistency": round(positive / n_windows, 4),
        "positive_windows": positive,
    }


def run_hypothesis(
    symbol: str,
    deltas: list[dict],
    params: dict | None = None,
    n_runs: int = 500,
    seed: int = 42,
    write_report: bool = True,
    keep_random: bool = False,
) -> dict:
    p = {**DEFAULTS, **(params or {})}
    if not deltas:
        return _blocked(symbol, "no footprint delta data", write_report)

    data = build_signals(deltas)
    closes, signals, eligible = data["closes"], data["signals"], data["eligible"]
    if len(closes) < 10:
        return _blocked(symbol, f"버킷 {len(closes)}개뿐 — 최소 표본 미달", write_report)

    trade_size = p.get("trade_size") or TARGET_NOTIONAL_USD / _median(closes)
    cost_bps = hl_effective_cost_bps("major", taker=True)
    trades = simulate_long_short(closes, signals, trade_size, cost_bps)
    strat = trade_metrics(trades)

    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [1]
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=trade_size, cost_bps=cost_bps,
        eligible_indices=eligible, n_runs=n_runs, seed=seed,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)
    wf = _windowed_consistency(trades, len(closes))

    result = {
        "symbol": symbol, "blocked": False,
        "strategy": strat, "random": pval, "walk_forward": wf,
        "n_bars": len(closes), "eligible_count": len(eligible),
    }
    if keep_random:
        result["random_stats"] = rnd
    if write_report:
        rep = build_report(
            name=f"orderflow_tpo_{symbol}",
            hypothesis=(
                f"TPO Value Area(period={TPO_PERIOD_SEC}s, VA%={VALUE_AREA_PCT}) 이탈 페이드: "
                "종가>VAH=숏, 종가<VAL=롱 (신규 가설, 프론트 lib/orderflow-data.ts "
                "computeTpoProfile/computeValueArea 이식)"
            ),
            universe=[symbol], timeframe="1m",
            cost={"cost_bps": cost_bps, "slippage_bps": 0, "spread_bps": 0, "effective_bps": cost_bps},
            strategy=strat, random_pval=pval,
            naive={"total_pnl": None, "note": "VA 페이드 신호는 buy&hold 비교 부적합 → random 분포가 주판정"},
            walk_forward_result={"summary": wf},
            is_harness_dryrun=False,
            extra={
                "n_bars": len(closes), "eligible_count": len(eligible),
                "note": "8일치 틱 데이터(2026-07-10~17), day(UTC) 앵커로 매일 프로파일 리셋.",
            },
        )
        result["report"] = rep
    return result


def _blocked(symbol: str, msg: str, write_report: bool) -> dict:
    res = {"symbol": symbol, "blocked": True, "reason": msg,
           "verdict": "BLOCKED: " + msg}
    if write_report:
        import os
        from research.reports.alpha_report import REPORT_DIR
        os.makedirs(REPORT_DIR, exist_ok=True)
        base = os.path.join(REPORT_DIR, f"orderflow_tpo_{symbol}")
        with open(base + ".json", "w") as f:
            json.dump(res, f, indent=2)
        with open(base + ".md", "w") as f:
            f.write(f"# Orderflow TPO Value Area Fade — {symbol}\n\n**BLOCKED.** {msg}\n")
    return res
