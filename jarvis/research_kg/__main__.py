"""`python -m jarvis.research_kg <cmd>` — 연구 지식 그래프 CLI. **분석·검색 전용.**

  entity     --entity-type --source-layer --source-id [--commit]
  link       --source --rel-type --target [--commit]
  lineage    [--commit]                    # 관계로부터 정방향 계보 파생
  similarity --entity-a --entity-b --score [--basis] [--commit]
  snapshot   [--commit]
  ingest     [--limit N] [--commit]        # 상위 레이어 READ ONLY 스캔→엔티티 등록
  report / verify / summary / replay

실제 실행·배포·주문·자본배분·모델적용 없음 — 그래프 기록·분석만. CONNECTED ≠ ENABLED.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _eng():
    from jarvis.research_kg.engine import ResearchKnowledgeGraphEngine
    return ResearchKnowledgeGraphEngine()


def _cmd_entity(a) -> int:
    e = _eng().register_entity(a.entity_type, a.source_layer, a.source_id, {}, _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "entity": e.to_dict(), "note": "그래프 노드 — 배포/적용 아님"})
    return 0


def _cmd_link(a) -> int:
    r = _eng().link_relationship(a.source, a.rel_type, a.target, _now(), commit=a.commit)
    _p({"committed": a.commit, "relationship": r.to_dict(), "note": "CONNECTED ≠ ENABLED"})
    return 0


def _cmd_lineage(a) -> int:
    edges = _eng().build_lineage(_now(), commit=a.commit)
    _p({"committed": a.commit, "lineage_edges": [e.to_dict() for e in edges]})
    return 0


def _cmd_similarity(a) -> int:
    r = _eng().analyze_similarity(a.entity_a, a.entity_b, a.score, a.basis or "", _now(),
                                  commit=a.commit)
    _p({"committed": a.commit, "similarity": r.to_dict(), "note": "서술적 라벨 — 자동 선택 아님"})
    return 0


def _cmd_snapshot(a) -> int:
    s = _eng().snapshot_graph(_now(), commit=a.commit)
    _p({"committed": a.commit, "snapshot": s.to_dict()})
    return 0


def _cmd_ingest(a) -> int:
    counts = _eng().ingest_from_sources(_now(), commit=a.commit, limit=a.limit)
    _p({"committed": a.commit, "registered": counts, "note": "상위 레이어 READ ONLY 스캔"})
    return 0


def _cmd_report(a) -> int:
    _p(_eng().generate_graph_report(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_kg.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_kg.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_kg")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("entity")
    for f in ("entity-type", "source-layer", "source-id"):
        e.add_argument(f"--{f}", required=True)
    e.add_argument("--commit", action="store_true")
    lk = sub.add_parser("link")
    for f in ("source", "rel-type", "target"):
        lk.add_argument(f"--{f}", required=True)
    lk.add_argument("--commit", action="store_true")
    ln = sub.add_parser("lineage")
    ln.add_argument("--commit", action="store_true")
    si = sub.add_parser("similarity")
    si.add_argument("--entity-a", required=True)
    si.add_argument("--entity-b", required=True)
    si.add_argument("--score", type=float, required=True)
    si.add_argument("--basis", default="")
    si.add_argument("--commit", action="store_true")
    sn = sub.add_parser("snapshot")
    sn.add_argument("--commit", action="store_true")
    ig = sub.add_parser("ingest")
    ig.add_argument("--limit", type=int, default=0)
    ig.add_argument("--commit", action="store_true")
    sub.add_parser("report")
    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"entity": _cmd_entity, "link": _cmd_link, "lineage": _cmd_lineage,
            "similarity": _cmd_similarity, "snapshot": _cmd_snapshot, "ingest": _cmd_ingest,
            "report": _cmd_report, "verify": _cmd_verify, "summary": _cmd_report,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
