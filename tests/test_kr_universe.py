from unittest.mock import MagicMock
import kr_universe.client as kru

_SAMPLE_HTML = """<html><body><table>
<tr><th>회사명</th><th>시장구분</th><th>종목코드</th><th>업종</th><th>주요제품</th><th>상장일</th><th>결산월</th><th>대표자명</th><th>홈페이지</th><th>지역</th></tr>
<tr><td>삼성전자</td><td>유가증권</td><td>005930</td><td>전자</td><td>반도체</td><td>1975-06-11</td><td>12월</td><td>이재용</td><td>www.samsung.com</td><td>경기도</td></tr>
<tr><td>삼성SDI</td><td>유가증권</td><td>006400</td><td>화학</td><td>배터리</td><td>1979-06-14</td><td>12월</td><td>최윤호</td><td>www.samsungsdi.com</td><td>경기도</td></tr>
<tr><td>카카오</td><td>코스닥</td><td>35720</td><td>IT</td><td>플랫폼</td><td>2006-01-31</td><td>12월</td><td>홍은택</td><td>www.kakao.com</td><td>제주도</td></tr>
</table></body></html>"""


def _mock_session(html: str = _SAMPLE_HTML) -> MagicMock:
    resp = MagicMock()
    resp.text = html
    resp.raise_for_status = MagicMock()
    session = MagicMock()
    session.get.return_value = resp
    return session


def setup_function():
    kru._cache = []
    kru._cache_ts = 0.0


def test_get_universe_returns_all_stocks():
    universe = kru.get_universe(session=_mock_session())
    assert len(universe) == 3


def test_get_universe_structure():
    universe = kru.get_universe(session=_mock_session())
    assert universe[0] == {"code": "005930", "name": "삼성전자", "market": "유가증권"}


def test_get_universe_zero_pads_short_code():
    universe = kru.get_universe(session=_mock_session())
    kakao = next(u for u in universe if u["name"] == "카카오")
    assert kakao["code"] == "035720"


def test_get_universe_uses_memory_cache():
    kru._cache = [{"code": "999999", "name": "캐시전용", "market": "X"}]
    kru._cache_ts = float("inf")
    universe = kru.get_universe()  # no session arg — must NOT make HTTP call
    assert universe[0]["code"] == "999999"


def test_get_universe_refreshes_stale_cache():
    kru._cache = [{"code": "OLD", "name": "구버전", "market": "X"}]
    kru._cache_ts = 0.0  # stale
    universe = kru.get_universe(session=_mock_session())
    assert len(universe) == 3


def test_search_by_name():
    kru.get_universe(session=_mock_session())
    results = kru.search_universe("삼성")
    assert len(results) == 2
    assert all("삼성" in r["name"] for r in results)


def test_search_by_code():
    kru.get_universe(session=_mock_session())
    results = kru.search_universe("005930")
    assert results[0]["name"] == "삼성전자"


def test_search_empty_query_returns_empty():
    kru._cache = [{"code": "005930", "name": "삼성전자", "market": "유가증권"}]
    kru._cache_ts = float("inf")
    assert kru.search_universe("") == []


def test_search_max_results():
    kru._cache = [{"code": f"{i:06d}", "name": f"종목{i}", "market": "유가증권"} for i in range(50)]
    kru._cache_ts = float("inf")
    results = kru.search_universe("종목", max_results=10)
    assert len(results) == 10
