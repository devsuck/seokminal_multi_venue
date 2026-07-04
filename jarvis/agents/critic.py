"""Critic / Red Team Agent — 유망 결과를 공격한다. config 변경 못 함.

결정적 휴리스틱으로 편향/약점 플래그 + 권고(reject/watchlist/paper_candidate).
승격 기준(스펙): net>0 · random>95pct · p<0.05 · WF 양쪽+ · not underpowered.
"""
from __future__ import annotations

import argparse
import json

from jarvis.agents import CRITIC_AGENT
from jarvis.permissions import require


def review(strategy_id: str, metrics: dict) -> dict:
    """백테스트 metrics 공격 → flags + recommendation."""
    require(CRITIC_AGENT, "critic_review", strategy_id)
    net = metrics.get("net")
    pct = metrics.get("random_percentile")
    p = metrics.get("empirical_p")
    wf1, wf2 = metrics.get("wf_first"), metrics.get("wf_second")
    powered = metrics.get("powered", True)

    flags = []
    if net is not None and net <= 0:
        flags.append("net_non_positive")
    if pct is not None and pct < 95:
        flags.append("random_below_95pct")
    if p is not None and p >= 0.05:
        flags.append("p_not_significant")
    if wf1 is not None and wf2 is not None and not (wf1 > 0 and wf2 > 0):
        flags.append("walk_forward_unstable")
    if not powered:
        flags.append("underpowered")

    passes = (net is not None and net > 0 and pct is not None and pct >= 95
              and p is not None and p < 0.05 and wf1 is not None and wf2 is not None
              and wf1 > 0 and wf2 > 0 and powered)
    weak = (net is not None and net > 0 and pct is not None and pct >= 80)
    if passes:
        rec = "paper_candidate"
    elif weak:
        rec = "watchlist"
    else:
        rec = "rejected"

    return {"strategy_id": strategy_id, "critic_flags": flags, "recommendation": rec,
            "required_forward_checks": ["entry_timing_feasibility", "cohort_distribution",
                                        "concentration_single_stock_year_sleeve"],
            "note": "Critic는 config를 바꾸지 않는다 — 권고만."}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.agents.critic")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("review")
    p.add_argument("--strategy", required=True)
    p.add_argument("--metrics", default="{}", help="JSON metrics")
    args = ap.parse_args(argv)
    if args.cmd == "review":
        print(json.dumps(review(args.strategy, json.loads(args.metrics)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
