"""Local Research Automation Engine (P45) — 반복 연구 작업 자동화. **워크플로 보조, 거래·배포·배분 없음.**

잡·스케줄·실행 이력·로그를 관리하고, 연구 안전 작업(데이터 새로고침·품질검사·연구점검·리포트·메모리·헬스)을
워크플로로 보조한다. **자동 거래·자동 배포·자동 자본 배분 없음 — 거래/배포/배분 잡은 등록 거부.** execution/broker/
live_trading import·호출 없음. 엔진은 execute()/trade()/deploy()/allocate()/approve() 를 노출하지 않는다.
run_job 은 주입된 연구 안전 콜러블만 실행(기본 record-only), 산출은 is_binding=False. 결정적·불변·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.local_automation import ledger
from jarvis.local_automation import models as M
from jarvis.local_automation.models import (
    GENESIS,
    AutomationReportRecord,
    AutomationSummary,
    IllegalJobTransition,
    JobEventRecord,
    JobRunRecord,
    LogRecord,
    ScheduleRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
)


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class LocalAutomationEngine:
    """로컬 연구 자동화 엔진. 워크플로 보조·이력 기록. 자동 거래/배포/배분 권한 없음. 이벤트 소싱·결정적."""

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ══════════════ 잡 생애주기(event-sourced) ══════════════
    def _job_event(self, job, name, kind, frm, to, note, now, *, commit):
        seq = len(ledger.job_events(job))
        eid = M.job_event_id(job, to, seq)
        rec = JobEventRecord(
            job_event_id=eid, job_id=job, name=name, kind=kind, from_state=frm, to_state=to,
            note=note, occurred_at=now, input_hash=input_digest(job, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.job_event_exists, ledger.jobs_head, ledger.append_job_event, eid,
                         rec, commit=commit)
        return JobEventRecord(**rec)

    def job_state(self, job) -> str | None:
        evs = ledger.job_events(job)
        return evs[-1].get("to_state") if evs else None

    def _job_meta(self, job) -> dict:
        evs = ledger.job_events(job)
        if not evs:
            raise UnknownEntityError(f"미등록 잡 {job}")
        g = evs[0]
        return {"name": g.get("name"), "kind": g.get("kind"), "state": evs[-1].get("to_state")}

    def register_job(self, name, kind, now="", *, commit=False) -> JobEventRecord:
        """자동화 잡 등록(genesis REGISTERED). **거래/배포/배분 종류는 거부.**"""
        kind = M.validate_job_kind(kind)
        job = M.job_id(name)
        evs = ledger.job_events(job)
        if evs:
            return JobEventRecord(**{k: v for k, v in evs[0].items()
                                     if k in JobEventRecord.__dataclass_fields__})
        return self._job_event(job, name, kind, GENESIS, M.J_REGISTERED, "registered", now,
                               commit=commit)

    def _transition(self, job, to, note, now, *, commit):
        m = self._job_meta(job)
        frm = m["state"]
        if not M.can_job_transition(frm, to):
            raise IllegalJobTransition(f"잡 {job} {frm}→{to} 불가")
        return self._job_event(job, m["name"], m["kind"], frm, to, note, now, commit=commit)

    def enable_job(self, job, note="enabled", now="", *, commit=False):
        return self._transition(job, M.J_ENABLED, note, now, commit=commit)

    def disable_job(self, job, note="disabled", now="", *, commit=False):
        return self._transition(job, M.J_DISABLED, note, now, commit=commit)

    def archive_job(self, job, note="archived", now="", *, commit=False):
        return self._transition(job, M.J_ARCHIVED, note, now, commit=commit)

    # ══════════════ 스케줄 ══════════════
    def set_schedule(self, job, cadence, enabled=True, now="", *, commit=False) -> ScheduleRecord:
        """잡 스케줄 설정(케이던스). **실제 스레드 없음 — 디스크립터·결정적 예정 판정만.**"""
        self._job_meta(job)
        cad = (cadence or "").strip().upper()
        if cad not in M.CADENCES:
            raise ValueError(f"미지원 케이던스 {cadence}")
        sid = M.schedule_id(job)
        rec = ScheduleRecord(
            schedule_id=sid, job_id=job, cadence=cad, enabled=bool(enabled), created_at=now,
            input_hash=input_digest(job, cad), previous_hash=GENESIS).to_dict()
        # 스케줄은 최신값 append(이력 유지). 동일 내용 재기록 방지 위해 내용 해시 기준 존재 확인.
        exists = any(s.get("schedule_id") == sid and s.get("cadence") == cad
                     and s.get("enabled") == bool(enabled) for s in ledger.read_schedules())
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists:
            head = ledger.schedules_head()
            ledger.append_schedule(_seal(rec, head["record_hash"] if head else GENESIS))
        return ScheduleRecord(**rec)

    def due_jobs(self, tick) -> list:
        """틱(정수)에서 실행 예정인 잡(스케줄 enabled + 케이던스 due). 결정적."""
        out = []
        for s in ledger.read_schedules():
            if s.get("enabled") and M.is_due(s.get("cadence"), tick):
                out.append(s.get("job_id"))
        return sorted(set(out))

    # ══════════════ 실행(run_job) ══════════════
    def run_job(self, job, action=None, now="", *, commit=False) -> JobRunRecord:
        """잡 1회 실행 기록. 비활성/보관 잡은 SKIPPED. **action 은 연구 안전 콜러블만(기본 record-only).**

        action() -> dict({"ok": bool, "summary": str, ...}). 예외 시 FAILED. is_binding 은 항상 False.
        """
        meta = self._job_meta(job)
        seq = len(ledger.runs_for(job))
        rid = M.run_id(job, seq)
        state = meta["state"]
        if state in (M.J_DISABLED, M.J_ARCHIVED):
            status, summary, payload = M.RUN_SKIPPED, f"job {state.lower()} — skipped", {}
        elif action is None:
            status, summary, payload = (M.RUN_SUCCESS, "recorded (no-op workflow step)",
                                        {"kind": meta["kind"]})
        else:
            try:
                res = action() or {}
                ok = bool(res.get("ok", True))
                status = M.RUN_SUCCESS if ok else M.RUN_FAILED
                summary = str(res.get("summary", status.lower()))
                payload = res
            except Exception as e:  # noqa: BLE001
                status, summary, payload = M.RUN_FAILED, f"error: {e}", {}
        rec = JobRunRecord(
            run_id=rid, job_id=job, kind=meta["kind"], status=status, summary=summary,
            result_digest=M.result_digest(payload), is_binding=False, created_at=now,
            input_hash=input_digest(job, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.run_exists, ledger.runs_head, ledger.append_run, rid, rec,
                         commit=commit)
        return JobRunRecord(**rec)

    def run_pipeline(self, job_list, action_map=None, now="", *, commit=False) -> list:
        """잡 목록을 순서대로 실행(워크플로 보조: 데이터 확인→품질검사→기록→요약→통지). 각 실행 기록."""
        action_map = action_map or {}
        out = []
        for job in job_list:
            out.append(self.run_job(job, action_map.get(job), now, commit=commit))
        return out

    def run_due(self, tick, action_map=None, now="", *, commit=False) -> list:
        return self.run_pipeline(self.due_jobs(tick), action_map, now, commit=commit)

    # ══════════════ 로그 ══════════════
    def log_activity(self, job, level, message, now="", *, commit=False) -> LogRecord:
        if level not in M.LOG_LEVELS:
            raise ValueError(f"미지원 level {level}")
        seq = len(ledger.read_logs())
        lid = M.log_id(seq)
        rec = LogRecord(log_id=lid, job_id=job, level=level, message=message, created_at=now,
                        input_hash=input_digest(seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.log_exists, ledger.logs_head, ledger.append_log, lid, rec,
                         commit=commit)
        return LogRecord(**rec)

    # ══════════════ 리포트 ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> AutomationReportRecord:
        """자동화 리포트(잡·스케줄·실행 집계). **is_binding=False, 자동 거래/배포/배분 없음.**"""
        jobs = ledger.job_ids()
        states = {j: self.job_state(j) for j in jobs}
        metas = {j: self._job_meta(j) for j in jobs}
        kind_dist: dict = {}
        for j in jobs:
            kind_dist[metas[j]["kind"]] = kind_dist.get(metas[j]["kind"], 0) + 1
        runs = ledger.read_runs()
        status_dist: dict = {}
        for r in runs:
            status_dist[r.get("status")] = status_dist.get(r.get("status"), 0) + 1
        rid = M.report_id(scope, now)
        rec = AutomationReportRecord(
            report_id=rid, scope=scope, job_count=len(jobs),
            enabled_job_count=sum(1 for st in states.values() if st == M.J_ENABLED),
            run_count=len(runs),
            success_count=sum(1 for r in runs if r.get("status") == M.RUN_SUCCESS),
            failed_count=sum(1 for r in runs if r.get("status") == M.RUN_FAILED),
            schedule_count=len(ledger.read_schedules()),
            kind_distribution=dict(sorted(kind_dist.items())),
            status_distribution=dict(sorted(status_dist.items())), is_binding=False,
            disclaimer=M.DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        return AutomationReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.local_automation.verify import verify_chain
        return verify_chain()

    def list_jobs(self) -> list:
        return ledger.job_ids()

    def jobs_in_state(self, state) -> list:
        return sorted(j for j in ledger.job_ids() if self.job_state(j) == state)

    def run_history(self, job) -> list:
        return [r.get("run_id") for r in ledger.runs_for(job)]

    def summary(self, now="") -> AutomationSummary:
        return AutomationSummary(
            timestamp=now, job_event_count=len(ledger.read_job_events()),
            job_count=len(ledger.job_ids()), schedule_count=len(ledger.read_schedules()),
            run_count=len(ledger.read_runs()), log_count=len(ledger.read_logs()),
            report_count=len(ledger.read_reports()))
