"""System Integration Engine (P35) — 전체 연구 생태계 정적 검증. **통합·검증 전용, 기능 추가 없음.**

계층 간 무결성·소유권·원장·해시·계보·안전성·API 일관성을 검증한다(정적 검사·파일 읽기만, import 결합 없음). **계층 변경
없음.** execution/broker/live_trading/portfolio_execution import·호출 없음. VALIDATION ≠ MUTATION · INTEGRATION ≠
EXECUTION. 결정적·불변·append-only. 검증 대상 계층은 READ ONLY.
"""
from __future__ import annotations

import ast
import os

from jarvis.system_integration import ledger
from jarvis.system_integration import models as M
from jarvis.system_integration.models import (
    GENESIS,
    ArtifactRecord,
    FindingRecord,
    IntegrationSummary,
    SystemReportRecord,
    ValidationRecord,
    content_hash,
    input_digest,
)

_JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DISCLAIMER = ("System Integration & Final Validation 데이터 — VALIDATION ≠ MUTATION · INTEGRATION ≠ "
               "EXECUTION. 계층 간 무결성·소유권·원장·해시·계보·안전성·API 일관성 검증 전용 — 기능 추가·계층 변경·실행·"
               "거래·배포 없음. 검증 대상 계층은 정적 검사·파일 읽기만(변경 없음).")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


def _pkg_dir(package) -> str:
    return os.path.join(_JARVIS_ROOT, package)


def _src_files(package) -> list:
    d = _pkg_dir(package)
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".py")]


class SystemIntegrationEngine:
    """시스템 통합·검증 엔진. 불변·append-only·결정적. 계층 변경/실행/거래/배포 권한 없음 — 정적 검증만."""

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

    # ══════════════ 개별 정적 검사(계층별, 결정적) ══════════════
    def check_structure(self, package) -> dict:
        """구조 검증: 필수 모듈 존재."""
        d = _pkg_dir(package)
        missing = [m for m in M.REQUIRED_MODULES if not os.path.exists(os.path.join(d, m))]
        return {"layer": package, "check_type": "STRUCTURE", "status": "PASS" if not missing
                else "FAIL", "detail": "ok" if not missing else f"missing:{missing}"}

    def check_prefix_confinement(self, package, prefix) -> dict:
        """접두사 확인: ledger.py 가 소유 접두사를 참조."""
        path = os.path.join(_pkg_dir(package), "ledger.py")
        if not os.path.exists(path):
            return {"layer": package, "check_type": "PREFIX_CONFINEMENT", "status": "FAIL",
                    "detail": "no ledger.py"}
        src = open(path).read()
        ok = f'"{prefix}' in src
        return {"layer": package, "check_type": "PREFIX_CONFINEMENT",
                "status": "PASS" if ok else "FAIL",
                "detail": "ok" if ok else f"prefix {prefix} not found"}

    def check_safety_imports(self, package) -> dict:
        """안전성(import): 금지 실행/브로커/라이브 import 없음."""
        bad = []
        for path in _src_files(package):
            if os.path.basename(os.path.dirname(path)) == "tests":
                continue
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
        return {"layer": package, "check_type": "SAFETY_IMPORTS",
                "status": "PASS" if not bad else "FAIL", "detail": "ok" if not bad else str(bad)}

    def check_safety_methods(self, package) -> dict:
        """안전성(메서드): 금지 실행/거래/배포 메서드 정의 없음."""
        bad = []
        for path in _src_files(package):
            tree = ast.parse(open(path).read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.lower() in M.FORBIDDEN_METHOD_NAMES:
                        bad.append(f"{os.path.basename(path)}:{node.name}")
        return {"layer": package, "check_type": "SAFETY_METHODS",
                "status": "PASS" if not bad else "FAIL", "detail": "ok" if not bad else str(bad)}

    def check_append_only(self, package) -> dict:
        """원장 검증: ledger.py append-only('a' 존재, 'w' 부재)."""
        path = os.path.join(_pkg_dir(package), "ledger.py")
        if not os.path.exists(path):
            return {"layer": package, "check_type": "APPEND_ONLY", "status": "FAIL",
                    "detail": "no ledger.py"}
        src = open(path).read()
        ok = '"a"' in src and '"w"' not in src
        return {"layer": package, "check_type": "APPEND_ONLY", "status": "PASS" if ok else "FAIL",
                "detail": "ok" if ok else "write-mode or missing append"}

    def check_model_leak(self, package) -> dict:
        """모델 식별자 유출 없음(소스)."""
        bad = []
        for path in _src_files(package):
            if os.path.basename(os.path.dirname(path)) == "tests":
                continue
            if M.MODEL_LEAK_TOKEN in open(path).read().lower():
                bad.append(os.path.basename(path))
        return {"layer": package, "check_type": "MODEL_LEAK",
                "status": "PASS" if not bad else "FAIL", "detail": "ok" if not bad else str(bad)}

    def check_api_consistency(self, package) -> dict:
        """API 일관성: verify.py 가 verify_chain·replay 노출."""
        path = os.path.join(_pkg_dir(package), "verify.py")
        if not os.path.exists(path):
            return {"layer": package, "check_type": "API_CONSISTENCY", "status": "FAIL",
                    "detail": "no verify.py"}
        src = open(path).read()
        ok = "def verify_chain(" in src and "def replay(" in src
        return {"layer": package, "check_type": "API_CONSISTENCY",
                "status": "PASS" if ok else "FAIL",
                "detail": "ok" if ok else "missing verify_chain/replay"}

    # ══════════════ 계층 간 무결성(레지스트리) ══════════════
    def check_ownership(self) -> dict:
        """소유권 검증: 등록 접두사·패키지 유일(중복 소유 없음)."""
        ok = M.prefixes_unique() and M.packages_unique()
        return {"layer": "*", "check_type": "OWNERSHIP", "status": "PASS" if ok else "FAIL",
                "detail": "unique" if ok else "duplicate prefix/package"}

    # ══════════════ 범용 해시체인 검증(모든 계층 공통 알고리즘) ══════════════
    def verify_hash_chain(self, records) -> dict:
        """임의 원장 레코드의 해시체인 검증(결정적, 모든 계층 공통)."""
        return M.verify_hash_records(records)

    def check_lineage(self, records) -> dict:
        """계보 검증: 아티팩트 parent 참조·순환(임의 아티팩트 집합)."""
        aids = {a.get("artifact_id") for a in records}
        edges = []
        issues = []
        for a in records:
            parent = a.get("parent_artifact")
            if parent:
                if parent not in aids:
                    issues.append(f"missing_parent:{a.get('artifact_id')}")
                edges.append((a.get("artifact_id"), parent))
        if M.detect_cycle_check(edges):
            issues.append("cycle")
        return {"check_type": "LINEAGE", "status": "PASS" if not issues else "FAIL",
                "detail": "ok" if not issues else str(issues)}

    # ══════════════ 전체 검증 실행 ══════════════
    def _layer_checks(self, layer) -> list:
        pkg, pfx = layer["package"], layer["prefix"]
        return [self.check_structure(pkg), self.check_prefix_confinement(pkg, pfx),
                self.check_safety_imports(pkg), self.check_safety_methods(pkg),
                self.check_append_only(pkg), self.check_model_leak(pkg),
                self.check_api_consistency(pkg)]

    def run_full_validation(self, scope="SYSTEM", now="", *, commit=False) -> dict:
        """전체 계층(P21~P34) 정적 검증 실행 → 발견·검증 기록. **검증만 — 변경 없음.**"""
        findings = [self.check_ownership()]
        for layer in M.LAYER_REGISTRY:
            findings.extend(self._layer_checks(layer))
        passed = sum(1 for f in findings if f["status"] == "PASS")
        failed = sum(1 for f in findings if f["status"] == "FAIL")
        if commit:
            seq = 0
            for f in findings:
                fid = M.finding_id(f.get("layer", "*"), f["check_type"], seq)
                seq += 1
                rec = FindingRecord(finding_id=fid, layer=f.get("layer", "*"),
                                    check_type=f["check_type"], status=f["status"],
                                    detail=f["detail"], created_at=now,
                                    input_hash=input_digest(f.get("layer", "*"), f["check_type"], seq),
                                    previous_hash=GENESIS).to_dict()
                self._emit(ledger.finding_exists, ledger.findings_head, ledger.append_finding, fid,
                           rec, commit=commit)
        vid = M.validation_id(scope, now)
        vrec = ValidationRecord(validation_id=vid, scope=scope, checks_run=len(findings),
                                checks_passed=passed, checks_failed=failed, all_passed=(failed == 0),
                                created_at=now, input_hash=input_digest(scope, now),
                                previous_hash=GENESIS).to_dict()
        vrec = self._emit(ledger.validation_exists, ledger.validations_head, ledger.append_validation,
                          vid, vrec, commit=commit)
        self._artifact(M.ART_VALIDATION, vid, "", now, commit=commit)
        return {"validation": ValidationRecord(**vrec).to_dict(), "findings": findings,
                "all_passed": failed == 0}

    # ══════════════ 아키텍처 요약 / 의존성 그래프 ══════════════
    def architecture_summary(self) -> dict:
        """아키텍처 요약(계층 레지스트리, 결정적)."""
        return {"layer_count": len(M.LAYER_REGISTRY),
                "layers": [{"phase": l["phase"], "package": l["package"], "prefix": l["prefix"]}
                           for l in M.LAYER_REGISTRY],
                "prefixes": M.registered_prefixes()}

    def dependency_graph(self) -> dict:
        """의존성 그래프(각 계층의 상위 READ ONLY 소스, 정적 파싱). 순환 없음(단방향 상위 참조)."""
        graph: dict = {}
        for layer in M.LAYER_REGISTRY:
            path = os.path.join(_pkg_dir(layer["package"]), "ledger.py")
            deps = []
            if os.path.exists(path):
                src = open(path).read()
                if "SOURCE_LAYERS" in src:
                    for other in M.LAYER_REGISTRY:
                        if other["package"] != layer["package"] and f'"{other["prefix"]}' in \
                                src.split("SOURCE_LAYERS", 1)[1]:
                            deps.append(other["package"])
            graph[layer["package"]] = sorted(set(deps))
        return graph

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> SystemReportRecord:
        """시스템 리포트(검증·발견 집계 + 아키텍처 요약 + 의존성 그래프). **is_binding=False.**"""
        findings = ledger.read_findings()
        ct_dist: dict = {}
        for f in findings:
            ct_dist[f.get("check_type")] = ct_dist.get(f.get("check_type"), 0) + 1
        rid = M.report_id(scope, now)
        rec = SystemReportRecord(
            report_id=rid, scope=scope, layer_count=len(M.LAYER_REGISTRY),
            validation_count=len(ledger.read_validations()), finding_count=len(findings),
            failed_finding_count=sum(1 for f in findings if f.get("status") == "FAIL"),
            check_type_distribution=dict(sorted(ct_dist.items())),
            architecture_summary=self.architecture_summary(), dependency_graph=self.dependency_graph(),
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return SystemReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.system_integration.verify import verify_chain
        return verify_chain()

    def summary(self, now="") -> IntegrationSummary:
        return IntegrationSummary(
            timestamp=now, layer_count=len(M.LAYER_REGISTRY),
            validation_count=len(ledger.read_validations()), finding_count=len(ledger.read_findings()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
