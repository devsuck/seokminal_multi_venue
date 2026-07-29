"""P10.1 Research Data Platform & Data Governance 테스트. **연구 데이터 관리 전용.**

레지스트리(불변·중복방지·버전)·스키마검증·품질(EXCELLENT/GOOD/WARNING/FAILED)·lineage(사이클/자기
참조/부모 검증)·스냅샷 재현성·verify(체인/변조/중복/lineage무결성)·replay·CLI·보안(금지import·집행/
브로커/포트폴리오 없음·삭제 API 없음·불변·append-only).

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_data import ledger
from jarvis.research_data import models as M
from jarvis.research_data.engine import ResearchDataEngine
from jarvis.research_data.models import (
    EXCELLENT,
    FAILED,
    GOOD,
    WARNING,
    ImmutableDatasetError,
    ImmutableFeatureError,
    LineageError,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_data.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchDataEngine()


def _ds(eng, did="D1", sv="1", asset="equity", commit=True):
    return eng.register_dataset(did, f"{did} name", "desc", asset, "src", "1d",
                                "2020-01-01", "2024-01-01", sv, "owner", T0, commit=commit)


def _feat(eng, fid="F1", cv="1", src="D1", commit=True):
    return eng.register_feature(fid, f"{fid} name", "desc", "momentum", src, cv, T0,
                                commit=commit)


# ── 1~17. models 순수 ──
def test_dataset_hash_deterministic():
    a = M.dataset_hash("D", "n", "d", "equity", "s", "1d", "2020", "2024", "1")
    b = M.dataset_hash("D", "n", "d", "equity", "s", "1d", "2020", "2024", "1")
    assert a == b


def test_dataset_hash_changes():
    a = M.dataset_hash("D", "n", "d", "equity", "s", "1d", "2020", "2024", "1")
    b = M.dataset_hash("D", "n", "d", "crypto", "s", "1d", "2020", "2024", "1")
    assert a != b


def test_feature_hash_deterministic():
    assert M.feature_hash("F", "n", "d", "c", "D", "1") == M.feature_hash("F", "n", "d", "c", "D", "1")


def test_content_hash_excludes_hash_fields():
    a = {"x": 1, "previous_hash": "p1", "record_hash": "r1"}
    b = {"x": 1, "previous_hash": "p2", "record_hash": "r2"}
    assert M.content_hash(a) == M.content_hash(b)


def test_quality_score_perfect():
    assert M.quality_score(0.0, 0.0, 0, True, True) == 100


def test_quality_score_penalties():
    assert M.quality_score(0.1, 0.0, 0, True, True) == 96   # 0.1*40=4
    assert M.quality_score(0.0, 0.1, 0, True, True) == 97   # 0.1*30=3
    assert M.quality_score(0.0, 0.0, 100, True, True) == 90  # 100*0.1=10


def test_quality_score_schema_invalid():
    assert M.quality_score(0.0, 0.0, 0, False, True) == 70   # -30
    assert M.quality_score(0.0, 0.0, 0, True, False) == 90   # -10


def test_quality_status_thresholds():
    assert M.quality_status(95, True) == EXCELLENT
    assert M.quality_status(80, True) == GOOD
    assert M.quality_status(70, True) == WARNING
    assert M.quality_status(40, True) == FAILED
    assert M.quality_status(95, False) == FAILED   # 스키마 무효 → FAILED


def test_snapshot_hash_deterministic():
    a = M.snapshot_hash({"D1": "1"}, {"F1": "1"})
    b = M.snapshot_hash({"D1": "1"}, {"F1": "1"})
    assert a == b


def test_snapshot_hash_order_independent():
    a = M.snapshot_hash({"D1": "1", "D2": "1"}, {})
    b = M.snapshot_hash({"D2": "1", "D1": "1"}, {})
    assert a == b


def test_compute_metrics_missing():
    recs = [{"a": 1, "b": None}, {"a": 2, "b": 3}]
    m = M.compute_metrics(recs, ["a", "b"])
    assert m["missing_ratio"] == 0.25 and m["schema_valid"] is False


def test_compute_metrics_duplicate():
    recs = [{"a": 1}, {"a": 1}, {"a": 2}]
    m = M.compute_metrics(recs, ["a"])
    assert round(m["duplicate_ratio"], 4) == round(1 / 3, 4)


def test_compute_metrics_timestamp_continuity():
    good = [{"timestamp": "t1"}, {"timestamp": "t2"}]
    bad = [{"timestamp": "t2"}, {"timestamp": "t1"}]
    assert M.compute_metrics(good, [])["timestamp_continuity"] is True
    assert M.compute_metrics(bad, [])["timestamp_continuity"] is False


def test_compute_metrics_empty():
    m = M.compute_metrics([], ["a"])
    assert m["missing_ratio"] == 0.0 and m["schema_valid"] is True


def test_detect_cycle_none():
    assert M.detect_lineage_cycle([("B", "A"), ("C", "B")]) == []


def test_detect_cycle_self():
    assert M.detect_lineage_cycle([], "A", "A") == ["A", "A"]


def test_detect_cycle_indirect():
    cyc = M.detect_lineage_cycle([("B", "A"), ("A", "B")])
    assert cyc and cyc[0] == cyc[-1]


# ── 18~24. Dataset Registry ──
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
    _ds(eng, did="D1", sv="1", asset="equity")
    with pytest.raises(ImmutableDatasetError):
        _ds(eng, did="D1", sv="1", asset="crypto")   # 동일 id+schema, 내용 상이


def test_register_new_schema_version_allowed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, sv="1")
    _ds(eng, sv="2")
    assert len(ledger.read_datasets()) == 2


def test_active_datasets_latest_version(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, sv="1")
    _ds(eng, sv="2")
    active = eng._active_datasets()
    assert len(active) == 1 and active[0]["schema_version"] == "2"


def test_dataset_hash_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _ds(_eng())
    assert ledger.read_datasets()[0]["dataset_hash"].startswith("sha256:")


# ── 25~27. Feature Registry ──
def test_register_feature_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _feat(_eng())
    assert f.feature_id == "F1" and f.feature_hash.startswith("sha256:")


def test_register_feature_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_feature("F1", "n", "d", "momentum", "D1", "1", T0, commit=True)
    with pytest.raises(ImmutableFeatureError):
        eng.register_feature("F1", "n2", "d", "momentum", "D1", "1", T0, commit=True)


def test_register_feature_new_version(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _feat(eng, cv="1")
    _feat(eng, cv="2")
    assert len(ledger.read_features()) == 2


# ── 28~31. Schema Validation ──
def test_validate_schema_valid(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    recs = [{"dataset_id": "D", "name": "n", "asset_class": "equity", "source": "s",
             "frequency": "1d", "schema_version": "1"}]
    v = _eng().validate_schema(recs)
    assert v["schema_valid"] is True and v["missing_fields"] == []


def test_validate_schema_missing_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    recs = [{"dataset_id": "D"}]
    v = _eng().validate_schema(recs, required_fields=["dataset_id", "name"])
    assert v["schema_valid"] is False and "name" in v["missing_fields"]


def test_validate_schema_timestamp_broken(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    recs = [{"a": 1, "timestamp": "t2"}, {"a": 2, "timestamp": "t1"}]
    v = _eng().validate_schema(recs, required_fields=["a"])
    assert v["timestamp_continuity"] is False


def test_validate_schema_duplicate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    recs = [{"a": 1}, {"a": 1}]
    v = _eng().validate_schema(recs, required_fields=["a"])
    assert v["duplicate_ratio"] > 0


# ── 32~38. Data Quality ──
def test_assess_quality_excellent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess_quality("D1", T0, metrics={"missing_ratio": 0.0, "duplicate_ratio": 0.0,
                              "outlier_count": 0, "schema_valid": True,
                              "timestamp_continuity": True})
    assert r.quality_score == 100 and r.status == EXCELLENT


def test_assess_quality_from_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    recs = [{"a": 1, "timestamp": "t1"}, {"a": 2, "timestamp": "t2"}]
    r = _eng().assess_quality("D1", T0, records=recs, required_fields=["a"])
    assert r.status == EXCELLENT


def test_assess_quality_failed_schema_invalid(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess_quality("D1", T0, metrics={"missing_ratio": 0.0, "duplicate_ratio": 0.0,
                              "outlier_count": 0, "schema_valid": False,
                              "timestamp_continuity": True})
    assert r.status == FAILED


def test_assess_quality_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess_quality("D1", T0, metrics={"missing_ratio": 0.7, "duplicate_ratio": 0.0,
                              "outlier_count": 0, "schema_valid": True,
                              "timestamp_continuity": True})
    assert r.status == WARNING and r.quality_score == 72


def test_quality_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().assess_quality("D1", T0, metrics={"missing_ratio": 0.0, "duplicate_ratio": 0.0,
                          "outlier_count": 0, "schema_valid": True,
                          "timestamp_continuity": True}, commit=True)
    assert len(ledger.read_quality_reports()) == 1


def test_quality_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    mt = {"missing_ratio": 0.0, "duplicate_ratio": 0.0, "outlier_count": 0,
          "schema_valid": True, "timestamp_continuity": True}
    eng.assess_quality("D1", T0, metrics=mt, commit=True)
    eng.assess_quality("D1", T1, metrics=mt, commit=True)   # 동일 메트릭 → 중복 방지
    assert len(ledger.read_quality_reports()) == 1


def test_quality_report_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess_quality("D1", T0, metrics={"missing_ratio": 0.0, "duplicate_ratio": 0.0,
                              "outlier_count": 0, "schema_valid": True,
                              "timestamp_continuity": True}).to_dict()
    for k in ("missing_ratio", "duplicate_ratio", "outlier_count", "schema_valid",
              "timestamp_continuity", "quality_score", "status"):
        assert k in r


# ── 39~45. Lineage ──
def test_register_lineage_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="RAW")
    _ds(eng, did="CLEAN")
    lr = eng.register_lineage("CLEAN", "RAW", "clean", "1", T0, commit=True)
    assert lr.parent_dataset == "RAW" and lr.dataset_id == "CLEAN"


def test_lineage_self_reference_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="A")
    with pytest.raises(LineageError):
        eng.register_lineage("A", "A", "t", "1", T0, commit=True)


def test_lineage_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="A")
    _ds(eng, did="B")
    eng.register_lineage("B", "A", "t", "1", T0, commit=True)
    with pytest.raises(LineageError):
        eng.register_lineage("A", "B", "t", "1", T0, commit=True)   # A->B->A 사이클


def test_lineage_missing_parent_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="CHILD")
    with pytest.raises(LineageError):
        eng.register_lineage("CHILD", "GHOST", "t", "1", T0, require_parent=True, commit=True)


def test_lineage_chain_order(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for did in ("RAW", "CLEAN", "FEAT"):
        _ds(eng, did=did)
    eng.register_lineage("CLEAN", "RAW", "clean", "1", T0, commit=True)
    eng.register_lineage("FEAT", "CLEAN", "feature", "1", T0, commit=True)
    assert eng.lineage_chain("FEAT") == ["RAW", "CLEAN", "FEAT"]


def test_lineage_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="A")
    _ds(eng, did="B")
    eng.register_lineage("B", "A", "t", "1", T0, commit=True)
    assert len(ledger.read_lineage()) == 1


def test_lineage_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="A")
    _ds(eng, did="B")
    eng.register_lineage("B", "A", "t", "1", T0, commit=True)
    eng.register_lineage("B", "A", "t", "1", T0, commit=True)   # 동일 → 중복 방지
    assert len(ledger.read_lineage()) == 1


# ── 46~51. Snapshot(재현성) ──
def test_snapshot_captures_versions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="D1", sv="2")
    _feat(eng, fid="F1", cv="3")
    s = eng.snapshot(T0)
    assert s.dataset_versions == {"D1": "2"} and s.feature_versions == {"F1": "3"}


def test_snapshot_deterministic_same_versions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng)
    assert eng.snapshot(T0).snapshot_id == eng.snapshot(T1).snapshot_id


def test_snapshot_reproducibility(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="D1", sv="1")
    _feat(eng, fid="F1", cv="1")
    h1 = eng.snapshot(T0).snapshot_hash
    # 동일 dataset/feature 버전 조합 → 동일 hash(다른 엔진 인스턴스)
    h2 = ResearchDataEngine().snapshot(T1).snapshot_hash
    assert h1 == h2


def test_snapshot_changes_on_new_version(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, sv="1")
    h1 = eng.snapshot(T0).snapshot_hash
    _ds(eng, sv="2")
    h2 = eng.snapshot(T0).snapshot_hash
    assert h1 != h2


def test_snapshot_append_dedup(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng)
    eng.snapshot(T0, commit=True)
    eng.snapshot(T1, commit=True)
    assert len(ledger.read_snapshots()) == 1


def test_snapshot_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().snapshot(T0)
    assert s.dataset_count == 0 and s.feature_count == 0


# ── 52~54. Summary ──
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="D1")
    _ds(eng, did="D2")
    _feat(eng, fid="F1")
    s = eng.summary(T0)
    assert s.dataset_count == 2 and s.feature_count == 1


def test_summary_avg_quality(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.assess_quality("D1", T0, metrics={"missing_ratio": 0.0, "duplicate_ratio": 0.0,
                       "outlier_count": 0, "schema_valid": True,
                       "timestamp_continuity": True}, commit=True)
    assert eng.summary(T0).average_quality_score == 100.0


def test_summary_failed_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.assess_quality("D1", T0, metrics={"missing_ratio": 0.0, "duplicate_ratio": 0.0,
                       "outlier_count": 0, "schema_valid": False,
                       "timestamp_continuity": True}, commit=True)
    assert eng.summary(T0).failed_datasets == 1


# ── 55~62. Verify / tamper / replay / lineage integrity ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_data.verify import verify_chain
    res = verify_chain()
    assert res["ok"] and res["n"] == 0


def test_verify_chain_intact_after_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_data.verify import verify_chain
    eng = _eng()
    _ds(eng, did="RAW")
    _ds(eng, did="CLEAN")
    _feat(eng)
    eng.register_lineage("CLEAN", "RAW", "clean", "1", T0, commit=True)
    eng.snapshot(T0, commit=True)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 3


def test_verify_detects_dataset_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_data.verify import verify_chain
    _ds(_eng())
    path = sp("datasets.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["asset_class"] = "TAMPERED"
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    res = verify_chain()
    assert res["ledgers"]["datasets.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_data.verify import verify_chain
    eng = _eng()
    _ds(eng, sv="1")
    _ds(eng, sv="2")
    path = sp("datasets.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    res = verify_chain()
    assert res["ledgers"]["datasets.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_data.verify import verify_chain
    _ds(_eng())
    path = sp("datasets.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    res = verify_chain()
    assert res["ledgers"]["datasets.jsonl"]["reason"] in {"duplicate_id", "previous_hash_broken"}


def test_verify_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_data.verify import lineage_integrity
    eng = _eng()
    _ds(eng, did="A")
    _ds(eng, did="B")
    eng.register_lineage("B", "A", "t", "1", T0, commit=True)
    assert lineage_integrity()["ok"] is True


def test_verify_lineage_integrity_detects_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_data.verify import lineage_integrity
    # 사이클 lineage 행 직접 주입(무결성 검사는 해시 무관)
    with open(sp("lineage.jsonl"), "w") as f:
        f.write(json.dumps({"lineage_id": "L1", "dataset_id": "B", "parent_dataset": "A"}) + "\n")
        f.write(json.dumps({"lineage_id": "L2", "dataset_id": "A", "parent_dataset": "B"}) + "\n")
    res = lineage_integrity()
    assert res["ok"] is False and res["cycle"]


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng)
    _feat(eng)
    from jarvis.research_data.verify import replay
    assert replay(eng, T0)["deterministic"] is True


# ── 63~69. CLI ──
def test_cli_register(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_data.__main__ import main
    rc = main(["register", "--dataset-id", "D1", "--name", "n", "--asset-class", "equity",
               "--source", "s", "--frequency", "1d", "--schema-version", "1",
               "--owner", "o", "--commit"])
    assert rc == 0 and "dataset" in capsys.readouterr().out


def test_cli_quality(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_data.__main__ import main
    rc = main(["quality", "--dataset-id", "D1", "--missing", "0.0", "--commit"])
    assert rc == 0 and "quality" in capsys.readouterr().out


def test_cli_lineage(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_data.__main__ import main
    rc = main(["lineage", "--dataset-id", "CLEAN", "--parent", "RAW",
               "--transformation", "clean", "--version", "1", "--commit"])
    assert rc == 0 and "lineage" in capsys.readouterr().out


def test_cli_snapshot(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_data.__main__ import main
    assert main(["snapshot", "--commit"]) == 0
    assert "snapshot_hash" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_data.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_data.__main__ import main
    assert main(["summary"]) == 0
    assert "dataset_count" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_data.__main__ import main
    assert main(["replay"]) == 0
    assert "deterministic" in capsys.readouterr().out


# ── 70~79. 보안/불변/무변경 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "portfolio", _j + "broker_readonly", _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.research_data.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.research_data.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", ".buy(", ".sell(",
                       "kill_switch(", "LiveExecutionEngine", "run_strategy", "execute_trade"):
            assert banned not in src, f"{m} has execution verb {banned}"


def test_no_broker_or_portfolio():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.research_data.{m}"))
        for banned in ("gateway.", "broker.submit", "broker_api", "portfolio.",
                       "rebalance(", "allocate_capital"):
            assert banned not in src, f"{m} has broker/portfolio verb {banned}"


def test_no_strategy_runtime():
    import importlib
    import inspect
    for m in ("engine", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.research_data.{m}"))
        for banned in ("StrategyRunner", "strategy_runtime", "deploy_strategy", "live_capital"):
            assert banned not in src, f"{m} has strategy runtime verb {banned}"


def test_ledger_no_delete_api():
    import inspect
    from jarvis.research_data import ledger as L
    src = inspect.getsource(L)
    for banned in ("def delete", "def update", "def remove", "def overwrite"):
        assert banned not in src, f"ledger exposes mutation API: {banned}"


def test_append_only_never_deletes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, sv="1")
    n1 = len(ledger.read_datasets())
    _ds(eng, sv="2")
    assert len(ledger.read_datasets()) > n1


def test_immutable_version_never_overwritten(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ds(eng, did="D1", sv="1", asset="equity")
    h0 = ledger.read_datasets()[0]["dataset_hash"]
    with pytest.raises(ImmutableDatasetError):
        _ds(eng, did="D1", sv="1", asset="crypto")
    assert ledger.read_datasets()[0]["dataset_hash"] == h0


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    for kw in ("research_data", "dataset_write", "data_governance"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def test_no_config_or_permission_mutation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    import jarvis.config as cfg
    from jarvis.permissions.policy import FORBIDDEN
    a0, f0 = cfg.AUTONOMY_LEVEL, len(FORBIDDEN)
    eng = _eng()
    _ds(eng)
    _feat(eng)
    eng.snapshot(T0, commit=True)
    assert cfg.AUTONOMY_LEVEL == a0 and len(FORBIDDEN) == f0


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
