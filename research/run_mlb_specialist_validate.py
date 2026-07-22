"""Polymarket MLB 스페셜리스트 컨센서스 검증 러너 — 다변형 BH-FDR 스크리닝, 실집행 없음.

변형 그리드 = {랭킹지표 pnl/winrate/roi} × {임계 majority/unanimous} × {N 4/5}.
각 변형의 컨센서스 신호 라벨(경기 정산까지 forward return)에서 방향 무작위 셔플
베이스라인 대비 empirical p-value를 구하고, **전 변형을 한 BH-FDR 풀로 보정**한다
(변형 골라잡기 = p-해킹 방지, 프로젝트 전역 규율). 다각화 봇 성과가 베이스라인.

⚠️ 스크리닝. 결과는 통계적 유의미성 확인일 뿐 실집행 근거 아님. walk-forward로
스페셜리스트를 선정하되(look-ahead 차단), 신규 라이브 수집 직후엔 표본 미달 —
BH-FDR 통과 시 전체 파이프라인 승격 검토.

NOTE: raw 수집 데이터(트레이드/포지션 스냅샷/정산결과)를 walk-forward로 돌려
변형별 라벨(`variant_labels`)을 조립하는 `load_and_report()`는 수집기(Task 3)
데이터 포맷에 결합돼 있어 데이터 축적 후 맥에서 완성한다. 여기 `compute_report`는
변형별 라벨을 입력받는 순수 검증 코어(완전 테스트됨).
"""
from __future__ import annotations

import datetime as dt
import json
import random as _random
from pathlib import Path

import pandas as pd

from research.hypotheses.mlb_specialist_consensus import build_labels, consensus_signals
from research.mlb_specialist.leaderboard import rank_specialists, wallet_mlb_stats
from research.validation.baselines import empirical_p_value
from research.validation.cost_model import polymarket_effective_cost_bps
from research.validation.metrics import trade_metrics
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/mlb_specialist"
RANKING_METRICS = ["pnl", "winrate", "roi"]
THRESHOLDS = ["majority", "unanimous"]
N_VALUES = [4, 5]
MIN_EVENTS = 10
N_RUNS = 500
SEED = 42
TRADE_SIZE = 1.0
COST_BPS = polymarket_effective_cost_bps()
# 스페셜리스트 게이트(스펙 §3.2 MIN_BETS/MIN_SPEC — 값 미지정이라 leaderboard 테스트
# 선례 그대로 사용). 컨센서스 파라미터(스펙 §3.4 기본값): N은 N_VALUES 변형 그리드,
# MIN_PRESENT 기본 3.
MIN_BETS = 10
MIN_SPEC = 0.5
MIN_PRESENT = 3


def variant_key(metric: str, threshold: str, n: int) -> str:
    return f"{metric}:{threshold}:N{n}"


def enumerate_variants() -> list[str]:
    return [variant_key(m, t, n) for m in RANKING_METRICS for t in THRESHOLDS for n in N_VALUES]


def _variant_pvalue(labels: pd.DataFrame) -> tuple[dict, dict]:
    """라벨(entry_price/exit_price/direction)에서 실제 total_pnl vs 방향 셔플 베이스라인."""
    rng = _random.Random(SEED)
    precomputed = []
    for _, row in labels.iterrows():
        en, ex = float(row["entry_price"]), float(row["exit_price"])
        cost = (abs(en) + abs(ex)) * TRADE_SIZE * COST_BPS / 10_000.0
        precomputed.append((float(row["direction"]), en, ex, cost))
    actual = [d * (ex - en) * TRADE_SIZE - c for d, en, ex, c in precomputed]
    strat = trade_metrics([{"pnl": p} for p in actual])
    random_totals = []
    for _ in range(N_RUNS):
        total = 0.0
        for _d, en, ex, c in precomputed:
            total += rng.choice((1.0, -1.0)) * (ex - en) * TRADE_SIZE - c
        random_totals.append(round(total, 6))
    return strat, empirical_p_value(strat["total_pnl"], random_totals)


def compute_report(variant_labels: dict[str, pd.DataFrame]) -> dict:
    """변형별 라벨 dict → 변형별 p-value + 단일 BH-FDR 풀 + verdict. 순수함수."""
    variants: list[dict] = []
    pvals: list[float] = []
    keys: list[str] = []
    for key, labels in variant_labels.items():
        n = 0 if labels is None else len(labels)
        if n < MIN_EVENTS:
            variants.append({"variant": key, "blocked": True,
                             "reason": f"라벨 {n}건 — 최소 표본 미달"})
            continue
        strat, pval = _variant_pvalue(labels)
        variants.append({"variant": key, "blocked": False, "n_events": n,
                         "total_pnl": strat["total_pnl"], "p_value": pval["p_value"],
                         "percentile": pval["percentile"]})
        pvals.append(pval["p_value"])
        keys.append(key)

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1}
    survivors = [k for k, s in zip(keys, bh["survivors"]) if s]
    pool = {"name": "mlb_specialist_consensus", "alpha": bh["alpha"], "n_tested": len(pvals),
            "n_survivors": bh["n_survivors"], "survivors": survivors, "threshold": bh.get("threshold")}
    verdict = "no_data" if not pvals else ("candidate" if pool["n_survivors"] > 0 else "no_edge")
    return {"hypothesis": "mlb_specialist_consensus", "cost_bps": COST_BPS,
            "variants": variants, "pools": [pool], "verdict": verdict}


def _load_jsonl_dir(dirpath: Path) -> list[dict]:
    rows: list[dict] = []
    if not dirpath.is_dir():
        return rows
    for f in sorted(dirpath.glob("*.jsonl")):
        with f.open() as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def _outcome_side(outcome) -> str | None:
    """체결 outcome("Yes"/"No" 등, data-api 실응답 확인: 2026-07-22) → "YES"/"NO".
    ⚠️ raw `side` 필드는 BUY/SELL(주문방향)이라 정산결과(winning_side)와 비교 불가 —
    leaderboard/consensus가 쓰는 "side"는 outcome(보유 방향)이어야 함."""
    if outcome is None:
        return None
    o = str(outcome).strip().upper()
    return o if o in ("YES", "NO") else None


def _build_resolutions(market_rows: list[dict]) -> dict[str, dict]:
    """condition_id별 최신 스냅샷이 closed면 yes/no 가격(1.0/0.0)에서 승패 도출."""
    latest: dict[str, dict] = {}
    for r in market_rows:
        cid = r.get("condition_id")
        if not cid:
            continue
        prev = latest.get(cid)
        if prev is None or r.get("ts", 0) >= prev.get("ts", 0):
            latest[cid] = r
    out = {}
    for cid, r in latest.items():
        if not r.get("closed"):
            continue
        yp, np_ = r.get("yes_price"), r.get("no_price")
        if yp is None or np_ is None:
            continue
        out[cid] = {"winning_side": "YES" if yp > np_ else "NO", "resolved_ts": r.get("ts", 0.0)}
    return out


def _build_entry_prices(market_rows: list[dict]) -> dict[str, dict[str, float]]:
    """condition_id별 최초 관측 가격(신호 시점 근사) — {"YES": ..., "NO": ...}."""
    out: dict[str, dict[str, float]] = {}
    for r in sorted(market_rows, key=lambda x: x.get("ts", 0)):
        cid = r.get("condition_id")
        if not cid or cid in out:
            continue
        yp, np_ = r.get("yes_price"), r.get("no_price")
        if yp is None or np_ is None:
            continue
        out[cid] = {"YES": float(yp), "NO": float(np_)}
    return out


def _daily_positions(trade_rows: list[dict]) -> dict[str, list[dict]]:
    """UTC 날짜별 포지션 스냅샷([{proxy_wallet, condition_id, side}]) — 중간매도 무시
    단순화(레벨보드와 동일, 스펙 §3.1)라 그날 체결 전부를 그대로 포지션으로 취급."""
    out: dict[str, list[dict]] = {}
    for t in trade_rows:
        side = _outcome_side(t.get("outcome"))
        wallet, cid, ts = t.get("proxy_wallet"), t.get("condition_id"), t.get("ts")
        if side is None or not wallet or not cid or ts is None:
            continue
        day = dt.datetime.fromtimestamp(float(ts), tz=dt.timezone.utc).date().isoformat()
        out.setdefault(day, []).append({"proxy_wallet": wallet, "condition_id": cid, "side": side})
    return out


def _trades_df(trade_rows: list[dict]) -> pd.DataFrame:
    cols = ["proxy_wallet", "condition_id", "side", "price", "size", "notional_usd", "ts"]
    rows = []
    for t in trade_rows:
        side = _outcome_side(t.get("outcome"))
        if side is None:
            continue
        rows.append({
            "proxy_wallet": t.get("proxy_wallet"), "condition_id": t.get("condition_id"), "side": side,
            "price": float(t.get("price", 0) or 0), "size": float(t.get("size", 0) or 0),
            "notional_usd": float(t.get("notional_usd", 0) or 0), "ts": float(t.get("ts", 0) or 0),
        })
    return pd.DataFrame(rows, columns=cols)


def load_and_report(data_dir: str = DATA_DIR) -> dict:
    """수집기(Task 3)가 쌓은 trades/{date}.jsonl + markets/{date}.jsonl에서 매일
    walk-forward 조립(스펙 §3.3): as_of 시점까지 정산된 성적으로 스페셜리스트
    재선정 → 그날 컨센서스 신호 → 변형별 라벨 누적 → compute_report."""
    base = Path(data_dir)
    trade_rows = _load_jsonl_dir(base)
    market_rows = _load_jsonl_dir(base / "markets")
    resolutions = _build_resolutions(market_rows)
    entry_prices = _build_entry_prices(market_rows)
    trades_df = _trades_df(trade_rows)
    by_day = _daily_positions(trade_rows)
    days = sorted(by_day)

    variant_labels: dict[str, pd.DataFrame] = {}
    for metric in RANKING_METRICS:
        for threshold in THRESHOLDS:
            for n in N_VALUES:
                signals: list[dict] = []
                for day in days:
                    as_of = dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp()
                    stats = wallet_mlb_stats(trades_df, resolutions, as_of=as_of)
                    specialists = rank_specialists(stats, metric, n, MIN_BETS, MIN_SPEC)
                    if not specialists:
                        continue
                    signals.extend(consensus_signals(by_day[day], specialists, MIN_PRESENT, threshold))
                variant_labels[variant_key(metric, threshold, n)] = build_labels(signals, resolutions, entry_prices)
    return compute_report(variant_labels)


def main() -> None:
    # 데이터 조립(load_and_report)은 수집기 데이터 축적 후 맥에서 완성 — 위 NOTE 참고.
    print("MLB 스페셜리스트 검증 — 변형 그리드:")
    for v in enumerate_variants():
        print(f"  {v}")
    print(f"\ncost_bps(polymarket) = {COST_BPS}, MIN_EVENTS={MIN_EVENTS}, N_RUNS={N_RUNS}")
    print("데이터 조립(walk-forward)은 수집기 데이터 축적 후 연결 — compute_report는 준비 완료.")


if __name__ == "__main__":
    main()
