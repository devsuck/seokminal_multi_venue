"""P9.1 System Health Monitoring & Operations 테스트. **OPERATIONS-ONLY.**

레벨 등급(HEALTHY/DEGRADED/WARNING/CRITICAL/OFFLINE/UNKNOWN)·집계(overall/score)·수집기
(원장 데이터 관측·레지스트리/권한/설정)·해시체인·리플레이·결정성·변조탐지·중복방지·CLI·
금지import없음·집행능력없음·상태변경없음·불변식(FORBIDDEN=6, autonomy<MIN_LIVE).
"""
from __future__ import annotations

import json
import os

from jarvis.system_health import collectors as C
from jarvis.system_health import models as M
from jarvis.system_health.engine import SystemHealthEngine
from jarvis.system_health.models import (
    CRITICAL,
    DEGRADED,
    GENESIS,
    HEALTHY,
    OFFLINE,
    UNKNOWN,
    WARNING,
    SubsystemProbe,
    probe_hash,
)

_NOW = "2026-07-23T00:00:00Z"
_STALE_TS = "2026-07-01T00:00:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.system_health.ledger.state_path", sp)
    monkeypatch.setattr("jarvis.system_health.collectors.state_path", sp)
    return sp


def _probe(name, status, warnings=None, errors=None):
    warnings = warnings or []
    errors = errors or []
    return SubsystemProbe(name=name, status=status, healthy=status in {HEALTHY, DEGRADED},
                          warnings=warnings, errors=errors,
                          hash=probe_hash(name, status, warnings, errors))


# ── 1~7. models: 등급/집계 순수함수 ──
def test_severity_ordering():
    assert M.severity(CRITICAL) > M.severity(OFFLINE) > M.severity(WARNING)
    assert M.severity(WARNING) > M.severity(DEGRADED) > M.severity(HEALTHY)


def test_overall_status_max_severity():
    assert M.overall_status([HEALTHY, DEGRADED, WARNING]) == WARNING
    assert M.overall_status([HEALTHY, CRITICAL, WARNING]) == CRITICAL
    assert M.overall_status([HEALTHY, HEALTHY]) == HEALTHY


def test_overall_status_empty_is_unknown():
    assert M.overall_status([]) == UNKNOWN


def test_health_score_all_healthy():
    assert M.health_score([HEALTHY, HEALTHY, HEALTHY]) == 100.0


def test_health_score_mixed():
    # HEALTHY(100)+CRITICAL(0) → 50
    assert M.health_score([HEALTHY, CRITICAL]) == 50.0


def test_health_score_empty_is_zero():
    assert M.health_score([]) == 0.0


def test_is_ok():
    assert M.is_ok(HEALTHY) and M.is_ok(DEGRADED)
    assert not M.is_ok(WARNING) and not M.is_ok(CRITICAL)
    assert not M.is_ok(OFFLINE) and not M.is_ok(UNKNOWN)


# ── 8~11. 해시 결정성(latency/timestamp 제외) ──
def test_probe_hash_excludes_latency():
    a = SubsystemProbe(name="X", status=HEALTHY, latency_ms=5.0,
                       hash=probe_hash("X", HEALTHY, [], []))
    b = SubsystemProbe(name="X", status=HEALTHY, latency_ms=999.0,
                       hash=probe_hash("X", HEALTHY, [], []))
    assert a.hash == b.hash   # latency 달라도 해시 동일


def test_probe_hash_changes_on_status():
    assert probe_hash("X", HEALTHY, [], []) != probe_hash("X", CRITICAL, [], [])


def test_report_id_deterministic():
    ih = M.input_hash([{"name": "A", "status": HEALTHY}])
    assert M.report_id(ih) == M.report_id(ih)
    assert M.report_id(ih).startswith("SHR:")


def test_input_hash_deterministic():
    probes = [{"name": "A", "status": HEALTHY}, {"name": "B", "status": WARNING}]
    assert M.input_hash(probes) == M.input_hash(list(probes))


# ── 12~16. 원장 수집기 등급 규칙 ──
def test_collect_ledger_missing_is_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = C.collect_ledger_subsystem("Execution Control", "nonexistent.jsonl", _NOW)
    assert p.status == UNKNOWN and p.healthy is False


def test_collect_ledger_error_marker_critical(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("x.jsonl"), "w") as f:
        f.write(json.dumps({"overall_status": "FAILED", "timestamp": _NOW}) + "\n")
    p = C.collect_ledger_subsystem("Execution Risk", "x.jsonl", _NOW)
    assert p.status == CRITICAL and p.errors


def test_collect_ledger_warning_marker(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("x.jsonl"), "w") as f:
        f.write(json.dumps({"status": "WARNING", "timestamp": _NOW}) + "\n")
    p = C.collect_ledger_subsystem("Fill Reconciliation", "x.jsonl", _NOW)
    assert p.status == WARNING and p.warnings


def test_collect_ledger_stale_warning(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("x.jsonl"), "w") as f:
        f.write(json.dumps({"overall_status": "PASS", "timestamp": _STALE_TS}) + "\n")
    p = C.collect_ledger_subsystem("Order Lifecycle", "x.jsonl", _NOW)
    assert p.status == WARNING
    assert any("stale" in w for w in p.warnings)


def test_collect_ledger_healthy(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("x.jsonl"), "w") as f:
        f.write(json.dumps({"overall_status": "PASS", "timestamp": _NOW}) + "\n")
    p = C.collect_ledger_subsystem("Post Trade Analytics", "x.jsonl", _NOW)
    assert p.status == HEALTHY and p.healthy is True


def test_grade_latency_degraded():
    recs = [{"overall_status": "PASS", "timestamp": _NOW}]
    p = C._grade_records("Y", recs, _NOW, latency_ms=400.0)
    assert p.status == DEGRADED and p.healthy is True


# ── 17~22. 전 서브시스템 수집 & 관측 소유 수집기 ──
def test_collect_all_has_17(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    probes = C.collect_all(_NOW)
    assert len(probes) == 17
    assert all(isinstance(p, SubsystemProbe) for p in probes)


def test_subsystem_names_17():
    names = C.subsystem_names()
    assert len(names) == 17
    assert "Registry" in names and "Permissions" in names and "Paper Runtime" in names


def test_collect_registry(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)   # 격리된 빈 레지스트리 → UNKNOWN(정직)
    p = C.collect_registry(_NOW)
    assert p.name == "Registry" and p.status in {UNKNOWN, HEALTHY}


def test_collect_permissions_healthy():
    p = C.collect_permissions(_NOW)
    assert p.status == HEALTHY   # FORBIDDEN 불변식 유지
    assert "FORBIDDEN" in p.detail


def test_collect_configuration_live_closed():
    p = C.collect_configuration(_NOW)
    # autonomy=5 < MIN_LIVE=6 → live 폐쇄 → HEALTHY
    assert p.status == HEALTHY and "live 폐쇄" in p.detail


def test_collect_all_deterministic_order(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = [p.name for p in C.collect_all(_NOW)]
    b = [p.name for p in C.collect_all(_NOW)]
    assert a == b


# ── 23~30. 엔진 집계 ──
def test_check_injected_all_healthy():
    probes = [_probe("A", HEALTHY), _probe("B", HEALTHY)]
    r = SystemHealthEngine().check(_NOW, probes=probes)
    assert r.overall_status == HEALTHY and r.health_score == 100.0


def test_check_overall_critical():
    probes = [_probe("A", HEALTHY), _probe("B", CRITICAL, errors=["boom"])]
    r = SystemHealthEngine().check(_NOW, probes=probes)
    assert r.overall_status == CRITICAL
    assert any("B:boom" == e for e in r.errors)


def test_check_offline_probe():
    probes = [_probe("A", OFFLINE)]
    r = SystemHealthEngine().check(_NOW, probes=probes)
    assert r.overall_status == OFFLINE


def test_check_unknown_probe():
    probes = [_probe("A", UNKNOWN)]
    r = SystemHealthEngine().check(_NOW, probes=probes)
    assert r.overall_status == UNKNOWN


def test_check_summary_distribution():
    probes = [_probe("A", HEALTHY), _probe("B", WARNING, warnings=["w"]), _probe("C", HEALTHY)]
    r = SystemHealthEngine().check(_NOW, probes=probes)
    assert r.summary["total"] == 3
    assert r.summary["healthy"] == 2 and r.summary["unhealthy"] == 1
    assert r.summary["status_distribution"][HEALTHY] == 2
    assert "B" in r.summary["degraded"]


def test_check_health_score_value():
    probes = [_probe("A", HEALTHY), _probe("B", CRITICAL)]
    r = SystemHealthEngine().check(_NOW, probes=probes)
    assert r.health_score == 50.0


def test_check_aggregates_warnings():
    probes = [_probe("A", WARNING, warnings=["stale:1s"])]
    r = SystemHealthEngine().check(_NOW, probes=probes)
    assert "A:stale:1s" in r.warnings


def test_check_determinism_same_probes_same_hash():
    probes = [_probe("A", HEALTHY), _probe("B", WARNING, warnings=["w"])]
    r1 = SystemHealthEngine().check(_NOW, probes=probes)
    r2 = SystemHealthEngine().check("2099-01-01T00:00:00Z", probes=probes)
    assert r1.report_hash == r2.report_hash   # timestamp 달라도 헬스상태 동일 → 동일 해시


# ── 31~37. 원장·체인·검증 ──
def test_commit_appends_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_health import ledger
    SystemHealthEngine().check(_NOW, probes=[_probe("A", HEALTHY)], commit=True)
    assert len(ledger.read_reports()) == 1


def test_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_health import ledger
    probes = [_probe("A", HEALTHY)]
    SystemHealthEngine().check(_NOW, probes=probes, commit=True)
    SystemHealthEngine().check(_NOW, probes=probes, commit=True)   # 동일 → 중복 방지
    assert len(ledger.read_reports()) == 1


def test_chain_links(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_health import ledger
    r1 = SystemHealthEngine().check(_NOW, probes=[_probe("A", HEALTHY)], commit=True)
    r2 = SystemHealthEngine().check(_NOW, probes=[_probe("A", CRITICAL)], commit=True)
    reps = ledger.read_reports()
    assert len(reps) == 2
    assert reps[0]["previous_hash"] == GENESIS
    assert reps[1]["previous_hash"] == r1.report_hash
    assert r2.report_hash != r1.report_hash


def test_verify_chain_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_health.verify import verify_chain
    SystemHealthEngine().check(_NOW, probes=[_probe("A", HEALTHY)], commit=True)
    SystemHealthEngine().check(_NOW, probes=[_probe("A", WARNING, warnings=["w"])], commit=True)
    res = verify_chain()
    assert res["ok"] and res["n"] == 2


def test_verify_detects_tampering(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.system_health.verify import verify_chain
    SystemHealthEngine().check(_NOW, probes=[_probe("A", HEALTHY)], commit=True)
    path = sp("system_health_reports.jsonl")
    reps = [json.loads(ln) for ln in open(path) if ln.strip()]
    reps[0]["subsystems"][0]["status"] = CRITICAL   # 상태 변조(해시 재계산 불일치)
    with open(path, "w") as f:
        f.write(json.dumps(reps[0]) + "\n")
    res = verify_chain()
    assert not res["ok"] and res["reason"] == "report_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.system_health.verify import verify_chain
    SystemHealthEngine().check(_NOW, probes=[_probe("A", HEALTHY)], commit=True)
    SystemHealthEngine().check(_NOW, probes=[_probe("A", WARNING, warnings=["w"])], commit=True)
    path = sp("system_health_reports.jsonl")
    reps = [json.loads(ln) for ln in open(path) if ln.strip()]
    reps[1]["previous_hash"] = "sha256:deadbeef"   # 체인 절단
    with open(path, "w") as f:
        for r in reps:
            f.write(json.dumps(r) + "\n")
    res = verify_chain()
    assert not res["ok"] and res["reason"] == "previous_hash_broken"


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_health.verify import replay
    res = replay(SystemHealthEngine(), _NOW, probes=[_probe("A", HEALTHY)])
    assert res["deterministic"] is True


# ── 38~41. CLI ──
def test_cli_check(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_health.__main__ import main
    assert main(["check"]) == 0
    assert "overall_status" in capsys.readouterr().out


def test_cli_status(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_health.__main__ import main
    assert main(["status"]) == 0
    assert "n_reports" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_health.__main__ import main
    assert main(["verify"]) == 0   # 빈 체인 = ok
    assert "ok" in capsys.readouterr().out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_health.__main__ import main
    assert main(["summary"]) == 0
    assert "health_score" in capsys.readouterr().out


# ── 42. 금지 import 없음 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    forbidden = ("jarvis.execution.gateway", "jarvis.execution.arm", "jarvis.live_execution",
                 "jarvis.paper_execution", "jarvis.risk.governor")
    for m in ("models", "collectors", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.system_health.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


# ── 43. 집행 능력 없음 ──
def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "collectors", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.system_health.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", "route_order",
                       ".buy(", ".sell(", "arm_execution", "LiveExecutionEngine"):
            assert banned not in src, f"{m} has execution verb {banned}"


# ── 44. 권한 상승 없음(불변식) ──
def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("system_health" in a for a in ACTION_PERMISSIONS)
    assert not any("health" in a.lower() for a in ACTION_PERMISSIONS)


# ── 45. 무변이(다른 서브시스템 원장 불변) ──
def test_no_mutation_of_other_ledgers(tmp_path, monkeypatch):
    import hashlib
    sp = _iso(tmp_path, monkeypatch)
    # 페이퍼 원장(집행 소유)을 만들어두고 헬스 체크가 건드리지 않음을 확인
    paper = sp("paper_positions.jsonl")
    with open(paper, "w") as f:
        f.write(json.dumps({"overall_status": "PASS", "timestamp": _NOW}) + "\n")
    before = hashlib.sha256(open(paper, "rb").read()).hexdigest()
    SystemHealthEngine().check(_NOW, commit=True)
    assert hashlib.sha256(open(paper, "rb").read()).hexdigest() == before


# ── 46. 리포트는 운영관측 전용(거래 인가 필드 없음) ──
def test_report_is_operations_only():
    r = SystemHealthEngine().check(_NOW, probes=[_probe("A", HEALTHY)])
    keys = set(r.to_dict())
    assert keys == {"report_id", "timestamp", "overall_status", "health_score", "subsystems",
                    "summary", "warnings", "errors", "input_hash", "report_hash", "previous_hash"}
    for f in ("authorized", "submit", "execute", "route", "order_id", "arm"):
        assert f not in keys


# ── 47. 자율 레벨 불변식(live 폐쇄) ──
def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
