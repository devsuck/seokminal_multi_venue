"""Integration Audit 자료형 (P41) — 기존 Jarvis 아키텍처 통합 감사. **읽기전용 내성(introspection).**

기존 시스템(P1~P40+)을 스캔·분석해 모듈 인벤토리·의존성 그래프·중복 분석·미사용 분석·통합 제안을 만든다.
**기존 원장·레코드는 절대 변경하지 않는다(READ ONLY).** 코드 변경 없이 정적 분석만 수행 — 새 지능 계층을 만들지 않는다.
거래·집행·배포 기능 없음.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

# ── 카테고리(연구 환경 정보구조) — P43 네비게이션에서 재사용 ──
CAT_RESEARCH = "Research"
CAT_KNOWLEDGE = "Knowledge"
CAT_AGENTS = "Agents"
CAT_SIMULATION = "Simulation"
CAT_MONITORING = "Monitoring"
CAT_SYSTEM = "System"
CAT_EXECUTION = "Execution"
CAT_OTHER = "Other"
CATEGORIES = (CAT_RESEARCH, CAT_KNOWLEDGE, CAT_AGENTS, CAT_SIMULATION, CAT_MONITORING,
              CAT_SYSTEM, CAT_EXECUTION, CAT_OTHER)

# ── 카테고리 판정 규칙(우선순위 순서대로 첫 일치) — 결정적 ──
# (카테고리, 키워드 튜플). 이름에 키워드가 포함되면 매칭.
_CATEGORY_RULES = (
    (CAT_EXECUTION, ("execution", "broker", "live_execution", "live_market", "order",
                     "fill", "reconciliation", "post_trade", "paper_execution", "portfolio")),
    (CAT_SIMULATION, ("simulation", "paper", "backtest", "experiment_orchestration",
                      "experiment_manager", "experiment_tracking")),
    (CAT_KNOWLEDGE, ("knowledge", "memory", "_kg", "literature", "learning", "insight",
                     "experience_memory")),
    (CAT_AGENTS, ("agent", "council", "coordinator", "collaboration", "conflict_resolution",
                  "reviewer")),
    (CAT_MONITORING, ("monitoring", "observability", "observatory", "diagnostics", "health",
                      "watchdog", "profiling", "benchmark", "resilience")),
    (CAT_SYSTEM, ("governance", "compliance", "policy", "audit", "security", "config",
                  "registry", "permission", "license", "sbom", "threat", "integrity",
                  "recovery", "emergency", "dependency", "release", "production", "operations",
                  "system", "control", "resource", "api", "gateway", "dashboard", "console")),
    (CAT_RESEARCH, ("research", "alpha", "strategy", "causal", "decision", "planner",
                    "planning", "optimization", "fusion", "meta", "validation", "lifecycle",
                    "improvement", "evolution")),
)


def categorize(name: str) -> str:
    """모듈 이름을 연구 환경 카테고리로 분류(결정적, 첫 일치 우선). P41 감사 + P43 네비게이션 공용."""
    n = (name or "").lower()
    for cat, keywords in _CATEGORY_RULES:
        if any(k in n for k in keywords):
            return cat
    return CAT_OTHER


def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def content_digest(payload) -> str:
    return _digest(payload)


def family_of(name: str) -> str:
    """이름 계열(마지막 토큰 제거) — 중복/과중복 클러스터링용."""
    parts = (name or "").split("_")
    return "_".join(parts[:-1]) if len(parts) > 1 else name


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    category: str
    family: str
    pattern: str            # standard | partial | other
    py_files: int
    has_tests: bool
    has_cli: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DuplicateCluster:
    family: str
    category: str
    members: list
    size: int
    recommendation: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DependencyStats:
    edge_count: int
    node_count: int
    top_imported: list      # [(name, in_degree), ...] 상위
    orphans: list           # in_degree 0(엔트리포인트 제외)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IntegrationProposal:
    family: str
    category: str
    members: list
    action: str             # INTEGRATE | REVIEW | KEEP
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AuditReport:
    module_count: int
    category_distribution: dict
    pattern_distribution: dict
    duplicate_cluster_count: int
    orphan_count: int
    proposal_count: int
    ui_page_count: int
    digest: str
    generated_at: str
    modules: list = field(default_factory=list)
    duplicate_clusters: list = field(default_factory=list)
    proposals: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
