import json
import pytest
from fastapi.testclient import TestClient
from api_server.main import app

client = TestClient(app)

# ── /spawner/validate ──────────────────────────────────────────────────────────

def test_validate_valid_rule_returns_true():
    rules = [
        {
            "condition": {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {
                            "indicator": "RSI",
                            "bar_type": "AAPL.NASDAQ-1-DAY-LAST-EXTERNAL",
                            "params": {"period": 14},
                        },
                        "op": "<",
                        "right": {"value": 30},
                    }
                ],
            }
        }
    ]
    r = client.get("/spawner/validate", params={"spawn_rules": json.dumps(rules)})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["errors"] == []
    assert len(body["rules"]) == 1
    info = body["rules"][0]
    assert info["rule_index"] == 0
    assert info["combinator"] == "AND"
    assert info["condition_count"] == 1
    assert "RSI" in info["indicators"]


def test_validate_invalid_json_returns_422():
    r = client.get("/spawner/validate", params={"spawn_rules": "not json"})
    assert r.status_code == 422


def test_validate_unknown_indicator_returns_errors():
    rules = [
        {
            "condition": {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {"indicator": "NOPE", "bar_type": "AAPL.NASDAQ-1-DAY-LAST-EXTERNAL", "params": {}},
                        "op": "<",
                        "right": {"value": 30},
                    }
                ],
            }
        }
    ]
    r = client.get("/spawner/validate", params={"spawn_rules": json.dumps(rules)})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert len(body["errors"]) == 1
    assert body["errors"][0]["rule_index"] == 0


def test_validate_missing_rsi_period_returns_errors():
    rules = [
        {
            "condition": {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {"indicator": "RSI", "bar_type": "AAPL.NASDAQ-1-DAY-LAST-EXTERNAL", "params": {}},
                        "op": "<",
                        "right": {"value": 30},
                    }
                ],
            }
        }
    ]
    r = client.get("/spawner/validate", params={"spawn_rules": json.dumps(rules)})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert body["errors"][0]["rule_index"] == 0


def test_validate_empty_rules_returns_valid():
    r = client.get("/spawner/validate", params={"spawn_rules": json.dumps([])})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["rules"] == []
    assert body["errors"] == []


# ── /spawner/evaluate ─────────────────────────────────────────────────────────

def _never_true_rules():
    return [
        {
            "condition": {
                "combinator": "AND",
                "conditions": [
                    {"left": {"value": 1}, "op": ">", "right": {"value": 2}}
                ],
            }
        }
    ]


def test_evaluate_returns_response_structure():
    r = client.post(
        "/spawner/evaluate",
        json={
            "spawn_rules": _never_true_rules(),
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"instrument_id", "start", "end", "bar_count", "trigger_events"}
    assert body["instrument_id"] == "AAPL.NASDAQ"
    assert body["bar_count"] > 0


def test_evaluate_never_true_condition_returns_empty_triggers():
    r = client.post(
        "/spawner/evaluate",
        json={
            "spawn_rules": _never_true_rules(),
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert r.status_code == 200
    assert r.json()["trigger_events"] == []


def test_evaluate_unknown_instrument_returns_400():
    r = client.post(
        "/spawner/evaluate",
        json={
            "spawn_rules": _never_true_rules(),
            "instrument_id": "NOPE.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert r.status_code == 400


def test_evaluate_invalid_condition_returns_422():
    r = client.post(
        "/spawner/evaluate",
        json={
            "spawn_rules": [{"condition": {"combinator": "BAD", "conditions": []}}],
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert r.status_code == 422


def test_evaluate_trigger_date_format():
    """RSI < 100 (always true once initialized) should produce a trigger event with YYYY-MM-DD date."""
    rules = [
        {
            "condition": {
                "combinator": "AND",
                "conditions": [
                    {
                        "left": {
                            "indicator": "RSI",
                            "bar_type": "AAPL.NASDAQ-1-DAY-LAST-EXTERNAL",
                            "params": {"period": 2},
                        },
                        "op": "<",
                        "right": {"value": 100},
                    }
                ],
            }
        }
    ]
    r = client.post(
        "/spawner/evaluate",
        json={
            "spawn_rules": rules,
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["trigger_events"]) == 1
    ev = body["trigger_events"][0]
    assert ev["rule_index"] == 0
    # Date must be YYYY-MM-DD
    import re
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", ev["trigger_date"])
