# Polymarket AI 판단 봇 (side="ai") — Design Spec

**작성:** 2026-08-23. 브레인스토밍 중 섹션별 확정, 사용자 승인 완료.

## 1. 배경

기존 `polymarket_bot.py`의 사이드 선택 로직(`favorite`/`underdog`/`random`)은
가격 구조만 보고 베팅한다 — 마켓이 실제로 무슨 내용인지는 전혀 안 본다.
`/status`의 `note` 필드에 mid_favorite 밴드(0.49~0.74) BH-FDR 생존 언급이
있지만(p=0.026, n=37) n≥100 재검증 전까지 실집행 승격 대상 아니고, 애초에
`_scan_and_enter`에 배선도 안 돼 있다.

사용자가 "AI CLI 넣어서 판단하게 하거나 네이버 검색 API 붙일 수 있냐"고
물어본 게 출발점. 브레인스토밍으로 이어져 두 아이디어(LLM 판단 + 검색
grounding)를 하나로 합친 신규 전략으로 설계했다: 마켓 질문 텍스트를 검색으로
grounding하고 LLM이 실제 내용 기반으로 YES 확률을 추정, 시장가와의 괴리
(edge)가 임계치 넘을 때만 진입.

## 2. 가설

Polymarket 활성마켓 중, 웹검색으로 grounding된 LLM 판단 확률과 시장가(YES
price) 사이 괴리가 거래비용 넘어설 만큼 크면, 그 방향(AI 확률 쪽)으로
포지션 잡았을 때 만기 시점 pnl이 양수인가.

기존 봇들(가격구조 기반)과 완전히 다른 신호 축 — 코드/포지션/예산 전부
독립, 기존 `polymarket_bot.py`/`polymarket_sharp_wallet_bot.py`와 섞지 않고
셋째 sibling 봇으로 병렬 실행한다(비교 기준선 확보 목적도 있음: 같은 마켓
유니버스에서 AI 판단이 가격구조 전략들보다 나은지 나중에 직접 비교 가능).

## 3. 아키텍처

```
api_server/polymarket_bot.py                    (기존, 무변경)
api_server/polymarket_sharp_wallet_bot.py        (기존, 무변경)
api_server/polymarket_ai_bot.py                  ← 신규 — 셋째 sibling 봇 (router/config/tick/start_loop/status)
research/polymarket_ai_judgment/judge.py         ← 신규 — Tavily 검색 + Groq 판단 + 캐시/예산(entity_tags.py 패턴 재사용)
research/data/polymarket_ai_judgment/judge_cache.json     ← 신규 — condition_id+question_hash 키 캐시
research/data/polymarket_ai_judgment/daily_call_state.json ← 신규 — 일일 호출 카운터(날짜 롤오버)
tests/test_polymarket_ai_bot.py                  ← 신규
tests/test_polymarket_ai_judgment_judge.py        ← 신규
```

`api_server/main.py`, `components/hud/PortfolioTab.tsx`(대시보드 리포)는
기존 sibling 봇 등록 패턴 그대로 따른다(§5.4).

## 4. 모듈 상세

### 4.1 후보 선정 (`api_server/polymarket_ai_bot.py` 내부, `_scan_candidates`)

`polymarket_bot.py`의 `_scan_and_enter` 필터 로직 재사용(같은 함수 복붙이
아니라 같은 필터 기준 — active/not-closed/accepting-orders, 자체 보유
포지션과 중복 제외, `min_liquidity`, `min/max_price`, `min/max_days_to_resolution`).
단, 포지션/예산은 이 봇 전용 상태로 완전 분리 — `polymarket_bot`/
`polymarket_sharp_wallet_bot`이 이미 잡은 마켓이어도 이 봇은 독립적으로
평가·진입 가능(섀도 트래킹이므로 실자본 중복 리스크 없음, paper 전용).

### 4.2 AI 판단 (`research/polymarket_ai_judgment/judge.py`)

`entity_tags.py`와 동일 골격(캐시 + 호출예산 + 스테일 폴백) 재사용, 이번엔
캐시 미스마다 **Tavily 검색 1회 + Groq 판단 1회**가 함께 발생한다는 점만
다르다.

```python
_MODEL = "llama-3.3-70b-versatile"      # entity_tags.py와 동일 모델(오탐비용 큰 판단이라 8b 아님)
_TAVILY_MAX_RESULTS = 5
_CACHE_PATH = Path("research/data/polymarket_ai_judgment/judge_cache.json")
_DAILY_STATE_PATH = Path("research/data/polymarket_ai_judgment/daily_call_state.json")

def judge_market(question: str, condition_id: str, tavily_client, groq_client) -> dict:
    """Tavily 검색 → Groq 판단 → {"yes_prob": float, "reasoning": str} 반환.
    호출자가 캐시/예산 체크 이후에만 부른다(§4.3)."""
```

- Tavily 클라이언트: `from tavily import TavilyClient`(공식 SDK, 신규
  의존성 1개 — `pyproject`/`requirements`에 추가), `api_key=os.environ["TAVILY_API_KEY"]`.
- Groq 클라이언트: 기존 컨벤션 그대로 `from openai import OpenAI`,
  `base_url="https://api.groq.com/openai/v1"`, `api_key=os.environ["GROQ_API_KEY"]`.
- 프롬프트: 마켓 질문 + Tavily 검색결과 스니펫(최대 5개, 각 title+content
  일부) → `{"yes_prob": 0.0~1.0, "reasoning": "..."}` JSON 강제. 마크다운
  코드펜스 제거 후 파싱, 실패 시 판단 스킵(포지션 진입 안 함 — 억지로
  fallback 확률 넣지 않음, entity_tags.py의 `[]` 폴백과 달리 이쪽은 misjudge
  가 곧바로 paper 자본 배분으로 이어지므로 실패는 "패스"가 안전한 기본값).

### 4.3 캐시 + 예산 (틱당 + 일일 이중 캡)

```python
_DEFAULT = {
    ...
    "interval_sec": 3600.0,          # 시간당 1틱, 24틱/일
    "max_new_calls_per_tick": 5,     # 틱당 신규 판단 캡
    "max_new_calls_per_day": 30,     # 일일 신규 판단 캡 — Tavily 무료티어 보호용
    "min_edge": 0.05,                # |ai_yes_prob - market_price| 이 값 미만이면 패스
}
```

- `judge_cache.json`: `entity_tags.py`와 동일 — `condition_id` + 질문
  텍스트 SHA-256(`question_hash`) 복합키, 캐시 히트면 재호출 없이 재사용
  (질문 텍스트 안 바뀌는 한 영구 재사용 — Polymarket 마켓 질문은 생성 후
  불변).
- `daily_call_state.json`: `{"date": "YYYY-MM-DD", "calls_used": N}` —
  틱마다 로드, 오늘 날짜와 다르면 리셋. 틱 처리 시 남은 예산 =
  `min(max_new_calls_per_tick, max_new_calls_per_day - calls_used)`. 0 이하면
  이번 틱은 캐시 히트 후보만 처리, 신규 판단 전부 스킵(다음 틱/다음날로
  자연 이월).
- 예산 소진으로 스킵된 후보는 버리지 않고 다음 틱에 다시 후보 목록에
  올라옴(캐시 미스 상태 유지) — 유실 없음.

**무료티어 계산 근거** (드래프트 24틱/일 × 틱당 5콜 최악케이스로 검토했던
결과, §5 참고): 일일 캡 30 설정 시 Tavily 30×30일=900/월(무료 1,000/월
대비 10% 마진), Groq 30콜×~1,000토큰≈30,000토큰/일(무료 TPD 100,000의
30%, RPD 1,000의 3%) — 양쪽 다 여유 있게 하한.

### 4.4 진입 판정 + 포지션/정산

- 캐시 히트든 신규 판단이든, `edge = ai_yes_prob - market_yes_price` 계산.
- `abs(edge) < min_edge` → 패스(진입 안 함, 로그만 남김).
- `edge >= min_edge` → YES 매수, `edge <= -min_edge` → NO 매수. 스테이크는
  기존 봇과 동일하게 `per_market_usd` 고정.
- 포지션 저장/정산(resolve 시 pnl 계산)은 `polymarket_bot.py`의 기존
  포지션 관리 로직과 동일 패턴 재사용(파일만 독립 — 로직 재작성 안 함).
- 예산(`budget`)·`max_positions`도 기존 봇과 동일 필드명으로 별도 상태에서
  관리 — `polymarket_bot`/`sharp_wallet_bot`과 자본 공유 없음.

### 4.5 등록 (`api_server/main.py`)

기존 sibling 봇 패턴 그대로:

```python
from api_server.polymarket_ai_bot import router as polymarket_ai_bot_router, start_loop as _polymarket_ai_bot_start
app.include_router(polymarket_ai_bot_router)
from api_server.polymarket_ai_bot import status as _polymarket_ai_bot_status
# 대시보드 PnL 집계 리스트:
{"id": "polymarket_ai_bot", "name": "Polymarket AI판단", "realized_pnl": _polymarket_ai_bot_status().get("realized_pnl", 0.0)},
# 시작 시:
_polymarket_ai_bot_start()
```

`id`가 `"polymarket"`으로 시작해 `PortfolioTab.tsx`(`id.startsWith("polymarket")`
필터)에 자동으로 HOME 폴리마켓 타일 합산에 잡힌다 — 프론트 추가 변경 불요.

### 4.6 `/polymarket` 대시보드 카드 (즉시 추가)

기존 배스킷/sharp_wallet 카드와 동일 포맷으로 신규 카드 1개: 예산/포지션수
/realized_pnl + 최근 판단 로그(질문, ai_yes_prob, market_price, edge, 진입
여부) 몇 줄. `lib/api.ts`에 `getPolymarketAiBotStatus()` 추가(raw fetch
금지 컨벤션), 새 컴포넌트 파일 없이 기존 카드 컴포넌트 재사용 가능하면
그걸 우선 재사용.

## 5. 비용/예산 근거 (Groq·Tavily 무료티어)

- **Groq 무료티어**(`llama-3.3-70b-versatile`, 2026-08 기준): 30 RPM /
  1,000 RPD / 12,000 TPM / 100,000 TPD.
- **Tavily 무료티어**(2026-08 기준): 월 1,000 크레딧(검색 1회=1크레딧).
- 드래프트 설정(틱당 캡 5, 캡 없는 일일 총량) 최악케이스 계산: 24틱/일 ×
  5 = 120콜/일 → Tavily 120×30일=3,600/월(무료한도 3.6배 초과), Groq
  토큰도 ~120,000/일로 TPD(100,000) 초과 — **틱당 캡만으론 Tavily가
  병목**이라 §4.3의 일일 캡(30) 도입 확정.
- 캐시 히트가 실제로는 대부분일 것(질문 텍스트 불변 마켓 재판정 없음) —
  위 계산은 순수 최악케이스(캐시 재사용 0) 기준 안전마진.

## 6. 검증 방법론

- v1은 **paper 전용**, 실집행 없음 — 프로젝트 전역 컨벤션 그대로.
- 최소 **N=20~30건** 정산(resolve) 누적 전엔 결론 안 냄(sharp_wallet 표본
  부족 반복 방지 컨벤션).
- 비교 기준선 2개: (a) 랜덤/무판단 베이스라인(같은 마켓 유니버스에서
  `random` side 대비), (b) 기존 `favorite`/`underdog` 대비 — 같은 마켓
  유니버스에서 AI 판단이 가격구조 신호보다 나은 엣지 있는지 직접 비교
  가능(파일 독립이라 3봇 동시가동 자체가 A/B 비교 인프라 겸함).
- 리포트는 별도 스크립트 없이 기존 `/status` + 대시보드 카드(§4.6)로
  충분 — 이 가설은 사람이 매 정산 로그를 직접 훑는 QA가 필요 없다(A타입
  함의판정과 달리 "맞았나/틀렸나"가 마켓 resolve로 자동 채점됨).

## 7. 실행모드 / Out of scope

- v1은 **paper-only**. 라이브 전환 조건: §6 N≥20~30건 누적 + 평균 pnl
  양수 + 기존 두 봇 대비 우위 확인. 미충족 시 무기한 paper 유지.
- 실주문/지갑 서명 — v1 전부 제외.
- Naver 검색 API — 이번 설계에서 제외(Tavily로 확정, §2 클래리파잉 답변).
- 판단 실패(JSON 파싱 실패 등) 시 재시도 로직 — v1 범위 밖, 그냥 패스
  하고 다음 틱에 캐시 미스 상태로 재시도됨(자연 재시도, 별도 코드 불요).
- `min_edge`(0.05) 등 임계값은 잠정치 — §6 검증 데이터 쌓이면 조정 대상.

## 8. 테스트 계획

- `tests/test_polymarket_ai_judgment_judge.py`: 캐시 히트/미스, 틱당 캡
  경계값, 일일 캡 경계값(날짜 롤오버 포함), Tavily/Groq 호출 실패 시
  패스(에러 삼키고 진입 안 함) 검증, JSON 파싱 실패 폴백.
- `tests/test_polymarket_ai_bot.py`: 후보 선정 필터(기존 `_scan_and_enter`
  필터 기준과 동일 동작), `min_edge` 미만 패스, edge 방향에 따른 YES/NO
  선택, 포지션/예산 독립성(다른 두 봇 상태에 영향 없음), `/status` 응답
  스키마.
