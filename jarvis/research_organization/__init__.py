"""jarvis.research_organization — Autonomous Research Organization Layer (P11.13). **조직 전용.**

자율 연구 생태계의 조직 조정 계층 — 연구 에이전트·프로세스·지식·의사결정 시스템이 구조화된 조직으로 어떻게
조정되는지를 관리한다(연구 팀 구조·에이전트 역할·책임 매핑·워크플로 소유·조정 정책·조직 상태 추적·연구 운영
투명성). Research Organization Registry·Research Units·Research Teams·Agent Roles·Research Responsibilities·
Workflow Ownership Records·Coordination Policies·Organization Snapshots·Organization Reports·Artifact Lineage
를 소유한다.

**거래 실행·전략 배포·라이브 승인·자본 배분·모델/전략 수정·권한 변경·자율 실행 인가를 하지 않는다.** 건강
지표는 분석 전용 — 자동 재배정·자동 승인·자동 실행을 유발하지 않는다. execution/broker/portfolio/risk/permission/
deployment/live import·호출 없음. ORGANIZATION ≠ EXECUTION · ROLE ≠ AUTHORIZATION · METRIC ≠ ACTION.
불변·append-only 해시체인·이벤트 소싱·결정적·재현. 상위 P9.8/P9.9·P10.1~P10.8·P11.1~P11.12 는 READ ONLY.
물리 원장은 rorg_ 접두사.
"""
from jarvis.research_organization.engine import ResearchOrganizationEngine  # noqa: F401
from jarvis.research_organization.models import (  # noqa: F401
    AGENT_ROLES,
    ORG_STATES,
    UNIT_TYPES,
    ArtifactRecord,
    CircularDependencyError,
    DanglingReferenceError,
    IllegalOrgTransition,
    ImmutableOrganizationError,
    ImmutablePolicyError,
    ImmutableResponsibilityError,
    ImmutableRoleError,
    ImmutableTeamError,
    ImmutableUnitError,
    ImmutableWorkflowError,
    InvalidAgentRole,
    InvalidUnitType,
    MissingOwnerError,
    OrgEventRecord,
    OrgReportRecord,
    OrgSummary,
    PolicyRecord,
    ResponsibilityRecord,
    RoleRecord,
    SnapshotRecord,
    TeamRecord,
    UnitRecord,
    UnknownOrganizationError,
    UnknownUnitError,
    WorkflowOwnershipRecord,
)
