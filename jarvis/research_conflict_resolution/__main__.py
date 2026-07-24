"""`python -m jarvis.research_conflict_resolution <cmd>` — 연구 충돌 분석·해소 CLI. **리뷰·분석 전용.**

  registry  --name [--mandate]                         레지스트리 등록 [--commit]
  conflict  --registry --subject [--desc]              충돌 등록(DETECTED) [--commit]
  analyze   --conflict                                 DETECTED→ANALYZING [--commit]
  claim     --conflict --agent --conclusion [--rationale]  주장 추가 [--commit]
  evidence  --claim --layer --ref --type [--detail]    증거 첨부 [--commit]
  position  --conflict --agent --claim [--rationale]   에이전트 포지션 [--commit]
  compare   --conflict                                 주장 비교 분석
  resolve-start --conflict [--facilitator]             해소 세션(→DISCUSSING) [--commit]
  resolve   --conflict --session --type [--winning --rationale]  해소 결과 [--commit]
  minority  --conflict --winning                       소수의견 자동 보존 [--commit]
  report    --conflict / conflicts / verify / replay / summary

실제 실행·승인·연구결과 수정 없음 — 충돌 기록·분석만.
CONFLICT ≠ EXECUTION · RESOLUTION ≠ APPROVAL · CONSENSUS ≠ DEPLOYMENT.
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
    from jarvis.research_conflict_resolution.engine import ResearchConflictResolutionEngine
    return ResearchConflictResolutionEngine()


def _cmd_registry(a) -> int:
    _p({"committed": a.commit,
        "registry": _eng().register_registry(a.name, a.mandate or "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_conflict(a) -> int:
    _p({"committed": a.commit,
        "conflict": _eng().register_conflict(a.registry, a.subject, a.desc or "", _now(),
                                             commit=a.commit).to_dict()})
    return 0


def _cmd_analyze(a) -> int:
    _p({"committed": a.commit,
        "conflict": _eng().start_analysis(a.conflict, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_claim(a) -> int:
    _p({"committed": a.commit,
        "claim": _eng().add_claim(a.conflict, a.agent, a.conclusion, a.rationale or "", _now(),
                                  commit=a.commit).to_dict()})
    return 0


def _cmd_evidence(a) -> int:
    _p({"committed": a.commit,
        "evidence": _eng().attach_evidence(a.claim, a.layer, a.ref, a.type, a.detail or "", _now(),
                                           commit=a.commit).to_dict()})
    return 0


def _cmd_position(a) -> int:
    _p({"committed": a.commit,
        "position": _eng().record_agent_position(a.conflict, a.agent, a.claim, a.rationale or "",
                                                 _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_compare(a) -> int:
    _p(_eng().compare_claims(a.conflict))
    return 0


def _cmd_resolve_start(a) -> int:
    _p({"committed": a.commit,
        "session": _eng().start_resolution(a.conflict, a.facilitator or "", "analysis", _now(),
                                           commit=a.commit).to_dict()})
    return 0


def _cmd_resolve(a) -> int:
    _p({"committed": a.commit,
        "outcome": _eng().record_resolution(a.conflict, a.session, a.type, a.winning or "",
                                            a.rationale or "", _now(), commit=a.commit).to_dict(),
        "note": "RESOLUTION ≠ APPROVAL"})
    return 0


def _cmd_minority(a) -> int:
    ms = _eng().preserve_all_minority(a.conflict, a.winning, _now(), commit=a.commit)
    _p({"committed": a.commit, "minority": [m.to_dict() for m in ms]})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.conflict, "CONFLICT", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_conflicts(a) -> int:
    _p({"conflicts": _eng().list_conflicts(a.registry or "")})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_conflict_resolution.verify import verify_chain
    res = verify_chain(check_minority=True)
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_conflict_resolution.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_conflict_resolution")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rg = sub.add_parser("registry")
    rg.add_argument("--name", required=True)
    rg.add_argument("--mandate", default="")
    rg.add_argument("--commit", action="store_true")
    cf = sub.add_parser("conflict")
    cf.add_argument("--registry", required=True)
    cf.add_argument("--subject", required=True)
    cf.add_argument("--desc", default="")
    cf.add_argument("--commit", action="store_true")
    an = sub.add_parser("analyze")
    an.add_argument("--conflict", required=True)
    an.add_argument("--commit", action="store_true")
    cl = sub.add_parser("claim")
    cl.add_argument("--conflict", required=True)
    cl.add_argument("--agent", required=True)
    cl.add_argument("--conclusion", required=True)
    cl.add_argument("--rationale", default="")
    cl.add_argument("--commit", action="store_true")
    ev = sub.add_parser("evidence")
    ev.add_argument("--claim", required=True)
    ev.add_argument("--layer", required=True)
    ev.add_argument("--ref", required=True)
    ev.add_argument("--type", required=True)
    ev.add_argument("--detail", default="")
    ev.add_argument("--commit", action="store_true")
    po = sub.add_parser("position")
    po.add_argument("--conflict", required=True)
    po.add_argument("--agent", required=True)
    po.add_argument("--claim", required=True)
    po.add_argument("--rationale", default="")
    po.add_argument("--commit", action="store_true")
    cm = sub.add_parser("compare")
    cm.add_argument("--conflict", required=True)
    rs = sub.add_parser("resolve-start")
    rs.add_argument("--conflict", required=True)
    rs.add_argument("--facilitator", default="")
    rs.add_argument("--commit", action="store_true")
    rv = sub.add_parser("resolve")
    rv.add_argument("--conflict", required=True)
    rv.add_argument("--session", required=True)
    rv.add_argument("--type", required=True,
                    choices=["CONSENSUS", "MAJORITY", "EVIDENCE_SUPERIOR", "UNRESOLVED"])
    rv.add_argument("--winning", default="")
    rv.add_argument("--rationale", default="")
    rv.add_argument("--commit", action="store_true")
    mi = sub.add_parser("minority")
    mi.add_argument("--conflict", required=True)
    mi.add_argument("--winning", required=True)
    mi.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--conflict", required=True)
    rp.add_argument("--commit", action="store_true")
    cs = sub.add_parser("conflicts")
    cs.add_argument("--registry", default="")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"registry": _cmd_registry, "conflict": _cmd_conflict, "analyze": _cmd_analyze,
            "claim": _cmd_claim, "evidence": _cmd_evidence, "position": _cmd_position,
            "compare": _cmd_compare, "resolve-start": _cmd_resolve_start, "resolve": _cmd_resolve,
            "minority": _cmd_minority, "report": _cmd_report, "conflicts": _cmd_conflicts,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
