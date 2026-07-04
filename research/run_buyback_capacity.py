"""② buyback 실행/수용력 현실성 — 백테스트→실전 관문.

질문: 진짜 굴릴 수 있나? ①이벤트 빈도(월 몇건) ②유동성(자본 배치 가능액)
③체결 타이밍 민감도(next_open vs 지연 vs 슬리피지) ④발행사 집중도.
실행: PYTHONPATH=. python3 research/run_buyback_capacity.py
"""
from __future__ import annotations

import bisect
import glob
import os
import statistics as _st

from research.data.kr_dart_events import load_events
from research.data.krx_api import build_series, market_dir

HOLD = 20
COST = 40.0


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _entry_net(b, ed, entry_offset=0, slip_bps=0.0):
    """entry_offset: 0=익일시가, 1=익익일시가(지연). slip_bps: 진입 슬리피지."""
    j = bisect.bisect_right(b["dates"], ed) + entry_offset
    if j >= len(b["dates"]):
        return None
    entry = b["open"][j] * (1 + slip_bps / 1e4)
    xi = min(j + HOLD, len(b["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return b["close"][xi] / entry - 1 - COST / 1e4


def main():
    print("=" * 70)
    print("② buyback 실행/수용력 현실성 (live-readiness)")
    print("=" * 70)
    series = _series()
    bb = load_events("buyback")
    matched = [(e, series[e["stock_code"]]) for e in bb if e["stock_code"] in series]

    # ── ① 빈도(월 몇건) ──
    months = sorted(set(e["date"][:7] for e, _ in matched))
    per_month = len(matched) / len(months)
    print(f"\n[빈도] 총 {len(matched)}건 / {len(months)}개월 = 월평균 {per_month:.1f}건")

    # ── ② 유동성(배치 가능 자본) ──
    depl = []
    for e, b in matched:
        k = bisect.bisect_right(b["dates"], e["date"]) - 1
        if k >= 20:
            tv = _st.mean(b["tval"][k - 20:k])   # 20일 평균 거래대금(원)
            depl.append(tv * 0.10)               # 10% 참여 가정 = 임팩트 낮은 배치액
    depl.sort()
    med = depl[len(depl) // 2]
    p25 = depl[len(depl) // 4]
    print(f"[유동성] 이벤트당 배치가능(거래대금 10%): 중앙값 {med/1e8:.1f}억 / 하위25% {p25/1e8:.1f}억")
    print(f"         월 {per_month:.0f}건 × 중앙 {med/1e8:.1f}억 ≈ 월 수용력 ~{per_month*med/1e8:.0f}억 규모")

    # ── ③ 체결 타이밍 민감도 ──
    base = [_entry_net(b, e["date"]) for e, b in matched]
    base = [x for x in base if x is not None]
    delay1 = [_entry_net(b, e["date"], entry_offset=1) for e, b in matched]
    delay1 = [x for x in delay1 if x is not None]
    slip = [_entry_net(b, e["date"], slip_bps=50) for e, b in matched]
    slip = [x for x in slip if x is not None]
    print(f"\n[체결 타이밍]")
    print(f"  익일시가(기준):   net {_st.mean(base):+.4f}")
    print(f"  익익일시가(1일지연): net {_st.mean(delay1):+.4f}  ({_st.mean(delay1)-_st.mean(base):+.4f})")
    print(f"  익일시가+50bps슬립: net {_st.mean(slip):+.4f}  ({_st.mean(slip)-_st.mean(base):+.4f})")

    # ── ④ 발행사 집중도 ──
    from collections import Counter
    cnt = Counter(e["stock_code"] for e, _ in matched)
    top10 = cnt.most_common(10)
    top10_share = sum(n for _, n in top10) / len(matched)
    print(f"\n[집중도] 상위10 종목이 이벤트의 {top10_share:.1%} | 최다: {top10[0][1]}건")
    print(f"         → 발행사/종목 중복제한 필요(팻테일 분산)")

    # ── 종합 판정 ──
    timing_ok = _st.mean(delay1) > 0 and _st.mean(base) - _st.mean(delay1) < 0.01
    liq_ok = med > 1e8   # 중앙 배치 1억+
    freq_ok = per_month >= 5
    print(f"\n[live-readiness]")
    print(f"  빈도 {'OK' if freq_ok else '낮음'}(월{per_month:.0f}) · 유동성 {'OK' if liq_ok else '얇음'}(중앙{med/1e8:.1f}억) · "
          f"타이밍 {'견고' if timing_ok else '민감'}(지연시 {_st.mean(delay1)-_st.mean(base):+.4f})")
    print(f"  결론: {'실전 가능한 규모·현실성' if (freq_ok and liq_ok) else '소자본 한정'} / "
          f"타이밍은 {'덜 민감' if timing_ok else '민감(즉시체결 인프라 필요)'}")

    from research.agents.experiment_registry import log_experiment
    log_experiment({"hypothesis_id": "kr_buyback_capacity_v1", "status": "analysis",
                    "per_month": round(per_month, 1), "deploy_median_krw": round(med),
                    "base_net": round(_st.mean(base), 6), "delay1_net": round(_st.mean(delay1), 6),
                    "slip50_net": round(_st.mean(slip), 6), "top10_share": round(top10_share, 4),
                    "note": "실행/수용력 분석. live-readiness 게이트"})


if __name__ == "__main__":
    main()
