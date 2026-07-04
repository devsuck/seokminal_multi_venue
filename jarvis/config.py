"""Jarvis Quant OS — 전역 설정·상태 경로·자율 레벨.

원칙: 연구=자율, 검증=결정적, 집행=제한, 전부 감사가능.
AI는 자기 권한을 확장할 수 없다(레벨은 사람만 올린다).
"""
from __future__ import annotations

import os

# 상태 저장(append-only jsonl). 프로세스 재시작에도 유지.
STATE_DIR = os.path.join(os.path.dirname(__file__), "_state")

# 코드 버전(감사용). git 아님 → 로컬 마커. 배포 시 커밋해시로 교체.
CODE_VERSION = os.environ.get("JARVIS_CODE_VERSION", "local-dev")

# 현재 자율 레벨. 0 manual … 7 constrained operator.
# 초기 목표 = 3~4(연구 자동화 + 페이퍼 모니터). live 실행 없음.
# ⚠️ 이 값은 사람만 바꾼다. AI/에이전트가 못 올린다(권한 정책이 강제).
AUTONOMY_LEVEL = int(os.environ.get("JARVIS_AUTONOMY_LEVEL", "5"))

# live 실행이 켜지는 최소 레벨. 아래면 Execution Gateway가 무조건 BLOCK.
MIN_LIVE_LEVEL = 6

LEVEL_NAMES = {
    0: "Manual research", 1: "AI report assistant", 2: "AI research/hypothesis agent",
    3: "Autonomous backtest+critique", 4: "Autonomous paper monitor",
    5: "Human-approved live proposal", 6: "Micro-live constrained execution",
    7: "Constrained portfolio operator",
}


def ensure_state_dir() -> str:
    os.makedirs(STATE_DIR, exist_ok=True)
    return STATE_DIR


def state_path(name: str) -> str:
    ensure_state_dir()
    return os.path.join(STATE_DIR, name)


def live_execution_enabled() -> bool:
    """live 실행 허용 여부. 레벨 게이트. 기본 False."""
    return AUTONOMY_LEVEL >= MIN_LIVE_LEVEL
