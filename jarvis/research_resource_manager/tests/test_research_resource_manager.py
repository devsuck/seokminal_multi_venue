"""P32 research_resource_manager 테스트 — 자원·사용·예산·배분(자동/프로비저닝 금지)·사용률·
계보·verify·replay·CLI·보안·READ ONLY 상위. RECORD ≠ ALLOCATE."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_resource_manager import ledger
from jarvis.research_resource_manager import models as M
from jarvis.research_resource_manager.engine import ResearchResourceManagerEngine
from jarvis.research_resource_manager.models import (
    BUDGET_CATEGORIES,
    FORBIDDEN_VERBS,
    RESOURCE_TYPES,
    USAGE_PURPOSES,
    UnknownEntityError,
    classify_utilization,
    content_hash,
    ratio,
    utilization,
)
from jarvis.research_resource_manager.verify import (
    allocation_integrity,
    duplicate_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_resource_manager.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchResourceManagerEngine()


def _res(e, rtype="GPU", name="a100-pool", cap=8.0, now=T[0]):
    return e.register_resource(rtype, name, cap, "gpus", "", now, commit=True).resource_id


# ═══════════════ resource registration ═══════════════
def test_register_resource(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().register_resource("GPU", "a100", 8.0, "gpus", "", T[0], commit=True)
    assert r.resource_id.startswith("RSR:")
    assert r.capacity == 8.0


def test_resource_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().register_resource("NOPE", "n", now=T[0], commit=True)


def test_resource_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_resource("GPU", "p", 8, now=T[0], commit=True).resource_id
    b = e.register_resource("GPU", "p", 16, now=T[1], commit=True).resource_id
    assert a == b
    assert len(ledger.read_resources()) == 1


def test_resource_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _res(e)
    assert any(a["artifact_type"] == "RESOURCE" for a in ledger.read_artifacts())


@pytest.mark.parametrize("rt", RESOURCE_TYPES)
def test_resource_types(tmp_path, monkeypatch, rt):
    _iso(tmp_path, monkeypatch)
    r = _eng().register_resource(rt, f"n-{rt}", 10, now=T[0], commit=True)
    assert r.resource_type == rt


# ═══════════════ usage ═══════════════
def test_record_usage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    u = e.record_usage(res, 3.0, "gpus", "TRAINING", "run1", T[1], commit=True)
    assert u.usage_id.startswith("RSU:")
    assert u.amount == 3.0


def test_usage_unknown_resource(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().record_usage("RSR:nope", 1, now=T[0], commit=True)


def test_usage_bad_purpose(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    with pytest.raises(ValueError):
        e.record_usage(res, 1, "gpus", "NOPE", now=T[1], commit=True)


@pytest.mark.parametrize("p", USAGE_PURPOSES)
def test_usage_purposes(p):
    assert p in USAGE_PURPOSES


# ═══════════════ budget ═══════════════
def test_record_budget(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    b = _eng().record_budget("COMPUTE", 10000.0, "USD", "2026-Q3", T[0], commit=True)
    assert b.budget_id.startswith("RSB:")
    assert b.amount == 10000.0


def test_budget_bad_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().record_budget("NOPE", 1, now=T[0], commit=True)


@pytest.mark.parametrize("c", BUDGET_CATEGORIES)
def test_budget_categories(c):
    assert c in BUDGET_CATEGORIES


# ═══════════════ allocation (no auto, no provision) ═══════════════
def test_record_allocation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    a = e.record_allocation(res, "exo:plan1", 2.0, "gpus", T[1], commit=True)
    assert a.allocation_id.startswith("RSL:")
    assert a.is_provisioned is False
    assert a.is_auto is False


def test_allocation_unknown_resource(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().record_allocation("RSR:nope", "e", 1, now=T[0], commit=True)


def test_allocation_never_provisioned(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    e.record_allocation(res, "e1", 1, now=T[1], commit=True)
    e.record_allocation(res, "e2", 2, now=T[2], commit=True)
    for a in ledger.read_allocations():
        assert a["is_provisioned"] is False
        assert a["is_auto"] is False


def test_allocation_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    a = e.record_allocation(res, "e", 1, now=T[1], commit=True)
    arts = {x["artifact_id"]: x for x in ledger.read_artifacts()}
    alloc_art = next(x for x in arts.values() if x["ref_id"] == a.allocation_id)
    assert alloc_art["parent_artifact"] == M.artifact_id(M.ART_RESOURCE, res)


# ═══════════════ utilization (READ ONLY) ═══════════════
def test_compute_utilization(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e, cap=10.0)
    e.record_usage(res, 4.0, "gpus", "TRAINING", now=T[1], commit=True)
    e.record_usage(res, 2.0, "gpus", "TRAINING", now=T[2], commit=True)
    u = e.compute_utilization(res)
    assert u["used"] == 6.0
    assert u["utilization"] == 0.6
    assert u["level"] == "MODERATE"


def test_compute_utilization_over_capacity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e, cap=2.0)
    e.record_usage(res, 3.0, "gpus", now=T[1], commit=True)
    u = e.compute_utilization(res)
    assert u["level"] == "OVER_CAPACITY"


def test_utilization_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().compute_utilization("RSR:nope")


def test_utilization_helper():
    assert utilization(3, 6) == 0.5
    assert utilization(1, 0) == 0.0


@pytest.mark.parametrize("rate,level", [
    (1.2, "OVER_CAPACITY"), (0.9, "HIGH"), (0.5, "MODERATE"), (0.1, "LOW"),
])
def test_classify_utilization(rate, level):
    assert classify_utilization(rate) == level


def test_ratio_helper():
    assert ratio(1, 4) == 0.25
    assert ratio(3, 0) == 0.0


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("strategy_generation", "experiment_orchestration", "autonomous_research",
              "research_automation", "production_readiness"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("exo_plans.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"plan_event_id": f"e{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("experiment_orchestration") == 3
    assert open(p).read() == before


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    e.record_usage(res, 2, "gpus", "TRAINING", now=T[1], commit=True)
    e.record_budget("COMPUTE", 5000, "USD", "Q3", T[2], commit=True)
    e.record_allocation(res, "e1", 1, now=T[3], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _res(e)
    p = sp("rrm_resources.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["capacity"] = 999
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    e.record_usage(res, 1, "gpus", now=T[1], commit=True)
    e.record_usage(res, 2, "gpus", now=T[2], commit=True)
    p = sp("rrm_usage.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_allocation_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    e.record_allocation(res, "e", 1, now=T[1], commit=True)
    assert allocation_integrity()["ok"] is True


def test_allocation_integrity_detects_provisioned(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    e.record_allocation(res, "e", 1, now=T[1], commit=True)
    p = sp("rrm_allocations.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_provisioned"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert allocation_integrity()["ok"] is False


def test_allocation_integrity_detects_auto(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    e.record_allocation(res, "e", 1, now=T[1], commit=True)
    p = sp("rrm_allocations.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_auto"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert allocation_integrity()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    e.record_usage(res, 1, "gpus", "ANALYSIS", now=T[1], commit=True)
    assert reference_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _res(e, name="a")
    _res(e, name="b", now=T[1])
    assert duplicate_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    e.record_allocation(res, "e", 1, now=T[1], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e)
    e.record_usage(res, 2, "gpus", now=T[1], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = _res(e, rtype="COMPUTE", cap=100.0)
    e.record_usage(res, 40, "cores", "SIMULATION", now=T[1], commit=True)
    e.record_budget("COMPUTE", 5000, "USD", "Q3", T[2], commit=True)
    e.record_allocation(res, "e1", 10, now=T[3], commit=True)
    r = e.generate_report("SYSTEM", T[4], commit=True)
    assert r.report_id.startswith("RSO:")
    assert r.is_binding is False
    assert r.resource_count == 1
    assert r.type_distribution.get("COMPUTE") == 1
    assert r.budget_by_category.get("COMPUTE") == 5000.0


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "ALLOCATE" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["TRACK", "RECORD", "OBSERVE", "MEASURE", "REGISTER"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


def test_forbidden_provision_membership():
    assert "PROVISION" in FORBIDDEN_VERBS
    assert "AUTO_ALLOCATE" in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.resource_id, ("GPU", "n"), "RSR:"),
    (M.usage_id, ("r", 0), "RSU:"),
    (M.budget_id, ("COMPUTE", "p"), "RSB:"),
    (M.allocation_id, ("r", "e", 0), "RSL:"),
    (M.report_id, ("s", "t"), "RSO:"),
    (M.artifact_id, ("RESOURCE", "r"), "RSA:"),
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
    res = _res(e)
    e.record_usage(res, 1, "gpus", now=T[1], commit=True)
    e.record_allocation(res, "e", 1, now=T[2], commit=True)
    s = e.summary(T[9])
    assert s.resource_count == 1
    assert s.usage_count == 1
    assert s.allocation_count == 1


def test_list_resources(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _res(e, name="a")
    _res(e, name="b", now=T[1])
    assert len(e.list_resources()) == 2


# ═══════════════ CLI ═══════════════
def test_cli_resource(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_resource_manager.__main__ import main
    assert main(["resource", "--type", "GPU", "--name", "a100", "--capacity", "8", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["resource"]["capacity"] == 8.0


def test_cli_usage_and_allocation(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_resource_manager.__main__ import main
    main(["resource", "--type", "GPU", "--name", "a100", "--capacity", "8", "--commit"])
    res = json.loads(capsys.readouterr().out)["resource"]["resource_id"]
    assert main(["usage", "--resource", res, "--amount", "2", "--purpose", "TRAINING",
                 "--commit"]) == 0
    capsys.readouterr()
    assert main(["allocation", "--resource", res, "--experiment", "e1", "--amount", "1",
                 "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["allocation"]["is_provisioned"] is False


def test_cli_budget(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_resource_manager.__main__ import main
    assert main(["budget", "--category", "COMPUTE", "--amount", "5000", "--commit"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_resource_manager.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_resource_manager.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_resource_manager.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_resource_manager.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().register_resource("GPU", "n", 8, now=T[0], commit=True)
    with pytest.raises(Exception):
        r.capacity = 5


def test_six_ledgers():
    assert len(ledger.ALL_LEDGERS) == 6


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rrm_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("rrm_resources.jsonl", "rrm_usage.jsonl", "rrm_budgets.jsonl",
                "rrm_allocations.jsonl", "rrm_reports.jsonl", "rrm_artifacts.jsonl"):
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
    bad = ("execute", "deploy", "trade", "allocate", "provision", "auto_allocate", "spin_up",
           "execute_trade", "place_order", "allocate_capital", "deploy_strategy", "launch_instance")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


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
    for attr in ("execute", "deploy", "trade", "allocate", "provision", "auto_allocate"):
        assert not hasattr(e, attr)


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("exo_plans.jsonl"), "w") as f:
        f.write(json.dumps({"plan_event_id": "exo:1"}) + "\n")
    e = _eng()
    # 자원 등록(추적만)
    gpu = e.register_resource("GPU", "a100-cluster", 16.0, "gpus", "", T[0], commit=True).resource_id
    store = e.register_resource("STORAGE", "research-nvme", 10000.0, "GB", "", T[1],
                                commit=True).resource_id
    # 예산 기록
    e.record_budget("COMPUTE", 20000.0, "USD", "2026-Q3", T[2], commit=True)
    # 사용 기록(관찰)
    e.record_usage(gpu, 6.0, "gpus", "TRAINING", "regime model", T[3], commit=True)
    e.record_usage(gpu, 4.0, "gpus", "BACKTEST", "overlay", T[4], commit=True)
    e.record_usage(store, 3000.0, "GB", "SIMULATION", "scenarios", T[5], commit=True)
    # 실험 배분 기록(자동 없음·프로비저닝 없음)
    a = e.record_allocation(gpu, "exo:plan1", 8.0, "gpus", T[6], commit=True)
    assert a.is_provisioned is False and a.is_auto is False
    # 사용률 관찰
    u = e.compute_utilization(gpu)
    assert u["used"] == 10.0
    assert u["utilization"] == 0.625  # 10/16
    # 리포트
    r = e.generate_report("SYSTEM", T[7], commit=True)
    assert r.resource_count == 2
    assert r.allocation_count == 1
    assert r.is_binding is False  # RECORD ≠ ALLOCATE
    # 배분은 결코 프로비저닝되지 않음
    assert all(x["is_provisioned"] is False and x["is_auto"] is False
               for x in ledger.read_allocations())
    assert open(sp("exo_plans.jsonl")).read()  # 상위 원장 불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[8])["deterministic"] is True
