"""Data Connection + Research Capture 테스트 — 기존 provider 재사용, 데이터만 개선.

핵심: 중복 provider 없음 · 8목표(availability/freshness/schema/retry/backfill/gap/lineage/quality) ·
연결 소스는 4차원 노출 · 키 없으면 정직하게 NEEDS_CREDENTIALS · UNKNOWN 감소 · capture 는 기록만(멱등) ·
새 provider/DB/원장 없음 · 실행/포트폴리오 없음.
"""
from __future__ import annotations

import ast
import pathlib

from jarvis.research_workflow import data_connection as dc
from jarvis.research_workflow import ledger as wl
from jarvis.research_workflow import research_capture as rc

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"
_N = "2026-07-29T00:00:00Z"


# ── 기존 provider 재사용(중복 아님) ──
def test_priority_sources_from_existing_catalog():
    from jarvis.research_workflow.providers import PROVIDER_CATALOG
    names = {c["name"] for c in PROVIDER_CATALOG}
    for s in dc.PRIORITY_SOURCES:
        assert s in names, s   # 새로 만들지 않고 카탈로그 재사용


# ── 목표 1: availability — 키 없으면 정직하게 NEEDS_CREDENTIALS ──
def test_availability_honest_credentials():
    krx = dc.availability("KRX")
    assert krx["status"] in ("AVAILABLE", "NEEDS_CREDENTIALS") and krx["requires_credentials"] is True
    edgar = dc.availability("SEC-EDGAR")
    assert edgar["status"] == "PUBLIC_AVAILABLE" and edgar["available"] is True


# ── 목표 2-3: freshness/schema — 데이터 없으면 UNKNOWN(정직) ──
def test_freshness_and_schema():
    assert dc.freshness("KRX", records=None)["status"] == "UNKNOWN"
    fr = dc.freshness("SEC-EDGAR", records=[{"date": "2026-07-28"}], now=_N)
    assert fr["status"] in ("FRESH", "STALE") and fr["known"] is True
    sc = dc.schema_validation("fundamental", [{"symbol": "A", "period": "Q", "metric": "rev", "value": 1}])
    assert sc["valid_pct"] == 100.0 and sc["known"] is True


# ── 목표 4-6: retry / backfill / gap ──
def test_retry_backfill_gap():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return "ok"
    r = dc.with_retry(flaky, attempts=4)
    assert r["ok"] is True and r["attempt"] == 2
    # no connector → 정직한 미연결
    assert dc.backfill("KRX", [1, 2], connector=None)["status"] == "NO_CONNECTOR"
    assert dc.backfill("KRX", [1, 2], connector=lambda b: b)["backfilled"] == 2
    gaps = dc.detect_gaps(["2026-07-01", "2026-07-03"], expected_dates=["2026-07-01", "2026-07-02", "2026-07-03"])
    assert gaps["gap_count"] == 1 and gaps["missing"] == ["2026-07-02"]


# ── 목표 7-8: lineage / quality ──
def test_lineage_and_quality():
    ln = dc.lineage("SEC-EDGAR")
    assert ln["known"] is True and any("consumer:" in c for c in ln["chain"])
    q = dc.quality_score(dc.availability("SEC-EDGAR"),
                         dc.freshness("SEC-EDGAR", records=[{"date": "2026-07-28"}], now=_N),
                         dc.schema_validation("fundamental", [{"symbol": "A", "period": "Q", "metric": "m", "value": 1}]))
    assert 0.0 <= q["quality_score"] <= 1.0 and q["grade"] in ("GOOD", "PARTIAL", "LOW")


# ── 연결 소스는 4차원 모두 노출 + UNKNOWN 감소 ──
def test_connect_source_exposes_four_dimensions():
    conn = dc.connect_source("SEC-EDGAR", raw=[{"symbol": "A", "period": "Q", "metric": "m", "value": 1, "date": "2026-07-28"}], now=_N)
    for dim in ("availability", "freshness", "quality", "lineage"):
        assert dim in conn, dim
    assert conn["is_decision"] is False


def test_unknown_decreases_when_data_flows():
    empty = dc.data_connection_status(now=_N)
    filled = dc.data_connection_status(now=_N, injected={"SEC-EDGAR": [{"symbol": "A", "period": "Q", "metric": "m", "value": 1, "date": "2026-07-28"}]})
    assert filled["dimensions_unknown"] < empty["dimensions_unknown"]   # UNKNOWN 감소
    assert set(empty["objectives"]) == {"availability", "freshness", "schema_validation", "retry",
                                        "backfill", "gap_detection", "lineage", "quality_scoring"}


# ── Research Capture: 기록만, 멱등(중복 skip) ──
def test_capture_preview_no_write():
    r = rc.capture_tracked_research(now=_N, commit=False)
    assert r["committed"] is False and r["is_decision"] is False
    assert r["captured"] >= 0 and "by_family" in r


def test_capture_family_inference():
    assert rc._infer_family("kr_dart_buyback_drift_v1") == "event"
    assert rc._infer_family("futures_tsmom") == "momentum"
    assert rc._infer_family("cross_sectional_funding") == "market_neutral"  # funding carry
    assert rc._infer_family("auto_fac_kr_size_smb") == "factor"
    assert rc._infer_family("weird_unknown_strat") == ""   # → baseline_relative 기본


# ── 새 원장 없음 + 금지 스캔 ──
def test_no_new_ledger():
    assert len(wl.ALL_LEDGERS) == 3


def test_no_forbidden_defs_imports_leak():
    for f in ("data_connection.py", "research_capture.py"):
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
