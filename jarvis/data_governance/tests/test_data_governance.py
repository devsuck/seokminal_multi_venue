"""P9.8 Data Governance & Lineage 테스트. **데이터 거버넌스 전용.**

레지스트리(불변·중복방지)·스키마·버전·계보(사이클/자기참조/부모/체인)·품질(8체크·상태)·스키마 drift
(NO/WARNING/CRITICAL, 타입변경)·신선도·신뢰도·verify(체인/변조/중복/계보)·replay·CLI·보안(금지import·
집행/브로커/포트폴리오 없음·삭제 API 없음·기존 원장 무변경(충돌 회피)·append-only·불변).

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.data_governance import ledger
from jarvis.data_governance import models as M
from jarvis.data_governance.engine import DataGovernanceEngine
from jarvis.data_governance.models import (
    CRITICAL_DRIFT,
    DEGRADED,
    EXCELLENT,
    FAILED,
    NO_DRIFT,
    RELIABLE,
    UNRELIABLE,
    WARNING,
    WARNING_DRIFT,
    ImmutableDatasetError,
    ImmutableSchemaError,
    LineageError,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T_LATE = "2026-07-25T00:00:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.data_governance.ledger.state_path", sp)
    return sp


def _eng():
    return DataGovernanceEngine()


def _ds(eng, did="D1", name=None, commit=True):
    return eng.register_dataset(did, name or f"{did} name", "desc", "krx", "equity",
                                "owner", T0, commit=commit)


# ── 1~20. models 순수 ──
def test_dataset_hash_deterministic():
    assert M.dataset_hash("D", "n", "s", "equity", "d") == M.dataset_hash("D", "n", "s", "equity", "d")


def test_schema_hash_deterministic():
    assert M.schema_hash("D", "1", {"a": "int"}) == M.schema_hash("D", "1", {"a": "int"})


def test_content_hash_excludes():
    a = {"x": 1, "previous_hash": "p1", "record_hash": "r1"}
    b = {"x": 1, "previous_hash": "p2", "record_hash": "r2"}
    assert M.content_hash(a) == M.content_hash(b)


def test_quality_score_perfect():
    assert M.quality_score({}) == 100


def test_quality_score_penalties():
    assert M.quality_score({"missing_ratio": 0.1}) == 96
    assert M.quality_score({"schema_mismatch": True}) == 75
    assert M.quality_score({"stale_timestamp": True}) == 85


def test_quality_status_thresholds():
    assert M.quality_status(95, False) == EXCELLENT
    assert M.quality_status(80, False) == "GOOD"
    assert M.quality_status(70, False) == WARNING
    assert M.quality_status(40, False) == FAILED
    assert M.quality_status(95, True) == FAILED


def test_reliability_level_thresholds():
    assert M.reliability_level(90) == RELIABLE
    assert M.reliability_level(60) == DEGRADED
    assert M.reliability_level(30) == UNRELIABLE


def test_compare_schemas_no_drift():
    level, _ = M.compare_schemas({"a": "int"}, {"a": "int"})
    assert level == NO_DRIFT


def test_compare_schemas_added_warning():
    level, changes = M.compare_schemas({"a": "int"}, {"a": "int", "b": "float"})
    assert level == WARNING_DRIFT and any("added:b" in c for c in changes)


def test_compare_schemas_type_change_critical():
    level, changes = M.compare_schemas({"price": "float"}, {"price": "string"})
    assert level == CRITICAL_DRIFT
    assert any("type_changed:price:float->string" in c for c in changes)


def test_compare_schemas_removed_critical():
    level, changes = M.compare_schemas({"a": "int", "b": "int"}, {"a": "int"})
    assert level == CRITICAL_DRIFT and any("removed:b" in c for c in changes)


def test_detect_cycle_none():
    assert M.detect_lineage_cycle([("B", "A")]) == []


def test_detect_cycle_self():
    assert M.detect_lineage_cycle([], "A", "A") == ["A", "A"]


def test_detect_cycle_indirect():
    cyc = M.detect_lineage_cycle([("B", "A"), ("A", "B")])
    assert cyc and cyc[0] == cyc[-1]


def test_compute_checks_missing():
    c = M.compute_checks([{"a": 1, "b": None}, {"a": 2, "b": 3}], {"a": "int", "b": "int"})
    assert c["missing_ratio"] == 0.25 and c["schema_mismatch"] is True


def test_compute_checks_duplicate():
    c = M.compute_checks([{"a": 1}, {"a": 1}, {"a": 2}], {"a": "int"})
    assert round(c["duplicate_ratio"], 4) == round(1 / 3, 4)


def test_compute_checks_unexpected_columns():
    c = M.compute_checks([{"a": 1, "surprise": 9}], {"a": "int"})
    assert "surprise" in c["unexpected_columns"]


def test_compute_checks_null_ratio():
    c = M.compute_checks([{"a": None, "b": 1}], {"a": "int", "b": "int"})
    assert c["null_ratio"] == 0.5


def test_compute_checks_row_count_anomaly():
    c = M.compute_checks([{"a": 1}], {"a": "int"}, expected_row_count=100)
    assert c["row_count_anomaly"] is True


def test_compute_checks_source_and_stale():
    recs = [{"a": 1, "source": "krx", "timestamp": T0}]
    c = M.compute_checks(recs, {"a": "int"}, T_LATE, expected_source="nyse")
    assert c["source_consistent"] is False and c["stale_timestamp"] is True


# ── 21~25. Dataset Registry + 충돌 회피 ──
def test_register_dataset_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = _ds(_eng(), commit=False)
    assert d.dataset_id == "D1" and d.dataset_hash.startswith("sha256:")


def test_register_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _ds(_eng())
    assert len(ledger.read_datasets()) == 1


def test_register_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng)
    _ds(eng)
    assert len(ledger.read_datasets()) == 1


def test_register_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="D1", name="orig")
    with pytest.raises(ImmutableDatasetError):
        _ds(eng, did="D1", name="changed")


def test_uses_dg_prefixed_file_not_p101(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _ds(_eng())
    assert os.path.exists(sp("dg_datasets.jsonl"))
    assert not os.path.exists(sp("datasets.jsonl"))   # P10.1 원장 미생성(충돌 회피)


# ── 26~28. Schema Registry ──
def test_register_schema_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().register_schema("D1", "1", {"price": "float"}, T0, commit=True)
    assert s.columns == {"price": "float"} and len(ledger.read_schemas()) == 1


def test_schema_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_schema("D1", "1", {"price": "float"}, T0, commit=True)
    with pytest.raises(ImmutableSchemaError):
        eng.register_schema("D1", "1", {"price": "string"}, T0, commit=True)


def test_schema_new_version(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_schema("D1", "1", {"price": "float"}, T0, commit=True)
    eng.register_schema("D1", "2", {"price": "string"}, T0, commit=True)
    assert len(ledger.read_schemas()) == 2


# ── 29~31. Version ──
def test_register_version_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    v = _eng().register_version("D1", "1", 1000, "sha256:abc", "SCH:1", T0, commit=True)
    assert v.row_count == 1000 and len(ledger.read_versions()) == 1


def test_version_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_version("D1", "1", 100, "c1", "S1", T0, commit=True)
    eng.register_version("D1", "2", 200, "c2", "S1", T0, commit=True)
    assert len(ledger.read_versions()) == 2


def test_version_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_version("D1", "1", 100, "c1", "S1", T0, commit=True)
    eng.register_version("D1", "1", 100, "c1", "S1", T1, commit=True)
    assert len(ledger.read_versions()) == 1


# ── 32~37. Lineage ──
def test_record_lineage_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="RAW")
    _ds(eng, did="CLEAN")
    lr = eng.record_lineage("CLEAN", "RAW", "transform", "adjust", "1", T0, commit=True)
    assert lr.parent_dataset == "RAW"


def test_lineage_self_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="A")
    with pytest.raises(LineageError):
        eng.record_lineage("A", "A", "op", "t", "1", T0, commit=True)


def test_lineage_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="A")
    _ds(eng, did="B")
    eng.record_lineage("B", "A", "op", "t", "1", T0, commit=True)
    with pytest.raises(LineageError):
        eng.record_lineage("A", "B", "op", "t", "1", T0, commit=True)


def test_lineage_missing_parent_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="CHILD")
    with pytest.raises(LineageError):
        eng.record_lineage("CHILD", "GHOST", "op", "t", "1", T0, require_parent=True, commit=True)


def test_lineage_chain_order(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for did in ("RAW", "CLEAN", "FEAT"):
        _ds(eng, did=did)
    eng.record_lineage("CLEAN", "RAW", "op", "t", "1", T0, commit=True)
    eng.record_lineage("FEAT", "CLEAN", "op", "t", "1", T0, commit=True)
    assert eng.lineage_chain("FEAT") == ["RAW", "CLEAN", "FEAT"]


def test_lineage_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="A")
    _ds(eng, did="B")
    eng.record_lineage("B", "A", "op", "t", "1", T0, commit=True)
    eng.record_lineage("B", "A", "op", "t", "1", T0, commit=True)
    assert len(ledger.read_lineage()) == 1


# ── 38~44. Quality (8 checks) ──
def test_validate_quality_excellent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().validate_quality("D1", T0, checks={})
    assert r.quality_score == 100 and r.status == EXCELLENT


def test_validate_quality_from_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    recs = [{"a": 1, "timestamp": T0}, {"a": 2, "timestamp": T1}]
    r = _eng().validate_quality("D1", T1, records=recs, expected_columns={"a": "int"})
    assert r.status == EXCELLENT


def test_validate_quality_schema_mismatch_failed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().validate_quality("D1", T0, checks={"schema_mismatch": True})
    assert r.status == FAILED


def test_validate_quality_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().validate_quality("D1", T0, checks={"missing_ratio": 0.7})
    assert r.status == WARNING and r.quality_score == 72


def test_quality_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().validate_quality("D1", T0, checks={}, commit=True)
    assert len(ledger.read_quality_reports()) == 1


def test_quality_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.validate_quality("D1", T0, checks={"missing_ratio": 0.1}, commit=True)
    eng.validate_quality("D1", T1, checks={"missing_ratio": 0.1}, commit=True)
    assert len(ledger.read_quality_reports()) == 1


def test_quality_report_has_8_checks(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().validate_quality("D1", T0, records=[{"a": 1, "timestamp": T0}],
                                expected_columns={"a": "int"})
    for k in ("missing_ratio", "duplicate_ratio", "null_ratio", "schema_mismatch",
              "stale_timestamp", "unexpected_columns", "row_count_anomaly", "source_consistent"):
        assert k in r.checks


# ── 45~48. Schema drift ──
def test_drift_no_drift(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().detect_schema_drift("D1", {"a": "int"}, old_columns={"a": "int"})
    assert res["drift_level"] == NO_DRIFT


def test_drift_type_change_critical(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().detect_schema_drift("D1", {"price": "string"}, old_columns={"price": "float"})
    assert res["drift_level"] == CRITICAL_DRIFT


def test_drift_added_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().detect_schema_drift("D1", {"a": "int", "b": "int"}, old_columns={"a": "int"})
    assert res["drift_level"] == WARNING_DRIFT


def test_drift_from_registered_schema(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_schema("D1", "1", {"price": "float"}, T0, commit=True)
    res = eng.detect_schema_drift("D1", {"price": "string"})   # old from ledger
    assert res["drift_level"] == CRITICAL_DRIFT


# ── 49~51. Stale / freshness ──
def test_detect_stale_fresh(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().detect_stale_data("D1", T0, T1)
    assert res["stale"] is False


def test_detect_stale_stale(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().detect_stale_data("D1", T0, T_LATE)   # 2일 경과
    assert res["stale"] is True


def test_check_source_freshness_reads_file(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 기존 P9.x 원장을 데이터로만 읽어 신선도 관측(무변경)
    with open(sp("system_health_reports.jsonl"), "w") as f:
        f.write(json.dumps({"report_id": "SHR:1", "timestamp": T0}) + "\n")
    res = _eng().check_source_freshness("system_health_reports.jsonl", T_LATE)
    assert res["stale"] is True and res["n_records"] == 1


# ── 52~55. Reliability ──
def test_reliability_high(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="A")
    _ds(eng, did="RAW")
    eng.validate_quality("A", T0, checks={}, commit=True)
    eng.record_lineage("A", "RAW", "op", "t", "1", T0, commit=True)
    r = eng.calculate_reliability_score("A", T0)
    assert r.level == RELIABLE and r.reliability_score >= 80


def test_reliability_no_data(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().calculate_reliability_score("GHOST", T0)
    assert r.quality_score == 0 and r.level in (UNRELIABLE, DEGRADED)


def test_reliability_reflects_quality(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.validate_quality("A", T0, checks={"schema_mismatch": True}, commit=True)
    r = eng.calculate_reliability_score("A", T0)
    assert r.quality_score == 75


def test_reliability_lineage_completeness(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="A")
    _ds(eng, did="P")
    eng.record_lineage("A", "P", "op", "t", "1", T0, commit=True)
    r = eng.calculate_reliability_score("A", T0)
    assert r.lineage_completeness == 100


# ── 56~58. Summary ──
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="D1")
    _ds(eng, did="D2")
    eng.register_schema("D1", "1", {"a": "int"}, T0, commit=True)
    s = eng.summary(T0)
    assert s.dataset_count == 2 and s.schema_count == 1


def test_summary_avg(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.validate_quality("D1", T0, checks={}, commit=True)
    assert eng.summary(T0).average_quality_score == 100.0


def test_summary_failed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.validate_quality("D1", T0, checks={"schema_mismatch": True}, commit=True)
    assert eng.summary(T0).failed_datasets == 1


# ── 59~65. Verify / tamper / replay / lineage ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_chain_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.verify import verify_chain
    eng = _eng()
    _ds(eng, did="RAW")
    _ds(eng, did="CLEAN")
    eng.register_schema("RAW", "1", {"a": "int"}, T0, commit=True)
    eng.record_lineage("CLEAN", "RAW", "op", "t", "1", T0, commit=True)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 3


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.verify import verify_chain
    _ds(_eng())
    path = sp("dg_datasets.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["source"] = "TAMPERED"
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    assert verify_chain()["ledgers"]["dg_datasets.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.verify import verify_chain
    eng = _eng()
    _ds(eng, did="A")
    _ds(eng, did="B")
    path = sp("dg_datasets.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ledgers"]["dg_datasets.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.verify import verify_chain
    _ds(_eng())
    path = sp("dg_datasets.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    assert verify_chain()["ledgers"]["dg_datasets.jsonl"]["reason"] in {"duplicate_id",
                                                                        "previous_hash_broken"}


def test_verify_lineage_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.verify import lineage_integrity
    with open(sp("dg_lineage_events.jsonl"), "w") as f:
        f.write(json.dumps({"lineage_id": "L1", "dataset_id": "B", "parent_dataset": "A"}) + "\n")
        f.write(json.dumps({"lineage_id": "L2", "dataset_id": "A", "parent_dataset": "B"}) + "\n")
    res = lineage_integrity()
    assert res["ok"] is False and res["cycle"]


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.validate_quality("D1", T0, checks={}, commit=True)
    from jarvis.data_governance.verify import replay
    assert replay(eng, "D1", T0)["deterministic"] is True


# ── 66~72. CLI ──
def test_cli_register(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.__main__ import main
    rc = main(["register", "--dataset-id", "D1", "--name", "n", "--source", "krx",
               "--asset-class", "equity", "--owner", "o", "--commit"])
    assert rc == 0 and "dataset" in capsys.readouterr().out


def test_cli_schema(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.__main__ import main
    rc = main(["schema", "--dataset-id", "D1", "--version", "1",
               "--columns-json", '{"price":"float"}', "--commit"])
    assert rc == 0 and "schema" in capsys.readouterr().out


def test_cli_lineage(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.__main__ import main
    rc = main(["lineage", "--dataset-id", "CLEAN", "--parent", "RAW",
               "--operation", "transform", "--version", "1", "--commit"])
    assert rc == 0 and "lineage" in capsys.readouterr().out


def test_cli_quality(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.__main__ import main
    rc = main(["quality", "--dataset-id", "D1", "--missing", "0.0", "--commit"])
    assert rc == 0 and "quality" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.__main__ import main
    assert main(["summary"]) == 0
    assert "dataset_count" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_governance.__main__ import main
    assert main(["replay", "--dataset-id", "D1"]) == 0
    assert "deterministic" in capsys.readouterr().out


# ── 73~82. 보안/충돌회피/불변 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "portfolio", _j + "broker_readonly", _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.data_governance.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.data_governance.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", ".buy(", ".sell(",
                       "kill_switch(", "LiveExecutionEngine", "run_strategy"):
            assert banned not in src, f"{m} has execution verb {banned}"


def test_no_broker_or_portfolio():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.data_governance.{m}"))
        for banned in ("gateway.", "broker.submit", "broker_api", "portfolio.",
                       "rebalance(", "allocate_capital"):
            assert banned not in src, f"{m} has broker/portfolio verb {banned}"


def test_ledger_no_delete_api():
    import inspect
    from jarvis.data_governance import ledger as L
    src = inspect.getsource(L)
    for banned in ("def delete", "def update", "def remove", "def overwrite"):
        assert banned not in src


def test_existing_p101_ledger_unchanged(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # P10.1 스타일 datasets.jsonl 을 미리 두고, P9.8 작업이 절대 건드리지 않음을 확인
    p101 = sp("datasets.jsonl")
    with open(p101, "w") as f:
        f.write(json.dumps({"dataset_id": "P101", "dataset_hash": "sha256:x"}) + "\n")
    before = hashlib.sha256(open(p101, "rb").read()).hexdigest()
    eng = _eng()
    _ds(eng)
    eng.register_schema("D1", "1", {"a": "int"}, T0, commit=True)
    eng.validate_quality("D1", T0, checks={}, commit=True)
    after = hashlib.sha256(open(p101, "rb").read()).hexdigest()
    assert before == after   # 기존 P10.1 원장 무변경
    assert not os.path.exists(sp("quality_reports.jsonl"))   # P10.1 품질 원장도 미생성


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    for kw in ("data_governance", "dataset_write", "lineage_write"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def test_append_only_never_deletes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="A")
    n1 = len(ledger.read_datasets())
    _ds(eng, did="B")
    assert len(ledger.read_datasets()) > n1


def test_immutable_never_overwritten(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="D1", name="orig")
    h0 = ledger.read_datasets()[0]["dataset_hash"]
    with pytest.raises(ImmutableDatasetError):
        _ds(eng, did="D1", name="changed")
    assert ledger.read_datasets()[0]["dataset_hash"] == h0


def test_no_config_mutation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    import jarvis.config as cfg
    from jarvis.permissions.policy import FORBIDDEN
    a0, f0 = cfg.AUTONOMY_LEVEL, len(FORBIDDEN)
    eng = _eng()
    _ds(eng)
    eng.validate_quality("D1", T0, checks={}, commit=True)
    assert cfg.AUTONOMY_LEVEL == a0 and len(FORBIDDEN) == f0


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
