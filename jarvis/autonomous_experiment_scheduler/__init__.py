"""jarvis.autonomous_experiment_scheduler — Autonomous Experiment Scheduler Layer (P12.2). **스케줄·기록 전용.**

자율 연구 실험을 위한 스케줄링 지능 — 실험 큐·우선순위·스케줄링 규칙·자원 인식·의존 순서·실행 윈도 계획을
관리한다. Experiment Queue Registry·Experiment Schedule Records·Scheduling Policies·Priority Rules·Dependency
Graph·Schedule Snapshots·Scheduling Reports 를 소유한다.

**실험을 실행하지 않는다 — 스케줄·기록만.** execution/broker/portfolio/risk/permission/deployment/live
import·호출 없음. SCHEDULE ≠ EXECUTION · PLAN ≠ RUN · PRIORITY ≠ APPROVAL. 불변·append-only 해시체인·이벤트 소싱·
결정적·재현. 무효 의존·순환 스케줄·중복 실행 요청·무단 우선순위 변경은 차단된다. 상위 P9.8~P12.1 은 READ ONLY.
물리 원장은 aes_ 접두사.
"""
from jarvis.autonomous_experiment_scheduler.engine import AutonomousExperimentSchedulerEngine  # noqa: F401,E501
from jarvis.autonomous_experiment_scheduler.models import (  # noqa: F401
    SCHEDULE_STATES,
    CircularScheduleError,
    DanglingDependencyError,
    DependencyRecord,
    DuplicateRequestError,
    IllegalScheduleTransition,
    ImmutablePolicyError,
    ImmutableScheduleError,
    PolicyRecord,
    PriorityChangeError,
    PriorityRecord,
    ScheduleEventRecord,
    ScheduleRecord,
    ScheduleReportRecord,
    SchedulerSummary,
    SnapshotRecord,
    UnknownRequestError,
    UnknownScheduleError,
)
