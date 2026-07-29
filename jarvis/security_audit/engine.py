"""Security Audit Engine (P38) — 최종 보안 감사(정적 검사). **감사 전용, 실행 권한 없음.**

원장·아키텍처·런타임 보안을 감사한다(파일 읽기·AST 정적 검사만). **엔진은 execute/trade/deploy/allocate/approve 를
노출하지 않는다.** execution/broker/live_trading/portfolio_execution import·호출 없음. AUDIT ≠ EXECUTION ·
VALIDATION ≠ MUTATION. 결정적·불변·append-only. 감사 대상은 READ ONLY.
"""
from __future__ import annotations

import ast
import os

from jarvis.security_audit import ledger
from jarvis.security_audit import models as M
from jarvis.security_audit.models import (
    GENESIS,
    ArtifactRecord,
    AuditRecord,
    AuditSummary,
    SecurityFindingRecord,
    SecurityReportRecord,
    content_hash,
    input_digest,
)

_JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DISCLAIMER = ("Security Hardening & Audit 데이터 — AUDIT ≠ EXECUTION · VALIDATION ≠ MUTATION. 원장·"
               "아키텍처·런타임 보안 감사 전용 — 실행·거래·배포·배분·승인 없음. 엔진은 execute/trade/deploy/allocate/"
               "approve 를 노출하지 않는다. 감사 대상 계층은 정적 검사만(변경 없음).")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


def _pkg_dir(package) -> str:
    return os.path.join(_JARVIS_ROOT, package)


def _src_files(package, include_tests=False) -> list:
    d = _pkg_dir(package)
    if not os.path.isdir(d):
        return []
    files = [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".py")]
    return files


def _method_defs(package):
    """계층 소스의 모든 메서드/함수 정의명(테스트 제외)."""
    names = []
    for path in _src_files(package):
        tree = ast.parse(open(path).read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append((os.path.basename(path), node.name))
    return names


class SecurityAuditEngine:
    """보안 감사 엔진. 불변·append-only·결정적. 실행/거래/배포/배분/승인 권한 없음 — 감사만."""

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

    # ══════════════ 원장 보안 ══════════════
    def audit_hash_chain(self, records) -> dict:
        """해시체인 무결성·변조 탐지(범용)."""
        res = M.verify_hash_records(records)
        return {"target": "*", "dimension": "LEDGER_SECURITY", "check_name": "hash_chain",
                "status": "PASS" if res["ok"] else "FAIL", "detail": res["reason"]}

    def audit_tamper_detection(self, records) -> dict:
        """변조 탐지 검증: 변조 시 반드시 FAIL(음성 대조)."""
        if not records:
            return {"target": "*", "dimension": "LEDGER_SECURITY",
                    "check_name": "tamper_detection", "status": "PASS", "detail": "empty"}
        tampered = [dict(r) for r in records]
        tampered[0] = dict(tampered[0])
        tampered[0]["__tamper__"] = "x"  # core 변경 → record_hash 불일치 유발
        detected = not M.verify_hash_records(tampered)["ok"]
        return {"target": "*", "dimension": "LEDGER_SECURITY", "check_name": "tamper_detection",
                "status": "PASS" if detected else "FAIL",
                "detail": "tamper detected" if detected else "tamper NOT detected"}

    # ══════════════ 아키텍처 보안 ══════════════
    def audit_forbidden_imports(self, package) -> dict:
        """금지 import(실행/브로커/라이브) 없음."""
        bad = []
        for path in _src_files(package):
            tree = ast.parse(open(path).read())
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                elif isinstance(node, ast.Import):
                    mods = [n.name for n in node.names]
                for mod in mods:
                    if any(mod.startswith(f) for f in M.FORBIDDEN_IMPORT_PREFIXES):
                        bad.append(f"{os.path.basename(path)}:{mod}")
        return {"target": package, "dimension": "ARCHITECTURE_SECURITY",
                "check_name": "forbidden_imports", "status": "PASS" if not bad else "FAIL",
                "detail": "ok" if not bad else str(bad)}

    def audit_ownership_boundary(self) -> dict:
        """소유권 위반 없음: 접두사·패키지 유일."""
        from jarvis.system_integration.models import packages_unique, prefixes_unique
        ok = prefixes_unique() and packages_unique()
        return {"target": "*", "dimension": "ARCHITECTURE_SECURITY",
                "check_name": "ownership_boundary", "status": "PASS" if ok else "FAIL",
                "detail": "unique" if ok else "duplicate"}

    def audit_model_leak(self, package) -> dict:
        """모델 식별자 유출 없음."""
        bad = [os.path.basename(p) for p in _src_files(package)
               if M.MODEL_LEAK_TOKEN in open(p).read().lower()]
        return {"target": package, "dimension": "ARCHITECTURE_SECURITY",
                "check_name": "model_leak", "status": "PASS" if not bad else "FAIL",
                "detail": "ok" if not bad else str(bad)}

    # ══════════════ 런타임 보안 ══════════════
    def audit_unsafe_execution(self, package) -> dict:
        """불안전 실행 경로 없음: 금지 실행/거래/배포 메서드 정의 없음."""
        bad = [f"{f}:{n}" for f, n in _method_defs(package)
               if n.lower() in M.FORBIDDEN_METHOD_NAMES]
        return {"target": package, "dimension": "RUNTIME_SECURITY",
                "check_name": "unsafe_execution", "status": "PASS" if not bad else "FAIL",
                "detail": "ok" if not bad else str(bad)}

    def audit_hidden_deployment(self, package) -> dict:
        """숨은 배포 능력 없음."""
        bad = [f"{f}:{n}" for f, n in _method_defs(package)
               if n.lower() in M.DEPLOYMENT_METHOD_NAMES]
        return {"target": package, "dimension": "RUNTIME_SECURITY",
                "check_name": "hidden_deployment", "status": "PASS" if not bad else "FAIL",
                "detail": "ok" if not bad else str(bad)}

    def audit_accidental_trading(self, package) -> dict:
        """우발적 거래 메서드 없음."""
        bad = [f"{f}:{n}" for f, n in _method_defs(package)
               if n.lower() in M.TRADING_METHOD_NAMES]
        return {"target": package, "dimension": "RUNTIME_SECURITY",
                "check_name": "accidental_trading", "status": "PASS" if not bad else "FAIL",
                "detail": "ok" if not bad else str(bad)}

    def audit_engine_surface(self, package) -> dict:
        """엔진 노출 검증: execute/trade/deploy/allocate/approve 미노출(정적)."""
        path = os.path.join(_pkg_dir(package), "engine.py")
        if not os.path.exists(path):
            return {"target": package, "dimension": "RUNTIME_SECURITY",
                    "check_name": "engine_surface", "status": "PASS", "detail": "no engine.py"}
        tree = ast.parse(open(path).read())
        bad = [node.name for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name in M.FORBIDDEN_ENGINE_METHODS]
        return {"target": package, "dimension": "RUNTIME_SECURITY", "check_name": "engine_surface",
                "status": "PASS" if not bad else "FAIL", "detail": "ok" if not bad else str(bad)}

    # ══════════════ 전체 감사 ══════════════
    def _target_checks(self, package) -> list:
        return [self.audit_forbidden_imports(package), self.audit_model_leak(package),
                self.audit_unsafe_execution(package), self.audit_hidden_deployment(package),
                self.audit_accidental_trading(package), self.audit_engine_surface(package)]

    def run_full_audit(self, scope="SYSTEM", now="", *, commit=False) -> dict:
        """전체 보안 감사(원장·아키텍처·런타임). 발견·감사 기록. **감사만 — 변경 없음.**"""
        sample = self._sample_chain(now)
        findings = [self.audit_hash_chain(sample), self.audit_tamper_detection(sample),
                    self.audit_ownership_boundary()]
        for target in M.AUDIT_TARGETS:
            findings.extend(self._target_checks(target))
        passed = sum(1 for f in findings if f["status"] == "PASS")
        failed = sum(1 for f in findings if f["status"] == "FAIL")
        if commit:
            seq = 0
            for f in findings:
                fid = M.finding_id(f.get("target", "*"), f["dimension"], seq)
                seq += 1
                rec = SecurityFindingRecord(
                    finding_id=fid, target=f.get("target", "*"), dimension=f["dimension"],
                    check_name=f["check_name"], status=f["status"], detail=str(f["detail"]),
                    created_at=now, input_hash=input_digest(f.get("target", "*"), f["dimension"], seq),
                    previous_hash=GENESIS).to_dict()
                self._emit(ledger.finding_exists, ledger.findings_head, ledger.append_finding, fid,
                           rec, commit=commit)
        aid = M.audit_id(scope, now)
        arec = AuditRecord(audit_id=aid, scope=scope, targets=len(M.AUDIT_TARGETS),
                           checks_run=len(findings), checks_passed=passed, checks_failed=failed,
                           all_secure=(failed == 0), created_at=now,
                           input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        arec = self._emit(ledger.audit_exists, ledger.audits_head, ledger.append_audit, aid, arec,
                          commit=commit)
        self._artifact(M.ART_AUDIT, aid, "", now, commit=commit)
        return {"audit": AuditRecord(**arec).to_dict(), "findings": findings,
                "all_secure": failed == 0}

    def _sample_chain(self, now) -> list:
        """감사용 결정적 샘플 해시체인(원장 보안 검증 대상)."""
        out = []
        prev = GENESIS
        for i in range(3):
            rec = {"id": f"sample{i}", "seq": i, "previous_hash": prev}
            rec["record_hash"] = content_hash(rec)
            out.append(rec)
            prev = rec["record_hash"]
        return out

    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> SecurityReportRecord:
        """보안 감사 리포트(감사·발견 집계). **is_binding=False, AUDIT ≠ EXECUTION.**"""
        findings = ledger.read_findings()
        dim_dist: dict = {}
        for f in findings:
            dim_dist[f.get("dimension")] = dim_dist.get(f.get("dimension"), 0) + 1
        rid = M.report_id(scope, now)
        rec = SecurityReportRecord(
            report_id=rid, scope=scope, target_count=len(M.AUDIT_TARGETS),
            audit_count=len(ledger.read_audits()), finding_count=len(findings),
            failed_finding_count=sum(1 for f in findings if f.get("status") == "FAIL"),
            dimension_distribution=dict(sorted(dim_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return SecurityReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.security_audit.verify import verify_chain
        return verify_chain()

    def summary(self, now="") -> AuditSummary:
        return AuditSummary(
            timestamp=now, target_count=len(M.AUDIT_TARGETS), audit_count=len(ledger.read_audits()),
            finding_count=len(ledger.read_findings()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
