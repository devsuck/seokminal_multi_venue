"""US 내부자 오픈마켓 매수 drift 검증 (OpenInsider Form 4 P코드).

검증 단계:
1. 전체 샘플 기초 통계 (n, median, win_rate)
2. 랜덤 베이스라인 부트스트랩 p-value
3. 워크포워드 (2022-2024 IS / 2025-2026 OOS)
4. 비용 스트레스 (50bps)
5. BH-FDR (단일가설)
6. 생존자편향 주의 라벨

사전등록: US_INSIDER_BUY_DRIFT_V1
- 가설: 임원/이사 오픈마켓 매수 공시일 기준 D+1 진입 20일 median > 0
- BH-FDR α=0.1 (단일가설이므로 raw p < 0.1 = 통과)
- WF 일관성 ≥ 0.6 필요
CLI: PYTHONPATH=. python3 research/run_us_insider_drift.py
"""
from __future__ import annotations

import random as _random
import statistics as _st
import bisect

HOLD_DAYS = 20
COST_BASE_BPS = 5
COST_STRESS_BPS = 50
N_BOOT = 1000
SEED = 42
WF_SPLIT = "2026-01-01"   # IS: 2025-10~2025-12  OOS: 2026~
# OpenInsider cnt=5000 → 실제 커버리지 ~9개월(2025-10~현재)
MIN_N_WF = 30


def _price_series(ticker: str) -> dict | None:
    try:
        import yfinance as yf
        df = yf.download(ticker, start="2020-01-01", auto_adjust=True, progress=False)
        if df.empty or len(df) < 20:
            return None
        cols = df.columns
        if hasattr(cols, "levels"):
            opens = df[("Open", ticker)].values
            closes = df[("Close", ticker)].values
        else:
            opens = df["Open"].values
            closes = df["Close"].values
        return {
            "dates": [d.strftime("%Y-%m-%d") for d in df.index],
            "open": [float(x) for x in opens],
            "close": [float(x) for x in closes],
        }
    except Exception:
        return None


def _ret(bars: dict, event_date: str, cost_bps: float) -> float | None:
    j0 = bisect.bisect_right(bars["dates"], event_date) - 1
    i = j0 + 1
    if j0 < 0 or i >= len(bars["dates"]):
        return None
    entry = bars["open"][i]
    xi = min(i + HOLD_DAYS, len(bars["dates"]) - 1)
    if entry <= 0 or xi <= i or xi < i + HOLD_DAYS:
        return None
    return (bars["close"][xi] / entry - 1) - cost_bps / 10_000.0


def _sign_test_p(rets: list[float]) -> float:
    """사인 테스트: H0: P(ret > 0) = 0.5. 이항 단측 p-value."""
    import math
    n = len(rets)
    k = sum(1 for r in rets if r > 0)
    # P(X >= k | X~Bin(n, 0.5)) — 정규근사
    mu = n * 0.5
    sigma = (n * 0.5 * 0.5) ** 0.5
    z = (k - mu) / sigma
    # Φ(-z) 근사 (표준정규 누적)
    return _norm_sf(z)


def _norm_sf(z: float) -> float:
    """P(Z > z) 표준정규 생존함수 근사."""
    import math
    return 0.5 * math.erfc(z / math.sqrt(2))


def _random_baseline_p(
    rets_event: list[float],
    bars_pool: list[dict],
    n_boot: int = N_BOOT,
) -> float:
    """랜덤 동빈도 베이스라인 대비 p-value.
    같은 n건을 같은 종목 풀에서 랜덤 진입 → median 분포 → 관측 median 퍼센타일."""
    rng = _random.Random(SEED)
    n = len(rets_event)
    obs = _st.median(rets_event)

    # 가능한 (bars, i) 풀 — 20일 완결 가능한 것만
    pool = []
    for bars in bars_pool:
        for i in range(1, len(bars["dates"]) - HOLD_DAYS - 1):
            entry = bars["open"][i]
            xi = i + HOLD_DAYS
            if entry > 0 and xi < len(bars["dates"]):
                r = (bars["close"][xi] / entry - 1) - COST_BASE_BPS / 10_000.0
                pool.append(r)
    if not pool:
        return 0.5

    count_above = 0
    for _ in range(n_boot):
        sample_med = _st.median(rng.choices(pool, k=n))
        if sample_med >= obs:
            count_above += 1
    return count_above / n_boot


def main():
    print("=" * 70)
    print("US 내부자 오픈마켓 매수 drift — 사전등록 US_INSIDER_BUY_DRIFT_V1")
    print("=" * 70)

    from research.data.openinsider import load_events
    events = load_events(min_date="2022-01-01")
    print(f"이벤트 로드: {len(events)}건  공시일 기준 D+1 진입 {HOLD_DAYS}일 보유")

    # 주가 시리즈 캐시
    print("주가 다운로드 중...", flush=True)
    _cache: dict[str, dict | None] = {}
    for e in events:
        t = e["ticker"]
        if t not in _cache:
            _cache[t] = _price_series(t)

    # 수익 계산
    rows_base: list[tuple[str, float]] = []   # (date, ret) base cost
    rows_stress: list[tuple[str, float]] = [] # stress cost
    for e in events:
        bars = _cache.get(e["ticker"])
        if bars is None:
            continue
        r_base = _ret(bars, e["disclosure_date"], COST_BASE_BPS)
        r_stress = _ret(bars, e["disclosure_date"], COST_STRESS_BPS)
        if r_base is not None:
            rows_base.append((e["disclosure_date"], r_base))
        if r_stress is not None:
            rows_stress.append((e["disclosure_date"], r_stress))

    rets_base = [r for _, r in rows_base]
    rets_stress = [r for _, r in rows_stress]

    print(f"\n[기초 통계 — base {COST_BASE_BPS}bps]")
    print(f"  n           = {len(rets_base)}")
    print(f"  median      = {_st.median(rets_base):+.4f} ({_st.median(rets_base)*100:+.2f}%)")
    print(f"  mean        = {_st.mean(rets_base):+.4f} (팻테일 주의)")
    print(f"  win_rate    = {sum(1 for x in rets_base if x > 0)/len(rets_base):.3f}")
    print(f"  stress {COST_STRESS_BPS}bps: median = {_st.median(rets_stress):+.4f}")

    # 랜덤 베이스라인 p-value
    print(f"\n[랜덤 베이스라인 부트스트랩 p-value] n_boot={N_BOOT}...", flush=True)
    bars_pool = [b for b in _cache.values() if b is not None]
    p_random = _random_baseline_p(rets_base, bars_pool)
    print(f"  p(random_baseline >= obs_median) = {p_random:.4f}")

    # 사인 테스트 (이항)
    p_sign = _sign_test_p(rets_base)
    print(f"\n[사인 테스트] H0: win_rate = 0.5")
    print(f"  win_rate = {sum(1 for x in rets_base if x>0)/len(rets_base):.4f}  p(단측) = {p_sign:.6f}")

    # 워크포워드
    print(f"\n[워크포워드] IS: <{WF_SPLIT}  OOS: >={WF_SPLIT}")
    rows_is = [r for d, r in rows_base if d < WF_SPLIT]
    rows_oos = [r for d, r in rows_base if d >= WF_SPLIT]
    for label, rets in [("IS ", rows_is), ("OOS", rows_oos)]:
        if len(rets) >= MIN_N_WF:
            print(f"  {label}: n={len(rets):4d}  median={_st.median(rets):+.4f}  win={sum(1 for x in rets if x>0)/len(rets):.3f}")
        else:
            print(f"  {label}: n={len(rets):4d}  UNDERPOWERED (< {MIN_N_WF})")

    oos_positive = len(rows_oos) > MIN_N_WF and _st.median(rows_oos) > 0
    is_positive = len(rows_is) > MIN_N_WF and _st.median(rows_is) > 0
    wf_consistent = is_positive and oos_positive
    print(f"  WF 일관성: IS {'✓' if is_positive else '✗'} OOS {'✓' if oos_positive else '✗'} → {'PASS' if wf_consistent else 'FAIL'}")

    # BH-FDR (단일 가설) — 랜덤 베이스라인 p 우선, sign test 보조
    print(f"\n[BH-FDR] α=0.1 (단일 가설)")
    p_bh = p_random if p_random > 0 else p_sign
    bh_pass = p_bh < 0.1
    print(f"  p_random={p_random:.4f}  p_sign={p_sign:.6f}  BH통과={'YES' if bh_pass else 'NO'}")

    # 생존자편향 경고
    print(f"\n[생존자편향 주의]")
    print(f"  yfinance = 현존 종목 위주. 상장폐지 종목 누락.")
    print(f"  내부자 매수 후 상장폐지 = 대부분 손실 → 실제 edge 과대평가 가능.")
    print(f"  PIT-clean 검증: CRSP 또는 Compustat 필요 (미구현)")

    # 최종 판정
    print(f"\n{'='*70}")
    verdict = "PASS" if (bh_pass and wf_consistent) else ("PROMISING" if bh_pass else "REJECT")
    print(f"판정: {verdict}")
    if verdict == "PASS":
        print("  → BH-FDR 통과 + WF 일관성. 단, 생존자편향 보정 전 live 불가.")
    elif verdict == "PROMISING":
        print("  → BH-FDR 통과했으나 WF 불일관 or OOS 부족. 관찰 지속.")
    else:
        print("  → BH-FDR 미통과. 엣지 없음.")
    print("=" * 70)

    return {
        "n": len(rets_base), "median": _st.median(rets_base),
        "p_random": p_random, "p_sign": p_sign,
        "bh_pass": bh_pass, "wf_consistent": wf_consistent,
        "verdict": verdict,
    }


if __name__ == "__main__":
    main()
