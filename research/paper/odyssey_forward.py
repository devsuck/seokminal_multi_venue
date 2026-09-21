"""오디세이(Odyssey) — buyback v1 순수형(사이징blend 없음, 균등weight=1.0) paper trading.
세이렌(SIREN, v1+사이징blend)의 울음(사이징 신호)에도 규칙(균등배분)에 묶여 흔들리지 않는 대조군 —
같은 시작일/초기자본으로 병렬 실행해 사이징blend가 실제로 수익에 기여하는지 비교하기 위함.

siren_forward.py와 진입/보유/비용 규칙(next_open/HOLD/cost) 완전 동일, 유일한 차이는 사이징 —
여기는 이벤트당 weight 항상 1.0(균등배분). 실주문 없음, 순수 리포팅.

실행: PYTHONPATH=. python3 -m research.paper.odyssey_forward
"""
from __future__ import annotations

import bisect
import datetime as _dt
import glob
import json
import os
import statistics as _st

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events
from research.paper import buyback_config as CFG

FROZEN_DATE = "2026-09-21"        # SIREN과 동일 시작일 — 비교 위해 맞춤
STARTING_CAPITAL = 1_000_000.0    # SIREN과 동일 초기자본
TARGET_CONCURRENT = 50
BASE_SLOT = STARTING_CAPITAL / TARGET_CONCURRENT
MIN_TICKET = 5_000.0
HOLD = CFG.HOLD_DAYS
COST_BPS = CFG.COST_BASE_BPS

STATE = os.path.join(os.path.dirname(__file__), "odyssey_state.json")
LEDGER = os.path.join(os.path.dirname(__file__), "odyssey_ledger.jsonl")
EQUITY = os.path.join(os.path.dirname(__file__), "odyssey_equity_curve.jsonl")
REPORT = os.path.join(os.path.dirname(__file__), "odyssey_report.md")


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _entry_idx(bars, event_date):
    j = bisect.bisect_right(bars["dates"], event_date)
    if j >= len(bars["dates"]) or bars["open"][j] <= 0:
        return None
    return j


def _load_state() -> dict:
    if not os.path.exists(STATE):
        return {"cash": STARTING_CAPITAL, "positions": []}
    return json.load(open(STATE))


def _save_state(state: dict):
    json.dump(state, open(STATE, "w"), ensure_ascii=False, indent=2)


def generate(write: bool = True) -> dict:
    series = _series()
    events = load_events("buyback")

    state = _load_state()
    opened_keys = {(p["stock_code"], p["event_date"]) for p in state["positions"]}

    new_events = [e for e in events if e["date"] >= FROZEN_DATE and (e["stock_code"], e["date"]) not in opened_keys]
    for e in sorted(new_events, key=lambda x: x["date"]):
        b = series.get(e["stock_code"])
        if b is None:
            continue
        j = _entry_idx(b, e["date"])
        if j is None:
            continue
        notional = min(state["cash"], BASE_SLOT)  # weight=1.0 고정 — 사이징blend 없음
        if notional < MIN_TICKET:
            continue
        entry_price = b["open"][j]
        state["cash"] -= notional
        state["positions"].append({
            "stock_code": e["stock_code"], "event_date": e["date"], "entry_date": b["dates"][j],
            "entry_price": entry_price, "notional": round(notional, 2), "weight": 1.0,
            "status": "open",
        })

    closed_now = []
    for p in state["positions"]:
        if p["status"] != "open":
            continue
        b = series.get(p["stock_code"])
        if b is None or p["entry_date"] not in b["dates"]:
            continue
        j = b["dates"].index(p["entry_date"])
        xi = min(j + HOLD, len(b["dates"]) - 1)
        if xi < j + HOLD:
            continue
        exit_price = b["close"][xi]
        ret = (exit_price / p["entry_price"] - 1) - COST_BPS / 10_000.0
        pnl = p["notional"] * ret
        state["cash"] += p["notional"] + pnl
        p.update({"status": "closed", "exit_date": b["dates"][xi], "exit_price": exit_price,
                  "ret": round(ret, 6), "pnl": round(pnl, 2)})
        closed_now.append(p)

    open_positions = []
    open_value = 0.0
    for p in state["positions"]:
        if p["status"] != "open":
            continue
        b = series.get(p["stock_code"])
        last_close = b["close"][-1] if b and b["close"] else p["entry_price"]
        mtm = p["notional"] * (last_close / p["entry_price"])
        open_value += mtm
        open_positions.append({**p, "last_close": last_close, "mtm": round(mtm, 2)})
    equity = state["cash"] + open_value

    closed = [p for p in state["positions"] if p["status"] == "closed"]
    n_closed = len(closed)
    win_rate = round(sum(1 for p in closed if p["ret"] > 0) / n_closed, 4) if n_closed else None
    mean_ret = round(_st.mean([p["ret"] for p in closed]), 6) if n_closed else None
    today = max((b["dates"][-1] for b in series.values() if b["dates"]), default=FROZEN_DATE)

    result = {
        "as_of": today, "starting_capital": STARTING_CAPITAL, "cash": round(state["cash"], 2),
        "equity": round(equity, 2), "return_pct": round(equity / STARTING_CAPITAL - 1, 4),
        "n_open": len(open_positions), "n_closed": n_closed, "win_rate": win_rate, "mean_ret": mean_ret,
        "open_positions": open_positions, "closed_now": closed_now,
    }

    if write:
        _save_state(state)
        with open(LEDGER, "a") as f:
            for p in closed_now:
                f.write(json.dumps(p, default=str, ensure_ascii=False) + "\n")
        with open(EQUITY, "a") as f:
            f.write(json.dumps({"date": today, "cash": round(state["cash"], 2), "equity": round(equity, 2),
                                "n_open": len(open_positions)}, default=str) + "\n")
        _write_md(result)
    return result


def _write_md(r: dict):
    lines = [
        "# 오디세이(Odyssey) — buyback v1 순수형(균등weight), SIREN 대조군", "",
        "> ⚠️ PAPER ONLY, NO LIVE. entry/hold/cost 동결, weight 항상 1.0(사이징blend 없음). "
        "SIREN(사이징blend 적용)과 동일 시작일/초기자본으로 병렬 실행 — 사이징blend 기여도 비교용.",
        f"> 초기자본 {STARTING_CAPITAL:,.0f}원 · 시작일 {FROZEN_DATE}", "",
        f"## 현황 (as of {r['as_of']})",
        f"- cash {r['cash']:,.0f}원 · equity {r['equity']:,.0f}원 · 수익률 {r['return_pct']:+.2%}",
        f"- 오픈 포지션 {r['n_open']}건 · 청산완료 {r['n_closed']}건"
        + (f" · 승률 {r['win_rate']:.1%} · 평균수익 {r['mean_ret']:+.2%}" if r["n_closed"] else ""),
        "", "## 오픈 포지션",
    ]
    if r["open_positions"]:
        for p in sorted(r["open_positions"], key=lambda x: x["entry_date"]):
            unreal = p["mtm"] / p["notional"] - 1
            lines.append(f"- {p['stock_code']} 진입 {p['entry_date']} @{p['entry_price']:,.0f} · "
                         f"배분 {p['notional']:,.0f}원 · 평가손익 {unreal:+.2%}")
    else:
        lines.append("- (없음)")
    lines += ["", "## 최근 청산"]
    if r["closed_now"]:
        for p in r["closed_now"]:
            lines.append(f"- {p['stock_code']} {p['entry_date']}→{p['exit_date']} "
                         f"ret={p['ret']:+.2%} pnl={p['pnl']:+,.0f}원")
    else:
        lines.append("- (이번 실행 신규청산 없음)")
    lines += ["", "## 운영 원칙",
              "- live 금지, 실주문 API 호출 없음.",
              "- entry/hold/cost 동결 — paper 결과로 재튜닝 금지.",
              "- 권장 관찰기간 1개월(짧은 샘플 — 참고용). SIREN과 equity 비교로 사이징blend 효과 판단."]
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    open(REPORT, "w").write("\n".join(lines) + "\n")


def main():
    r = generate(write=True)
    print(f"report → {REPORT}")
    print(f"equity={r['equity']:,.0f}원 ({r['return_pct']:+.2%}) · open={r['n_open']} closed={r['n_closed']}")


if __name__ == "__main__":
    main()
