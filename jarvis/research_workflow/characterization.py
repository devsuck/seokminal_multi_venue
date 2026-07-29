"""Golden Research Snapshot / Characterization (P202-1) — 리팩터링 안전망. **읽기 전용, 결정적.**

목적: P203(validation 통합)·P204(hypothesis 파사드) 리팩터링이 **의미를 보존**하는지 증명한다.
`output == output` 이 아니라 **`meaning == meaning`** — 553건 연구 이력의 연결(registry→experiments→
knowledge graph→recall→governance)이 코드 정리 후에도 동일한 의미를 내는지 지문(fingerprint)으로 고정.

두 계층:
  ① Data meaning — registry·experiment_registry·ingestion(예측과 무관, 영구 하드 불변).
  ② Composed meaning — knowledge_graph·recall·knowledge_health·hypothesis_discovery·governance
     (모듈 조율 결과 — 리팩터링이 깰 수 있는 지점).

주의: lesson 기반 수치는 예측 레코드(impact=prediction*)를 제외해 예측 누적에 강건. composed 계층은
리팩터링 세션 내 재생성 기준(예측 대량 누적 전). **재사용만, 새 원장 없음.**
원칙(§Constitution): 통합·검증만 · 결정적 · 자문 전용 · 거래·집행 없음.
"""
from __future__ import annotations

import ast
import hashlib
import json
import pathlib

# recall 연결이 깨지지 않았는지 확인할 고정 질의(과거 실패가 걸리는 것들)
_CANONICAL_QUERIES = ("momentum", "kr_pure_momentum_v1 reversal", "buyback drift")
_PREDICTION_IMPACTS = ("prediction", "prediction_transition")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _fp(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return "sha1:" + hashlib.sha1(blob.encode()).hexdigest()[:16]


def _r(v, n=4):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


# ── ① Data meaning (예측과 무관, 하드 불변) ──
def _data_meaning() -> dict:
    reg = _safe(lambda: __import__("jarvis.registry", fromlist=["StrategyRegistry"]
                                   ).StrategyRegistry().all_current(), []) or []
    by_status: dict = {}
    sids = []
    for s in reg:
        sids.append(s.get("strategy_id"))
        by_status[s.get("status", "?")] = by_status.get(s.get("status", "?"), 0) + 1

    def _tested(sid):
        return _safe(lambda: __import__("research.agents.experiment_registry",
                                        fromlist=["already_tested"]).already_tested(sid), []) or []

    per_strategy = {}
    total_rows = 0
    for sid in sorted(x for x in sids if x):
        rows = _tested(sid)
        total_rows += len(rows)
        if not rows:
            continue
        verdicts = sorted({str(r.get("verdict")) for r in rows})
        last = rows[-1]
        per_strategy[sid] = {
            "n": len(rows), "latest_status": last.get("status"),
            "verdict_fingerprint": _fp(verdicts),
            "metrics": {k: _r(last.get(k)) for k in ("sharpe", "p", "wf_first", "wf_second",
                                                     "ann_return", "max_drawdown")}}
    ingestion = _safe(lambda: __import__("jarvis.research_ingestion.engine",
                                         fromlist=["ResearchIngestionEngine"]
                                         ).ResearchIngestionEngine().summary(), None)
    by_outcome = (getattr(ingestion, "by_outcome", None) or {}) if ingestion else {}
    return {"registry": {"count": len(sids), "by_status": dict(sorted(by_status.items())),
                         "strategy_fingerprint": _fp(sorted(x for x in sids if x))},
            "experiments": {"strategies_with_data": len(per_strategy), "total_rows": total_rows,
                            "per_strategy_fingerprint": _fp(per_strategy)},
            "ingestion": {"by_outcome": dict(sorted(by_outcome.items()))}}


def _lessons_ex_predictions() -> int:
    rows = _safe(lambda: __import__("jarvis.research_memory_intelligence.ledger",
                                    fromlist=["read_lessons"]).read_lessons(), []) or []
    return sum(1 for r in rows if str(r.get("impact")) not in _PREDICTION_IMPACTS)


# ── ② Composed meaning (리팩터링이 깰 수 있는 지점) ──
def _composed_meaning() -> dict:
    kg = _safe(lambda: __import__("jarvis.research_workflow.knowledge_graph_upgrade",
                                  fromlist=["build_research_knowledge_graph"]
                                  ).build_research_knowledge_graph(), {}) or {}
    kh = _safe(lambda: __import__("jarvis.research_workflow.knowledge_quality",
                                  fromlist=["build_knowledge_health"]).build_knowledge_health(), {}) or {}
    gov = _safe(lambda: __import__("jarvis.research_workflow.governance",
                                   fromlist=["build_governance"]).build_governance(), {}) or {}

    def _recall(q):
        r = _safe(lambda: __import__("jarvis.research_workflow.semantic_recall",
                                     fromlist=["recall_context"]).recall_context(q), {}) or {}
        cnt = lambda v: len(v) if isinstance(v, list) else (int(v) if v else 0)  # noqa: E731
        return {"tried_before": bool(r.get("tried_before")),
                "made_this_mistake": bool(r.get("made_this_mistake")),
                "similar_failures": cnt(r.get("similar_failures")),
                "past_conclusions": cnt(r.get("past_conclusions"))}

    hyp = _safe(lambda: __import__("jarvis.research_workflow.hypothesis_discovery",
                                   fromlist=["discover_research"]).discover_research("momentum", limit=6),
                {}) or {}
    return {
        "knowledge_graph": {"node_count": kg.get("node_count", len(kg.get("nodes", []) or [])),
                            "edge_count": kg.get("edge_count", len(kg.get("edges", []) or []))},
        "knowledge_health": {"grade": kh.get("grade"),
                             "lessons_ex_predictions": _lessons_ex_predictions()},
        "recall": {q: _recall(q) for q in _CANONICAL_QUERIES},
        "hypothesis_discovery": {"count": hyp.get("hypothesis_count", 0),
                                 "recall_first": hyp.get("recall_first")},
        "governance": {"governance": gov.get("governance"), "passed": gov.get("passed")}}


def build_meaning_snapshot() -> dict:
    """연구 의미 지문(결정적·읽기전용) — data meaning(하드) + composed meaning(리팩터링 가드)."""
    data = _data_meaning()
    composed = _composed_meaning()
    return {"schema": "research_meaning_v1",
            "data_meaning": data, "composed_meaning": composed,
            "data_meaning_hash": _fp(data),
            "is_advisory": True, "is_decision": False,
            "note": ("Golden Research Snapshot(읽기전용) — meaning==meaning 안전망. "
                     "data_meaning 은 예측 무관 하드 불변. composed 는 리팩터링 가드(세션 내 재생성 기준).")}


# ── Call Graph Golden (P204) — 호출 구조 보존 검증 ──
# 리팩터링이 의미(meaning)뿐 아니라 **호출 구조**(누가 누구를 조율하는가)까지 보존하는지 확인.
# 파사드가 내부 모듈을 재구현하지 않고 정말 '조율'만 하는지 AST 로 지문화(결정적).
_SRC_DIR = pathlib.Path(__file__).resolve().parent
# 호출 구조를 감시할 서브시스템(P204 hypothesis discovery)
CALL_GRAPH_MODULES = ("research_discovery", "hypothesis_discovery", "creative_hypothesis",
                      "hypothesis_generator", "research_search", "research_expansion",
                      "research_critic", "research_priority", "experiment_prioritization")


def _module_refs(src: str) -> set:
    """AST — 이 모듈이 참조하는 research_workflow 형제 모듈 집합(import + __import__ 문자열)."""
    refs = set()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and \
                node.module.startswith("jarvis.research_workflow."):
            refs.add(node.module.split(".")[-1])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and \
                        arg.value.startswith("jarvis.research_workflow."):
                    refs.add(arg.value.split(".")[-1])
    return refs


def build_call_graph(modules=CALL_GRAPH_MODULES) -> dict:
    """서브시스템 호출 그래프(결정적) — {module: sorted[참조하는 형제 모듈]}. 파사드 조율 구조 지문."""
    graph = {}
    for m in modules:
        path = _SRC_DIR / f"{m}.py"
        refs = _module_refs(path.read_text(encoding="utf-8")) if path.exists() else set()
        # 서브시스템 내부 참조만(구조 핵심) — 외부 잡음 제외
        graph[m] = sorted(refs & set(modules))
    return {"schema": "call_graph_v1", "modules": list(modules), "graph": graph,
            "graph_hash": _fp(graph), "is_advisory": True, "is_decision": False,
            "note": ("Call Graph Golden(읽기전용) — 파사드가 내부 모듈을 재구현 않고 조율만 하는지 "
                     "AST 호출 구조로 검증. 리팩터링이 호출 위상을 바꾸면 감지.")}


def compare_call_graph(golden: dict) -> dict:
    """현재 호출 그래프 vs 골든 — 호출 구조 동일성(결정적)."""
    cur = build_call_graph()
    same = cur["graph_hash"] == golden.get("graph_hash")
    diffs = []
    if not same:
        g, c = golden.get("graph", {}), cur["graph"]
        for m in set(g) | set(c):
            if g.get(m) != c.get(m):
                diffs.append({"module": m, "golden": g.get(m), "current": c.get(m)})
    return {"call_graph_identical": same, "diffs": diffs,
            "is_advisory": True, "is_decision": False,
            "note": "Call Graph 비교 — 호출 구조 보존 증명(파사드 조율 위상 불변)."}


def compare_to_golden(golden: dict) -> dict:
    """현재 스냅샷 vs 골든 — data_meaning 은 하드 동일성, composed 는 구조·불변식 확인. 결정적."""
    cur = build_meaning_snapshot()
    data_same = cur["data_meaning_hash"] == golden.get("data_meaning_hash")
    diffs = []
    if not data_same:
        gd, cd = golden.get("data_meaning", {}), cur["data_meaning"]
        for k in ("registry", "experiments", "ingestion"):
            if gd.get(k) != cd.get(k):
                diffs.append(f"data_meaning.{k} changed")
    # composed 불변식(리팩터링이 깨면 안 되는 것)
    comp = cur["composed_meaning"]
    gcomp = golden.get("composed_meaning", {})
    composed_checks = {
        "governance_compliant": comp["governance"].get("governance") == gcomp.get("governance", {}).get("governance"),
        "recall_connections_preserved": comp["recall"] == gcomp.get("recall"),
        "hypothesis_discovery_stable": comp["hypothesis_discovery"] == gcomp.get("hypothesis_discovery"),
        "knowledge_grade_stable": comp["knowledge_health"].get("grade") == gcomp.get("knowledge_health", {}).get("grade"),
    }
    return {"data_meaning_identical": data_same, "data_diffs": diffs,
            "composed_checks": composed_checks,
            "meaning_preserved": data_same and all(composed_checks.values()),
            "is_advisory": True, "is_decision": False,
            "note": "meaning==meaning 비교 — data_meaning 하드 동일 + composed 불변식. 리팩터링 안전 증명."}
