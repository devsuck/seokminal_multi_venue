"""Auto-Research 엔진 — karpathy/autoresearch 패턴을 '정직하게' 적용.

autoresearch(karpathy): 에이전트가 밤새 train.py 반복 수정 → 5분 학습 → 지표 개선되면 유지(~100회/밤).
마켓에 순진하게 이식하면? = p-해킹 기계. 노이즈 데이터에 100번 시도 = 우연히 '엣지' 나옴.
  (독립검정 30개서 최소 1개 p<0.05 확률 ≈ 78.5%)

정직한 이식 = "유지" 기준을 raw 수익이 아니라:
  (1) 배치 전체 다중검정 보정(BH-FDR) 통과  ← 몇 개를 시도했는지 반영
  (2) 레드팀 결정적 통제 전부 통과            ← confound/lookahead/생존편향 차단
둘 다 넘어야 리더보드 후보. 나머지는 정직하게 REJECT/UNDERPOWERED.

지금 실장착 엔진: event_family — 실제 KRX PIT + DART 이벤트(합성 아님).
factor / tsmom / regime = 훅만 등록(가짜 결과 금지, 'engine_pending'으로 표기).
새 엔진은 candidate.run()이 {p, net, percentile, ...} evidence만 반환하면 그대로 배치에 편입."""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

from research.scanner.event_study import event_study, load_series
from research.scanner.verdict import classify, DISPLAY
from research.scanner.families import FAMILIES, redteam_spec
from research.data.kr_dart_events import load_events
from research.validation.multiple_testing import benjamini_hochberg
from jarvis.redteam.review import review_strategy
from research.agents.experiment_registry import log_experiment

_DIR = os.path.dirname(__file__)
RESULTS = os.path.join(_DIR, "results.jsonl")
STATUS = os.path.join(_DIR, "status.json")

BATCH_ALPHA = 0.10  # BH-FDR 목표 FDR


@dataclass
class Candidate:
    cid: str
    category: str          # event_family | factor | tsmom | regime
    thesis: str
    direction: str         # bullish | research | bearish
    run: Callable[[], Optional[dict]]  # → evidence dict {p,net,percentile,...,_res,_spec} or None
    meta: dict = field(default_factory=dict)


# ── 엔진 1: event_family (실 데이터) ──────────────────────────────────
def _event_family_candidates(series: dict) -> list[Candidate]:
    out: list[Candidate] = []
    for fam_id, fam in FAMILIES.items():
        ev = load_events(fam_id)
        if len(ev) < 30:      # 데이터 없거나 부족 → 후보에서 제외(UNDERPOWERED로 별도 기록)
            out.append(Candidate(
                cid=f"ev_{fam_id}", category="event_family", thesis=fam["thesis"],
                direction=fam["direction"], run=(lambda: None),
                meta={"fam_id": fam_id, "n": len(ev), "underpowered": True}))
            continue

        def _make(fam_id=fam_id, fam=fam, ev=ev):
            def _run():
                res = event_study(ev, series, fam["direction"])
                if res.get("verdict") == "UNDERPOWERED" or res.get("p") is None:
                    return None
                res["_spec"] = redteam_spec(fam_id, fam)
                return res
            return _run
        out.append(Candidate(
            cid=f"ev_{fam_id}", category="event_family", thesis=fam["thesis"],
            direction=fam["direction"], run=_make(), meta={"fam_id": fam_id, "n": len(ev)}))
    return out


# ── 엔진 훅(대기): 가짜 결과 안 만듦, 정직하게 status만 ───────────────
# factor 배선됨(engines_factor). tsmom/regime은 '새 정보 없음'으로 정직 보류:
#   tsmom 변형(룩백·슬리브)은 Phase 103 robustness로 같은 데이터에서 이미 분석
#   — 재슬롯 = 이중계상. regime은 buyback×레짐(v2 shadow)·TSMOM×레짐(기각) 완료.
_PENDING_ENGINES = [
    ("tsmom", "변형(룩백·슬리브)은 robustness로 기분석 — 새 시장/데이터 오면 배선"),
    ("regime", "생존자×레짐 이미 검증(v2 shadow·기각) — 새 조합 생기면 배선"),
]


def collect_candidates() -> tuple[list[Candidate], dict]:
    series = load_series()
    cands = _event_family_candidates(series)
    from research.autoresearch.engines_factor import factor_candidates, load_fundamentals
    fund = load_fundamentals(list(series.keys()))
    cands += factor_candidates(series, fund=fund)  # KR 횡단면 팩터(사전등록 7: size·amihud·turnover·PER·PBR·ROIC·F-Score)
    return cands, series


def run_batch() -> dict:
    """1회 배치: 후보 전부 실행 → 배치 BH-FDR → 레드팀 → 리더보드 저장·반환."""
    started = dt.datetime.now().isoformat(timespec="seconds")
    cands, _ = collect_candidates()

    ran: list[dict] = []       # p-value 나온 후보(BH 대상)
    underpowered: list[dict] = []
    for c in cands:
        if c.meta.get("underpowered"):
            underpowered.append({"cid": c.cid, "category": c.category, "thesis": c.thesis,
                                 "n": c.meta.get("n", 0), "verdict": "UNDERPOWERED"})
            continue
        res = c.run()
        if res is None:
            underpowered.append({"cid": c.cid, "category": c.category, "thesis": c.thesis,
                                 "n": c.meta.get("n", 0), "verdict": "UNDERPOWERED"})
            continue
        ran.append({"cand": c, "res": res})

    # ── 배치 BH-FDR: '몇 개를 시도했는지' 반영(핵심 anti-p-hack) ──
    pvals = [r["res"]["p"] for r in ran]
    bh = benjamini_hochberg(pvals, alpha=BATCH_ALPHA)
    survivors = bh["survivors"]

    leaderboard: list[dict] = []
    for i, r in enumerate(ran):
        c, res = r["cand"], r["res"]
        rt = review_strategy(res["_spec"], res["evidence"]) if res.get("_spec") else {"verdict": "N/A", "failed": [], "missing": []}
        bh_survivor = bool(survivors[i]) if i < len(survivors) else False
        status, _text = classify(
            net=res.get("net"), percentile=res.get("percentile"), p=res.get("p"),
            wf_first=res.get("wf_first"), wf_second=res.get("wf_second"),
            redteam_verdict=rt["verdict"], bh_survivor=bh_survivor)
        verdict = DISPLAY.get(status, status.upper())
        entry = {
            "cid": c.cid, "category": c.category, "thesis": c.thesis, "direction": c.direction,
            "n": res.get("n"), "net": res.get("net"), "median": res.get("median"),
            "percentile": res.get("percentile"), "p": res.get("p"),
            "wf_first": res.get("wf_first"), "wf_second": res.get("wf_second"),
            "top_tail": res.get("top_tail_share"),
            "bh_survivor": bh_survivor, "bh_threshold": bh["threshold"],
            "redteam": rt["verdict"], "redteam_failed": rt.get("failed", []), "redteam_missing": rt.get("missing", []),
            "verdict": verdict,
        }
        leaderboard.append(entry)
        # 지식 축적(registry)
        log_experiment({
            "hypothesis_id": f"auto_{c.cid}",
            "status": "candidate" if status == "candidate" else ("watchlist" if status == "watchlist" else "rejected"),
            "n": res.get("n"), "net": res.get("net"), "percentile": res.get("percentile"), "p": res.get("p"),
            "wf_first": res.get("wf_first"), "wf_second": res.get("wf_second"),
            "redteam": rt["verdict"], "direction": c.direction, "data_quality": "KRX PIT survivorship-free",
            "verdict": f"auto-research {verdict}", "note": c.thesis, "batch_bh_alpha": BATCH_ALPHA,
        })

    # 정렬: CANDIDATE 우선 → percentile → net
    order = {"CANDIDATE": 0, "WATCHLIST": 1, "REJECT_REDTEAM": 2, "REJECT_BH": 3}
    leaderboard.sort(key=lambda e: (order.get(e["verdict"], 9), -(e["percentile"] or 0), -(e["net"] or 0)))

    finished = dt.datetime.now().isoformat(timespec="seconds")
    n_cand = sum(1 for e in leaderboard if e["verdict"] == "CANDIDATE")
    summary = {
        "started": started, "finished": finished,
        "n_tested": len(ran), "n_underpowered": len(underpowered),
        "n_candidates": n_cand, "bh_alpha": BATCH_ALPHA, "bh_threshold": bh["threshold"], "bh_n_survivors": bh["n_survivors"],
        "leaderboard": leaderboard, "underpowered": underpowered,
        "pending_engines": [{"category": k, "note": v, "status": "engine_pending"} for k, v in _PENDING_ENGINES],
        "honest_note": ("배치 BH-FDR(다중검정 보정)로 '몇 개 시도했는지'를 반영해 우연 후보를 걸러냄. "
                        "CANDIDATE=BH 생존+레드팀 전통제 통과. 발견은 증거 아님 → 페이퍼 OOS 재현 필요."),
    }
    _persist(summary)
    return summary


def _persist(summary: dict) -> None:
    with open(STATUS, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(RESULTS, "a") as f:
        f.write(json.dumps({"finished": summary["finished"], "n_tested": summary["n_tested"],
                            "n_candidates": summary["n_candidates"],
                            "leaderboard": summary["leaderboard"]}, ensure_ascii=False) + "\n")


def load_status() -> dict:
    if not os.path.exists(STATUS):
        return {"leaderboard": [], "underpowered": [], "n_tested": 0, "n_candidates": 0,
                "pending_engines": [{"category": k, "note": v, "status": "engine_pending"} for k, v in _PENDING_ENGINES],
                "honest_note": "아직 배치 미실행 — /auto-research에서 실행하거나 run_autoresearch.py."}
    with open(STATUS) as f:
        return json.load(f)


def latest_bh_survivor(fam_id: str) -> bool | None:
    """최신 배치 리더보드에서 이 family의 BH-FDR 생존 여부. 배치/항목 없으면 None(미확정)."""
    if not os.path.exists(STATUS):
        return None
    try:
        with open(STATUS) as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    for e in data.get("leaderboard", []):
        if e.get("cid") == f"ev_{fam_id}":
            v = e.get("bh_survivor")
            return bool(v) if v is not None else None  # 키 없음/null = 미확정(reject 아님)
    return None
