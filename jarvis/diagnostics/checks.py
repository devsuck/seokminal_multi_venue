"""진단 (P14) — 원장·계보·성능 건강 점검. **관찰·경고 전용, 원본 불변.**

죽은 원장·대형 원장·느린 replay·깨진 계보·스냅샷 드리프트·성능 회귀를 결정적으로 탐지해 Diagnostic 으로 보고한다.
자동 조치·복구·실행을 하지 않는다 — 관찰과 경고만. 기존 모듈을 변경하지 않는다(완전 additive).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# 심각도
INFO = "INFO"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
SEVERITIES = (INFO, WARNING, CRITICAL)
_ORDER = {INFO: 0, WARNING: 1, CRITICAL: 2}


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str
    subject: str
    detail: str
    is_actionable: bool = False   # 항상 False — 관찰·경고만, 자동 조치 없음

    def to_dict(self) -> dict:
        return asdict(self)


def dead_ledger(subject: str, record_count: int) -> Diagnostic | None:
    """죽은(빈) 원장 탐지."""
    if record_count <= 0:
        return Diagnostic("DEAD_LEDGER", WARNING, subject, "ledger has 0 records")
    return None


def large_ledger(subject: str, record_count: int, *, threshold: int = 100000) -> Diagnostic | None:
    """대형 원장 경고(임계 초과)."""
    if record_count > threshold:
        return Diagnostic("LARGE_LEDGER", WARNING, subject,
                          f"records={record_count} > threshold={threshold}")
    return None


def slow_replay(subject: str, duration: float, *, threshold: float = 1.0) -> Diagnostic | None:
    """느린 replay 경고(임계 초과)."""
    if duration > threshold:
        return Diagnostic("SLOW_REPLAY", WARNING, subject,
                          f"duration={duration} > threshold={threshold}")
    return None


def broken_lineage(artifacts: list, *, id_field: str = "artifact_id",
                   parent_field: str = "parent_artifact") -> list:
    """깨진 계보(dangling parent) 탐지 — CRITICAL 목록."""
    ids = {a.get(id_field) for a in artifacts}
    out: list = []
    for a in artifacts:
        parent = a.get(parent_field)
        if parent and parent not in ids:
            out.append(Diagnostic("BROKEN_LINEAGE", CRITICAL, a.get(id_field),
                                  f"dangling parent {parent}"))
    return out


def snapshot_drift(previous: dict, current: dict) -> list:
    """스냅샷 드리프트 탐지(키별 카운트 변화). 감소=WARNING, 증가/신규/삭제=INFO."""
    out: list = []
    for key in sorted(set(previous) | set(current)):
        p = previous.get(key)
        c = current.get(key)
        if p == c:
            continue
        if p is None:
            out.append(Diagnostic("SNAPSHOT_DRIFT", INFO, key, f"added: {c}"))
        elif c is None:
            out.append(Diagnostic("SNAPSHOT_DRIFT", WARNING, key, f"removed (was {p})"))
        elif isinstance(p, (int, float)) and isinstance(c, (int, float)) and c < p:
            out.append(Diagnostic("SNAPSHOT_DRIFT", WARNING, key, f"decreased {p}->{c}"))
        else:
            out.append(Diagnostic("SNAPSHOT_DRIFT", INFO, key, f"changed {p}->{c}"))
    return out


def performance_regression(compare_result: dict) -> list:
    """벤치마크 비교(compare_reports) 결과에서 회귀 탐지 — WARNING."""
    out: list = []
    for reg in compare_result.get("regressions", []):
        out.append(Diagnostic("PERF_REGRESSION", WARNING, reg.get("name"),
                              f"per_iter {reg.get('previous')}->{reg.get('current')}"))
    if not compare_result.get("same_workload", True):
        out.append(Diagnostic("WORKLOAD_CHANGED", INFO, "suite",
                              "benchmark workload fingerprint differs"))
    return out


def run_diagnostics(*, ledgers: dict | None = None, replays: dict | None = None,
                    artifacts: list | None = None, snapshots: tuple | None = None,
                    compare_result: dict | None = None, large_threshold: int = 100000,
                    slow_threshold: float = 1.0) -> dict:
    """전체 진단 집계 → 결정적 리포트(심각도별 카운트 + 정렬 목록).

    ledgers: {subject: record_count}, replays: {subject: duration},
    artifacts: 계보 목록, snapshots: (previous, current), compare_result: compare_reports 산출.
    """
    findings: list = []
    for subject, cnt in sorted((ledgers or {}).items()):
        d = dead_ledger(subject, cnt)
        if d:
            findings.append(d)
        lg = large_ledger(subject, cnt, threshold=large_threshold)
        if lg:
            findings.append(lg)
    for subject, dur in sorted((replays or {}).items()):
        d = slow_replay(subject, dur, threshold=slow_threshold)
        if d:
            findings.append(d)
    if artifacts is not None:
        findings.extend(broken_lineage(artifacts))
    if snapshots is not None:
        findings.extend(snapshot_drift(snapshots[0], snapshots[1]))
    if compare_result is not None:
        findings.extend(performance_regression(compare_result))

    findings.sort(key=lambda d: (-_ORDER[d.severity], d.code, d.subject or ""))
    by_sev = {s: sum(1 for d in findings if d.severity == s) for s in SEVERITIES}
    return {"ok": by_sev[CRITICAL] == 0, "total": len(findings), "by_severity": by_sev,
            "findings": [d.to_dict() for d in findings],
            "healthy": len(findings) == 0}
