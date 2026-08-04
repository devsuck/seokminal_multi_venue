from research.polymarket_market_implication import pairing


def _market(cid, question, end_date, entities):
    return {"condition_id": cid, "question": question, "end_date": end_date, "entities": entities}


def test_group_by_shared_entity_groups_and_drops_singletons():
    m1 = _market("c1", "Q1", "2026-09-01", ["X"])
    m2 = _market("c2", "Q2", "2026-09-05", ["X"])
    m3 = _market("c3", "Q3", "2026-09-10", ["Y"])
    groups = pairing.group_by_shared_entity([m1, m2, m3])
    assert list(groups.keys()) == ["X"]
    assert groups["X"] == [m1, m2]


def test_candidate_pairs_within_maturity_window_included():
    m1 = _market("c1", "Q1", "2026-09-01", ["X"])
    m2 = _market("c2", "Q2", "2026-09-14", ["X"])  # 13일 차이 (<14)
    pairs = pairing.candidate_pairs([m1, m2])
    assert pairs == [(m1, m2)]


def test_candidate_pairs_at_exact_boundary_included():
    m1 = _market("c1", "Q1", "2026-09-01", ["X"])
    m2 = _market("c2", "Q2", "2026-09-15", ["X"])  # 정확히 14일 차이 (==window, 포함)
    pairs = pairing.candidate_pairs([m1, m2], maturity_window_days=14)
    assert pairs == [(m1, m2)]


def test_candidate_pairs_outside_maturity_window_excluded():
    m1 = _market("c1", "Q1", "2026-09-01", ["X"])
    m2 = _market("c2", "Q2", "2026-09-16", ["X"])  # 15일 차이 (>window, 제외)
    pairs = pairing.candidate_pairs([m1, m2], maturity_window_days=14)
    assert pairs == []


def test_candidate_pairs_excludes_self_pair():
    m1 = _market("c1", "Q1", "2026-09-01", ["X"])
    pairs = pairing.candidate_pairs([m1, m1])
    assert pairs == []


def test_candidate_pairs_dedupes_across_multiple_shared_entities():
    m1 = _market("c1", "Q1", "2026-09-01", ["X", "Z"])
    m2 = _market("c2", "Q2", "2026-09-05", ["X", "Z"])
    pairs = pairing.candidate_pairs([m1, m2])
    assert pairs == [(m1, m2)]  # X그룹·Z그룹 양쪽에 다 걸려도 쌍은 1번만
