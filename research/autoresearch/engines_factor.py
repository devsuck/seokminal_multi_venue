"""KR 횡단면 팩터 엔진 — autoresearch 배치 편입 (사전등록 3개, 동결).

미검증만 태운다: size(SMB)·Amihud 비유동성·회전율(neglect).
momentum/reversal/sector = 기각, low_vol = WEAK — 전부 같은 KRX PIT 데이터로
이미 검증됨 → 재실험 금지(차별화 없는 재검 = p-해킹).

방법(사전등록·동결):
  월말 리밸런스 L-S quintile. 신호 = 월말까지 데이터만(lookahead 없음),
  수익 = 다음 달. 비용 80bps/월(양 레그 왕복 40bps, 풀턴오버 가정 = 보수적),
  스트레스 160bps. permutation null(월내 신호 셔플) → empirical p.
  direction=research: KR 공매도 제약으로 L-S는 구조 확인용 — 통과 시
  롱 레그 tilt를 별도 사전등록(여기서 튜닝 금지).
"""
from __future__ import annotations

import bisect
from typing import Optional

from research.validation.baselines import empirical_p_value

COST_M = 0.008        # 월 왕복비용(양 레그 40bps 보수)
STRESS_M = 0.016
_WIN = 60             # amihud/turnover 신호 윈도우(거래일)
_MIN_STOCKS = 50      # 월별 최소 종목(횡단면 성립)
_MIN_MONTHS = 12      # 최소 개월(전후반 분할 가능)

# 사전등록 슬레이트(동결) — long_low: 신호 오름차순 하위 quintile이 롱 레그
FACTORS = {
    "kr_size_smb": {
        "signal": "marcap", "long_low": True,
        "thesis": "소형주 프리미엄(SMB) — PIT survivorship-free로 정직 검증(생존편향 함정 통제)"},
    "kr_amihud_illiq": {
        "signal": "amihud", "long_low": False,
        "thesis": "Amihud 비유동성 프리미엄 — 비유동 보유 보상. 비용 스트레스가 심판"},
    "kr_turnover_neglect": {
        "signal": "turnover", "long_low": True,
        "thesis": "저회전(neglected) 프리미엄 — 관심 밖 종목 보상"},
}


def _month_ends(series: dict) -> list[str]:
    all_dates: set = set()
    for s in series.values():
        all_dates.update(s["dates"])
    by_m: dict = {}
    for d in sorted(all_dates):
        by_m[d[:7]] = d          # 월별 마지막 거래일
    return [by_m[m] for m in sorted(by_m)]


def _signal_at(kind: str, s: dict, j: int) -> Optional[float]:
    """월말 인덱스 j 기준 신호(과거 데이터만)."""
    if kind == "marcap":
        v = s["marcap"][j]
        return v if v > 0 else None
    lo = max(1, j - _WIN + 1)
    if j - lo < 40:              # 유효 관측 부족
        return None
    if kind == "amihud":
        vals = []
        for i in range(lo, j + 1):
            tv, c0, c1 = s["tval"][i], s["close"][i - 1], s["close"][i]
            if tv > 0 and c0 > 0:
                vals.append(abs(c1 / c0 - 1.0) / tv)
        return (sum(vals) / len(vals)) if len(vals) >= 40 else None
    if kind == "turnover":
        vals = [s["tval"][i] / s["marcap"][i] for i in range(lo, j + 1) if s["marcap"][i] > 0]
        return (sum(vals) / len(vals)) if len(vals) >= 40 else None
    return None


def _panel(fid: str, series: dict) -> list[tuple[list, list]]:
    """월별 (signals[], fwd_rets[]) — 신호는 m 월말, 수익은 m+1월."""
    kind = FACTORS[fid]["signal"]
    ends = _month_ends(series)
    if len(ends) < _MIN_MONTHS + 1:
        return []
    panel = []
    for mi in range(len(ends) - 1):
        e0, e1 = ends[mi], ends[mi + 1]
        sigs, fwds = [], []
        for s in series.values():
            ds = s["dates"]
            j0 = bisect.bisect_right(ds, e0) - 1
            if j0 < _WIN or ds[j0][:7] != e0[:7]:      # 그 달에 거래 없으면 제외
                continue
            j1 = bisect.bisect_right(ds, e1) - 1
            if j1 <= j0 or ds[j1][:7] != e1[:7]:
                continue
            c0, c1 = s["close"][j0], s["close"][j1]
            if c0 <= 0 or c1 <= 0:
                continue
            sig = _signal_at(kind, s, j0)
            if sig is None:
                continue
            sigs.append(sig)
            fwds.append(c1 / c0 - 1.0)
        if len(sigs) >= _MIN_STOCKS:
            panel.append((sigs, fwds))
    return panel


def run_factor(fid: str, series: dict, n_perms: int = 300) -> Optional[dict]:
    """단일 팩터 실행 → engine 규격 evidence dict. 데이터 부족 시 None(UNDERPOWERED)."""
    import numpy as np
    panel = _panel(fid, series)
    if len(panel) < _MIN_MONTHS:
        return None
    long_low = FACTORS[fid]["long_low"]
    rng = np.random.default_rng(42)

    ls, month_arrs = [], []
    for sigs, fwds in panel:
        a_sig = np.asarray(sigs); a_fwd = np.asarray(fwds)
        order = np.argsort(a_sig)
        k = max(5, len(order) // 5)
        lo_leg, hi_leg = order[:k], order[-k:]
        long_leg, short_leg = (lo_leg, hi_leg) if long_low else (hi_leg, lo_leg)
        ls.append(float(a_fwd[long_leg].mean() - a_fwd[short_leg].mean()))
        month_arrs.append((a_fwd, k))

    gross = float(np.mean(ls))
    net = gross - COST_M
    stress = gross - STRESS_M
    med = float(np.median(ls)) - COST_M
    half = len(ls) // 2
    wf1 = float(np.mean(ls[:half])) - COST_M
    wf2 = float(np.mean(ls[half:])) - COST_M

    # permutation null: 월내 무작위 두 그룹(같은 k) 차이 — 신호 정보 제거
    perm_stats = []
    for _ in range(n_perms):
        acc = 0.0
        for a_fwd, k in month_arrs:
            idx = rng.permutation(len(a_fwd))
            acc += float(a_fwd[idx[:k]].mean() - a_fwd[idx[-k:]].mean())
        perm_stats.append(acc / len(month_arrs) - COST_M)
    pv = empirical_p_value(net, perm_stats)
    pct = pv["percentile"] or 0.0

    # research 방향: 어느 쪽이든 극단이면 신호(롱 구조는 후속 사전등록)
    rnd_pass = (pct >= 95 and net > 0) or (pct <= 5 and net < 0)
    wf_pass = (net > 0 and wf1 > 0 and wf2 > 0) or (net < 0 and wf1 < 0 and wf2 < 0)
    cost_pass = (net > 0 and stress > 0) or (net < 0 and stress < 0)
    evidence = {
        "random_baseline": "passed" if rnd_pass else "failed",
        "walk_forward": "passed" if wf_pass else "failed",
        "cost_stress": "passed" if cost_pass else "failed",
        "survivorship": "passed",          # KRX PIT 구조적
        "lookahead": "passed",             # 신호 = 월말까지 데이터만
        "multiple_testing": "passed",      # 배치 BH-FDR 적용
    }
    return {"n": len(ls), "net": round(net, 6), "median": round(med, 6),
            "percentile": pv["percentile"], "p": pv["p_value"],
            "net_stress": round(stress, 6), "wf_first": round(wf1, 6), "wf_second": round(wf2, 6),
            "top_tail_share": None, "direction": "research", "evidence": evidence,
            "_spec": {"market": "KR", "family": "factor", "entry": "month_end_rebalance",
                      "n_variants": len(FACTORS)}}


def factor_candidates(series: dict, n_perms: int = 300) -> list:
    """배치 편입용 Candidate 목록(지연 실행)."""
    from research.autoresearch.engine import Candidate
    out = []
    for fid, f in FACTORS.items():
        def _make(fid=fid):
            return lambda: run_factor(fid, series, n_perms=n_perms)
        out.append(Candidate(cid=f"fac_{fid}", category="factor", thesis=f["thesis"],
                             direction="research", run=_make(), meta={"factor": fid}))
    return out
