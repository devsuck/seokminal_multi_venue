"""jarvis.local_automation — Local Research Automation (P45). **워크플로 보조, 거래·배포·배분 없음.**

개인 연구자의 반복 작업(데이터 새로고침·품질검사·연구점검·리포트 생성·메모리 업데이트·헬스 체크)을 잡·스케줄·
실행 이력·자동화 로그로 관리한다. **자동화 = 워크플로 보조 — 자동 거래·자동 배포·자동 자본 배분이 아니다.**
거래/배포/배분 잡은 등록 자체가 거부된다. execution/broker/live_trading import·호출 없음. 엔진은 execute()/trade()/
deploy()/allocate()/approve() 를 노출하지 않는다. 불변·append-only·해시체인·이벤트 소싱·결정적. 원장 la_ 접두사.
기존 P1~P44 불변.
"""
from jarvis.local_automation.engine import LocalAutomationEngine  # noqa: F401
from jarvis.local_automation.models import (  # noqa: F401
    CADENCES,
    JOB_KINDS,
    JOB_STATES,
    RUN_STATUSES,
    AutomationReportRecord,
    AutomationSummary,
    ForbiddenJobKindError,
    IllegalJobTransition,
    JobEventRecord,
    JobRunRecord,
    LogRecord,
    ScheduleRecord,
    UnknownEntityError,
    can_job_transition,
    is_due,
    validate_job_kind,
)
