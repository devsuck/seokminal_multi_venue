"""System Health Engine (P9.1) — 서브시스템 관측 집계 → SystemHealthReport. **집행 아님.**

collectors.collect_all() → SubsystemProbe 목록 → overall_status(최대 심각도)·health_score(평균)
집계 → 해시체인 SystemHealthReport. **상태 변경·거래 인가·브로커 접촉 없음.** 결정적:
동일 헬스 상태 → 동일 report_hash(latency/timestamp 제외). injectable probes 로 테스트 결정성 확보.
"""
from __future__ import annotations

from jarvis.system_health import collectors, ledger
from jarvis.system_health.models import (
    GENESIS,
    SubsystemProbe,
    SystemHealthReport,
    health_score,
    input_hash,
    is_ok,
    overall_status,
    report_hash,
    report_id,
)


class SystemHealthEngine:
    """전 서브시스템 헬스 관측기. 읽기전용·결정적·append-only."""

    def check(self, now: str = "", *, probes: list | None = None,
              commit: bool = False) -> SystemHealthReport:
        """관측 → 집계 → 리포트. probes 주입 시 그대로 사용(테스트 결정성)."""
        if probes is None:
            probes = collectors.collect_all(now)
        probe_dicts = [p.to_dict() if isinstance(p, SubsystemProbe) else dict(p)
                       for p in probes]

        statuses = [p["status"] for p in probe_dicts]
        overall = overall_status(statuses)
        score = health_score(statuses)

        warnings: list = []
        errors: list = []
        for p in probe_dicts:
            for w in p.get("warnings", []):
                warnings.append(f"{p['name']}:{w}")
            for e in p.get("errors", []):
                errors.append(f"{p['name']}:{e}")

        summary = self._summarize(probe_dicts)

        ih = input_hash(probe_dicts)
        rid = report_id(ih)
        rh = report_hash(rid, overall, score, probe_dicts, warnings, errors, ih)

        prev_hash = GENESIS
        if commit and not ledger.report_exists(rid):
            head = ledger.chain_head()
            prev_hash = head["report_hash"] if head else GENESIS

        report = SystemHealthReport(
            report_id=rid, timestamp=now, overall_status=overall, health_score=score,
            subsystems=probe_dicts, summary=summary, warnings=warnings, errors=errors,
            input_hash=ih, report_hash=rh, previous_hash=prev_hash)

        if commit and not ledger.report_exists(rid):
            ledger.append_report(report.to_dict())
        return report

    @staticmethod
    def _summarize(probe_dicts: list) -> dict:
        dist: dict = {}
        for p in probe_dicts:
            dist[p["status"]] = dist.get(p["status"], 0) + 1
        n = len(probe_dicts)
        healthy = sum(1 for p in probe_dicts if is_ok(p["status"]))
        return {
            "total": n,
            "healthy": healthy,
            "unhealthy": n - healthy,
            "status_distribution": dict(sorted(dist.items())),
            "degraded": [p["name"] for p in probe_dicts if not is_ok(p["status"])],
        }
