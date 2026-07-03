"""S1 이벤트 family 확장 — 키워드 필터 predicate + family 스키마 + 배치 편입."""
from __future__ import annotations

from research.data.kr_dart_events import report_matches
from research.scanner.families import FAMILIES

S1_FAMILIES = ["treasury_disposal", "control_change", "asset_transfer", "rights_issue"]


# ── report_matches predicate ──────────────────────────────────
def test_report_matches_include_hit():
    assert report_matches("자기주식처분결정", ["자기주식처분"], ["취득"]) is True


def test_report_matches_exclude_blocks():
    # 취득 공시는 처분 family에서 제외
    assert report_matches("자기주식취득결정", ["자기주식처분"], ["취득"]) is False


def test_report_matches_rights_excludes_bonus():
    assert report_matches("유상증자결정", ["유상증자"], ["무상"]) is True
    assert report_matches("무상증자결정", ["유상증자"], ["무상"]) is False


def test_report_matches_no_include_is_false():
    assert report_matches("배당결정", ["유상증자"], []) is False


# ── FAMILIES 스키마 ───────────────────────────────────────────
def test_s1_families_present():
    for fid in S1_FAMILIES:
        assert fid in FAMILIES, f"{fid} 누락"


def test_s1_families_schema():
    expected = {
        "treasury_disposal": ("bearish", ["자기주식처분"], ["취득"]),
        "control_change": ("bullish", ["최대주주변경", "경영권"], []),
        "asset_transfer": ("research", ["자산양수도", "영업양수도"], []),
        "rights_issue": ("bearish", ["유상증자"], ["무상"]),
    }
    for fid, (direction, kw, ex) in expected.items():
        fam = FAMILIES[fid]
        assert fam["direction"] == direction
        assert fam["keywords"] == kw
        assert fam["exclude"] == ex
        assert fam.get("pblntf_ty") == "B"
        assert fam.get("thesis")
