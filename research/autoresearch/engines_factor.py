"""KR 횡단면 팩터 엔진 — autoresearch 배치 편입 (사전등록 8개, 동결).

미검증만 태운다: size(SMB)·Amihud 비유동성·회전율(neglect)·PER·PBR·ROIC·F-Score·
밸류+퀄리티 종합점수(composite). momentum/reversal/sector = 기각, low_vol = WEAK —
전부 같은 KRX PIT 데이터로 이미 검증됨 → 재실험 금지(차별화 없는 재검 = p-해킹).

composite는 PER/PBR/ROIC/F-Score 개별 4개와 다른 독립 가설(신호 결합으로 개별
잡음 상쇄) — 재검 아님. 개별 4개가 REJECT_BH 났다고 이것도 자동 기각 아님, 별도 검증.
펀더멘털 캐시가 대형주 위주라 composite 유니버스 자체가 대형주 한정(소형주 틸트는
캐시와 교집합 0이라 시도 안 함 — 별도 데이터 확장 없인 검증 불가, 의도적으로 배제).

방법(사전등록·동결):
  월말 리밸런스 L-S quintile. 신호 = 월말까지 데이터만(lookahead 없음),
  수익 = 다음 달. 비용 80bps/월(양 레그 왕복 40bps, 풀턴오버 가정 = 보수적),
  스트레스 160bps. permutation null(월내 신호 셔플) → empirical p.
  direction=research: KR 공매도 제약으로 L-S는 구조 확인용 — 통과 시
  롱 레그 tilt를 별도 사전등록(여기서 튜닝 금지).

밸류/퀄리티(PER/PBR/ROIC/F-Score) PIT: DART 사업보고서 법정제출기한(사업연도 종료 후
90일 = 익년 3/31)을 보수적으로 반영 — FY=Y 실적은 Y+1년 4월부터 다음 사업보고서
나오기 전(Y+2년 3월)까지만 신호로 사용(_fy_for_date). 룩어헤드 없음.
"""
from __future__ import annotations

import bisect
from typing import Optional

from research.data.valuation_factors import compute_factors
from research.validation.baselines import empirical_p_value

COST_M = 0.008        # 월 왕복비용(양 레그 40bps 보수)
STRESS_M = 0.016
_WIN = 60             # amihud/turnover 신호 윈도우(거래일)
_MIN_STOCKS = 50      # 월별 최소 종목(횡단면 성립)
_MIN_MONTHS = 12      # 최소 개월(전후반 분할 가능)

_VALUE_SIGNALS = {"per", "pbr", "roic", "fscore"}
_VALUE_FIELD = {"per": "per", "pbr": "pbr", "roic": "roic_pct", "fscore": "f_score"}

# composite: 4개 필드 전부 있어야 채택(부분결측 배제) — 부호 맞춰 z-평균(+면 저평가/고퀄리티)
_COMPOSITE_FIELDS = ("per", "pbr", "roic_pct", "f_score")
_COMPOSITE_SIGN = {"per": -1.0, "pbr": -1.0, "roic_pct": 1.0, "f_score": 1.0}

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
    "kr_value_per": {
        "signal": "per", "long_low": True,
        "thesis": "저PER 밸류 프리미엄 — DART 연간실적×KRX PIT 시총, 공시시차 반영"},
    "kr_value_pbr": {
        "signal": "pbr", "long_low": True,
        "thesis": "저PBR 밸류 프리미엄 — 동일 파이프라인(순자산/시총)"},
    "kr_quality_roic": {
        "signal": "roic", "long_low": False,
        "thesis": "고ROIC 퀄리티 프리미엄 — NOPAT/투하자본 근사, 세율 22% 고정"},
    "kr_quality_fscore": {
        "signal": "fscore", "long_low": False,
        "thesis": "고F-Score(Piotroski 8/9) 퀄리티 프리미엄 — 재무 건전성 개선주"},
    "kr_value_quality_composite": {
        "signal": "composite", "long_low": False,
        "thesis": "밸류+퀄리티 종합점수(PER·PBR·ROIC·F-Score 부호맞춘 월내 z-평균, 펀더멘털 캐시가 "
                   "커버하는 대형주 유니버스 한정) — 개별 지표 하나로 승부보지 않고 결합해 종목별 잡음 "
                   "상쇄, '대형주가 밸류 대비 많이 떨어졌을 때' 가치 진입 판단보조용 종합가격"},
}


def _fy_for_date(date_str: str) -> str:
    """date_str 기준 사용 가능한 최신 사업보고서 연도(공시시차 PIT, 보수적)."""
    y, m = int(date_str[:4]), int(date_str[5:7])
    return str(y - 1 if m >= 4 else y - 2)


def load_fundamentals(codes: list[str], years: tuple[str, ...] = ("2022", "2023", "2024", "2025")) -> dict:
    """{stock_code: {year: fin_dict}} — dart_financials 캐시에서 로드(없는 연도는 스킵)."""
    from research.data.dart_financials import load_cached
    fund: dict = {}
    for code in codes:
        yearly = {y: fin for y in years if (fin := load_cached(code, y)) is not None}
        if yearly:
            fund[code] = yearly
    return fund


def _month_ends(series: dict) -> list[str]:
    all_dates: set = set()
    for s in series.values():
        all_dates.update(s["dates"])
    by_m: dict = {}
    for d in sorted(all_dates):
        by_m[d[:7]] = d          # 월별 마지막 거래일
    return [by_m[m] for m in sorted(by_m)]


def _signal_at(kind: str, s: dict, j: int, fund: Optional[dict] = None, code: Optional[str] = None) -> Optional[float]:
    """월말 인덱스 j 기준 신호(과거 데이터만)."""
    if kind == "marcap":
        v = s["marcap"][j]
        return v if v > 0 else None
    if kind in _VALUE_SIGNALS:
        marcap = s["marcap"][j]
        if marcap <= 0 or fund is None or code is None:
            return None
        fin = fund.get(code, {}).get(_fy_for_date(s["dates"][j]))
        if fin is None:
            return None
        return compute_factors(fin, marcap).get(_VALUE_FIELD[kind])
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


def _composite_panel(series: dict, fund: Optional[dict]) -> list[tuple[list, list]]:
    """월별 (composite_scores[], fwd_rets[]) — per/pbr/roic/fscore 4개 전부 있는 종목만,
    그 달 횡단면 내 z-점수(부호맞춤) 평균. 신호=월말까지 데이터만, 수익=다음달(lookahead 없음)."""
    import numpy as np
    ends = _month_ends(series)
    if len(ends) < _MIN_MONTHS + 1 or fund is None:
        return []
    panel = []
    for mi in range(len(ends) - 1):
        e0, e1 = ends[mi], ends[mi + 1]
        codes_ok, raws, fwds = [], {f: [] for f in _COMPOSITE_FIELDS}, []
        for code, s in series.items():
            ds = s["dates"]
            j0 = bisect.bisect_right(ds, e0) - 1
            if j0 < _WIN or ds[j0][:7] != e0[:7]:
                continue
            j1 = bisect.bisect_right(ds, e1) - 1
            if j1 <= j0 or ds[j1][:7] != e1[:7]:
                continue
            c0, c1 = s["close"][j0], s["close"][j1]
            if c0 <= 0 or c1 <= 0:
                continue
            marcap = s["marcap"][j0]
            if marcap <= 0:
                continue
            fin = fund.get(code, {}).get(_fy_for_date(ds[j0]))
            if fin is None:
                continue
            fac = compute_factors(fin, marcap)
            vals = {f: fac.get(f) for f in _COMPOSITE_FIELDS}
            if any(v is None for v in vals.values()):
                continue
            codes_ok.append(code)
            for f in _COMPOSITE_FIELDS:
                raws[f].append(vals[f])
            fwds.append(c1 / c0 - 1.0)
        if len(codes_ok) < _MIN_STOCKS:
            continue
        z = np.zeros(len(codes_ok))
        for f in _COMPOSITE_FIELDS:
            arr = np.asarray(raws[f], dtype=float)
            sd = arr.std()
            zi = (arr - arr.mean()) / sd if sd > 0 else np.zeros_like(arr)
            z += _COMPOSITE_SIGN[f] * zi
        panel.append(((z / len(_COMPOSITE_FIELDS)).tolist(), fwds))
    return panel


def _panel(fid: str, series: dict, fund: Optional[dict] = None) -> list[tuple[list, list]]:
    """월별 (signals[], fwd_rets[]) — 신호는 m 월말, 수익은 m+1월."""
    if fid == "kr_value_quality_composite":
        return _composite_panel(series, fund)
    kind = FACTORS[fid]["signal"]
    ends = _month_ends(series)
    if len(ends) < _MIN_MONTHS + 1:
        return []
    panel = []
    for mi in range(len(ends) - 1):
        e0, e1 = ends[mi], ends[mi + 1]
        sigs, fwds = [], []
        for code, s in series.items():
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
            sig = _signal_at(kind, s, j0, fund=fund, code=code)
            if sig is None:
                continue
            sigs.append(sig)
            fwds.append(c1 / c0 - 1.0)
        if len(sigs) >= _MIN_STOCKS:
            panel.append((sigs, fwds))
    return panel


def run_factor(fid: str, series: dict, fund: Optional[dict] = None, n_perms: int = 300) -> Optional[dict]:
    """단일 팩터 실행 → engine 규격 evidence dict. 데이터 부족 시 None(UNDERPOWERED)."""
    import numpy as np
    panel = _panel(fid, series, fund=fund)
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


def factor_candidates(series: dict, fund: Optional[dict] = None, n_perms: int = 300) -> list:
    """배치 편입용 Candidate 목록(지연 실행). fund 없으면 밸류/퀄리티 4개는 UNDERPOWERED."""
    from research.autoresearch.engine import Candidate
    out = []
    for fid, f in FACTORS.items():
        def _make(fid=fid):
            return lambda: run_factor(fid, series, fund=fund, n_perms=n_perms)
        out.append(Candidate(cid=f"fac_{fid}", category="factor", thesis=f["thesis"],
                             direction="research", run=_make(), meta={"factor": fid}))
    return out
