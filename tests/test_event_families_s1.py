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


def test_report_matches_conflict_exclude_wins():
    # include·exclude 둘 다 포함되면 exclude 우선(제외) — 동결 필터 무결성
    assert report_matches("자기주식처분 및 자기주식취득 정정신고", ["자기주식처분"], ["취득"]) is False


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


# ── 배치 편입 (engine) ────────────────────────────────────────
def test_new_families_enter_batch_when_powered(monkeypatch):
    import research.autoresearch.engine as eng
    # 모든 family에 이벤트 100건 있는 것처럼 → 전부 실행 가능 Candidate
    monkeypatch.setattr(eng, "load_events", lambda fid: [{}] * 100)
    cands = eng._event_family_candidates({"X": {}})
    cids = {c.cid for c in cands}
    for fid in S1_FAMILIES:
        assert f"ev_{fid}" in cids, f"ev_{fid} 배치 미편입"
        c = next(c for c in cands if c.cid == f"ev_{fid}")
        assert not c.meta.get("underpowered")


def test_new_families_underpowered_when_no_data(monkeypatch):
    import research.autoresearch.engine as eng
    monkeypatch.setattr(eng, "load_events", lambda fid: [])   # 커버리지 0
    cands = eng._event_family_candidates({"X": {}})
    for fid in S1_FAMILIES:
        c = next(c for c in cands if c.cid == f"ev_{fid}")
        assert c.meta.get("underpowered") is True
