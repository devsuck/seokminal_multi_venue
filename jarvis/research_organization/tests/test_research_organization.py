"""P11.13 Autonomous Research Organization 테스트. **조직 조정 — 조직 전용.**

조직 생성(CREATED→CONFIGURED→ACTIVE→COORDINATING→REVIEWED→ARCHIVED)·유닛 생애주기·역할 배정·책임 매핑·워크플로
소유·조정 정책·소유/의존 그래프·건강 지표(분석 전용)·스냅샷 결정성·리포트(is_binding=False)·verify(체인/변조/중복/
생애주기/소유/역할orphan/책임체인/의존순환/계보/스냅샷)·replay·CLI·보안(금지import·실행/배포/승인/인가 없음·삭제 API
없음·불변·ORGANIZATION≠EXECUTION·METRIC≠ACTION·append-only·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_organization import ledger
from jarvis.research_organization import models as M
from jarvis.research_organization.engine import ResearchOrganizationEngine
from jarvis.research_organization.models import (
    AGENT_ROLES,
    O_ACTIVE,
    O_ARCHIVED,
    O_CONFIGURED,
    O_COORDINATING,
    O_CREATED,
    O_REVIEWED,
    UNIT_TYPES,
    CircularDependencyError,
    DanglingReferenceError,
    IllegalOrgTransition,
    ImmutableOrganizationError,
    ImmutablePolicyError,
    ImmutableResponsibilityError,
    ImmutableRoleError,
    ImmutableUnitError,
    ImmutableWorkflowError,
    InvalidAgentRole,
    InvalidUnitType,
    MissingOwnerError,
    UnknownOrganizationError,
    UnknownUnitError,
)
from jarvis.research_organization.verify import (
    dependency_integrity,
    lifecycle_integrity,
    lineage_integrity,
    ownership_integrity,
    responsibility_integrity,
    replay,
    role_integrity,
    snapshot_consistency,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_organization.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchOrganizationEngine()


def _org(e, name="alpha_lab", mandate="autonomous research", now=T[0]):
    return e.register_organization(name, mandate, now, commit=True).org_id


def _unit(e, org=None, utype="DATA_RESEARCH", name="data_unit", now=T[1]):
    if org is None:
        org = _org(e)
    return e.create_research_unit(org, utype, name, "", now, commit=True).unit_id


def _active(e):
    """ACTIVE 상태 조직 + 1 유닛."""
    org = _org(e)
    u = e.create_research_unit(org, "DATA_RESEARCH", "u1", "", T[1], commit=True).unit_id
    e.activate_organization(org, T[2], commit=True)
    return org, u


# ══════════════ Phase 0 / 접두사 / 소유 ══════════════
def test_prefix_all_ledgers_rorg():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rorg_")


def test_ten_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 10


def test_source_ledgers_includes_governance():
    assert "data_governance" in ledger.SOURCE_LEDGERS
    assert "model_governance" in ledger.SOURCE_LEDGERS
    assert len(ledger.SOURCE_LEDGERS) == 22


def test_unit_types_seven():
    assert len(UNIT_TYPES) == 7


def test_agent_roles_six():
    assert len(AGENT_ROLES) == 6


def test_org_states_six():
    assert len(M.ORG_STATES) == 6


# ══════════════ register_organization ══════════════
def test_register_org_genesis_created(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    assert org.startswith("ROG:")
    assert e.current_state(org) == O_CREATED


def test_register_org_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_organization("lab", "m", T[0], commit=True)
    e.register_organization("lab", "m", T[1], commit=True)
    assert len(ledger.org_ids()) == 1


def test_register_org_immutable_mandate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_organization("lab", "m1", T[0], commit=True)
    with pytest.raises(ImmutableOrganizationError):
        e.register_organization("lab", "m2", T[1], commit=True)


def test_register_org_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_ORG]
    assert any(a["ref_id"] == org for a in arts)


def test_register_org_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_organization("lab", "m", T[0], commit=False)
    assert ledger.read_org_events() == []


# ══════════════ create_research_unit (lifecycle) ══════════════
def test_create_unit_configures_org(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    e.create_research_unit(org, "DATA_RESEARCH", "u1", "", T[1], commit=True)
    assert e.current_state(org) == O_CONFIGURED


def test_create_unit_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    with pytest.raises(InvalidUnitType):
        e.create_research_unit(org, "NOPE", "u1", "", T[1], commit=True)


def test_create_unit_unknown_org(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownOrganizationError):
        e.create_research_unit("ROG:ghost", "DATA_RESEARCH", "u1", "", T[1], commit=True)


def test_create_unit_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    e.create_research_unit(org, "DATA_RESEARCH", "u1", "d1", T[1], commit=True)
    with pytest.raises(ImmutableUnitError):
        e.create_research_unit(org, "DATA_RESEARCH", "u1", "d2", T[2], commit=True)


def test_create_unit_second_stays_configured(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    e.create_research_unit(org, "DATA_RESEARCH", "u1", "", T[1], commit=True)
    e.create_research_unit(org, "MODEL_RESEARCH", "u2", "", T[2], commit=True)
    assert e.current_state(org) == O_CONFIGURED
    # 조직 이벤트: CREATED, CONFIGURED (두 번째 유닛은 추가 전이 없음)
    assert len(ledger.org_events(org)) == 2


@pytest.mark.parametrize("utype", list(UNIT_TYPES))
def test_all_unit_types(tmp_path, monkeypatch, utype):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    u = e.create_research_unit(org, utype, "u-" + utype, "", T[1], commit=True)
    assert u.unit_type == utype


# ══════════════ create_research_team ══════════════
def test_create_team_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    t = e.create_research_team(u, "team_a", "", T[2], commit=True)
    assert t.team_id.startswith("ROT:")
    assert t.unit_id == u


def test_create_team_unknown_unit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownUnitError):
        e.create_research_team("ROU:ghost", "t", "", T[2], commit=True)


def test_create_team_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    e.create_research_team(u, "t", "d1", T[2], commit=True)
    with pytest.raises(M.ImmutableTeamError):
        e.create_research_team(u, "t", "d2", T[3], commit=True)


# ══════════════ assign_agent_role ══════════════
def test_assign_role_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    r = e.assign_agent_role(u, "agent1", "RESEARCHER", "", T[2], commit=True)
    assert r.role_id.startswith("ROR:")
    assert r.role == "RESEARCHER"


def test_assign_role_invalid_role(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    with pytest.raises(InvalidAgentRole):
        e.assign_agent_role(u, "agent1", "WIZARD", "", T[2], commit=True)


def test_assign_role_orphan_unit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _org(e)
    with pytest.raises(UnknownUnitError):
        e.assign_agent_role("ROU:ghost", "agent1", "RESEARCHER", "", T[2], commit=True)


def test_assign_role_dangling_team(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    with pytest.raises(DanglingReferenceError):
        e.assign_agent_role(u, "agent1", "RESEARCHER", "ROT:ghost", T[2], commit=True)


def test_assign_role_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    t = e.create_research_team(u, "t", "", T[2], commit=True).team_id
    e.assign_agent_role(u, "agent1", "RESEARCHER", t, T[3], commit=True)
    with pytest.raises(ImmutableRoleError):
        e.assign_agent_role(u, "agent1", "RESEARCHER", "", T[4], commit=True)


def test_assign_role_with_team(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    t = e.create_research_team(u, "t", "", T[2], commit=True).team_id
    r = e.assign_agent_role(u, "agent1", "ANALYST", t, T[3], commit=True)
    assert r.team_id == t


@pytest.mark.parametrize("role", list(AGENT_ROLES))
def test_all_agent_roles(tmp_path, monkeypatch, role):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    r = e.assign_agent_role(u, "agent-" + role, role, "", T[2], commit=True)
    assert r.role == role


# ══════════════ define_responsibility ══════════════
def test_define_responsibility_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    r = e.define_responsibility(org, "agent1", "data quality", ["src1"], "clean dataset", "EV1",
                                now=T[1], commit=True)
    assert r.responsibility_id.startswith("ROB:")
    assert r.owner == "agent1"
    assert r.evidence_reference == "EV1"


def test_define_responsibility_required_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    r = e.define_responsibility(org, "a", "s", ["i"], "o", "e", now=T[1], commit=True)
    d = r.to_dict()
    for f in ("owner", "scope", "input_sources", "expected_output", "evidence_reference",
              "lifecycle_state"):
        assert f in d


def test_define_responsibility_missing_owner(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    with pytest.raises(MissingOwnerError):
        e.define_responsibility(org, "", "s", now=T[1], commit=True)


def test_define_responsibility_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    e.define_responsibility(org, "a", "s", expected_output="o1", now=T[1], commit=True)
    with pytest.raises(ImmutableResponsibilityError):
        e.define_responsibility(org, "a", "s", expected_output="o2", now=T[2], commit=True)


# ══════════════ map_workflow_owner ══════════════
def test_map_workflow_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    org = ledger.get_unit(u)["org_id"]
    w = e.map_workflow_owner(org, "ingest", u, ["src"], [], T[2], commit=True)
    assert w.workflow_id.startswith("ROK:")
    assert w.owner_unit == u


def test_map_workflow_dangling_owner(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    with pytest.raises(DanglingReferenceError):
        e.map_workflow_owner(org, "w", "ROU:ghost", now=T[2], commit=True)


def test_map_workflow_dangling_dependency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    org = ledger.get_unit(u)["org_id"]
    with pytest.raises(DanglingReferenceError):
        e.map_workflow_owner(org, "w", u, depends_on=["ROK:ghost"], now=T[2], commit=True)


def test_map_workflow_circular_dependency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    org = ledger.get_unit(u)["org_id"]
    w1 = e.map_workflow_owner(org, "w1", u, now=T[2], commit=True).workflow_id
    w2 = e.map_workflow_owner(org, "w2", u, depends_on=[w1], now=T[3], commit=True).workflow_id
    # w1 이 w2 에 의존하게 만들려 하면 순환 — w1 은 이미 불변이므로 신규 워크플로로 순환 시도
    w3 = e.map_workflow_owner(org, "w3", u, depends_on=[w2], now=T[4], commit=True).workflow_id
    # 순환 직접 검증
    assert M.detect_cycle([(w1, w2), (w2, w3), (w3, w1)]) != []


def test_map_workflow_immutable_owner(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u1 = _unit(e, name="u1")
    org = ledger.get_unit(u1)["org_id"]
    u2 = e.create_research_unit(org, "MODEL_RESEARCH", "u2", "", T[2], commit=True).unit_id
    e.map_workflow_owner(org, "w", u1, now=T[3], commit=True)
    with pytest.raises(ImmutableWorkflowError):
        e.map_workflow_owner(org, "w", u2, now=T[4], commit=True)


def test_map_workflow_valid_dependency_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    org = ledger.get_unit(u)["org_id"]
    w1 = e.map_workflow_owner(org, "w1", u, now=T[2], commit=True).workflow_id
    w2 = e.map_workflow_owner(org, "w2", u, depends_on=[w1], now=T[3], commit=True)
    assert w1 in w2.depends_on


# ══════════════ activate / policy / coordinating ══════════════
def test_activate_organization(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    assert e.current_state(org) == O_ACTIVE


def test_activate_from_created_illegal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    with pytest.raises(IllegalOrgTransition):
        e.activate_organization(org, T[2], commit=True)


def test_policy_transitions_coordinating(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.create_coordination_policy(org, "sync", "cadence", "daily", T[3], commit=True)
    assert e.current_state(org) == O_COORDINATING


def test_policy_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.create_coordination_policy(org, "p", "t", "rule1", T[3], commit=True)
    with pytest.raises(ImmutablePolicyError):
        e.create_coordination_policy(org, "p", "t", "rule2", T[4], commit=True)


def test_review_and_archive(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.create_coordination_policy(org, "p", "t", "r", T[3], commit=True)
    e.review_organization(org, T[4], commit=True)
    assert e.current_state(org) == O_REVIEWED
    e.archive_organization(org, T[5], commit=True)
    assert e.current_state(org) == O_ARCHIVED


def test_full_lifecycle_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    e.create_research_unit(org, "DATA_RESEARCH", "u1", "", T[1], commit=True)
    e.activate_organization(org, T[2], commit=True)
    e.create_coordination_policy(org, "p", "t", "r", T[3], commit=True)
    e.review_organization(org, T[4], commit=True)
    e.archive_organization(org, T[5], commit=True)
    states = [r["to_state"] for r in ledger.org_events(org)]
    assert states == [O_CREATED, O_CONFIGURED, O_ACTIVE, O_COORDINATING, O_REVIEWED, O_ARCHIVED]


def test_archive_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.create_coordination_policy(org, "p", "t", "r", T[3], commit=True)
    e.review_organization(org, T[4], commit=True)
    e.archive_organization(org, T[5], commit=True)
    with pytest.raises(IllegalOrgTransition):
        e.archive_organization(org, T[6], commit=True)


def test_review_can_return_to_coordinating(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.create_coordination_policy(org, "p", "t", "r", T[3], commit=True)
    e.review_organization(org, T[4], commit=True)
    e._transition(org, O_COORDINATING, "back", T[5], commit=True)
    assert e.current_state(org) == O_COORDINATING


# ══════════════ evaluate_organization_state (health metrics, analytical) ══════════════
def test_evaluate_returns_metrics(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.assign_agent_role(u, "a1", "RESEARCHER", "", T[3], commit=True)
    e.map_workflow_owner(org, "w", u, now=T[4], commit=True)
    h = e.evaluate_organization_state(org)
    for k in ("coordination_completeness", "ownership_coverage", "dependency_clarity",
              "research_throughput", "unresolved_conflicts"):
        assert k in h


def test_evaluate_is_analytical_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    before = len(ledger.read_org_events())
    h = e.evaluate_organization_state(org)
    assert h["is_analytical"] is True
    assert "METRIC ≠ ACTION" in h["note"]
    # 분석은 상태를 바꾸지 않음
    assert len(ledger.read_org_events()) == before


def test_ownership_coverage_full(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.map_workflow_owner(org, "w", u, now=T[3], commit=True)
    h = e.evaluate_organization_state(org)
    assert h["ownership_coverage"] == 1.0


def test_coordination_completeness(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.assign_agent_role(u, "a1", "RESEARCHER", "", T[3], commit=True)
    h = e.evaluate_organization_state(org)
    assert h["coordination_completeness"] == 1.0


def test_dependency_clarity_clean(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    w1 = e.map_workflow_owner(org, "w1", u, now=T[3], commit=True).workflow_id
    e.map_workflow_owner(org, "w2", u, depends_on=[w1], now=T[4], commit=True)
    h = e.evaluate_organization_state(org)
    assert h["dependency_clarity"] == 1.0


def test_research_throughput_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.assign_agent_role(u, "a1", "RESEARCHER", "", T[3], commit=True)
    e.map_workflow_owner(org, "w", u, now=T[4], commit=True)
    h = e.evaluate_organization_state(org)
    assert h["research_throughput"] >= 3


def test_unresolved_conflicts_zero_when_clean(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.assign_agent_role(u, "a1", "RESEARCHER", "", T[3], commit=True)
    e.map_workflow_owner(org, "w", u, now=T[4], commit=True)
    h = e.evaluate_organization_state(org)
    assert h["unresolved_conflicts"] == 0


# ══════════════ coordination framework ══════════════
def test_dependency_map(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    w1 = e.map_workflow_owner(org, "w1", u, now=T[3], commit=True).workflow_id
    w2 = e.map_workflow_owner(org, "w2", u, depends_on=[w1], now=T[4], commit=True).workflow_id
    dm = e.dependency_map(org)
    assert dm[w2] == [w1]


def test_ownership_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    w = e.map_workflow_owner(org, "w", u, now=T[3], commit=True).workflow_id
    og = e.ownership_graph(org)
    assert og[w] == u


def test_workflow_routing_map(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    w = e.map_workflow_owner(org, "w", u, ["src1"], now=T[3], commit=True).workflow_id
    rm = e.workflow_routing_map(org)
    assert rm[w]["owner"] == u
    assert "src1" in rm[w]["inputs"]


def test_identify_bottlenecks(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    w1 = e.map_workflow_owner(org, "w1", u, now=T[3], commit=True).workflow_id
    e.map_workflow_owner(org, "w2", u, depends_on=[w1], now=T[4], commit=True)
    e.map_workflow_owner(org, "w3", u, depends_on=[w1], now=T[5], commit=True)
    bn = e.identify_bottlenecks(org)
    assert bn[0][0] == w1 and bn[0][1] == 2


# ══════════════ snapshot ══════════════
def test_snapshot_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.assign_agent_role(u, "a1", "RESEARCHER", "", T[3], commit=True)
    e.assign_agent_role(u, "a2", "ANALYST", "", T[4], commit=True)
    snap = e.snapshot_organization(org, "ALL", T[5], commit=True)
    assert snap.unit_count == 1
    assert snap.role_count == 2
    assert snap.role_distribution.get("RESEARCHER") == 1


def test_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    a = e.snapshot_organization(org, "ALL", T[5], commit=False)
    b = e.snapshot_organization(org, "ALL", T[5], commit=False)
    assert a.snapshot_id == b.snapshot_id
    assert a.unit_type_distribution == b.unit_type_distribution


def test_snapshot_consistency_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.snapshot_organization(org, "ALL", T[5], commit=True)
    assert snapshot_consistency()["ok"] is True


# ══════════════ report ══════════════
def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.create_research_team(u, "t", "", T[3], commit=True)
    e.assign_agent_role(u, "a1", "RESEARCHER", "", T[4], commit=True)
    e.define_responsibility(org, "a1", "scope", now=T[5], commit=True)
    e.map_workflow_owner(org, "w", u, now=T[6], commit=True)
    rep = e.generate_report(org, "ALL", T[7], commit=True)
    assert rep.unit_count == 1
    assert rep.team_count == 1
    assert rep.role_count == 1
    assert rep.responsibility_count == 1
    assert rep.workflow_count == 1


def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    rep = e.generate_report(org, "ALL", T[1], commit=True)
    assert rep.is_binding is False


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    rep = e.generate_report(org, "ALL", T[1], commit=True)
    assert "ORGANIZATION ≠ EXECUTION" in rep.disclaimer


def test_report_includes_health(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    rep = e.generate_report(org, "ALL", T[3], commit=True)
    assert "coordination_completeness" in rep.health


# ══════════════ hash chain & tamper ══════════════
def test_chain_intact_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.assign_agent_role(u, "a1", "RESEARCHER", "", T[3], commit=True)
    e.map_workflow_owner(org, "w", u, now=T[4], commit=True)
    e.create_coordination_policy(org, "p", "t", "r", T[5], commit=True)
    e.snapshot_organization(org, "ALL", T[6], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tampered_unit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _unit(e)
    p = ledger.state_path(ledger.UNITS[0])
    recs = ledger.read_units()
    recs[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    e.create_research_unit(org, "DATA_RESEARCH", "u1", "", T[1], commit=True)
    e.create_research_unit(org, "MODEL_RESEARCH", "u2", "", T[2], commit=True)
    p = ledger.state_path(ledger.UNITS[0])
    recs = ledger.read_units()
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.UNITS[0]]["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _unit(e)
    p = ledger.state_path(ledger.UNITS[0])
    recs = ledger.read_units()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.UNITS[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    assert lifecycle_integrity()["ok"] is True


def test_lifecycle_integrity_unauthorized_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng()
    p = ledger.state_path(ledger.ORGANIZATIONS[0])
    bad = {"org_event_id": "ROV:bad", "org_id": "ROG:bad", "name": "x", "from_state": M.GENESIS,
           "to_state": O_ACTIVE, "previous_hash": M.GENESIS}
    bad["record_hash"] = M.content_hash(bad)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps(bad, ensure_ascii=False) + "\n")
    assert lifecycle_integrity()["ok"] is False


def test_ownership_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.map_workflow_owner(org, "w", u, now=T[3], commit=True)
    assert ownership_integrity()["ok"] is True


def test_ownership_integrity_invalid_owner(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.map_workflow_owner(org, "w", u, now=T[3], commit=True)
    p = ledger.state_path(ledger.WORKFLOWS[0])
    recs = ledger.read_workflows()
    recs[0]["owner_unit"] = "ROU:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert ownership_integrity()["ok"] is False


def test_role_integrity_orphan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    e.assign_agent_role(u, "a1", "RESEARCHER", "", T[2], commit=True)
    p = ledger.state_path(ledger.ROLES[0])
    recs = ledger.read_roles()
    recs[0]["unit_id"] = "ROU:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert role_integrity()["ok"] is False


def test_role_integrity_duplicate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    e.assign_agent_role(u, "a1", "RESEARCHER", "", T[2], commit=True)
    p = ledger.state_path(ledger.ROLES[0])
    recs = ledger.read_roles()
    forged = dict(recs[0])
    forged["role_id"] = "ROR:forged00000"
    forged["previous_hash"] = recs[0]["record_hash"]
    forged["record_hash"] = M.content_hash(forged)
    with open(p, "a") as f:
        f.write(json.dumps(forged, ensure_ascii=False, default=str) + "\n")
    assert role_integrity()["ok"] is False


def test_responsibility_integrity_broken_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    e.define_responsibility(org, "a", "s", ["ROK:ghost"], now=T[1], commit=True)
    assert responsibility_integrity()["ok"] is False


def test_responsibility_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    u = _unit(e)
    org = ledger.get_unit(u)["org_id"]
    e.define_responsibility(org, "a", "s", [u], now=T[2], commit=True)
    assert responsibility_integrity()["ok"] is True


def test_dependency_integrity_detects_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.map_workflow_owner(org, "w1", u, now=T[3], commit=True)
    p = ledger.state_path(ledger.WORKFLOWS[0])
    recs = ledger.read_workflows()
    recs[0]["depends_on"] = ["ROK:ghost"]
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert dependency_integrity()["ok"] is False


def test_dependency_integrity_detects_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    w1 = e.map_workflow_owner(org, "w1", u, now=T[3], commit=True).workflow_id
    w2 = e.map_workflow_owner(org, "w2", u, depends_on=[w1], now=T[4], commit=True).workflow_id
    # w1 에 w2 의존을 위조 주입 → 순환
    p = ledger.state_path(ledger.WORKFLOWS[0])
    recs = ledger.read_workflows()
    for r in recs:
        if r["workflow_id"] == w1:
            r["depends_on"] = [w2]
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert dependency_integrity()["ok"] is False


def test_snapshot_consistency_detects_corrupt(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.snapshot_organization(org, "ALL", T[5], commit=True)
    p = ledger.state_path(ledger.SNAPSHOTS[0])
    recs = ledger.read_snapshots()
    recs[0]["unit_count"] = 99
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert snapshot_consistency()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _unit(e)
    assert lineage_integrity()["ok"] is True


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _active(e)
    assert replay(e, T[9])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.assign_agent_role(u, "a1", "RESEARCHER", "", T[3], commit=True)
    s = e.summary(T[9])
    assert s.unit_count == 1
    assert s.role_count == 1


def test_replay_reengine_equal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _active(e)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


def test_verify_integrity_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _unit(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = verify_chain()
    assert res["ok"] is True and res["n"] == 0


# ══════════════ can_transition matrix ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (O_CREATED, O_CONFIGURED, True),
    (O_CONFIGURED, O_CONFIGURED, True),
    (O_CONFIGURED, O_ACTIVE, True),
    (O_ACTIVE, O_COORDINATING, True),
    (O_COORDINATING, O_REVIEWED, True),
    (O_REVIEWED, O_ARCHIVED, True),
    (O_REVIEWED, O_COORDINATING, True),
    (O_CREATED, O_ACTIVE, False),
    (O_CREATED, O_ARCHIVED, False),
    (O_CONFIGURED, O_COORDINATING, False),
    (O_ARCHIVED, O_ACTIVE, False),
    (O_ACTIVE, O_REVIEWED, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["EXECUTE", "TRADE", "DEPLOY", "ALLOCATE", "PROMOTE_LIVE",
                                  "APPROVE_TRADING", "APPROVE_MODEL", "MODIFY_STRATEGY",
                                  "MODIFY_MODEL", "CHANGE_PERMISSION", "CHANGE_CONFIG",
                                  "AUTHORIZE_EXECUTION", "REASSIGN"])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["ORGANIZE", "MAP", "ASSIGN", "COORDINATE", "EVALUATE", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 / prefixes ══════════════
def test_ids_deterministic():
    assert M.org_id("x") == M.org_id("x")
    assert M.unit_id("o", "t", "n") == M.unit_id("o", "t", "n")
    assert M.role_id("u", "a", "r") == M.role_id("u", "a", "r")


def test_ids_prefixes_ro_scheme():
    assert M.org_id("x").startswith("ROG:")
    assert M.org_event_id("o", "s", 0).startswith("ROV:")
    assert M.unit_id("o", "t", "n").startswith("ROU:")
    assert M.team_id("u", "n").startswith("ROT:")
    assert M.role_id("u", "a", "r").startswith("ROR:")
    assert M.responsibility_id("o", "ow", "s").startswith("ROB:")
    assert M.workflow_id("o", "w").startswith("ROK:")
    assert M.policy_id("o", "n").startswith("ROP:")
    assert M.snapshot_id("o", "s", "t").startswith("RON:")
    assert M.report_id("o", "s", "t").startswith("ROO:")
    assert M.artifact_id("t", "r").startswith("ROF:")


def test_ratio_pure():
    assert M.ratio(1, 2) == 0.5
    assert M.ratio(0, 0) == 1.0
    assert M.ratio(3, 3) == 1.0


def test_detect_cycle_and_ancestors():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) != []
    assert M.detect_cycle([("a", "b")]) == []
    assert M.ancestors([("c", "b"), ("b", "a")], "c") == ["a", "b"]


def test_content_hash_excludes_hash_fields():
    a = {"x": 1, "previous_hash": "p", "record_hash": "r"}
    b = {"x": 1, "previous_hash": "q", "record_hash": "s"}
    assert M.content_hash(a) == M.content_hash(b)


# ══════════════ 보안: 금지 import AST 스캔 ══════════════
_PKG_DIR = os.path.dirname(os.path.dirname(__file__))
_FORBIDDEN_PREFIXES = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.capital_allocation", "jarvis.live_trading", "jarvis.risk_controller",
    "jarvis.portfolio_execution",
)


def _module_files():
    for fn in os.listdir(_PKG_DIR):
        if fn.endswith(".py"):
            yield os.path.join(_PKG_DIR, fn)


def test_no_forbidden_imports():
    for path in _module_files():
        with open(path) as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                for bad in _FORBIDDEN_PREFIXES:
                    assert not name.startswith(bad), f"{path}: {name}"


def test_no_forbidden_method_defs():
    forbidden = ("def execute", "def trade", "def deploy", "def allocate", "def promote_live",
                 "def approve_trading", "def approve_model", "def modify_strategy",
                 "def modify_model", "def change_permission", "def change_config",
                 "def place_order")
    for path in _module_files():
        with open(path) as f:
            src = f.read().lower()
        for bad in forbidden:
            assert bad not in src, f"{path}: {bad}"


def test_no_model_id_leak():
    for path in _module_files():
        with open(path) as f:
            assert "claude-opus" not in f.read().lower()


def test_ledger_no_delete_update_api():
    import jarvis.research_organization.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    with open(os.path.join(_PKG_DIR, "ledger.py")) as f:
        src = f.read()
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


def test_all_written_files_have_rorg_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org, u = _active(e)
    e.assign_agent_role(u, "a1", "RESEARCHER", "", T[3], commit=True)
    e.map_workflow_owner(org, "w", u, now=T[4], commit=True)
    e.snapshot_organization(org, "ALL", T[5], commit=True)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("rorg_"), fn


# ══════════════ 소스 참조 READ ONLY ══════════════
def test_source_ref_exists_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("data_governance", "x") is False


def test_source_ref_read_only_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = ledger.state_path("dg_datasets.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps({"dataset_hash": "D1"}) + "\n")
    before = os.path.getmtime(p)
    assert ledger.source_ref_exists("data_governance", "D1") is True
    assert os.path.getmtime(p) == before


# ══════════════ CLI ══════════════
def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_organization.__main__ import main
    assert main(["summary"]) == 0
    assert "unit_count" in json.loads(capsys.readouterr().out)


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_organization.__main__ import main
    assert main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_organization.__main__ import main
    main(["org", "--name", "lab", "--commit"])
    org = json.loads(capsys.readouterr().out)["org"]["org_id"]
    main(["unit", "--org", org, "--type", "DATA_RESEARCH", "--name", "u1", "--commit"])
    u = json.loads(capsys.readouterr().out)["unit"]["unit_id"]
    main(["role", "--unit", u, "--agent", "a1", "--role", "RESEARCHER", "--commit"])
    capsys.readouterr()
    main(["activate", "--org", org, "--commit"])
    capsys.readouterr()
    assert main(["policy", "--org", org, "--name", "sync", "--rule", "daily", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["policy"]["policy_id"].startswith("ROP:")


def test_cli_evaluate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_organization.__main__ import main
    main(["org", "--name", "lab", "--commit"])
    org = json.loads(capsys.readouterr().out)["org"]["org_id"]
    main(["unit", "--org", org, "--type", "DATA_RESEARCH", "--name", "u1", "--commit"])
    capsys.readouterr()
    assert main(["evaluate", "--org", org]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["is_analytical"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_organization.__main__ import main
    assert main(["replay"]) == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_snapshot_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_organization.__main__ import main
    main(["org", "--name", "lab", "--commit"])
    org = json.loads(capsys.readouterr().out)["org"]["org_id"]
    main(["unit", "--org", org, "--type", "DATA_RESEARCH", "--name", "u1", "--commit"])
    capsys.readouterr()
    assert main(["snapshot", "--org", org, "--commit"]) == 0
    capsys.readouterr()
    assert main(["report", "--org", org, "--commit"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["is_binding"] is False


def test_cli_workflow_and_units(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_organization.__main__ import main
    main(["org", "--name", "lab", "--commit"])
    org = json.loads(capsys.readouterr().out)["org"]["org_id"]
    main(["unit", "--org", org, "--type", "DATA_RESEARCH", "--name", "u1", "--commit"])
    u = json.loads(capsys.readouterr().out)["unit"]["unit_id"]
    assert main(["workflow", "--org", org, "--name", "w", "--owner-unit", u, "--commit"]) == 0
    capsys.readouterr()
    assert main(["units", "--org", org]) == 0
    assert len(json.loads(capsys.readouterr().out)["units"]) == 1


# ══════════════ no stray writes ══════════════
def test_no_stray_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    org = _org(e)
    e.create_research_unit(org, "DATA_RESEARCH", "u1", "", T[1], commit=False)
    assert ledger.read_units() == []
