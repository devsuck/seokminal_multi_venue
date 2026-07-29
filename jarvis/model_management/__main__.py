"""`python -m jarvis.model_management <cmd>` — 모델 관리 CLI. **라이브 배포 없음.**

  model     --name --type                                  모델 등록(REGISTERED) [--commit]
  version   --model --version [--framework]                모델 버전 [--commit]
  validate  --model --check [--passed --score]             검증 결과 [--commit]
  perf      --model --metric --value [--dataset]           성능 이력 [--commit]
  metadata  --model --key --value                          메타 [--commit]
  compare   --model-a --model-b                            모델 비교
  report [--scope] / verify / summary / replay

라이브 배포·거래·실행·자본 배분 없음. MANAGED ≠ DEPLOYED · AVAILABLE_FOR_RESEARCH ≠ LIVE.
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
    from jarvis.model_management.engine import ModelManagementEngine
    return ModelManagementEngine()


def _cmd_model(a) -> int:
    _p({"committed": a.commit,
        "model": _eng().register_model(a.name, a.type, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_version(a) -> int:
    _p({"committed": a.commit,
        "version": _eng().create_version(a.model, a.version, {"v": a.version}, a.framework or "",
                                       _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_validate(a) -> int:
    _p({"committed": a.commit,
        "validation": _eng().validate_model(a.model, a.check, a.passed, a.score, "", "", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_perf(a) -> int:
    _p({"committed": a.commit,
        "performance": _eng().record_performance(a.model, a.metric, a.value, a.dataset or "", "",
                                               _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_metadata(a) -> int:
    _p({"committed": a.commit,
        "metadata": _eng().record_metadata(a.model, a.key, a.value, _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_compare(a) -> int:
    _p(_eng().compare_models(a.model_a, a.model_b))
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.model_management.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.model_management.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.model_management")
    sub = ap.add_subparsers(dest="cmd", required=True)

    mo = sub.add_parser("model")
    mo.add_argument("--name", required=True)
    mo.add_argument("--type", required=True)
    mo.add_argument("--commit", action="store_true")

    ve = sub.add_parser("version")
    ve.add_argument("--model", required=True)
    ve.add_argument("--version", required=True)
    ve.add_argument("--framework", default="")
    ve.add_argument("--commit", action="store_true")

    va = sub.add_parser("validate")
    va.add_argument("--model", required=True)
    va.add_argument("--check", required=True)
    va.add_argument("--passed", action="store_true")
    va.add_argument("--score", type=float, default=1.0)
    va.add_argument("--commit", action="store_true")

    pe = sub.add_parser("perf")
    pe.add_argument("--model", required=True)
    pe.add_argument("--metric", required=True)
    pe.add_argument("--value", type=float, required=True)
    pe.add_argument("--dataset", default="")
    pe.add_argument("--commit", action="store_true")

    md = sub.add_parser("metadata")
    md.add_argument("--model", required=True)
    md.add_argument("--key", required=True)
    md.add_argument("--value", required=True)
    md.add_argument("--commit", action="store_true")

    co = sub.add_parser("compare")
    co.add_argument("--model-a", dest="model_a", required=True)
    co.add_argument("--model-b", dest="model_b", required=True)

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"model": _cmd_model, "version": _cmd_version, "validate": _cmd_validate,
            "perf": _cmd_perf, "metadata": _cmd_metadata, "compare": _cmd_compare,
            "report": _cmd_report, "verify": _cmd_verify, "summary": _cmd_summary,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
