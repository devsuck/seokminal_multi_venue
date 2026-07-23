"""Self Audit Intelligence Engine (P10.24) — 전 연구 생태계 무결성 메타 감사. **READ ONLY 검사·기록 전용.**

P9.8~P10.23 전 계층 원장을 READ ONLY 로 검사(파일 기반, import 없음)해 감사 정의·감사 실행·무결성 점검·위반
기록·감사 리포트·감사 계보를 남긴다. **원장·정책·config·permission·strategy·model 을 수정/복구/적용/배포하지
않는다.** execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk
controller import·호출 없음. AUDIT ≠ REPAIR · FINDING ≠ FIX · INSPECTION ≠ MODIFICATION · REPORT ≠ ACTION.
상위 파일은 읽기만. 결정적·append-only. repair/modify/fix/apply/deploy 메서드 없음.
"""
from __future__ import annotations

from jarvis.self_audit_intelligence import ledger
from jarvis.self_audit_intelligence.models import (
    ART_AUDIT,
    ART_CHECK,
    ART_REPORT,
    ART_RUN,
    ART_VIOLATION,
    CK_DOCUMENTATION,
    CK_HASH_CHAIN,
    CK_LIFECYCLE,
    CK_LINEAGE,
    CK_VALIDATION,
    COMPLETED,
    CREATED,
    GENESIS,
    PASS,
    RUNNING,
    WARNING,
    AuditArtifact,
    AuditDefinition,
    AuditReport,
    AuditRunEvent,
    AuditSummary,
    IllegalTransition,
    IntegrityCheck,
    UnknownRun,
    ViolationRecord,
    artifact_id as _artifact_id,
    audit_documentation,
    audit_hash_chain,
    audit_id as _audit_id,
    audit_lifecycle,
    audit_lineage,
    can_transition_run,
    check_id as _check_id,
    content_hash,
    input_digest,
    metadata_hash as _metadata_hash,
    report_id as _report_id,
    run_event_id,
    run_id as _run_id,
    violation_id as _violation_id,
    worst_result,
)

_DISCLAIMER = ("연구 자가 감사 데이터 — AUDIT ≠ REPAIR · FINDING ≠ FIX · INSPECTION ≠ MODIFICATION · "
               "REPORT ≠ ACTION. 원장/정책/config/permission/strategy/model 수정·복구·적용·배포 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchSelfAuditEngine:
    """연구 자가 감사 엔진. 불변·append-only·결정적. 실행/복구/수정/적용/배포 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = AuditArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Audit Registry + Audit Run (이벤트 소싱) ──
    def run_state(self, run_id: str) -> str:
        evs = ledger.run_events_for(run_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _run_meta(self, run_id: str) -> dict | None:
        evs = ledger.run_events_for(run_id)
        return evs[0] if evs else None

    def _emit_run_event(self, meta: dict, frm: str, to: str, now: str, *, commit: bool) -> dict:
        if not can_transition_run(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(run)")
        rid = meta["run_id"]
        eid = run_event_id(rid, frm, to)
        rec = AuditRunEvent(
            event_id=eid, run_id=rid, audit_ref=meta["audit_ref"], scope=meta["scope"],
            epoch=meta["epoch"], from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(rid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.run_event_exists(eid):
            head = ledger.runs_head()
            ledger.append_run_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _register_audit(self, name: str, scope: str, target_layers: list, now: str,
                        *, commit: bool) -> dict:
        aid = _audit_id(name)
        mh = _metadata_hash({"scope": scope, "target_layers": sorted(target_layers or [])})
        existing = ledger.get_audit(aid)
        if existing is not None:
            return existing
        rec = AuditDefinition(
            audit_id=aid, name=name, scope=scope, target_layers=sorted(target_layers or []),
            metadata_hash=mh, created_at=now, input_hash=input_digest(name),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.audit_exists(aid):
            head = ledger.audits_head()
            ledger.append_audit(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_AUDIT, aid, "", now, commit=commit)
        return rec

    def create_audit_run(self, name: str = "ecosystem_integrity", scope: str = "GLOBAL",
                       target_layers: list | None = None, epoch: str = "", now: str = "",
                       *, commit: bool = False) -> AuditRunEvent:
        """감사 정의를 레지스트리에 등록하고 감사 실행을 생성(CREATED). **검사 준비 — 수정 없음.**"""
        targets = sorted(target_layers or list(ledger.AUDIT_TARGETS.keys()))
        adef = self._register_audit(name, scope, targets, now, commit=commit)
        aid = adef["audit_id"]
        rid = _run_id(aid, epoch)
        existing = ledger.run_events_for(rid)
        if existing:
            return AuditRunEvent(**existing[-1])
        meta = {"run_id": rid, "audit_ref": aid, "scope": scope, "epoch": epoch}
        rec = self._emit_run_event(meta, "", CREATED, now, commit=commit)
        self._record_artifact(ART_RUN, rid, _artifact_id(ART_AUDIT, aid)
                              if ledger.artifact_exists(_artifact_id(ART_AUDIT, aid)) else "",
                              now, commit=commit)
        return AuditRunEvent(**rec)

    def _advance_run(self, run_ref: str, to: str, now: str, *, commit: bool) -> None:
        meta = self._run_meta(run_ref)
        if meta is None:
            return
        cur = self.run_state(run_ref)
        if cur != to and can_transition_run(cur, to):
            self._emit_run_event(meta, cur, to, now, commit=commit)

    # ── 점검·위반 기록(내부) ──
    def _record_check(self, run_ref: str, layer: str, kind: str, result: str, locus: str,
                     detail: str, evidence: list, now: str, *, commit: bool) -> IntegrityCheck:
        cid = _check_id(run_ref, layer, kind, locus)
        rec = IntegrityCheck(
            check_id=cid, run_ref=run_ref, layer=layer, check_kind=kind, result=result,
            locus=locus, detail=detail, evidence=list(evidence or []), created_at=now,
            input_hash=input_digest(run_ref, layer, kind, locus), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.check_exists(cid):
            head = ledger.checks_head()
            ledger.append_check(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_RUN, run_ref) if ledger.artifact_exists(
            _artifact_id(ART_RUN, run_ref)) else ""
        self._record_artifact(ART_CHECK, cid, parent, now, commit=commit)
        if result != PASS:
            self._record_violation(run_ref, layer, kind, result, locus, detail, now, commit=commit)
        return IntegrityCheck(**rec)

    def _record_violation(self, run_ref: str, layer: str, kind: str, result: str, locus: str,
                        detail: str, now: str, *, commit: bool) -> dict:
        vid = _violation_id(run_ref, layer, kind, locus)
        rec = ViolationRecord(
            violation_id=vid, run_ref=run_ref, layer=layer, check_kind=kind, result=result,
            locus=locus, detail=detail, created_at=now,
            input_hash=input_digest(run_ref, layer, kind, locus), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.violation_exists(vid):
            head = ledger.violations_head()
            ledger.append_violation(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_CHECK, _check_id(run_ref, layer, kind, locus))
        parent = parent if ledger.artifact_exists(parent) else ""
        self._record_artifact(ART_VIOLATION, vid, parent, now, commit=commit)
        return rec

    # ── scan_layer_integrity: 깨진 해시체인 + 유효하지 않은 생명주기 ──
    def scan_layer_integrity(self, run_ref: str, layer: str, now: str = "",
                           *, commit: bool = False) -> list:
        """상위 계층 원장의 해시체인 무결성(+이벤트 소싱 생명주기 구조)을 검사·기록. **읽기 전용.**"""
        if self._run_meta(run_ref) is None:
            raise UnknownRun(f"미존재 감사 실행 {run_ref}")
        self._advance_run(run_ref, RUNNING, now, commit=commit)
        spec = ledger.AUDIT_TARGETS.get(layer)
        out: list = []
        if not spec:
            out.append(self._record_check(run_ref, layer, CK_VALIDATION, WARNING, "target",
                                          "unknown audit target", [], now, commit=commit))
            return out
        filename, id_field, kind = spec
        records = ledger.read_target(filename)
        chain = audit_hash_chain(records, id_field)
        out.append(self._record_check(run_ref, layer, CK_HASH_CHAIN, chain["result"], "chain",
                                      "; ".join(chain["issues"]), chain["issues"], now,
                                      commit=commit))
        if kind == "event":
            life = audit_lifecycle(records)
            out.append(self._record_check(run_ref, layer, CK_LIFECYCLE, life["result"],
                                          "lifecycle", "; ".join(life["issues"]), life["issues"],
                                          now, commit=commit))
        return out

    # ── verify_lineage: 누락 부모(missing parent) ──
    def verify_lineage(self, run_ref: str, layer: str, now: str = "",
                     *, commit: bool = False) -> IntegrityCheck:
        """상위 계층 아티팩트 원장 계보(누락 부모·순환)를 검사·기록. **읽기 전용.**"""
        if self._run_meta(run_ref) is None:
            raise UnknownRun(f"미존재 감사 실행 {run_ref}")
        self._advance_run(run_ref, RUNNING, now, commit=commit)
        spec = ledger.AUDIT_TARGETS.get(layer)
        if not spec:
            return self._record_check(run_ref, layer, CK_VALIDATION, WARNING, "target",
                                     "unknown audit target", [], now, commit=commit)
        records = ledger.read_target(spec[0])
        lin = audit_lineage(records)
        return self._record_check(run_ref, layer, CK_LINEAGE, lin["result"], "lineage",
                                 "; ".join(lin["issues"]), lin["issues"], now, commit=commit)

    # ── detect_missing_governance: 누락 검증(원장 부재) ──
    def detect_missing_governance(self, run_ref: str, now: str = "",
                               *, commit: bool = False) -> list:
        """기대 거버넌스 계층 원장의 부재/공백을 검사·기록(누락 검증). **읽기 전용.**"""
        if self._run_meta(run_ref) is None:
            raise UnknownRun(f"미존재 감사 실행 {run_ref}")
        self._advance_run(run_ref, RUNNING, now, commit=commit)
        out: list = []
        for layer in ledger.EXPECTED_GOVERNANCE_LAYERS:
            present = ledger.target_exists(layer)
            count = ledger.target_count(layer)
            if not present:
                result, detail = WARNING, "governance_ledger_absent"
            elif count == 0:
                result, detail = WARNING, "governance_ledger_empty"
            else:
                result, detail = PASS, "present"
            out.append(self._record_check(run_ref, layer, CK_VALIDATION, result, "presence",
                                          detail, [], now, commit=commit))
        return out

    # ── detect_policy_drift: 미문서화 변경 ──
    def detect_policy_drift(self, run_ref: str, layer: str, now: str = "",
                         *, commit: bool = False) -> IntegrityCheck:
        """상위 계층 원장의 미문서화 변경(필수 문서 필드 누락)을 검사·기록. **읽기 전용.**"""
        if self._run_meta(run_ref) is None:
            raise UnknownRun(f"미존재 감사 실행 {run_ref}")
        self._advance_run(run_ref, RUNNING, now, commit=commit)
        spec = ledger.AUDIT_TARGETS.get(layer)
        if not spec:
            return self._record_check(run_ref, layer, CK_VALIDATION, WARNING, "target",
                                     "unknown audit target", [], now, commit=commit)
        records = ledger.read_target(spec[0])
        doc = audit_documentation(records)
        return self._record_check(run_ref, layer, CK_DOCUMENTATION, doc["result"], "doc",
                                 "; ".join(doc["issues"]), doc["issues"], now, commit=commit)

    # ── generate_audit_report ──
    def generate_audit_report(self, run_ref: str, now: str = "",
                            *, commit: bool = False) -> AuditReport:
        """감사 실행의 점검·위반을 집계해 리포트 생성(run→COMPLETED). overall_result 는 최악 결과."""
        meta = self._run_meta(run_ref)
        if meta is None:
            raise UnknownRun(f"미존재 감사 실행 {run_ref}")
        checks = ledger.checks_for(run_ref)
        res_dist: dict = {}
        kind_dist: dict = {}
        layers: set = set()
        for c in checks:
            res_dist[c.get("result")] = res_dist.get(c.get("result"), 0) + 1
            kind_dist[c.get("check_kind")] = kind_dist.get(c.get("check_kind"), 0) + 1
            layers.add(c.get("layer"))
        violations = ledger.violations_for(run_ref)
        vkind_dist: dict = {}
        for v in violations:
            vkind_dist[v.get("check_kind")] = vkind_dist.get(v.get("check_kind"), 0) + 1
        overall = worst_result([c.get("result") for c in checks])
        rid = _report_id(run_ref)
        rec = AuditReport(
            report_id=rid, run_ref=run_ref, scope=meta.get("scope", "GLOBAL"),
            layers_scanned=sorted(layers), check_count=len(checks),
            check_result_distribution=dict(sorted(res_dist.items())),
            check_kind_distribution=dict(sorted(kind_dist.items())), violation_count=len(violations),
            violation_kind_distribution=dict(sorted(vkind_dist.items())), overall_result=overall,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(run_ref),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._advance_run(run_ref, COMPLETED, now, commit=commit)
        self._record_artifact(ART_REPORT, rid, _artifact_id(ART_RUN, run_ref)
                              if ledger.artifact_exists(_artifact_id(ART_RUN, run_ref)) else "",
                              now, commit=commit)
        return AuditReport(**rec)

    # ── replay_audit (결정성 검증) ──
    def _compute_findings(self, target_layers: list) -> list:
        """대상 계층별 결정적 findings (layer,kind,locus,result) — commit 없음, 순수 계산."""
        out: list = []
        for layer in sorted(target_layers or []):
            spec = ledger.AUDIT_TARGETS.get(layer)
            if not spec:
                out.append((layer, CK_VALIDATION, "target", WARNING))
                continue
            filename, id_field, kind = spec
            records = ledger.read_target(filename)
            out.append((layer, CK_HASH_CHAIN, "chain", audit_hash_chain(records, id_field)["result"]))
            out.append((layer, CK_DOCUMENTATION, "doc", audit_documentation(records)["result"]))
            if kind == "artifact":
                out.append((layer, CK_LINEAGE, "lineage", audit_lineage(records)["result"]))
            if kind == "event":
                out.append((layer, CK_LIFECYCLE, "lifecycle", audit_lifecycle(records)["result"]))
        return sorted(out)

    def replay_audit(self, target_layers: list | None = None) -> dict:
        """동일 상태에서 findings 를 두 번 계산 → 동일 산출(결정성). commit·수정 없음."""
        targets = sorted(target_layers or list(ledger.AUDIT_TARGETS.keys()))
        f1 = self._compute_findings(targets)
        f2 = self._compute_findings(targets)
        return {"deterministic": f1 == f2, "n_findings": len(f1),
                "overall_result": worst_result([r for _, _, _, r in f1])}

    # ── 전체 스캔 편의 ──
    def scan_all(self, run_ref: str, target_layers: list | None = None, now: str = "",
               *, commit: bool = False) -> dict:
        """대상 계층 전체에 대해 무결성·계보·문서화 검사 + 누락 거버넌스 검사를 실행. **읽기 전용.**"""
        targets = sorted(target_layers or list(ledger.AUDIT_TARGETS.keys()))
        for layer in targets:
            self.scan_layer_integrity(run_ref, layer, now, commit=commit)
            self.detect_policy_drift(run_ref, layer, now, commit=commit)
            spec = ledger.AUDIT_TARGETS.get(layer)
            if spec and spec[2] == "artifact":
                self.verify_lineage(run_ref, layer, now, commit=commit)
        self.detect_missing_governance(run_ref, now, commit=commit)
        return {"run_ref": run_ref, "checks": len(ledger.checks_for(run_ref)),
                "violations": len(ledger.violations_for(run_ref))}

    # ── 분석 ──
    def analyze(self, run_ref: str) -> dict:
        checks = ledger.checks_for(run_ref)
        return {"overall_result": worst_result([c.get("result") for c in checks]),
                "check_count": len(checks),
                "violation_count": len(ledger.violations_for(run_ref))}

    # ── Summary ──
    def summary(self, now: str = "") -> AuditSummary:
        runs = ledger.distinct_runs()
        rstate: dict = {}
        for r in runs:
            st = self.run_state(r.get("run_id"))
            rstate[st] = rstate.get(st, 0) + 1
        checks = ledger.read_checks()
        cres: dict = {}
        for c in checks:
            cres[c.get("result")] = cres.get(c.get("result"), 0) + 1
        return AuditSummary(
            timestamp=now, audit_count=len(ledger.read_audits()), run_count=len(runs),
            run_state_distribution=dict(sorted(rstate.items())), check_count=len(checks),
            check_result_distribution=dict(sorted(cres.items())),
            violation_count=len(ledger.read_violations()),
            report_count=len(ledger.read_reports()))
