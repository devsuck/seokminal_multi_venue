"""SIREN — KR buyback drift 전략 paper trading(모의 원화계좌). 실주문 없음, 순수 리포팅.

동결 config(buyback_config) + 이번 세션 확정 사이징blend(run_buyback_sizing_full_blend.py) 그대로.
초기자본 100만원 가정, notional(명목) KRW 배분 — 실제 최소단위/호가 제약 무시(백테스트 수식과
정합성 유지 목적, 실주문 전제 아님). 목표동시보유 슬롯수로 1회 배분 상한(BASE_SLOT) 산출 후
사이징weight 곱해서 배분, 가용현금 부족하면 스킵.

사이징 배분비율(pct_rank)은 FROZEN_DATE 이전 이벤트만으로 계산한 calibration pool 기준 —
미래정보 사용 안 함(PIT).

상태: siren_state.json(오픈/청산 포지션 전체), siren_ledger.jsonl(청산시마다 1줄 append),
siren_equity_curve.jsonl(실행마다 1줄 스냅샷), siren_report.md(현황 리포트).

동결: entry(next_open)/hold(20일)/cost(40bps)/사이징weight — paper 결과로 재튜닝 금지, live 금지.
실행: PYTHONPATH=. python3 -m research.paper.siren_forward
"""
from __future__ import annotations

import bisect
import datetime as _dt
import glob
import json
import os
import statistics as _st

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events, pull_buyback_details
from research.paper import buyback_config as CFG

FROZEN_DATE = "2026-09-21"        # SIREN 시작일 — 이 날짜 이후 이벤트만 진입대상
STARTING_CAPITAL = 1_000_000.0    # 유저 실제 운용예정액(100만원) 시뮬레이션
TARGET_CONCURRENT = 50            # 목표 동시보유 슬롯수(이벤트 발생빈도 기반 대략치)
BASE_SLOT = STARTING_CAPITAL / TARGET_CONCURRENT   # 1슬롯 상한 = 2만원
MIN_TICKET = 5_000.0              # 이보다 작으면 배분 스킵(의미없는 소액)
HOLD = CFG.HOLD_DAYS
COST_BPS = CFG.COST_BASE_BPS

STATE = os.path.join(os.path.dirname(__file__), "siren_state.json")
LEDGER = os.path.join(os.path.dirname(__file__), "siren_ledger.jsonl")
EQUITY = os.path.join(os.path.dirname(__file__), "siren_equity_curve.jsonl")
REPORT = os.path.join(os.path.dirname(__file__), "siren_report.md")


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


def _calib_pool(events, dmap, series):
    """FROZEN_DATE 이전(과거) 이벤트만으로 금액/ADV ratio 분포 계산 — 미래정보 미사용."""
    ratios = []
    for e in events:
        if e["date"] >= FROZEN_DATE:
            continue
        b = series.get(e["stock_code"])
        if b is None:
            continue
        j = _entry_idx(b, e["date"])
        if j is None:
            continue
        j0 = j - 1
        if j0 < 5:
            continue
        adv = _st.mean(b["tval"][max(0, j0 - 20):j0])
        d = dmap.get((e["corp_code"], e["date"].replace("-", "")))
        amt = d.get("plan_amount") if d else None
        if amt and adv > 0:
            ratios.append(amt / adv)
    return sorted(ratios)


def _weight(ratio, calib_sorted):
    if ratio is None or not calib_sorted:
        return 1.0
    rank = bisect.bisect_right(calib_sorted, ratio)
    return max(rank / len(calib_sorted), 1e-6)


def generate(write: bool = True) -> dict:
    series = _series()
    events = load_events("buyback")
    corps = sorted({e["corp_code"] for e in events if e.get("corp_code")})
    end = _dt.date.today().strftime("%Y%m%d")
    details = pull_buyback_details(corps, "20240101", end)
    dmap = {(d["corp_code"], d["rcept_dt"]): d for d in details}
    calib = _calib_pool(events, dmap, series)

    state = _load_state()
    opened_keys = {(p["stock_code"], p["event_date"]) for p in state["positions"]}

    new_events = [e for e in events if e["date"] >= FROZEN_DATE and (e["stock_code"], e["date"]) not in opened_keys]
    for e in sorted(new_events, key=lambda x: x["date"]):
        b = series.get(e["stock_code"])
        if b is None:
            continue
        j = _entry_idx(b, e["date"])
        if j is None:
            continue  # 다음날 시가 데이터 아직 미도착 — 다음 실행에서 재시도
        j0 = j - 1
        adv = _st.mean(b["tval"][max(0, j0 - 20):j0]) if j0 >= 5 else 0
        d = dmap.get((e["corp_code"], e["date"].replace("-", "")))
        amt = d.get("plan_amount") if d else None
        ratio = (amt / adv) if (amt and adv > 0) else None
        w = _weight(ratio, calib)
        notional = min(state["cash"], BASE_SLOT * w)
        if notional < MIN_TICKET:
            continue
        entry_price = b["open"][j]
        state["cash"] -= notional
        state["positions"].append({
            "stock_code": e["stock_code"], "event_date": e["date"], "entry_date": b["dates"][j],
            "entry_price": entry_price, "notional": round(notional, 2), "weight": round(w, 4),
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
            continue  # 아직 HOLD일 안 지남
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
        "# SIREN — KR Buyback Drift Paper Trading", "",
        "> ⚠️ PAPER ONLY, NO LIVE. 실주문/자동집행 없음 — 순수 리포팅. "
        "entry/hold/cost/사이징 동결(v1+blend, 이번세션 확정).",
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
                         f"배분 {p['notional']:,.0f}원(w={p['weight']}) · 평가손익 {unreal:+.2%}")
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
              "- live 금지, 실주문 API 호출 없음 — 상태파일(JSON)+리포트(md)만 갱신.",
              "- entry/hold/cost/사이징weight 동결 — paper 결과로 재튜닝 금지.",
              "- 팻테일 특성 상 초반 수개월은 손익 미미하거나 음수 정상 — 최소 3개월, 권장 12개월 관찰."]
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    open(REPORT, "w").write("\n".join(lines) + "\n")


def main():
    r = generate(write=True)
    print(f"report → {REPORT}")
    print(f"equity={r['equity']:,.0f}원 ({r['return_pct']:+.2%}) · open={r['n_open']} closed={r['n_closed']}")


if __name__ == "__main__":
    main()
