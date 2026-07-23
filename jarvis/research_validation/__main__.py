"""`python -m jarvis.research_validation <cmd>` — 연구 검증·재현성 거버넌스 CLI. **평가 기록 전용.**

  validate  --target-layer --target-id [--type --session-ref] [--commit]
  checklist --validation-id --items-json [--commit]
  replay    --validation-id --inputs-json --metadata-json --seed [--original-hash] [--commit]
  lineage   --validation-id --target-layer [--commit]
  score     --validation-id [--components-json] [--commit]
  report / verify / summary

실제 실행·배포·자본배분·권한/config/autonomy 변경 없음 — 연구 품질 평가·기록만.
VALIDATED ≠ APPROVED · VALIDATED ≠ DEPLOYABLE · score ≠ approval.
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
    from jarvis.research_validation.engine import ResearchValidationEngine
    return ResearchValidationEngine()


def _cmd_validate(a) -> int:
    v = _eng().register_validation(a.target_layer, a.target_id, a.type, a.session_ref or "",
                                   _now(), commit=a.commit)
    _p({"committed": a.commit, "validation": v.to_dict(), "note": "VALIDATED ≠ APPROVED"})
    return 0


def _cmd_checklist(a) -> int:
    items = json.loads(a.items_json)
    c = _eng().evaluate_checklist(a.validation_id, items, _now(), commit=a.commit)
    _p({"committed": a.commit, "checklist": c.to_dict(), "note": "자동 수정 없음 — 라벨만"})
    return 0


def _cmd_replay(a) -> int:
    inputs = json.loads(a.inputs_json) if a.inputs_json else {}
    metadata = json.loads(a.metadata_json) if a.metadata_json else {}
    r = _eng().verify_replay(a.validation_id, inputs, metadata, a.seed, a.original_hash or "",
                             _now(), commit=a.commit)
    _p({"committed": a.commit, "replay": r.to_dict()})
    return 0


def _cmd_lineage(a) -> int:
    l = _eng().validate_lineage(a.validation_id, a.target_layer, _now(), commit=a.commit)
    _p({"committed": a.commit, "lineage_report": l.to_dict()})
    return 0


def _cmd_score(a) -> int:
    components = json.loads(a.components_json) if a.components_json else None
    s = _eng().compute_validation_score(a.validation_id, components, _now(), commit=a.commit)
    _p({"committed": a.commit, "score": s.to_dict(), "note": "score ≠ approval · score ≠ deployment"})
    return 0


def _cmd_report(a) -> int:
    _p(_eng().generate_audit_summary(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_validation.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_validation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    vd = sub.add_parser("validate")
    vd.add_argument("--target-layer", required=True)
    vd.add_argument("--target-id", required=True)
    vd.add_argument("--type", default="FULL")
    vd.add_argument("--session-ref", default="")
    vd.add_argument("--commit", action="store_true")
    ck = sub.add_parser("checklist")
    ck.add_argument("--validation-id", required=True)
    ck.add_argument("--items-json", required=True)
    ck.add_argument("--commit", action="store_true")
    rp = sub.add_parser("replay")
    rp.add_argument("--validation-id", required=True)
    rp.add_argument("--inputs-json", default="")
    rp.add_argument("--metadata-json", default="")
    rp.add_argument("--seed", default="0")
    rp.add_argument("--original-hash", default="")
    rp.add_argument("--commit", action="store_true")
    ln = sub.add_parser("lineage")
    ln.add_argument("--validation-id", required=True)
    ln.add_argument("--target-layer", required=True)
    ln.add_argument("--commit", action="store_true")
    sc = sub.add_parser("score")
    sc.add_argument("--validation-id", required=True)
    sc.add_argument("--components-json", default="")
    sc.add_argument("--commit", action="store_true")
    sub.add_parser("report")
    sub.add_parser("summary")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    disp = {"validate": _cmd_validate, "checklist": _cmd_checklist, "replay": _cmd_replay,
            "lineage": _cmd_lineage, "score": _cmd_score, "report": _cmd_report,
            "summary": _cmd_report, "verify": _cmd_verify}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
