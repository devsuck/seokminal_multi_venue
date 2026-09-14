# AI 포트폴리오 빌더 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** registry 검증 전략(paper_active 이상) 대상, Claude CLI가 배분 비중+근거를 추천하는 주간 자동 생성 기능 + 조회 API + 전용 대시보드 페이지를 추가한다. 추천만 — 실행/주문 없음.

**Architecture:** `api_server/ai_portfolio.py`(신규)가 `jarvis.investment_os.consume_research()`로 후보를 읽고 Claude CLI(공유 헬퍼 `api_server/claude_cli.py`, `lv5_agent.py`에서 추출)를 호출해 비중 JSON을 받는다. 파싱/캡(0.4) 검증 실패 시 `construct_portfolio()` 룰 기반으로 폴백. 결과는 `jarvis/_state/ai_portfolio_recs.jsonl`에 append. launchd가 주 1회(월요일 07:00) 트리거. `api_server/console_api.py`에 조회 엔드포인트 2개 추가. 대시보드는 기존 `--c-*` 디자인 토큰과 `Panel`/`PanelHead`/`Badge` 프리미티브를 그대로 써서 `/investment-os/ai-portfolio` 전용 페이지를 만들고, 기존 `investment-os` 개요 탭 포트폴리오 패널에 링크를 단다.

**Tech Stack:** FastAPI(백엔드), Next.js/React/TypeScript(프론트), Claude CLI subprocess, launchd(macOS 스케줄러), pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-09-09-ai-portfolio-builder-design.md`

## Global Constraints

- 모든 산출물은 `is_advisory=True`, `is_decision=False`, `requires_human_review=True` — 실행/주문 코드 절대 추가 금지.
- 단일 전략 최대 비중 캡 `0.4`(`portfolio_construction.py`의 `_MAX_WEIGHT`와 동일 값 재사용).
- Claude CLI 실패 경로(없음/타임아웃/파싱실패/캡위반) → 항상 `construct_portfolio()` 룰 기반 폴백, 예외로 죽지 않음.
- Python 인터프리터: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`. `asyncio_mode="auto"` — `@pytest.mark.asyncio` 절대 금지.
- 프론트엔드: raw `fetch` 금지, 반드시 `lib/console-api.ts`의 `get<T>` 경유. `style={{}}` 금지(차트/바 너비 예외). AbortController 패턴(abort→create→assign ref→fetch→catch AbortError→finally guard→unmount cleanup) 준수.
- 커밋: main 직접 커밋(브랜치 없음). 각 태스크 끝에 커밋.

---

### Task 1: Claude CLI 공유 헬퍼 추출

기존 `api_server/lv5_agent.py`에 있던 `_claude_bin()`/`_call_claude()`를 `api_server/claude_cli.py`로 옮기고 `lv5_agent.py`는 이를 import해서 씀. 로직 변경 없음 — 순수 이동. `ai_portfolio.py`(Task 2)가 이 공유 모듈을 씀.

**Files:**
- Create: `api_server/claude_cli.py`
- Modify: `api_server/lv5_agent.py:17-26` (import 블록), `api_server/lv5_agent.py:53-72` (`_claude_bin`/`_call_claude` 정의부 삭제)
- Test: 기존 `tests/test_lv5_agent.py` 전건 그린 유지로 검증(신규 테스트 파일 불필요 — 순수 이동이라 동작 변경 없음)

**Interfaces:**
- Produces: `api_server.claude_cli.claude_bin() -> str | None`, `api_server.claude_cli.call_claude(claude_path: str, prompt: str, timeout: int = 90) -> str`

- [ ] **Step 1: `api_server/claude_cli.py` 생성**

```python
"""Claude CLI 호출 공유 헬퍼 — lv5_agent, ai_portfolio 등 배치성 LLM 호출이 공유."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

_log = logging.getLogger(__name__)


def claude_bin() -> str | None:
    return shutil.which("claude") or (
        os.path.expanduser("~/.local/bin/claude")
        if os.path.exists(os.path.expanduser("~/.local/bin/claude")) else None
    )


def call_claude(claude_path: str, prompt: str, timeout: int = 90) -> str:
    """Claude CLI 호출 → stdout 반환. 실패 시 빈 문자열."""
    try:
        proc = subprocess.run(
            [claude_path, "--dangerously-skip-permissions",
             "--permission-mode", "bypassPermissions", "--print", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        return proc.stdout.strip()
    except Exception as e:
        _log.warning("[claude_cli] 호출 실패: %s", e)
        return ""
```

- [ ] **Step 2: `api_server/lv5_agent.py`의 import 블록 수정**

`api_server/lv5_agent.py:17-26`을 다음으로 교체(현재: `import json/logging/os/re/shutil/subprocess/threading/time` + 4개 `from api_server...` — `os`/`shutil`/`subprocess`는 `_claude_bin`/`_call_claude` 안에서만 쓰였으므로 삭제, 대신 `claude_cli` import 추가):

```python

import json
import logging
import re
import threading
import time

from api_server.claude_cli import call_claude as _call_claude, claude_bin as _claude_bin
from api_server.lv5_learner import extract_trade_outcomes
from api_server.lv5_memory import read_memory, append_memory
from api_server.lv5_context import get_cached_context, format_context_for_prompt
from api_server.lv5_dsl import set_cached_dsl
```

- [ ] **Step 3: `_claude_bin`/`_call_claude` 정의부 삭제**

`api_server/lv5_agent.py:53-72`(`# ── Claude CLI helper ──` 주석 줄부터 `_call_claude` 함수 끝까지)를 통째로 삭제. 이 아래의 `# ── Prompt builders ──` 주석과 이어지던 나머지 코드는 그대로 둠. 파일 내 다른 곳(285줄, 302줄, 311줄, 322줄)의 `_claude_bin()`/`_call_claude(...)` 호출부는 이름이 그대로 alias로 살아있으므로 수정 불필요.

- [ ] **Step 4: 기존 테스트 그린 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lv5_agent.py -q`
Expected: PASS(회귀 없음)

- [ ] **Step 5: Commit**

```bash
git add api_server/claude_cli.py api_server/lv5_agent.py
git commit -m "refactor: Claude CLI 헬퍼를 api_server/claude_cli.py로 추출"
```

---

### Task 2: `api_server/ai_portfolio.py` — AI 포트폴리오 추천 코어

Claude CLI로 비중+근거 생성, 실패시 룰 기반 폴백, jsonl 영속화. 이 태스크는 Claude CLI를 절대 실제로 호출하지 않는 테스트만 작성한다(`call_claude`를 monkeypatch).

**Files:**
- Create: `api_server/ai_portfolio.py`
- Test: `tests/test_ai_portfolio.py`

**Interfaces:**
- Consumes: `api_server.claude_cli.claude_bin() -> str | None`, `api_server.claude_cli.call_claude(claude_path, prompt, timeout=90) -> str`(Task 1), `jarvis.investment_os.consume_research(*, limit=50) -> dict`(기존, 반환 `{"candidates": [...], "count": int, ...}`), `jarvis.investment_os.construct_portfolio(candidates=None, *, method="evidence_weighted") -> dict`(기존, 반환에 `"weights": dict` 포함)
- Produces: `api_server.ai_portfolio.generate_ai_recommendation() -> dict`, `api_server.ai_portfolio.latest_recommendation() -> dict | None`, `api_server.ai_portfolio.history(limit: int = 20) -> list[dict]`

- [ ] **Step 1: 실패 테스트 작성 — `tests/test_ai_portfolio.py`**

```python
"""AI 포트폴리오 추천 코어 테스트. Claude CLI 실호출 절대 없음 — call_claude는 항상 monkeypatch."""
from __future__ import annotations

import json

import api_server.ai_portfolio as ap


CANDIDATES = [
    {"strategy_id": "s1", "status": "paper_active", "family": "momentum",
     "asset_class": "kr_equity", "evidence_grade": "STRONG"},
    {"strategy_id": "s2", "status": "paper_candidate", "family": "meanrev",
     "asset_class": "crypto", "evidence_grade": "MEDIUM"},
]


def _patch_consume(monkeypatch, candidates):
    monkeypatch.setattr(
        "jarvis.investment_os.consume_research",
        lambda **kw: {"candidates": candidates, "count": len(candidates)},
    )


def _patch_state_path(monkeypatch, tmp_path):
    monkeypatch.setattr(ap, "_STATE_PATH", str(tmp_path / "ai_portfolio_recs.jsonl"))


def test_generate_ai_recommendation_success(monkeypatch, tmp_path):
    _patch_consume(monkeypatch, CANDIDATES)
    _patch_state_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ap, "claude_bin", lambda: "claude")
    raw = json.dumps({
        "weights": {"s1": 0.6, "s2": 0.4},
        "per_strategy_note": {"s1": "강한 증거", "s2": "중간 증거"},
        "overall_rationale": "s1 비중 상향",
    })
    monkeypatch.setattr(ap, "call_claude", lambda *a, **kw: raw)

    rec = ap.generate_ai_recommendation()

    assert rec["fallback_used"] is False
    assert abs(sum(rec["weights"].values()) - 1.0) < 1e-6
    assert max(rec["weights"].values()) <= 0.4 + 1e-6
    assert rec["is_advisory"] is True
    assert rec["is_decision"] is False
    assert rec["requires_human_review"] is True


def test_generate_ai_recommendation_parse_failure_falls_back(monkeypatch, tmp_path):
    _patch_consume(monkeypatch, CANDIDATES)
    _patch_state_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ap, "claude_bin", lambda: "claude")
    monkeypatch.setattr(ap, "call_claude", lambda *a, **kw: "not json at all")

    rec = ap.generate_ai_recommendation()

    assert rec["fallback_used"] is True
    assert set(rec["weights"].keys()) <= {"s1", "s2"}


def test_generate_ai_recommendation_cap_violation_falls_back(monkeypatch, tmp_path):
    _patch_consume(monkeypatch, CANDIDATES)
    _patch_state_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ap, "claude_bin", lambda: "claude")
    raw = json.dumps({"weights": {"s1": 0.9, "s2": 0.1}})
    monkeypatch.setattr(ap, "call_claude", lambda *a, **kw: raw)

    rec = ap.generate_ai_recommendation()

    assert rec["fallback_used"] is True


def test_generate_ai_recommendation_no_candidates(monkeypatch, tmp_path):
    _patch_consume(monkeypatch, [])
    _patch_state_path(monkeypatch, tmp_path)

    rec = ap.generate_ai_recommendation()

    assert rec["candidates_count"] == 0
    assert rec["fallback_used"] is False
    assert rec["weights"] == {}


def test_generate_ai_recommendation_no_cli_skips_call(monkeypatch, tmp_path):
    _patch_consume(monkeypatch, CANDIDATES)
    _patch_state_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ap, "claude_bin", lambda: None)
    called = []
    monkeypatch.setattr(ap, "call_claude", lambda *a, **kw: called.append(1) or "")

    rec = ap.generate_ai_recommendation()

    assert called == []
    assert rec["fallback_used"] is True


def test_history_and_latest_round_trip(monkeypatch, tmp_path):
    _patch_state_path(monkeypatch, tmp_path)
    ap._append({"timestamp": "t1", "weights": {"s1": 1.0}})
    ap._append({"timestamp": "t2", "weights": {"s2": 1.0}})

    assert ap.latest_recommendation()["timestamp"] == "t2"
    hist = ap.history(limit=10)
    assert [r["timestamp"] for r in hist] == ["t2", "t1"]
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ai_portfolio.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'api_server.ai_portfolio'`)

- [ ] **Step 3: `api_server/ai_portfolio.py` 구현**

```python
"""AI 포트폴리오 구성 — registry 검증 전략(paper_active 이상) 대상, LLM이 비중+근거 제안.
**추천만, 실행 없음.** investment_os 불변식과 동일: is_advisory=True, is_decision=False,
requires_human_review=True. Research OS 무변경(읽기전용 소비).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os

from api_server.claude_cli import call_claude, claude_bin

_log = logging.getLogger(__name__)
_STATE_PATH = "jarvis/_state/ai_portfolio_recs.jsonl"
_MAX_WEIGHT = 0.4  # portfolio_construction.py의 _MAX_WEIGHT와 동일 캡


def _build_prompt(candidates: list[dict]) -> str:
    lines = [
        f"- {c['strategy_id']} | family={c.get('family', '?')} | "
        f"asset_class={c.get('asset_class', '?')} | evidence={c.get('evidence_grade', 'UNKNOWN')} | "
        f"status={c.get('status', '?')}"
        for c in candidates
    ]
    return (
        "다음은 페이퍼 검증을 통과했거나 진행 중인 트레이딩 전략 목록이다. 각 전략에 배분 비중을 "
        "추천하라.\n\n" + "\n".join(lines) +
        "\n\n규칙: 비중 합계는 정확히 1.0. 단일 전략 최대 비중 0.4. evidence_grade가 낮거나 "
        "UNKNOWN인 전략은 보수적으로. 아래 JSON 스키마로 한 줄만 출력(설명 텍스트 금지):\n"
        '{"weights": {"<strategy_id>": <float>, ...}, '
        '"per_strategy_note": {"<strategy_id>": "<한줄 근거>", ...}, '
        '"overall_rationale": "<전체 근거 한 문단>"}'
    )


def _parse_response(raw: str, candidate_ids: set[str]) -> dict | None:
    try:
        data = json.loads(raw.strip().splitlines()[-1]) if raw.strip() else None
    except (json.JSONDecodeError, IndexError):
        return None
    if not isinstance(data, dict) or "weights" not in data:
        return None
    try:
        weights = {k: float(v) for k, v in data["weights"].items() if k in candidate_ids}
    except (TypeError, ValueError):
        return None
    if not weights:
        return None
    total = sum(weights.values())
    if total <= 0:
        return None
    weights = {k: round(v / total, 4) for k, v in weights.items()}
    if max(weights.values()) > _MAX_WEIGHT + 1e-6:
        return None  # 캡 위반 — 폴백으로
    return {
        "weights": weights,
        "per_strategy_note": {k: v for k, v in (data.get("per_strategy_note") or {}).items()
                               if k in candidate_ids},
        "overall_rationale": str(data.get("overall_rationale", "")),
    }


def generate_ai_recommendation() -> dict:
    """주 1회(launchd) 호출 진입점. 반환 = jsonl에 append하는 레코드와 동일 dict."""
    from jarvis.investment_os import consume_research, construct_portfolio

    k = consume_research()
    candidates = [c for c in k.get("candidates", []) if c.get("evidence_grade") != "REJECTED"]
    ts = dt.datetime.now(dt.timezone.utc).isoformat()

    if not candidates:
        record = {"timestamp": ts, "weights": {}, "per_strategy_note": {}, "overall_rationale": "",
                   "fallback_used": False, "candidates_count": 0,
                   "is_advisory": True, "is_decision": False, "requires_human_review": True,
                   "note": "구성할 후보 없음 — 연구 지식 축적 필요."}
        _append(record)
        return record

    candidate_ids = {c["strategy_id"] for c in candidates}
    parsed = None
    claude = claude_bin()
    if claude:
        prompt = _build_prompt(candidates)
        for _ in range(2):  # 1회 재시도
            raw = call_claude(claude, prompt, timeout=120)
            parsed = _parse_response(raw, candidate_ids)
            if parsed:
                break
    else:
        _log.warning("[ai_portfolio] Claude CLI 없음 — 폴백")

    fallback_used = parsed is None
    if fallback_used:
        rule_based = construct_portfolio(candidates)
        parsed = {"weights": rule_based.get("weights", {}), "per_strategy_note": {},
                  "overall_rationale": "AI 응답 파싱 실패 또는 Claude CLI 없음 — 규칙 기반(evidence_weighted) 폴백."}

    record = {"timestamp": ts, "candidates_count": len(candidates), "fallback_used": fallback_used,
              **parsed,
              "is_advisory": True, "is_decision": False, "requires_human_review": True,
              "note": "AI Portfolio Builder(추천) — 실제 배분/집행 아님. 사람이 결정."}
    _append(record)
    return record


def _append(record: dict) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(_STATE_PATH, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def latest_recommendation() -> dict | None:
    rows = _read_all()
    return rows[-1] if rows else None


def history(limit: int = 20) -> list[dict]:
    return _read_all()[-limit:][::-1]


def _read_all() -> list[dict]:
    if not os.path.exists(_STATE_PATH):
        return []
    with open(_STATE_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ai_portfolio.py -q`
Expected: PASS(7 tests)

- [ ] **Step 5: Commit**

```bash
git add api_server/ai_portfolio.py tests/test_ai_portfolio.py
git commit -m "feat: AI 포트폴리오 추천 코어(ai_portfolio.py) 추가"
```

---

### Task 3: `console_api.py` 조회 엔드포인트

`GET /console/investment-os/ai-portfolio/latest`, `GET /console/investment-os/ai-portfolio/history`. `tests/test_console_api.py`는 TestClient가 아니라 함수를 직접 호출하는 파일 컨벤션(예: `c.status()`)을 따른다 — 그대로 따름.

**Files:**
- Modify: `api_server/console_api.py:2307`(`investment_os_advance` 함수 끝, `# ── Forward Learning` 주석 바로 앞)에 엔드포인트 2개 삽입
- Test: `tests/test_console_api.py`

**Interfaces:**
- Consumes: `api_server.ai_portfolio.latest_recommendation() -> dict | None`, `api_server.ai_portfolio.history(limit: int = 20) -> list[dict]`(Task 2), 기존 `_safe(fn, default=None)` 헬퍼(`api_server/console_api.py:14`)

- [ ] **Step 1: 실패 테스트 작성 — `tests/test_console_api.py`에 추가**

파일 끝에 추가:

```python

def test_ai_portfolio_latest_empty_when_no_recs(monkeypatch):
    monkeypatch.setattr("api_server.ai_portfolio.latest_recommendation", lambda: None)
    r = c.ai_portfolio_latest()
    assert isinstance(r, dict)
    assert r["weights"] == {}


def test_ai_portfolio_latest_returns_record(monkeypatch):
    rec = {"timestamp": "t1", "weights": {"s1": 1.0}, "fallback_used": False}
    monkeypatch.setattr("api_server.ai_portfolio.latest_recommendation", lambda: rec)
    r = c.ai_portfolio_latest()
    assert r["timestamp"] == "t1"


def test_ai_portfolio_history_shape(monkeypatch):
    recs = [{"timestamp": "t2"}, {"timestamp": "t1"}]
    monkeypatch.setattr("api_server.ai_portfolio.history", lambda limit=20: recs)
    r = c.ai_portfolio_history(limit=5)
    assert isinstance(r, dict) and r["records"] == recs
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_console_api.py -q -k ai_portfolio`
Expected: FAIL(`AttributeError: module 'api_server.console_api' has no attribute 'ai_portfolio_latest'`)

- [ ] **Step 3: `api_server/console_api.py:2307`에 엔드포인트 삽입**

`investment_os_advance` 함수 끝(2307번째 줄, `# ── Forward Learning — thesis vs 실제 결과 (READ ONLY) ──` 주석 바로 앞)에 아래 삽입:

```python

@router.get("/investment-os/ai-portfolio/latest")
def ai_portfolio_latest() -> dict:
    """AI 포트폴리오 추천 최신 1건. 없으면 빈 weights. 추천만, 실행 없음."""
    import api_server.ai_portfolio as ap
    rec = _safe(lambda: ap.latest_recommendation(), None)
    return rec or {"weights": {}, "is_advisory": True, "is_decision": False,
                    "note": "아직 생성된 추천 없음(주간 launchd job 대기 중)."}


@router.get("/investment-os/ai-portfolio/history")
def ai_portfolio_history(limit: int = 20) -> dict:
    """AI 포트폴리오 추천 이력."""
    import api_server.ai_portfolio as ap
    return {"records": _safe(lambda: ap.history(limit), []) or []}

```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_console_api.py -q`
Expected: PASS(전건)

- [ ] **Step 5: Commit**

```bash
git add api_server/console_api.py tests/test_console_api.py
git commit -m "feat: AI 포트폴리오 추천 조회 엔드포인트 추가(/console/investment-os/ai-portfolio/*)"
```

---

### Task 4: 주간 launchd 트리거

`~/Library/LaunchAgents/com.seokminal.ai-portfolio.plist` 생성. **`launchctl load`는 시스템 상태 변경(백그라운드 잡 등록)이라 이 단계에서 실행하지 않는다 — 파일만 만들고, 사용자가 검토 후 직접 `launchctl load`를 실행하도록 안내 문구를 마지막에 출력한다.**

**Files:**
- Create: `~/Library/LaunchAgents/com.seokminal.ai-portfolio.plist`(리포 밖)

**Interfaces:**
- Consumes: `api_server.ai_portfolio.generate_ai_recommendation()`(Task 2, 인자 없음)

- [ ] **Step 1: plist 파일 생성**

`~/Library/LaunchAgents/com.seokminal.prune-research-data.plist`와 동일 템플릿(`StartCalendarInterval`에 `Weekday` 추가):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.seokminal.ai-portfolio</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Library/Frameworks/Python.framework/Versions/3.14/bin/python3</string>
        <string>-c</string>
        <string>from api_server.ai_portfolio import generate_ai_recommendation; generate_ai_recommendation()</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/seokhun/seokminal/seokminal-multi-venue</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/seokhun/Library/Logs/seokminal-ai-portfolio.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/seokhun/Library/Logs/seokminal-ai-portfolio.err.log</string>
</dict>
</plist>
```

- [ ] **Step 2: plist 문법 검증**

Run: `plutil -lint ~/Library/LaunchAgents/com.seokminal.ai-portfolio.plist`
Expected: `OK`

- [ ] **Step 3: 사용자에게 안내(이 태스크는 커밋 없음 — 리포 밖 파일)**

작업 로그/보고에 다음을 남길 것: "plist 생성 완료. 실제 등록하려면 `launchctl load ~/Library/LaunchAgents/com.seokminal.ai-portfolio.plist` 직접 실행 필요(자동 실행 안 함)."

---

### Task 5: 프론트엔드 API 클라이언트 — `lib/console-api.ts`

`getAiPortfolioLatest`/`getAiPortfolioHistory` 추가. 기존 `getInvestmentOs` 바로 옆(`lib/console-api.ts:779` 이후)에 배치. 이 리포엔 `console-api.ts` 전용 vitest 파일이 하나도 없음(기존 관행상 커버리지 없는 영역) — 새 테스트 파일을 신설하지 않고 `npx tsc --noEmit`로 타입만 검증한다(YAGNI — 없는 관행을 이 두 함수 때문에 새로 만들지 않음).

**Files:**
- Modify: `/Users/seokhun/seokminal/seokminal-dashboard/lib/console-api.ts:779`(`getInvestmentOs` 정의 직후)

**Interfaces:**
- Consumes: 기존 `get<T>(path, signal)`(`lib/console-api.ts:7`)
- Produces: `getAiPortfolioLatest(signal?) -> Promise<AiPortfolioResp>`, `getAiPortfolioHistory(limit?, signal?) -> Promise<AiPortfolioHistoryResp>`, 타입 `AiPortfolioResp`, `AiPortfolioHistoryResp`

- [ ] **Step 1: `lib/console-api.ts:779`(`getInvestmentOs` 정의) 바로 뒤에 추가**

```typescript

// AI 포트폴리오 추천 — registry 검증 전략(paper_active+) 대상 Claude 배분 추천. 주 1회 자동 생성.
export interface AiPortfolioResp {
  timestamp?: string;
  weights: Record<string, number>;
  per_strategy_note?: Record<string, string>;
  overall_rationale?: string;
  fallback_used?: boolean;
  candidates_count?: number;
  is_advisory: boolean;
  is_decision: boolean;
  note?: string;
}
export const getAiPortfolioLatest = (s?: AbortSignal) =>
  get<AiPortfolioResp>(`/console/investment-os/ai-portfolio/latest`, s);

export interface AiPortfolioHistoryResp {
  records: AiPortfolioResp[];
}
export const getAiPortfolioHistory = (limit = 20, s?: AbortSignal) =>
  get<AiPortfolioHistoryResp>(`/console/investment-os/ai-portfolio/history?limit=${limit}`, s);
```

- [ ] **Step 2: 타입 검증**

Run: `cd /Users/seokhun/seokminal/seokminal-dashboard && npx tsc --noEmit`
Expected: 에러 0건

- [ ] **Step 3: Commit**

```bash
cd /Users/seokhun/seokminal/seokminal-dashboard
git add lib/console-api.ts
git commit -m "feat: AI 포트폴리오 추천 조회 API 클라이언트 추가"
```

---

### Task 6: 전용 대시보드 페이지 + 진입 링크

`/investment-os/ai-portfolio` 페이지 신설(기존 `--c-*` 토큰 + `Panel`/`PanelHead`/`Badge` 프리미티브 재사용). 기존 `investment-os` 개요 탭의 "포트폴리오 구성" 패널에 진입 링크 추가.

**Files:**
- Create: `/Users/seokhun/seokminal/seokminal-dashboard/app/(console)/investment-os/ai-portfolio/page.tsx`
- Modify: `/Users/seokhun/seokminal/seokminal-dashboard/app/(console)/investment-os/page.tsx`(포트폴리오 구성 `PanelHead`의 `right`, 현재 `right={<Badge tone="mute">추천 · 실배분 아님</Badge>}` 한 줄)

**Interfaces:**
- Consumes: `getAiPortfolioLatest(signal?)`, `getAiPortfolioHistory(limit?, signal?)`, 타입 `AiPortfolioResp`/`AiPortfolioHistoryResp`(Task 5), 기존 `Panel`/`PanelHead`/`Badge`/`SkeletonLines`(`components/console/primitives`), 기존 로컬 `TabLink({href, label})`(`app/(console)/investment-os/page.tsx:105`)

- [ ] **Step 1: `app/(console)/investment-os/ai-portfolio/page.tsx` 생성**

```tsx
"use client";
// AI 포트폴리오 추천 — registry 검증 전략(paper_active+) 대상 Claude 배분 추천.
// /console/investment-os/ai-portfolio/*. READ ONLY — 추천만, 실행/주문 없음. 사람이 최종 결정.
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  getAiPortfolioLatest, getAiPortfolioHistory,
  type AiPortfolioResp, type AiPortfolioHistoryResp,
} from "@/lib/console-api";
import { Panel, PanelHead, Badge, SkeletonLines } from "@/components/console/primitives";

export default function AiPortfolioPage() {
  const [latest, setLatest] = useState<AiPortfolioResp | null>(null);
  const [hist, setHist] = useState<AiPortfolioHistoryResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    setErr(null);
    try {
      const [l, h] = await Promise.all([
        getAiPortfolioLatest(ctrl.signal),
        getAiPortfolioHistory(20, ctrl.signal),
      ]);
      if (!ctrl.signal.aborted) { setLatest(l); setHist(h); }
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) setErr((e as Error).message);
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, []);
  useEffect(() => { run(); return () => abortRef.current?.abort(); }, [run]);

  const weights = Object.entries(latest?.weights ?? {});

  return (
    <div className="min-h-full c-bg p-5 space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[9px] font-semibold tracking-[0.24em] uppercase text-[var(--c-text-3)]">
            registry 검증 전략(paper_active+) · 주 1회 자동 생성
          </div>
          <div className="text-[13px] font-semibold text-[var(--c-text-1)]">AI 포트폴리오 추천</div>
        </div>
        <Link href="/investment-os" className="text-[11px] text-[var(--c-hud)] hover:underline no-underline">
          ← Investment OS
        </Link>
      </div>

      <Panel>
        <PanelHead kicker="ai_portfolio · Claude CLI 배분 추천" title="최신 추천"
          right={<Badge tone="mute">추천 · 실배분/주문 아님 — 사람이 최종 결정</Badge>} />
        <div className="p-4 space-y-2">
          {loading && <SkeletonLines rows={4} />}
          {err && <div className="text-[11px] text-[var(--c-neg)]">{err}</div>}
          {latest?.fallback_used && (
            <Badge tone="warn">AI 응답 실패 — 규칙 기반(evidence_weighted) 폴백</Badge>
          )}
          {!loading && weights.length === 0 && (
            <div className="text-[11px] text-[var(--c-text-3)]">{latest?.note ?? "추천 없음"}</div>
          )}
          {weights.map(([sid, w]) => (
            <div key={sid} className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-[var(--c-text-1)] w-52 truncate">{sid}</span>
                <div className="flex-1 h-1.5 bg-[var(--c-border)] rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${w * 100}%`, background: "var(--c-hud)" }} />
                </div>
                <span className="text-[11px] c-num text-[var(--c-text-3)] w-14 text-right">{(w * 100).toFixed(1)}%</span>
              </div>
              {latest?.per_strategy_note?.[sid] && (
                <div className="text-[9px] text-[var(--c-text-3)] pl-1">{latest.per_strategy_note[sid]}</div>
              )}
            </div>
          ))}
          {latest?.overall_rationale && (
            <div className="pt-2 border-t border-[var(--c-border)] text-[11px] text-[var(--c-text-2)] leading-relaxed">
              {latest.overall_rationale}
            </div>
          )}
        </div>
      </Panel>

      <Panel>
        <PanelHead kicker="이력" title="최근 추천 이력" right={hist && <Badge tone="mute">{hist.records.length}건</Badge>} />
        <div className="p-4 space-y-1.5">
          {loading && <SkeletonLines rows={3} />}
          {!loading && (hist?.records.length ?? 0) === 0 && (
            <div className="text-[11px] text-[var(--c-text-3)]">이력 없음.</div>
          )}
          {hist?.records.map((r, i) => (
            <div key={i} className="flex items-center justify-between text-[11px] c-num text-[var(--c-text-2)] border-b border-[var(--c-border)] last:border-0 py-1">
              <span>{r.timestamp}</span>
              <span>{Object.keys(r.weights).length}개 전략{r.fallback_used ? " · 폴백" : ""}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
```

- [ ] **Step 2: `investment-os/page.tsx`의 포트폴리오 구성 패널에 진입 링크 추가**

`app/(console)/investment-os/page.tsx`에서 `<PanelHead kicker="포트폴리오 구성" title="추천 비중" right={<Badge tone="mute">추천 · 실배분 아님</Badge>} />`를 찾아 `right`를 다음으로 교체(기존 Badge 유지 + 링크 추가):

```tsx
                    <PanelHead kicker="포트폴리오 구성" title="추천 비중"
                      right={<div className="flex items-center gap-2">
                        <Badge tone="mute">추천 · 실배분 아님</Badge>
                        <TabLink href="/investment-os/ai-portfolio" label="AI 추천 보기" />
                      </div>} />
```

- [ ] **Step 3: 타입 검증**

Run: `cd /Users/seokhun/seokminal/seokminal-dashboard && npx tsc --noEmit`
Expected: 에러 0건

- [ ] **Step 4: 개발 서버로 수동 확인**

Run: `cd /Users/seokhun/seokminal/seokminal-dashboard && npm run dev`
브라우저로 `http://localhost:3000/investment-os` 접속 → 개요 탭 "포트폴리오 구성" 패널에서 "AI 추천 보기" 링크 클릭 → `/investment-os/ai-portfolio`에서 최신 추천/이력 렌더 확인(백엔드 `uvicorn api_server.main:app` 구동 중이어야 함). 추천이 아직 없으면(launchd 미실행) "추천 없음" 문구가 정상 표시되는지 확인.

- [ ] **Step 5: Commit**

```bash
cd /Users/seokhun/seokminal/seokminal-dashboard
git add "app/(console)/investment-os/ai-portfolio/page.tsx" "app/(console)/investment-os/page.tsx"
git commit -m "feat: AI 포트폴리오 추천 전용 페이지 + 진입 링크 추가"
```

---

## 최종 검증

- [ ] `cd /Users/seokhun/seokminal/seokminal-multi-venue && /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q` → 전건 그린(신규 실패 0건)
- [ ] `cd /Users/seokhun/seokminal/seokminal-dashboard && npx tsc --noEmit && npm test` → 에러/실패 0건
- [ ] `docs/progress.md`에 세션 로그 추가(완료 작업/변경 파일/다음 할 일 — 전역 CLAUDE.md 컨벤션)
