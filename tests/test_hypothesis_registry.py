"""가설 레지스트리 유닛테스트."""
from research.hypothesis_registry import HYPOTHESES, registry_list, warmable_runners


def test_warmable_runners_are_polymarket_two():
    wr = warmable_runners()
    assert set(wr) == {"polymarket_sharp_wallet", "polymarket_whale"}
    assert all(v.startswith("research.run_") for v in wr.values())


def test_registry_list_warmable_first():
    rl = registry_list()
    assert rl[0]["warmable"] and rl[1]["warmable"]
    assert not rl[-1]["warmable"]


def test_every_entry_has_required_meta():
    for k, v in HYPOTHESES.items():
        assert {"title", "category", "data_source", "validator", "warmable"} <= set(v)
        if v["warmable"]:
            assert v["validator"], f"{k} warmable인데 validator 없음"
