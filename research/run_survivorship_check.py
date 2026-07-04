"""US 내부자 매수 drift — 생존자편향 보정 검증.

OpenInsider 이벤트 중:
- yfinance 로드 성공 = 현존 종목 (surviving)
- yfinance 로드 실패 = 상장폐지 가능성 (delisted candidate)

Stooq.com 대안 로드로 상장폐지 종목 수익 추정 후 편향 크기 측정.
Stooq URL: https://stooq.com/q/d/l/?s=TICKER.US&d1=YYYYMMDD&d2=YYYYMMDD&i=d

CLI: PYTHONPATH=. python3 research/run_survivorship_check.py
"""
from __future__ import annotations

import bisect
import io
import statistics as _st
import time
from datetime import date

HOLD_DAYS = 20
COST_BPS = 5


def _price_stooq(ticker: str, start: str = "20200101") -> dict | None:
    """Stooq.com CSV 다운로드 (상장폐지 포함). 실패 시 None."""
    import requests
    end = date.today().strftime("%Y%m%d")
    url = "https://stooq.com/q/d/l/"
    params = {"s": f"{ticker}.US", "d1": start, "d2": end, "i": "d"}
    try:
        r = requests.get(url, params=params, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or "<html" in r.text[:200]:
            return None
        lines = r.text.strip().split("\n")
        if len(lines) < 3:
            return None
        dates, opens, closes = [], [], []
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 5:
                continue
            try:
                dates.append(parts[0].strip())
                opens.append(float(parts[1]))
                closes.append(float(parts[4]))
            except ValueError:
                continue
        if len(dates) < 5:
            return None
        return {"dates": dates, "open": opens, "close": closes}
    except Exception:
        return None


def _price_yfinance(ticker: str) -> dict | None:
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


def _ret(bars: dict, event_date: str) -> float | None:
    j0 = bisect.bisect_right(bars["dates"], event_date) - 1
    i = j0 + 1
    if j0 < 0 or i >= len(bars["dates"]):
        return None
    entry = bars["open"][i]
    xi = min(i + HOLD_DAYS, len(bars["dates"]) - 1)
    if entry <= 0 or xi <= i or xi < i + HOLD_DAYS:
        return None
    return (bars["close"][xi] / entry - 1) - COST_BPS / 10_000.0


def main():
    print("=" * 65)
    print("US 내부자 매수 drift — 생존자편향 보정 검증")
    print("=" * 65)

    from research.data.openinsider import load_events
    events = load_events(min_date="2022-01-01")
    tickers = list({e["ticker"] for e in events})
    print(f"고유 종목: {len(tickers)}개  이벤트: {len(events)}건")

    # 1단계: yfinance 로드 시도 (현존 종목)
    print("\n[1단계] yfinance 로드...")
    yf_cache: dict[str, dict | None] = {}
    for t in tickers:
        yf_cache[t] = _price_yfinance(t)
    surviving = [t for t in tickers if yf_cache[t] is not None]
    delisted_candidates = [t for t in tickers if yf_cache[t] is None]
    print(f"  현존(yfinance 성공): {len(surviving)}개")
    print(f"  상장폐지 후보(yfinance 실패): {len(delisted_candidates)}개")

    # 2단계: 상장폐지 후보 → Stooq 시도
    print(f"\n[2단계] Stooq로 상장폐지 후보 {len(delisted_candidates)}개 재시도...")
    stooq_cache: dict[str, dict | None] = {}
    for i, t in enumerate(delisted_candidates):
        stooq_cache[t] = _price_stooq(t)
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(delisted_candidates)} 처리")
        time.sleep(0.2)
    stooq_found = [t for t in delisted_candidates if stooq_cache[t] is not None]
    stooq_not_found = [t for t in delisted_candidates if stooq_cache[t] is None]
    print(f"  Stooq 성공: {len(stooq_found)}개  미발견: {len(stooq_not_found)}개")

    # 3단계: 수익 계산 — 현존 vs Stooq 추가
    rets_surviving: list[float] = []
    for e in events:
        bars = yf_cache.get(e["ticker"])
        if bars is None:
            continue
        r = _ret(bars, e["disclosure_date"])
        if r is not None:
            rets_surviving.append(r)

    rets_stooq_extra: list[float] = []
    for e in events:
        if e["ticker"] not in stooq_found:
            continue
        bars = stooq_cache[e["ticker"]]
        r = _ret(bars, e["disclosure_date"])
        if r is not None:
            rets_stooq_extra.append(r)

    rets_combined = rets_surviving + rets_stooq_extra

    print(f"\n[결과]")
    if rets_surviving:
        print(f"  surviving-only   : n={len(rets_surviving):4d}  "
              f"median={_st.median(rets_surviving):+.4f} ({_st.median(rets_surviving)*100:+.2f}%)  "
              f"win={sum(1 for x in rets_surviving if x>0)/len(rets_surviving):.3f}")
    if rets_stooq_extra:
        print(f"  Stooq 추가분     : n={len(rets_stooq_extra):4d}  "
              f"median={_st.median(rets_stooq_extra):+.4f} ({_st.median(rets_stooq_extra)*100:+.2f}%)  "
              f"win={sum(1 for x in rets_stooq_extra if x>0)/len(rets_stooq_extra):.3f}")
    if rets_combined:
        print(f"  combined         : n={len(rets_combined):4d}  "
              f"median={_st.median(rets_combined):+.4f} ({_st.median(rets_combined)*100:+.2f}%)  "
              f"win={sum(1 for x in rets_combined if x>0)/len(rets_combined):.3f}")

    # 편향 크기
    if rets_surviving and rets_combined:
        bias = _st.median(rets_surviving) - _st.median(rets_combined)
        print(f"\n  생존자편향 크기  : {bias*100:+.2f}% (surviving - combined)")
        pct_cover = len(rets_combined) / max(len(rets_surviving) + len(rets_stooq_extra), 1)
        print(f"  여전히 미발견    : {len(stooq_not_found)}개 → 잔존 편향 있을 수 있음")

    print("\n[판정]")
    if rets_stooq_extra:
        stooq_med = _st.median(rets_stooq_extra)
        surv_med = _st.median(rets_surviving) if rets_surviving else 0
        if stooq_med < surv_med - 0.005:
            print("  상장폐지 종목 수익 < 현존 종목 → 생존자편향 확인됨")
            print("  surviving-only 결과는 실제보다 과대평가")
        else:
            print("  Stooq 추가분 수익 ≒ 현존 종목 → 편향 미미 or Stooq 커버 부족")
    else:
        print("  Stooq 데이터 없음 — 편향 측정 불가 (네트워크/커버리지 문제)")


if __name__ == "__main__":
    main()
