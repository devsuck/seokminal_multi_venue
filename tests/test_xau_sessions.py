"""XAU 세션 판정 유닛테스트 — NY 로컬시각 창 + DST 경계."""
from datetime import datetime
from zoneinfo import ZoneInfo

from research.xau_session.sessions import (
    NY_TZ,
    in_session,
    is_session_end,
    is_session_start,
)


def _ts(y, mo, d, h, mi, tz=NY_TZ) -> float:
    """NY 로컬 (y,mo,d,h,mi) → UTC epoch 초."""
    return datetime(y, mo, d, h, mi, tzinfo=tz).timestamp()


# ── 세션 포함/제외 ───────────────────────────────────────────────
def test_ny_session_inclusive_start_exclusive_end():
    assert in_session(_ts(2026, 1, 15, 8, 0), "ny")       # 시작봉 포함
    assert in_session(_ts(2026, 1, 15, 15, 45), "ny")
    assert not in_session(_ts(2026, 1, 15, 16, 0), "ny")  # 종료봉 제외
    assert not in_session(_ts(2026, 1, 15, 7, 45), "ny")


def test_london_half_hour_end():
    assert in_session(_ts(2026, 1, 15, 11, 15), "london")
    assert not in_session(_ts(2026, 1, 15, 11, 30), "london")  # 11:30 종료 제외
    assert in_session(_ts(2026, 1, 15, 2, 0), "london")


# ── 자정 넘는 Asian (19:00 → 익일 03:00) ─────────────────────────
def test_asian_wraps_midnight():
    assert in_session(_ts(2026, 1, 15, 19, 0), "asian")    # 시작
    assert in_session(_ts(2026, 1, 15, 23, 30), "asian")   # 자정 전
    assert in_session(_ts(2026, 1, 16, 0, 30), "asian")    # 자정 후
    assert in_session(_ts(2026, 1, 16, 2, 45), "asian")    # 종료 직전
    assert not in_session(_ts(2026, 1, 16, 3, 0), "asian") # 03:00 종료 제외
    assert not in_session(_ts(2026, 1, 15, 18, 45), "asian")
    assert not in_session(_ts(2026, 1, 16, 12, 0), "asian")


# ── DST: 여름(EDT, UTC-4)에도 NY 로컬 창이 동일하게 유지 ─────────
def test_dst_summer_ny_local_window_holds():
    # 7월(EDT): NY 08:00 = UTC 12:00. 세션 판정은 NY 로컬 기준이라 변함없어야.
    assert in_session(_ts(2026, 7, 15, 8, 0), "ny")
    assert not in_session(_ts(2026, 7, 15, 16, 0), "ny")
    # 같은 UTC 순간이라도 겨울/여름 NY 로컬이 다르므로 epoch로 교차확인
    summer = datetime(2026, 7, 15, 8, 0, tzinfo=NY_TZ)
    assert summer.utcoffset().total_seconds() == -4 * 3600
    winter = datetime(2026, 1, 15, 8, 0, tzinfo=NY_TZ)
    assert winter.utcoffset().total_seconds() == -5 * 3600


def test_dst_spring_forward_day():
    # 2026-03-08 02:00 로컬은 존재하지 않음(2→3시 점프). 그 전후 세션 판정이 깨지지 않아야.
    # London 02:00 시작인데 그날 02:00이 스킵됨 → 02:30(=EDT 03:30 상당) 로컬은 세션 안.
    assert in_session(_ts(2026, 3, 8, 3, 0), "london")
    assert not in_session(_ts(2026, 3, 8, 1, 30), "london")


# ── 세션 시작/종료 엣지 감지 ──────────────────────────────────────
def test_session_start_edge():
    prev = _ts(2026, 1, 15, 7, 45)
    cur = _ts(2026, 1, 15, 8, 0)
    assert is_session_start(prev, cur, "ny")
    assert not is_session_start(cur, _ts(2026, 1, 15, 8, 15), "ny")  # 이미 안


def test_session_start_first_bar_none_prev():
    assert is_session_start(None, _ts(2026, 1, 15, 8, 0), "ny")
    assert not is_session_start(None, _ts(2026, 1, 15, 7, 0), "ny")


def test_session_end_edge_triggers_on_exit_bar():
    # 아시안 종료: 02:45 안 → 03:00 밖. 03:00 봉에서 종료 감지.
    prev = _ts(2026, 1, 16, 2, 45)
    cur = _ts(2026, 1, 16, 3, 0)
    assert is_session_end(prev, cur, "asian")
    assert not is_session_end(None, cur, "asian")
    assert not is_session_end(prev, _ts(2026, 1, 16, 2, 50), "asian")  # 아직 안
