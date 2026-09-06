# 멀티시그널 통합 (서브프로젝트 B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `autopilot` 에이전트(실가동 페이퍼트레이딩)의 STEP 3 종목분석에 재무제표(회계장부) 참고 관점을 추가하고, 나머지 대시보드 기능 100+개를 실측/demo로 감사해 이후 배선 대상을 확정한다.

**Architecture:** 기존에 3회 검증된 레시피(console_api.py 실측 엔드포인트 → autopilot/tools/*.sh → CLAUDE.md STEP → pytest+curl 검증 → 양쪽 레포 커밋)를 재무제표에 적용. 병행해서 서브에이전트로 나머지 엔드포인트 전수 감사.

**Tech Stack:** FastAPI(`api_server/console_api.py`), 기존 `research/data/dart_financials.py`(KR/DART), Finnhub `stock/metric` API(US, 신규 wrapper), zsh+python3 tools 스크립트.

**Spec:** `docs/superpowers/specs/2026-09-06-multi-signal-integration-design.md`

## Global Constraints

- 모든 신규 fetch는 `_safe()` 래퍼로 감싸 예외 시 빈 값 폴백 — 에이전트 사이클을 절대 죽이지 않음.
- 매수/매도 결정 로직 추가 금지 — 전부 참고용 컨텍스트, 최종 판단은 `claude --print`의 LLM.
- 각 기능은 `pytest tests/ -q` 전체 그린(현재 베이스라인 1975 passed) + 실제 심볼/코드로 curl 스모크테스트 확인 후에만 커밋.
- `seokminal-multi-venue`와 `autopilot`은 별도 git 레포 — 각각 독립 커밋.
- Task 2 완료 시점에 STEP 3 하위 관점이 5개(A~E)가 됨 — 8개 넘기 전까지는 가드레일 재확인 불필요(스펙 §가드레일).

---

### Task 1: 대시보드 엔드포인트 전수 감사 (읽기전용)

**Files:**
- Create: `docs/superpowers/audits/2026-09-06-console-api-audit.md` (감사 결과 보고서, 서브에이전트 산출물을 이 경로에 저장)

**Interfaces:**
- Consumes: 없음(신규 조사)
- Produces: 감사 보고서 — Task 3(감사 시점엔 이 플랜에 없었으나, 감사 결과를 바탕으로 이후 이 플랜에 추가됨)가 참조할 `{endpoint, backing_module, data_source, symbol_scoped, trading_relevant, notes}` 표

- [x] **Step 1: 서브에이전트에 감사 위임**

`general-purpose` 서브에이전트(subagent_type: "general-purpose")에게 아래 프롬프트로 위임:

```
seokminal-multi-venue/api_server/console_api.py의 @router.get(...) 엔드포인트를 전부
grep -n '@router\.' 로 나열한 뒤(약 100개), macro-intelligence/insider-flow-live/
dart-events-live 3개는 이미 확인 완료라 건너뛰고, 나머지 각각에 대해:

1. 핸들러 함수를 읽고 실제 데이터를 만드는 backing 함수/모듈을 찾는다
   (jarvis/research_workflow/*.py 또는 research/data/*.py로 import해서 호출하는지,
   아니면 하드코딩된 dict/상수를 그대로 반환하는지 구분)
2. data_source를 REAL(외부 API/캐시 파일에서 실측 로드) / DEMO(하드코딩 상수) /
   MIXED(일부만 실측, 나머지 fallback demo)로 분류
3. symbol_scoped: 쿼리파라미터로 종목 단위 필터링 가능한지 (예/아니오)
4. trading_relevant: 개별 종목 매수/매도 판단에 실제 정보가치가 있는지
   (순수 운영 모니터링/거버넌스용 대시보드 엔드포인트는 아니오로 분류)
5. notes: 배선한다면 난이도/전제조건 한 줄

마크다운 표로 정리해서 보고. 코드 수정 금지 — 읽기 전용 조사만.
```

- [x] **Step 2: 보고서 저장**

서브에이전트 결과를 `docs/superpowers/audits/2026-09-06-console-api-audit.md`에 저장.

- [x] **Step 3: 커밋**

```bash
cd /Users/seokhun/seokminal/seokminal-multi-venue
git add docs/superpowers/audits/2026-09-06-console-api-audit.md
git commit -m "docs: console_api.py 100+ 엔드포인트 실측/demo 감사 보고서"
```

---

### Task 2: 재무제표(회계장부) 실측 배선 — KR(DART) + US(Finnhub)

**Files:**
- Modify: `api_server/console_api.py` (신규 `/console/financials-live` 엔드포인트)
- Create: `autopilot/tools/financials.sh`
- Modify: `autopilot/CLAUDE.md` (STEP 3에 E관점 추가, 도구 표에 행 추가)

**Interfaces:**
- Consumes: `research/data/dart_financials.py::load_cached(stock_code, year) -> dict | None`,
  `load_corp_codes() -> pd.DataFrame`, `fetch_one(corp_code, year) -> list[dict]`,
  `parse_financials(rows) -> dict` (모두 기존 함수, 시그니처 변경 없음)
- Produces: `GET /console/financials-live?code=005930` (KR) 또는 `?symbol=AAPL` (US) →
  `{code|symbol, year?, total_assets, total_liab, total_equity, sale, op_profit,
  net_profit, ...}` (KR, DART 계정과목 기준) 또는 `{symbol, pe_ttm, roe_ttm,
  debt_to_equity, current_ratio, net_margin_ttm, revenue_growth_yoy}` (US, Finnhub 기준)

- [x] **Step 1: Finnhub 실제 응답 필드 확인 (US)**

먼저 실제 API를 한 번 호출해서 필드명을 확정한다 (Finnhub 무료 티어 `stock/metric` 응답
필드는 심볼/시점에 따라 존재 여부가 다를 수 있어 문서만 보고 짐작하지 않는다):

```bash
cd /Users/seokhun/seokminal/seokminal-multi-venue
KEY=$(grep '^FINNHUB_API_KEY=' .env | cut -d= -f2)
curl -s "https://finnhub.io/api/v1/stock/metric?symbol=AAPL&metric=all&token=$KEY" | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(sorted(d.get('metric',{}).keys()))"
```

출력된 실제 키 목록에서 아래 canonical 키에 매핑되는 실제 필드명을 확정한다:
PER(peNormalizedAnnual 계열), ROE(roeTTM 계열), 부채비율(totalDebt/totalEquityAnnual 계열),
유동비율(currentRatioAnnual 계열), 순이익률(netProfitMarginTTM 계열), 매출성장률(YoY 계열).
Step 2의 `_FINNHUB_FIELD_MAP` 값을 이 출력에 맞게 조정한다.

- [x] **Step 2: `console_api.py`에 엔드포인트 추가**

`@router.get("/company-intelligence")` 정의 바로 위에 추가 (기존 macro/insider/dart
엔드포인트들과 같은 블록):

```python
_FINNHUB_FIELD_MAP = {
    "pe_ttm": "peNormalizedAnnual",
    "roe_ttm": "roeTTM",
    "debt_to_equity": "totalDebt/totalEquityAnnual",
    "current_ratio": "currentRatioAnnual",
    "net_margin_ttm": "netProfitMarginTTM",
    "revenue_growth_yoy": "revenueGrowthTTMYoy",
}  # Step 1에서 실제 Finnhub 응답으로 확정한 필드명으로 교체


def _fetch_us_financials(symbol: str) -> dict | None:
    """Finnhub 기본 재무지표(무료 티어) 실측. 실패 시 None(호출부가 빈 값 폴백)."""
    import requests

    key = os.environ.get("FINNHUB_API_KEY", "")
    if not key:
        return None
    r = requests.get("https://finnhub.io/api/v1/stock/metric",
                      params={"symbol": symbol, "metric": "all", "token": key}, timeout=15)
    r.raise_for_status()
    m = r.json().get("metric", {}) or {}
    if not m:
        return None
    return {k: m.get(v) for k, v in _FINNHUB_FIELD_MAP.items()}


def _fetch_kr_financials(code: str) -> dict | None:
    """DART 재무제표(연간, 캐시 우선) 실측. 실패 시 None."""
    import datetime as _dt

    from research.data.dart_financials import fetch_one, load_cached, load_corp_codes, parse_financials

    year = str(_dt.date.today().year - 1)  # 최신 확정 사업연도(전년 사업보고서)
    cached = load_cached(code, year)
    if cached:
        return {"year": year, **cached}
    corp_df = load_corp_codes()
    row = corp_df[corp_df["stock_code"] == code]
    if row.empty:
        return None
    rows = fetch_one(row.iloc[0]["corp_code"], year)
    if not rows:
        return None
    return {"year": year, **parse_financials(rows)}


@router.get("/financials-live")
def financials_live_endpoint(symbol: str | None = None, code: str | None = None) -> dict:
    """회계장부(재무제표) 실측 — KR: DART(연간 사업보고서) / US: Finnhub 기본지표.
    매수/매도 신호 아님, 참고용. READ ONLY."""
    if code:
        real = _safe(lambda: _fetch_kr_financials(code.strip()))
        return {"code": code.strip(), **(real or {})}
    if symbol:
        real = _safe(lambda: _fetch_us_financials(symbol.strip().upper()))
        return {"symbol": symbol.strip().upper(), **(real or {})}
    return {}
```

- [x] **Step 3: API 재시작 + 실측 스모크테스트**

```bash
cd /Users/seokhun/seokminal/seokminal-multi-venue
bash scripts/restart_api.sh
curl -s "http://localhost:8000/console/financials-live?symbol=AAPL" | python3 -m json.tool
curl -s "http://localhost:8000/console/financials-live?code=005930" | python3 -m json.tool
```

Expected: 둘 다 하드코딩 demo가 아닌 실제 숫자(0이나 null이 아닌 자산총계/ROE 등) 포함.
비어있으면 Step 1 필드명 또는 DART corp_code 매핑을 재확인.

- [x] **Step 4: pytest 전체 회귀 확인**

```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q
```
Expected: 1975 passed(신규 실패 없음).

- [x] **Step 5: `autopilot/tools/financials.sh` 신설**

```bash
#!/bin/zsh
# Usage: financials.sh AAPL          (미국, Finnhub)
#        financials.sh --kr 005930   (한국, DART)
API="http://localhost:8000"

if [[ "$1" == "--kr" ]]; then
  QS="code=$2"
else
  QS="symbol=$1"
fi

echo "=== 재무제표: $1 $2 ==="
curl -s "$API/console/financials-live?$QS" | \
  /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c "
import json,sys
d=json.load(sys.stdin)
if len(d) <= 1:
    print('데이터 없음')
else:
    for k,v in d.items():
        if k not in ('symbol','code'):
            print(f'  {k}: {v}')
"
```

```bash
chmod +x /Users/seokhun/seokminal/autopilot/tools/financials.sh
zsh /Users/seokhun/seokminal/autopilot/tools/financials.sh AAPL
zsh /Users/seokhun/seokminal/autopilot/tools/financials.sh --kr 005930
```

- [x] **Step 6: `autopilot/CLAUDE.md` 배선**

도구 표에 행 추가 (`dart.sh` 행 바로 아래):

```markdown
| `financials.sh` | `zsh tools/financials.sh AAPL` / `zsh tools/financials.sh --kr 005930` | 재무제표(회계장부) 실측(미국 Finnhub/한국 DART) |
```

STEP 3에 E관점 추가 (D관점 블록 바로 아래):

```markdown
**E. 재무제표(회계장부) 관점**
```
zsh tools/financials.sh AAPL          # 미국
zsh tools/financials.sh --kr 005930   # 한국
```
- **참고용 컨텍스트**(매수/매도 신호 아님) — 이것만으로 결정하지 말 것
- 부채비율 급등/유동비율 급락 시 신규 진입 보류 검토
- 영업이익/순이익 전기 대비 급감(YoY 적자전환 등) 시 기존 포지션 리스크 재점검
```

매수 신호 목록 아래에 한 줄 추가:

```markdown
- (STEP 3E 재무제표 부채비율 급등/적자전환 있으면 신규 진입 보류 검토)
```

- [x] **Step 7: 커밋 (양쪽 레포)**

```bash
cd /Users/seokhun/seokminal/seokminal-multi-venue
git add api_server/console_api.py
git commit -m "feat: /console/financials-live 실측 배선 (KR DART / US Finnhub)"

cd /Users/seokhun/seokminal/autopilot
git add CLAUDE.md tools/financials.sh
git commit -m "feat: STEP 3E 재무제표(회계장부) 관점 추가"
```

- [x] **Step 8: progress.md 기록 (양쪽 레포)**

`seokminal-multi-venue/docs/progress.md`에 새 세션 로그 항목, `seokminal-dashboard/docs/progress.md`에 새 Phase 항목 — 기존 macro/insider/dart 항목과 동일 형식으로 완료 내용 + 커밋 해시 기록.

---

## Task 3+: 결정 경과 (2026-09-06)

Task 1·2 완료 + 최종 리뷰(fix 1회 포함) CLEAN 후, 감사 보고서의 "배선 우선순위 후보"
(전략 단위 5개: `/fusion`/`/overlay`/`/investment-os`/`/forward-learning`/`/monthly-review`,
빠른 전환 후보 3개: `/sector-intelligence`/`/company-intelligence`/`/company-monitor`)를
사용자에게 제시.

**Ruling A (사용자 선택 옵션 2 → 조사 후 기각):** 사용자가 처음 전략 단위 5개(옵션 2)를
선택했으나, read-only 조사 결과 `jarvis.registry`(96개 계량전략, 신호 나오는 건 선물
TSMOM류 + 한국 자사주매입/월초효과 4개 전략뿐)와 `autopilot`(registry 미등록, 별도
스크리너로 임의 종목 스윙매매)이 **개념적으로 별개 시스템** — 5개 엔드포인트 응답은 전부
`strategy_id` 키 기준이고 종목(symbol) 필드 자체가 없어 종목 필터로 좁힐 자연스러운
교집합이 없음(단순 난이도 문제 아님). 이 사실을 사용자에게 보고 → 사용자가 옵션 1(빠른
전환 3개)로 재선택.

**Ruling B (사용자 선택 옵션 1 중 `/sector-intelligence` 제외):** 빠른 전환 3개 착수 전
`console_api.py`/`jarvis/research_workflow/{company_monitor,company_intelligence,
sector_intelligence}.py` 실제 코드 확인 결과 `/sector-intelligence`는 다른 둘과 패턴이
다름 — `company`/`entity` 같은 종목 파라미터가 아예 없고(`sector` 파라미터만 받음),
데모 데이터도 가짜 재무(`eps 0.5/0.62`)가 아니라 정적 3-섹터 seed(`_SECTOR_SEED`:
semiconductor/ai_infra/tech)라 재무제표 헬�를 꽂을 지점이 없음. 실제 REAL 전환에는
섹터/ETF 구성종목 데이터소스가 새로 필요해 "재무 헬퍼 재사용" 범위를 벗어남 —
**이번 Task 3에서 제외**, 별도 스파이크로 남김(감사서에 이미 "패턴 기반, 미상세 확인"
경고가 있던 항목과 같은 성격). Task 3는 `/company-monitor`·`/company-intelligence`
2개로 축소.

**Ruling C (autopilot CLAUDE.md 미변경):** `/company-monitor`/`/company-intelligence`가
내부적으로 재사용하는 `news_pipeline`/`ownership_pipeline`/`earnings_intelligence`는
이미 autopilot STEP 3C(뉴스)·3D(내부자/공시)·3E(재무제표)가 각각 커버 중인 정보와
겹친다. 이 둘을 autopilot에 새 STEP으로 추가하면 같은 정보를 다른 포맷으로 한 번 더
묻는 중복 호출이 되어 STEP 3 비용 가드레일(스펙 §가드레일, 사이클당 도구 호출 수)에
반하는 효과만 있음 — **이번 Task는 대시보드(`console_api.py`) 응답을 실측으로 바꾸는
것에 한정하고 `autopilot/CLAUDE.md`는 건드리지 않는다.**

### Task 3: `/company-monitor`, `/company-intelligence` 실측 재무 필드 부착

**Files:**
- Modify: `api_server/console_api.py:1578-1586`(`/company-monitor`), `1814-1822`(`/company-intelligence`)
- Modify: `docs/superpowers/audits/2026-09-06-console-api-audit.md`, `docs/progress.md`,
  `seokminal-dashboard/docs/progress.md` (Step 5/6에서 갱신)

**Interfaces:**
- Consumes: Task 2가 이미 만든 `_fetch_us_financials(symbol) -> dict | None`,
  `_fetch_kr_financials(code) -> dict | None`(둘 다 모듈 상단, 시그니처 변경 없음)
- Produces: 두 엔드포인트 응답에 신규 top-level 키 `financials_live`(symbol/code 쿼리파라미터
  준 경우만 채워짐, 없으면 응답 구조 기존과 동일 — 하위호환)

**설계 메모(왜 기존 `financials=[...]` 파라미터에 안 꽂는지):** `company_monitor.update()`가
내부적으로 넘기는 `financials=[{"expected":{"eps":0.5},"actual":{"eps":0.62}}]`는
`earnings_intelligence.analyze_earnings()`가 "기대 vs 실제 서프라이즈"를 계산하는 용도
(애널리스트 컨센서스 vs 실제 실적). Finnhub/DART 헬퍼가 주는 건 컨센서스 추정치가 아니라
현재 시점 실측 비율(P/E·ROE·부채비율 등)이라 이 파라미터의 "expected" 자리에 넣을 게
없음 — 억지로 끼워맞추면 의미 왜곡. 대신 완전히 별도 필드로 붙여서 진짜 실측 데이터임을
명확히 구분한다. 기존 `financials=[eps 0.5/0.62]` 하드코딩은 예시 데모로 그대로 둔다
(제거는 이번 Task 범위 밖 — earnings-surprise 예시 로직 자체는 이번 변경과 무관).

- [x] **Step 1: `/company-monitor`에 `symbol`/`code` 쿼리파라미터 + `financials_live` 부착**

`api_server/console_api.py:1578-1586`을 아래로 교체:

```python
@router.get("/company-monitor")
def company_monitor(company: str = "", symbol: str | None = None, code: str | None = None) -> dict:
    """P143 — CompanyUpdateReport(재무·실적·뉴스·소유 변화·영향·우선순위). 신호 아님. READ ONLY.
    symbol(US)/code(KR) 주면 financials_live에 실측 재무지표(Finnhub/DART) 부착."""
    def _run():
        name = (company or "NVDA").strip()
        from jarvis.research_workflow.company_monitor import update
        result = update(name, financials=[{"company": name, "expected": {"eps": 0.5},
                      "actual": {"eps": 0.62}}], headlines=[{"text": f"{name} product news", "entity": name}])
        if code:
            result["financials_live"] = _safe(lambda: _fetch_kr_financials(code.strip()))
        elif symbol:
            result["financials_live"] = _safe(lambda: _fetch_us_financials(symbol.strip().upper()))
        return result
    return _safe(_run, {"events": []}) or {}
```

- [x] **Step 2: `/company-intelligence`에 동일 패턴 적용**

`api_server/console_api.py:1814-1822`을 아래로 교체:

```python
@router.get("/company-intelligence")
def company_intelligence_endpoint(entity: str = "TSMC", symbol: str | None = None,
                                  code: str | None = None) -> dict:
    """P154 — CompanyIntelligenceReport(관계·이벤트·재무·교훈·리스크). 매수/매도 신호 아님. READ ONLY.
    symbol(US)/code(KR) 주면 financials_live에 실측 재무지표(Finnhub/DART) 부착."""
    def _run():
        name = (entity or "TSMC").strip()
        from jarvis.research_workflow.company_intelligence import analyze_company
        result = analyze_company(name, financials=[{"company": name, "expected": {"eps": 0.5},
                               "actual": {"eps": 0.62}}], headlines=[{"text": f"{name} news", "entity": name}])
        if code:
            result["financials_live"] = _safe(lambda: _fetch_kr_financials(code.strip()))
        elif symbol:
            result["financials_live"] = _safe(lambda: _fetch_us_financials(symbol.strip().upper()))
        return result
    return _safe(_run, {"relationships": {}}) or {}
```

- [x] **Step 3: API 재시작 + 실측 스모크테스트**

```bash
cd /Users/seokhun/seokminal/seokminal-multi-venue
bash scripts/restart_api.sh
curl -s "http://localhost:8000/console/company-monitor?company=AAPL&symbol=AAPL" | python3 -m json.tool
curl -s "http://localhost:8000/console/company-monitor?company=삼성전자&code=005930" | python3 -m json.tool
curl -s "http://localhost:8000/console/company-intelligence?entity=AAPL&symbol=AAPL" | python3 -m json.tool
curl -s "http://localhost:8000/console/company-monitor" | python3 -m json.tool
```

Expected: 처음 3개는 `financials_live`에 null 아닌 실측 값(P/E·ROE 또는 자산총계 등) 포함.
마지막(파라미터 없음, 기존 호출 방식)은 `financials_live` 키 자체가 응답에 없어야 함
(하위호환 — 기존 대시보드 호출부가 깨지지 않는지 확인).

- [x] **Step 4: pytest 전체 회귀 확인**

```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q
```
Expected: 1975 passed(신규 실패 없음).

- [x] **Step 5: 감사 보고서 갱신**

`docs/superpowers/audits/2026-09-06-console-api-audit.md`의 `/company-monitor`,
`/company-intelligence` 행(92행, 100행)을 `data_source: DEMO → MIXED`로 갱신하고,
`/sector-intelligence`가 Task 3 범위에서 제외된 이유(위 Ruling B)를 "남은 우려" 절
바로 위에 짧게 추가.

- [x] **Step 6: 커밋 + 기록**

```bash
cd /Users/seokhun/seokminal/seokminal-multi-venue
git add api_server/console_api.py docs/superpowers/audits/2026-09-06-console-api-audit.md
git commit -m "feat: company-monitor/company-intelligence에 실측 재무(financials_live) 부착"
```

`seokminal-multi-venue/docs/progress.md`, `seokminal-dashboard/docs/progress.md`에
기존 Phase 형식으로 완료 항목 추가(별도 커밋 또는 위 커밋에 포함, 기존 관행대로).

**Task 3 이후:** `/sector-intelligence` REAL 전환과 5개 전략 엔드포인트 건은 이번
플랜 범위 밖으로 확정 종료(위 Ruling A/B). 이 플랜은 Task 3 완료 + 리뷰 클린을 끝으로
종료한다.
