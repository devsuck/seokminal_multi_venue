"""Research Agent — 가설 생성/랭킹/v2 제안. LLM은 CLI(Claude Code)가 담당, 여기선 구조화.

권한: RESEARCH_ONLY. 등록·감사만 하고 실행/승격 못 함.
Market Memory를 먼저 consult → 유사 거부사례 있으면 differentiation 요구.
"""
from __future__ import annotations

import argparse
import json

from jarvis.agents import RESEARCH_AGENT
from jarvis.memory import MarketMemory, seed_lessons
from jarvis.permissions import require
from jarvis.registry import StrategyRegistry


def propose(strategy_id: str, name: str, rationale: str, required_data: list[str],
            expected_edge_type: str, known_risks: list[str],
            keywords: list[str] | None = None, register: bool = True) -> dict:
    """구조화 가설 초안. Market Memory consult 포함. draft로 등록."""
    require(RESEARCH_AGENT, "create_strategy_hypothesis", strategy_id)
    mem = MarketMemory()
    seed_lessons(mem)
    similar = mem.consult(keywords or [strategy_id, expected_edge_type])
    draft = {
        "hypothesis_id": strategy_id, "name": name, "rationale": rationale,
        "required_data": required_data, "expected_edge_type": expected_edge_type,
        "known_risks": known_risks,
        "similar_rejected": [s["lesson_id"] for s in similar],
        "differentiation_required": bool(similar),
        "next_action": "data_gate",
    }
    if register:
        reg = StrategyRegistry()
        if reg.state(strategy_id) is None:
            reg.register(strategy_id, name=name, config={"rationale": rationale, "edge_type": expected_edge_type})
    return draft


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.agents.research")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose")
    p.add_argument("--id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--topic", default="")
    p.add_argument("--edge", default="event")
    args = ap.parse_args(argv)
    if args.cmd == "propose":
        d = propose(args.id, args.name, rationale=args.topic or args.name,
                    required_data=["daily_ohlcv", "market_cap", "event_dates"],
                    expected_edge_type=args.edge, known_risks=["small_sample", "crowded"],
                    keywords=[args.topic, args.edge])
        print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
