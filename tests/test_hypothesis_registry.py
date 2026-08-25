"""가설 레지스트리 유닛테스트."""
from research.hypothesis_registry import HYPOTHESES, registry_list, warmable_runners


def test_warmable_runners_only_include_flagged_entries():
    wr = warmable_runners()
    assert set(wr) == {k for k, v in HYPOTHESES.items() if v["warmable"]}
    assert all(v.startswith("research.run_") for v in wr.values())


def test_registry_list_warmable_first():
    rl = registry_list()
    assert len(rl) == len(HYPOTHESES)
    warmable_flags = [r["warmable"] for r in rl]
    assert warmable_flags == sorted(warmable_flags, reverse=True)


def test_every_entry_has_required_meta():
    for k, v in HYPOTHESES.items():
        assert {"title", "category", "data_source", "validator", "warmable"} <= set(v)
        if v["warmable"]:
            assert v["validator"], f"{k} warmable인데 validator 없음"
