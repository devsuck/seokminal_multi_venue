"""Research Resource Manager Engine (P32) — 연구 자원 추적 기록. **자동 배분·프로비저닝 없음, 동작 없음.**

**기록만 한다 — 자동으로 배분하지 않으며 인프라를 프로비저닝하지 않는다.** execution/broker/live_trading/
portfolio_execution import·호출 없음. RECORD ≠ ALLOCATE · RECORD ≠ PROVISION · TRACK ≠ EXECUTE. 결정적·불변·
append-only. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.research_resource_manager import ledger
from jarvis.research_resource_manager import models as M
from jarvis.research_resource_manager.models import (
    GENESIS,
    AllocationRecord,
    ArtifactRecord,
    BudgetRecord,
    ResourceRecord,
    ResourceReportRecord,
    ResourceSummary,
    UnknownEntityError,
    UsageRecord,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Research Resource Manager 데이터 — RECORD ≠ ALLOCATE · RECORD ≠ PROVISION · TRACK ≠ "
               "EXECUTE. 연구 자원(데이터셋·컴퓨트·스토리지·예산·GPU·실험 배분) 추적 기록 전용 — 자동 배분·인프라 "
               "프로비저닝·실행·거래·자본 배분 없음.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchResourceManagerEngine:
    """연구 자원 관리 엔진. 불변·append-only·결정적. 자동 배분/프로비저닝/실행/거래 권한 없음."""

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _artifact(self, atype, ref, parent, now, *, commit) -> ArtifactRecord:
        aid = M.artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref, parent_artifact=parent,
                             created_at=now, input_hash=input_digest(atype, ref),
                             previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.artifact_exists, ledger.artifacts_head, ledger.append_artifact,
                         aid, rec, commit=commit)
        return ArtifactRecord(**rec)

    # ══════════════ register_resource ══════════════
    def register_resource(self, resource_type, name, capacity=0.0, unit="units", source_reference="",
                          now="", *, commit=False) -> ResourceRecord:
        """연구 자원 등록(불변). **추적만 — 프로비저닝 아님.**"""
        if resource_type not in M.RESOURCE_TYPES:
            raise ValueError(f"미지원 resource_type {resource_type}")
        rid = M.resource_id(resource_type, name)
        existing = ledger.resource_by_id(rid)
        if existing:
            return ResourceRecord(**{k: v for k, v in existing.items()
                                     if k in ResourceRecord.__dataclass_fields__})
        rec = ResourceRecord(resource_id=rid, resource_type=resource_type, name=name,
                             capacity=float(capacity), unit=unit, source_reference=source_reference,
                             created_at=now, input_hash=input_digest(resource_type, name),
                             previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.resource_exists, ledger.resources_head, ledger.append_resource, rid,
                         rec, commit=commit)
        self._artifact(M.ART_RESOURCE, rid, "", now, commit=commit)
        return ResourceRecord(**rec)

    # ══════════════ record_usage ══════════════
    def record_usage(self, resource, amount, unit="units", purpose="EXPERIMENT", detail="", now="",
                     *, commit=False) -> UsageRecord:
        """자원 사용 기록(불변). **관찰·기록만 — 소비 발생시키지 않음.**"""
        if not ledger.resource_by_id(resource):
            raise UnknownEntityError(f"미등록 자원 {resource}")
        if purpose not in M.USAGE_PURPOSES:
            raise ValueError(f"미지원 purpose {purpose}")
        seq = len(ledger.usage_for(resource))
        uid = M.usage_id(resource, seq)
        rec = UsageRecord(usage_id=uid, resource_id=resource, amount=float(amount), unit=unit,
                          purpose=purpose, detail=detail, timestamp=now,
                          input_hash=input_digest(resource, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.usage_exists, ledger.usage_head, ledger.append_usage, uid, rec,
                         commit=commit)
        return UsageRecord(**rec)

    # ══════════════ record_budget ══════════════
    def record_budget(self, category, amount, currency="USD", period="", now="",
                      *, commit=False) -> BudgetRecord:
        """연구 예산 기록(불변). **기록만 — 지출 발생시키지 않음.**"""
        if category not in M.BUDGET_CATEGORIES:
            raise ValueError(f"미지원 category {category}")
        bid = M.budget_id(category, period)
        rec = BudgetRecord(budget_id=bid, category=category, amount=float(amount), currency=currency,
                           period=period, created_at=now, input_hash=input_digest(category, period),
                           previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.budget_exists, ledger.budgets_head, ledger.append_budget, bid, rec,
                         commit=commit)
        self._artifact(M.ART_BUDGET, bid, "", now, commit=commit)
        return BudgetRecord(**rec)

    # ══════════════ record_allocation (자동 없음, 프로비저닝 없음) ══════════════
    def record_allocation(self, resource, experiment_ref, requested_amount, unit="units", now="",
                          *, commit=False) -> AllocationRecord:
        """실험 배분 기록(불변, is_provisioned=False·is_auto=False). **기록만 — 자동 배분·프로비저닝 없음.**"""
        if not ledger.resource_by_id(resource):
            raise UnknownEntityError(f"미등록 자원 {resource}")
        seq = len(ledger.allocations_for(resource))
        aid = M.allocation_id(resource, experiment_ref, seq)
        rec = AllocationRecord(
            allocation_id=aid, resource_id=resource, experiment_ref=experiment_ref,
            requested_amount=float(requested_amount), unit=unit, is_provisioned=False, is_auto=False,
            created_at=now, input_hash=input_digest(resource, experiment_ref, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.allocation_exists, ledger.allocations_head, ledger.append_allocation,
                         aid, rec, commit=commit)
        self._artifact(M.ART_ALLOCATION, aid, M.artifact_id(M.ART_RESOURCE, resource), now,
                       commit=commit)
        return AllocationRecord(**rec)

    # ══════════════ compute_utilization (READ ONLY, 결정적 관찰) ══════════════
    def compute_utilization(self, resource) -> dict:
        """자원 사용률 관찰(결정적). used=Σusage, capacity=등록 용량. **관찰만 — 배분 아님.**"""
        r = ledger.resource_by_id(resource)
        if not r:
            raise UnknownEntityError(f"미등록 자원 {resource}")
        used = round(sum(float(u.get("amount", 0)) for u in ledger.usage_for(resource)), 6)
        allocated = round(sum(float(a.get("requested_amount", 0))
                              for a in ledger.allocations_for(resource)), 6)
        cap = float(r.get("capacity", 0))
        rate = M.utilization(used, cap)
        return {"resource_id": resource, "used": used, "allocated": allocated, "capacity": cap,
                "utilization": rate, "level": M.classify_utilization(rate)}

    def all_utilizations(self) -> dict:
        return {rid: self.compute_utilization(rid) for rid in ledger.resource_ids()}

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> ResourceReportRecord:
        """자원 리포트(자원·사용·예산·배분 집계 + 사용률). **is_binding=False, RECORD ≠ ALLOCATE.**"""
        resources = ledger.read_resources()
        type_dist: dict = {}
        for r in resources:
            type_dist[r.get("resource_type")] = type_dist.get(r.get("resource_type"), 0) + 1
        util = {rid: self.compute_utilization(rid)["utilization"] for rid in ledger.resource_ids()}
        budget_cat: dict = {}
        for b in ledger.read_budgets():
            budget_cat[b.get("category")] = round(
                budget_cat.get(b.get("category"), 0.0) + float(b.get("amount", 0)), 6)
        rid = M.report_id(scope, now)
        rec = ResourceReportRecord(
            report_id=rid, scope=scope, resource_count=len(resources),
            usage_count=len(ledger.read_usage()), budget_count=len(ledger.read_budgets()),
            allocation_count=len(ledger.read_allocations()),
            type_distribution=dict(sorted(type_dist.items())),
            utilization_by_resource=dict(sorted(util.items())),
            budget_by_category=dict(sorted(budget_cat.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return ResourceReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.research_resource_manager.verify import verify_chain
        return verify_chain()

    def list_resources(self) -> list:
        return ledger.resource_ids()

    def summary(self, now="") -> ResourceSummary:
        return ResourceSummary(
            timestamp=now, resource_count=len(ledger.read_resources()),
            usage_count=len(ledger.read_usage()), budget_count=len(ledger.read_budgets()),
            allocation_count=len(ledger.read_allocations()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
