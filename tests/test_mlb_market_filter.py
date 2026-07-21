from research.mlb_specialist.market_filter import is_mlb_market, mlb_condition_ids


def _mkt(question="", slug="", event_title="", sports=None, cid="c1"):
    return {"question": question, "slug": slug, "event_title": event_title,
            "sports_market_type": sports, "condition_id": cid}


def test_explicit_mlb_keyword():
    assert is_mlb_market(_mkt(question="MLB: Yankees to win the World Series"))


def test_baseball_keyword():
    assert is_mlb_market(_mkt(event_title="Baseball game outcome"))


def test_team_names_with_sports_type_no_conflict():
    assert is_mlb_market(_mkt(question="Dodgers vs Padres", sports="moneyline"))


def test_team_name_without_sports_type_is_not_enough():
    # 스포츠 마켓 표시 없고 명시 키워드도 없으면 팀명만으론 판정 보류(False)
    assert is_mlb_market(_mkt(question="Dodgers vs Padres")) is False


def test_conflicting_league_keyword_blocks_team_overlap():
    # Giants/Cardinals는 NFL과 겹침 — nfl 키워드 있으면 MLB 아님
    assert is_mlb_market(_mkt(question="NY Giants NFL playoff", sports="moneyline")) is False


def test_explicit_mlb_wins_over_conflict_keyword():
    # "mlb" 명시가 있으면 타 리그 키워드 섞여도 MLB로 인정
    assert is_mlb_market(_mkt(question="MLB vs NFL ratings", slug="mlb-x")) is True


def test_nba_market_is_false():
    assert is_mlb_market(_mkt(question="Lakers vs Celtics NBA", sports="moneyline")) is False


def test_non_sports_market_is_false():
    assert is_mlb_market(_mkt(question="Will BTC hit 100k?", slug="crypto-btc")) is False


def test_mlb_condition_ids_filters():
    markets = [
        _mkt(question="MLB Yankees", cid="a"),
        _mkt(question="NBA Lakers", sports="moneyline", cid="b"),
        _mkt(question="Astros vs Rangers", sports="moneyline", cid="c"),
    ]
    assert mlb_condition_ids(markets) == {"a", "c"}
