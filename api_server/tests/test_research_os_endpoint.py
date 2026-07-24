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
