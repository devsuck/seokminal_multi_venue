# 논문 기반 알파 마이닝 파이프라인 — Design Spec

**작성:** 2026-07-15. 유럽 거시경제 캘린더 트랙은 유저가 스코프 접음(EUREX
IB 커버리지 없음, 비용 대비 가치 낮다고 판단). 대체 아이디어로 전환: arXiv
논문을 자동으로 읽어 백테스트 가능한 가설로 변환하는 파이프라인.

## 1. 배경

지금까지 `research/hypotheses/*`의 모든 가설은 사람(컨트롤러/유저)이 직접
설계·코딩했다. 이번 트랙은 처음으로 "논문에서 가설을 뽑아내는" 상류 소스를
자동화한다 — 병목이던 "논문 읽는 시간"을 없애는 게 목적이고, 통계적 품질관리
(랜덤베이스라인 p-value, BH-FDR 신규격리풀)는 기존 컨벤션 그대로 유지한다.

## 2. 소스 — arXiv (SSRN 아님)

SSRN은 공식 API 없고 본문 대부분 유료(초록만 무료) — 자동화하려면 스크레이핑인데
ToS 걸림. **arXiv q-fin(PM/TR/ST/CP)** 섹션은 본문 전체 무료 + 공식 API 있음,
계량투자 논문도 다수 게재됨. 법적으로 깨끗한 arXiv로 소스를 확정한다.

## 3. 자동화 정도 — 완전자동 + 다단계 필터

가설 코드까지 LLM이 통짜로 생성한다(반자동 대비 사람 개입 없음). BH-FDR는
원래 "후보 많이 던지고 통계로 거른다" 용도라 완전자동+대량후보 자체는 문제
없음 — alpha 고정, 신규 격리풀 유지하면 후보가 늘수록 오히려 검출력이 오른다.

**진짜 위험은 "저질가설"이 아니라 "버그 있는 코드가 우연히 유의하게 나오는
것"** (참고: whale-tracking Task 3에서 `build_price_series` 그리드 계산
floor-division 버그를 사람이 리뷰 중 발견한 전례 있음 — 자동화하면 이
안전망이 사라진다). 그래서 통계게이트(BH-FDR) 앞에 싼 필터 2단계를 둔다:

1. **자산커버리지 필터** — 논문이 요구하는 자산군이 지금 데이터로 검증
   가능한지 확인. 검증 불가능한 가설을 코드생성까지 보내는 건 낭비.
2. **코드 정합성 스모크체크** — 생성된 시그널함수가 크래시 없이 돌아가고,
   시그널이 전부 NaN/상수가 아닌지 확인. 비싼 random-baseline p-value
   검증을 태우기 전에 싼 걸로 먼저 거른다.

## 4. v1 스코프 — equity intraday 한정 (확장 가능한 스키마)

기존 `research/hypotheses/runner.py`가 이미 완성된 제네릭 검증엔진이다 —
시그널함수 시그니처 `(ohlc, feat, aux, params) -> {"entry": bool[], "eligible": int[]}`
만 맞추면 이벤트백테스트+random베이스라인+BH-FDR+OOS분할이 전부 공짜로
붙는다(미국 유동주식+섹터벤치마크, `research/data/pull_intraday.py::DEFAULT_UNIVERSE`,
15분봉). 크립토/선물/폴리마켓은 전부 각자 커스텀 러너라 자동생성 대상으로
쓰기엔 배선방식이 제각각이고 위험이 크다(TSMOM류는 entry/eligible bool
시그널 형태 자체가 안 맞음).

**결정:** v1은 `equity_intraday` 자산군만 코드생성 대상으로 삼는다. 단,
논문 파싱 단계의 구조화 스펙 스키마는 자산군 무관하게 설계한다(`asset_class`
필드를 항상 채우되, 코드생성기는 `equity_intraday`일 때만 연결). 이러면
나중에 크립토/선물 확장할 때 파싱단은 안 건드리고 코드생성기만 추가하면
된다 — v1 안전성과 미래 확장성을 동시에 얻는 절충안.

## 5. 아키텍처

```
research/papers/arxiv_fetcher.py     ← arXiv API 일별 폴링, 커서 dedup, PDF→텍스트
research/papers/extract_spec.py      ← LLM: 논문텍스트 → 구조화 스펙(JSON)
research/papers/coverage_filter.py   ← 순수함수: asset_class=="equity_intraday"만 통과
research/papers/codegen_signal.py    ← LLM: 스펙 → SignalFn 코드 생성
research/papers/smoke_check.py       ← 생성코드 exec + fixture OHLC로 크래시/degenerate 체크
research/run_paper_ingest.py         ← 위 5단계 orchestration, 1회성 트리거(cron 아님)
research/run_paper_hypothesis_validate.py  ← research/hypotheses/papers/*.py 모아 runner.py 엔진 태움
```

### 데이터 흐름

```
arXiv 신규논문(커서 이후만)
  → PDF 텍스트 추출
  → extract_spec: LLM → {asset_class, signal_description, direction,
                          holding_period, data_requirements}
  → coverage_filter: equity_intraday만 통과, 나머진 사유와 함께
                      research/data/paper_pipeline/rejected.jsonl에 기록
  → codegen_signal: LLM → SignalFn 코드
                     (few-shot: 기존 research/hypotheses/strategies.py 예시)
    → research/hypotheses/papers/<arxiv_id>_<slug>.py 저장
      (모듈 docstring에 arXiv ID·제목·원 논문 링크 — 추적성 확보)
  → smoke_check: 크래시/전부-None/전부-False/NaN 체크
    → 실패 시 discard, 사유를 rejected.jsonl에 기록(파일은 지움)
    → 통과 시 파일 유지
  → (별도 실행) run_paper_hypothesis_validate.py:
      통과분 전체를 runner.py 엔진에 태움 → 신규 격리 BH-FDR 풀(paper 전용,
      기존 가설 풀과 절대 안 섞음) → CANDIDATE/REJECT
```

## 6. LLM 호출 — Claude Code CLI 서브프로세스 (신규 API 키 불필요)

기존 `ai_strategy/advisor.py`는 Groq(`llama-3.1-8b-instant`)를 쓰지만, 논문
파싱+코드생성은 그보다 훨씬 무거운 작업이라 8B 모델로는 불안정하다. 새
Anthropic API 키를 발급하는 대신 **이미 인증된 Claude Code CLI를 서브프로세스로
호출**한다:

```python
# research/papers/llm_cli.py
import subprocess

def call_claude(prompt: str, timeout: int = 300) -> str:
    """Claude Code CLI 헤드리스 호출. 툴 접근 없이 순수 텍스트생성만
    (파일쓰기는 호출측 스크립트가 직접 함 — codegen 결과도 문자열로만 받는다)."""
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--allowedTools", ""],
        capture_output=True, text=True, timeout=timeout, check=True,
    )
    return result.stdout
```

`extract_spec.py`/`codegen_signal.py` 둘 다 이 래퍼를 쓴다. 신규 키 발급
없이 지금 세션과 동일한 구독/인증을 재사용 — 배치(일단위) 처리라 논문당
서브프로세스 하나씩 뜨는 지연은 문제 없음.

## 7. 케이던스

arXiv는 일단위 다이제스트라 24/7 tmux 폴러가 필요 없다. `run_paper_ingest.py`는
1회성 트리거 스크립트로 만들고, 실제 OS-level cron 등록(launchd 등)은 이번
스펙 범위 밖 — 필요해지면 별도로 정한다.

## 8. 신규 의존성

PDF 텍스트 추출 라이브러리가 지금 없음 — `pdfplumber`(순수 파이썬, 시스템
의존성 없음) 추가. `pyproject.toml`에 등록.

## 9. 에러 처리

- arXiv fetch 실패: 재시도/백오프(기존 콜렉터 패턴), 커서 유지, 다음 사이클
- LLM CLI 논스토어/malformed JSON: 로그+스킵, 배치 전체는 안 죽음
- codegen 결과 문법오류(exec 실패): smoke_check에서 걸러짐 → discard, 사유 로그
- smoke_check 실패(크래시/degenerate): discard, 사유 로그
- 전부 `research/data/paper_pipeline/rejected.jsonl`에 감사기록 — 완전자동
  파이프라인이라 "왜 이 논문은 안 됐지" 나중에 확인 가능해야 함

## 10. 테스트 계획

- `tests/test_arxiv_fetcher.py`: 커서 dedup, fetch 재시도/백오프(HTTP mock)
- `tests/test_coverage_filter.py`: equity_intraday 통과/나머지 자산군 차단
  (순수함수, synthetic 스펙으로 직접 테스트)
- `tests/test_smoke_check.py`: 정상 SignalFn 통과, 크래시 코드 차단, 전부-False
  시그널 차단, NaN 시그널 차단(순수함수, fixture OHLC + 합성 SignalFn)
- `tests/test_llm_cli.py`: subprocess.run patch, stdout 파싱만 검증(라이브
  CLI 호출 없음)
- `tests/test_run_paper_hypothesis_validate.py`: 빈 입력 시 verdict 필드
  존재 확인 등 최소 스모크(기존 validate 러너 테스트 패턴 따름)

라이브 arXiv fetch/Claude CLI 호출은 테스트에서 하지 않음(기존 컨벤션).

## 11. Out of scope

- 크립토/선물/폴리마켓 자산군 코드생성 — 스키마는 준비하되 v1 코드생성기는
  equity_intraday만 연결(4절 참조)
- OS-level cron 자동 스케줄링 — 수동 트리거만(7절 참조)
- 생성된 가설이 CANDIDATE 판정을 받아도 라이브 집행은 기존 Jarvis
  arm_criteria(최소 페이퍼 기간) 게이트를 그대로 통과해야 함 — 이 파이프라인은
  가설 생성·검증까지만, 집행 경로는 건드리지 않음
