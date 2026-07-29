"""Backfill 룬북 테스트 — 기존 실험 이력 → 연구 원장 멱등 백필.

핵심: 기존 registry(읽기) + 기존 ResearchIngestionEngine(쓰기)만 재사용 · 새 원장/엔진 없음 · 자문 전용 ·
결정적 · 멱등(재수집 no-op) · 거래·집행·배포 없음. status→outcome 은 충실한 번역(새 판정 아님).
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import backfill as bf
from jarvis.research_workflow import ledger as wl

SRC = pathlib.Path(__file__).resolve().parent.parent / "backfill.py"
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


class _FakeEngine:
    """ingest 를 기록만 하는 가짜 엔진(원장 무변경) — 스키마·멱등 계약 검증용."""

    def __init__(self):
        self.calls = []
        self._seen = set()

    def ingest(self, schema, now="", *, commit=False, strict=False, provenance=None):
        from types import SimpleNamespace
        key = (schema["strategy_name"], schema["strategy_version"], str(schema.get("metrics")))
        dedup = key in self._seen
        self._seen.add(key)
        self.calls.append((schema, now, commit))
        mem = "none"
        if schema.get("outcome") == "FAILURE":
            mem = "failure"
        elif schema.get("outcome") == "SUCCESS":
            mem = "success"
        return SimpleNamespace(outcome=schema.get("outcome", "INCOMPLETE"),
                               memory_written="none" if dedup else mem, deduplicated=dedup)


# ── status → outcome 는 충실한 번역(고정 매핑) ──
def test_status_outcome_map_is_faithful():
    assert bf.STATUS_OUTCOME["rejected"] == "FAILURE"
    assert bf.STATUS_OUTCOME["no_effect"] == "FAILURE"
    assert bf.STATUS_OUTCOME["paper_candidate"] == "SUCCESS"
    assert bf.STATUS_OUTCOME["candidate"] == "PARTIAL"
    assert bf.STATUS_OUTCOME["weak"] == "INCOMPLETE"
    # 미지의 status 는 정직하게 INCOMPLETE
    row = {"status": "some_new_status_9x", "verdict": "?"}
    assert bf._schema("x", row)["outcome"] == "INCOMPLETE"


# ── distinct verdict 당 최신 1건(반복 로깅 축소, 실제 반복 보존) ──
def test_distinct_by_verdict_collapses_relogging():
    rows = [{"verdict": "A", "net": 1}, {"verdict": "A", "net": 2}, {"verdict": "A", "net": 3},
            {"verdict": "B", "net": 9}]
    kept = bf._distinct_by_verdict(rows)
    assert len(kept) == 2                       # A, B
    a = [r for r in kept if r["verdict"] == "A"][0]
    assert a["net"] == 3                         # 최신 유지


# ── 스키마 매핑: 실패는 원본 verdict/note 를 원인·교훈으로 보존, 지표 날조 없음 ──
def test_schema_preserves_verdict_and_no_fabrication():
    row = {"status": "rejected", "verdict": "REJECT — 비용 후 음수", "note": "cost kills edge",
           "sharpe": -0.3, "max_drawdown": -0.2, "p": 0.9}
    s = bf._schema("kr_x", row)
    assert s["outcome"] == "FAILURE"
    assert s["root_cause"] == "REJECT — 비용 후 음수"
    assert s["lesson"] == "cost kills edge"
    assert s["metrics"]["sharpe"] == -0.3 and s["metrics"]["max_drawdown"] == -0.2
    # 없는 지표는 담지 않는다(정직한 결측)
    assert "volatility" not in s["metrics"] and "cost_impact" not in s["metrics"]


# ── 드라이런은 원장을 만들지 않는다(가짜 엔진 사용) ──
def test_run_backfill_dryrun_and_idempotent():
    fake = _FakeEngine()
    r1 = bf.run_backfill(commit=False, engine=fake)
    assert r1["is_advisory"] is True and r1["is_decision"] is False
    assert r1["records_ingested"] >= 0
    n = len(fake.calls)
    # 같은 엔진으로 재실행 → 전부 dedup(멱등 계약)
    r2 = bf.run_backfill(commit=False, engine=fake)
    assert len(fake.calls) == 2 * n
    assert r2["records_deduplicated"] == r2["records_ingested"] + r2["records_deduplicated"] \
        or r2["records_ingested"] == 0


# ── plan 미리보기 계약 ──
def test_plan_shape():
    fake_ok = bf.plan()
    for k in ("strategies_scanned", "records_to_ingest", "by_outcome",
              "rows_collapsed_by_verdict_dedup", "is_advisory", "is_decision"):
        assert k in fake_ok, k
    assert fake_ok["is_decision"] is False


# ── 새 원장 없음 ──
def test_no_new_ledger():
    assert len(wl.ALL_LEDGERS) == 3


# ── 금지 def/import/모델 누출 없음 ──
def test_no_forbidden_defs_imports_leak():
    src = SRC.read_text()
    assert MODEL_LEAK_TOKEN not in src.lower()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in
                           ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                            "jarvis.live_trading", "jarvis.portfolio_execution")), node.module
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in ("execute", "trade", "deploy", "allocate", "approve",
                                     "place_order", "deploy_strategy"), node.name
