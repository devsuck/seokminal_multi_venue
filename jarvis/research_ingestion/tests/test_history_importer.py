"""Historical Research Backfill(P55) 테스트 — 임포트·매핑·중복보호·INCOMPLETE 보존·엔드투엔드·안전.

핵심 요구(문서 §Tests):
  1. 과거 파일 임포트 성공          4. recall 이 임포트된 연구를 찾는다
  2. 중복 임포트 → 중복 없음        5. failure_intelligence 가 옛 실패를 회수한다
  3. 누락 지표 → INCOMPLETE 보존    6. 해시체인 유효 유지
초기 검증: TSMOM(성공)·ORB(실패)·VWAP(불완전) 알려진 연구가 recall/failure_intelligence 에 나타난다.
모든 관련 원장을 같은 tmp _state 로 격리(P53/P54 패턴 재사용).
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from jarvis.research_ingestion import ledger
from jarvis.research_ingestion import models as M
from jarvis.research_ingestion.engine import ResearchIngestionEngine
from jarvis.research_ingestion.history_importer import (
    SOURCE_TYPE,
    HistoricalResearchImporter,
    _collect_metrics,
    map_record,
    read_records,
)
from jarvis.research_ingestion.verify import verify_chain

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

_FULL_VALID = {"return": 0.14, "sharpe": 0.9, "max_drawdown": -0.18, "volatility": 0.13,
               "walk_forward": 0.8, "out_of_sample": 0.7, "cost_impact": 0.1,
               "parameter_stability": 0.8, "random_baseline": 0.2}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.experiment_tracking import ledger as el
    from jarvis.research_memory_intelligence import ledger as ml
    from jarvis.research_assistant import ledger as al
    monkeypatch.setattr(ledger, "state_path", sp)
    monkeypatch.setattr(el, "state_path", sp)
    monkeypatch.setattr(ml, "state_path", sp)
    monkeypatch.setattr(al, "state_path", sp)
    return HistoricalResearchImporter(ResearchIngestionEngine())


# ── 알려진 과거 연구 예시(형태가 서로 다름 — 하나의 옛 포맷 강요 안 함) ──
def _tsmom():   # 성공, 중첩 metrics, 풀 검증
    return {"strategy": "TSMOM", "version": "2019", "universe": "GLOBAL_FUT",
            "start": "2000-01", "end": "2018-12", "factors": ["ret_12m", "ret_3m"],
            "hypothesis": "time-series momentum across futures",
            "metrics": dict(_FULL_VALID)}


def _orb():     # 실패, 최상위 평면 지표, 명시 root_cause
    return {"name": "ORB", "market": "US_EQ", "date_range": ["2015-01", "2020-12"],
            "sharpe": -0.1, "return": -0.05, "max_drawdown": -0.35, "volatility": 0.2,
            "walk_forward": 0.2, "out_of_sample": -0.3, "cost_impact": 0.15,
            "parameter_stability": 0.6, "random_baseline": 0.1,
            "root_cause": "regime change broke the opening-range edge",
            "lesson": "ORB edge is regime-dependent; require macro filter"}


def _vwap_incomplete():   # 불완전 — 검증지표 대부분 누락(조작 금지 → INCOMPLETE)
    return {"strategy": "VWAP_MeanReversion", "universe": "KR_EQ",
            "metrics": {"sharpe": 0.6, "return": 0.08}}


def _archive():
    return [_tsmom(), _orb(), _vwap_incomplete()]


# ── 매핑 계층 ──
def test_map_record_aliases():
    ctx = map_record(_tsmom())
    assert ctx["strategy_name"] == "TSMOM"
    assert ctx["universe"] == "GLOBAL_FUT"
    assert ctx["features"] == ["ret_12m", "ret_3m"]
    assert ctx["period"] == {"start": "2000-01", "end": "2018-12"}
    assert ctx["metrics"]["sharpe"] == 0.9
    assert ctx["source"] == SOURCE_TYPE


def test_map_record_date_range_and_flat_metrics():
    ctx = map_record(_orb())
    assert ctx["strategy_name"] == "ORB"
    assert ctx["period"] == {"start": "2015-01", "end": "2020-12"}
    assert ctx["metrics"]["max_drawdown"] == -0.35
    assert ctx["root_cause"].startswith("regime change")


def test_map_record_field_map_override():
    rec = {"strat": "X", "sr": 0.7}
    ctx = map_record(rec, field_map={"strategy_name": "strat"})
    assert ctx["strategy_name"] == "X"


def test_collect_metrics_no_fabrication():
    m = _collect_metrics(_vwap_incomplete())
    assert m == {"sharpe": 0.6, "return": 0.08}   # 없는 검증지표를 지어내지 않음


# ── 파일 리더(포맷 감지) ──
def test_read_jsonl(tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in _archive()), encoding="utf-8")
    assert len(read_records(str(p))) == 3


def test_read_json_array(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps(_archive()), encoding="utf-8")
    assert len(read_records(str(p))) == 3


def test_read_json_records_wrapper(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"records": _archive()}), encoding="utf-8")
    assert len(read_records(str(p))) == 3


def test_read_csv(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("strategy,sharpe,max_drawdown,universe\nTSMOM,0.9,-0.18,GLOBAL\n",
                 encoding="utf-8")
    recs = read_records(str(p))
    assert recs[0]["strategy"] == "TSMOM"
    ctx = map_record(recs[0])
    assert ctx["metrics"]["sharpe"] == 0.9   # CSV 문자열도 숫자로 매핑


# ── 1. 과거 파일 임포트 성공 ──
def test_import_file_succeeds(env, tmp_path):
    p = tmp_path / "arch.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in _archive()), encoding="utf-8")
    summ = env.import_file(str(p), now=NOW, commit=True)
    assert summ.record_count == 3
    assert summ.imported == 3
    assert summ.errors == []
    assert len(ledger.read_ingestions()) == 3
    from jarvis.experiment_tracking import ledger as el
    assert len(el.read_experiments()) == 3


# ── 2. 중복 임포트 → 중복 없음(파일명·시각 무관) ──
def test_duplicate_import_no_duplicate(env):
    a = env.import_records(_archive(), source_file="fileA.jsonl", now=NOW, commit=True)
    # 다른 파일명·다른 시각으로 재임포트 — 내용 동일 → 중복 지식 없음
    b = env.import_records(_archive(), source_file="fileB.jsonl",
                           now="2026-06-06T00:00:00Z", commit=True)
    assert a.imported == 3 and a.deduplicated == 0
    assert b.imported == 0 and b.deduplicated == 3
    assert len(ledger.read_ingestions()) == 3
    from jarvis.experiment_tracking import ledger as el
    assert len(el.read_experiments()) == 3


# ── 3. 누락 지표 → INCOMPLETE 보존 ──
def test_missing_metrics_incomplete(env):
    summ = env.import_records([_vwap_incomplete()], now=NOW, commit=True)
    assert summ.incomplete == 1
    rows = ledger.read_ingestions()
    assert rows[0]["outcome"] == M.OUT_INCOMPLETE
    assert rows[0]["validation_complete"] is False


# ── 4. recall 이 임포트된 연구를 찾는다(TSMOM) ──
def test_recall_finds_tsmom(env):
    env.import_records(_archive(), now=NOW, commit=True)
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    r = ResearchAssistantEngine().recall("TSMOM")
    assert r.tried_before is True


# ── 5. failure_intelligence 가 옛 실패를 회수한다(ORB) ──
def test_failure_intelligence_retrieves_orb(env):
    env.import_records(_archive(), now=NOW, commit=True)
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    asst = ResearchAssistantEngine()
    fi = asst.failure_intelligence()
    assert fi.total_failures >= 1
    mc = asst.mistake_check("ORB")
    assert mc["made_this_mistake"] is True


def test_orb_classified_regime(env):
    summ = env.import_records([_orb()], now=NOW, commit=True)
    assert summ.failures == 1
    rows = ledger.read_ingestions()
    assert rows[0]["outcome"] == M.OUT_FAILURE
    assert rows[0]["failure_category"] == "REGIME_CHANGE"


def test_lesson_appears_in_assistant(env):
    env.import_records([_orb()], now=NOW, commit=True)
    from jarvis.research_memory_intelligence import ledger as ml
    lessons = ml.read_lessons()
    assert any("regime" in str(x.get("lesson", "")).lower() for x in lessons)


# ── 6. 해시체인 유효 유지 ──
def test_hash_chain_valid_after_import(env):
    env.import_records(_archive(), now=NOW, commit=True)
    res = verify_chain()
    assert res["ok"]
    assert res["n"] == 3


# ── Provenance(추적성) ──
def test_provenance_recorded(env):
    env.import_records([_tsmom()], source_file="research_archive.jsonl", now=NOW, commit=True)
    row = ledger.read_ingestions()[0]
    assert row["source_type"] == "historical_import"
    assert row["source_file"] == "research_archive.jsonl"
    from jarvis.experiment_tracking import ledger as el
    params = {p["key"]: p["value"] for p in el.read_parameters()}
    assert params.get("source_type") == "historical_import"
    assert params.get("source_file") == "research_archive.jsonl"
    assert params.get("import_timestamp") == NOW


def test_summary_by_source_type(env):
    env.import_records(_archive(), now=NOW, commit=True)
    s = ResearchIngestionEngine().summary(NOW)
    assert s.by_source_type.get("historical_import") == 3


# ── 드라이런 — 기록 없음 ──
def test_dry_run_no_writes(env):
    summ = env.import_records(_archive(), now=NOW, commit=False)
    assert summ.record_count == 3
    assert ledger.read_ingestions() == []
    from jarvis.experiment_tracking import ledger as el
    assert el.read_experiments() == []


# ── 개별 레코드 오류 격리(백필 전체 중단 금지) ──
def test_bad_record_isolated(env):
    recs = [_tsmom(), {"metrics": "not-a-dict"}, _orb()]
    summ = env.import_records(recs, now=NOW, commit=True)
    # 정상 2건은 수집, 나쁜 1건은 error 로 격리(혹은 빈 지표로 흡수) — 전체 중단 없음
    assert summ.imported >= 2
    assert summ.record_count == 3


# ── 안전 스캔 ──
def test_no_forbidden_imports():
    tree = ast.parse(open(SRC / "history_importer.py").read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
           "jarvis.live_trading", "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


def test_no_dangerous_defs():
    tree = ast.parse(open(SRC / "history_importer.py").read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


def test_no_model_id_leak():
    assert MODEL_LEAK_TOKEN not in open(SRC / "history_importer.py").read().lower()


def test_importer_no_execution_methods(env):
    for m in ("execute", "trade", "deploy", "allocate", "approve"):
        assert not hasattr(env, m)


# ── CLI ──
def test_cli_import_history(tmp_path, monkeypatch, capsys):
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.experiment_tracking import ledger as el
    from jarvis.research_memory_intelligence import ledger as ml
    monkeypatch.setattr(ledger, "state_path", sp)
    monkeypatch.setattr(el, "state_path", sp)
    monkeypatch.setattr(ml, "state_path", sp)
    p = tmp_path / "arch.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in _archive()), encoding="utf-8")
    from jarvis.research_ingestion import __main__ as cli
    rc = cli.main(["import-history", "--file", str(p), "--commit"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "summary" in out
    assert len(ledger.read_ingestions()) == 3


def test_cli_import_history_dry_run_overrides_commit(tmp_path, monkeypatch, capsys):
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.experiment_tracking import ledger as el
    from jarvis.research_memory_intelligence import ledger as ml
    monkeypatch.setattr(ledger, "state_path", sp)
    monkeypatch.setattr(el, "state_path", sp)
    monkeypatch.setattr(ml, "state_path", sp)
    p = tmp_path / "arch.json"
    p.write_text(json.dumps(_archive()), encoding="utf-8")
    from jarvis.research_ingestion import __main__ as cli
    # --dry-run 은 --commit 을 이긴다(안전)
    rc = cli.main(["import-history", "--file", str(p), "--commit", "--dry-run"])
    assert rc == 0
    assert ledger.read_ingestions() == []
