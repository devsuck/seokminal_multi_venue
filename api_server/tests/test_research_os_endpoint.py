"""`/console/research-os` 엔드포인트 테스트 — P41~P45 라이브 집계, READ ONLY. HTTP 없이 함수 직접 호출."""
from __future__ import annotations


def test_research_os_shape():
    from api_server.console_api import research_os
    r = research_os()
    assert set(r) >= {"meta", "sections", "audit", "runtime", "assistant", "automation",
                      "capabilities", "disclaimer"}


def test_research_os_meta_live():
    from api_server.console_api import research_os
    m = research_os()["meta"]
    assert m["section_count"] == 4
    assert m["item_count"] == 10
    assert m["module_count"] >= 100          # 실제 트리 규모
    assert m["coverage"] == 1.0
    assert m["digest"].startswith("sha256:")


def test_research_os_sections():
    from api_server.console_api import research_os
    secs = research_os()["sections"]
    assert {s["section"] for s in secs} == {"Research", "Knowledge", "Agents", "System"}
    assert sum(s["moduleCount"] for s in secs) == research_os()["meta"]["module_count"]


def test_research_os_runtime_health():
    from api_server.console_api import research_os
    rt = research_os()["runtime"]
    assert rt["health_status"] in ("OK", "WARN", "FAIL")
    assert rt["module_count"] >= 100


def test_research_os_assistant_advisory():
    from api_server.console_api import research_os
    a = research_os()["assistant"]
    assert a["is_decision"] is False
    assert a["is_advisory"] is True


def test_research_os_capabilities():
    from api_server.console_api import research_os
    caps = research_os()["capabilities"]
    phases = {c["phase"] for c in caps}
    assert phases == {"P41", "P42", "P43", "P44", "P45"}
    for c in caps:
        assert c["metric"]


def test_research_os_read_only_disclaimer():
    from api_server.console_api import research_os
    d = research_os()["disclaimer"]
    assert "READ ONLY" in d
    assert "workflow assistance" in d.lower()


def test_research_os_dependency_graph():
    from api_server.console_api import research_os
    g = research_os()["graph"]
    ids = {n["id"] for n in g["nodes"]}
    assert ids == {"Research", "Knowledge", "Agents", "System"}
    assert g["edge_total"] >= 1
    for e in g["edges"]:
        assert e["source"] in ids and e["target"] in ids
        assert e["source"] != e["target"]      # 자기 루프는 node.internal 로 표현
        assert e["weight"] >= 1


def test_research_os_drilldown_modules():
    from api_server.console_api import research_os
    secs = research_os()["sections"]
    total = 0
    for s in secs:
        for it in s["items"]:
            assert isinstance(it["modules"], list)
            total += len(it["modules"])
    assert total == research_os()["meta"]["module_count"]


def test_research_os_module_edges():
    from api_server.console_api import research_os
    g = research_os()["graph"]
    assert "module_edges" in g
    assert len(g["module_edges"]) == g["edge_total"]
    for e in g["module_edges"]:
        assert {"source", "target", "sourceSection", "targetSection"} <= set(e)


def test_assistant_endpoint_idle():
    from api_server.console_api import assistant
    r = assistant("")
    assert r["intent"] == "idle"
    assert len(r["suggestions"]) == 5


def test_assistant_endpoint_query():
    from api_server.console_api import assistant
    r = assistant("Have we tried momentum?")
    assert r["intent"] in ("recall", "overview")
    assert r["is_decision"] is False
    assert "suggestions" in r


def test_research_os_workspaces():
    from api_server.console_api import research_os
    ws = research_os()["workspaces"]
    names = [w["workspace"] for w in ws]
    assert names == ["Home", "Research", "Experiments", "Knowledge", "Assistant", "System"]


def test_failure_intel_endpoint():
    from api_server.console_api import failure_intel
    r = failure_intel("momentum")
    assert "failure_intelligence" in r and "memory_graph" in r
    assert r["is_decision"] is False
    assert [l["lens"] for l in r["perspectives"]["lenses"]] == \
        ["Quant", "Risk", "Macro", "Supply", "News", "Critic"]


def test_failure_intel_endpoint_no_q():
    from api_server.console_api import failure_intel
    r = failure_intel("")
    assert "failure_intelligence" in r
    assert "perspectives" not in r
