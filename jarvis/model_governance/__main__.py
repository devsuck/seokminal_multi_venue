"""`python -m jarvis.model_governance <cmd>` — 모델 거버넌스 CLI. **관리·감사 전용.**

  register  --model-id --name --model-type --task --owner [--description] [--commit]
  version   --model-id --version --framework [--params-json] [--commit]
  evaluate  --model-id --version --accuracy --sharpe --max-drawdown --stability --confidence [--commit]
  approve   --model-id --version --approver --decision {APPROVE,REJECT} [--rationale] [--commit]
  deploy    --model-id --version --environment --by [--note] [--commit]
  drift     --model-id --version --drift-type {FEATURE_DRIFT,PREDICTION_DRIFT,PERFORMANCE_DRIFT} --baseline --current [--commit]
  verify / summary / replay

모델 실행·학습·배포·거래 없음 — 등록/평가/승인/기록/drift 감사만.
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
    from jarvis.model_governance.engine import ModelGovernanceEngine
    return ModelGovernanceEngine()


def _cmd_register(a) -> int:
    d = _eng().register_model(a.model_id, a.name, a.description or "", a.model_type, a.task,
                              a.owner, _now(), commit=a.commit)
    _p({"committed": a.commit, "model": d.to_dict()})
    return 0


def _cmd_version(a) -> int:
    params = json.loads(a.params_json) if a.params_json else {}
    v = _eng().create_version(a.model_id, a.version, a.framework, params, _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "version": v.to_dict()})
    return 0


def _cmd_evaluate(a) -> int:
    from jarvis.model_governance.models import IllegalTransition
    try:
        r = _eng().record_evaluation(a.model_id, a.version, accuracy=a.accuracy, sharpe=a.sharpe,
                                     max_drawdown=a.max_drawdown, stability=a.stability,
                                     confidence_score=a.confidence, now=_now(), commit=a.commit)
    except IllegalTransition as e:
        _p({"error": str(e)})
        return 1
    _p({"committed": a.commit, "evaluation": r.to_dict()})
    return 0


def _cmd_approve(a) -> int:
    from jarvis.model_governance.models import ApprovalError, IllegalTransition
    try:
        r = _eng().approve_model(a.model_id, a.version, a.approver, a.decision, a.rationale or "",
                                 now=_now(), commit=a.commit)
    except (ApprovalError, IllegalTransition) as e:
        _p({"error": str(e)})
        return 1
    _p({"committed": a.commit, "approval": r.to_dict(), "note": "승인 기록만 — 실제 배포 아님"})
    return 0


def _cmd_deploy(a) -> int:
    from jarvis.model_governance.models import IllegalTransition
    try:
        r = _eng().record_deployment(a.model_id, a.version, a.environment, a.by, a.note or "",
                                     now=_now(), commit=a.commit)
    except IllegalTransition as e:
        _p({"error": str(e)})
        return 1
    _p({"committed": a.commit, "deployment": r.to_dict(),
        "note": "배포 후보 기록만 — 실제 배포/거래 없음"})
    return 0


def _cmd_drift(a) -> int:
    r = _eng().detect_model_drift(a.model_id, a.version, a.drift_type, baseline=a.baseline,
                                  current=a.current, now=_now(), commit=a.commit)
    _p({"committed": a.commit, "drift": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.model_governance.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().generate_governance_report(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.model_governance.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.model_governance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    for f in ("model-id", "name", "model-type", "task", "owner"):
        r.add_argument(f"--{f}", required=True)
    r.add_argument("--description", default="")
    r.add_argument("--commit", action="store_true")
    v = sub.add_parser("version")
    for f in ("model-id", "version", "framework"):
        v.add_argument(f"--{f}", required=True)
    v.add_argument("--params-json", default="{}")
    v.add_argument("--commit", action="store_true")
    e = sub.add_parser("evaluate")
    for f in ("model-id", "version"):
        e.add_argument(f"--{f}", required=True)
    for f in ("accuracy", "sharpe", "max-drawdown", "stability", "confidence"):
        e.add_argument(f"--{f}", type=float, default=0.0)
    e.add_argument("--commit", action="store_true")
    p = sub.add_parser("approve")
    for f in ("model-id", "version", "approver"):
        p.add_argument(f"--{f}", required=True)
    p.add_argument("--decision", required=True, choices=["APPROVE", "REJECT"])
    p.add_argument("--rationale", default="")
    p.add_argument("--commit", action="store_true")
    d = sub.add_parser("deploy")
    for f in ("model-id", "version", "environment", "by"):
        d.add_argument(f"--{f}", required=True)
    d.add_argument("--note", default="")
    d.add_argument("--commit", action="store_true")
    dr = sub.add_parser("drift")
    for f in ("model-id", "version", "drift-type"):
        dr.add_argument(f"--{f}", required=True)
    dr.add_argument("--baseline", type=float, default=0.0)
    dr.add_argument("--current", type=float, default=0.0)
    dr.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"register": _cmd_register, "version": _cmd_version, "evaluate": _cmd_evaluate,
            "approve": _cmd_approve, "deploy": _cmd_deploy, "drift": _cmd_drift,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
