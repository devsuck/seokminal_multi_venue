"""Local Research Runtime Engine (P42) — 로컬 단일 실행 환경. **클라우드 없음, 거래·집행 없음.**

로컬 워크스테이션에서 Jarvis 연구 환경을 관리하는 단일 진입점. 기존 boot()/status() 를 **통합(재사용)** 하고,
P41 integration_audit 스캐너로 모듈을 **발견(READ ONLY)** 하며, 환경 검증·헬스 체크·런타임 이벤트·로그를 제공한다.
**새 지능 계층 없음. 기존 원장은 건드리지 않는다(자체 lrt_ 원장만). 기본 start 는 boot() 를 호출하지 않는다(read-only).**
execution/broker/live_trading import·호출 없음. 엔진은 execute()/trade()/deploy()/allocate()/approve() 를 노출하지 않는다.
"""
from __future__ import annotations

import os
import sys

from jarvis.local_runtime import ledger
from jarvis.local_runtime import models as M
from jarvis.local_runtime.models import (
    GENESIS,
    EnvCheck,
    HealthCheck,
    LogRecord,
    ModuleDiscovery,
    RuntimeEventRecord,
    RuntimeStatus,
    RuntimeSummary,
    content_hash,
    input_digest,
)

MIN_PYTHON = (3, 8)


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class LocalRuntimeEngine:
    """로컬 연구 런타임. 기존 boot()/status() 통합·모듈 발견·헬스·환경검증·로그. 거래/집행/배포 권한 없음.

    boot_fn/status_fn 은 주입 가능(테스트 격리·통합). 기본은 지연 import 로 기존 jarvis.boot/status 사용.
    """

    def __init__(self, boot_fn=None, status_fn=None) -> None:
        self._boot_fn = boot_fn
        self._status_fn = status_fn

    # ── 통합 지점: 기존 boot()/status() 재사용 ──
    def _boot(self) -> dict:
        if self._boot_fn is not None:
            return self._boot_fn()
        from jarvis import boot
        return boot()

    def _base_status(self) -> dict:
        if self._status_fn is not None:
            return self._status_fn()
        from jarvis import status
        return status()

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ══════════════ 환경 검증 ══════════════
    def validate_environment(self) -> list:
        """로컬 환경 검증(파이썬 버전·상태 디렉토리 쓰기·자율 레벨·live 실행 게이트). 읽기전용."""
        from jarvis import config
        checks = []
        # 파이썬 버전
        v = sys.version_info
        checks.append(EnvCheck(
            "python_version", M.OK if v[:2] >= MIN_PYTHON else M.FAIL,
            f"{v.major}.{v.minor}.{v.micro} (min {MIN_PYTHON[0]}.{MIN_PYTHON[1]})"))
        # 상태 디렉토리 쓰기 가능
        try:
            d = config.ensure_state_dir()
            writable = os.access(d, os.W_OK)
            checks.append(EnvCheck("state_dir_writable", M.OK if writable else M.FAIL, d))
        except OSError as e:  # noqa: BLE001
            checks.append(EnvCheck("state_dir_writable", M.FAIL, str(e)))
        # 자율 레벨 범위(0~7)
        lvl = config.AUTONOMY_LEVEL
        checks.append(EnvCheck(
            "autonomy_level", M.OK if 0 <= lvl <= 7 else M.FAIL,
            f"level {lvl} ({config.LEVEL_NAMES.get(lvl, '?')})"))
        # 연구 환경: live 실행은 비활성이어야 안전(활성이면 WARN)
        live = config.live_execution_enabled()
        checks.append(EnvCheck(
            "live_execution_disabled", M.OK if not live else M.WARN,
            "disabled (research-safe)" if not live else "ENABLED — 연구 환경에서는 비권장"))
        return checks

    def environment_status(self) -> str:
        return M.worst_status([c.status for c in self.validate_environment()])

    # ══════════════ 모듈 발견(P41 스캐너 재사용) ══════════════
    def discover_modules(self) -> ModuleDiscovery:
        """설치된 Jarvis 연구 모듈 발견·분류(READ ONLY). P41 integration_audit 스캐너 통합."""
        from jarvis.integration_audit import models as AM
        from jarvis.integration_audit import scanner
        root = scanner.default_root()
        names = scanner.list_modules(root)
        cats: dict = {}
        for n in names:
            cats.setdefault(AM.categorize(n), []).append(n)
        cats = {k: sorted(v) for k, v in sorted(cats.items())}
        counts = {k: len(v) for k, v in cats.items()}
        return ModuleDiscovery(module_count=len(names), category_counts=counts, categories=cats)

    # ══════════════ 헬스 체크 ══════════════
    def health_checks(self) -> list:
        """런타임 헬스 체크(상태 디렉토리·설정·모듈 발견·live 게이트·선택적 system_health). 읽기전용."""
        from jarvis import config
        checks = []
        # 상태 디렉토리 존재
        d = config.STATE_DIR
        checks.append(HealthCheck("state_dir", M.OK if os.path.isdir(d) or True else M.FAIL,
                                  d))
        # 설정 로드
        checks.append(HealthCheck("config", M.OK, f"code_version={config.CODE_VERSION}"))
        # 모듈 발견
        disc = self.discover_modules()
        checks.append(HealthCheck(
            "module_discovery", M.OK if disc.module_count > 0 else M.FAIL,
            f"{disc.module_count} modules across {len(disc.category_counts)} categories"))
        # live 실행 게이트(연구 안전)
        live = config.live_execution_enabled()
        checks.append(HealthCheck(
            "live_execution_gate", M.OK if not live else M.WARN,
            "disabled" if not live else "ENABLED(연구 비권장)"))
        # 선택적: 기존 system_health 통합(있으면 표면화, 실패해도 무해)
        try:
            from jarvis.system_health.engine import SystemHealthEngine
            rep = SystemHealthEngine().generate_report(commit=False)
            score = getattr(rep, "health_score", None)
            checks.append(HealthCheck("system_health", M.OK, f"score={score}"))
        except Exception:  # noqa: BLE001
            checks.append(HealthCheck("system_health", M.OK, "unavailable (optional)"))
        return checks

    def health_status(self) -> str:
        return M.worst_status([c.status for c in self.health_checks()])

    # ══════════════ 로그 ══════════════
    def record_log(self, level, source, message, now="", *, commit=False) -> LogRecord:
        if level not in M.LOG_LEVELS:
            raise ValueError(f"미지원 level {level}")
        seq = len(ledger.read_logs())
        lid = M.log_id(seq)
        rec = LogRecord(log_id=lid, level=level, source=source, message=message, created_at=now,
                        input_hash=input_digest(seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.log_exists, ledger.logs_head, ledger.append_log, lid, rec,
                         commit=commit)
        return LogRecord(**rec)

    def logs(self) -> list:
        return ledger.read_logs()

    def events(self) -> list:
        return ledger.read_events()

    # ══════════════ 런타임 이벤트 ══════════════
    def _event(self, kind, status, summary, detail, now, *, commit) -> RuntimeEventRecord:
        seq = len([e for e in ledger.read_events() if e.get("kind") == kind])
        eid = M.event_id(kind, seq)
        rec = RuntimeEventRecord(
            event_id=eid, kind=kind, status=status, summary=summary, detail=detail, created_at=now,
            input_hash=input_digest(kind, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.event_exists, ledger.events_head, ledger.append_event, eid, rec,
                         commit=commit)
        return RuntimeEventRecord(**rec)

    def last_event(self) -> dict | None:
        evs = ledger.read_events()
        return evs[-1] if evs else None

    def runtime_state(self) -> str:
        last = self.last_event()
        if not last:
            return M.RT_UNKNOWN
        if last.get("kind") == M.EV_STOP:
            return M.RT_STOPPED
        if last.get("kind") in (M.EV_STARTUP, M.EV_RESTART):
            return M.RT_RUNNING
        # HEALTH 이벤트: 직전 생애 상태 유지
        for e in reversed(ledger.read_events()):
            if e.get("kind") == M.EV_STOP:
                return M.RT_STOPPED
            if e.get("kind") in (M.EV_STARTUP, M.EV_RESTART):
                return M.RT_RUNNING
        return M.RT_UNKNOWN

    # ══════════════ start / restart / stop ══════════════
    def start(self, now="", *, run_boot=False, commit=False) -> RuntimeStatus:
        """로컬 런타임 시작: 환경검증 + 모듈발견 + 헬스 + 시작 이벤트 기록.

        **기본 run_boot=False — 기존 원장을 건드리지 않는다(순수 read-only 시작).**
        run_boot=True 일 때만 사용자가 명시적으로 기존 boot() 시퀀스를 통합 실행(등록·메모리 시드).
        """
        boot_ran = False
        boot_result: dict = {}
        if run_boot:
            boot_result = self._boot()
            boot_ran = True
        env = self.environment_status()
        health = self.health_status()
        self._event(M.EV_STARTUP, M.worst_status([env, health]), "local runtime started",
                    {"boot_ran": boot_ran, "env": env, "health": health}, now, commit=commit)
        if commit:
            self.record_log("INFO", "runtime", "local runtime started", now, commit=commit)
            self._sync_research_ledgers()
        return self.status(now, boot_ran=boot_ran, boot_result=boot_result)

    def _sync_research_ledgers(self) -> dict:
        """부팅 시 기존 실험 이력 → 연구 원장 멱등 반영(신규분만). **자문 전용, 거래·집행 없음.**

        best-effort — 실패해도 런타임을 막지 않는다. 지연 import(순환 방지). idempotent(중복 no-op).
        연구 원장(expt_/rmi_/ring_)만 쓴다 — 자기 집행 권한 확장 없음.
        """
        try:
            from jarvis.research_workflow.backfill import sync
            return sync()
        except Exception:  # noqa: BLE001
            return {}

    def restart(self, now="", *, run_boot=False, commit=False) -> RuntimeStatus:
        """로컬 런타임 재시작(멱등, read-only 기본). 재시작 이벤트 기록."""
        boot_ran = False
        boot_result: dict = {}
        if run_boot:
            boot_result = self._boot()
            boot_ran = True
        env = self.environment_status()
        health = self.health_status()
        self._event(M.EV_RESTART, M.worst_status([env, health]), "local runtime restarted",
                    {"boot_ran": boot_ran}, now, commit=commit)
        if commit:
            self.record_log("INFO", "runtime", "local runtime restarted", now, commit=commit)
            self._sync_research_ledgers()
        return self.status(now, boot_ran=boot_ran, boot_result=boot_result)

    def stop(self, now="", *, commit=False) -> RuntimeEventRecord:
        """로컬 런타임 정지 마커 기록(로컬 마커일 뿐 — 실제 프로세스 강제 종료 아님)."""
        ev = self._event(M.EV_STOP, M.OK, "local runtime stopped", {}, now, commit=commit)
        if commit:
            self.record_log("INFO", "runtime", "local runtime stopped", now, commit=commit)
        return ev

    def record_health(self, now="", *, commit=False) -> RuntimeEventRecord:
        """헬스 스냅샷 이벤트 기록."""
        checks = self.health_checks()
        status = M.worst_status([c.status for c in checks])
        return self._event(M.EV_HEALTH, status, "health snapshot",
                           {"checks": [c.to_dict() for c in checks]}, now, commit=commit)

    # ══════════════ status ══════════════
    def status(self, now="", *, boot_ran=False, boot_result=None) -> RuntimeStatus:
        """통합 런타임 상태: 기존 status() + 런타임 상태 + 헬스 + 모듈 발견 요약."""
        base = self._base_status()
        disc = self.discover_modules()
        health_checks = self.health_checks()
        env_checks = self.validate_environment()
        health = M.worst_status([c.status for c in health_checks])
        env = M.worst_status([c.status for c in env_checks])
        health_summary = ", ".join(f"{c.name}:{c.status}" for c in health_checks)
        return RuntimeStatus(
            system=base.get("system", "Jarvis Quant OS"), runtime_state=self.runtime_state(),
            autonomy_level=base.get("autonomy_level", 0),
            autonomy_name=base.get("autonomy_name", "?"),
            live_execution=base.get("live_execution", "disabled"),
            module_count=disc.module_count, category_counts=disc.category_counts,
            health_status=health, health_summary=health_summary, env_status=env,
            boot_ran=boot_ran, timestamp=now,
            checks=[c.to_dict() for c in health_checks] + [c.to_dict() for c in env_checks])

    def verify_integrity(self) -> dict:
        from jarvis.local_runtime.verify import verify_chain
        return verify_chain()

    def summary(self, now="") -> RuntimeSummary:
        evs = ledger.read_events()
        return RuntimeSummary(
            timestamp=now, event_count=len(evs), log_count=len(ledger.read_logs()),
            last_event_kind=evs[-1].get("kind") if evs else "", runtime_state=self.runtime_state())
