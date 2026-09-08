# AI 포트폴리오 구성 기능 — Design Spec

**Status:** Draft, pending user review
**Sub-project:** 1/2 (2번은 별도 스펙 — 포트폴리오 UI 전면 재설계, 이번 스코프 아님)

## 배경

사용자 요청: "autopilot 에이전트들처럼 AI가 포트폴리오 짜는 기능 없나?" — 조사 결과 현재
코드베이스엔 없음:

- `jarvis/investment_os/portfolio_construction.py::construct_portfolio()` — 있지만 **결정론적**
  (evidence_grade 가중 or 동일가중 룰). LLM 판단 아님.
- 대시보드 `app/portfolio/page.tsx` "최적화 도구" 탭 → `/portfolio/optimizer` — 마코위츠
  평균-분산 **교육용** 도구, 실전 배분 아님, 역시 결정론적.
- 비교 대상(사용자가 말한 "autopilot 에이전트"): `/Users/seokhun/seokminal/autopilot/agent_loop.sh` —
  zsh가 신호 계산, Claude CLI가 해석+판단해서 JSON 한 줄 emit하는 루프. 개별 심볼 단위 매매 판단이지
  포트폴리오 비중 판단 아님.

→ "여러 전략 걸쳐 LLM이 비중 판단" 하는 흐름 자체가 없음. 신규 서브시스템 = architectural.

## 스코프 (사용자 확정)

- **대상**: registry 검증 전략만(paper_active 이상). 임의 종목 배분은 범위 밖.
- **주기**: 주 1회 자동 생성(수동 트리거 아님).
- **UI**: 이번 스코프에 전용 페이지 포함(기존 디자인 토큰/레이아웃은 그대로 따름 — 전면 개편은
  2번 서브프로젝트).

## 불변식 (investment_os 계층 규칙, 이 기능도 예외 없음)

`jarvis/investment_os/__init__.py` 헤더에 명시된 계층 원칙 그대로 적용:
- 모든 산출물은 `is_advisory=True`, `is_decision=False`, `requires_human_review=True`.
- 실행/주문 없음. Research OS 무변경(읽기전용 소비만).
- 레벨6/registry-arm 실행 게이트와 무관 — 이 기능은 추천 텍스트만 생성하므로 지금 바로 유용함
  (2026-09-09 세션에서 "레지스트리 전략 실행 에이전트" 신설은 실행 게이트가 다 막혀있어 지금
  만들어봐야 기능적으로 무의미하다고 판단해 미뤘던 것과 다름 — 그건 실행 경로, 이건 추천 전용).

## 아키텍처

새 모듈 `api_server/ai_portfolio.py`. `jarvis/investment_os/`가 아니라 `api_server/`에 두는 이유:
investment_os는 순수함수(결정론적, subprocess 없음) 계층 — 여기 Claude CLI subprocess 호출을
섞으면 그 계층의 "결정론적 룰 기반" 성격이 깨짐. `api_server/lv5_agent.py`가 이미 같은 패턴
(Claude CLI subprocess로 3-Phase 리뷰)을 쓰고 있어 그 옆에 나란히 둠.

## 컴포넌트

### 1. `api_server/claude_cli.py` (신규, 공유 헬퍼 추출)

`lv5_agent.py`의 `_claude_bin()` / `_call_claude()`를 여기로 이동. `lv5_agent.py`는 이 모듈에서
import해서 갈아탐(로직 변경 없음, 위치만 이동 — 중복 코드 방지).

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

`lv5_agent.py`에서 바꿀 것: `_claude_bin`/`_call_claude` 정의 삭제, 대신
`from api_server.claude_cli import claude_bin as _claude_bin, call_claude as _call_claude` import.
기존 호출부(`_claude_bin()`, `_call_claude(...)`) 코드는 손대지 않음 — 이름 그대로 로컬 별칭.

### 2. `api_server/ai_portfolio.py` (신규)

```python
"""AI 포트폴리오 구성 — registry 검증 전략(paper_active 이상) 대상, LLM이 비중+근거 제안.
**추천만, 실행 없음.** investment_os 불변식과 동일: is_advisory=True, is_decision=False,
requires_human_review=True. Research OS 무변경(읽기전용 소비)."""
from __future__ import annotations

import datetime as dt
import json
import logging

from api_server.claude_cli import call_claude, claude_bin

_log = logging.getLogger(__name__)
_STATE_PATH = "jarvis/_state/ai_portfolio_recs.jsonl"
_MAX_WEIGHT = 0.4  # portfolio_construction.py와 동일 캡


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
        "UNKNOWN인 전략은 보수적으로. 아래 JSON 스키마로 **한 줄**만 출력(설명 텍스트 금지):\n"
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
    weights = {k: float(v) for k, v in data["weights"].items() if k in candidate_ids}
    if not weights:
        return None
    total = sum(weights.values())
    if total <= 0:
        return None
    weights = {k: round(v / total, 4) for k, v in weights.items()}
    if max(weights.values()) > _MAX_WEIGHT + 1e-6:
        return None  # 캡 위반 — 재시도/폴백으로
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
    ts = dt.datetime.now(dt.UTC).isoformat()

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
    import os
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(_STATE_PATH, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def latest_recommendation() -> dict | None:
    return _read_all()[-1] if _read_all() else None


def history(limit: int = 20) -> list[dict]:
    return _read_all()[-limit:][::-1]


def _read_all() -> list[dict]:
    import os
    if not os.path.exists(_STATE_PATH):
        return []
    with open(_STATE_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]
```

### 3. API 엔드포인트 (`api_server/console_api.py`에 추가, 기존 `/investment-os` 섹션 옆)

```python
@router.get("/investment-os/ai-portfolio/latest")
def ai_portfolio_latest() -> dict:
    """AI 포트폴리오 추천 최신 1건. 없으면 빈 dict. 추천만, 실행 없음."""
    from api_server.ai_portfolio import latest_recommendation
    return _safe(lambda: latest_recommendation(), None) or {
        "weights": {}, "note": "아직 생성된 추천 없음(주간 launchd job 대기 중)."}


@router.get("/investment-os/ai-portfolio/history")
def ai_portfolio_history(limit: int = 20) -> dict:
    """AI 포트폴리오 추천 이력."""
    from api_server.ai_portfolio import history
    return {"records": _safe(lambda: history(limit), []) or []}
```

### 4. launchd job — `com.seokminal.ai-portfolio.plist`

`prune-research-data.plist`와 동일 템플릿, `StartCalendarInterval`에 `Weekday` 추가(월요일 07:00):

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

plist 파일 자체는 리포 밖(`~/Library/LaunchAgents/`)이라 구현 플랜에는 "이 내용으로 파일 생성 +
`launchctl load` 안내" 스텝으로 들어감(실제 load는 사용자 확인 후 — launchd 등록은 시스템
변경이라 세션 규칙상 확인 필요).

### 5. 대시보드 페이지 — `app/portfolio/ai-builder/page.tsx` (신규)

- `lib/api.ts`에 `getAiPortfolioLatest()`, `getAiPortfolioHistory(limit)` 함수 추가(raw fetch 금지
  컨벤션 준수).
- 최신 추천: 전략별 비중 바 차트/표 + `overall_rationale` 텍스트 + 전략별 `per_strategy_note`.
- `fallback_used=true`면 눈에 띄게 배지 표시("AI 응답 실패 — 규칙 기반 폴백").
- 이력: 최근 N건 타임라인(주차별 비중 변화).
- 기존 디자인 토큰(`bg-bg/panel`, `text-text-1/2/3` 등) 그대로 사용, `components/console/primitives.tsx`
  (`Panel`, `PanelHead`, `Badge`) 재사용.
- 상단 disclaimer 고정 문구: "AI 추천 — 실제 배분/주문 아님. 사람이 최종 결정." (investment_os
  기존 disclaimer 톤과 통일).

## 에러 처리

- Claude CLI 없음 / 타임아웃 / JSON 파싱 실패 / 캡(0.4) 위반 → 1회 재시도 → 그래도 실패 시
  `construct_portfolio()` 룰 기반 결과로 폴백, `fallback_used=true`. 예외로 죽지 않음(항상 레코드
  하나는 남김).
- 후보 0개 → 빈 추천 레코드 + 안내 메시지(기존 `construct_portfolio()`의 "구성할 후보 없음" 패턴과
  동일).
- `_state/ai_portfolio_recs.jsonl` 쓰기 실패는 상위로 예외 전파(다른 `_state/*.jsonl` append와 동일
  — 조용히 삼키지 않음, 이건 감사 로그가 아니라 유일한 데이터 소스이므로).

## 테스트

- `tests/test_ai_portfolio.py`(신규):
  - `call_claude` monkeypatch로 정상 JSON 응답 → 비중 합=1, 0.4 캡 이내 검증.
  - 파싱 실패 응답(빈 문자열/깨진 JSON) → 재시도 1회 후 폴백 확인, `fallback_used=True`.
  - 캡 위반 응답(한 전략 0.9) → 폴백 경로 타는지 확인.
  - 후보 0개 → 빈 레코드 + `fallback_used=False`.
  - `claude_bin()`이 None(CLI 없음) → 즉시 폴백, `call_claude` 호출 안 됨.
  - `_append`/`history`/`latest_recommendation` — 임시 `_STATE_PATH` monkeypatch해서 append 후
    읽기 왕복 검증.
- `tests/test_console_api.py` 또는 신규 파일에 `/investment-os/ai-portfolio/latest`,
  `/investment-os/ai-portfolio/history` TestClient 테스트(빈 상태 / 데이터 있는 상태 둘 다).
- 실제 Claude CLI를 호출하는 테스트는 없음(`lv5_agent.py` 기존 테스트 방식과 동일 — 항상 mock).
- `api_server/claude_cli.py` 추출 후 `lv5_agent.py` 기존 테스트 전부 그린 유지 확인(리팩터 회귀 없음).

## 스코프 밖 (2번 서브프로젝트 또는 아예 범위 밖)

- 포트폴리오 페이지 전체 UI 재설계(디자인 토큰 탈피 등) — 2번 서브프로젝트, 별도 스펙.
- 임의 종목/자산 배분 — registry 검증 전략만.
- 수동 트리거 버튼 — 이번엔 주간 자동만(필요해지면 나중 확장, YAGNI).
- 실행/자동매매 연동 — investment_os 불변식상 영구 범위 밖.
