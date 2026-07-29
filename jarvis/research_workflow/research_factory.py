"""Research Factory (P210) — 기관급 연구 공장. **약한 아이디어를 더 일찍 죽이는 깔때기.** 실행 없음.

목표는 아이디어를 **더** 만드는 게 아니라 **약한 걸 먼저 REJECT** 하는 것. 살아남은 연구만 진행.

깔때기(각 게이트가 REJECT):
  Idea → Economic rationale → Novelty → Similarity → Data availability → Experiment design →
  Backtest → Walk-forward → Multiple testing(BH-FDR) → Capacity → Slippage → Failure analysis → Paper Candidate.

**LLM 사용 규칙(엄격)**: LLM 은 **절대 아이디어 생성기가 아니다.** LLM 은 **오직 economic rationale 심판**이다.
  프롬프트: "경제적 메커니즘을 설명하라. 설득력 있는 메커니즘이 없으면 기각하라."
  judge 는 주입(credential-free) — 없으면 rationale 유무만 결정적 사전심사(가짜 통과 없음).
**그 외 전부 결정적.** 실행·배분·포트폴리오 결정 없음.

**재사용**: semantic_recall(novelty)·research_similarity(similarity)·data_connection(data)·
experiment_designer(design)·backtest_bridge(backtest=외부/사람)·research_ingestion(failure taxonomy).
새 엔진/원장 없음. 원칙(§Constitution): 통합·조율만 · 자문 전용 · 거래·집행 없음 · 사람이 결정.
"""
from __future__ import annotations

GATES = ("economic_rationale", "novelty", "similarity", "data_availability", "experiment_design",
         "backtest", "walk_forward", "multiple_testing", "capacity", "slippage", "failure_analysis",
         "paper_candidate")

# 결정적 임계 (게이트 기준)
_NOVELTY_MAX_PRIOR = 5        # 선행연구 이보다 많으면 novelty 기각(과다연구)
_SIMILARITY_MAX = 0.85       # 이보다 유사하면 중복 기각
_SHARPE_MIN = 0.0            # 백테스트 최소
_FDR_ALPHA = 0.1            # BH-FDR 유의수준
_CAPACITY_MIN_ADV_PCT = 0.0  # 용량(참고)
# economic rationale judge 프롬프트(LLM 에 주입되는 유일한 프롬프트 — 심판용)
ECONOMIC_JUDGE_PROMPT = ("Explain the economic mechanism for this hypothesis. "
                         "If no convincing mechanism exists, reject.")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _count(v):
    if isinstance(v, list):
        return len(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _gate(name, passed, reason, **extra):
    return {"gate": name, "passed": passed, "reason": reason, **extra}


# ── Gate 1: Economic rationale — 유일한 LLM 사용처(심판, 생성 아님) ──
def economic_rationale_gate(idea: dict, *, judge=None) -> dict:
    """경제적 메커니즘 심판. judge(LLM) 주입 시 설득력 판정 → REJECT/PASS. 없으면 rationale 유무만 결정적 사전심사.

    judge: callable({thesis, prompt}) -> {convincing: bool, mechanism: str, reason: str}. **오직 심판.**
    """
    rationale = str(idea.get("rationale") or idea.get("economic_rationale") or idea.get("mechanism") or "").strip()
    if judge is not None:
        v = _safe(lambda: judge({"thesis": idea.get("thesis") or idea.get("statement", ""),
                                 "rationale": rationale, "prompt": ECONOMIC_JUDGE_PROMPT}), {}) or {}
        convincing = bool(v.get("convincing"))
        return _gate("economic_rationale", convincing,
                     "convincing economic mechanism" if convincing else "no convincing mechanism → reject",
                     judged_by="llm", mechanism=v.get("mechanism", ""), judge_reason=v.get("reason", ""))
    # judge 없음 — rationale 없으면 명확히 REJECT(약한 아이디어 조기 제거). 있으면 심판 대기(가짜 통과 금지).
    if not rationale:
        return _gate("economic_rationale", False, "no stated economic rationale → reject (weak idea)",
                     judged_by="deterministic_prescreen")
    return _gate("economic_rationale", None, "rationale exists — awaiting LLM/human economic judge",
                 judged_by="pending_judge", provisional=True)


# ── Gate 2: Novelty (semantic_recall — 과다연구면 기각) ──
def novelty_gate(idea: dict) -> dict:
    q = str(idea.get("thesis") or idea.get("statement") or idea.get("strategy_id", ""))
    r = _safe(lambda: __import__("jarvis.research_workflow.semantic_recall",
                                 fromlist=["recall_context"]).recall_context(q), {}) or {}
    prior = _count(r.get("prior_research_count"))
    passed = prior <= _NOVELTY_MAX_PRIOR
    return _gate("novelty", passed,
                 f"prior_research={prior} (<= {_NOVELTY_MAX_PRIOR})" if passed
                 else f"over-researched (prior={prior}) → reject", prior_research=prior)


# ── Gate 3: Similarity (research_similarity — 중복이면 기각) ──
def similarity_gate(idea: dict, *, existing=None) -> dict:
    sim = _safe(lambda: __import__("jarvis.research_workflow.research_similarity",
                                   fromlist=["ResearchSimilarity"]).ResearchSimilarity())
    q = str(idea.get("thesis") or idea.get("statement", ""))
    max_sim = 0.0
    for e in (existing or []):
        s = _safe(lambda ee=e: sim.compare(q, ee)["similarity_score"], 0.0) if sim else 0.0
        max_sim = max(max_sim, s)
    passed = max_sim < _SIMILARITY_MAX
    return _gate("similarity", passed,
                 f"max_similarity={max_sim} (< {_SIMILARITY_MAX})" if passed
                 else f"duplicate (sim={max_sim}) → reject", max_similarity=round(max_sim, 4))


# ── Gate 4: Data availability (data_connection — 데이터 없으면 기각) ──
def data_availability_gate(idea: dict) -> dict:
    category = idea.get("data_category") or "market"
    # 필요 데이터를 제공하는 소스가 카탈로그에 존재하는가(키 유무 아님 — 커버리지 기준)
    reg = _safe(lambda: __import__("jarvis.research_workflow.providers",
                                   fromlist=["provider_registry"]).provider_registry(), {}) or {}
    cats = set(reg.get("categories", []))
    passed = category in cats or category in ("market", "fundamental")
    return _gate("data_availability", passed,
                 f"provider covers '{category}'" if passed else f"no data provider for '{category}' → reject",
                 category=category)


# ── Gate 5: Experiment design (experiment_designer — 설계 불가면 기각) ──
def experiment_design_gate(idea: dict) -> dict:
    spec = _safe(lambda: __import__("jarvis.research_workflow.experiment_designer",
                                    fromlist=["design_experiment"]).design_experiment(idea), {}) or {}
    ok = bool(spec.get("universe") and spec.get("metrics"))
    return _gate("experiment_design", ok,
                 "valid experiment spec" if ok else "cannot design testable experiment → reject",
                 expected_research_value=spec.get("expected_research_value"))


# ── Gate 6: Backtest (backtest_bridge — 외부/사람, 자동 실행 없음; 결과로 판정) ──
def backtest_gate(idea: dict) -> dict:
    m = idea.get("metrics") or {}
    sharpe = _num(m.get("sharpe"))
    net = _num(m.get("net") if m.get("net") is not None else m.get("net_pnl"))
    if sharpe is None and net is None:
        # 결과 없음 → 외부 사람 실행 대기(자동 백테스트 없음)
        return _gate("backtest", None, "no backtest result — external human run required (no auto-backtest)",
                     status="EXTERNAL_PENDING")
    ok = (sharpe is None or sharpe >= _SHARPE_MIN) and (net is None or net >= 0)
    return _gate("backtest", ok,
                 f"sharpe={sharpe} net={net}" if ok else f"backtest failed (sharpe={sharpe} net={net}) → reject",
                 sharpe=sharpe, net=net)


# ── Gate 7: Walk-forward (OOS 붕괴면 기각) ──
def walk_forward_gate(idea: dict) -> dict:
    m = idea.get("metrics") or {}
    wf1 = _num(m.get("wf_first")) if m.get("wf_first") is not None else _num(m.get("wf_first_sharpe"))
    wf2 = _num(m.get("wf_second")) if m.get("wf_second") is not None else _num(m.get("wf_second_sharpe"))
    if wf1 is None or wf2 is None:
        return _gate("walk_forward", None, "no walk-forward split — required before proceeding",
                     status="MISSING")
    if wf1 > 0 and wf2 <= 0:
        return _gate("walk_forward", False, f"OOS collapse (wf1={wf1}, wf2={wf2}) → overfit reject",
                     wf_first=wf1, wf_second=wf2)
    passed = not (wf1 <= 0 and wf2 <= 0)
    return _gate("walk_forward", passed,
                 f"walk-forward holds (wf1={wf1}, wf2={wf2})" if passed
                 else "both windows negative → reject", wf_first=wf1, wf_second=wf2)


# ── Gate 8: Multiple testing (BH-FDR — 배치 게이트) ──
def _bh_fdr(pvals, alpha=_FDR_ALPHA):
    """Benjamini-Hochberg — 유의 생존 마스크(결정적). 통계 프리미티브(엔진 아님)."""
    indexed = sorted((p, i) for i, p in enumerate(pvals) if p is not None)
    m = len(indexed)
    survive = [False] * len(pvals)
    kmax = 0
    for rank, (p, _) in enumerate(indexed, start=1):
        if p <= (rank / m) * alpha:
            kmax = rank
    for rank, (p, i) in enumerate(indexed, start=1):
        if rank <= kmax:
            survive[i] = True
    return survive


def multiple_testing_gate(alive_ideas, *, alpha=_FDR_ALPHA) -> list:
    """살아남은 아이디어들의 p-value 에 BH-FDR 적용 → 생존 마스크. 배치 게이트."""
    pvals = [_num((i.get("metrics") or {}).get("empirical_p")
                  if (i.get("metrics") or {}).get("empirical_p") is not None
                  else (i.get("metrics") or {}).get("p")) for i in alive_ideas]
    if not any(p is not None for p in pvals):
        return [_gate("multiple_testing", None, "no p-values — cannot apply FDR", status="MISSING")
                for _ in alive_ideas]
    mask = _bh_fdr(pvals, alpha)
    out = []
    for i, surv in enumerate(mask):
        p = pvals[i]
        if p is None:
            out.append(_gate("multiple_testing", None, "no p-value", status="MISSING"))
        else:
            out.append(_gate("multiple_testing", surv,
                             f"survives BH-FDR (p={p}, alpha={alpha})" if surv
                             else f"fails BH-FDR (p={p}) → reject", p_value=p))
    return out


# ── Gate 9: Capacity (용량 부족이면 기각) ──
def capacity_gate(idea: dict) -> dict:
    m = idea.get("metrics") or {}
    cap = _num(m.get("capacity") or m.get("adv_pct"))
    if cap is None:
        return _gate("capacity", None, "capacity unknown — ADV/turnover data required", status="UNKNOWN")
    passed = cap >= _CAPACITY_MIN_ADV_PCT
    return _gate("capacity", passed, f"capacity ok ({cap})" if passed else "capacity too small → reject",
                 capacity=cap)


# ── Gate 10: Slippage (비용 후 음수면 기각) ──
def slippage_gate(idea: dict) -> dict:
    m = idea.get("metrics") or {}
    cost = _num(m.get("cost_impact"))
    net_after = _num(m.get("net_after_cost"))
    if net_after is not None:
        passed = net_after >= 0
        return _gate("slippage", passed, f"net_after_cost={net_after}" if passed
                     else "negative after slippage → reject", net_after_cost=net_after)
    if cost is not None:
        passed = cost < 0.3
        return _gate("slippage", passed, f"cost_impact={cost}" if passed
                     else "cost-sensitive → reject", cost_impact=cost)
    return _gate("slippage", None, "cost data unknown — cost stress required", status="UNKNOWN")


# ── Gate 11: Failure analysis (기각 사유 자동 분류) ──
def failure_analysis(idea: dict, terminal_gate: str, reason: str) -> dict:
    m = idea.get("metrics") or {}
    cat = _safe(lambda: __import__("jarvis.research_ingestion.models",
                                   fromlist=["auto_classify_failure"]
                                   ).auto_classify_failure(m, reason), "UNCLASSIFIED")
    return {"rejected_at": terminal_gate, "reason": reason, "failure_category": cat}


def _run_idea(idea, *, judge, existing) -> dict:
    """한 아이디어를 게이트 순서로 통과(첫 REJECT 에서 정지). backtest~ 이후는 배치 FDR 전까지."""
    trace = []
    seq = [lambda i: economic_rationale_gate(i, judge=judge),
           novelty_gate,
           lambda i: similarity_gate(i, existing=existing),
           data_availability_gate,
           experiment_design_gate,
           backtest_gate,
           walk_forward_gate]
    for fn in seq:
        g = fn(idea)
        trace.append(g)
        if g["passed"] is False:   # 하드 REJECT
            fa = failure_analysis(idea, g["gate"], g["reason"])
            return {"idea": idea.get("strategy_id") or idea.get("thesis", "")[:40],
                    "status": "REJECTED", "rejected_at": g["gate"], "reason": g["reason"],
                    "failure": fa, "trace": trace, "alive": False}
        if g["passed"] is None:    # HELD(외부/판단 대기) — 진행 보류
            return {"idea": idea.get("strategy_id") or idea.get("thesis", "")[:40],
                    "status": "HELD", "held_at": g["gate"], "reason": g["reason"],
                    "trace": trace, "alive": False}
    return {"idea": idea.get("strategy_id") or idea.get("thesis", "")[:40],
            "status": "ALIVE_PRE_FDR", "trace": trace, "alive": True}


def run_factory(ideas, *, judge=None, alpha=_FDR_ALPHA) -> dict:
    """연구 공장 실행 — 깔때기로 약한 아이디어 조기 REJECT. 살아남은 것만 Paper Candidate. 결정적(judge 제외).

    ideas: [{strategy_id, thesis, rationale, metrics{sharpe,net,wf_first,wf_second,empirical_p,...},
    data_category, family}]. judge: LLM economic-rationale 심판(주입, 선택). 없으면 rationale 유무만 사전심사.
    """
    ideas = list(ideas or [])
    theses = [str(i.get("thesis") or i.get("strategy_id", "")) for i in ideas]
    # 1) per-idea 순차 게이트(economic~walk_forward) — similarity 는 **자기 제외** 다른 아이디어와 비교
    results = [_run_idea(i, judge=judge, existing=[t for j, t in enumerate(theses) if j != k])
               for k, i in enumerate(ideas)]
    alive_idx = [k for k, r in enumerate(results) if r["alive"]]
    alive_ideas = [ideas[k] for k in alive_idx]

    # 2) 배치 게이트: BH-FDR
    fdr = multiple_testing_gate(alive_ideas, alpha=alpha)
    for j, k in enumerate(alive_idx):
        g = fdr[j]
        results[k]["trace"].append(g)
        if g["passed"] is False:
            results[k].update({"status": "REJECTED", "rejected_at": "multiple_testing",
                               "reason": g["reason"], "alive": False,
                               "failure": failure_analysis(ideas[k], "multiple_testing", g["reason"])})

    # 3) per-survivor: capacity → slippage
    for k in [k for k, r in enumerate(results) if r["alive"]]:
        for fn, gname in ((capacity_gate, "capacity"), (slippage_gate, "slippage")):
            g = fn(ideas[k])
            results[k]["trace"].append(g)
            if g["passed"] is False:
                results[k].update({"status": "REJECTED", "rejected_at": gname, "reason": g["reason"],
                                   "alive": False,
                                   "failure": failure_analysis(ideas[k], gname, g["reason"])})
                break

    # 4) 최종 Paper Candidate = 전 게이트 통과
    for r in results:
        if r["alive"]:
            r["status"] = "PAPER_CANDIDATE"

    return _funnel_report(ideas, results)


def _funnel_report(ideas, results) -> dict:
    rejected_by_gate: dict = {}
    held_by_gate: dict = {}
    for r in results:
        if r["status"] == "REJECTED":
            rejected_by_gate[r["rejected_at"]] = rejected_by_gate.get(r["rejected_at"], 0) + 1
        elif r["status"] == "HELD":
            held_by_gate[r["held_at"]] = held_by_gate.get(r["held_at"], 0) + 1
    candidates = [r for r in results if r["status"] == "PAPER_CANDIDATE"]
    fail_cats: dict = {}
    for r in results:
        fc = (r.get("failure") or {}).get("failure_category")
        if fc:
            fail_cats[fc] = fail_cats.get(fc, 0) + 1
    return {"entered": len(ideas), "gates": list(GATES),
            "paper_candidates": len(candidates),
            "rejected": sum(1 for r in results if r["status"] == "REJECTED"),
            "held": sum(1 for r in results if r["status"] == "HELD"),
            "rejected_by_gate": dict(sorted(rejected_by_gate.items())),
            "held_by_gate": dict(sorted(held_by_gate.items())),
            "failure_categories": dict(sorted(fail_cats.items())),
            "survival_rate_pct": round(100.0 * len(candidates) / len(ideas), 1) if ideas else None,
            "candidates": [r["idea"] for r in candidates],
            "results": results,
            "llm_usage": "economic_rationale judge ONLY (never idea generator)",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Research Factory(읽기전용) — 약한 아이디어 조기 REJECT 깔때기. 살아남은 것만 Paper Candidate. "
                     "LLM 은 economic rationale 심판 전용(생성 아님). 그 외 결정적. 자동 백테스트/실행/배분 없음.")}


def _ideas_from_registry() -> list:
    """실제 전략 이력(experiment_registry)으로 아이디어 구성 — 데모/운영용. 읽기전용."""
    reg = _safe(lambda: __import__("jarvis.registry", fromlist=["StrategyRegistry"]
                                   ).StrategyRegistry().all_current(), []) or []
    at = _safe(lambda: __import__("research.agents.experiment_registry",
                                  fromlist=["already_tested"]).already_tested)
    ideas = []
    for s in reg:
        sid = s.get("strategy_id", "")
        rows = _safe(lambda ss=sid: at(ss), []) if at else []
        if not rows:
            continue
        e = rows[-1]
        ideas.append({"strategy_id": sid, "thesis": f"{sid} durable edge",
                      "rationale": str(e.get("verdict") or e.get("note") or ""),
                      "data_category": "market",
                      "metrics": {"sharpe": e.get("sharpe"),
                                  "net": e.get("net") if e.get("net") is not None else e.get("net_pnl"),
                                  "wf_first": e.get("wf_first"), "wf_second": e.get("wf_second"),
                                  "empirical_p": e.get("p"), "cost_impact": e.get("cost_stress")}})
    return ideas


def run_on_registry(*, judge=None, alpha=_FDR_ALPHA) -> dict:
    """실제 전략 이력에 깔때기 적용 — 무엇이 조기 REJECT 되는지 시연. judge 없으면 economic 게이트 HELD."""
    return run_factory(_ideas_from_registry(), judge=judge, alpha=alpha)
