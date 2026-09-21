"""KR buyback 익절타이밍 진단 — 설명력용(v1 필터 수정 아님).

20일 고정보유 final return vs 보유기간 중 MFE(최대 forward return) 비교.
MFE >> final이면 "익절했으면 나았다" 가설 근거 → 익절/트레일링스탑 v2 별도 사전등록 검토.
목적별(소각/주가안정/기타)도 같이 분해 — run_buyback_size_decomp.py와 동일 join 패턴.
실행: PYTHONPATH=. python3 research/run_buyback_exit_mfe.py
"""
from __future__ import annotations

import bisect
import statistics as _st
import glob, os

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events, pull_buyback_details, save_events, pull_events
from research.paper import buyback_config as CFG

HOLD = CFG.HOLD_DAYS


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _path(bars, event_date):
    """공시 다음날 시가 진입 → 보유기간 중 매일 종가 forward return. (mfe, mfe_day, final) 반환."""
    j0 = bisect.bisect_right(bars["dates"], event_date) - 1
    i = j0 + 1
    if j0 < 0 or i >= len(bars["dates"]):
        return None
    entry = bars["open"][i]
    if entry <= 0:
        return None
    rets = []
    for k in range(1, HOLD + 1):
        xi = min(i + k, len(bars["dates"]) - 1)
        rets.append(bars["close"][xi] / entry - 1)
        if xi == len(bars["dates"]) - 1:
            break
    if not rets:
        return None
    mfe = max(rets)
    mfe_day = rets.index(mfe) + 1
    return mfe, mfe_day, rets[-1]


def _report(label, rows):
    if len(rows) < 20:
        print(f"  {label}: 표본 부족({len(rows)})"); return
    mfes = [r[0] for r in rows]; days = [r[1] for r in rows]; finals = [r[2] for r in rows]
    gaps = [m - f for m, f in zip(mfes, finals)]
    print(f"  {label}: n={len(rows)}")
    print(f"    final({HOLD}일고정)  median={_st.median(finals):+.4f} mean={_st.mean(finals):+.4f}")
    print(f"    MFE(보유중최고점)   median={_st.median(mfes):+.4f} mean={_st.mean(mfes):+.4f} mean_day={_st.mean(days):.1f}")
    print(f"    gap(MFE-final)     median={_st.median(gaps):+.4f} mean={_st.mean(gaps):+.4f}")


def main():
    print("=" * 70 + "\nKR BUYBACK 익절타이밍 진단 (설명력용, v1 튜닝 금지)\n" + "=" * 70)
    events = load_events("buyback")
    if not events or "corp_code" not in events[0]:
        print("corp_code 없는 이벤트 → 재pull"); events = pull_events("buyback", years=2.0); save_events("buyback", events)
    corps = sorted({e["corp_code"] for e in events if e.get("corp_code")})
    print(f"buyback {len(events)}건, 고유 corp {len(corps)} → 상세 fetch")
    details = pull_buyback_details(corps, "20240101", "20260921")
    dmap = {(d["corp_code"], d["rcept_dt"]): d for d in details}
    print(f"상세 {len(details)}건")

    series = _series()
    all_rows = []
    by_purpose: dict[str, list] = {}
    for e in events:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        p = _path(b, e["date"])
        if p is None:
            continue
        all_rows.append(p)
        d = dmap.get((e["corp_code"], e["date"].replace("-", "")))
        purpose = "소각" if (d and "소각" in d.get("purpose", "")) else ("주가안정" if (d and "주가" in d.get("purpose", "")) else "기타")
        by_purpose.setdefault(purpose, []).append(p)

    print(f"\n전체({HOLD}일 보유):")
    _report("전체", all_rows)

    print("\n목적별:")
    for pname, rows in sorted(by_purpose.items(), key=lambda x: -len(x[1])):
        _report(pname, rows)

    print("\n결론: gap(MFE-final) 크면 → 익절/트레일링스탑 variant 사전등록 검토. v1(next_open/HOLD20 고정청산) 동결 유지.")


if __name__ == "__main__":
    main()
