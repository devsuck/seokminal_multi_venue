"""봇/에이전트 상태 정합성 불변식 — '조용한 회계 버그' 런타임 감지.

실집행 레이어에서 과거에 *조용히* 틀렸던 버그류를 상태만 보고 잡아내기 위한
순수 검증 함수 모음. 매매/정산 로직엔 전혀 관여 안 함 — 관찰·알람 전용.
HUD(/lab/health)가 주기적으로 돌려 위반을 노출한다.

과거 사례(이 모듈이 있었으면 몇 주 방치 안 됐을 것):
- 다각화 봇 `spent`가 실제 오픈 포지션 합과 어긋남(정산 시 감산 로직 버그류)
- 폴리마켓 정산 큐 멈춤 — 만기 훨씬 지난 포지션이 며칠째 미정산으로 큐에 잔류
- 에이전트 read_cycles 1000 캡 초과로 오래된 체결이 창밖으로 밀려 성과 왜곡
- 마이그레이션이 필수 필드 빠진 포지션을 복원(스키마 붕괴)

각 함수는 위반 리스트를 반환한다. 위반 = {severity, entity, code, detail}.
severity: "error"(회계 불일치·데이터 붕괴) | "warn"(임계 근접·주의).
"""
from __future__ import annotations

# 부동소수 반올림(대부분 round(...,2)) 흡수용 허용오차
TOL = 0.011
# router_autopilot이 read_cycles에 쓰는 캡. 이 값에 도달하면 FIFO 잘림 재발 위험.
CYCLE_CAP = 100_000


def _v(severity: str, entity: str, code: str, detail: str) -> dict:
    return {"severity": severity, "entity": entity, "code": code, "detail": detail}


def check_agent(
    agent_id: str,
    alloc: float,
    realized_pnl: float,
    invested: float,
    n_cycles: int,
    *,
    cycle_cap: int = CYCLE_CAP,
) -> list[dict]:
    """AI 에이전트 성과 회계 정합성 검증(router_autopilot 성과 계산 입력값 기준).

    cash = alloc + realized_pnl - invested 는 호출부가 계산 — 여기선 그 컴포넌트의
    독립 정합성만 본다. 반환: 위반 리스트."""
    entity = f"agent:{agent_id}"
    out: list[dict] = []

    # 1) FIFO 잘림 재발 위험 — cycle 수가 캡에 도달하면 오래된 체결이 창밖으로 밀림
    if n_cycles >= cycle_cap:
        out.append(_v("warn", entity, "CYCLE_CAP_SATURATION",
                      f"cycle {n_cycles} >= 캡 {cycle_cap} — read_cycles 창 밖으로 "
                      f"오래된 체결 밀려 성과 왜곡 위험(캡 상향 필요)"))

    # 2) invested 음수 — 오픈 포지션 원가는 음수일 수 없음
    if invested < -TOL:
        out.append(_v("error", entity, "INVESTED_NEGATIVE",
                      f"invested={invested} < 0 — 회계 붕괴"))

    # 3) 과다 배분 — 오픈 원가가 배정자본 초과(현금이 음수로만 설명됨)
    if invested > alloc + TOL:
        out.append(_v("warn", entity, "OVER_ALLOCATED",
                      f"invested={invested} > alloc={alloc} — 배정자본 초과 배분"))

    return out
