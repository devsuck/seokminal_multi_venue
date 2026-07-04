"""Lv2 — 리서치 큐. 스케줄 Claude Code(CLI, API키 0)가 가설 스펙을 여기 기록.

결정적 ingest 가드:
- dedup: 이미 registry에 있는 id 거부(재검 = 새 버전 id로).
- Market Memory consult: 거부된 family와 유사하면 differentiation 필수(없으면 거부).
- rate cap: 한 배치 최대 N개(스프레이 방지, BH-FDR 예산과 함께).
run_pending()이 pending을 run_batch로 검증(BH-FDR) 후 processed로 이동.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from jarvis.config import state_path
from jarvis.memory import MarketMemory, seed_lessons

_PENDING = "research_pending.jsonl"
_PROCESSED = "research_processed.jsonl"
MAX_BATCH = 25   # 한 실행 최대 가설수(스프레이 방지)


def _read(name: str) -> list[dict]:
    p = state_path(name)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _append(name: str, row: dict) -> None:
    os.makedirs(os.path.dirname(state_path(name)), exist_ok=True)
    with open(state_path(name), "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _rewrite(name: str, rows: list[dict]) -> None:
    with open(state_path(name), "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def pending() -> list[dict]:
    return _read(_PENDING)


def processed() -> list[dict]:
    return _read(_PROCESSED)


def submit(spec: dict, source: str = "scheduled_cli") -> dict:
    """가설 스펙 제출. 가드 통과 시 pending에 추가."""
    sid = spec.get("id")
    if not sid or not spec.get("name"):
        return {"accepted": False, "reason": "missing_id_or_name"}

    from jarvis.registry import StrategyRegistry
    if StrategyRegistry().state(sid) is not None:
        return {"accepted": False, "reason": "already_tested_in_registry", "strategy_id": sid}
    if any(p.get("id") == sid for p in pending()):
        return {"accepted": False, "reason": "duplicate_in_queue", "strategy_id": sid}

    # Market Memory consult — 명시 keywords로만(family/market은 너무 광범위).
    # 거부 family와 유사하면 differentiation 필수.
    mem = MarketMemory()
    seed_lessons(mem)
    kws = [k for k in spec.get("keywords", []) if k]
    similar = mem.consult(kws) if kws else []
    if similar and not spec.get("differentiation"):
        return {"accepted": False, "reason": "similar_rejected_needs_differentiation",
                "strategy_id": sid, "similar": [s["lesson_id"] for s in similar]}

    row = {**spec, "_source": source, "_similar": [s["lesson_id"] for s in similar],
           "_submitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _append(_PENDING, row)
    return {"accepted": True, "strategy_id": sid, "similar": [s["lesson_id"] for s in similar]}


def run_pending(alpha: float = 0.1, auto_deploy: bool = True, cap: int = MAX_BATCH) -> dict:
    """pending 가설을 run_batch(BH-FDR)로 검증 후 processed로 이동."""
    from jarvis.pipeline import run_batch
    q = pending()
    if not q:
        return {"ran": 0, "report": None, "capped": False}
    batch = q[:cap]
    specs = [{k: v for k, v in s.items() if not k.startswith("_")} for s in batch]
    report = run_batch(specs, alpha=alpha, auto_deploy=auto_deploy)

    final_by = {d["strategy_id"]: d["final"] for d in report["decisions"]}
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for s in batch:
        _append(_PROCESSED, {**s, "_final": final_by.get(s.get("id")), "_processed_at": ts})
    _rewrite(_PENDING, q[cap:])   # 처리분 제거, 초과분 유지
    return {"ran": len(batch), "capped": len(q) > cap, "report": report}


def generate_stub(topic: str, n: int = 3) -> list[dict]:
    """LLM 없는 결정적 템플릿 생성기(스켈레톤). 스케줄 Claude Code가 이걸 대체/증강.

    ⚠️ 실제 아이디어 생성은 Claude Code(CLI)가 담당. 이건 파이프 동작확인용 더미."""
    base = topic.lower().replace(" ", "_")[:20]
    return [{"id": f"gen_{base}_{i}", "name": f"{topic} v{i}", "family": "event",
             "market": "KR", "thesis": f"[stub] {topic} 가설 {i}",
             "required_data": ["daily_ohlcv", "market_cap", "disclosure_event_dates"],
             "edge_bps": 0.0, "n_trades": 40, "hold": 20, "cost_bps": 40.0, "seed": 1000 + i,
             "note": "stub — 스케줄 Claude Code가 실제 아이디어로 교체"}
            for i in range(n)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_queue")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit"); s.add_argument("--spec", required=True, help="스펙 JSON 파일 or inline")
    sub.add_parser("list")
    r = sub.add_parser("run"); r.add_argument("--alpha", type=float, default=0.1)
    args = ap.parse_args(argv)

    if args.cmd == "submit":
        raw = open(args.spec).read() if os.path.exists(args.spec) else args.spec
        data = json.loads(raw)
        specs = data if isinstance(data, list) else [data]
        print(json.dumps([submit(sp) for sp in specs], ensure_ascii=False, indent=2))
    elif args.cmd == "list":
        print(json.dumps({"pending": len(pending()), "processed": len(processed()),
                          "pending_ids": [p.get("id") for p in pending()]}, ensure_ascii=False, indent=2))
    elif args.cmd == "run":
        res = run_pending(alpha=args.alpha)
        print(json.dumps({"ran": res["ran"], "capped": res["capped"],
                          "decisions": res["report"]["decisions"] if res["report"] else []},
                         ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
