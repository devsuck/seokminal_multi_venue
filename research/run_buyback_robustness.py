"""KR 자사주 buyback — paper 전 로버스트니스 분해 (진단, 튜닝 아님).

#1 timestamp 진입 가능성  #2 진입 타이밍 비교  #3 공시유형 분해
#5 집중도(issuer/시총/시장) 분해. 원본 config 동결, 분해로 파라미터 안 바꿈.
실행: PYTHONPATH=. python3 research/run_buyback_robustness.py
"""
from __future__ import annotations

import bisect
import random as _random
import statistics as _st

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events
from research.validation.baselines import empirical_p_value
from research.paper import buyback_config as CFG
import glob, os

HOLD = CFG.HOLD_DAYS
RT = CFG.COST_BASE_BPS
N_RUNS = 300
SEED = 42


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _entry_idx(bars, event_date, mode):
    j0 = bisect.bisect_right(bars["dates"], event_date) - 1  # 공시일(≤)
    if j0 < 0:
        return None
    if mode == "ann_close":   # 공시일 종가 (lookahead 가능성)
        return ("close", j0)
    if mode == "next_open":   # 다음날 시가 (frozen)
        return ("open", j0 + 1)
    if mode == "next_close":  # 다음날 종가
        return ("close", j0 + 1)
    if mode == "delayed_open":  # +1일 지연 시가
        return ("open", j0 + 2)
    return None


def _ret(bars, event_date, mode, rt=RT):
    ei = _entry_idx(bars, event_date, mode)
    if ei is None:
        return None
    fld, i = ei
    if i >= len(bars["dates"]):
        return None
    entry = bars[fld][i]
    xi = min(i + HOLD, len(bars["dates"]) - 1)
    if entry <= 0 or xi <= i:
        return None
    return (bars["close"][xi] / entry - 1) - rt / 10_000.0


def _pool_net(series, n, mode, rng):
    """random: 같은 진입방식·보유·비용, 랜덤 종목·날짜."""
    codes = list(series.keys())
    s = 0.0
    for _ in range(n):
        b = series[rng.choice(codes)]
        i = rng.randrange(20, max(21, len(b["dates"]) - HOLD - 2))
        fld = "close" if "close" in mode else "open"
        entry = b[fld][i]; xi = min(i + HOLD, len(b["dates"]) - 1)
        s += ((b["close"][xi] / entry - 1) - RT / 10_000.0) if entry > 0 else 0.0
    return s / n


def main():
    print("=" * 74 + "\nKR BUYBACK 로버스트니스 분해 (진단, config 동결)\n" + "=" * 74)
    series = _series()
    bb = load_events("buyback")
    matched = [e for e in bb if e["stock_code"] in series]
    print(f"KRX 시계열 {len(series)} | buyback 매칭 {len(matched)}/{len(bb)}")

    print("\n#1 timestamp: OpenDART rcept_dt=날짜만(시각 없음) → 공시 다음날 진입이 현실적. announcement-close는 lookahead 위험")

    print("\n#2 진입 타이밍 비교 (net, base cost):")
    rng = _random.Random(SEED)
    for mode in ["ann_close", "next_open", "next_close", "delayed_open"]:
        rets = [r for e in matched if (r := _ret(series[e["stock_code"]], e["date"], mode)) is not None]
        if not rets:
            continue
        net = _st.mean(rets)
        randnet = [_pool_net(series, len(rets), mode, rng) for _ in range(N_RUNS)]
        pv = empirical_p_value(net, randnet)
        tag = " ← frozen" if mode == "next_open" else (" (lookahead 위험)" if mode == "ann_close" else "")
        print(f"  {mode:13} n={len(rets)} net={net:+.4f} vs random pct={pv['percentile']} p={pv['p_value']}{tag}")

    print("\n#3 공시유형 분해 (net, next_open base):")
    for label, kw in [("직접취득(결정)", None), ("신탁계약", "신탁")]:
        if kw:
            sub = [e for e in matched if "신탁" in e.get("report_nm", "")]
        else:
            sub = [e for e in matched if "신탁" not in e.get("report_nm", "")]
        rets = [r for e in sub if (r := _ret(series[e["stock_code"]], e["date"], "next_open")) is not None]
        if rets:
            print(f"  {label:12} n={len(rets)} net={_st.mean(rets):+.4f} 승률={sum(1 for x in rets if x>0)/len(rets):.3f}")

    print("\n#5 집중도 분해:")
    # 시장(KOSPI/KOSDAQ)
    for mkt in ["KOSPI", "KOSDAQ"]:
        rets = [r for e in matched if series[e["stock_code"]].get("market") == mkt
                and (r := _ret(series[e["stock_code"]], e["date"], "next_open")) is not None]
        if rets:
            print(f"  시장 {mkt:7} n={len(rets)} net={_st.mean(rets):+.4f}")
    # issuer 집중
    from collections import Counter
    cnt = Counter(e["stock_code"] for e in matched)
    top = cnt.most_common(5)
    tot = sum(cnt.values())
    print(f"  issuer 고유 {len(cnt)}개 | 상위5 비중 {sum(c for _,c in top)/tot*100:.1f}% | 최다 {top[0][1]}건")
    # 시총 버킷 (이벤트 시점 근사=최근 marcap)
    def mc_bucket(mc):
        return "대형(1조+)" if mc >= 1e12 else "중형(1천억+)" if mc >= 1e11 else "소형"
    buckets = {}
    for e in matched:
        b = series[e["stock_code"]]
        mc = b["marcap"][-1] if b["marcap"] else 0
        r = _ret(b, e["date"], "next_open")
        if r is not None:
            buckets.setdefault(mc_bucket(mc), []).append(r)
    for bk, rs in sorted(buckets.items()):
        print(f"  시총 {bk:10} n={len(rs)} net={_st.mean(rs):+.4f}")

    print("\n#4 buyback size/시총, size/ADV: OpenDART list.json에 취득금액 없음 → 상세보고서(tsstkAqDcsn) 파싱 필요 = 다음 데이터작업")
    print("\n원본 스펙 동결. 위 분해로 파라미터 튜닝 금지.")


if __name__ == "__main__":
    main()
