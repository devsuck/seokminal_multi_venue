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

import datetime as _dt
import time as _time

# 부동소수 반올림(대부분 round(...,2)) 흡수용 허용오차
TOL = 0.011
# 만기 이 일수 넘게 지났는데 아직 미정산이면 '정산 멈춤' 의심
STUCK_RESOLUTION_DAYS = 7
# horizon 30~300s 집행봇이 이만큼 늦게까지 안 청산되면 청산루프 멈춤 의심
STUCK_EXIT_SECONDS = 3600
# router_autopilot이 read_cycles에 쓰는 캡. 이 값에 도달하면 FIFO 잘림 재발 위험.
CYCLE_CAP = 100_000

_POSITION_REQUIRED_KEYS = (
    "condition_id", "event_id", "side", "entry_price", "usd", "shares", "end_date",
)


def _v(severity: str, entity: str, code: str, detail: str) -> dict:
    return {"severity": severity, "entity": entity, "code": code, "detail": detail}


def check_polymarket_bot(cfg: dict, *, today: _dt.date | None = None) -> list[dict]:
    """폴리마켓 다각화 봇 상태(cfg: data/polymarket_bot.json) 정합성 검증.

    today는 테스트 주입용(기본 오늘). 반환: 위반 리스트(빈 리스트면 정상)."""
    today = today or _dt.date.today()
    entity = "polymarket_bot"
    out: list[dict] = []

    positions = cfg.get("positions") or []
    budget = float(cfg.get("budget", 0.0))
    spent = float(cfg.get("spent", 0.0))
    max_positions = int(cfg.get("max_positions", 0))

    # 1) 포지션 스키마 붕괴(마이그레이션 버그류) — 필수 필드 결손
    for i, pos in enumerate(positions):
        missing = [k for k in _POSITION_REQUIRED_KEYS if k not in pos]
        if missing:
            q = pos.get("question", pos.get("condition_id", f"#{i}"))
            out.append(_v("error", entity, "POSITION_SCHEMA",
                          f"포지션 '{q}' 필수 필드 결손: {missing}"))

    # 2) spent 회계 불일치 — spent는 오픈 포지션 usd 합과 같아야 함
    #    (정산 시 감산하는 설계라 누적이 아니라 '현재 배포액'을 표현)
    pos_usd_sum = round(sum(float(p.get("usd", 0.0)) for p in positions), 2)
    if abs(spent - pos_usd_sum) > TOL:
        out.append(_v("error", entity, "SPENT_MISMATCH",
                      f"spent={spent} != 오픈 포지션 usd 합={pos_usd_sum} "
                      f"(차이 {round(spent - pos_usd_sum, 2)})"))

    # 3) spent가 예산 초과 — 배포액이 예산을 넘을 수 없음
    if spent > budget + TOL:
        out.append(_v("error", entity, "SPENT_OVER_BUDGET",
                      f"spent={spent} > budget={budget}"))

    # 4) 슬롯 초과 — 오픈 포지션 수가 상한 초과
    if max_positions and len(positions) > max_positions:
        out.append(_v("error", entity, "SLOTS_EXCEEDED",
                      f"오픈 포지션 {len(positions)} > max_positions {max_positions}"))

    # 5) 정산 멈춤 — 만기 STUCK일 넘게 지났는데 아직 큐에 잔류
    for pos in positions:
        end_raw = pos.get("end_date")
        if not end_raw:
            continue
        try:
            end = _dt.date.fromisoformat(str(end_raw)[:10])
        except ValueError:
            continue
        overdue = (today - end).days
        if overdue > STUCK_RESOLUTION_DAYS:
            q = pos.get("question", pos.get("condition_id", "?"))
            out.append(_v("error", entity, "STUCK_RESOLUTION",
                          f"포지션 '{q}' 만기 {end} 후 {overdue}일째 미정산 "
                          f"(>{STUCK_RESOLUTION_DAYS}일) — 정산 큐 멈춤 의심"))

    return out


_SHARP_WALLET_POSITION_REQUIRED_KEYS = (
    "condition_id", "convergence_bucket", "horizon_s", "direction",
    "entry_price", "entry_ts", "exit_at", "usd", "shares", "outcome_index",
)


def check_polymarket_sharp_wallet_bot(cfg: dict, *, now: float | None = None) -> list[dict]:
    """sharp_wallet 집행봇 상태(data/polymarket_sharp_wallet_bot.json) 정합성 검증.

    now는 테스트 주입용(기본 현재 unix ts). 반환: 위반 리스트(빈 리스트면 정상)."""
    now = now if now is not None else _time.time()
    entity = "polymarket_sharp_wallet_bot"
    out: list[dict] = []

    positions = cfg.get("positions") or []
    budget = float(cfg.get("budget", 0.0))
    spent = float(cfg.get("spent", 0.0))
    max_positions = int(cfg.get("max_concurrent_positions", 0))

    # 1) 포지션 스키마 붕괴
    for i, pos in enumerate(positions):
        missing = [k for k in _SHARP_WALLET_POSITION_REQUIRED_KEYS if k not in pos]
        if missing:
            cid = pos.get("condition_id", f"#{i}")
            out.append(_v("error", entity, "POSITION_SCHEMA",
                          f"포지션 '{cid}' 필수 필드 결손: {missing}"))

    # 2) spent 회계 불일치
    pos_usd_sum = round(sum(float(p.get("usd", 0.0)) for p in positions), 2)
    if abs(spent - pos_usd_sum) > TOL:
        out.append(_v("error", entity, "SPENT_MISMATCH",
                      f"spent={spent} != 오픈 포지션 usd 합={pos_usd_sum} "
                      f"(차이 {round(spent - pos_usd_sum, 2)})"))

    # 3) spent가 예산 초과
    if spent > budget + TOL:
        out.append(_v("error", entity, "SPENT_OVER_BUDGET",
                      f"spent={spent} > budget={budget}"))

    # 4) 슬롯 초과
    if max_positions and len(positions) > max_positions:
        out.append(_v("error", entity, "SLOTS_EXCEEDED",
                      f"오픈 포지션 {len(positions)} > max_concurrent_positions {max_positions}"))

    # 5) 청산 멈춤 — horizon 지나고도 오래 미청산
    for pos in positions:
        exit_at = pos.get("exit_at")
        if exit_at is None:
            continue
        overdue = now - float(exit_at)
        if overdue > STUCK_EXIT_SECONDS:
            cid = pos.get("condition_id", "?")
            out.append(_v("error", entity, "STUCK_EXIT",
                          f"포지션 '{cid}' exit_at({exit_at}) 후 {round(overdue)}초째 미청산 "
                          f"(>{STUCK_EXIT_SECONDS}s) — 청산루프 멈춤 의심"))

    return out


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
