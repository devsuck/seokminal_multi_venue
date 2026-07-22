"""XAU Session Confluence — 순수 신호+리스크 상태머신 (Pine v6 포팅).

바 시퀀스(베이스 15m) → 트레이드 리스트. 사이클(Asian 시작 19:00 리셋 →
Asian 종료 03:00 레인지 고정 → London 돌파 1회 → NY 연속 1회) 상태머신.
스펙: docs/superpowers/specs/2026-07-21-xau-session-confluence-port-design.md §3–4.

충실도(§4):
- 바 종가 평가(process_orders_on_close): 돌파/진입 신호는 확정 바 close에서, 진입가=그 바 close.
- 청산은 resting SL/TP → 이후 바의 high/low로 인트라바 판정. 한 바에서 SL·TP 동시 도달 시
  보수적으로 SL 우선(TradingView 기본 가정).
- no-lookahead: 60m 아시안레인지는 확정 상위봉만(러너가 리샘플·정렬 제공). HTF 바이어스도 동일.

sizing(qty)은 equity 복리 의존이라 여기서 계산 안 함 — risk_per_unit만 싣고 러너(Task 3)가
순차 equity로 수량·비용 적용. 트레이드의 R 배수는 여기서 확정(승=+riskReward·R, 패=-1R).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from research.xau_session.sessions import (
    in_session,
    is_session_end,
    is_session_start,
)


@dataclass
class Config:
    """Pine 전략 인풋 기본값(유저 확인: 미변경). 결과 보고 안 바꿈."""
    use_london_breakout: bool = True
    use_ny_continuation: bool = True
    risk_reward: float = 0.5
    risk_percent: float = 3.0            # 러너 sizing용
    # 필터
    filter_asian_width: bool = True
    asian_width_min: float = 1.2         # (hi-lo)/lo*100 하한
    asian_width_max: float = 100.0
    filter_htf_bias: bool = False
    filter_stop_dist: bool = False
    stop_dist_min: float = 0.0           # |entry-sl|/entry*100
    stop_dist_max: float = 100.0
    filter_candle_strength: bool = False
    candle_strength_min: float = 0.6
    # 엑싯 (기본 SL+TP만)
    use_breakeven: bool = False
    be_trigger_r: float = 0.45          # Pine "Breakeven Trigger (x SL distance)" 기본값
    use_time_exit: bool = False
    max_bars_in_trade: int = 60
    use_trailing: bool = False           # 부분청산+ATR 트레일 (미구현 — 토글 시 명시 에러)


@dataclass
class Trade:
    entry_ts: int
    exit_ts: int
    direction: int          # +1 롱 / -1 숏
    entry_price: float
    sl: float
    tp: float
    exit_price: float
    exit_reason: str        # "tp" | "sl" | "time"
    risk_per_unit: float    # |entry - sl| (>0)


@dataclass
class _Cycle:
    """한 사이클(Asian 19:00 시작 ~ 다음 London/NY) 상태."""
    asian_hi: float | None = None
    asian_lo: float | None = None
    fixed_hi: float | None = None
    fixed_lo: float | None = None
    range_ready: bool = False
    london_done: bool = False
    london_dir: int = 0             # +1/-1, 0=아직
    breakout_level: float | None = None
    ny_done: bool = False


@dataclass
class _Pos:
    direction: int
    entry_ts: int
    entry_price: float
    sl: float
    tp: float
    risk_per_unit: float
    orig_risk: float
    bars_held: int = 0


def _htf_bias_at(htf: dict | None, ts: int) -> int:
    """ts 이하 마지막 확정 HTF봉의 바이어스(+1 bullish/-1 bearish/0 없음). no-lookahead."""
    if not htf:
        return 0
    hts, bias = htf["ts"], htf["bias"]
    lo, hi, ans = 0, len(hts) - 1, -1
    while lo <= hi:                       # ts_i <= ts 인 최대 인덱스
        mid = (lo + hi) // 2
        if hts[mid] <= ts:
            ans, lo = mid, mid + 1
        else:
            hi = mid - 1
    return bias[ans] if ans >= 0 else 0


def _candle_strength_ok(direction: int, o: float, h: float, l: float, c: float, min_pos: float) -> bool:
    rng = h - l
    if rng <= 0:
        return False
    pos = (c - l) / rng if direction > 0 else (h - c) / rng
    return pos >= min_pos


def _passes_entry_filters(
    cfg: Config, cyc: _Cycle, direction: int, entry: float, sl: float,
    bar: tuple[float, float, float, float], htf: dict | None, ts: int,
) -> bool:
    o, h, l, c = bar
    if cfg.filter_asian_width:
        width = (cyc.fixed_hi - cyc.fixed_lo) / cyc.fixed_lo * 100.0
        if not (cfg.asian_width_min <= width <= cfg.asian_width_max):
            return False
    if cfg.filter_htf_bias:
        b = _htf_bias_at(htf, ts)
        if b != direction:
            return False
    if cfg.filter_stop_dist:
        dist = abs(entry - sl) / entry * 100.0
        if not (cfg.stop_dist_min <= dist <= cfg.stop_dist_max):
            return False
    if cfg.filter_candle_strength and not _candle_strength_ok(direction, o, h, l, c, cfg.candle_strength_min):
        return False
    return True


def _open(direction: int, ts: int, entry: float, sl: float, cfg: Config) -> _Pos:
    risk = abs(entry - sl)
    tp = entry + cfg.risk_reward * risk if direction > 0 else entry - cfg.risk_reward * risk
    return _Pos(direction, ts, entry, sl, tp, risk, risk)


def _check_exit(pos: _Pos, ts: int, h: float, l: float, c: float, cfg: Config) -> Trade | None:
    """resting SL/TP(인트라바 high/low) + 옵션 브레이크이븐/시간청산. 청산 시 Trade, 아니면 None.
    같은 바 SL·TP 동시 → SL 우선(보수)."""
    pos.bars_held += 1
    if cfg.use_breakeven:
        trig = pos.entry_price + cfg.be_trigger_r * pos.orig_risk * pos.direction
        reached = h >= trig if pos.direction > 0 else l <= trig
        if reached:
            pos.sl = pos.entry_price
    if pos.direction > 0:
        hit_sl, hit_tp = l <= pos.sl, h >= pos.tp
    else:
        hit_sl, hit_tp = h >= pos.sl, l <= pos.tp
    if hit_sl:
        px = pos.sl
        reason = "sl"
    elif hit_tp:
        px = pos.tp
        reason = "tp"
    elif cfg.use_time_exit and pos.bars_held >= cfg.max_bars_in_trade:
        px = c
        reason = "time"
    else:
        return None
    return Trade(pos.entry_ts, ts, pos.direction, pos.entry_price, pos.sl, pos.tp,
                 px, reason, pos.risk_per_unit)


def run(bars: dict, cfg: Config | None = None, htf: dict | None = None) -> list[Trade]:
    """베이스 바(dict: ts,o,h,l,c 리스트) → 트레이드 리스트. htf: 선택 240m 바이어스
    {ts:[...], bias:[+1/-1]} (filter_htf_bias용, no-lookahead lookup)."""
    cfg = cfg or Config()
    if cfg.use_trailing:
        raise NotImplementedError("부분청산+ATR 트레일은 미구현 — 기본 OFF. 필요 시 별도 태스크.")
    ts_, o_, h_, l_, c_ = bars["ts"], bars["o"], bars["h"], bars["l"], bars["c"]
    n = len(ts_)
    trades: list[Trade] = []
    cyc = _Cycle()
    pos: _Pos | None = None
    prev_ts: int | None = None

    for i in range(n):
        ts, o, h, l, c = int(ts_[i]), o_[i], h_[i], l_[i], c_[i]

        # 1) 기존 포지션 청산(이 바 인트라바) — 진입보다 먼저
        if pos is not None:
            done = _check_exit(pos, ts, h, l, c, cfg)
            if done is not None:
                trades.append(done)
                pos = None

        # 2) 사이클 상태 전이
        if is_session_start(prev_ts, ts, "asian"):
            cyc = _Cycle(asian_hi=h, asian_lo=l)
        elif in_session(ts, "asian") and cyc.asian_hi is not None:
            cyc.asian_hi = max(cyc.asian_hi, h)
            cyc.asian_lo = min(cyc.asian_lo, l)
        if is_session_end(prev_ts, ts, "asian") and cyc.asian_hi is not None:
            cyc.fixed_hi, cyc.fixed_lo = cyc.asian_hi, cyc.asian_lo
            cyc.range_ready = True

        # 3) 런던 돌파 감지(항상 — NY연속이 level/dir 필요). 진입은 토글로 게이트.
        london_just_fired = False
        if (cyc.range_ready and not cyc.london_done and in_session(ts, "london")
                and cyc.fixed_hi is not None):
            up = c > cyc.fixed_hi
            dn = c < cyc.fixed_lo
            if up or dn:
                cyc.london_dir = 1 if up else -1     # 동봉 양방향 → 롱 우선
                cyc.breakout_level = cyc.fixed_hi if up else cyc.fixed_lo
                cyc.london_done = True
                london_just_fired = True

        # 4) 진입 신호(플랫일 때만). 런던돌파(방금 이 바) 또는 NY연속.
        if pos is None and cyc.london_dir != 0:
            direction = 0
            if cfg.use_london_breakout and london_just_fired:
                direction = cyc.london_dir
            elif (cfg.use_ny_continuation and not cyc.ny_done
                  and cyc.breakout_level is not None and in_session(ts, "ny")):
                cont = c > cyc.breakout_level if cyc.london_dir > 0 else c < cyc.breakout_level
                if cont:
                    direction = cyc.london_dir
                    cyc.ny_done = True
            if direction != 0:
                sl = cyc.fixed_lo if direction > 0 else cyc.fixed_hi
                if abs(c - sl) > 0 and _passes_entry_filters(
                        cfg, cyc, direction, c, sl, (o, h, l, c), htf, ts):
                    pos = _open(direction, ts, c, sl, cfg)

        prev_ts = ts

    return trades
