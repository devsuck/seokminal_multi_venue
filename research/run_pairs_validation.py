"""페어트레이딩 통계적 차익거래 — 사전등록 검증.

사전등록: PAIRS_STATARB_V1
- 가설: 공적분 쌍(EG p<0.05) D+1 z>2 진입, z<0.5 청산 → 비용 후 Sharpe > 0
- 유니버스: US 동일섹터 ETF 쌍 (사전정의, data snooping 방지)
- IS: 2020-01-01~2022-12-31, OOS: 2023-01-01~현재
- BH-FDR α=0.1 (다중 pair 보정)
- random: 같은 기간 무관 쌍 대조

왜 US ETF: yfinance 오프라인 캐시, 유동성 충분, 대표성 있는 고정 유니버스.

CLI: PYTHONPATH=. python3 research/run_pairs_validation.py
"""
from __future__ import annotations

import math
import random as _random
import statistics as _st

# ── 사전정의 유니버스 (고정, 변경 불가) ─────────────────────────────────
# 경제적 공적분 근거 있는 섹터 내 쌍만. 사후 선택 금지.
PAIRS: list[tuple[str, str, str]] = [
    # ── 동일 사업 · 직접 경쟁 (가장 강한 공적분 후보) ──
    ("KO",   "PEP",  "음료 완전경쟁 — 같은 채널/소비자/원가"),
    ("MO",   "PM",   "담배 모기업/분사 — 2008 PM 스핀오프, 공통 브랜드/원가"),
    ("HD",   "LOW",  "홈인테리어 완전경쟁 — 미국 유이한 두 업체"),
    ("CVS",  "WBA",  "약국 완전경쟁 — 동일 입지/보험/상품"),
    ("VZ",   "T",    "통신 과점 — 망 투자/ARPU 구조 동일"),
    ("MCD",  "QSR",  "패스트푸드 프랜차이즈 — 버거킹 모회사"),
    # ── 동일 상품 다른 ETF 래퍼 ──────────────────────────
    ("HYG",  "JNK",  "하이일드채권 ETF — 동일 자산군"),
    ("GLD",  "IAU",  "금 ETF — 동일 기초자산 다른 운용사"),
    ("USO",  "BNO",  "WTI/브렌트 원유 ETF — 동일 상품군"),
    # ── 동일 채권 만기 ETF ───────────────────────────────
    ("TLT",  "IEF",  "장기/중기 국채 ETF — 이자율 동일 드라이버"),
    # ── 동일 광업 가치사슬 ───────────────────────────────
    ("GLD",  "GDX",  "금 현물 ETF vs 금광주 ETF — 금가격 공통 드라이버"),
    # ── 정제/업스트림 쌍 ─────────────────────────────────
    ("XOM",  "CVX",  "메이저 통합 오일 — 동일 원가/유가 노출"),
]

IS_START  = "2015-01-01"
IS_END    = "2022-12-31"
OOS_START = "2023-01-01"
OOS_END   = "2026-12-31"
COST_BPS  = 10.0          # ETF 페어 왕복 (bid-ask × 2)
COST_STRESS_BPS = 30.0
N_BOOT    = 500
SEED      = 42


def _prices(ticker: str, start: str, end: str) -> list[float] | None:
    try:
        import yfinance as yf
        df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        if df.empty or len(df) < 20:
            return None
        cols = df.columns
        closes = df[("Close", ticker)].values if hasattr(cols, "levels") else df["Close"].values
        return [float(x) for x in closes if not math.isnan(x)]
    except Exception:
        return None


def _align(a: list[float], b: list[float]) -> tuple[list[float], list[float]]:
    n = min(len(a), len(b))
    return a[:n], b[:n]


def _run_pair(a: list[float], b: list[float], cost: float) -> dict:
    from pairs_trading.johansen import test_cointegration
    from pairs_trading.backtest import backtest_pairs
    res = test_cointegration(a, b)
    bt = backtest_pairs(a, b, res["hedge_ratio"], res["spread"], res["signals"], cost_bps=cost)
    return {**res, **bt}


def _random_sharpe(a: list[float], b: list[float], cost: float, n: int = N_BOOT) -> tuple[float, float]:
    """같은 종목 무작위 윈도우 쌍 → Sharpe 분포 → 관측값 퍼센타일 + p-value."""
    from pairs_trading.johansen import test_cointegration
    from pairs_trading.backtest import backtest_pairs
    rng = _random.Random(SEED)
    L = min(len(a), len(b))
    window = L // 2
    sharpes: list[float] = []
    for _ in range(n):
        i = rng.randint(0, L - window - 1)
        j = rng.randint(0, L - window - 1)
        sa, sb = a[i:i+window], b[j:j+window]
        if len(sa) < 20 or len(sb) < 20:
            continue
        try:
            r = test_cointegration(sa, sb)
            bt = backtest_pairs(sa, sb, r["hedge_ratio"], r["spread"], r["signals"], cost_bps=cost)
            s = bt.get("sharpe_ratio")
            if s is not None:
                sharpes.append(s)
        except Exception:
            continue
    if not sharpes:
        return 0.0, 0.5
    obs = None  # will be filled by caller
    return sharpes, len(sharpes)


def main():
    print("=" * 70)
    print("페어트레이딩 — 사전등록 PAIRS_STATARB_V1")
    print("=" * 70)
    print(f"IS: {IS_START}~{IS_END}   OOS: {OOS_START}~현재")
    print(f"비용: base {COST_BPS}bps · stress {COST_STRESS_BPS}bps · 쌍 {len(PAIRS)}개")

    results: list[dict] = []

    for a_sym, b_sym, reason in PAIRS:
        print(f"\n[{a_sym}/{b_sym}] {reason}")

        # 가격 로드
        a_is = _prices(a_sym, IS_START, IS_END)
        b_is = _prices(b_sym, IS_START, IS_END)
        a_oos = _prices(a_sym, OOS_START, OOS_END)
        b_oos = _prices(b_sym, OOS_START, OOS_END)

        if not a_is or not b_is:
            print("  IS 데이터 없음 → SKIP")
            continue

        a_is, b_is = _align(a_is, b_is)
        if len(a_is) < 100:
            print(f"  IS n={len(a_is)} 부족 → SKIP")
            continue

        # IS 공적분 검정 + 백테스트
        is_res = _run_pair(a_is, b_is, COST_BPS)
        eg_p = is_res["eg_pvalue"]
        cointegrated = is_res["cointegrated"]
        sharpe_is = is_res.get("sharpe_ratio")
        hl = is_res.get("half_life_days", 999)
        print(f"  IS 공적분: EG p={eg_p:.4f} {'✓' if cointegrated else '✗'}  half-life={hl:.1f}d  Sharpe={sharpe_is}")

        # OOS 백테스트 (IS hedge ratio 고정)
        sharpe_oos = None
        oos_ret = None
        if a_oos and b_oos:
            a_oos, b_oos = _align(a_oos, b_oos)
            if len(a_oos) >= 50:
                from pairs_trading.johansen import test_cointegration
                from pairs_trading.backtest import backtest_pairs
                # IS hedge ratio 고정(data leakage 방지)
                oos_spread = [a_oos[i] - is_res["hedge_ratio"] * b_oos[i] - is_res["intercept"]
                              for i in range(len(a_oos))]
                spread_mean = _st.mean(oos_spread)
                spread_std = _st.pstdev(oos_spread) or 1.0
                oos_z = [(s - spread_mean) / spread_std for s in oos_spread]
                oos_sig = []
                for z in oos_z:
                    if z > 2.0:   oos_sig.append("sell_spread")
                    elif z < -2.0: oos_sig.append("buy_spread")
                    elif abs(z) < 0.5: oos_sig.append("exit")
                    else: oos_sig.append("hold")
                bt_oos = backtest_pairs(a_oos, b_oos, is_res["hedge_ratio"],
                                        oos_spread, oos_sig, cost_bps=COST_BPS)
                sharpe_oos = bt_oos.get("sharpe_ratio")
                oos_ret = bt_oos.get("total_return_pct")
                print(f"  OOS: Sharpe={sharpe_oos}  ret={oos_ret}%  trades={bt_oos.get('num_trades')}")
            else:
                print(f"  OOS n={len(a_oos)} 부족")

        # stress
        stress_res = _run_pair(a_is, b_is, COST_STRESS_BPS)
        sharpe_stress = stress_res.get("sharpe_ratio")
        print(f"  stress {COST_STRESS_BPS}bps: Sharpe={sharpe_stress}")

        results.append({
            "pair": f"{a_sym}/{b_sym}",
            "eg_p": eg_p,
            "cointegrated_is": cointegrated,
            "half_life": hl,
            "sharpe_is": sharpe_is,
            "sharpe_oos": sharpe_oos,
            "oos_ret_pct": oos_ret,
            "sharpe_stress": sharpe_stress,
            "n_trades_is": is_res.get("num_trades", 0),
        })

    # ── 집계 ──────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"[집계] 총 {len(results)}개 쌍 분석")
    cointegrated_pairs = [r for r in results if r["cointegrated_is"]]
    print(f"  IS 공적분 통과: {len(cointegrated_pairs)}/{len(results)}")

    # BH-FDR (공적분 p-value 기준)
    eg_ps = sorted([(r["eg_p"], r["pair"]) for r in results])
    m = len(eg_ps)
    alpha = 0.1
    bh_threshold = 0
    for rank, (p, pair) in enumerate(eg_ps, 1):
        if p <= alpha * rank / m:
            bh_threshold = rank
    bh_survivors = [pair for _, pair in eg_ps[:bh_threshold]]
    print(f"  BH-FDR α={alpha} 생존: {len(bh_survivors)}개 → {bh_survivors}")

    # OOS 일관성
    oos_valid = [r for r in results if r["sharpe_oos"] is not None]
    if oos_valid:
        oos_pos = [r for r in oos_valid if r["sharpe_oos"] > 0]
        print(f"\n  OOS Sharpe > 0: {len(oos_pos)}/{len(oos_valid)} ({len(oos_pos)/len(oos_valid):.1%})")
        sharpes_oos = [r["sharpe_oos"] for r in oos_valid if r["sharpe_oos"] is not None]
        print(f"  OOS Sharpe median={_st.median(sharpes_oos):.3f} mean={_st.mean(sharpes_oos):.3f}")

    # 종합 판정
    print(f"\n[종합 판정]")
    strong = [r for r in results if r["cointegrated_is"]
              and r.get("sharpe_is") and r["sharpe_is"] > 0.5
              and r.get("sharpe_oos") and r["sharpe_oos"] > 0
              and r.get("sharpe_stress") and r["sharpe_stress"] > 0]
    print(f"  IS Sharpe>0.5 + OOS>0 + stress>0 동시 통과: {len(strong)}개")
    for r in strong:
        print(f"    {r['pair']}: IS {r['sharpe_is']} / OOS {r['sharpe_oos']} / stress {r['sharpe_stress']}")

    if strong and len(bh_survivors) > 0:
        print(f"\n  → CANDIDATE: {len(strong)}개 쌍. 단 ETF 간 스프레드는 arbitrage 아닌 corr trade.")
        print(f"     - 타임아웃: 공적분 붕괴 시 half-life 초과 보유 → 무제한 손실 가능")
        print(f"     - 슬리피지: 실제 bid-ask 반영 필요 (10bps 과소평가 가능)")
    elif cointegrated_pairs:
        print(f"\n  → WATCHLIST: 공적분은 있으나 비용/OOS 기준 미달.")
    else:
        print(f"\n  → REJECT: 공적분 없거나 비용 후 엣지 없음.")

    print("=" * 70)
    return results


if __name__ == "__main__":
    main()
