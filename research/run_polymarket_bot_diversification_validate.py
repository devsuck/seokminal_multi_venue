"""Polymarket 다각화 배스킷(무엣지 베이스라인) 사후검증 러너 — 실집행 없음, 스크리닝만.

`api_server/polymarket_bot.py`는 스스로 "엣지 주장 없음"이라 적어뒀지만(다각화용
저상관 이벤트 리스크 분산), 정산 로그(data/polymarket_bot_log.jsonl, kind="resolve")
실측 승률이 진입가(시장 내재확률)보다 눈에 띄게 높아 재검토 요청받음(2026-08-15).

귀무가설: "시장가(entry_price)=진짜 승률"(효율시장) → 이 가정으로 각 트레이드를
Bernoulli(p=entry_price) 재추첨한 몬테카를로 귀무분포 대비 실제 net PnL의 empirical
p-value를 구한다. 가격밴드 2변형(mid/heavy favorite, 중앙값 분할)을 단일 BH-FDR
풀로 보정(변형 골라잡기 방지, 프로젝트 전역 규율)한 뒤 walk-forward(시간순 전/후반
둘 다 양수) 게이트. idiom은 run_mlb_specialist_validate.py/
run_polymarket_whale_coincidence_validate.py와 동일 — validation/* 그대로 재사용.

⚠️ 스크리닝. verdict=="candidate"라도 실집행 근거 아님 — 표본 37건, 사후 밴드분할.
"""
from __future__ import annotations

import json
import random as _random
import statistics as _st
from pathlib import Path

from research.validation.baselines import empirical_p_value
from research.validation.cost_model import polymarket_effective_cost_bps
from research.validation.metrics import trade_metrics
from research.validation.multiple_testing import benjamini_hochberg

LOG_PATH = Path("data/polymarket_bot_log.jsonl")
PER_MARKET_USD = 20.0
N_RUNS = 500
SEED = 42
MIN_EVENTS = 10
COST_BPS = polymarket_effective_cost_bps()


def load_resolved(path: Path = LOG_PATH) -> list[dict]:
    """kind="resolve" 로그만, 시간순(walk-forward 전제)."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get("kind") == "resolve":
            rows.append(d)
    rows.sort(key=lambda r: r["ts"])
    return rows


def _split_bands(rows: list[dict]) -> dict[str, list[dict]]:
    """진입가 중앙값 분할 — 엣지가 특정 밴드에 몰려있는지(vs 전체 평평) 확인용."""
    if not rows:
        return {"mid_favorite": [], "heavy_favorite": []}
    median = _st.median(r["entry_price"] for r in rows)
    return {
        "mid_favorite": [r for r in rows if r["entry_price"] < median],
        "heavy_favorite": [r for r in rows if r["entry_price"] >= median],
    }


def _trade_pnl(entry_price: float, won: bool) -> tuple[float, float]:
    """(net_pnl, cost) — shares=스테이크/진입가, 승리시 정산가 1.0, 패배시 0.0."""
    shares = PER_MARKET_USD / entry_price
    exit_price = 1.0 if won else 0.0
    cost = (entry_price + exit_price) * shares * COST_BPS / 10_000.0
    gross = (shares * exit_price) - PER_MARKET_USD
    return gross - cost, cost


def _walk_forward(rows: list[dict]) -> dict:
    """시간순 전/후반 2분할 net PnL 부호 게이트 — 프로젝트 전역 idiom
    (run_polymarket_whale_validate.py._walk_forward)과 동일."""
    n = len(rows)
    mid = n // 2

    def _net(chunk):
        return round(sum(_trade_pnl(r["entry_price"], bool(r["payout"]))[0] for r in chunk), 6)

    first, second = _net(rows[:mid]), _net(rows[mid:])
    return {"wf_first": first, "wf_second": second, "n_first": mid, "n_second": n - mid,
            "both_positive": first > 0 and second > 0}


def _variant_report(rows: list[dict]) -> dict:
    net_pnls = [_trade_pnl(r["entry_price"], bool(r["payout"]))[0] for r in rows]
    strat = trade_metrics([{"pnl": p} for p in net_pnls])

    rng = _random.Random(SEED)
    random_totals = []
    for _ in range(N_RUNS):
        total = 0.0
        for r in rows:
            won = rng.random() < r["entry_price"]  # 귀무: 시장가=진짜 확률
            total += _trade_pnl(r["entry_price"], won)[0]
        random_totals.append(round(total, 6))

    pval = empirical_p_value(strat["total_pnl"], random_totals)
    return {"n_events": len(rows), "strategy": strat, "random": pval, "walk_forward": _walk_forward(rows)}


def compute_report(rows: list[dict]) -> dict:
    """정산 로그 rows → 밴드별 검정 + 단일 BH-FDR 풀 + verdict. 순수함수."""
    bands = _split_bands(rows)
    variants: list[dict] = []
    pvals: list[float] = []
    keys: list[str] = []
    wf_ok: dict[str, bool] = {}
    for key, band_rows in bands.items():
        if len(band_rows) < MIN_EVENTS:
            variants.append({"variant": key, "blocked": True,
                             "reason": f"라벨 {len(band_rows)}건 — 최소 표본({MIN_EVENTS}) 미달"})
            continue
        r = _variant_report(band_rows)
        variants.append({"variant": key, "blocked": False, "n_events": r["n_events"],
                         "total_pnl": r["strategy"]["total_pnl"], "win_rate": r["strategy"]["win_rate"],
                         "avg_entry_price": round(_st.mean(x["entry_price"] for x in band_rows), 4),
                         "p_value": r["random"]["p_value"], "percentile": r["random"]["percentile"],
                         "walk_forward": r["walk_forward"]})
        pvals.append(r["random"]["p_value"])
        keys.append(key)
        wf_ok[key] = r["walk_forward"]["both_positive"]

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1}
    survivors_raw = [k for k, s in zip(keys, bh["survivors"]) if s]
    survivors = [k for k in survivors_raw if wf_ok.get(k)]
    pool = {"name": "polymarket_bot_diversification", "alpha": bh["alpha"], "n_tested": len(pvals),
            "n_survivors": len(survivors), "survivors": survivors,
            "survivors_before_walk_forward": survivors_raw, "threshold": bh.get("threshold")}
    verdict = "no_data" if not rows else ("candidate" if pool["n_survivors"] > 0 else "no_edge")
    return {"hypothesis": "polymarket_bot_diversification", "cost_bps": COST_BPS,
            "n_resolved": len(rows), "variants": variants, "pools": [pool], "verdict": verdict}


def load_and_report(path: Path = LOG_PATH) -> dict:
    return compute_report(load_resolved(path))


def main() -> None:
    rep = load_and_report()
    print(f"\n=== cost_bps(polymarket) = {rep['cost_bps']}, n_resolved={rep['n_resolved']} ===\n")
    for v in rep["variants"]:
        if v["blocked"]:
            print(f"{v['variant']} -> BLOCKED ({v['reason']})")
            continue
        wf = v["walk_forward"]
        print(f"{v['variant']} n={v['n_events']} avg_entry_price={v['avg_entry_price']} "
              f"win_rate={v['win_rate']} total_pnl={v['total_pnl']} p_value={v['p_value']} "
              f"percentile={v['percentile']} wf_first={wf['wf_first']}(n={wf['n_first']}) "
              f"wf_second={wf['wf_second']}(n={wf['n_second']}) wf_both_positive={wf['both_positive']}")
    for pool in rep["pools"]:
        print(f"\n=== BH-FDR (polymarket_bot_diversification 풀, alpha={pool['alpha']}) ===")
        print(f"survivors before walk-forward gate: {pool['survivors_before_walk_forward']}")
        print(f"survivors (BH-FDR + walk-forward both>0): {pool['survivors']}")
        print(f"n_survivors: {pool['n_survivors']} / {pool['n_tested']}")
    print(f"\nverdict: {rep['verdict']}")


if __name__ == "__main__":
    main()
