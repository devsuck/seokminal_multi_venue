"""jarvis.profiling — 프로파일링 헬퍼 (P14 Production Hardening). **관찰 전용, 완전 additive.**

CPU·메모리·replay·graph·simulation 프로파일링을 주입 clock/mem 로 결정적으로 수행하고, 섹션별 통계·핫스팟 리포트를
생성한다. 기존 P9~P13 모듈/원장을 변경하지 않으며, 순수 관찰이라 대상 동작을 바꾸지 않는다. 실행 능력 없음.
"""
from jarvis.profiling.profiler import (  # noqa: F401
    Profiler,
    SectionStat,
    StepClock,
    StepMemSampler,
    profile_callable,
    profile_cpu,
    profile_graph,
    profile_memory,
    profile_replay,
    profile_simulation,
)
