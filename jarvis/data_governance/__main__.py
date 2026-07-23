"""`python -m jarvis.data_governance <cmd>` — 데이터 거버넌스 CLI. **거버넌스 전용.**

  register  --dataset-id --name --source --asset-class --owner [--description] [--commit]
  schema    --dataset-id --version --columns-json [--commit]   (컬럼={"col":"type"})
  lineage   --dataset-id --parent --operation --version [--transformation] [--commit]
  quality   --dataset-id --missing --duplicate --null [--schema-mismatch] [--stale] [--commit]
  verify
  summary
  replay    [--dataset-id]

실행/거래/브로커/리스크/포트폴리오 변경 없음 — 데이터 거버넌스·계보·품질만.
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
    from jarvis.data_governance.engine import DataGovernanceEngine
    d = DataGovernanceEngine().register_dataset(
        a.dataset_id, a.name, a.description or "", a.source, a.asset_class, a.owner,
        _now(), commit=a.commit)
    _p({"committed": a.commit, "dataset": d.to_dict()})
    return 0


def _cmd_schema(a) -> int:
    from jarvis.data_governance.engine import DataGovernanceEngine
    cols = json.loads(a.columns_json)
    s = DataGovernanceEngine().register_schema(a.dataset_id, a.version, cols, _now(),
                                               commit=a.commit)
    _p({"committed": a.commit, "schema": s.to_dict()})
    return 0


def _cmd_lineage(a) -> int:
    from jarvis.data_governance.engine import DataGovernanceEngine
    from jarvis.data_governance.models import LineageError
    try:
        lr = DataGovernanceEngine().record_lineage(
            a.dataset_id, a.parent, a.operation, a.transformation or "", a.version, _now(),
            require_parent=False, commit=a.commit)
    except LineageError as e:
        _p({"error": str(e)})
        return 1
    _p({"committed": a.commit, "lineage": lr.to_dict()})
    return 0


def _cmd_quality(a) -> int:
    from jarvis.data_governance.engine import DataGovernanceEngine
    checks = {"missing_ratio": a.missing, "duplicate_ratio": a.duplicate,
              "null_ratio": a.null, "schema_mismatch": a.schema_mismatch,
              "stale_timestamp": a.stale, "unexpected_columns": [],
              "row_count_anomaly": False, "source_consistent": True}
    r = DataGovernanceEngine().validate_quality(a.dataset_id, _now(), checks=checks,
                                                commit=a.commit)
    _p({"committed": a.commit, "quality": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.data_governance.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    from jarvis.data_governance.engine import DataGovernanceEngine
    _p(DataGovernanceEngine().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.data_governance.engine import DataGovernanceEngine
    from jarvis.data_governance.verify import replay
    _p(replay(DataGovernanceEngine(), a.dataset_id or "", _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.data_governance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    for f in ("dataset-id", "name", "source", "asset-class", "owner"):
        r.add_argument(f"--{f}", required=True)
    r.add_argument("--description", default="")
    r.add_argument("--commit", action="store_true")
    s = sub.add_parser("schema")
    s.add_argument("--dataset-id", required=True)
    s.add_argument("--version", required=True)
    s.add_argument("--columns-json", required=True)
    s.add_argument("--commit", action="store_true")
    ln = sub.add_parser("lineage")
    ln.add_argument("--dataset-id", required=True)
    ln.add_argument("--parent", required=True)
    ln.add_argument("--operation", required=True)
    ln.add_argument("--transformation", default="")
    ln.add_argument("--version", required=True)
    ln.add_argument("--commit", action="store_true")
    q = sub.add_parser("quality")
    q.add_argument("--dataset-id", required=True)
    q.add_argument("--missing", type=float, default=0.0)
    q.add_argument("--duplicate", type=float, default=0.0)
    q.add_argument("--null", type=float, default=0.0)
    q.add_argument("--schema-mismatch", action="store_true")
    q.add_argument("--stale", action="store_true")
    q.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("summary")
    rp = sub.add_parser("replay")
    rp.add_argument("--dataset-id", default="")
    args = ap.parse_args(argv)
    disp = {"register": _cmd_register, "schema": _cmd_schema, "lineage": _cmd_lineage,
            "quality": _cmd_quality, "verify": _cmd_verify, "summary": _cmd_summary,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
