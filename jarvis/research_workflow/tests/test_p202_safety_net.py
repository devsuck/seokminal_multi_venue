"""P202 Migration Safety Net 테스트 — characterization(meaning==meaning) + capture hook + ledger contract.

핵심: 리팩터링(P203/204) 전 안전망. data_meaning 은 예측 무관 하드 불변 · composed 는 연결 보존 확인 ·
capture hook 은 전달만(scoring/eval/dashboard 없음) · LedgerBackend 는 backend 독립 · 새 원장 없음.
"""
from __future__ import annotations

import ast
import json
import pathlib

from jarvis.research_workflow import characterization as ch
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import ledger_writer as lw
from jarvis.research_workflow import prediction_capture_hook as hook

SRC = pathlib.Path(__file__).resolve().parent.parent
GOLDEN = pathlib.Path(__file__).resolve().parent / "golden" / "research_meaning.json"
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_MODULES = ("characterization.py", "prediction_capture_hook.py", "ledger_writer.py")
_N = "2026-07-26T00:00:00Z"


# ── P202-1 Characterization: meaning == meaning ──
def test_meaning_snapshot_matches_golden():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    cmp = ch.compare_to_golden(golden)
    assert cmp["data_meaning_identical"] is True, cmp["data_diffs"]
    assert cmp["meaning_preserved"] is True, cmp["composed_checks"]


def test_meaning_snapshot_deterministic():
    a = ch.build_meaning_snapshot()
    b = ch.build_meaning_snapshot()
    assert a["data_meaning_hash"] == b["data_meaning_hash"]
    assert a["data_meaning"] == b["data_meaning"]


def test_data_meaning_captures_real_history():
    snap = ch.build_meaning_snapshot()
    # 553 실험 · 61 전략 연결이 지문에 잡혀야 함
    assert snap["data_meaning"]["registry"]["count"] >= 60
    assert snap["data_meaning"]["experiments"]["total_rows"] >= 500
    assert snap["data_meaning"]["ingestion"]["by_outcome"].get("FAILURE", 0) > 0


# ── P202-2 Capture Hook: 전달만(scoring/eval 없음) ──
def test_capture_hook_committee_preview():
    packet = {"research_summary": "momentum edge in KR event studies", "confidence": "HIGH",
              "limitations": ["random 못 넘으면 폐기"], "supporting_evidence": ["exp:1", "exp:2"]}
    s = hook.capture_from_committee(packet, strategy_family="event", now=_N)
    assert s["state"] == "PENDING" and s["source"] == "committee" and s["confidence"] == "HIGH"
    assert s["invalidation_condition"] == "random 못 넘으면 폐기"
    assert s["evaluation_framework"]["framework"] == "abnormal_return"  # family 로 결정적 유도
    assert s["is_decision"] is False


def test_capture_hook_normalizes_confidence():
    assert hook._norm_conf(0.8) == "HIGH" and hook._norm_conf(0.5) == "MEDIUM" and hook._norm_conf(0.2) == "LOW"
    assert hook._norm_conf("med") == "MEDIUM"
    s = hook.capture_from_hypothesis({"question": "q", "confidence": 0.3}, now=_N)
    assert s["confidence"] == "LOW" and s["source"] == "automatic_discovery"


def test_capture_hook_generic_source_whitelist():
    s = hook.capture_research_output("bogus_source", thesis="t", now=_N)
    assert s["source"] == "human_hypothesis"  # 화이트리스트 외 → 기본


# ── P202-3 Ledger contract: backend 독립 ──
def test_ledger_backend_contract(tmp_path):
    b = lw.JsonlLedgerBackend("x.jsonl")
    b._path = lambda: str(tmp_path / "x.jsonl")   # 임시 경로(_state 무오염)
    assert b.read() == [] and b.head() is None
    b.append({"id": 1, "v": "a"})
    b.append({"id": 2, "v": "b"})
    assert len(b.read()) == 2 and b.head()["id"] == 2
    v = b.verify()
    assert v["ok"] is True and v["records"] == 2


def test_ledger_backend_abstract():
    base = lw.LedgerBackend()
    for m in ("append", "read", "head", "verify"):
        try:
            getattr(base, m)() if m in ("read", "head", "verify") else getattr(base, m)({})
            assert False, f"{m} should raise"
        except NotImplementedError:
            pass


# ── 새 원장 없음 + 금지 스캔 ──
def test_no_new_ledger():
    assert len(wl.ALL_LEDGERS) == 3


def test_no_forbidden_defs_imports_leak():
    for f in _MODULES:
        src = open(SRC / f).read()
        assert MODEL_LEAK_TOKEN not in src.lower(), f
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(b) for b in
                               ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                                "jarvis.live_trading", "jarvis.portfolio_execution")), (f, node.module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in ("execute", "trade", "deploy", "allocate", "approve",
                                         "place_order", "deploy_strategy"), (f, node.name)
