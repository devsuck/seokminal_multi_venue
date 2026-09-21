"""KR buyback v1 데이터 감사 — 미조정 corp action(액면분할/감자 등) 탐지 후 오염 이벤트 제외 net 재계산.
진단용, v1 필터 영구 수정 아님(원인 규명 + 정제된 net 산출).

탐지 시그니처: 종가 1일 변동이 극단적(가격 2배↑ or 절반↓)인데 marcap 변동은 정상 범위 →
split-adjust 안 된 corp action으로 간주.
실행: PYTHONPATH=. python3 research/run_buyback_split_audit.py
"""
from __future__ import annotations

import bisect
import statistics as _st
import glob, os

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events
from research.validation.baselines import empirical_p_value
from research.paper import buyback_config as CFG

HOLD = CFG.HOLD_DAYS
RT = CFG.COST_BASE_BPS
N_RUNS = 500
SEED = 42

PRICE_JUMP = 2.0   # 종가 전일비 2배 이상 또는 1/2 이하
MARCAP_STABLE = (0.7, 1.4)  # marcap 전일비 정상 변동 범위


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _find_split_days(series: dict) -> dict:
    """{stock_code: set(flagged_dates)} — split-signature 있는 날짜."""
    flagged: dict = {}
    for code, b in series.items():
        closes, marcaps, dates = b["close"], b["marcap"], b["dates"]
        bad = set()
        for i in range(1, len(dates)):
            c0, c1 = closes[i - 1], closes[i]
            m0, m1 = marcaps[i - 1], marcaps[i]
            if c0 <= 0 or c1 <= 0 or m0 <= 0 or m1 <= 0:
                continue
            price_ratio = c1 / c0
            marcap_ratio = m1 / m0
            jumped = price_ratio >= PRICE_JUMP or price_ratio <= 1 / PRICE_JUMP
            marcap_ok = MARCAP_STABLE[0] <= marcap_ratio <= MARCAP_STABLE[1]
            if jumped and marcap_ok:
                bad.add(dates[i])
        if bad:
            flagged[code] = bad
    return flagged


def _fwd(bars, event_date):
    j = bisect.bisect_right(bars["dates"], event_date)
    if j >= len(bars["dates"]) or bars["open"][j] <= 0:
        return None
    entry = bars["open"][j]
    xi = min(j + HOLD, len(bars["dates"]) - 1)
    if xi <= j:
        return None
    return j, xi, (bars["close"][xi] / entry - 1) - RT / 10_000.0


def _random_pool(series):
    pool = []
    for b in series.values():
        for j in range(len(b["dates"]) - HOLD - 1):
            pool.append((b, j))
    return pool


def main():
    print("=" * 74 + "\nKR BUYBACK 데이터 감사 — 미조정 corp action 스캔\n" + "=" * 74)
    series = _series()
    print(f"KRX 시계열 {len(series)}종목 스캔 중...")
    flagged = _find_split_days(series)
    total_flags = sum(len(v) for v in flagged.values())
    print(f"split-시그니처 종목 {len(flagged)}개, 총 {total_flags}건")

    events = load_events("buyback")
    clean, contaminated = [], []
    for e in events:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        r = _fwd(b, e["date"])
        if r is None:
            continue
        j, xi, ret = r
        window_dates = set(b["dates"][j:xi + 1])
        bad_dates = flagged.get(e["stock_code"], set())
        if window_dates & bad_dates:
            contaminated.append((e["stock_code"], b.get("name", ""), e["date"], ret))
        else:
            clean.append((e["date"], ret))

    print(f"\n전체 매칭 {len(clean) + len(contaminated)}건 중 오염(보유기간 중 split-시그니처 낌) {len(contaminated)}건")
    if contaminated:
        contaminated.sort(key=lambda x: x[3])
        print("오염 이벤트 (return 낮은 순 상위 15):")
        for code, name, date, ret in contaminated[:15]:
            print(f"  {ret*100:+7.2f}%  {code:<8}{name:<14}{date}")

    # 정제 net (오염 이벤트 제외)
    rets = [r for _, r in clean]
    net_clean = _st.mean(rets)
    print(f"\n정제 후 v1 net (base_20bps): n={len(clean)} net={net_clean:+.4f} "
          f"(오염 포함 전체 n={len(clean)+len(contaminated)})")

    pool = _random_pool(series)
    rng = __import__("random").Random(SEED)
    rmeans = []
    for _ in range(N_RUNS):
        s = 0.0
        for _ in range(len(clean)):
            b, j = pool[rng.randrange(len(pool))]
            e0 = b["open"][j + 1]; xi = min(j + 1 + HOLD, len(b["dates"]) - 1)
            s += ((b["close"][xi] / e0 - 1) - RT / 10_000.0) if e0 > 0 else 0.0
        rmeans.append(s / len(clean))
    pv = empirical_p_value(net_clean, rmeans)
    print(f"vs random pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f})")

    print(f"\n비교: 오염포함 v1 net ≈ +0.0207 (n=1978, 이전 런) vs 정제 net={net_clean:+.4f} (n={len(clean)})")


if __name__ == "__main__":
    main()
