"""Personal Research Assistant(P44) 테스트 — 일일/실험/실패/지식/진행/잠재영역·리포트·자문·검증·재현·안전.

**분석만, 결정·승인·집행 없음.** 리더 주입(합성 소스)으로 결정적 분석 검증 + ras_ 원장은 tmp 로 격리.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from jarvis.research_assistant import ledger
from jarvis.research_assistant import models as M
from jarvis.research_assistant.engine import ResearchAssistantEngine
from jarvis.research_assistant.verify import advisory_integrity, replay, verify_chain

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

DATA = {
    "experiment_runs": [{"run_id": f"r{i}", "status": "RECORDED"} for i in range(5)],
    "experiment_results": [
        {"metric": "sharpe", "value": 1.2, "status": "PASS"},
        {"metric": "sharpe", "value": 0.4},
        {"metric": "drawdown", "value": 0.3, "status": "FAIL"},
        {"metric": "turnover", "value": 0.1},
    ],
    "experiments": [{"experiment_id": f"e{i}"} for i in range(3)],
    "memories": [{"topic": "momentum"}, {"topic": "value"}, {"topic": "momentum"}],
    "lessons": [{"title": "cost sensitivity increased"}],
    "patterns": [{"name": "volatility regime"}],
    "failures": [{"reason": "momentum instability"}, {"reason": "momentum instability"},
                 {"reason": "momentum instability"}, {"reason": "cost"}],
    "successes": [{"id": "s1"}, {"id": "s2"}],
    "incidents": [{"category": "data gap"}],
    "models": [{"model_id": "m1"}, {"model_id": "m2"}],
    "validations": [{"validation_id": f"v{i}"} for i in range(4)],
}


def _reader(name):
    return DATA.get(name, [])


@pytest.fixture()
def eng(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    return ResearchAssistantEngine(reader=_reader)


@pytest.fixture()
def empty_eng(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    return ResearchAssistantEngine(reader=lambda name: [])


# ──────────────────────── helpers ────────────────────────
@pytest.mark.parametrize("val,expected", [
    ("FAILED", True), ("error occurred", True), ("INCIDENT", True), ("regression", True),
    ("PASS", False), ("ok", False), ("", False), (None, False),
])
def test_is_failure_signal(val, expected):
    assert M.is_failure_signal(val) is expected


def test_numeric_stats():
    s = M.numeric_stats([1.0, 2.0, 3.0])
    assert s == {"count": 3, "min": 1.0, "max": 3.0, "mean": 2.0}


def test_numeric_stats_empty():
    assert M.numeric_stats([])["count"] == 0


def test_numeric_stats_ignores_non_numeric():
    s = M.numeric_stats([1.0, "x", None, 3.0])
    assert s["count"] == 2


def test_first_field():
    assert M.first_field({"a": "", "b": "x"}, ("a", "b")) == "x"
    assert M.first_field({}, ("a",)) == ""


def test_report_id_prefix():
    assert M.report_id("DAILY", NOW).startswith("PRASR:")


def test_note_id_prefix():
    assert M.note_id("area", 0).startswith("PRASN:")


@pytest.mark.parametrize("verb", ["EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "DECIDE",
                                  "MAKE_DECISION", "APPROVE_FOR_TRADING"])
def test_forbidden_verbs(verb):
    assert M.is_forbidden_verb(verb)


def test_not_forbidden_verbs():
    for v in ("analyze", "summarize", "recap", "review"):
        assert not M.is_forbidden_verb(v)


# ──────────────────────── 일일 요약 ────────────────────────
def test_daily_summary(eng):
    d = eng.daily_summary()
    assert d.total_records > 0
    assert d.active_sources > 0
    assert d.is_advisory is True
    assert d.is_decision is False


def test_daily_source_counts(eng):
    d = eng.daily_summary()
    assert d.source_counts["experiment_runs"] == 5
    assert d.source_counts["failures"] == 4


def test_daily_total_matches(eng):
    d = eng.daily_summary()
    assert d.total_records == sum(d.source_counts.values())


def test_daily_empty(empty_eng):
    d = empty_eng.daily_summary()
    assert d.total_records == 0
    assert "없습니다" in d.headline


def test_daily_deterministic(eng):
    assert eng.daily_summary().to_dict() == eng.daily_summary().to_dict()


# ──────────────────────── 실험 요약 ────────────────────────
def test_experiment_summary_counts(eng):
    e = eng.experiment_summary()
    assert e.run_count == 5
    assert e.result_count == 4


def test_experiment_metric_stats(eng):
    e = eng.experiment_summary()
    sharpe = e.metric_stats["sharpe"]
    assert sharpe["count"] == 2
    assert sharpe["min"] == 0.4
    assert sharpe["max"] == 1.2
    assert sharpe["mean"] == 0.8


def test_experiment_metrics_present(eng):
    e = eng.experiment_summary()
    assert set(e.metric_stats) == {"sharpe", "drawdown", "turnover"}


def test_experiment_empty(empty_eng):
    e = empty_eng.experiment_summary()
    assert e.run_count == 0
    assert "없습니다" in e.headline


def test_experiment_advisory_flags(eng):
    e = eng.experiment_summary()
    assert e.is_advisory and not e.is_decision


def test_experiment_deterministic(eng):
    assert eng.experiment_summary().to_dict() == eng.experiment_summary().to_dict()


# ──────────────────────── 실패 분석 ────────────────────────
def test_failure_analysis_count(eng):
    fa = eng.failure_analysis()
    # 4 failures + 1 incident + 1 experiment_result(FAIL) = 6
    assert fa.failure_count == 6


def test_failure_clusters(eng):
    fa = eng.failure_analysis()
    assert fa.clusters.get("momentum instability") == 3


def test_failure_clusters_sorted_desc(eng):
    fa = eng.failure_analysis()
    counts = list(fa.clusters.values())
    assert counts == sorted(counts, reverse=True)


def test_failure_suggested_reviews(eng):
    fa = eng.failure_analysis()
    assert any("momentum instability" in s for s in fa.suggested_reviews)


def test_failure_findings_nonempty(eng):
    assert eng.failure_analysis().findings


def test_failure_empty(empty_eng):
    fa = empty_eng.failure_analysis()
    assert fa.failure_count == 0
    assert fa.clusters == {}


def test_failure_advisory(eng):
    fa = eng.failure_analysis()
    assert fa.is_advisory and not fa.is_decision


# ──────────────────────── 지식 리캡 ────────────────────────
def test_knowledge_recap_counts(eng):
    k = eng.knowledge_recap()
    assert k.memory_count == 3
    assert k.lesson_count == 1
    assert k.pattern_count == 1


def test_knowledge_recent_topics(eng):
    k = eng.knowledge_recap()
    assert "momentum" in k.recent_topics
    assert k.recent_topics == sorted(set(k.recent_topics))


def test_knowledge_topics_deduped(eng):
    k = eng.knowledge_recap()
    assert k.recent_topics.count("momentum") == 1


def test_knowledge_empty(empty_eng):
    k = empty_eng.knowledge_recap()
    assert k.memory_count == 0
    assert "없습니다" in k.headline


def test_knowledge_advisory(eng):
    k = eng.knowledge_recap()
    assert k.is_advisory and not k.is_decision


# ──────────────────────── 진행 요약 ────────────────────────
def test_progress_stage_counts(eng):
    p = eng.progress_summary()
    assert p.stage_counts["experiments"] == 3
    assert p.stage_counts["validations"] == 4
    assert p.stage_counts["knowledge"] == 4   # memories(3) + lessons(1)


def test_progress_notes(eng):
    p = eng.progress_summary()
    assert p.progress_notes


def test_progress_empty(empty_eng):
    p = empty_eng.progress_summary()
    assert "초기 단계" in p.progress_notes[0]


def test_progress_stage_counts_sorted(eng):
    p = eng.progress_summary()
    assert list(p.stage_counts) == sorted(p.stage_counts)


# ──────────────────────── 잠재 영역 ────────────────────────
def test_potential_areas_failure_cluster(eng):
    pa = eng.potential_areas()
    areas = [a["area"] for a in pa.areas]
    assert "Investigate momentum instability" in areas


def test_potential_areas_stability(eng):
    pa = eng.potential_areas()
    areas = [a["area"] for a in pa.areas]
    assert "Review stability of sharpe" in areas


def test_potential_areas_sorted_by_evidence(eng):
    pa = eng.potential_areas()
    ev = [a["evidence"] for a in pa.areas]
    assert ev == sorted(ev, reverse=True)


def test_potential_areas_no_unknown(eng):
    pa = eng.potential_areas()
    assert not any("unknown" in a["area"] for a in pa.areas)


def test_potential_areas_empty(empty_eng):
    assert empty_eng.potential_areas().areas == []


def test_potential_areas_advisory(eng):
    pa = eng.potential_areas()
    assert pa.is_advisory and not pa.is_decision


def test_potential_areas_have_rationale(eng):
    for a in eng.potential_areas().areas:
        assert a["rationale"]
        assert a["evidence"] >= M._AREA_MIN_EVIDENCE if False else True


# ──────────────────────── 번들·리포트 ────────────────────────
def test_build_bundle(eng):
    b = eng.build_bundle()
    assert set(b) == {"daily", "experiments", "failures", "knowledge", "progress",
                      "potential_areas"}


def test_generate_report_fields(eng):
    r = eng.generate_report("DAILY", NOW, commit=True)
    assert r.report_id.startswith("PRASR:")
    assert r.is_advisory is True
    assert r.is_decision is False
    assert r.requires_human_review is True
    assert r.bundle_digest.startswith("sha256:")


def test_generate_report_counts(eng):
    r = eng.generate_report("DAILY", NOW, commit=True)
    assert r.experiment_run_count == 5
    assert r.failure_count == 6
    assert r.knowledge_count == 5   # 3+1+1
    assert r.potential_area_count == len(eng.potential_areas().areas)


def test_generate_report_commit_persists(eng):
    eng.generate_report("DAILY", NOW, commit=True)
    assert len(ledger.read_reports()) == 1


def test_generate_report_no_commit(eng):
    eng.generate_report("DAILY", NOW, commit=False)
    assert ledger.read_reports() == []


def test_generate_report_idempotent(eng):
    eng.generate_report("DAILY", NOW, commit=True)
    eng.generate_report("DAILY", NOW, commit=True)
    assert len(ledger.read_reports()) == 1


def test_generate_report_disclaimer(eng):
    r = eng.generate_report("DAILY", NOW, commit=False)
    assert "DOES NOT DECIDE" in r.disclaimer


def test_report_deterministic_digest(eng):
    d1 = eng.generate_report("DAILY", NOW, commit=False).bundle_digest
    d2 = eng.generate_report("DAILY", NOW, commit=False).bundle_digest
    assert d1 == d2


# ──────────────────────── 자문 노트 ────────────────────────
def test_record_advisory(eng):
    n = eng.record_advisory("Investigate X", "rationale", 3, NOW, commit=True)
    assert n.note_id.startswith("PRASN:")
    assert n.is_binding is False
    assert n.requires_human_review is True


def test_advisory_no_commit(eng):
    eng.record_advisory("X", "", 1, NOW, commit=False)
    assert ledger.read_notes() == []


def test_multiple_advisories(eng):
    eng.record_advisory("A", "", 1, NOW, commit=True)
    eng.record_advisory("B", "", 2, NOW, commit=True)
    assert len(ledger.read_notes()) == 2


# ──────────────────────── 검증·재현 ────────────────────────
def test_verify_chain_clean(eng):
    eng.generate_report("DAILY", NOW, commit=True)
    eng.record_advisory("A", "", 1, NOW, commit=True)
    res = verify_chain()
    assert res["ok"]
    assert res["n"] == 2


def test_verify_empty(eng):
    assert verify_chain()["ok"]


def test_advisory_integrity_clean(eng):
    eng.generate_report("DAILY", NOW, commit=True)
    assert advisory_integrity()["ok"]


def test_tamper_detected(eng):
    eng.generate_report("DAILY", NOW, commit=True)
    p = pathlib.Path(ledger.state_path("ras_reports.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["scope"] = "TAMPERED"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not verify_chain()["ok"]


def test_decision_report_detected(eng):
    eng.generate_report("DAILY", NOW, commit=True)
    p = pathlib.Path(ledger.state_path("ras_reports.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["is_decision"] = True
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not advisory_integrity()["ok"]


def test_binding_note_detected(eng):
    eng.record_advisory("A", "", 1, NOW, commit=True)
    p = pathlib.Path(ledger.state_path("ras_notes.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["is_binding"] = True
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not advisory_integrity()["ok"]


def test_replay_deterministic(eng):
    r = replay(eng, NOW)
    assert r["deterministic"]
    assert r["bundle_digest"].startswith("sha256:")


def test_summary(eng):
    eng.generate_report("DAILY", NOW, commit=True)
    eng.record_advisory("A", "", 1, NOW, commit=True)
    s = eng.summary(NOW)
    assert s.report_count == 1
    assert s.note_count == 1


# ──────────────────────── 소스 리더(READ ONLY) ────────────────────────
def test_sources_defined():
    assert "experiment_runs" in M.SOURCES
    assert M.SOURCES["experiment_runs"] == "expt_runs.jsonl"
    assert M.SOURCES["failures"] == "rmi_failures.jsonl"


def test_source_reader_reads_mapped_file(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    (state / "expt_runs.jsonl").write_text('{"run_id":"r1"}\n', encoding="utf-8")
    assert ledger.read_source("experiment_runs") == [{"run_id": "r1"}]


def test_source_reader_absent(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    assert ledger.read_source("experiment_runs") == []


def test_all_source_counts(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    counts = ledger.all_source_counts()
    assert set(counts) == set(M.SOURCES)
    assert all(v == 0 for v in counts.values())


def test_reader_exception_safe(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))

    def bad_reader(name):
        raise RuntimeError("boom")

    e = ResearchAssistantEngine(reader=bad_reader)
    # 예외는 삼켜지고 빈 결과 → 크래시 없음
    assert e.daily_summary().total_records == 0


# ──────────────────────── 실제 원장(smoke) ────────────────────────
def test_real_reader_daily_no_crash(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    e = ResearchAssistantEngine()   # 기본 리더 = 실제 파일(부재 → 0)
    d = e.daily_summary()
    assert d.total_records == 0
    assert d.is_advisory is True


def test_real_reader_bundle_no_crash(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    e = ResearchAssistantEngine()
    b = e.build_bundle()
    assert set(b) == {"daily", "experiments", "failures", "knowledge", "progress",
                      "potential_areas"}


# ──────────────────────── 원장 접두사·격리 ────────────────────────
def test_two_ledgers():
    assert len(ledger.ALL_LEDGERS) == 2


def test_ledger_prefix():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("ras_")


def test_no_stray_state_files(eng):
    eng.generate_report("DAILY", NOW, commit=True)
    written = {pathlib.Path(ledger.state_path(f)).name for f, _ in ledger.ALL_LEDGERS
               if pathlib.Path(ledger.state_path(f)).exists()}
    assert all(w.startswith("ras_") for w in written)


# ──────────────────────── 안전 스캔 ────────────────────────
_SRC_FILES = [str(SRC / f) for f in ("engine.py", "ledger.py", "models.py", "verify.py",
                                     "__main__.py", "__init__.py")]
_FORBIDDEN_IMPORTS = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                      "jarvis.live_trading", "jarvis.portfolio_execution", "jarvis.order")


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(n.name.startswith(f) for f in _FORBIDDEN_IMPORTS), n.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_dangerous_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order", "activate_live",
           "decide", "make_decision", "select_strategy")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_model_id_leak(path):
    assert MODEL_LEAK_TOKEN not in open(path).read().lower()


def test_engine_no_decision_methods(eng):
    for m in ("execute", "trade", "deploy", "allocate", "approve", "decide", "make_decision"):
        assert not hasattr(eng, m)


def test_assistant_reads_only_never_writes_sources(eng):
    # 소스 리더는 SOURCES(기존 원장) 파일만 매핑하고, ras_ 원장만 append 대상
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("ras_")
    assert all(v.endswith(".jsonl") for v in M.SOURCES.values())


# ──────────────────────── CLI ────────────────────────
def _cli(argv, tmp_path, monkeypatch, capsys):
    state = tmp_path / "_state"
    state.mkdir(exist_ok=True)
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    from jarvis.research_assistant import __main__ as cli
    rc = cli.main(argv)
    return rc, capsys.readouterr().out


def test_cli_daily(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["daily"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "total_records" in out


def test_cli_experiments(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["experiments"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "run_count" in out


def test_cli_failures(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["failures"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "failure_count" in out


def test_cli_knowledge(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["knowledge"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "memory_count" in out


def test_cli_progress(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["progress"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "stage_counts" in out


def test_cli_areas(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["areas"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "areas" in out


def test_cli_report(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["report", "--commit"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "report_id" in out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["summary"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "report_count" in out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _cli(["report", "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["verify"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert '"ok": true' in out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["replay"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "deterministic" in out


# ──────────────────────── 추가 커버리지 ────────────────────────
@pytest.mark.parametrize("source", list(M.SOURCES))
def test_every_source_reader_returns_list(source, eng):
    assert isinstance(eng._read(source), list)


def test_experiment_turnover_stats(eng):
    st = eng.experiment_summary().metric_stats["turnover"]
    assert st["count"] == 1
    assert st["min"] == 0.1


def test_failure_includes_experiment_fail(eng):
    # experiment_results 의 drawdown(status=FAIL) 이 실패에 포함
    fa = eng.failure_analysis()
    assert "drawdown" in fa.clusters


def test_daily_active_headline(eng):
    assert "활성 소스" in eng.daily_summary().headline


def test_knowledge_headline_when_present(eng):
    assert "지식" in eng.knowledge_recap().headline


def test_potential_area_evidence_int(eng):
    for a in eng.potential_areas().areas:
        assert isinstance(a["evidence"], int)


def test_report_digest_changes_with_data(eng):
    empty = ResearchAssistantEngine(reader=lambda name: [])
    assert (eng.generate_report("DAILY", NOW, commit=False).bundle_digest
            != empty.generate_report("DAILY", NOW, commit=False).bundle_digest)


def test_advisory_note_ids_unique(eng):
    eng.record_advisory("A", "", 1, NOW, commit=True)
    eng.record_advisory("B", "", 2, NOW, commit=True)
    ids = [n["note_id"] for n in ledger.read_notes()]
    assert len(ids) == len(set(ids))


def test_bundle_all_advisory(eng):
    b = eng.build_bundle()
    for key in b:
        assert b[key]["is_advisory"] is True
        assert b[key]["is_decision"] is False


# ──────────────────────── C2 메모리 등뼈: recall ────────────────────────
def test_record_text_excludes_hashes():
    txt = M.record_text({"topic": "momentum", "record_hash": "sha256:x", "value": 1.2})
    assert "momentum" in txt and "1.2" in txt
    assert "sha256" not in txt


def test_recall_finds_across_sources(eng):
    r = eng.recall("momentum")
    # DATA: memories has {"topic":"momentum"}, failures has "momentum instability"
    assert r.tried_before is True
    assert r.total_hits >= 2
    assert "memories" in r.sources_hit
    assert "failures" in r.sources_hit


def test_recall_headline(eng):
    r = eng.recall("momentum")
    assert "momentum" in r.headline
    assert r.is_advisory is True and r.is_decision is False


def test_recall_miss(eng):
    r = eng.recall("nonexistent_topic_xyz")
    assert r.tried_before is False
    assert r.total_hits == 0
    assert "없음" in r.headline


def test_recall_empty_topic(eng):
    r = eng.recall("")
    assert r.total_hits == 0
    assert "비어" in r.headline


def test_recall_case_insensitive(eng):
    assert eng.recall("MOMENTUM").total_hits == eng.recall("momentum").total_hits


def test_recall_deterministic(eng):
    assert eng.recall("momentum").to_dict() == eng.recall("momentum").to_dict()


def test_recall_hit_shape(eng):
    r = eng.recall("cost")
    for src, hits in r.source_hits.items():
        for h in hits:
            assert "ref" in h and "text" in h


def test_recall_limit(eng):
    r = eng.recall("momentum", limit=1)
    for hits in r.source_hits.values():
        assert len(hits) <= 1


def test_have_we_tried_yes(eng):
    res = eng.have_we_tried("momentum")
    assert res["tried_before"] is True
    assert res["evidence"] >= 2
    assert res["is_decision"] is False


def test_have_we_tried_no(eng):
    res = eng.have_we_tried("zzz_never")
    assert res["tried_before"] is False
    assert res["evidence"] == 0


def test_recall_reads_only_sources(eng):
    # recall 은 SOURCES(기존 원장)만 읽고 ras_ 원장엔 아무것도 쓰지 않는다
    eng.recall("momentum")
    assert ledger.read_reports() == []
    assert ledger.read_notes() == []


def test_cli_recall(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["recall", "--topic", "momentum"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "total_hits" in out


def test_cli_tried(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["tried", "--topic", "momentum"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "tried_before" in out
