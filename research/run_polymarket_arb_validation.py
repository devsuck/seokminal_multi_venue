"""수집된 오더북 스냅샷(research/data/polymarket_arb/*.jsonl)으로 폴리마켓
합가격 차익거래 기회의 go/no-go를 판정한다.

기존 하우스 방식(랜덤 베이스라인 p-value)과 다른 3축 게이트:
지속성(연속 유지시간) x 순마진(사이즈 감안 캡처가능액) x 빈도(주당 발생건수).

Usage: python -m research.run_polymarket_arb_validation [--data-dir DIR] [--min-duration-sec N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path


def load_snapshots(data_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(Path(data_dir).glob("*.jsonl")):
        for line in path.read_text().strip().splitlines():
            if line:
                rows.append(json.loads(line))
    return rows


def _capturable_margin_usd(row: dict) -> float:
    capturable_size = min(row["yes_ask_size"], row["no_ask_size"])
    return round(capturable_size * (1.0 - row["sum_ask"]), 4)


def _summarize_run(condition_id: str, rows: list[dict]) -> dict:
    start = dt.datetime.fromisoformat(rows[0]["ts"])
    end = dt.datetime.fromisoformat(rows[-1]["ts"])
    return {
        "condition_id": condition_id,
        "start_ts": rows[0]["ts"],
        "end_ts": rows[-1]["ts"],
        "duration_sec": (end - start).total_seconds(),
        "min_sum_ask": min(r["sum_ask"] for r in rows),
        "ticks": len(rows),
        "max_capturable_margin_usd": max(_capturable_margin_usd(r) for r in rows),
    }


def find_opportunity_runs(snapshots: list[dict]) -> list[dict]:
    """condition_id별 시간순 정렬 후 연속된 is_opportunity=True 구간(run)을 찾는다."""
    by_market: dict[str, list[dict]] = defaultdict(list)
    for row in snapshots:
        by_market[row["condition_id"]].append(row)

    runs: list[dict] = []
    for condition_id, rows in by_market.items():
        rows.sort(key=lambda r: r["ts"])
        current: list[dict] = []
        for row in rows:
            if row["is_opportunity"]:
                current.append(row)
            else:
                if current:
                    runs.append(_summarize_run(condition_id, current))
                    current = []
        if current:
            runs.append(_summarize_run(condition_id, current))
    return runs


def evaluate_runs(runs: list[dict], min_duration_sec: float = 3.0) -> dict:
    persistent = [r for r in runs if r["duration_sec"] >= min_duration_sec]
    if not persistent:
        return {"persistent_runs": 0, "runs_per_week": 0.0, "verdict": "REJECT_NO_PERSISTENT_RUNS"}

    start_times = [dt.datetime.fromisoformat(r["start_ts"]) for r in persistent]
    span_days = max((max(start_times) - min(start_times)).total_seconds() / 86400, 1.0)
    runs_per_week = round(len(persistent) / span_days * 7, 2)

    return {
        "persistent_runs": len(persistent),
        "runs_per_week": runs_per_week,
        "best_min_sum_ask": min(r["min_sum_ask"] for r in persistent),
        "verdict": "CANDIDATE",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="research/data/polymarket_arb")
    parser.add_argument("--min-duration-sec", type=float, default=3.0)
    args = parser.parse_args()

    snapshots = load_snapshots(Path(args.data_dir))
    runs = find_opportunity_runs(snapshots)
    report = evaluate_runs(runs, min_duration_sec=args.min_duration_sec)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
