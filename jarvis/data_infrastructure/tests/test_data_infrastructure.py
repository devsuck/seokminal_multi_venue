"""P41 data_infrastructure 테스트 — 소스·데이터셋 생애주기·버전(해시·계보)·피처·품질·재현·
verify·replay·CLI·보안·READ ONLY 상위. DATA ≠ TRADING."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.data_infrastructure import ledger
from jarvis.data_infrastructure import models as M
from jarvis.data_infrastructure.engine import DataInfrastructureEngine
from jarvis.data_infrastructure.models import (
    DATASET_STATES,
    FORBIDDEN_VERBS,
    QUALITY_DIMENSIONS,
    SOURCE_TYPES,
    D_ARCHIVED,
    D_AVAILABLE,
    D_CREATED,
    D_VALIDATED,
    IllegalDatasetTransition,
    UnknownEntityError,
    can_dataset_transition,
    content_hash,
    data_content_hash,
)
from jarvis.data_infrastructure.verify import (
    dataset_lifecycle_integrity,
    duplicate_integrity,
    lineage_integrity,
    quality_integrity,
    replay,
    verify_chain,
    version_lineage_integrity,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.data_infrastructure.ledger.state_path", sp)
    return sp


def _eng():
    return DataInfrastructureEngine()


def _ds(e, name="spx-daily", now=T[0]):
    return e.create_dataset(name, "", now, commit=True).dataset_id


# ═══════════════ data source ═══════════════
def test_register_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().register_source("MARKET_DATA", "vendor-x", "s3://x", "daily bars", T[0], commit=True)
    assert s.source_id.startswith("DTS:")
    assert s.source_type == "MARKET_DATA"


def test_source_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().register_source("NOPE", "n", now=T[0], commit=True)


def test_source_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_source("MARKET_DATA", "v", now=T[0], commit=True).source_id
    b = e.register_source("MARKET_DATA", "v", now=T[1], commit=True).source_id
    assert a == b
    assert len(ledger.read_sources()) == 1


@pytest.mark.parametrize("st", SOURCE_TYPES)
def test_source_types(tmp_path, monkeypatch, st):
    _iso(tmp_path, monkeypatch)
    s = _eng().register_source(st, f"n-{st}", now=T[0], commit=True)
    assert s.source_type == st


# ═══════════════ dataset lifecycle ═══════════════
def test_create_dataset(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_dataset("spx", "", T[0], commit=True)
    assert ev.to_state == D_CREATED
    assert ev.dataset_id.startswith("DTD:")
    assert ev.dataset_event_id.startswith("DTE:")


def test_dataset_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    e.validate_dataset(ds, now=T[1], commit=True)
    e.mark_available(ds, now=T[2], commit=True)
    e.archive_dataset(ds, now=T[3], commit=True)
    assert e.dataset_state(ds) == D_ARCHIVED


def test_dataset_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    with pytest.raises(IllegalDatasetTransition):
        e.mark_available(ds, now=T[1], commit=True)  # CREATED→AVAILABLE skip


def test_dataset_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_dataset("d", now=T[0], commit=True).dataset_id
    b = e.create_dataset("d", now=T[1], commit=True).dataset_id
    assert a == b
    assert len(ledger.dataset_events(a)) == 1


def test_dataset_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().validate_dataset("DTD:nope", now=T[1], commit=True)


def test_dataset_with_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = e.register_source("MARKET_DATA", "v", now=T[0], commit=True).source_id
    ds = e.create_dataset("d", sid, T[1], commit=True).dataset_id
    assert e._dataset_meta(ds)["source_id"] == sid


def test_dataset_unknown_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().create_dataset("d", "DTS:nope", T[0], commit=True)


def test_datasets_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    e.validate_dataset(ds, now=T[1], commit=True)
    assert ds in e.datasets_in_state(D_VALIDATED)


@pytest.mark.parametrize("frm,to,ok", [
    (D_CREATED, D_VALIDATED, True), (D_CREATED, D_AVAILABLE, False),
    (D_VALIDATED, D_AVAILABLE, True), (D_AVAILABLE, D_ARCHIVED, True),
    (D_ARCHIVED, D_VALIDATED, False), (D_CREATED, D_ARCHIVED, False),
])
def test_dataset_transition_matrix(frm, to, ok):
    assert can_dataset_transition(frm, to) is ok


@pytest.mark.parametrize("s", DATASET_STATES)
def test_dataset_states(s):
    assert s in DATASET_STATES


# ═══════════════ version (hash / lineage / reproducibility) ═══════════════
def test_create_version(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    v = e.create_version(ds, "v1", {"rows": [1, 2, 3]}, 3, {"cols": ["a"]}, T[1], commit=True)
    assert v.version_id.startswith("DTV:")
    assert v.content_hash.startswith("sha256:")
    assert v.row_count == 3


def test_version_reproducible_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    # 동일 payload → 동일 content_hash (재현성)
    assert data_content_hash({"rows": [1, 2]}) == data_content_hash({"rows": [1, 2]})
    assert data_content_hash({"rows": [1]}) != data_content_hash({"rows": [2]})


def test_version_lineage_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    v1 = e.create_version(ds, "v1", {"x": 1}, 1, {}, T[1], commit=True)
    v2 = e.create_version(ds, "v2", {"x": 2}, 2, {}, T[2], commit=True)
    assert v2.parent_version == v1.version_id


def test_version_unknown_dataset(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().create_version("DTD:nope", "v1", now=T[0], commit=True)


def test_version_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    a = e.create_version(ds, "v1", {"x": 1}, now=T[1], commit=True).version_id
    b = e.create_version(ds, "v1", {"x": 999}, now=T[2], commit=True).version_id
    assert a == b
    assert len(ledger.versions_for(ds)) == 1


def test_version_artifact_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    v = e.create_version(ds, "v1", {"x": 1}, now=T[1], commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    v_art = next(a for a in arts.values() if a["ref_id"] == v.version_id)
    assert v_art["parent_artifact"] == M.artifact_id(M.ART_DATASET, ds)


# ═══════════════ features ═══════════════
def test_prepare_features(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    f = e.prepare_features(ds, "momentum", ["ret_1d", "ret_5d", "vol_20d"], "", "momentum feats",
                           T[1], commit=True)
    assert f.feature_set_id.startswith("DTF:")
    assert len(f.features) == 3


def test_features_unknown_dataset(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().prepare_features("DTD:nope", "f", ["a"], now=T[0], commit=True)


# ═══════════════ quality ═══════════════
def test_record_quality(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    q = e.record_quality(ds, "COMPLETENESS", 0.98, True, [], "", T[1], commit=True)
    assert q.quality_id.startswith("DTQ:")
    assert q.passed is True


def test_quality_bad_dimension(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    with pytest.raises(ValueError):
        e.record_quality(ds, "NOPE", 0.5, now=T[1], commit=True)


def test_quality_clamped(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    q = e.record_quality(ds, "ACCURACY", 5.0, now=T[1], commit=True)
    assert q.score == 1.0


@pytest.mark.parametrize("d", QUALITY_DIMENSIONS)
def test_quality_dimensions(d):
    assert d in QUALITY_DIMENSIONS


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("data_governance", "alpha_intelligence", "simulation"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("dg_datasets.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"dataset_hash": f"h{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("data_governance") == 3
    assert open(p).read() == before


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = e.register_source("MARKET_DATA", "v", now=T[0], commit=True).source_id
    ds = e.create_dataset("d", sid, T[1], commit=True).dataset_id
    e.validate_dataset(ds, now=T[2], commit=True)
    e.create_version(ds, "v1", {"x": 1}, 1, {}, T[3], commit=True)
    e.prepare_features(ds, "f", ["a"], now=T[4], commit=True)
    e.record_quality(ds, "VALIDITY", 0.9, now=T[5], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _ds(e)
    p = sp("dinf_datasets.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    e.create_version(ds, "v1", {"x": 1}, now=T[1], commit=True)
    e.create_version(ds, "v2", {"x": 2}, now=T[2], commit=True)
    p = sp("dinf_versions.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _ds(e)
    p = sp("dinf_datasets.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_dataset_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    e.validate_dataset(ds, now=T[1], commit=True)
    assert dataset_lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _ds(e, "a")
    _ds(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_version_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    e.create_version(ds, "v1", {"x": 1}, now=T[1], commit=True)
    e.create_version(ds, "v2", {"x": 2}, now=T[2], commit=True)
    assert version_lineage_integrity()["ok"] is True


def test_quality_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    e.record_quality(ds, "TIMELINESS", 0.9, now=T[1], commit=True)
    assert quality_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    e.create_version(ds, "v1", {"x": 1}, now=T[1], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    e.create_version(ds, "v1", {"x": 1}, now=T[1], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_source("MARKET_DATA", "v", now=T[0], commit=True)
    ds = _ds(e, now=T[1])
    e.validate_dataset(ds, now=T[2], commit=True)
    e.mark_available(ds, now=T[3], commit=True)
    r = e.generate_report("SYSTEM", T[4], commit=True)
    assert r.report_id.startswith("DTR:")
    assert r.is_binding is False
    assert r.dataset_count == 1
    assert r.available_dataset_count == 1
    assert r.source_type_distribution.get("MARKET_DATA") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "TRADING" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["INGEST", "VALIDATE", "VERSION", "STORE", "RECORD"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.source_id, ("MARKET_DATA", "n"), "DTS:"),
    (M.dataset_id, ("n",), "DTD:"),
    (M.dataset_event_id, ("d", "CREATED", 0), "DTE:"),
    (M.version_id, ("d", "v1"), "DTV:"),
    (M.feature_set_id, ("d", "f"), "DTF:"),
    (M.quality_id, ("d", "ACCURACY", 0), "DTQ:"),
    (M.report_id, ("s", "t"), "DTR:"),
    (M.artifact_id, ("DATASET", "r"), "DTA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ summary ═══════════════
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ds = _ds(e)
    e.create_version(ds, "v1", {"x": 1}, now=T[1], commit=True)
    s = e.summary(T[9])
    assert s.dataset_count == 1
    assert s.version_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_source(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_infrastructure.__main__ import main
    assert main(["source", "--type", "MARKET_DATA", "--name", "v", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["source"]["source_type"] == "MARKET_DATA"


def test_cli_dataset_and_version(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_infrastructure.__main__ import main
    main(["dataset", "--name", "d", "--commit"])
    ds = json.loads(capsys.readouterr().out)["dataset"]["dataset_id"]
    assert main(["version", "--dataset", ds, "--version", "v1", "--rows", "100", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["version"]["row_count"] == 100


def test_cli_quality(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_infrastructure.__main__ import main
    main(["dataset", "--name", "d", "--commit"])
    ds = json.loads(capsys.readouterr().out)["dataset"]["dataset_id"]
    assert main(["quality", "--dataset", ds, "--dimension", "COMPLETENESS", "--score", "0.9",
                 "--passed", "--commit"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_infrastructure.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_infrastructure.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_infrastructure.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.data_infrastructure.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_dataset("d", now=T[0], commit=True)
    with pytest.raises(Exception):
        ev.name = "x"


def test_seven_ledgers():
    assert len(ledger.ALL_LEDGERS) == 7


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("dinf_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("dinf_sources.jsonl", "dinf_datasets.jsonl", "dinf_versions.jsonl",
                "dinf_features.jsonl", "dinf_quality.jsonl", "dinf_reports.jsonl",
                "dinf_artifacts.jsonl"):
        assert req in names


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.live_trading", "jarvis.portfolio_execution",
    "jarvis.live_portfolio", "jarvis.portfolio", "jarvis.order", "jarvis.deployment", "jarvis.live",
)


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(n.name.startswith(f) for f in _FORBIDDEN_IMPORTS), n.name


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_method_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "execute_trade", "place_order",
           "allocate_capital", "deploy_strategy", "activate_live", "broker_execution")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert ("claude" + "-opus") not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def purge_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


def test_engine_no_forbidden_methods():
    e = _eng()
    for attr in ("execute", "trade", "deploy", "allocate", "approve"):
        assert not hasattr(e, attr)


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("dg_datasets.jsonl"), "w") as f:
        f.write(json.dumps({"dataset_hash": "dg:1"}) + "\n")
    e = _eng()
    # 데이터 소스 → 데이터셋 → 검증 → 버전(재현성) → 피처 → 품질 → 가용
    src = e.register_source("MARKET_DATA", "prime-vendor", "s3://bars", "daily", T[0],
                            commit=True).source_id
    ds = e.create_dataset("spx-daily-bars", src, T[1], commit=True).dataset_id
    e.record_quality(ds, "COMPLETENESS", 0.99, True, [], "", T[2], commit=True)
    e.validate_dataset(ds, now=T[3], commit=True)
    v1 = e.create_version(ds, "2026-07-01", {"rows": list(range(1000))}, 1000, {"cols": ["o", "c"]},
                          T[4], commit=True)
    v2 = e.create_version(ds, "2026-07-02", {"rows": list(range(1010))}, 1010, {"cols": ["o", "c"]},
                          T[5], commit=True)
    assert v2.parent_version == v1.version_id  # 계보
    e.prepare_features(ds, "momentum", ["ret_1d", "ret_5d"], v2.version_id, "", T[6], commit=True)
    e.mark_available(ds, now=T[7], commit=True)
    assert e.dataset_state(ds) == D_AVAILABLE
    # 재현성: 동일 payload → 동일 해시
    assert data_content_hash({"rows": list(range(1000))}) == v1.content_hash
    r = e.generate_report("SYSTEM", T[8], commit=True)
    assert r.available_dataset_count == 1
    assert r.version_count == 2
    assert r.is_binding is False  # DATA ≠ TRADING
    assert open(sp("dg_datasets.jsonl")).read()  # 상위 원장 불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[9])["deterministic"] is True
