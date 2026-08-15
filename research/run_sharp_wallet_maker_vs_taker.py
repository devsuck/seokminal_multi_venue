"""sharp_wallet 페이퍼봇 taker(현재 라이브 방식) vs 메이커 지정가 체결 비교.

틱 수집기 커버리지가 좁아(2026-08-04 전수조사: anchor 3149개 중 120개만 틱
데이터 존재, ~4%) 전체 모집단 결론이 아니라 겹치는 구간 한정 방향성 확인용.
entry만 taker/maker로 갈리고 exit는 양쪽 다 동일하게 horizon 만료 시 강제
taker 청산(현재 라이브 봇과 동일 가정) — entry 체결방식만 격리해서 비교.

사용: python3 -m research.run_sharp_wallet_maker_vs_taker
"""
from __future__ import annotations

from pathlib import Path

from research import jsonl_dates
from research.hypotheses.polymarket_sharp_wallet import build_convergence_count, load_sharp_wallet_trades
from research.polymarket_tick.fill_sim import load_tick_window, simulate_maker_fill
from research.validation.cost_model import polymarket_effective_cost_bps

_HORIZON_S = 300.0  # 봇의 _HORIZONS_BY_BUCKET 유일값(bucket1/3)과 동일
_LIVE_BUCKETS = (1, 3)  # bucket2는 봇 v1 진입 금지 그룹


def _spread_bps(rows: list[dict]) -> float | None:
    for row in reversed(rows):
        bid, ask = row.get("best_bid"), row.get("best_ask")
        if bid and ask and ask > bid:
            return (ask - bid) / ((ask + bid) / 2) * 10_000
    return None


def _price_near(rows: list[dict], ts: float) -> float | None:
    trades = [r for r in rows if r.get("event_type") == "price_change"]
    before = [r for r in trades if r["_ts_epoch"] <= ts]
    if before:
        return before[-1]["price"]
    after = [r for r in trades if r["_ts_epoch"] > ts]
    return after[0]["price"] if after else None


def run(dates: list[str] | None = None) -> dict:
    if dates is None:
        dates = jsonl_dates.list_dates(Path("research/data/polymarket_sharp_wallet"))
    trades = load_sharp_wallet_trades(dates)
    anchors = build_convergence_count(trades)
    anchors = anchors[anchors["convergence_bucket"].isin(_LIVE_BUCKETS)]

    taker_pnls: list[float] = []
    maker_pnls: list[float] = []
    covered = 0
    no_coverage = 0

    for _, row in anchors.iterrows():
        if row["outcome_index"] not in (0, 1):
            continue
        outcome = "yes" if row["outcome_index"] == 0 else "no"
        direction = float(row["direction"])
        ts_a, ts_b = float(row["ts"]), float(row["ts"]) + _HORIZON_S

        window = load_tick_window(row["condition_id"], ts_a, ts_b)
        window = [r for r in window if r.get("outcome") == outcome]
        entry_price = _price_near(window, ts_a)
        exit_price = _price_near(window, ts_b)
        if not window or entry_price is None or exit_price is None:
            no_coverage += 1
            continue
        covered += 1

        entry_spread = _spread_bps([r for r in window if r["_ts_epoch"] <= ts_a]) or 200.0
        exit_spread = _spread_bps([r for r in window if r["_ts_epoch"] <= ts_b]) or 200.0

        # taker: 현재 라이브 봇과 동일 — 왕복(entry+exit) 스프레드 비용
        taker_cost_bps = polymarket_effective_cost_bps(spread_bps=(entry_spread + exit_spread) / 2)
        taker_cost = (entry_price + exit_price) * taker_cost_bps / 10_000.0
        taker_pnls.append(direction * (exit_price - entry_price) - taker_cost)

        # maker: entry는 anchor 시점 best_bid/ask에 지정가, 체결 여부는 이후 실제 프린트로 판정
        book_rows = [r for r in window if r["_ts_epoch"] <= ts_a and r.get("best_bid") and r.get("best_ask")]
        if not book_rows:
            continue
        bid, ask = book_rows[-1]["best_bid"], book_rows[-1]["best_ask"]
        limit_price = bid if direction > 0 else ask
        fill = simulate_maker_fill(row["condition_id"], outcome, direction, limit_price, ts_a, ts_b)
        if not fill["filled"]:
            continue  # 미체결 — maker PnL 기여 없음(fill-rate에서만 집계)

        # exit는 taker와 동일하게 강제청산 — exit leg만 스프레드 비용 발생(entry는 메이커라 무비용)
        maker_cost_bps = polymarket_effective_cost_bps(spread_bps=exit_spread)
        maker_cost = exit_price * maker_cost_bps / 10_000.0
        maker_pnls.append(direction * (exit_price - fill["fill_price"]) - maker_cost)

    return {
        "anchors_total": int(len(anchors)),
        "covered": covered,
        "no_tick_coverage": no_coverage,
        "taker_n": len(taker_pnls),
        "taker_mean_pnl_per_share": round(sum(taker_pnls) / len(taker_pnls), 5) if taker_pnls else None,
        "maker_fill_rate": round(len(maker_pnls) / covered, 3) if covered else None,
        "maker_n_filled": len(maker_pnls),
        "maker_mean_pnl_per_share": round(sum(maker_pnls) / len(maker_pnls), 5) if maker_pnls else None,
    }


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(run(), indent=2, ensure_ascii=False))
