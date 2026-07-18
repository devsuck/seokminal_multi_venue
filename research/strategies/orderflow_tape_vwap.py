"""가설: 체결속도 버스트 + day-VWAP ±1σ 밴드 이탈 페이드(reversion).

`/orderflow` 대시보드에 이번에 새로 얹은 두 라이브 지표(체결속도 패널, VWAP 밴드)를
조합한 신규 가설 — 각자는 표시만 하고 매매판정은 안 하던 두 신호를 처음으로 결합.
버스트(rolling median 대비 급등) 중에 가격이 VWAP 밴드 밖까지 밀려나 있으면 그 극단을
페이드(반대매매): 밴드 위 버스트=SELL, 밴드 아래 버스트=BUY. 버스트가 "체결 몰림=단기
소진 신호"라는 직관(대량체결 가설과 유사한 climax 논리)과 밴드 이탈=평균회귀 소지를
결합한 것 — 사전 직관일 뿐 검증된 적 없음.

⚠️ DORMANT 모듈 — 검증된 알파 아님. 임계값(TAPE_BURST_MULTIPLIER=2.5,
TAPE_BURST_ROLLING_BARS=60, VWAP_BAND_SIGMA=1.0)은 이 파일 작성 시점에 한 번 정하고
결과 보고 재조정하지 않는다(데이터 스누핑 방지 — absorption.py/스푸핑 휴리스틱과 동일 원칙).

체결속도는 `orderflow/aggregator.py`의 `TAPE_WINDOW_SEC`(10초 슬라이딩)를 그대로
import해서 프론트/라이브 백엔드와 동일 정의를 쓴다. VWAP은 `lib/orderflow-data.ts`의
`computeVwapBands`와 같은 ±1σ 개념이지만, typical price를 봉 h/l/c 평균이 아니라 틱
price 자체로 쓴다(틱 단위라 오히려 더 정밀 — absorption.py가 이미 쓴 "프론트와 의도적
차이는 주석으로 명시" 원칙). day(UTC) 앵커만 지원, week/month는 이번 가설 스코프 밖.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import deque

from orderflow.aggregator import TAPE_WINDOW_SEC
from research.reports.alpha_report import build_report
from research.validation.baselines import empirical_p_value, random_same_frequency
from research.validation.cost_model import hl_effective_cost_bps
from research.validation.engine import simulate_long_short
from research.validation.metrics import trade_metrics

BUCKET_SEC = 60
VWAP_BAND_SIGMA = 1.0  # 프론트 computeVwapBands의 up1/dn1과 동일 폭
# 스푸핑 휴리스틱(5.0배)보다 완화된 배수 — 체결속도는 스냅샷 사이즈 아웃라이어보다
# 변동성이 작아 5배 문턱은 거의 안 뜬다(사전 판단, 결과 보고 조정 안 함).
TAPE_BURST_MULTIPLIER = 2.5
TAPE_BURST_ROLLING_BARS = 60  # 60봉(1시간 @ 60s) rolling median. 짧으면 노이즈, 길면 반응 지연
MIN_WARMUP_BARS = 20  # absorption.py MIN_WARMUP_SAMPLES와 동일 원칙

# absorption.py와 동일 이유: 코인개수 고정 시 BTC/ETH 가격스케일 차이로 노셔널 폭주 —
# 달러노셔널 고정으로 심볼 무관 공정비교.
TARGET_NOTIONAL_USD = 1000.0

DEFAULTS: dict = {}


def load_ticks(paths: list[str]) -> list[dict]:
    """여러 일자 jsonl 파일 → 시간순 정렬된 틱 리스트."""
    ticks: list[dict] = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    ticks.append(json.loads(line))
    ticks.sort(key=lambda t: t["ts"])
    return ticks


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2.0 if n % 2 == 0 else s[mid]


def _day_key(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).strftime("%Y-%m-%d")


def build_bars_and_signals(ticks: list[dict], bucket_sec: int = BUCKET_SEC) -> dict:
    """틱 → 60s bar(close) + 체결속도버스트×VWAP밴드이탈 페이드 신호(BUY/SELL/HOLD).

    체결속도(TAPE_WINDOW_SEC 슬라이딩)와 day-VWAP(causal 누적)을 틱 순서대로 굴리며
    각 봉 마감 시점 값으로 판정 — lookahead 없음. eligible = 버스트가 뜬 봉(밴드 안이라
    HOLD가 나온 경우도 포함, "판정 가능 모집단" 규칙은 absorption.py와 동일)."""
    recent_trade_ts: deque[float] = deque()

    cum_v = cum_pv = cum_pv2 = 0.0
    cur_day: str | None = None

    bar_close: dict[int, float] = {}
    bar_order: list[int] = []
    bar_vwap: dict[int, float] = {}
    bar_sd: dict[int, float] = {}
    bar_tape_speed: dict[int, float] = {}

    cur_bar: int | None = None
    for t in ticks:
        ts, price, size = t["ts"], t["price"], t["size"]

        recent_trade_ts.append(ts)
        cutoff = ts - TAPE_WINDOW_SEC
        while recent_trade_ts and recent_trade_ts[0] < cutoff:
            recent_trade_ts.popleft()
        tape_speed = len(recent_trade_ts) / TAPE_WINDOW_SEC

        day = _day_key(ts)
        if day != cur_day:
            cur_day = day
            cum_v = cum_pv = cum_pv2 = 0.0
        cum_v += size
        cum_pv += price * size
        cum_pv2 += price * price * size

        b = int(ts // bucket_sec)
        if b != cur_bar:
            cur_bar = b
            bar_order.append(b)
        bar_close[b] = price
        bar_tape_speed[b] = tape_speed  # 봉 마지막 틱 시점 값 = 그 순간 라이브 패널이 보였을 값
        if cum_v > 0:
            vwap = cum_pv / cum_v
            variance = max(0.0, cum_pv2 / cum_v - vwap * vwap)
            bar_vwap[b] = vwap
            bar_sd[b] = variance ** 0.5

    tape_hist: deque[float] = deque(maxlen=TAPE_BURST_ROLLING_BARS)
    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []

    for i, b in enumerate(bar_order):
        close = bar_close[b]
        closes.append(close)
        speed = bar_tape_speed.get(b, 0.0)
        sig = "HOLD"

        if len(tape_hist) >= MIN_WARMUP_BARS and b in bar_vwap:
            median_speed = _median(list(tape_hist))
            if median_speed > 0 and speed >= TAPE_BURST_MULTIPLIER * median_speed:
                eligible.append(i)
                vwap, sd = bar_vwap[b], bar_sd[b]
                up1, dn1 = vwap + VWAP_BAND_SIGMA * sd, vwap - VWAP_BAND_SIGMA * sd
                if close > up1:
                    sig = "SELL"  # 버스트 중 밴드 위 = 극단을 페이드
                elif close < dn1:
                    sig = "BUY"   # 버스트 중 밴드 아래 = 극단을 페이드
        tape_hist.append(speed)
        signals.append(sig)

    return {"closes": closes, "signals": signals, "eligible": eligible}


def _windowed_consistency(trades: list[dict], n_bars: int, n_windows: int = 5) -> dict:
    """walk_forward() 모듈(closes만 받아 구간별 signal_fn 재계산) 대신 쓰는 대체 지표.

    day-VWAP은 하루 전체 causal 누적이라 구간을 잘라 signal_fn을 다시 돌리면 각 구간
    시작점에서 VWAP이 부당하게 리셋돼버림 — 이미 계산된(전체 이력 기준) trades를
    진입 인덱스로 5구간에 나눠 구간별 순손익 부호만 본다. walk_forward.py의
    summary 스키마(consistency=양수 구간 비율)와 필드명 맞춤."""
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
    tick_paths: list[str],
    params: dict | None = None,
    n_runs: int = 500,
    seed: int = 42,
    write_report: bool = True,
    keep_random: bool = False,
) -> dict:
    """버스트×VWAP밴드 페이드 신호 검증 실행. 틱 데이터 없음 → BLOCKED 리포트."""
    p = {**DEFAULTS, **(params or {})}
    ticks = load_ticks(tick_paths)
    if not ticks:
        return _blocked(symbol, "no tick data — collector 확인 필요", write_report)

    data = build_bars_and_signals(ticks)
    closes, signals, eligible = data["closes"], data["signals"], data["eligible"]
    if len(closes) < 10:
        return _blocked(symbol, f"틱→버킷 변환 후 {len(closes)}봉뿐 — 최소 표본 미달", write_report)

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
        "n_bars": len(closes), "eligible_count": len(eligible), "n_ticks": len(ticks),
    }
    if keep_random:
        result["random_stats"] = rnd
    if write_report:
        rep = build_report(
            name=f"orderflow_tape_vwap_{symbol}",
            hypothesis=(
                f"체결속도 버스트(rolling median x{TAPE_BURST_MULTIPLIER}) + day-VWAP "
                f"±{VWAP_BAND_SIGMA}σ 밴드 이탈 페이드: 버스트 중 밴드 위=숏, 버스트 중 "
                "밴드 아래=롱 (신규 조합가설, 대시보드 체결속도패널+VWAP밴드 지표 재사용)"
            ),
            universe=[symbol], timeframe="1m",
            cost={"cost_bps": cost_bps, "slippage_bps": 0, "spread_bps": 0, "effective_bps": cost_bps},
            strategy=strat, random_pval=pval,
            naive={"total_pnl": None, "note": "버스트 페이드 신호는 buy&hold 비교 부적합 → random 분포가 주판정"},
            walk_forward_result={"summary": wf},
            is_harness_dryrun=False,
            extra={
                "n_bars": len(closes), "eligible_count": len(eligible), "n_ticks": len(ticks),
                "note": (
                    "8일치 틱 데이터(2026-07-10~17). walk_forward.py 모듈 미사용 — "
                    "day-VWAP가 구간 경계 넘는 causal 누적이라 구간별 signal_fn 재계산 방식과 "
                    "안 맞음, 전체 이력 기준으로 계산된 거래를 진입시점 5구간으로 나눈 "
                    "consistency로 대체(_windowed_consistency)."
                ),
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
        base = os.path.join(REPORT_DIR, f"orderflow_tape_vwap_{symbol}")
        with open(base + ".json", "w") as f:
            json.dump(res, f, indent=2)
        with open(base + ".md", "w") as f:
            f.write(f"# Orderflow Tape-Speed x VWAP Fade — {symbol}\n\n**BLOCKED.** {msg}\n")
    return res
