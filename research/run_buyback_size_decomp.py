"""KR buyback size 분해 — 설명력/리스크용(v1 필터 수정 아님).

취득예정금액/시총, 취득예정금액/ADV, 취득주식수/유통, 취득목적별 포워드수익 분해.
size effect 강하면 → Buyback Size-Aware v2를 별도 사전등록(여기서 v1 튜닝 금지).
실행: PYTHONPATH=. python3 research/run_buyback_size_decomp.py
"""
from __future__ import annotations

import bisect
import statistics as _st
import glob, os

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events, pull_buyback_details, save_events, pull_events
from research.paper import buyback_config as CFG

HOLD = CFG.HOLD_DAYS
RT = CFG.COST_BASE_BPS


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _fwd_and_ctx(bars, event_date):
    j0 = bisect.bisect_right(bars["dates"], event_date) - 1
    i = j0 + 1
    if j0 < 0 or i >= len(bars["dates"]):
        return None
    entry = bars["open"][i]; xi = min(i + HOLD, len(bars["dates"]) - 1)
    if entry <= 0 or xi < i + HOLD:
        return None
    ret = (bars["close"][xi] / entry - 1) - RT / 10_000.0
    # 시총 + ADV(20일 평균 거래대금) at event
    mc = bars["marcap"][j0] if j0 < len(bars["marcap"]) else 0
    adv = _st.mean(bars["tval"][max(0, j0 - 20):j0]) if j0 >= 5 else 0
    return ret, mc, adv


def _bucket_report(label, pairs):
    """pairs=[(ratio, ret)] → 분위별 net."""
    pairs = [(x, r) for x, r in pairs if x is not None and x > 0]
    if len(pairs) < 20:
        print(f"  {label}: 표본 부족({len(pairs)})"); return
    pairs.sort()
    q = len(pairs) // 4
    for name, seg in [("하위25%", pairs[:q]), ("중간50%", pairs[q:3 * q]), ("상위25%", pairs[3 * q:])]:
        rets = [r for _, r in seg]
        print(f"  {label} {name}: n={len(seg)} median={_st.median(rets):+.4f} mean={_st.mean(rets):+.4f}")


def main():
    print("=" * 70 + "\nKR BUYBACK SIZE 분해 (설명력용, v1 튜닝 금지)\n" + "=" * 70)
    events = load_events("buyback")
    if not events or "corp_code" not in events[0]:
        print("corp_code 없는 이벤트 → 재pull"); events = pull_events("buyback", years=2.0); save_events("buyback", events)
    corps = sorted({e["corp_code"] for e in events if e.get("corp_code")})
    print(f"buyback {len(events)}건, 고유 corp {len(corps)} → 상세 fetch")
    details = pull_buyback_details(corps, "20240101", "20260701")
    # (corp_code, rcept_dt) → detail
    dmap = {(d["corp_code"], d["rcept_dt"]): d for d in details}
    print(f"상세 {len(details)}건")

    series = _series()
    amt_mc, amt_adv, shr_flt, by_purpose = [], [], [], {}
    for e in events:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        fc = _fwd_and_ctx(b, e["date"])
        if fc is None:
            continue
        ret, mc, adv = fc
        d = dmap.get((e["corp_code"], e["date"].replace("-", "")))
        if d and d.get("plan_amount"):
            if mc > 0:
                amt_mc.append((d["plan_amount"] / mc, ret))
            if adv > 0:
                amt_adv.append((d["plan_amount"] / adv, ret))
        # 목적 분해 (소각 vs 기타)
        purpose = "소각" if (d and "소각" in d.get("purpose", "")) else ("주가안정" if (d and "주가" in d.get("purpose", "")) else "기타")
        by_purpose.setdefault(purpose, []).append(ret)

    print("\n#3-a 취득예정금액/시가총액 (클수록 강한 신호?):")
    _bucket_report("금액/시총", amt_mc)
    print("\n#3-b 취득예정금액/ADV (유동성 대비 규모):")
    _bucket_report("금액/ADV", amt_adv)
    print("\n#3-c 취득 목적별 (net median/mean):")
    for p, rs in sorted(by_purpose.items(), key=lambda x: -len(x[1])):
        if len(rs) >= 20:
            print(f"  {p:8} n={len(rs)} median={_st.median(rs):+.4f} mean={_st.mean(rs):+.4f} 승률={sum(1 for x in rs if x>0)/len(rs):.3f}")

    print("\n결론: size effect 강하면 Buyback Size-Aware v2 별도 사전등록. v1(next_open/HOLD20) 동결 유지.")


if __name__ == "__main__":
    main()
