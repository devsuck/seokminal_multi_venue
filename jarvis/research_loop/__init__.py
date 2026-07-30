"""jarvis.research_loop — Research Loop (C5). **사람 승인 필수, 자동 실행/집행/승인 없음.**

**ARCHIVED (Phase1 STEP3-B, 2026-07-31):** no active real-import caller found anywhere in the repo (no import, no declarative ledger mention, no catalog mention) — most isolated module found in the Phase1 audit. Migration: no active consumer identified; re-evaluate for full removal in a later phase.

헌장 워크플로의 읽기전용 모델: 관측→가설→제안→**사람 승인**→(연구)실행→검증→리포트→지식→메모리.
각 단계는 기록된 상태일 뿐 — 루프는 아무것도 자동 실행하지 않는다. 제안→실행 전이는 사람 APPROVED 검토 없이는
차단(게이트). 엔진은 approve()/execute()/trade()/deploy()/allocate() 를 노출하지 않는다. 불변·해시체인·이벤트 소싱.
기존 P1~P45 불변. 원장 rloop_ 접두사.
"""
from jarvis.research_loop.engine import ResearchLoopEngine  # noqa: F401
from jarvis.research_loop.models import (  # noqa: F401
    APPROVAL_GATED_STAGES,
    REVIEW_DECISIONS,
    STAGES,
    ApprovalRequiredError,
    HumanReviewRecord,
    IllegalStageTransition,
    LoopReportRecord,
    LoopStageEvent,
    LoopSummary,
    can_stage_transition,
    requires_human_approval,
)
