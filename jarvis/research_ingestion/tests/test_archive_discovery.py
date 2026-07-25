"""Research Archive Discovery(P56) 테스트 — 발견·감지·신뢰도·검증상태·읽기전용·안전.

핵심: 과거 연구 자산을 찾아 Manifest 를 만들되, **어떤 원장에도 쓰지 않는다(발견 ≠ 임포트)**.
"""
from __future__ import annotations

import ast
import json
import pathlib

from jarvis.research_ingestion import ledger
from jarvis.research_ingestion.archive_discovery import (
    CONF_HIGH,
    CONF_MEDIUM,
    VS_COMPLETE,
    VS_INCOMPLETE,
    ResearchArchiveDiscovery,
    analyze_file,
    discover,
)

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"

_FULL = {"return": 0.14, "sharpe": 0.9, "max_drawdown": -0.18, "volatility": 0.13,
         "walk_forward": 0.8, "out_of_sample": 0.7, "cost_impact": 0.1,
         "parameter_stability": 0.8, "random_baseline": 0.2}


def _archive_tree(tmp_path):
    root = tmp_path / "research"
    (root / "sub").mkdir(parents=True)
    # 1) 완전 검증 JSON(HIGH, COMPLETE)
    (root / "tsmom.json").write_text(json.dumps(
        {"strategy": "TSMOM", "metrics": dict(_FULL)}), encoding="utf-8")
    # 2) 불완전 JSONL(MEDIUM, INCOMPLETE)
    (root / "vwap.jsonl").write_text(json.dumps(
        {"strategy": "VWAP", "metrics": {"sharpe": 0.6, "return": 0.08}}), encoding="utf-8")
    # 3) CSV(전략+지표)
    (root / "orb.csv").write_text("strategy,sharpe,max_drawdown\nORB,-0.1,-0.35\n",
                                  encoding="utf-8")
    # 4) Markdown 리포트
    (root / "sub" / "report.md").write_text(
        "# Momentum\n\nsharpe: 1.2\nmax_drawdown: -0.2\n", encoding="utf-8")
    # 5) 노이즈(감지 안 됨)
    (root / "notes.md").write_text("just some meeting notes, nothing quant\n", encoding="utf-8")
    return root


def test_analyze_full_json_high_complete(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"strategy": "TSMOM", "metrics": dict(_FULL)}), encoding="utf-8")
    c = analyze_file(str(p))
    assert c.detected_strategy == "TSMOM"
    assert c.confidence == CONF_HIGH
    assert c.validation_status == VS_COMPLETE
    assert c.import_candidate is True


def test_analyze_incomplete_medium(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text(json.dumps({"strategy": "VWAP", "metrics": {"sharpe": 0.6, "return": 0.08}}),
                 encoding="utf-8")
    c = analyze_file(str(p))
    assert c.confidence == CONF_MEDIUM
    assert c.validation_status == VS_INCOMPLETE
    assert c.import_candidate is True     # 후보이긴 하나 임포트는 사람 승인 필요


def test_analyze_markdown_metrics(tmp_path):
    p = tmp_path / "r.md"
    p.write_text("# EMA Cross\n\nsharpe: 0.7\nreturn: 0.05\n", encoding="utf-8")
    c = analyze_file(str(p))
    assert "sharpe" in c.detected_metrics
    assert c.detected_metrics["sharpe"] == 0.7


def test_analyze_unsupported_returns_none(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("hello", encoding="utf-8")
    assert analyze_file(str(p)) is None


def test_discover_finds_candidates(tmp_path):
    _archive_tree(tmp_path)
    man = discover(["research"], base=str(tmp_path))
    names = {c.detected_strategy for c in man.candidates}
    assert "TSMOM" in names
    assert man.candidate_count >= 4
    assert man.by_confidence.get(CONF_HIGH, 0) >= 1


def test_discover_ranks_high_first(tmp_path):
    _archive_tree(tmp_path)
    man = discover(["research"], base=str(tmp_path))
    assert man.candidates[0].confidence == CONF_HIGH   # 정렬: HIGH 먼저


def test_discovery_is_read_only(tmp_path, monkeypatch):
    # 발견은 아무 원장에도 쓰지 않는다
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda n: str(state / n))
    _archive_tree(tmp_path)
    discover(["research"], base=str(tmp_path))
    assert ledger.read_ingestions() == []
    assert list(state.iterdir()) == []


def test_discover_default_roots_missing_ok(tmp_path):
    # 기본 루트가 없어도 예외 없이 빈 매니페스트
    man = discover(base=str(tmp_path / "empty"))
    assert man.candidate_count == 0


def test_manifest_advisory(tmp_path):
    _archive_tree(tmp_path)
    man = discover(["research"], base=str(tmp_path))
    d = man.to_dict()
    assert d["is_advisory"] is True
    assert d["requires_human_review"] is True


def test_engine_wrapper(tmp_path):
    _archive_tree(tmp_path)
    man = ResearchArchiveDiscovery().discover(["research"], base=str(tmp_path))
    assert man.candidate_count >= 4


def test_bad_file_isolated(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{not valid json", encoding="utf-8")
    c = analyze_file(str(p))
    assert c is not None and c.confidence == "NONE"    # 오류는 격리, 스캔 중단 안 함


# ── 안전 스캔 ──
def test_no_forbidden_imports():
    tree = ast.parse(open(SRC / "archive_discovery.py").read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
           "jarvis.live_trading", "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


def test_no_dangerous_defs():
    tree = ast.parse(open(SRC / "archive_discovery.py").read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


def test_no_model_id_leak():
    assert MODEL_LEAK_TOKEN not in open(SRC / "archive_discovery.py").read().lower()
