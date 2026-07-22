"""Coverage Analyzers (P5) — projection + KG 읽고 ResearchGap 산출. 결정적.

빈 데이터/빈 그래프는 우아하게(빈 결과). 전략 로직·소스 무변경(읽기만).
"""
from __future__ import annotations

from jarvis.planner.models import (
    CANONICAL_FAMILIES,
    CANONICAL_REGIMES,
    ResearchGap,
    family_of,
    gap_id,
)
from jarvis.planner.scoring import saturating, score

# 실패사유 → 처방(설명가능). (remedy_text, target_area, category)
_REMEDY = {
    "SIGNAL_DEAD": ("Explore alternative signal generation family", "signal_generation", "MISSING_STRATEGY_FAMILY"),
    "COST_EXECUTION": ("Investigate lower-turnover / higher-edge strategies", "turnover_reduction", "KNOWLEDGE_GAP"),
    "FAILED_MULTIPLE_TESTING": ("Pre-register fewer, stronger hypotheses (BH-FDR discipline)", "hypothesis_discipline", "REDUCE_REDUNDANCY"),
    "INDISTINGUISHABLE_FROM_RANDOM": ("Target different market structure / higher-signal regimes", "market_structure", "KNOWLEDGE_GAP"),
    "SURVIVORSHIP": ("Use PIT survivorship-free datasets", "pit_data", "DATA_GAP"),
    "LOOKAHEAD": ("Fix lookahead; closed-bar features only", "methodology", "KNOWLEDGE_GAP"),
    "UNDERPOWERED": ("Expand universe/sample for statistical power", "sample_size", "DATA_GAP"),
    "BLOCKED_BY_DATA": ("Acquire/wire missing datasets", "data_acquisition", "DATA_GAP"),
    "CONFOUND": ("Add entry-confound baseline controls", "methodology", "KNOWLEDGE_GAP"),
    "NEGATIVE_DRIFT": ("Re-frame as short/negative-drift risk filter", "direction", "KNOWLEDGE_GAP"),
    "NO_EFFECT": ("Drop family; reallocate research to higher-signal areas", "reallocation", "REDUCE_REDUNDANCY"),
}


def _failure_patterns(kg) -> dict:
    rows = kg.query("""SELECT fr.name reason, COUNT(*) n FROM edges e
        JOIN nodes fr ON fr.id=e.target_id
        WHERE e.relation='failed_because' GROUP BY fr.name""")
    return {r["reason"]: r["n"] for r in rows}


def analyze_failure_patterns(p3, kg, ts: str = "") -> list[ResearchGap]:
    """지배적 실패사유 → 처방 제안. 예: SIGNAL_DEAD 다수 → 대체 신호군 탐색."""
    patterns = _failure_patterns(kg)
    total = sum(patterns.values()) or 1
    gaps = []
    for reason, n in sorted(patterns.items(), key=lambda kv: (-kv[1], kv[0])):
        if reason == "OTHER":
            continue
        remedy = _REMEDY.get(reason)
        if not remedy:
            continue
        text, area, category = remedy
        impact = saturating(n, 12)                 # 12건이면 최대 임팩트
        evidence = saturating(n, 20)
        confidence = 0.85
        sc = score(impact, confidence, evidence)
        gaps.append(ResearchGap(
            id=gap_id(category, area), type=category,
            description=f"{n} '{reason}' failures ({round(100*n/total)}% of classified) → {text}",
            evidence={"failure_reason": reason, "count": n, "share": round(n / total, 3),
                      "remedy": text, **sc},
            priority_score=sc["priority"], related_entities=[area, reason], created_at=ts))
    return gaps


def _strategy_families(p3) -> dict:
    """패밀리 → {n, rejected, ids}. id-prefix 분류."""
    fam: dict = {}
    for r in p3.query("SELECT id,status FROM strategies"):
        f = family_of(r["id"])
        d = fam.setdefault(f, {"n": 0, "rejected": 0, "ids": []})
        d["n"] += 1
        d["ids"].append(r["id"])
        if r["status"] in ("rejected", "blocked_by_data"):
            d["rejected"] += 1
    return fam


def analyze_strategy_family_coverage(p3, kg, ts: str = "") -> list[ResearchGap]:
    """누락 패밀리(MISSING_STRATEGY_FAMILY) + 과집중/전멸(REPLACE/REDUNDANCY)."""
    fam = _strategy_families(p3)
    gaps = []
    total = sum(d["n"] for d in fam.values()) or 1
    present = {f for f in fam if f != "unclassified"}

    # 누락 정규 패밀리
    for f in CANONICAL_FAMILIES:
        if f not in present or fam.get(f, {}).get("n", 0) == 0:
            sc = score(0.6, 0.55, 0.6)             # 기회이나 heuristic 분류라 confidence 중간
            gaps.append(ResearchGap(
                id=gap_id("MISSING_STRATEGY_FAMILY", f), type="MISSING_STRATEGY_FAMILY",
                description=f"No tested strategies in canonical family '{f}'",
                evidence={"family": f, "present_families": sorted(present), **sc},
                priority_score=sc["priority"], related_entities=[f], created_at=ts))

    # 과집중 + 전멸(REPLACE_FAILED_STRATEGY)
    for f, d in sorted(fam.items()):
        if f == "unclassified" or d["n"] < 2:
            continue
        reject_rate = d["rejected"] / d["n"]
        if reject_rate >= 0.8:                     # 사실상 전멸한 패밀리 → 대체
            impact = saturating(d["rejected"], 10)
            sc = score(impact, 0.8, saturating(d["n"], 8))
            gaps.append(ResearchGap(
                id=gap_id("REPLACE_FAILED_STRATEGY", f), type="REPLACE_FAILED_STRATEGY",
                description=f"Family '{f}': {d['rejected']}/{d['n']} rejected — replace with alternative approach",
                evidence={"family": f, "n": d["n"], "rejected": d["rejected"],
                          "reject_rate": round(reject_rate, 3), **sc},
                priority_score=sc["priority"], related_entities=sorted(d["ids"])[:8], created_at=ts))
        elif d["n"] / total >= 0.35:               # 한 패밀리에 과집중
            sc = score(0.5, 0.7, saturating(d["n"], 12))
            gaps.append(ResearchGap(
                id=gap_id("REDUCE_REDUNDANCY", f"concentration_{f}"), type="REDUCE_REDUNDANCY",
                description=f"Research over-concentrated in '{f}' ({d['n']}/{total}) — diversify directions",
                evidence={"family": f, "n": d["n"], "share": round(d["n"] / total, 3), **sc},
                priority_score=sc["priority"], related_entities=[f], created_at=ts))
    return gaps


def analyze_regime_coverage(p3, kg, ts: str = "") -> list[ResearchGap]:
    """정규 레짐 대비 커버리지. 레짐 태깅 자체가 없으면 KNOWLEDGE_GAP + 누락 레짐."""
    present = {r["name"] for r in kg.query("SELECT name FROM nodes WHERE type='Regime'")}
    gaps = []
    if not present:
        sc = score(0.5, 0.6, 0.5)
        gaps.append(ResearchGap(
            id=gap_id("KNOWLEDGE_GAP", "regime_tagging"), type="KNOWLEDGE_GAP",
            description="No regime-tagged strategies/decisions — regime coverage cannot be assessed",
            evidence={"present_regimes": [], "canonical": CANONICAL_REGIMES, **sc},
            priority_score=sc["priority"], related_entities=["regime"], created_at=ts))
    for reg in CANONICAL_REGIMES:
        if reg not in present:
            sc = score(0.4, 0.5, 0.4)
            gaps.append(ResearchGap(
                id=gap_id("MISSING_REGIME", reg), type="MISSING_REGIME",
                description=f"No strategy coverage for regime '{reg}'",
                evidence={"regime": reg, "present": sorted(present), **sc},
                priority_score=sc["priority"], related_entities=[reg], created_at=ts))
    return gaps


def analyze_research_redundancy(p3, kg, ts: str = "") -> list[ResearchGap]:
    """반복 실패 방향(많이 재검했는데 계속 실패)."""
    rows = p3.query("""SELECT id, COUNT(*) n,
        SUM(CASE WHEN status IN ('rejected','no_effect','weak') THEN 1 ELSE 0 END) fails
        FROM experiments GROUP BY id HAVING n>=3 AND fails>=3 ORDER BY fails DESC, id LIMIT 12""")
    gaps = []
    for r in rows:
        impact = saturating(r["fails"], 8)
        sc = score(impact, 0.75, saturating(r["n"], 10))
        fam = family_of(r["id"])
        gaps.append(ResearchGap(
            id=gap_id("REDUCE_REDUNDANCY", r["id"]), type="REDUCE_REDUNDANCY",
            description=f"'{r['id']}' retested {r['n']}x with {r['fails']} failures — stop repeating this direction",
            evidence={"hypothesis": r["id"], "family": fam, "runs": r["n"], "fails": r["fails"], **sc},
            priority_score=sc["priority"], related_entities=[r["id"], fam], created_at=ts))
    return gaps


def analyze_data_gaps(p3, kg, ts: str = "") -> list[ResearchGap]:
    """blocked_by_data 전략 → 데이터 획득 필요."""
    blocked = p3.query("SELECT id FROM strategies WHERE status='blocked_by_data'")
    gaps = []
    if blocked:
        n = len(blocked)
        sc = score(saturating(n, 6), 0.9, saturating(n, 10))
        gaps.append(ResearchGap(
            id=gap_id("DATA_GAP", "blocked_strategies"), type="DATA_GAP",
            description=f"{n} strategies blocked_by_data — acquire/wire missing datasets to unblock",
            evidence={"n_blocked": n, "ids": sorted(s["id"] for s in blocked)[:10], **sc},
            priority_score=sc["priority"], related_entities=[s["id"] for s in blocked][:10], created_at=ts))
    return gaps


def analyze_knowledge_gaps(p3, kg, ts: str = "") -> list[ResearchGap]:
    """파이프라인이 아직 생성 못 하는 엔티티(빈 노드타입) → 지식 격차."""
    gaps = []
    checks = [("Signal", "signal generation not producing graph signals"),
              ("Allocation", "no allocation history — portfolio pipeline not run/written"),
              ("PortfolioDecision", "no portfolio decision history")]
    for ntype, desc in checks:
        n = kg.query("SELECT COUNT(*) c FROM nodes WHERE type=?", (ntype,))[0]["c"]
        if n == 0:
            sc = score(0.3, 0.9, 0.3)
            gaps.append(ResearchGap(
                id=gap_id("KNOWLEDGE_GAP", ntype), type="KNOWLEDGE_GAP",
                description=f"{desc} ({ntype} nodes = 0)",
                evidence={"entity": ntype, "count": 0, **sc},
                priority_score=sc["priority"], related_entities=[ntype], created_at=ts))
    # OTHER 실패군이 크면 taxonomy 개선 격차
    other = _failure_patterns(kg).get("OTHER", 0)
    if other >= 10:
        sc = score(0.3, 0.7, saturating(other, 30))
        gaps.append(ResearchGap(
            id=gap_id("KNOWLEDGE_GAP", "failure_taxonomy"), type="KNOWLEDGE_GAP",
            description=f"{other} failures uncategorized (OTHER) — refine failure taxonomy for better learning",
            evidence={"other_count": other, **sc},
            priority_score=sc["priority"], related_entities=["failure_taxonomy"], created_at=ts))
    return gaps


def analyze_all(p3, kg, ts: str = "") -> list[ResearchGap]:
    """빈 그래프면 빈 결과. 아니면 전체 분석기 실행 후 gap dedup(id)."""
    if kg.query("SELECT COUNT(*) c FROM nodes")[0]["c"] == 0:
        return []
    gaps: dict = {}
    for fn in (analyze_failure_patterns, analyze_strategy_family_coverage,
               analyze_regime_coverage, analyze_research_redundancy,
               analyze_data_gaps, analyze_knowledge_gaps):
        for g in fn(p3, kg, ts):
            gaps[g.id] = g
    return list(gaps.values())
