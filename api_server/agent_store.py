"""SQLite-backed store for AI trading agents and their structured cycle logs.

The shell agent loop talks to the backend over HTTP (as it already does for
Alpaca), so the backend is the single source of truth for agent definitions
and per-cycle records. Cycles are structured rows — not raw stdout — so the
frontend can render compact cards instead of dumping a terminal pane.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import uuid
from pathlib import Path

# Known agent types and their default cadence/universe/gate profile. Profiles
# are data, not code, so a new strategy is a new row rather than a new branch.
AGENT_PROFILES: dict[str, dict] = {
    "condition_lv1": {
        # Lv1 — 백테스트 조건식 그대로 페이퍼 (자연어→조건식 변환 후 승격). daily bar 기반.
        "label": "조건식 (Lv1)",
        "cadence_seconds": 24 * 3600,
        "position_pct": 0.10,
        "force_eod_close": False,
        "paper": True,
        "autonomy": 1,
    },
    "option_lv1": {
        # Lv1 — 백테스트 조건식으로 검증한 기초자산 신호를 옵션 계약(콜/풋) 매수/청산으로 실행.
        # condition_lv1과 게이트+EMA 판단 로직은 동일, 체결만 옵션(IB, 항상 paper)으로 나감.
        "label": "옵션 조건식 (Lv1)",
        "cadence_seconds": 24 * 3600,
        "force_eod_close": False,
        "paper": True,
        "autonomy": 1,
        "venue": "US",  # 옵션은 항상 IB
    },
    "swing": {
        "label": "스윙",
        "cadence_seconds": 8 * 3600,
        "universe_size": 10,
        "buy_score_threshold": 18,  # of 40
        "force_eod_close": False,
    },
    "longterm": {
        # 장기투자 — 스윙과 동일 실행 경로, 주기만 길게(주 단위 점검).
        "label": "장투",
        "cadence_seconds": 7 * 24 * 3600,
        "universe_size": 15,
        "buy_score_threshold": 16,  # of 40
        "force_eod_close": False,
    },
    "daytrade": {
        "label": "데이트레이딩",
        "cadence_seconds": 5 * 60,
        "universe_size": 15,
        "buy_score_threshold": 22,
        "force_eod_close": True,
        "tp_pct": 0.04,
        "sl_pct": 0.02,
        "lv5_agentic": True,  # autonomy≥3(신규 Lv3=구Lv5): Claude CLI 에이전틱 자가학습 루프 활성
    },
    "kr_daytrade": {
        "label": "데이트레이딩 (한국주식)",
        "venue": "KR",
        "cadence_seconds": 5 * 60,
        "buy_score_threshold": 55,
        "position_pct": 0.10,
        "force_eod_close": True,
        "paper": True,
        "tp_pct": 0.03,
        "sl_pct": 0.02,
        "lv5_agentic": True,
    },
    "hl_daytrade": {
        "label": "데이트레이딩 (Hyperliquid 무기한)",
        "venue": "HL",
        "cadence_seconds": 5 * 60,
        "buy_score_threshold": 55,
        "leverage": 3,
        "position_pct": 0.10,
        "force_eod_close": False,
        "paper": True,
        "tp_pct": 0.05,
        "sl_pct": 0.03,
        "lv5_agentic": True,
    },
    "autonomous": {
        # Lv3(구Lv5) 자율형 학습 AI — 뉴스·공시·전 기능을 활용해 스스로 전략을 생성·학습.
        # 항상 paper로 시작 — God Mode 승급(3조건 심사+사람 확인) 전까진 실 집행 없음.
        "label": "자율형 학습 AI",
        "cadence_seconds": 4 * 3600,      # 4시간 주기 탐색·재학습
        "universe_size": 30,
        "buy_score_threshold": 60,
        "force_eod_close": False,
        "paper": True,
        "autonomy": 3,
        "use_news": True,            # 시장 뉴스 피드 활성화
        "use_disclosures": True,     # KR+US 공시 분석
        "use_ml_self_learn": True,   # 자체 ML 전략 생성·검증 루프
        "venue": "US",
    },
    "kr_macro": {
        # Lv3(구Lv5) KR 거시 전략 AI — 한국 정부 정책·거시 데이터 분석.
        # Situation → Impact → Portfolio 3단계 방법론.
        "label": "KR 거시 전략 AI",
        "cadence_seconds": 24 * 3600,     # 1일 주기 거시 리뷰
        "universe_size": 20,
        "buy_score_threshold": 55,
        "force_eod_close": False,
        "paper": True,
        "autonomy": 3,
        "venue": "KR",
        "use_news": True,
        "use_disclosures": True,
        "methodology": "situation_impact_portfolio",  # KR macro 3단계
        "focus": ["AI_basic_act", "low_birth_rate", "semiconductor_infra", "geopolitics"],
        "human_in_loop": True,       # 최종 투자는 사람 결정 명시
    },
}

_VALID_DECISIONS = {"WATCH", "BUY", "SELL", "SKIP", "HOLD"}


def _db_path() -> Path:
    return Path(os.environ.get("AGENT_DB_PATH", "data/agents.db"))


def _conn() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        account_alloc REAL NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        cycle INTEGER NOT NULL,
        ts TEXT NOT NULL,
        payload TEXT NOT NULL
    )""")
    # Migrations for older DBs.
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(agents)")}
    if "paper" not in cols:
        conn.execute("ALTER TABLE agents ADD COLUMN paper INTEGER NOT NULL DEFAULT 1")
    if "autonomy" not in cols:
        # 1=fixed rules, 2=AI strategist (backtest-validated), 3=full autonomy
        conn.execute("ALTER TABLE agents ADD COLUMN autonomy INTEGER NOT NULL DEFAULT 2")
    if "market" not in cols:
        # US | KR | MIXED — market scope for swing agents (others ignore it)
        conn.execute("ALTER TABLE agents ADD COLUMN market TEXT NOT NULL DEFAULT 'US'")
    if "protected" not in cols:
        # 잠금: 삭제 시 이름 타이핑 확인 요구 (실수 삭제 방지)
        conn.execute("ALTER TABLE agents ADD COLUMN protected INTEGER NOT NULL DEFAULT 0")
    if "god_mode" not in cols:
        # God Mode 승급 여부. 생성 시 설정 불가 — Lv3(자가학습) 에이전트가 최근 30일 3조건
        # 심사(api_server/god_mode.py)를 통과하고 사람이 확인 클릭해야만 promote_to_god_mode()가
        # 세팅. 1이면 jarvis.execution.agent_gate.enforce_paper가 이 에이전트만 live 허용.
        conn.execute("ALTER TABLE agents ADD COLUMN god_mode INTEGER NOT NULL DEFAULT 0")
    if "condition_json" not in cols:
        # Lv1(조건식 페이퍼): 백테스트에서 검증한 조건식(buildSpawnRules 포맷의 rule 1개) 그대로.
        conn.execute("ALTER TABLE agents ADD COLUMN condition_json TEXT")
    if "instrument_id" not in cols:
        conn.execute("ALTER TABLE agents ADD COLUMN instrument_id TEXT")
    if "spawned" not in cols:
        # 조건이 한 번 True가 된 후에는 계속 EMA fast/slow 크로스로 진입/청산 (EMACrossFlat과 동일 의미론).
        conn.execute("ALTER TABLE agents ADD COLUMN spawned INTEGER NOT NULL DEFAULT 0")
    if "position_state" not in cols:
        conn.execute("ALTER TABLE agents ADD COLUMN position_state TEXT NOT NULL DEFAULT 'FLAT'")
    if "option_expiry" not in cols:
        # option_lv1 전용: 기초자산 신호로 매매할 옵션 계약 스펙 (YYYYMMDD/행사가/C·P/계약수).
        conn.execute("ALTER TABLE agents ADD COLUMN option_expiry TEXT")
    if "option_strike" not in cols:
        conn.execute("ALTER TABLE agents ADD COLUMN option_strike REAL")
    if "option_right" not in cols:
        conn.execute("ALTER TABLE agents ADD COLUMN option_right TEXT")
    if "option_contracts" not in cols:
        conn.execute("ALTER TABLE agents ADD COLUMN option_contracts INTEGER NOT NULL DEFAULT 1")
    conn.commit()
    return conn


# ── Agents ────────────────────────────────────────────────────────────────────

def create_agent(name: str, agent_type: str, account_alloc: float,
                 paper: bool = True, autonomy: int = 2, market: str = "US",
                 condition: dict | None = None,
                 instrument_id: str | None = None,
                 option: dict | None = None) -> dict:
    """autonomy: 1=조건식(Lv1, 백테스트 승격 전용) / 2=AI 전략가(구Lv2·3·4 통합) /
    3=자가학습(구Lv5). God Mode는 생성 시 지정 불가 — promote_to_god_mode() 참고.

    option: agent_type="option_lv1" 전용 — {"expiry": "YYYYMMDD", "strike": float,
    "right": "C"|"P", "contracts": int}. 기초자산 조건식 신호를 옵션 계약 매매로 실행."""
    if agent_type not in AGENT_PROFILES:
        raise ValueError(f"unknown agent type: {agent_type!r}")
    if autonomy not in (1, 2, 3):
        raise ValueError(f"autonomy must be 1, 2, or 3, got {autonomy}")
    if market not in ("US", "KR", "MIXED"):
        raise ValueError(f"market must be US, KR, or MIXED, got {market!r}")
    # Lv1(조건식): 백테스트 승격 플로우 전용 — 조건식+종목 둘 다 있거나 둘 다 없어야 함.
    if bool(condition) != bool(instrument_id):
        raise ValueError("condition과 instrument_id는 함께 지정해야 함")
    if autonomy == 1 and not condition:
        raise ValueError("autonomy=1은 condition/instrument_id 필수 (백테스트에서 승격)")
    if agent_type == "option_lv1" and not option:
        raise ValueError("option_lv1은 option(expiry/strike/right/contracts) 필수")
    if option and agent_type != "option_lv1":
        raise ValueError("option은 option_lv1 전용")
    option_expiry = option_strike = option_right = None
    option_contracts = 1
    if option:
        option_expiry = str(option.get("expiry") or "")
        option_strike = float(option.get("strike", 0))
        option_right = str(option.get("right") or "")
        option_contracts = int(option.get("contracts", 1))
        if not (len(option_expiry) == 8 and option_expiry.isdigit()):
            raise ValueError(f"option.expiry는 YYYYMMDD 형식이어야 함: {option_expiry!r}")
        if option_strike <= 0:
            raise ValueError(f"option.strike는 0보다 커야 함: {option_strike!r}")
        if option_right not in ("C", "P"):
            raise ValueError(f"option.right는 'C' 또는 'P'여야 함: {option_right!r}")
        if option_contracts < 1:
            raise ValueError(f"option.contracts는 1 이상이어야 함: {option_contracts!r}")
    agent = {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "type": agent_type,
        "account_alloc": float(account_alloc),
        "status": "stopped",
        "paper": bool(paper),
        "autonomy": int(autonomy),
        "market": market,
        "god_mode": False,
        "condition_json": json.dumps(condition, ensure_ascii=False) if condition else None,
        "instrument_id": instrument_id,
        "spawned": False,
        "position_state": "FLAT",
        "option_expiry": option_expiry,
        "option_strike": option_strike,
        "option_right": option_right,
        "option_contracts": option_contracts,
        "created_at": _dt.datetime.now(_dt.UTC).isoformat(),
    }
    conn = _conn()
    conn.execute(
        "INSERT INTO agents (id,name,type,account_alloc,status,paper,autonomy,market,"
        "condition_json,instrument_id,option_expiry,option_strike,option_right,"
        "option_contracts,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (agent["id"], agent["name"], agent["type"], agent["account_alloc"],
         agent["status"], 1 if paper else 0, int(autonomy), market,
         agent["condition_json"], agent["instrument_id"],
         agent["option_expiry"], agent["option_strike"], agent["option_right"],
         agent["option_contracts"], agent["created_at"]),
    )
    conn.commit()
    conn.close()
    return _with_profile(agent)


def promote_to_god_mode(agent_id: str) -> dict:
    """Lv3(자가학습) 에이전트를 God Mode로 승급 — paper→live 전환.

    호출 전 god_mode.evaluate(agent_id)의 3조건이 모두 통과했어야 하고, 그래도
    사람이 최종 확인 클릭을 거쳐야 한다(자동 승급 없음) — 이 함수 자체는 심사를
    하지 않으므로 router가 반드시 evaluate() 재검증 후에만 호출해야 한다.
    """
    agent = get_agent(agent_id)
    if agent is None:
        raise ValueError("agent not found")
    if int(agent.get("autonomy", 0)) != 3:
        raise ValueError("God Mode 승급은 Lv3(자가학습) 에이전트만 가능")
    if agent.get("god_mode"):
        return agent
    conn = _conn()
    conn.execute("UPDATE agents SET god_mode=1, paper=0 WHERE id=?", (agent_id,))
    conn.commit()
    conn.close()
    return get_agent(agent_id)


def set_condition_state(agent_id: str, spawned: bool | None = None,
                        position_state: str | None = None) -> dict | None:
    """Lv1 tick 후 spawned/position_state 갱신 (조건 최초 충족 여부, 현재 포지션)."""
    if position_state is not None and position_state not in ("FLAT", "LONG"):
        raise ValueError(f"invalid position_state: {position_state!r}")
    sets, params = [], []
    if spawned is not None:
        sets.append("spawned=?"); params.append(1 if spawned else 0)
    if position_state is not None:
        sets.append("position_state=?"); params.append(position_state)
    if not sets:
        return get_agent(agent_id)
    params.append(agent_id)
    conn = _conn()
    cur = conn.execute(f"UPDATE agents SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return get_agent(agent_id) if changed else None


def list_agents() -> list[dict]:
    conn = _conn()
    rows = conn.execute("SELECT * FROM agents ORDER BY created_at").fetchall()
    conn.close()
    return [_with_profile(dict(r)) for r in rows]


def get_agent(agent_id: str) -> dict | None:
    conn = _conn()
    row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    conn.close()
    return _with_profile(dict(row)) if row else None


def set_status(agent_id: str, status: str) -> dict | None:
    if status not in ("running", "stopped"):
        raise ValueError(f"invalid status: {status!r}")
    conn = _conn()
    cur = conn.execute("UPDATE agents SET status=? WHERE id=?", (status, agent_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return get_agent(agent_id) if changed else None


def delete_agent(agent_id: str) -> bool:
    conn = _conn()
    cur = conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    conn.execute("DELETE FROM cycles WHERE agent_id=?", (agent_id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return bool(deleted)


def set_protected(agent_id: str, protected: bool) -> dict | None:
    conn = _conn()
    cur = conn.execute("UPDATE agents SET protected=? WHERE id=?", (1 if protected else 0, agent_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return get_agent(agent_id) if changed else None


def _with_profile(agent: dict) -> dict:
    agent["profile"] = AGENT_PROFILES.get(agent["type"], {})
    if "paper" in agent:  # SQLite stores 0/1 → expose as bool
        agent["paper"] = bool(agent["paper"])
    if "protected" in agent:
        agent["protected"] = bool(agent["protected"])
    if "spawned" in agent:
        agent["spawned"] = bool(agent["spawned"])
    if "god_mode" in agent:
        agent["god_mode"] = bool(agent["god_mode"])
    return agent


# ── Cycles ──────────────────────────────────────────────────────────────────

def record_cycle(agent_id: str, payload: dict) -> dict:
    """Persist one structured cycle. Validates the decision enum; stores the
    rest as a JSON payload so the schema can evolve without migrations."""
    decision = payload.get("decision")
    if decision not in _VALID_DECISIONS:
        raise ValueError(f"invalid decision: {decision!r} (expected {_VALID_DECISIONS})")
    entry = {
        "agent_id": agent_id,
        "cycle": int(payload.get("cycle", 0)),
        "ts": payload.get("ts") or _dt.datetime.now(_dt.UTC).isoformat(),
        **payload,
    }
    conn = _conn()
    conn.execute(
        "INSERT INTO cycles (agent_id,cycle,ts,payload) VALUES (?,?,?,?)",
        (agent_id, entry["cycle"], entry["ts"], json.dumps(entry, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    return entry


def read_cycles(agent_id: str, limit: int = 50) -> list[dict]:
    """Return recent cycles for an agent, newest last."""
    conn = _conn()
    rows = conn.execute(
        "SELECT payload FROM cycles WHERE agent_id=? ORDER BY id DESC LIMIT ?",
        (agent_id, limit),
    ).fetchall()
    conn.close()
    return [json.loads(r["payload"]) for r in reversed(rows)]
