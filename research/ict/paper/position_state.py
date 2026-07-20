"""IN_POSITION 상태 크래시 복구용 상태파일. 프로세스 재시작 시 진행 중이던
페이퍼 포지션을 잃지 않도록 진입 시점에 기록, 청산 시 삭제한다."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass


@dataclass
class PositionState:
    side: str  # "bullish" | "bearish"
    entry_price: float
    stop: float
    target: float
    zone_source: str  # "OB" | "iFVG"
    of_trigger: str  # "absorption" | "stop_run" | "divergence"
    entered_ts: float


def save_position_state(path: str, state: PositionState) -> None:
    with open(path, "w") as f:
        json.dump(asdict(state), f)


def load_position_state(path: str) -> PositionState | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    return PositionState(**data)


def clear_position_state(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)
