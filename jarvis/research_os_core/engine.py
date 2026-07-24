"""Research OS Core Engine (P10.30) — Phase 10 최종 상위 연구 운영 환경. **관측 전용.**

10대 도메인에 걸쳐 전 계층(P9.8~P10.29)을 READ ONLY 로 참조(파일 기반, import 없음)해 모듈 등록·OS 스냅샷 구성·
OS 헬스 산출·글로벌 리포트 생성·전체 무결성 검증을 수행하고 OS 레지스트리·글로벌 상태·모듈 카탈로그·시스템
스냅샷·연구 리포트를 남긴다. **이 계층은 관측만 한다 — execute·trade·deploy·allocate·modify 없음.**
execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk controller import·
호출 없음. OBSERVE ≠ EXECUTE · SNAPSHOT ≠ DEPLOY · HEALTH ≠ ACTION · REPORT ≠ TRADE. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_os_core import ledger
from jarvis.research_os_core.models import (
    DOMAIN_DEPS,
    DOMAINS,
    GENESIS,
    STATE_ACTIVE,
    STATE_EMPTY,
    STATE_MISSING,
    CatalogRecord,
    GlobalReportRecord,
    GlobalStateRecord,
    ImmutableCatalogError,
    ImmutableModuleError,
    ImmutableReportError,
    ImmutableSnapshotError,
    ImmutableStateError,
    InvalidDomain,
    ModuleRecord,
    OSSummary,
    SnapshotRecord,
    catalog_id as _catalog_id,
    content_hash,
    dependency_issues,
    domain_coverage as _domain_coverage,
    health_level,
    input_digest,
    module_id as _module_id,
    os_health_score,
    report_id as _report_id,
    snapshot_id as _snapshot_id,
    state_id as _state_id,
)

_DISCLAIMER = ("Research OS Core 데이터 — OBSERVE ≠ EXECUTE · SNAPSHOT ≠ DEPLOY · HEALTH ≠ ACTION · "
               "REPORT ≠ TRADE. 상위 연구 운영 환경 관측·집계·리포트 전용 — 실행/거래/배포/할당/변경 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchOSCoreEngine:
    """Phase 10 최종 상위 연구 운영 환경 엔진. 불변·append-only·결정적. 실행/거래/배포/할당/변경 권한 없음."""

    # ══════════════ register_module ══════════════
    def register_module(self, name: str, domain: str, phase: str = "", ledger_file: str = "",
                       id_field: str = "", now: str = "", *, commit: bool = False) -> ModuleRecord:
        """모듈(계층)을 OS 레지스트리에 관측 대상으로 등록. **관측 등록만 — 실행 권한 부여 아님.**"""
        if domain not in DOMAINS:
            raise InvalidDomain(f"미등록 도메인 {domain}")
        mid = _module_id(name)
        existing = ledger.get_module(mid)
        if existing is not None:
            if existing.get("domain") != domain or existing.get("phase") != phase:
                raise ImmutableModuleError(f"{mid} 모듈 불변 — 변경 불가")
            return ModuleRecord(**{k: v for k, v in existing.items()
                                   if k in ModuleRecord.__dataclass_fields__})
        rec = ModuleRecord(module_id=mid, name=name, domain=domain, phase=phase,
                           ledger_file=ledger_file, id_field=id_field, registered_at=now,
                           input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.module_exists(mid):
            head = ledger.registry_head()
            ledger.append_module(_seal(rec, head["record_hash"] if head else GENESIS))
        return ModuleRecord(**rec)

    def _register_catalog(self, domain: str, module: str, ledger_file: str, phase: str, now: str,
                        *, commit: bool) -> CatalogRecord:
        cid = _catalog_id(domain, module)
        existing = ledger.get_catalog(cid)
        if existing is not None:
            if existing.get("ledger_file") != ledger_file:
                raise ImmutableCatalogError(f"{cid} 카탈로그 불변 — 변경 불가")
            return CatalogRecord(**{k: v for k, v in existing.items()
                                    if k in CatalogRecord.__dataclass_fields__})
        rec = CatalogRecord(catalog_id=cid, domain=domain, module=module, ledger_file=ledger_file,
                            phase=phase, created_at=now, input_hash=input_digest(domain, module),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.catalog_exists(cid):
            head = ledger.catalog_head()
            ledger.append_catalog(_seal(rec, head["record_hash"] if head else GENESIS))
        return CatalogRecord(**rec)

    def discover_modules(self, now: str = "", *, commit: bool = False) -> list:
        """모듈 카탈로그(10대 도메인 × P9.8~P10.29) 완전 발견·등록. **READ ONLY 발견.**"""
        out: list = []
        for domain, module, filename, id_field, phase in ledger.catalog_modules():
            self._register_catalog(domain, module, filename, phase, now, commit=commit)
            out.append(self.register_module(module, domain, phase, filename, id_field, now,
                                            commit=commit))
        return out

    # ══════════════ 모듈 상태(내부) ══════════════
    def _module_state(self, rec: dict) -> str:
        filename = rec.get("ledger_file", "")
        if not filename or not ledger.source_exists(filename):
            return STATE_MISSING
        return STATE_ACTIVE if ledger.source_count(filename) > 0 else STATE_EMPTY

    def _aggregate(self) -> dict:
        """레지스트리 기준 도메인별 모듈 상태 집계(결정적)."""
        modules = ledger.read_modules()
        per_domain: dict = {}
        active = 0
        phase_dist: dict = {}
        for m in modules:
            dom = m.get("domain")
            st = self._module_state(m)
            per_domain.setdefault(dom, {"total": 0, "active": 0})
            per_domain[dom]["total"] += 1
            if st == STATE_ACTIVE:
                per_domain[dom]["active"] += 1
                active += 1
            phase_dist[m.get("phase")] = phase_dist.get(m.get("phase"), 0) + 1
        covered = sum(1 for d in per_domain.values() if d["active"] > 0)
        total = len(modules)
        coverage = _domain_coverage(covered, len(DOMAINS))
        activity = round((float(active) / total) if total > 0 else 0.0, 8)
        dep = self.check_dependency_integrity()
        return {
            "module_count": total, "active_module_count": active,
            "per_domain": {k: per_domain[k] for k in sorted(per_domain)},
            "covered_domains": covered, "domain_count": len(per_domain),
            "domain_coverage": coverage, "module_activity": activity,
            "integrity_ok": dep["ok"], "phase_distribution": dict(sorted(phase_dist.items())),
        }

    # ══════════════ dependency integrity ══════════════
    def check_dependency_integrity(self) -> dict:
        """도메인 데이터 흐름 DAG 무결성(미지 노드·순환) 검증. **탐지·보고만.**"""
        issues = dependency_issues(list(DOMAIN_DEPS), list(DOMAINS))
        return {"ok": not issues, "issues": issues, "edge_count": len(DOMAIN_DEPS),
                "node_count": len(DOMAINS)}

    # ══════════════ governance compliance ══════════════
    def check_governance_compliance(self) -> dict:
        """거버넌스 컴플라이언스: 10대 도메인 카탈로그 존재·Audit/Control Plane 등록. **점검만.**"""
        issues: list = []
        cat_domains = {c.get("domain") for c in ledger.read_catalog()}
        for d in DOMAINS:
            if d not in cat_domains:
                issues.append(f"missing_domain_catalog:{d}")
        reg_domains = {m.get("domain") for m in ledger.read_modules()}
        for required in ("AUDIT", "CONTROL_PLANE"):
            if required not in reg_domains:
                issues.append(f"missing_required_domain:{required}")
        return {"ok": not issues, "issues": sorted(set(issues))}

    # ══════════════ build_os_snapshot ══════════════
    def build_os_snapshot(self, scope: str = "GLOBAL", now: str = "",
                        *, commit: bool = False) -> SnapshotRecord:
        """OS 시스템 스냅샷(도메인별 모듈 상태·커버리지·헬스). **결정적·재현.**"""
        agg = self._aggregate()
        score = os_health_score(agg["domain_coverage"], agg["module_activity"], agg["integrity_ok"])
        level = health_level(score, agg["module_count"])
        sid = _snapshot_id(scope, now)
        existing = ledger.get_snapshot(sid)
        if existing is not None:
            if existing.get("module_count") != agg["module_count"] or \
                    existing.get("health_level") != level:
                raise ImmutableSnapshotError(f"{sid} 스냅샷 불변 — 변경 불가")
            return SnapshotRecord(**{k: v for k, v in existing.items()
                                     if k in SnapshotRecord.__dataclass_fields__})
        rec = SnapshotRecord(
            snapshot_id=sid, scope=scope, module_count=agg["module_count"],
            active_module_count=agg["active_module_count"], domain_count=agg["domain_count"],
            covered_domains=agg["covered_domains"], domain_coverage=agg["domain_coverage"],
            per_domain=agg["per_domain"], overall_score=score, health_level=level,
            phase_distribution=agg["phase_distribution"], disclaimer=_DISCLAIMER, snapshot_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        return SnapshotRecord(**rec)

    # ══════════════ calculate_os_health ══════════════
    def calculate_os_health(self, scope: str = "GLOBAL", now: str = "",
                          *, commit: bool = False) -> GlobalStateRecord:
        """OS 헬스(도메인 커버리지·모듈 활성·무결성) 산출·글로벌 상태 기록. **HEALTH ≠ ACTION.**"""
        agg = self._aggregate()
        score = os_health_score(agg["domain_coverage"], agg["module_activity"], agg["integrity_ok"])
        level = health_level(score, agg["module_count"])
        stid = _state_id(scope, now)
        existing = ledger.get_state(stid)
        if existing is not None:
            if abs(float(existing.get("overall_score", -1)) - score) > 1e-9:
                raise ImmutableStateError(f"{stid} 글로벌 상태 불변 — 변경 불가")
            return GlobalStateRecord(**{k: v for k, v in existing.items()
                                        if k in GlobalStateRecord.__dataclass_fields__})
        rec = GlobalStateRecord(
            state_id=stid, scope=scope, module_count=agg["module_count"],
            active_module_count=agg["active_module_count"], covered_domains=agg["covered_domains"],
            domain_coverage=agg["domain_coverage"], module_activity=agg["module_activity"],
            integrity_ok=agg["integrity_ok"], overall_score=score, level=level, computed_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.state_exists(stid):
            head = ledger.state_head()
            ledger.append_state(_seal(rec, head["record_hash"] if head else GENESIS))
        return GlobalStateRecord(**rec)

    # ══════════════ generate_global_report ══════════════
    def generate_global_report(self, scope: str = "GLOBAL", metrics: dict | None = None,
                             now: str = "", *, commit: bool = False) -> GlobalReportRecord:
        """글로벌 연구 리포트(모듈·도메인 커버리지·헬스·의존성·컴플라이언스). **관측 리포트 — 실행 지시 아님.**"""
        m = dict(metrics or {})
        agg = self._aggregate()
        score = os_health_score(agg["domain_coverage"], agg["module_activity"], agg["integrity_ok"])
        level = health_level(score, agg["module_count"])
        dep = self.check_dependency_integrity()
        comp = self.check_governance_compliance()
        rid = _report_id(scope, now)
        rec = GlobalReportRecord(
            report_id=rid, scope=scope, module_count=agg["module_count"],
            active_module_count=agg["active_module_count"], domain_count=agg["domain_count"],
            covered_domains=agg["covered_domains"], domain_coverage=agg["domain_coverage"],
            overall_score=score, health_level=level, per_domain=agg["per_domain"],
            phase_distribution=agg["phase_distribution"], dependency_ok=dep["ok"],
            compliance_ok=comp["ok"], metrics=m, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return GlobalReportRecord(**rec)

    # ══════════════ verify_all_integrity ══════════════
    def verify_all_integrity(self) -> dict:
        """전체 무결성 검증: 원장 체인·도메인 의존성·거버넌스 컴플라이언스·모듈 발견 완전성. **읽기 전용.**"""
        from jarvis.research_os_core.verify import verify_chain
        chain = verify_chain()
        dep = self.check_dependency_integrity()
        comp = self.check_governance_compliance()
        discovery = self.module_discovery_status()
        # 구조 무결성(원장 체인 + 도메인 의존성 DAG)이 ok 를 결정. 컴플라이언스·발견 완전성은
        # 별도 신호로 보고(빈/미부트스트랩 OS 도 체인 자체는 무결하므로 ok).
        ok = chain["ok"] and dep["ok"]
        return {"ok": ok, "chain": chain, "dependency": dep, "compliance": comp,
                "discovery": discovery}

    def module_discovery_status(self) -> dict:
        """카탈로그 대비 등록 모듈 완전성(결정적)."""
        expected = {m[1] for m in ledger.catalog_modules()}
        registered = {r.get("name") for r in ledger.read_modules()}
        missing = sorted(expected - registered)
        return {"expected": len(expected), "registered": len(registered & expected),
                "missing": missing, "complete": not missing}

    # ══════════════ 조회 편의 ══════════════
    def list_modules(self, domain: str = "") -> list:
        mods = ledger.read_modules()
        if domain:
            mods = [m for m in mods if m.get("domain") == domain]
        return sorted(m.get("name") for m in mods if m.get("name"))

    def domains_present(self) -> list:
        return sorted({m.get("domain") for m in ledger.read_modules() if m.get("domain")})

    def latest_snapshot(self, scope: str = "GLOBAL") -> dict | None:
        found = None
        for s in ledger.read_snapshots():
            if s.get("scope") == scope:
                found = s
        return found

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> OSSummary:
        return OSSummary(
            timestamp=now, module_count=len(ledger.read_modules()),
            catalog_count=len(ledger.read_catalog()), state_count=len(ledger.read_state()),
            snapshot_count=len(ledger.read_snapshots()), report_count=len(ledger.read_reports()))
