"""P15 threat_model 테스트 — 리스크 점수·매트릭스·모델 완전성·결정성·마크다운·보안."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.threat_model import model as TM
from jarvis.threat_model.model import (
    CRITICAL,
    HIGH,
    LOW,
    MEDIUM,
    build_threat_model,
    filter_by_severity,
    residual_risks,
    risk_matrix,
    risk_score,
    severity_of,
    threats,
    to_markdown,
)


# ═══════════════ risk_score / severity ═══════════════
@pytest.mark.parametrize("lk,im,score", [(1, 1, 1), (2, 3, 6), (5, 5, 25), (3, 4, 12)])
def test_risk_score(lk, im, score):
    assert risk_score(lk, im) == score


def test_risk_score_clamps():
    assert risk_score(9, 9) == 25
    assert risk_score(0, 0) == 1


@pytest.mark.parametrize("score,sev", [
    (1, LOW), (3, LOW), (4, MEDIUM), (8, MEDIUM), (9, HIGH), (14, HIGH),
    (15, CRITICAL), (25, CRITICAL)])
def test_severity_of(score, sev):
    assert severity_of(score) == sev


# ═══════════════ threats ═══════════════
def test_threats_nonempty():
    assert len(threats()) >= 5


def test_threats_sorted_by_score_desc():
    scores = [t.score for t in threats()]
    assert scores == sorted(scores, reverse=True)


def test_threats_have_mitigations():
    assert all(len(t.mitigations) >= 1 for t in threats())


def test_threats_have_residual():
    assert all(t.residual for t in threats())


def test_threat_score_matches():
    for t in threats():
        assert t.score == risk_score(t.likelihood, t.impact)
        assert t.severity == severity_of(t.score)


def test_threat_frozen():
    t = threats()[0]
    with pytest.raises(Exception):
        t.score = 0


def test_threats_deterministic():
    a = [t.to_dict() for t in threats()]
    b = [t.to_dict() for t in threats()]
    assert a == b


# ═══════════════ risk_matrix ═══════════════
def test_risk_matrix_count():
    m = risk_matrix()
    assert m["count"] == len(threats())


def test_risk_matrix_by_severity():
    m = risk_matrix()
    assert sum(m["by_severity"].values()) == m["count"]


def test_risk_matrix_max_score():
    m = risk_matrix()
    assert m["max_score"] == max(t["score"] for t in m["threats"])


def test_risk_matrix_deterministic():
    assert risk_matrix() == risk_matrix()


# ═══════════════ build_threat_model ═══════════════
def test_model_has_all_sections():
    m = build_threat_model()
    for key in ("assets", "trust_boundaries", "attack_surfaces", "threat_actors",
                "risk_matrix", "mitigations", "residual_risks"):
        assert key in m


def test_model_assets_nonempty():
    assert len(build_threat_model()["assets"]) >= 3


def test_model_trust_boundaries():
    assert len(build_threat_model()["trust_boundaries"]) >= 3


def test_model_attack_surfaces():
    assert len(build_threat_model()["attack_surfaces"]) >= 4


def test_model_threat_actors():
    assert len(build_threat_model()["threat_actors"]) >= 3


def test_model_deterministic():
    assert build_threat_model() == build_threat_model()


def test_model_timestamp_independent():
    a = build_threat_model(generated_at="2026-01-01")
    b = build_threat_model(generated_at="2026-12-31")
    del a["generated_at"]
    del b["generated_at"]
    assert a == b


def test_model_mitigations_per_threat():
    m = build_threat_model()
    for t in m["risk_matrix"]["threats"]:
        assert t["id"] in m["mitigations"]


def test_model_counts():
    m = build_threat_model()
    assert m["asset_count"] == len(m["assets"])
    assert m["threat_count"] == m["risk_matrix"]["count"]


def test_model_scope_no_execution():
    m = build_threat_model()
    assert "거래" in m["scope"] or "집행" in m["scope"]


# ═══════════════ residual / filter ═══════════════
def test_residual_risks():
    rr = residual_risks()
    assert len(rr) == len(threats())
    assert all("residual" in r for r in rr)


def test_filter_by_severity():
    for sev in (LOW, MEDIUM, HIGH, CRITICAL):
        filtered = filter_by_severity(sev)
        assert all(t["severity"] == sev for t in filtered)


def test_filter_matches_matrix():
    total = sum(len(filter_by_severity(s)) for s in (LOW, MEDIUM, HIGH, CRITICAL))
    assert total == len(threats())


# ═══════════════ markdown ═══════════════
def test_markdown_contains_sections():
    md = to_markdown()
    assert "## Assets" in md
    assert "## Risk Matrix" in md
    assert "## Residual Risks" in md


def test_markdown_deterministic():
    assert to_markdown() == to_markdown()


def test_markdown_has_title():
    assert to_markdown().startswith("# ")


# ═══════════════ 보안 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN = ("jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
              "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order")


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN), node.module


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()
