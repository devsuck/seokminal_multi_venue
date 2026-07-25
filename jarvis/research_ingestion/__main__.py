"""`python -m jarvis.research_ingestion <cmd>` — 연구 데이터 파이프라인 CLI. **실행 없음.**

  ingest --file backtest.json [--commit]                 P53 스키마 JSON 1건 수집
  ingest-backtest --file raw_backtest.json               backtest_runner 원본 출력 1건 수집(P54)
      [--context ctx.json] [--commit]                     (스키마 검증·중복탐지·수집 감사 포함)
  validate --file backtest.json                           스키마·검증지표 확인
  summary / verify / replay

'ingest-backtest' = 과거 백테스트 백필. backtest_runner/agents.backtest 의 완료-시점 출력을
얇은 어댑터로 P53 스키마에 매핑 → 기존 ingest() 로 흘려보낸다. 기존 원장(expt_/rmi_)에 기록만.
거래·집행 없음. 멱등(재수집 no-op).
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


def _cmd_ingest_backtest(a) -> int:
    from jarvis.research_ingestion.backtest_adapter import adapt, ingest_backtest
    raw = _load(a.file)
    ctx = _load(a.context) if a.context else None
    schema = adapt(raw, context=ctx)          # 백필 전 매핑 결과 미리 노출(감사)
    v = _eng().validate(schema)
    res = ingest_backtest(raw, context=ctx, now=_now(), commit=a.commit)
    _p({"committed": a.commit, "validation": v, "mapped_schema": schema,
        "result": res.to_dict()})
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
    ib = sub.add_parser("ingest-backtest")
    ib.add_argument("--file", required=True, help="backtest_runner 원본 출력 JSON")
    ib.add_argument("--context", help="연구 메타·검증지표 보강 JSON(선택)")
    ib.add_argument("--commit", action="store_true")
    va = sub.add_parser("validate")
    va.add_argument("--file", required=True)
    for name in ("summary", "verify", "replay"):
        sub.add_parser(name)
    args = ap.parse_args(argv)
    disp = {"ingest": _cmd_ingest, "ingest-backtest": _cmd_ingest_backtest,
            "validate": _cmd_validate, "summary": _cmd_summary,
            "verify": _cmd_verify, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
