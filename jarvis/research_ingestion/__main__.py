"""`python -m jarvis.research_ingestion <cmd>` — 연구 데이터 파이프라인 CLI. **실행 없음.**

  ingest --file backtest.json [--commit]    백테스트 JSON 1건 수집
  validate --file backtest.json             스키마·검증지표 확인
  summary / verify / replay

기존 원장(expt_/rmi_)에 기록만. 거래·집행 없음. 멱등.
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
    from jarvis.research_ingestion.engine import ResearchIngestionEngine
    return ResearchIngestionEngine()


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _cmd_ingest(a) -> int:
    _p({"committed": a.commit, "result": _eng().ingest(_load(a.file), _now(),
                                                       commit=a.commit).to_dict()})
    return 0


def _cmd_validate(a) -> int:
    _p(_eng().validate(_load(a.file)))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_ingestion.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_ingestion.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_ingestion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest")
    ing.add_argument("--file", required=True)
    ing.add_argument("--commit", action="store_true")
    va = sub.add_parser("validate")
    va.add_argument("--file", required=True)
    for name in ("summary", "verify", "replay"):
        sub.add_parser(name)
    args = ap.parse_args(argv)
    disp = {"ingest": _cmd_ingest, "validate": _cmd_validate, "summary": _cmd_summary,
            "verify": _cmd_verify, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
