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

from research import jsonl_dates


def load_snapshots(data_dir: Path) -> list[dict]:
    return jsonl_dates.iter_all_rows(Path(data_dir))


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


def find_opportunity_runs(snapshots: list[dict], max_gap_sec: float = 30.0) -> list[dict]:
    """condition_id별 시간순 정렬 후 연속된 is_opportunity=True 구간(run)을 찾는다.

    같은 market이라도 두 True 틱 사이 시간 간격이 max_gap_sec을 넘으면(컬렉터
    재시작·top-N 재선정으로 수집이 끊긴 구간) 별개 run으로 쪼갠다 — 안 그러면
    수집 공백까지 지속시간에 합산되어 거짓 CANDIDATE가 나온다.
    """
    by_market: dict[str, list[dict]] = defaultdict(list)
    for row in snapshots:
        by_market[row["condition_id"]].append(row)

    runs: list[dict] = []
    for condition_id, rows in by_market.items():
        rows.sort(key=lambda r: r["ts"])
        current: list[dict] = []
        for row in rows:
            if row["is_opportunity"]:
                if current:
                    gap = (dt.datetime.fromisoformat(row["ts"])
                           - dt.datetime.fromisoformat(current[-1]["ts"])).total_seconds()
                    if gap > max_gap_sec:
                        runs.append(_summarize_run(condition_id, current))
                        current = []
                current.append(row)
            else:
                if current:
                    runs.append(_summarize_run(condition_id, current))
                    current = []
        if current:
            runs.append(_summarize_run(condition_id, current))
    return runs


def evaluate_runs(runs: list[dict], min_duration_sec: float = 3.0, min_margin_usd: float = 0.0) -> dict:
    """지속성(min_duration_sec) x 순마진(min_margin_usd) 2축 게이트 — 빈도(축3)는
    수집 데이터를 실제로 본 뒤 정하는 판단이라(스펙 명시) 여기선 강제하지 않고 보고만 한다."""
    persistent = [r for r in runs if r["duration_sec"] >= min_duration_sec]
    if not persistent:
        return {
            "persistent_runs": 0, "margin_qualified_runs": 0, "runs_per_week": 0.0,
            "best_min_sum_ask": None, "best_max_capturable_margin_usd": None,
            "verdict": "REJECT_NO_PERSISTENT_RUNS",
        }

    best_margin = max(r["max_capturable_margin_usd"] for r in persistent)
    margin_qualified = [r for r in persistent if r["max_capturable_margin_usd"] > min_margin_usd]
    if not margin_qualified:
        return {
            "persistent_runs": len(persistent), "margin_qualified_runs": 0, "runs_per_week": 0.0,
            "best_min_sum_ask": min(r["min_sum_ask"] for r in persistent),
            "best_max_capturable_margin_usd": best_margin,
            "verdict": "REJECT_NO_POSITIVE_MARGIN",
        }

    start_times = [dt.datetime.fromisoformat(r["start_ts"]) for r in margin_qualified]
    span_days = max((max(start_times) - min(start_times)).total_seconds() / 86400, 1.0)
    runs_per_week = round(len(margin_qualified) / span_days * 7, 2)

    return {
        "persistent_runs": len(persistent),
        "margin_qualified_runs": len(margin_qualified),
        "runs_per_week": runs_per_week,
        "best_min_sum_ask": min(r["min_sum_ask"] for r in margin_qualified),
        "best_max_capturable_margin_usd": best_margin,
        "verdict": "CANDIDATE",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="research/data/polymarket_arb")
    parser.add_argument("--min-duration-sec", type=float, default=3.0)
    parser.add_argument("--min-margin-usd", type=float, default=0.0)
    parser.add_argument("--max-gap-sec", type=float, default=30.0)
    args = parser.parse_args()

    snapshots = load_snapshots(Path(args.data_dir))
    runs = find_opportunity_runs(snapshots, max_gap_sec=args.max_gap_sec)
    report = evaluate_runs(runs, min_duration_sec=args.min_duration_sec, min_margin_usd=args.min_margin_usd)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
