"""`python -m jarvis.data_infrastructure <cmd>` — 실데이터 인프라 CLI. **거래 연결 없음.**

  source   --type --name [--uri --desc]                    데이터 소스 등록 [--commit]
  dataset  --name [--source]                               데이터셋 생성(CREATED) [--commit]
  version  --dataset --version [--rows]                    데이터셋 버전(해시·계보) [--commit]
  feature  --dataset --name --features                     피처셋 준비 [--commit]
  quality  --dataset --dimension --score [--passed]        품질 리포트 [--commit]
  report [--scope] / verify / summary / replay

거래·실행·배포·자본 배분 없음. DATA ≠ TRADING · METADATA ≠ EXECUTION.
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
    from jarvis.data_infrastructure.engine import DataInfrastructureEngine
    return DataInfrastructureEngine()


def _split(s):
    return [x for x in (s or "").split("|") if x]


def _cmd_source(a) -> int:
    _p({"committed": a.commit,
        "source": _eng().register_source(a.type, a.name, a.uri or "", a.desc or "", _now(),
                                       commit=a.commit).to_dict()})
    return 0


def _cmd_dataset(a) -> int:
    _p({"committed": a.commit,
        "dataset": _eng().create_dataset(a.name, a.source or "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_version(a) -> int:
    _p({"committed": a.commit,
        "version": _eng().create_version(a.dataset, a.version, {"v": a.version}, a.rows, {}, _now(),
                                       commit=a.commit).to_dict()})
    return 0


def _cmd_feature(a) -> int:
    _p({"committed": a.commit,
        "feature_set": _eng().prepare_features(a.dataset, a.name, _split(a.features), "", "", _now(),
                                             commit=a.commit).to_dict()})
    return 0


def _cmd_quality(a) -> int:
    _p({"committed": a.commit,
        "quality": _eng().record_quality(a.dataset, a.dimension, a.score, a.passed, [], "", _now(),
                                       commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.data_infrastructure.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.data_infrastructure.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.data_infrastructure")
    sub = ap.add_subparsers(dest="cmd", required=True)

    so = sub.add_parser("source")
    so.add_argument("--type", required=True)
    so.add_argument("--name", required=True)
    so.add_argument("--uri", default="")
    so.add_argument("--desc", default="")
    so.add_argument("--commit", action="store_true")

    ds = sub.add_parser("dataset")
    ds.add_argument("--name", required=True)
    ds.add_argument("--source", default="")
    ds.add_argument("--commit", action="store_true")

    ve = sub.add_parser("version")
    ve.add_argument("--dataset", required=True)
    ve.add_argument("--version", required=True)
    ve.add_argument("--rows", type=int, default=0)
    ve.add_argument("--commit", action="store_true")

    fe = sub.add_parser("feature")
    fe.add_argument("--dataset", required=True)
    fe.add_argument("--name", required=True)
    fe.add_argument("--features", default="")
    fe.add_argument("--commit", action="store_true")

    qu = sub.add_parser("quality")
    qu.add_argument("--dataset", required=True)
    qu.add_argument("--dimension", required=True)
    qu.add_argument("--score", type=float, required=True)
    qu.add_argument("--passed", action="store_true")
    qu.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"source": _cmd_source, "dataset": _cmd_dataset, "version": _cmd_version,
            "feature": _cmd_feature, "quality": _cmd_quality, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
