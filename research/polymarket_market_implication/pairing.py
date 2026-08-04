"""엔티티 공유 + 만기근접 후보쌍 필터 — 순수함수, 저장/네트워크 없음.

entity_tags.tag_markets()가 붙인 "entities" 필드 기준으로 마켓을 묶고,
MATURITY_WINDOW_DAYS 안 드는(만기 비슷한) 쌍만 후보로 남긴다. 만기 차이 큰
방향성 단일다리 쌍은 자본 lock 리스크로 범위 밖 — 매칭만기 헤지형만 다루기로
한 설계 결정(spec §7)."""
from __future__ import annotations

import datetime as dt

MATURITY_WINDOW_DAYS = 14


def group_by_shared_entity(markets: list[dict]) -> dict[str, list[dict]]:
    """entities 필드 기준 엔티티별 그룹핑. 소속 마켓 1개뿐인 엔티티는 제외(비교 대상 없음)."""
    groups: dict[str, list[dict]] = {}
    for m in markets:
        for e in m.get("entities", []):
            groups.setdefault(e, []).append(m)
    return {e: ms for e, ms in groups.items() if len(ms) >= 2}


def candidate_pairs(
    markets: list[dict], maturity_window_days: int = MATURITY_WINDOW_DAYS
) -> list[tuple[dict, dict]]:
    """엔티티 공유 + 만기 차이 maturity_window_days 이내인 서로 다른 마켓 쌍(중복 제거)."""
    groups = group_by_shared_entity(markets)
    seen_keys: set[tuple[str, str]] = set()
    pairs: list[tuple[dict, dict]] = []
    for group_markets in groups.values():
        for i in range(len(group_markets)):
            for j in range(i + 1, len(group_markets)):
                a, b = group_markets[i], group_markets[j]
                if a["condition_id"] == b["condition_id"]:
                    continue
                key = tuple(sorted((a["condition_id"], b["condition_id"])))
                if key in seen_keys:
                    continue
                try:
                    end_a = dt.date.fromisoformat(a["end_date"])
                    end_b = dt.date.fromisoformat(b["end_date"])
                except (ValueError, TypeError):
                    continue
                if abs((end_a - end_b).days) > maturity_window_days:
                    continue
                seen_keys.add(key)
                pairs.append((a, b))
    return pairs
