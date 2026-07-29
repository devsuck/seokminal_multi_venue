"""Consolidation Facades(C1) 테스트 — 계열/멤버/resolve/요약·존재검증·안전. 읽기전용·무손실."""
from __future__ import annotations

import ast
import pathlib

import pytest

from jarvis.facades import models as M
from jarvis.facades.engine import FacadeRegistry

SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


@pytest.fixture()
def reg():
    return FacadeRegistry()   # 실제 트리


# ── 계열 정의 ──
def test_four_families():
    assert set(M.FAMILIES) == {"coordination", "oversight", "observability", "self_improvement"}


def test_family_sizes():
    assert len(M.FAMILIES["coordination"]["members"]) == 9
    assert len(M.FAMILIES["oversight"]["members"]) == 5
    assert len(M.FAMILIES["observability"]["members"]) == 3
    assert len(M.FAMILIES["self_improvement"]["members"]) == 4


def test_representatives_are_members():
    for spec in M.FAMILIES.values():
        assert spec["representative"] in spec["members"]


def test_no_member_in_two_families():
    seen = set()
    for spec in M.FAMILIES.values():
        for m in spec["members"]:
            assert m not in seen, m
            seen.add(m)


# ── 엔진(합성) ──
def test_facade_present_missing():
    reg = FacadeRegistry(module_names=["research_governance", "research_compliance"])
    f = reg.facade("oversight")
    assert set(f.present_members) == {"research_governance", "research_compliance"}
    assert "research_reviewer" in f.missing_members
    assert f.member_count == 2


def test_families_sorted(reg):
    assert reg.families() == sorted(reg.families())


def test_resolve():
    reg = FacadeRegistry(module_names=[])
    assert reg.resolve("research_council") == "coordination"
    assert reg.resolve("research_reviewer") == "oversight"
    assert reg.resolve("research_observatory") == "observability"
    assert reg.resolve("nonexistent") is None


def test_representative_of(reg):
    assert reg.representative_of("coordination") == "research_orchestration"


def test_facade_unknown_raises(reg):
    with pytest.raises(KeyError):
        reg.facade("nonexistent")


# ── 실제 트리(존재 검증) ──
def test_real_members_present(reg):
    # 실제 트리에 계열 멤버 대부분이 존재해야 함
    cov = reg.facade("coordination")
    assert cov.member_count >= 7   # 9개 중 대다수 존재


def test_real_all_facades(reg):
    facs = reg.all_facades()
    assert len(facs) == 4
    for f in facs:
        assert f.reduction.endswith("참조점 1개")


def test_real_summary(reg):
    s = reg.summary()
    assert s["facade_count"] == 4
    assert s["modules_covered"] >= 18   # 21개 선언 중 대다수 존재
    assert "Integration Before Expansion" in s["note"]


def test_real_resolve_roundtrip(reg):
    # 실제 존재하는 멤버는 파사드로 해석돼야
    for f in reg.all_facades():
        for m in f.present_members:
            assert reg.resolve(m) == f.name


# ── 무손실 보증(파사드는 하부 모듈을 import 하지 않음) ──
def test_facades_do_not_import_members():
    # 파사드 소스는 research_* 하부 모듈을 import 하지 않아야(결합 금지)
    for src in ("engine.py", "models.py", "__init__.py", "__main__.py"):
        text = (SRC / src).read_text()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("jarvis.research_"), node.module


# ── 안전 스캔 ──
_SRC_FILES = [str(SRC / f) for f in ("engine.py", "models.py", "__main__.py", "__init__.py")]


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution", "jarvis.live_trading")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_dangerous_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "trade", "deploy", "allocate", "approve")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_model_id_leak(path):
    assert MODEL_LEAK_TOKEN not in open(path).read().lower()


def test_registry_no_execution_methods(reg):
    for m in ("execute", "trade", "deploy", "allocate", "approve"):
        assert not hasattr(reg, m)


# ── CLI ──
def _cli(argv, capsys):
    from jarvis.facades import __main__ as cli
    rc = cli.main(argv)
    return rc, capsys.readouterr().out


def test_cli_list(capsys):
    rc, out = _cli(["list"], capsys)
    assert rc == 0
    assert "coordination" in out


def test_cli_members(capsys):
    rc, out = _cli(["members", "--name", "oversight"], capsys)
    assert rc == 0
    assert "research_governance" in out


def test_cli_resolve(capsys):
    rc, out = _cli(["resolve", "--module", "research_council"], capsys)
    assert rc == 0
    assert "coordination" in out


def test_cli_summary(capsys):
    rc, out = _cli(["summary"], capsys)
    assert rc == 0
    assert "facade_count" in out
