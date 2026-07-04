"""A — 멀티엣지 포트폴리오 북. 생존 엣지(TSMOM 선물 + buyback KR)를 한 책으로.

각 슬리브 월수익 시계열 → 상관 → 등가중/리스크패리티 조합 → 개별 vs 조합 Sharpe/MDD.
핵심 질문: 무상관이면 합쳐서 Sharpe↑(분산이득)? CB는 음드리프트(롱아님) → 회피오버레이로 별도.
실행: PYTHONPATH=. python3 research/run_portfolio_book.py
"""
from __future__ import annotations

import statistics as _st


def _ann_sharpe(m: list[float]) -> float:
    if len(m) < 2 or _st.stdev(m) < 1e-12:
        return 0.0
    return _st.mean(m) * (12 ** 0.5) / _st.stdev(m)


def _max_dd(m: list[float]) -> float:
    eq, peak, worst = 1.0, 1.0, 0.0
    for r in m:
        eq *= (1 + r); peak = max(peak, eq)
        worst = min(worst, eq / peak - 1)
    return worst


def _corr(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = _st.mean(a), _st.mean(b)
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)
    sa, sb = _st.stdev(a), _st.stdev(b)
    return cov / (sa * sb) if sa > 1e-12 and sb > 1e-12 else 0.0


def _report(name: str, m: list[float]):
    ann = _st.mean(m) * 12
    print(f"  {name:22} n={len(m):3} 연율 {ann:+.2%}  Sharpe {_ann_sharpe(m):+.2f}  MDD {_max_dd(m):+.1%}")


def _stat(m: list[float]) -> dict:
    return {"n": len(m), "ann": round(_st.mean(m) * 12, 6),
            "sharpe": round(_ann_sharpe(m), 3), "mdd": round(_max_dd(m), 4)}


def build_book() -> dict:
    """멀티엣지 북 구조화 데이터(UI용). TSMOM+buyback 월수익 조합."""
    import research.paper.tsmom_forward as tf
    pn = tf.panels()
    res = tf.run_portfolio(pn, tf.tsmom_weights, tf.CFG.PARAMS, tf.CFG.COST_BASE_BPS, tf.CFG.REBALANCE_DAYS)
    tsmom_m = tf.monthly_returns(res["daily_returns"], res["dates"])

    from research.paper.buyback_forward import generate as bb_gen
    bb = bb_gen(write=False)
    bb_m = {m: c["mean"] for m, c in bb["cohorts"].items() if c["n"] >= 5}

    common = sorted(set(tsmom_m) & set(bb_m))
    t = [tsmom_m[m] for m in common]
    b = [bb_m[m] for m in common]
    out = {
        "sleeves": [{"name": "TSMOM (선물)", **_stat(list(tsmom_m.values()))},
                    {"name": "buyback (KR)", **_stat(list(bb_m.values()))}],
        "common_months": len(common),
        "range": f"{common[0]}~{common[-1]}" if common else None,
        "note": "CB 발행=음드리프트(롱 아님) → 회피 오버레이(발행사 배제)로 사용.",
        # live-readiness 제약(② 수용력 분석). 책이 수익뿐 아니라 현실 제약도 보이게.
        "constraints": {
            "buyback": {"scale": "소자본(소형주)", "capacity": "월 ~46억",
                        "events_month": 70, "timing": "1일 지연시 -0.62% (즉시체결 필요)"},
            "tsmom": {"scale": "선물 = 확장 가능(대형 AUM OK)", "capacity": "높음",
                      "events_month": None, "timing": "월 리밸(덜 민감)"},
        },
    }
    if len(common) < 6:
        out["combined"] = None
        return out
    out["correlation"] = round(_corr(t, b), 3)
    ew = [0.5 * t[i] + 0.5 * b[i] for i in range(len(common))]
    vt, vb = (_st.stdev(t) or 1e-9), (_st.stdev(b) or 1e-9)
    wt, wb = (1 / vt), (1 / vb); s = wt + wb; wt, wb = wt / s, wb / s
    rp = [wt * t[i] + wb * b[i] for i in range(len(common))]
    out["combined"] = {
        "equal_weight": {**_stat(ew), "weights": {"tsmom": 0.5, "buyback": 0.5}},
        "risk_parity": {**_stat(rp), "weights": {"tsmom": round(wt, 3), "buyback": round(wb, 3)}},
    }
    # 등가중 누적곡선(월별)
    eq = 1.0
    monthly = []
    for i, m in enumerate(common):
        eq *= (1 + ew[i])
        monthly.append({"period": m, "tsmom": round(t[i], 6), "buyback": round(b[i], 6),
                        "combined": round(ew[i], 6), "cum": round(eq - 1, 6)})
    out["monthly"] = monthly
    return out


def main():
    print("=" * 70)
    print("A — 멀티엣지 포트폴리오 북 (TSMOM 선물 + buyback KR)")
    print("=" * 70)

    # TSMOM 월수익
    import research.paper.tsmom_forward as tf
    pn = tf.panels()
    res = tf.run_portfolio(pn, tf.tsmom_weights, tf.CFG.PARAMS, tf.CFG.COST_BASE_BPS, tf.CFG.REBALANCE_DAYS)
    tsmom_m = tf.monthly_returns(res["daily_returns"], res["dates"])

    # buyback 월수익(월 코호트 평균 이벤트수익 ≈ 슬리브 월 P&L/자본)
    from research.paper.buyback_forward import generate as bb_gen
    bb = bb_gen(write=False)
    bb_m = {m: c["mean"] for m, c in bb["cohorts"].items() if c["n"] >= 5}

    print(f"\nTSMOM 월수 {len(tsmom_m)} | buyback 월수 {len(bb_m)}")
    print("\n개별 슬리브(전체 기간):")
    _report("TSMOM", list(tsmom_m.values()))
    _report("buyback", list(bb_m.values()))

    common = sorted(set(tsmom_m) & set(bb_m))
    if len(common) < 6:
        print(f"\n겹치는 월 {len(common)}개 — 조합 검정 불가(기간 불일치)"); return
    t = [tsmom_m[m] for m in common]
    b = [bb_m[m] for m in common]
    corr = _corr(t, b)
    print(f"\n겹치는 {len(common)}개월 ({common[0]}~{common[-1]}) | 상관 {corr:+.2f}")
    print("겹치는 구간 개별:")
    _report("TSMOM(공통)", t); _report("buyback(공통)", b)

    # 등가중
    ew = [0.5 * t[i] + 0.5 * b[i] for i in range(len(common))]
    # 리스크패리티(역변동성)
    vt, vb = (_st.stdev(t) or 1e-9), (_st.stdev(b) or 1e-9)
    wt, wb = (1 / vt), (1 / vb); s = wt + wb; wt, wb = wt / s, wb / s
    rp = [wt * t[i] + wb * b[i] for i in range(len(common))]
    print(f"\n조합 (분산이득 확인):")
    _report("등가중 0.5/0.5", ew)
    _report(f"리스크패리티 {wt:.0%}/{wb:.0%}", rp)

    best_indiv = max(_ann_sharpe(t), _ann_sharpe(b))
    combo = max(_ann_sharpe(ew), _ann_sharpe(rp))
    print(f"\n최고 개별 Sharpe {best_indiv:+.2f} → 조합 Sharpe {combo:+.2f} "
          f"({'분산이득 O' if combo > best_indiv else '분산이득 미미'})")
    print(f"\nCB 발행 = 음드리프트(롱아님) → 롱슬리브 제외, '회피 오버레이'(CB발행사 배제)로 사용.")
    print("결론: 무상관(상관 {:+.2f})이면 합쳐서 위험대비 개선. 이게 '실제 굴릴 책'.".format(corr))


if __name__ == "__main__":
    main()
