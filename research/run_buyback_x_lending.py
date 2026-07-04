"""KSD 대차잔고 × 이벤트 상호작용 — 사전등록 H1·H2·H3 판정.

사전등록: research/ksd_lending_prereg.md (동결 2026-07-04, 데이터 결합 전).
- H1 buyback × 高대차(D−2 잔고비율 top tercile) → 드리프트 강함 (top−bottom > 0)
- H2 buyback 공시후 Δ대차(D0..D+5) 하위 → D+6..D+20 수익 높음 (low−high > 0)
- H3 treasury_disposal × 高대차 → 더 음수 (top−bottom < 0)
BH-FDR α=0.1 (3 primary). tercile n<100 = UNDERPOWERED. v1 불변.

실행: PYTHONPATH=. python3 research/run_buyback_x_lending.py
"""
from __future__ import annotations

import bisect
import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.data.kr_dart_events import load_events
from research.data.ksd_lending import load_lending
from research.scanner.event_study import COST_BASE, COST_STRESS, HOLD, event_study, load_series
from research.validation.multiple_testing import benjamini_hochberg

MIN_TERCILE_N = 100
BOOT = 1000
SEED = 42


def _bar_idx(b, date):
    """이벤트 날짜의 다음 bar 인덱스(진입일)와 그 직전 인덱스들 접근용."""
    return bisect.bisect_right(b["dates"], date)


def _ratio_d2(b, lending, date):
    """공시일 D 기준 D−2 bar의 대차잔고비율. 결측 None."""
    j = _bar_idx(b, date)
    k = j - 2
    if k < 0 or not lending:
        return None
    d2 = b["dates"][k]
    bal = lending.get(d2)
    if bal is None:
        # 대차 데이터는 영업일 갭 있을 수 있음 — d2 이전 최근값(최대 10일)
        import datetime as dt
        dd = dt.date.fromisoformat(d2)
        for lag in range(1, 11):
            bal = lending.get((dd - dt.timedelta(days=lag)).isoformat())
            if bal is not None:
                break
    if bal is None:
        return None
    close = b["close"][k]
    marcap = b["marcap"][k]
    if close <= 0 or marcap <= 0:
        return None
    shares = marcap / close
    return bal / shares if shares > 0 else None


def _delta_lending(b, lending, date):
    """Δ대차잔고 D0..D+5 상대변화. 결측 None."""
    j = _bar_idx(b, date)
    if j + 5 >= len(b["dates"]):
        return None
    d0, d5 = b["dates"][j], b["dates"][j + 5]
    b0, b5 = lending.get(d0), lending.get(d5)
    if b0 is None or b5 is None or b0 <= 0:
        return None
    return b5 / b0 - 1


def _fwd_late(b, date, cost):
    """H2 보유창: D+6 시가 진입, D+20 종가 청산."""
    j = _bar_idx(b, date)
    ei = j + 5  # 진입 bar = D+6 (j가 D+1)
    xi = j + HOLD - 1
    if xi >= len(b["dates"]) or ei >= len(b["dates"]):
        return None
    entry = b["open"][ei]
    if entry <= 0 or xi <= ei:
        return None
    return b["close"][xi] / entry - 1 - cost / 1e4


def _boot_diff_p(a: list, c: list, direction: int) -> float:
    """단측 부트스트랩: P(관측 diff 방향이 우연). direction=+1이면 mean(a)>mean(c) 검정."""
    rng = _random.Random(SEED)
    obs = (_st.fmean(a) - _st.fmean(c)) * direction
    pool = a + c
    na = len(a)
    worse = 0
    for _ in range(BOOT):
        rng.shuffle(pool)
        d = (_st.fmean(pool[:na]) - _st.fmean(pool[na:])) * direction
        if d >= obs:
            worse += 1
    return (1 + worse) / (BOOT + 1)


def _terciles(vals: list[tuple]) -> tuple[list, list]:
    """(signal, event) 리스트 → (top tercile events, bottom tercile events). signal 오름차순."""
    vals = sorted(vals, key=lambda x: x[0])
    n = len(vals)
    t = n // 3
    return [e for _, e in vals[-t:]], [e for _, e in vals[:t]]


def _rets(events, series, cost, fwd):
    out = []
    for e in events:
        b = series.get(e.get("stock_code"))
        if b is None:
            continue
        r = fwd(b, e["date"], cost)
        if r is not None:
            out.append((e["date"], r))
    return out


def _wf_diff(top_r, bot_r, direction):
    """전/후반 각각 diff 방향 일치 여부. (date, ret) 리스트."""
    out = []
    for half in (0, 1):
        ta = sorted(top_r); ba = sorted(bot_r)
        tm = len(ta) // 2; bm = len(ba) // 2
        t = ta[:tm] if half == 0 else ta[tm:]
        c = ba[:bm] if half == 0 else ba[bm:]
        if not t or not c:
            return [False, False]
        d = (_st.fmean(r for _, r in t) - _st.fmean(r for _, r in c)) * direction
        out.append(d > 0)
    return out


def _fwd_std(b, date, cost):
    j = _bar_idx(b, date)
    if j >= len(b["dates"]):
        return None
    xi = min(j + HOLD, len(b["dates"]) - 1)
    entry = b["open"][j]
    if entry <= 0 or xi <= j:
        return None
    return b["close"][xi] / entry - 1 - cost / 1e4


def run_hypothesis(hid, events, series, lending_map, signal_fn, fwd_fn, direction):
    """공통: signal로 tercile 분할 → top vs bottom diff (사전등록 방향) + stress."""
    sig = []
    missing = 0
    for e in events:
        b = series.get(e.get("stock_code"))
        if b is None:
            continue
        lend = lending_map.get(e["stock_code"], {})
        s = signal_fn(b, lend, e["date"])
        if s is None:
            missing += 1
            continue
        sig.append((s, e))
    top, bot = _terciles(sig)
    if min(len(top), len(bot)) < MIN_TERCILE_N:
        return {"hid": hid, "verdict": "UNDERPOWERED", "n_top": len(top), "n_bot": len(bot),
                "missing": missing, "p": None}
    top_r = _rets(top, series, COST_BASE, fwd_fn)
    bot_r = _rets(bot, series, COST_BASE, fwd_fn)
    if min(len(top_r), len(bot_r)) < MIN_TERCILE_N:
        return {"hid": hid, "verdict": "UNDERPOWERED", "n_top": len(top_r), "n_bot": len(bot_r),
                "missing": missing, "p": None}
    p = _boot_diff_p([r for _, r in top_r], [r for _, r in bot_r], direction)
    top_s = _rets(top, series, COST_STRESS, fwd_fn)
    bot_s = _rets(bot, series, COST_STRESS, fwd_fn)
    diff = _st.fmean(r for _, r in top_r) - _st.fmean(r for _, r in bot_r)
    diff_stress = (_st.fmean(r for _, r in top_s) - _st.fmean(r for _, r in bot_s)) if top_s and bot_s else None
    wf = _wf_diff(top_r, bot_r, direction)
    return {"hid": hid, "n_top": len(top_r), "n_bot": len(bot_r), "missing": missing,
            "net_top": round(_st.fmean(r for _, r in top_r), 5),
            "net_bot": round(_st.fmean(r for _, r in bot_r), 5),
            "diff": round(diff, 5), "diff_stress": round(diff_stress, 5) if diff_stress is not None else None,
            "p": p, "wf_ok": all(wf), "wf": wf, "direction": direction}


def main():
    print("=" * 72)
    print("KSD 대차잔고 × 이벤트 — 사전등록 H1·H2·H3 (prereg 2026-07-04)")
    print("=" * 72)
    series = load_series()
    buyback = load_events("buyback")
    disposal = load_events("treasury_disposal")
    codes = {e["stock_code"] for e in buyback + disposal if e.get("stock_code")}
    lending_map = {c: load_lending(c) for c in codes}
    covered = sum(1 for v in lending_map.values() if v)
    print(f"buyback {len(buyback)} · disposal {len(disposal)} · lending 커버 {covered}/{len(codes)}")

    results = [
        run_hypothesis("H1_buyback_high_loan", buyback, series, lending_map,
                       _ratio_d2, _fwd_std, +1),
        run_hypothesis("H2_buyback_delta_loan", buyback, series, lending_map,
                       _delta_lending, _fwd_late, -1),  # Δ하위(top=Δ상위)가 나쁨 = top−bottom < 0 검정
        run_hypothesis("H3_disposal_high_loan", disposal, series, lending_map,
                       _ratio_d2, _fwd_std, -1),
    ]

    pvals = [r["p"] for r in results if r["p"] is not None]
    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {"survivors": []}
    si = iter(bh["survivors"])
    for r in results:
        r["bh_survivor"] = next(si) if r["p"] is not None else None

    for r in results:
        if r.get("verdict") == "UNDERPOWERED":
            print(f"\n[{r['hid']}] UNDERPOWERED n_top={r['n_top']} n_bot={r['n_bot']} missing={r['missing']}")
            status = "underpowered"
        else:
            ok = bool(r["bh_survivor"]) and r["wf_ok"] and (r["diff_stress"] is not None
                 and r["diff_stress"] * r["direction"] > 0)
            status = "candidate" if ok else "rejected"
            print(f"\n[{r['hid']}] top {r['net_top']:+.4f}(n{r['n_top']}) vs bot {r['net_bot']:+.4f}(n{r['n_bot']})")
            print(f"  diff={r['diff']:+.5f} stress={r['diff_stress']} p={r['p']} BH={r['bh_survivor']} WF={r['wf']}")
            print(f"  → {status.upper()}")
        log_experiment({"hypothesis_id": f"ksd_{r['hid']}", "status": status,
                        "n": r.get("n_top"), "net": r.get("diff"), "p": r.get("p"),
                        "data_quality": "KRX PIT + KSD lending D-2",
                        "verdict": f"prereg 2026-07-04 {status}",
                        "note": "buyback/disposal × 대차잔고 상호작용 (v1 불변, 통과시 v2 별도등록)"})

    print("\n완료 — 사전등록 기준 그대로, 결과 후 튜닝 없음.")


if __name__ == "__main__":
    main()
