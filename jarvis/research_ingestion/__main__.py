"""`python -m jarvis.research_ingestion <cmd>` — 연구 데이터 파이프라인 CLI. **실행 없음.**

  ingest --file backtest.json [--commit]                 P53 스키마 JSON 1건 수집
  ingest-backtest --file raw_backtest.json               backtest_runner 원본 출력 1건 수집(P54)
      [--context ctx.json] [--commit]                     (스키마 검증·중복탐지·수집 감사 포함)
  import-history --file archive.jsonl [--commit|--dry-run]  과거 연구 파일 백필(P55: JSON/JSONL/CSV)
      [--field-map map.json]                                (별칭 매핑·중복보호·provenance·INCOMPLETE 보존)
  discover [--root DIR ...] [--all]                         과거 연구 자산 발견(P56: Manifest, 임포트 안 함)
  revalidate --file record.json                            불완전 검증 진단(P57: 누락 검증 목록·조작 없음)
      | backlog                                             (backlog: 원장의 INCOMPLETE 목록)
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


def _cmd_import_history(a) -> int:
    from jarvis.research_ingestion.history_importer import HistoricalResearchImporter
    fmap = _load(a.field_map) if a.field_map else None
    commit = bool(a.commit) and not a.dry_run    # --dry-run 이 항상 우선(안전)
    imp = HistoricalResearchImporter()
    summ = imp.import_file(a.file, now=_now(), commit=commit, field_map=fmap)
    _p({"committed": commit, "dry_run": (not commit), "summary": summ.to_dict()})
    return 0


def _cmd_discover(a) -> int:
    from jarvis.research_ingestion.archive_discovery import discover
    roots = a.root or None
    man = discover(roots, include_empty=bool(a.all))
    _p(man.to_dict())
    return 0


def _cmd_revalidate(a) -> int:
    from jarvis.research_ingestion.revalidation import ResearchRevalidationEngine
    eng = ResearchRevalidationEngine()
    if a.backlog:
        _p(eng.incomplete_backlog().to_dict())
        return 0
    if not a.file:
        _p({"error": "--file 또는 backlog 필요"})
        return 1
    # CLI 는 하네스 없이 진단(plan)만 — 실제 재실행은 프로그램에서 하네스 주입 필요(조작 방지)
    plan = eng.plan(_load(a.file))
    res = eng.revalidate(_load(a.file), harness=None)
    _p({"plan": plan.to_dict(), "result": res.to_dict()})
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
    ih = sub.add_parser("import-history")
    ih.add_argument("--file", required=True, help="과거 연구 파일(JSON/JSONL/CSV)")
    ih.add_argument("--field-map", dest="field_map", help="별칭 매핑 오버라이드 JSON(선택)")
    ih.add_argument("--commit", action="store_true")
    ih.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="기록 없이 매핑·판정만(안전; --commit 보다 우선)")
    dc = sub.add_parser("discover")
    dc.add_argument("--root", action="append", help="탐색 디렉터리(반복 지정; 없으면 기본 위치)")
    dc.add_argument("--all", action="store_true", help="감지 실패 파일도 포함")
    rv = sub.add_parser("revalidate")
    rv.add_argument("--file", help="재검증 진단할 레코드 JSON")
    rv.add_argument("--backlog", action="store_true", help="원장의 INCOMPLETE 목록")
    va = sub.add_parser("validate")
    va.add_argument("--file", required=True)
    for name in ("summary", "verify", "replay"):
        sub.add_parser(name)
    args = ap.parse_args(argv)
    disp = {"ingest": _cmd_ingest, "ingest-backtest": _cmd_ingest_backtest,
            "import-history": _cmd_import_history, "discover": _cmd_discover,
            "revalidate": _cmd_revalidate,
            "validate": _cmd_validate, "summary": _cmd_summary,
            "verify": _cmd_verify, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
