"""`python -m jarvis.research_data <cmd>` — 연구 데이터 거버넌스 CLI. **연구 관리 전용.**

  register  --dataset-id --name --asset-class --source --frequency --schema-version --owner [옵션] [--commit]
  quality   --dataset-id --missing --duplicate --outliers [--schema-invalid] [--ts-broken] [--commit]
  lineage   --dataset-id --parent --transformation --version [--commit]
  snapshot  [--commit]
  verify
  summary
  replay

전략 실행·주문·포트폴리오·브로커·live capital 없음 — 데이터 관리·감사만.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cmd_register(a) -> int:
    from jarvis.research_data.engine import ResearchDataEngine
    d = ResearchDataEngine().register_dataset(
        a.dataset_id, a.name, a.description or "", a.asset_class, a.source, a.frequency,
        a.coverage_start or "", a.coverage_end or "", a.schema_version, a.owner, _now(),
        commit=a.commit)
    _p({"committed": a.commit, "dataset": d.to_dict(), "note": "데이터셋 등록(불변 버전)"})
    return 0


def _cmd_quality(a) -> int:
    from jarvis.research_data.engine import ResearchDataEngine
    metrics = {"missing_ratio": a.missing, "duplicate_ratio": a.duplicate,
               "outlier_count": a.outliers, "schema_valid": not a.schema_invalid,
               "timestamp_continuity": not a.ts_broken}
    r = ResearchDataEngine().assess_quality(a.dataset_id, _now(), metrics=metrics,
                                            commit=a.commit)
    _p({"committed": a.commit, "quality": r.to_dict()})
    return 0


def _cmd_lineage(a) -> int:
    from jarvis.research_data.engine import ResearchDataEngine
    from jarvis.research_data.models import LineageError
    try:
        r = ResearchDataEngine().register_lineage(
            a.dataset_id, a.parent, a.transformation or "", a.version, _now(),
            require_parent=False, commit=a.commit)
    except LineageError as e:
        _p({"error": str(e)})
        return 1
    _p({"committed": a.commit, "lineage": r.to_dict()})
    return 0


def _cmd_snapshot(a) -> int:
    from jarvis.research_data.engine import ResearchDataEngine
    _p(ResearchDataEngine().snapshot(_now(), commit=a.commit).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_data.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    from jarvis.research_data.engine import ResearchDataEngine
    _p(ResearchDataEngine().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.research_data.engine import ResearchDataEngine
    from jarvis.research_data.verify import replay
    _p(replay(ResearchDataEngine(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    for f in ("dataset-id", "name", "asset-class", "source", "frequency",
              "schema-version", "owner"):
        r.add_argument(f"--{f}", required=True)
    for f in ("description", "coverage-start", "coverage-end"):
        r.add_argument(f"--{f}", default="")
    r.add_argument("--commit", action="store_true")
    q = sub.add_parser("quality")
    q.add_argument("--dataset-id", required=True)
    q.add_argument("--missing", type=float, default=0.0)
    q.add_argument("--duplicate", type=float, default=0.0)
    q.add_argument("--outliers", type=int, default=0)
    q.add_argument("--schema-invalid", action="store_true")
    q.add_argument("--ts-broken", action="store_true")
    q.add_argument("--commit", action="store_true")
    ln = sub.add_parser("lineage")
    ln.add_argument("--dataset-id", required=True)
    ln.add_argument("--parent", required=True)
    ln.add_argument("--transformation", default="")
    ln.add_argument("--version", required=True)
    ln.add_argument("--commit", action="store_true")
    for name in ("snapshot",):
        s = sub.add_parser(name)
        s.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"register": _cmd_register, "quality": _cmd_quality, "lineage": _cmd_lineage,
            "snapshot": _cmd_snapshot, "verify": _cmd_verify, "summary": _cmd_summary,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
