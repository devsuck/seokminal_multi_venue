# Progress Log

> 이 파일은 세션 간 작업 맥락을 이어주는 용도입니다.
> 새 세션 시작 시: `@docs/progress.md @CLAUDE.md 읽고 이어서 작업해줘`

## 세션 로그 (2026-08-02 계속 2) — ICT/LTF 웹소켓 진짜 근본원인 확정 + 해결

이전 세션 정정(바로 아래 섹션)에서 "로그도 완전 공백, sudo py-spy 필요, 근본원인 미확정"으로 남긴 부분을 이어서 조사. 유저 지시 없이 자율 진행("계속해줘").

### 정정의 정정 — "로그 공백"은 오진이었음
- 이전 세션이 `tmux capture-pane`으로 확인한 게 원인 — 실제 tmux 실행 커맨드는 `... > /tmp/ict_debug.log 2>&1`로 stdout을 파일로 리다이렉트하고 있어서 pane 자체는 항상 빈 게 정상. `/tmp/ict_debug.log`를 직접 열어보니 재기동 이후 계속 재시도 중이었고(628회 `LTF 스트림 오류` 로그, 5→10→20→40→60s 백오프 정상 순환), 매번 `TimeoutError: timed out during opening handshake` — `websockets` 내부 `open_timeout`이 `loop.getaddrinfo`(asyncio 자체 DNS resolver, 공유 default executor 경유)의 `CancelledError`를 감싸 발생.

### 진짜 근본원인
- `sudo py-spy` 없이 실측으로 좁힘: 프로세스 kill 없이 새 셸에서 fresh 프로세스로 `loop.getaddrinfo('api.hyperliquid.xyz', 443)` 단발/40회 반복 테스트 — 전부 5ms 이내 성공. 반면 라이브 `ict-orderflow-paper` 프로세스는 재기동해도(4번째) 100% 재현되는 타임아웃(총 828회 관측, gaierror 포함) — **asyncio 자체 resolver(`loop.getaddrinfo`, 공유 default executor 경유)가 이 프로세스/환경 조합에서만 막힘**. 반면 HTF 폴링(`fetch_htf_bars`)이 쓰는 `research/net_utils.py`의 순수 스레드 기반 resolver(공유 executor 안 씀, 매 호출 새 `threading.Thread`)는 같은 호스트로 그 사이 계속 성공 — HTF 소켓은 매번 정상 ESTABLISHED 확인됨.
- 즉 문제는 DNS/네트워크 자체가 아니라 **asyncio 공유 executor를 거치는 resolver 경로 하나만** 이 환경에서 막히는 것. (스레드 풀 고갈 가설도 검증했으나 기각 — `ps -M`으로 스레드 수 확인 결과 4개뿐, 누수 아님. 정확한 OS 레벨 원인은 여전히 미확정이지만 우회로 실용적 해결.)

### 수정 (커밋 전, 아래 "변경된 파일" 참고)
- `orderflow/hl_adapter.py`: connect 직전에 `research/net_utils.call_with_hard_timeout` + `socket.getaddrinfo`(HTF와 동일한 순수 스레드 방식)로 IP를 직접 resolve, `websockets.connect(url, host=<resolved_ip>, server_hostname=<원래 호스트>)`로 넘겨 asyncio 자체 resolver 경로(`loop.create_connection`의 `_ensure_resolved`)를 완전히 우회 — `host`가 이미 IP 리터럴이면 asyncio가 `getaddrinfo` 자체를 안 부르는 걸 CPython 소스(`base_events.py::_ensure_resolved` → `_ipaddr_info`)로 확인 후 적용. `server_hostname`은 TLS SNI/인증서 검증용, HTTP Upgrade의 Host 헤더는 URI 자체가 안 바뀌어서 자동으로 올바르게 유지됨.
- 연결 수명주기 가시성 부재도 이번 조사를 오래 끈 원인이라 판단 — `resolving`/`connected`/최초 3개+매 200개마다 메시지 로그를 `logging.info`로 추가(운영 관측용, 디버그용 임시 코드 아님).
- `tests/test_orderflow_hl_adapter.py`: `resolve_fn` 주입 지원하도록 fake들 갱신 + resolve 실패가 기존 재연결 루프로 전파되는지 확인하는 회귀 테스트 1개 추가.

### 실측 검증
- `ict-orderflow-paper` 재기동 후 로그: `resolved api.hyperliquid.xyz -> 18.66.192.82, connecting` → `connected` → 실제 `l2Book`/`trades` 메시지 수신 확인(200개 메시지 90초 내 도달, `subscriptionResponse` 정상 ack 포함). 이전엔 100% 실패했던 게 즉시 성공으로 전환.
- `pytest tests/` 전체 2083 passed(pre-existing 실패 없음).

### 변경된 파일
- `orderflow/hl_adapter.py`, `tests/test_orderflow_hl_adapter.py`

### 다음 세션 확인
- 저널이 실제로 채워지기 시작하는지 관찰 재개(N/30 보고, 사용자 명시 요청) — **연결 복구 후 2/30 확인**(2026-08-02T15:13 신규 short CISD+OB 엔트리, +0.21R).
- 이번 우회가 임시방편인지 근본해결인지는 좀 더 지켜봐야 함 — asyncio resolver가 왜 이 환경에서만 막히는지 OS 레벨 원인은 여전히 미상, 재발하면(다시 100% 타임아웃 패턴 보이면) 우회 자체도 뚫릴 수 있음, sudo py-spy로 확인은 여전히 유효한 차기 옵션.

### 다른 collector들 점검 (같은 세션, 계속)
- 나머지 11개 tmux collector(polymarket 계열, cross-venue-skew, hl-orderflow-tick 등) pane 확인 — DNS 실패(`Errno 8`)/타임아웃 로그가 마지막 줄에 남아있었으나, 프로세스 CPU 시간이 계속 누적 중이고 방금 재확인한 `socket.getaddrinfo`가 즉시 성공 → **일시적 DNS 블립이 이미 복구된 과거 로그**로 판단(ict 엔진처럼 100% 재현되는 영구정지 패턴 아님). 별도 조치 안 함, 다음 세션에 재발 여부만 가볍게 재확인.

## 세션 로그 (2026-08-02 계속 3) — 봇 라이브 포지션(GOOGL/NVDA) 미실현 PnL 0 버그 수정

유저 리포트: "몇 개 봇이 구글/엔비디아 샀는데 현재가 반영이 안 돼서 PnL 0으로 뜬다."

### 원인
- `api_server/routers/agents.py`의 `_latest_price()`(구 172-187행)가 에이전트의 실제 체결 venue(IB live/HL/Alpaca paper)와 무관하게 **무조건 Alpaca REST**로만 현재가를 조회하고 있었음.
- IB로 라이브 체결된 GOOGL/NVDA 포지션은 Alpaca 쪽에 데이터가 없어 `_latest_price`가 매번 조용히 실패(`except Exception: return None`) → `agent_performance()`의 `unrealized` 합계가 초기값 `0.0`에서 한 번도 안 늘어난 채 그대로 반환됨. "가격 못 가져옴"과 "진짜 PnL 0"이 구분 안 되고 똑같이 $0.00으로 뜸.

### 수정
- `api_server/routers/agents.py`: `agent_performance()`에서 에이전트 venue(`profile.venue` 또는 KR/US 기본값) + `enforce_paper()` 판정을 보고 가격 소스를 분기.
  - HL 에이전트 → `_hl_latest_prices()`(hyperliquid `get_candles` 마지막 봉 종가, 신규 헬퍼)
  - 라이브(비페이퍼) US 에이전트 → `_ib_latest_prices()`(IB `get_intraday_bars`+`score_intraday`, `_daytrade_tick_locked`의 IB 실행 루프와 동일 패턴 재사용, 신규 헬퍼)
  - 그 외(페이퍼/KR 등) → 기존 `_latest_price()`(Alpaca) 그대로 유지
- `tests/test_agent_performance_api.py`: 라이브 US 에이전트가 IB 경로를 타고(Alpaca 안 타는지까지 단언) `unrealized_pnl`이 정확히 계산되는지 확인하는 회귀 테스트 1개 추가.
- 검증: `pytest tests/` 2084 passed(pre-existing 실패 없음).
- **주의**: 지금 이 환경엔 TWS/IB Gateway가 안 떠 있음(`lsof -i :7496/:7497` 빈 결과) — 이 우회 자체는 라이브 검증 못 했고 코드 경로/유닛테스트로만 확인. 유저 실제 환경(TWS 켜진 상태)에서 진짜로 현재가가 뜨는지 확인 필요.

### 변경된 파일
- `api_server/routers/agents.py`, `tests/test_agent_performance_api.py`

### 다음 세션 확인
- TWS 켜진 상태에서 실제로 GOOGL/NVDA 미실현 PnL이 뜨는지 라이브 확인.
- KR 에이전트는 여전히 Alpaca 경로라 KR 종목(`005930.KS` 등) 현재가도 못 가져올 가능성 있음 — 이번엔 스코프 밖(유저가 US/IB만 언급), 재발하면 KR 전용 가격 소스(KIS?) 연결 필요.

---

## 세션 로그 (2026-08-01) — 릴리스감사 Phase1 완료 확인 (STEP4 + D클러스터)

이전 세션(들)에서 진행된 릴리스감사 Phase1 STEP4 작업 2건이 이 파일에 기록 안 된 채 커밋만 남아있던 걸 발견 → 상태 검증 후 기록.

### 확인된 완료 작업 (커밋은 이미 있었음, 기록만 누락)
- `990c1ea` — 죽은 거버넌스/유틸리티 스캐폴딩 32개 `git rm` (`docs/phase1/module_inventory_phase1.json` REMOVE_CANDIDATE 91개 중 독립 유틸리티 클러스터: benchmark/cache/compliance/concurrency/continuous_learning/data_governance/data_infrastructure/dependency/diagnostics/documentation/emergency/experiment_manager/experiment_orchestration/facades/integrity/knowledge_sharing/license/model_management/observability/operational_audit/operations/operations_console/performance/profiling/resilience/sbom/security/self_audit_intelligence/self_improvement_intelligence/simulation_environment/threat_model/workflow_automation)
- `ae7d429` — D클러스터 5개(`release_candidate`/`security_audit`/`production_review`/`system_integration`/`architecture_docs`) archive 마킹. `docs/phase1/research_namespace_inventory.md`가 STEP5로 분리 계획했던 "죽은 감사도구 archive(security_audit 클러스터 포함)"가 이 커밋으로 흡수되어 실행 완료됨 — 별도 STEP5 불필요.

### 이번 세션에서 한 것 — 완료 상태 검증만 (코드 변경 없음)
- `docs/phase1/module_inventory_phase1.json` 109개 모듈 전체를 `git ls-files`로 대조: REMOVE_CANDIDATE 91개 전부 git 미추적(삭제 완료), ARCHIVE 13개 전부 `__init__.py`에 ARCHIVED 마커 확인. Phase1 전체 스코프 100% 처리 완료 확정.
- `pytest tests/ -q` **2031 passed**, `jarvis.research_workflow.governance.validate_all()` 전 도메인 `passed: true`, `seokminal-dashboard`에서 `npx tsc --noEmit` clean — STEP3-B 체크리스트가 요구하는 검증 3종 전부 사후 통과 확인.
- `jarvis/benchmark` 등 REMOVE된 디렉토리에 `__pycache__`/컴파일된 `.pyc` 잔해가 파일시스템에 남아있음 발견 — `.gitignore`로 무시되는 순수 바이트코드 캐시라 무해, git 상태엔 영향 없음(정리 안 함).

### 다음 할 일
- [x] 로컬 브랜치(`claude/polymarket-wallet-scoring-awzj6n`)가 origin보다 8커밋 앞섬 — push 여부 사용자 확인 필요 → 2026-08-02 병합+push 완료, 아래 세션 로그 참고
- [ ] whale 원장 계속 쌓이는 대로 리더보드/self-score 재검증(표본 늘어야 결론 남)
- [ ] ICT/orderflow 저널 진행 — 계속 관찰(사용자 명시 요청: 채워질 때마다 N/30 보고)
- [ ] cross-venue-skew 데이터 수집됐지만 validation 스크립트 아직 미실행 — 다음 세션 후보

---

## 세션 로그 (2026-08-02) — sharp_wallet 집행봇 SDD 병합 + 검증기 재검증

### 완료된 작업
- **sharp_wallet 집행봇 SDD 실행계획(2026-08-02) 6개 태스크 전부 완료**: CLOB 클라이언트, positions API, 진입/청산 봇 로직, tick/loop/라우터, 리스크가드, `/lab/health` 회계 불변식. 최종 브랜치 리뷰에서 Critical 1건(outcomeIndex 미반영 — sharp wallet이 No 매수해도 direction=+1로 기록돼 봇이 반대방향 진입, 588건 중 323건 영향) + Important 3건 발견 → fix round 1건으로 전부 해결, 재리뷰 클린. 전체 스위트 2072 passed.
- **`claude/polymarket-wallet-scoring-awzj6n` → main 병합+push**(fast-forward, d63b6c5). origin과 동기화 완료.
- **검증기(`run_polymarket_sharp_wallet_validate.py`) 재검증**: 최종 브랜치 리뷰에서 별도 발견된 `build_price_series` outcome 혼입 버그(같은 마켓 Yes/No 두 토큰 체결이 하나의 가격 시계열에 섞임 — 2689개 마켓 중 1512개가 양쪽 다 거래돼 영향) 수정. `build_price_series`에 `outcome_index` 필터 추가, `build_labels_multi_horizon` 조회키를 `(condition_id, outcome_index)`로 변경, outcome_index가 {0,1} 밖인 anchor는 라벨링에서 제외. 커밋 9677cce, push 완료.
  - A/B 비교(현재 데이터 n=5178, 수정전/후 코드로 동일 데이터셋 각각 재실행): 수정 전 BH-FDR survivors 14/18(bucket 8/9, tercile 6/9) wf_pass 10/14, 수정 후 18/18(bucket 9/9, tercile 9/9) wf_pass 7/18. verdict는 양쪽 다 `paper_candidate_forward_test_required`(추가 수집분 때문에 이미 다운그레이드 상태였고 이 수정 자체가 원인 아님, old코드+현재데이터로 별도 확인함).
  - 결론: outcome 혼입 수정으로 신호가 더 넓은 그룹에서 BH-FDR 생존하지만 walk-forward 안정성은 오히려 하락. **라이브 전환 근거는 여전히 부족 — paper 유지, 계속 관찰.**

### 변경된 파일
- `api_server/polymarket_sharp_wallet_bot.py`(신규), `api_server/invariants.py`, `api_server/lab_api.py`, `api_server/main.py`, `polymarket/clob_client.py`(신규), `research/hypotheses/polymarket_sharp_wallet.py`, `research/run_polymarket_sharp_wallet_validate.py`, 관련 테스트

### 다음 할 일
- [ ] sharp_wallet 집행봇 `/lab` 대시보드에서 enabled=true로 켤지는 별도 결정 — 현재 paper verdict가 forward_test_required라 신중
- [x] whale의 `build_price_series`도 동일한 outcome 혼입 패턴 가능성 있음 → 2026-08-02 확인+수정 완료, 아래 추가 세션 로그 참고
- [ ] whale 원장 계속 쌓이는 대로 리더보드/self-score 재검증(표본 늘어야 결론 남)
- [ ] ICT/orderflow 저널 진행 — 계속 관찰(사용자 명시 요청: 채워질 때마다 N/30 보고)
- [ ] cross-venue-skew 데이터 수집됐지만 validation 스크립트 아직 미실행 — 다음 세션 후보

---

## 세션 로그 (2026-08-02 계속) — polymarket_whale outcome 혼입 버그 수정

### 완료된 작업
- **`research/hypotheses/polymarket_whale.py` outcome 혼입 버그 확인+수정**: sharp_wallet과 동일 패턴 — `build_price_series`가 condition_id만으로 필터링해 같은 마켓 Yes/No 두 토큰 체결이 하나의 가격 시계열에 섞이고 있었음(903개 마켓 중 398개=44%가 양쪽 outcome 다 거래됨). `load_whale_trades`에 `outcome_index` 파싱 추가, `build_spike_signal` 출력에 pass-through, `build_price_series(df, condition_id, outcome_index)`로 시그니처 변경, `build_labels_multi_horizon` 조회키를 `(condition_id, outcome_index)`로 변경 + outcome_index가 {0,1} 밖인 스파이크는 라벨링 제외. `run_polymarket_whale_validate.py::run_family()`, `run_polymarket_whale_wallet_analysis.py::_build_all_labels()` 호출부도 함께 수정. 커밋 90b07b8, push 완료.
  - A/B 비교(현재 데이터, 수정전/후 코드 동일 데이터셋): 수정 전 n_anchors=167, BH-FDR survivors 1/3(news:300s), verdict=`candidate`. 수정 후 n_anchors=79, survivors=0/3, verdict=`no_edge`.
  - 결론: outcome 혼입 버그가 news:300s를 거짓 candidate로 만들고 있었음. 버그 수정 후 진짜 verdict는 no_edge — **sharp_wallet과 반대 방향**(sharp_wallet은 버그 고치니 생존폭이 넓어짐, whale은 유일 생존자가 사라짐). 전체 스위트 2078 passed.
- **"다수 선택지(>2 outcome) 마켓 처리" 질문 답변**: Polymarket Data API의 raw `outcomeIndex`가 데이터상 `{0, 1, 999}`만 나옴 — 999가 API 자체의 비이진/negRisk 마켓 통합 센티널. 세부 카테고리 구분 데이터 자체가 없어 sharp_wallet/whale 둘 다 999(및 결측)는 라벨링에서 전부 제외하는 것 외엔 처리 방법이 없음(코드 한계가 아니라 데이터 한계).

### 변경된 파일
- `research/hypotheses/polymarket_whale.py`, `research/run_polymarket_whale_validate.py`, `research/run_polymarket_whale_wallet_analysis.py`, `tests/test_polymarket_whale.py`, `tests/test_run_polymarket_whale_validate.py`

### 다음 할 일
- [ ] whale 원장 계속 쌓이는 대로 재검증(현재 no_edge, 표본 늘면 재확인)

---

## 세션 로그 (2026-08-02 계속) — ICT/LTF 웹소켓 영구정지 수정 + 함대 전체 감사(취침 중 자율진행)

유저 지시: "원인 더 파보고, 수정해줘 그리고 나머지 전략들도 다 표본쌓였는지, 그 과정에서 오류없는지 확인해줘. 나 잘테니까 일어나있을 때 확인할 수 있도록해줘" → "계속해줘 끝까지". 아래 전부 유저 개입 없이 끝까지 진행.

### 완료된 작업

**1. ICT/오더플로우 LTF 웹소켓 영구정지 버그 수정** (`2a6a907`) — 저널 10일간 0건의 근본 원인 (⚠️ 부분 해결, 아래 정정 참고)
- `HyperliquidOrderflowClient.stream()`이 connect/idle 둘 다 타임아웃 가드가 없어서, macOS 슬립/웨이크 등으로 DNS/connect가 OS 레벨에서 멈추거나 연결이 정상 종료(`StopAsyncIteration`)되면 예외도 로그도 없이 LTF 스트림이 영구 정지하는 구조였음. `ict-orderflow-paper` 프로세스 실측: `lsof` 소켓 0개, 재연결 로직 자체가 없었음.
- `orderflow/hl_adapter.py`에 `asyncio.wait_for`로 connect/idle 타임아웃 추가, `research/run_ict_paper_engine.py`의 `_stream_ltf` 호출부에 지수 백오프 재연결 루프 추가. 테스트 2개 파일 업데이트.

**⚠️ 정정 (같은 세션, 커밋 이후 실측)** — 위 수정 자체는 코드상 맞고(재연결/백오프 로직은 실측으로 정상 동작 확인 — 5s→10s→20s→40s 백오프 시퀀스 트레이스백과 함께 관측됨), **하지만 재기동한 라이브 `ict-orderflow-paper` 프로세스가 지금도 LTF 웹소켓에 연결하지 못하고 있음**. 저널은 계속 0건으로 남을 가능성 높음. 실측 근거:
  - `_poll_htf`의 HTF 15분봉 fetch(`fetch_htf_bars`)는 성공 확인됨 — HL API(CloudFront 프록시로 추정되는 호스트)로 향하는 established TCP 연결이 프로세스 시작 직후 바로 열려 3분 넘게 유지됨.
  - 그런데 `_stream_ltf`의 웹소켓 연결(`wss://api.hyperliquid.xyz/ws`)은 그 이후 단 한 번도 소켓 활동(SYN_SENT조차)이 안 잡히고, 예외 로그도 전혀 안 찍힘(로그 파일 unbuffered `-u` 옵션으로 재확인, 완전 공백) — 3분+ 관찰.
  - 프로세스를 세 번(PID 83682 → 84355 → 85282) 완전 재기동해도 동일 — whale_tick 사례(재기동 한 번으로 해결)와 달리 재기동으로 안 풀림.
  - 반면 동일 셸에서 실행한 독립 ad-hoc 스크립트(`websockets.connect` 단독, HTF+WS 동시 `asyncio.gather` 조합)는 매번 1초 이내 정상 연결 성공 — 네트워크/DNS 자체 문제 아님, tmux로 띄운 이 특정 장기 프로세스 컨텍스트에서만 재현.
  - `py-spy dump`로 정확한 블로킹 지점 확인 시도했으나 root 권한 필요, sudo 캐시 없어 실패 — 근본원인 미확정 상태로 세션 종료.
  - 가설(미확증): `_poll_htf`가 `call_with_hard_timeout`을 `await` 없이 동기 호출해 이벤트 루프를 블로킹하는 패턴(`research/run_ict_paper_engine.py`의 `_poll_htf`) 자체는 독립 리프로 스크립트로는 재현 안 됐지만, asyncio 내부 리졸버(3.14 프레임워크 빌드)가 이 특정 스케줄링 순서에서 걸리는 경합 조건일 가능성.
  - **결론: 저널이 채워질 것으로 기대하지 말 것.** 프로세스는 살아있고 자체 재시도(백오프)하니 크래시는 안 나지만, 실제로 스트림을 못 열고 있어 트레이드 진입 자체가 발생 못 함.

**2. 함대 전체 감사 — 9개 tracked 수집기 + 관련 파일 전수 점검, 발견된 문제 전부 수정** (`6f275e7`)
- `polymarket_mlb_specialist_tick` 거짓 "stuck" 알람: 저유동성 마켓이라 체결 간격 30~110분(2026-08-01 `research/data/mlb_specialist/*.jsonl` 150건 실측)인데 기본 임계 900s를 써서 상시 오탐. `api_server/fleet_health.py`의 `STALE_AFTER_S`에 `"polymarket_mlb_specialist_tick": 7200` 추가. 수집기 자체는 정상 작동 중이었음(코드 버그 아님).
- `polymarket_arb` / `polymarket_updown_arb` 크래시루프(진짜 버그): 두 `run_forever()` 루프에 예외처리가 전혀 없어서 네트워크 순간장애만 나도 프로세스 통째로 죽고, 워치독(`ops/collector_watchdog.py`)의 tmux kill+재생성 재기동에만 의존하고 있었음 — 재기동마다 이전 scrollback/로그가 통째로 날아가 원인 사후분석도 불가능한 구조. 조사 도중 실제로 두 수집기가 라이브로 재크래시하는 걸 목격(`/lab/fleet` 폴링 중 dead 전환 확인). MLB 수집기 등 다른 수집기들이 이미 쓰던 try/except+지수백오프 패턴을 그대로 이식해 자체복구하도록 수정. 신규 회귀테스트 2개 추가(`test_run_forever_survives_run_once_exception_and_backs_off`), 전체 스위트 2082 passed 확인.
- `polymarket_whale_tick` 지속 stale: 코드 자체(`net_utils.call_with_hard_timeout`)는 정상 — 매 시도 `TimeoutError: 20.0s 내 응답 없음` 100% 재현, 근데 신규 프로세스로 curl 날리면 즉시 성공 → 프로세스 로컬 OS 레벨 DNS/리졸버 wedge로 확인(net_utils 자체 버그 아니라 그 가드가 못 고치는 종류의 프로세스 상태 오염). `/lab/collectors/polymarket_whale_tick/restart`로 프로세스 재기동해서 해결.

### 변경된 파일
- `api_server/fleet_health.py` — MLB 임계 오버라이드 추가
- `research/run_polymarket_arb_scan.py`, `research/run_polymarket_updown_arb_scan.py` — try/except+백오프 추가
- `tests/test_run_polymarket_arb_scan.py`, `tests/test_run_polymarket_updown_arb_scan.py` — 회귀테스트 추가

### 현재 함대 상태 (최종 확인, 2026-08-02 03:12 UTC)
`/lab/fleet` 9개 전부 `verdict: fresh`. `ok: false`인데 이유는 `polymarket_arb`(restart_count_24h=6)·`polymarket_updown_arb`(3)의 `flapping` 플래그가 켜져 있어서 — 전부 **수정 배포 전** 크래시루프 때 쌓인 24시간 롤링 카운트라 지금 상태 이상은 아님, 시간 지나면 자연히 꺼짐(재발하면 진짜 문제).

### 막힌 부분 / 사용자 결정 필요
- **`run_gex_snapshot_collect.py`**: 자체 docstring상 "tmux로 상시 실행" 대상인데 tmux 세션 자체가 없음(~13일째 중단 추정, 데이터 최신성 기준). `/lab/fleet`의 `COLLECTORS`(`api_server/lab_api.py`) 설정에도 아예 없어서 죽어도 알람이 안 뜨는 구조. 의도적 중단인지 방치인지 불명 — 임의로 재기동 안 함, 확인 후 재개 여부/`COLLECTORS`에 편입할지 결정 필요.
- `run_paper_ingest.py`의 16일 묵은 `cursor.json`은 자체 docstring상 1회성 트리거 스크립트(cron 아님)라 정상, 조치 불필요.

### 다음 할 일
- [x] **최우선**: `ict-orderflow-paper` LTF 웹소켓 미연결 문제 진단 — **해결됨, 아래 "세션 로그 (2026-08-02 계속 2)" 참고.**
- [ ] `gex_snapshot` 수집기 재개 여부 결정 (위 참고)
- [ ] whale 원장 계속 쌓이는 대로 재검증(현재 no_edge, 표본 늘면 재확인)
- [ ] ICT/orderflow 저널 진행 — 웹소켓 연결 자체는 복구됨(아래 참고), 이제 실제 신호 발생까지 관찰 필요(사용자 명시 요청이던 N/30 보고 재개)
- [ ] cross-venue-skew 데이터 수집됐지만 validation 스크립트 아직 미실행 — 다음 세션 후보

---

## 세션 로그 (2026-07-31) — Polymarket sharp_wallet/whale 검증 고도화

### 완료된 작업
- **sharp_wallet 정식 등록 + walk-forward**: `polymarket_sharp_wallet_convergence_v1`을
  `experiment_registry`에 처음 등록. BH-FDR 생존 15개 그룹(bucket/tercile×horizon) 중
  walk-forward(시간순 반분, 전반/후반 둘 다 양수) 통과 11/15 → `paper_candidate_forward_test_required`.
  bucket2(정확히 2개 샤프월렛 컨버전스)만 전반/후반 둘 다 일관되게 음수 — 노이즈보다
  실제 역효과에 가까움, bucket 축이 단조롭지 않다는 신호.
- **whale 지갑 역추적 2건 신규 검증**: whale 원장 raw jsonl에 이미 있던 `proxyWallet`을
  로더가 버리고 있던 걸 발견 → `hypotheses/polymarket_whale.py`에 `proxy_wallet` 컬럼 추가.
  1) 리더보드 교차조회: whale 스파이크 176건 중 공식 리더보드(top50) 지갑 체결 **0건** —
     "큰 거래"와 "검증된 실력"이 완전히 분리된 모집단임을 확인.
  2) self-referential 지갑 스코어(prequential, lookahead 없음): 과거 평균 수익 상위 30%
     지갑 필터링 시 30s/120s 유의미하게 나왔으나 표본 5~6건뿐 — 통계적으로 신뢰 안 함.
  둘 다 `experiment_registry` 등록(`polymarket_whale_leaderboard_wallet_v1`,
  `polymarket_whale_selfscore_wallet_v1`, 둘 다 `candidate`지만 표본 협소 명시).
- 결론: whale 엣지가 약한 근본 원인은 "큰 체결 = 정보력"이라는 미검증 전제 + 이벤트
  자체가 희귀(9일간 176건, sharp_wallet은 4451건)해서 표본이 안 쌓임. 지갑 정체를
  넣어봐도(리더보드/자체스코어 둘 다) 표본 부족으로 결론 못 냄 — 더 오래 수집 필요.

### 변경된 파일
- `research/run_polymarket_sharp_wallet_validate.py` — walk-forward 추가, `log_experiment` 호출 추가
- `research/hypotheses/polymarket_whale.py` — `proxy_wallet` 컬럼 3곳(load/spike/label)에 추가
- `research/run_polymarket_whale_wallet_analysis.py` — 신규, 리더보드 교차조회 + self-referential 스코어
- `docs/progress.md` — 본 항목

### 다음 할 일
- [ ] whale 원장 계속 쌓이는 대로 리더보드/self-score 재검증(표본 늘어야 결론 남)
- [ ] ICT/orderflow 저널 1/30 — 계속 관찰(사용자 명시 요청: 채워질 때마다 N/30 보고)
- [ ] cross-venue-skew 데이터 4.0G 수집됐지만 validation 스크립트 아직 미실행 — 다음 세션 후보

### 막힌 부분 / 결정사항
- git 작업트리에서 발견된, 이 세션과 무관한 미커밋 변경 6건 전부 검토·분리 커밋 완료:
  1. `execution/broker.py` 삭제 — 실사용처 없는 죽은 코드 확인 (`b8e2705`)
  2. `orderflow/kis_adapter.py` 삭제 — KIS 해외선물 폐기 결정 건([[project_kis_futures_data_shelved]]) (`b8e2705`)
  3. `api_server/graph_api.py` mark-to-market 버그 수정 — 기존 테스트 4/4 통과 확인 후 (`f0c40d9`)
  4. `krx/client.py` 당일 빈 응답 시 최근 영업일 fallback (`a4933eb`)
  5. `jarvis/research_workflow/hypothesis_generator.py` topic 관련도 재정렬 — 테스트 전무 상태였어서
     신규 테스트(`tests/test_hypothesis_generator.py`) 12건 작성 후 커밋 (`e20a1db`)
  6. `jarvis/_state/*`, `research/data/*`, `research/autoresearch/*` — 백그라운드 tmux 에이전트가
     상시 쌓는 런타임 로그/데이터, 코드 아님 — 커밋 대상 아니라 그대로 둠(정상)
- `run_polymarket_whale_validate.py`의 walk-forward 게이트(`_walk_forward` 함수 +
  관련 테스트)는 이전 세션에서 이미 구현돼 미커밋 상태였던 것 확인 — 같은 주제라
  sharp_wallet 커밋(`88959bf`)에 함께 포함.

## 현재 상태 (마지막 업데이트: 2026-07-11 liquidity pool 벤뉴 뱃지 UI)

### 완료된 작업

**Phase 1 — KIS 데이터/주문 (2026-06-21 ~ 06-22)**
- KIS 일봉 데이터 수집 → `ParquetDataCatalog` 저장 (`data_ingestion.py`, `backends/kis/`)
- KIS WebSocket 실시간 체결 스트리밍 (`live_trade_stream.py`, `backends/kis/ws_client.py`)
- KIS 모의투자 주문 실행 (매수/매도/취소/조회) (`backends/kis/order_client.py`)

**Phase 2 — IB 데이터/주문 (2026-06-22 ~ 06-24)**
- IB 실시간 체결 스트리밍 (`live_trade_stream_ib.py`, `backends/ib/client.py`)
- IB 페이퍼트레이딩 주문 실행 (`backends/ib/order_client.py`)
- IB 히스토리컬 일봉 수집 → catalog (`data_ingestion_ib.py`)

**Phase 3 — 조건 엔진 / 전략 스포너 (2026-06-23)**
- JSON 조건 파서 + 평가기 (AND/OR 조합) (`condition_engine/`)
- 조건 충족 시 전략 동적 스폰 (`strategy_spawner/`)

**Phase 4 — 백테스트 / 분석 (2026-06-24)**
- NautilusTrader BacktestEngine 래퍼 (`backtest_runner/`)
- 종목 간 수익률 상관관계 행렬 (`correlation_analysis/`)

**Phase 5 — 대시보드 API + 베타 분석 (2026-06-25)**
- FastAPI 서버: `/bars`, `/backtest`, `/correlation` 엔드포인트 (`api_server/main.py`)
- KOSPI 인덱스 + SPY ETF catalog 수집 (`data_ingestion_kospi.py`)
- `beta_for_pair()` 함수 구현 (`beta_analysis/beta.py`) — beta, correlation 계산

### 완료된 작업 (continued)

**Phase 9 — 매크로 지표 + 기업 재무정보 (2026-06-25 ~ 06-26)**
- FRED API 연동 (`fred/client.py`) — 14개 미국 거시지표 (`/fred/catalog`, `/fred/series`)
- ECOS API 연동 (`ecos/client.py`) — 14개 한국 거시지표 (`/ecos/catalog`, `/ecos/series`)
- 대시보드 US-MACRO / KR-MACRO 탭 분리 (`app/quant/page.tsx`)
- KIS 토큰 캐시 (disk) 구현 (`backends/kis/auth.py`) — rate limit 우회
- 통합 수집 CLI (`ingest.py`) — domestic/ib/index/batch/crno-search 서브커맨드
- 금융위원회 기업재무정보 API (`corp_finance/client.py`, `/corp-finance/summary` 엔드포인트)
  - 검증된 crno 8개: 삼성전자/현대차/기아/LG전자/LG화학/삼성SDI/NAVER/KB금융
  - `ingest.py crno-search` — 매출액 기준 FSC DB에서 crno 자동 검색
  - Quant > FACTOR 탭에 기업재무 패널 추가 (다년도 테이블 + 바 차트)

**Phase 10 — 퀀트 지표 고도화 + 외부 데이터 소스 확장 (2026-06-26)**
- 백테스트 응답에 Sortino/Volatility/WinRate/P-L Ratio/AvgWin/AvgLoss 추가 (`backtest_runner/runner.py`)
- 몬테카를로 시뮬레이션 (`monte_carlo/simulator.py`) + `/monte-carlo` 엔드포인트
- 레짐 필터 (`regime_filter/detector.py`) + `/regime` 엔드포인트
- 금융위원회 crno 기반 기업재무 API 구현 (`corp_finance/client.py`, `/corp-finance/summary`)
- KRX OpenAPI 클라이언트 (`krx/client.py`) — 구독 신청 후 사용 가능
- SEC EDGAR 클라이언트 (`sec_edgar/client.py`) — 무료, 키 불필요
  - `/edgar/summary`: 미국 기업 연도별 재무제표
  - `/edgar/concept`: XBRL concept 시계열
- 대시보드 대규모 개편:
  - backtest 페이지: "empty state" UI (항상 표시, 빈 값 → RUN 시 채워짐)
  - quant 페이지 탭 추가: MONTE CARLO, REGIME
  - US-MACRO 탭 하단에 SEC EDGAR 재무제표 패널 추가
  - `pyproject.toml`에 `krx*`, `sec_edgar*` 추가

### 진행 중 / 다음 할 일

- [ ] SK하이닉스 crno 미확인 (FSC DB: `python ingest.py crno-search --sale-trillion 44.6 --year 2022 --tolerance 2`)
- [ ] 신한지주, POSCO홀딩스 crno 추가

### 알아둘 것 / 블로커
- `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` 셸 프로필에 영구 설정됨
- API 서버는 `cd nautilus-multi-venue && uvicorn api_server.main:app --reload` 실행
- CORS: `localhost:3000`만 허용
- KRX API: `apikey` 헤더 사용, `data-dbg.krx.co.kr`은 테스트 서버(키 미승인시 401), 프로덕션은 포털 승인 후 별도 URL
- SEC EDGAR: `User-Agent: "seokminal research bot"` + `From: tjrgns97502@naver.com` 헤더 필수
- SEC EDGAR rate limit: 10 req/s → client에 0.11s throttle 내장됨
- KSD API: `DATA_GO_KR_API_KEY` 사용 (별도 키 없음). 실제 엔드포인트:
  - 배당: `1160100/GetStocDiviInfoService_V2/getDiviInfo_V2`
  - 대차순위: `1160100/GetStocLendBorrInfoService_V2/getStLendAndBorrItemRank_V2`
  - 권리일정: `1160100/GetStocRighScheService_V2/getRighExerReasSche_V2`
  - 발행정보: `1160100/GetStocIssuInfoService_V3/getStocIssuInfo_V3`
  - ⚠️ 금융위원회 KSD 서비스는 `/service/` prefix 없음 (기업재무는 `/service/` 있음)
- KSD 대차순위: `basDt`로 특정 날짜 조회. 최근 영업일 데이터만 존재 (공휴일/주말 없음)

---

## 2026-07-08: Polymarket 실시간 틱 수집기 (Phase 1 — 데이터 수집만)

### 완료된 작업
- Polymarket CLOB WSS 구독 기반 틱 수집기 신규 트랙 (`polymarket_arb` REST 폴링과 별개)
- 브레인스토밍 → 스펙(`docs/superpowers/specs/2026-07-08-polymarket-tick-collector-design.md`) → 계획(`docs/superpowers/plans/2026-07-08-polymarket-tick-collector.md`) → subagent-driven 구현, 4개 태스크 전부 태스크리뷰+최종 브랜치리뷰 통과
- 스코프: 라이브 스포츠/속보 마켓 확률 틱을 WSS로 받아 jsonl 적재만 함. 전략/판정 로직 없음. `api_server/polymarket_bot.py`(프로덕션 페이퍼봇) 손대지 않음.
- 스펙 대비 2개 의도적 이탈: (1) news 거래량 급증 기준 드롭 — 지원 필드 없음, (2) 명시적 WSS unsubscribe 대신 5분 주기 전체 재연결로 대체 — 공개 문서에 unsubscribe 포맷 없음
- 최종 브랜치리뷰에서 unattended 운영 리스크 2건 발견 후 수정: WSS clean-close 시 백오프 없이 즉시 재연결하던 핫루프 버그, `game_start_time` naive timestamp 하나가 전체 재선정 사이클을 죽이던 버그

### 변경된 파일
- `polymarket/client.py` — `_map_market()`에 `sports_market_type`, `game_start_time` 필드 추가
- `research/polymarket_tick/market_selector.py` (신규) — sports/news 분류 순수함수
- `research/polymarket_tick/ws_collector.py` (신규) — CLOB WSS 클라이언트 + 틱 파싱 (`backends/kis/ws_client.py` 패턴 재사용)
- `research/run_polymarket_tick_collect.py` (신규) — 무한루프 진입점, 5분 재선정 + WSS 스트리밍 + 지수백오프
- `pyproject.toml` — `websockets>=15.0` 의존성 추가
- 테스트 4개 신규 파일, 커밋 히스토리: `ec7d30d..eeb1cd8` (main 직접 커밋)

### 다음 할 일
- 몇 주 데이터 쌓인 뒤 모멘텀/오버리액션 가설 검증 spec→plan 별도 사이클 (그 전까진 그냥 방치, 건드릴 필요 없음)

### 막힌 부분/결정사항
- 없음 — 전 과정 클린 (task reviewer 1회 fix cycle, 최종 브랜치 reviewer 1회 fix cycle, 이후 승인)
- tmux 세션 `polymarket-tick`으로 2026-07-08 04:39 KST부터 상시 실행 시작 (`polymarket-arb`와 같은 머신, 별도 세션). 첫 SSL 인증서 에러(`CERTIFICATE_VERIFY_FAILED`, python.org 빌드가 시스템 CA 미설치) → `/Applications/Python 3.14/Install Certificates.command` 실행으로 해결 — 코드 버그 아니고 이 macOS의 환경설정 문제. 재시작 후 정상 동작 확인 (뉴스 마켓 틱 20초에 404개 적재 확인).

---

## 2026-07-08 (세션2): 리소스 조사 — 코드 변경 없음

### 완료된 작업
- "플랫폼 느리다" 리포트 → PID 85156 조사. 처음엔 autoresearch 좀비 워커로 오판(status.json 타임스탬프만 보고 성급히 결론) → 재확인 결과 **오판이었음**: 85156 부모가 `uvicorn api_server.main:app --reload`(PID 39399) — reload 모드가 spawn하는 진짜 API 서버 프로세스 그 자체. `sample`로 콜스택 찍어보니 현재 idle(kevent 대기), 누적 CPU도 10분/경과 1h24m 수준 — 좀비도 스핀도 아님. RAM 1.29GB는 nautilus_trader+pandas+numpy 로드된 정상 베이스라인. **kill 안 함, 코드 수정 불필요** — 죽이면 백엔드 API 끊김.
- 발열 원인 추가 조사: 이 프로젝트 밖 오래된 dev 서버들(`seoka`, `web3-tcg` web/server, `netlify dev`) 떠있었지만 전부 CPU 0%/RAM 미미 — 발열 무관. 크롬/VSCode/Claude.app은 정상 사용량.
- 폴리마켓 틱 데이터 현황 체크: tmux `polymarket-tick` 살아있음, 04:39~05:50 약 1h10m 누적 — `2026-07-08.jsonl` 54MB, 124,804줄 (news 125,190 / sports 266). 검증 돌리기엔 한참 부족, 계속 방치.

### 변경된 파일
- 없음 (조사만, 코드 수정 없음)

### 다음 할 일
- 없음 (기존 "몇 주 데이터 쌓인 뒤 검증" 계획 그대로 유지)

### 막힌 부분/결정사항
- PID 85156은 앞으로도 uvicorn 서버 켜져있는 한 정상적으로 계속 떠있음 — "왜 안 꺼지냐"는 질문 다시 나오면 이 항목 참고, 재조사 불필요.

---

## 2026-07-08 (세션3): KR 밸류/퀄리티 팩터 + 종합점수, autoresearch 배치 편입

### 완료된 작업
- 기존 사전등록 3팩터(size/amihud/turnover, 전부 CANDIDATE) 배치에 PER/PBR/ROIC/F-Score 4개 추가 검증 — 표본 22~27개월(DART 재무제표 PIT 공시시차 반영, `_fy_for_date`)로 전부 REJECT_BH (PBR은 pct=0.67로 오히려 반대 방향, 노이즈 아니고 실제 반대신호 — 성장주 장세 반영으로 판단)
- "개별 지표 말고 결합해서 판단보조로 써야지" 피드백 반영 → `kr_value_quality_composite`(PER·PBR·ROIC·F-Score 부호맞춘 월내 z-평균) 신규 사전등록. 개별로는 안 보이던 신호가 결합하니 pct=96.0·p=0.0432로 **BH-FDR 생존**. 단 비용 스트레스(160bps)에서 마이너스로 뒤집혀 redteam `cost_stress` 탈락 → REJECT_REDTEAM
- 중간에 "구조 CANDIDATE(size/turnover) 롱 레그 내부 2차 밸류틸트" 시도했다가 폐기: size 레그(소형주)는 DART 펀더멘털 캐시(대형주 위주)와 교집합 0으로 상시 UNDERPOWERED, turnover 레그는 22개월 확보됐지만 pct=18.67로 반대신호 — 사용자가 "소형주 안 건드려도 됨, 대형주 급락 시 가치 판단보조가 원래 목적"이라 정정, 관련 코드/테스트 전부 되돌림(커밋에 안 남음)
- 최종 결론: composite는 대형주(펀더멘털 커버리지 유니버스) 급락 시 "펀더멘털 대비 진짜 싼지" 확인하는 **판단보조 필터**로만 근거 있음. 단독 자동매매 트리거로 쓸 근거 없음(비용 못 버팀)

### 변경된 파일
- `research/autoresearch/engines_factor.py` — PER/PBR/ROIC/F-Score 4팩터 + composite 8번째 팩터, `_fy_for_date` PIT 로직, `compute_factors` 연동
- `research/autoresearch/engine.py` — `collect_candidates()`에 `load_fundamentals` 배선
- `research/data/dart_financials.py`(신규), `research/data/valuation_factors.py`(신규) — DART 재무제표 PIT 수집 + PER/PBR/ROIC/F-Score/PSR/EV-EBIT/Piotroski F-Score 계산. 전자는 corp_code 매핑에 `curl -m` 필수(requests 스트리밍은 대용량 XML에서 timeout 안 먹힘)
- `tests/test_engines_factor.py` — 합성 데이터 수학 검증 9개(각 팩터 planted-effect 탐지 + 무효과 근처 + fund 없으면 None)
- 커밋: `c5c0b19` (main 직접). 이 세션에서 건드린 것 중 무관한 변경(`api_server/graph_api.py`, `jarvis/_state/*`, `research/data/polymarket_tick/`)은 커밋에서 제외 — 다른 트랙 것이라 그대로 둠(아직 uncommitted 상태로 남아있음, 다음 세션에서 확인 필요할 수도)

### 다음 할 일
- 없음(이 트랙은 여기서 정리). 재시도하려면 DART 캐시를 소형주까지 확장해야 함 — 별도 데이터 수집 작업, 지금 계획 없음
- `git status`에 남아있는 무관 변경(`api_server/graph_api.py`, `docs 외 jarvis/_state/*`)은 이 세션에서 건드린 적 없음 — 다음 세션에서 뭔지 확인 필요하면 참고

### 막힌 부분/결정사항
- composite REJECT_REDTEAM(cost_stress) 사유는 재검토 대상 아님 — "왜 이거 안 씀" 질문 다시 나오면 이 항목 참고
- size_value_tilt/turnover_value_tilt는 시도했다가 방향 잘못 짚어서 폐기한 거라 재시도 안 함(코드에 흔적 없음, 이 로그가 유일한 기록)

---

## 2026-07-08 (세션4): ICT 조합 백테스트 페이지 + 프리셋/검색/타임프레임 확장
> ⚠️ 이 세션의 "프리셋(기각확정 재현)" 별도 탭 구조는 세션5에서 폐기됨 — 아래 내용은 히스토리 기록용, 현재 UI와 다름. 최신 상태는 세션5 참고.

### 완료된 작업
- ICT 프리미티브(킬존·sweep·FVG·OB·BOS-CHoCH) 자유조합 AND백테스트 신규 페이지 `/ict` — 매칭random 대비 net/percentile/p-value/WF1·WF2 참고통계, 전부 REJECT 확정된 표준조합(experiment_registry) 경고 배너 상시 노출
- "reject된 것도 실험" 요청 반영 — `research/ict/models_2024.MODELS` 6개 고정모델(전부 REJECT 확정)을 "프리셋(기각확정 재현)" 탭으로 노출, 모델 로직/파라미터는 원본 그대로 다른 심볼·기간에 재현만 가능(재검증 아님 명시)
- 심볼 선택 plain `<select>` → 검색형 콤보박스(타이핑 필터, 라이브 크립토 태그 표시)
- 타임프레임 1m/5m/15m/1h/4h/1d로 확장. 디스크 미보유분은 3단 폴백: ①직접저장 ②크립토(LIQUID_PERPS 25종)는 HL API 라이브조회+캐시(모든 tf) ③주식/ETF는 15m 원본→1h/4h만 pandas 리샘플 합성(1m/5m은 소스 없음, IB TWS 필요해서 미지원 — 에러 메시지로 명확히 안내)
- Nautilus 카탈로그(`/bars` 등)가 1-DAY 고정이라 킬존(시간대) 프리미티브에 못 쓴다는 걸 이전 세션에 확인 → `research/data/intraday_store.py`(별도 평범 parquet)로 라우팅, 재확인 완료

### 변경된 파일
- `research/ict/combinator.py` — `evaluate_preset()` 신규(+공통 통계 꼬리부 `_stats_vs_random()`로 `evaluate_combo()`와 중복 제거), `PRESET_IDS` 추가
- `api_server/router_ict.py` — `/ict/presets` GET 신규, `/ict/backtest`에 `preset` 필드(지정 시 `primitives` 무시), `_load_or_synthesize()`(라이브조회/리샘플 폴백), `/ict/symbols`에 `live_symbols` 추가
- `tests/test_ict_combinator.py` — preset 관련 테스트 2개 추가(알수없는 프리셋 에러, 정상 실행)
- `seokminal-dashboard/lib/api.ts` — `IctPresetsResponse`/`getIctPresets`, `IctSymbolsResponse.live_symbols`, `IctBacktestRequest.preset` 추가
- `seokminal-dashboard/app/ict/page.tsx` — 조합빌더/프리셋 탭 전환, 검색형 심볼 콤보박스, 고정 6종 타임프레임 셀렉트, 라이브 심볼 뱃지
- 브라우저로 3가지 다 라이브 검증: BTC 검색선택→4h AND콤보 실행(HL 라이브조회 성공, UNDERPOWERED 정상 렌더) / 프리셋탭 2024 Model→BTC 1m 재현 실행(라이브조회+진입 3건 UNDERPOWERED 정상 렌더) / AAPL 1h 프리셋(15m 리샘플 정상)
- `pytest tests/` 773 passed, 기존 무관 pre-existing 4실패(test_auth 3개 + test_backtest_happy_path)만 유지. `tsc --noEmit` 클린

### 다음 할 일
- 없음(이 트랙 정리 완료)
- DART 소형주 캐시 확장(세션3에서 남긴 할 일)은 백그라운드에서 계속 진행 중(PID 39906, 2026-07-08 세션4 종료 시점 기준 2022년도 처리 중, 4개 연도 중 1번째) — 다음 세션에서 완료 여부·최종 커버리지 숫자 확인 필요

### 막힌 부분/결정사항
- 없음. 프리셋 탭은 재검증 아니라는 점 페이지 문구에 상시 고정 — "왜 프리셋 켜놨는데 REJECT라고 하냐" 질문 나오면 이 항목 참고

---

## 2026-07-08 (세션5): ICT 프리셋 탭 폐기 → 전부 조합빌더로 병합 + Turtle Soup 신규

### 완료된 작업
- 사용자 피드백: "ICT는 여러 전략을 동시에 섞어서 쓰는 거지 CISD 하나로 매매하는 게 아니다. 프리셋 탭(단일모델 고정)이 구조적으로 틀렸다. 터틀 수프도 추가해서 전부 조합빌더에 섞어라." → 세션4에서 만든 별도 "프리셋(기각확정 재현)" 탭을 완전히 제거하고, 프리셋 6종의 핵심 로직(OTE/Unicorn/iFVG/CISD)을 양방향(bullish/bearish) 객관적 프리미티브로 일반화해 조합빌더에 흡수. 새 패턴 Turtle Soup(확정 swing 가짜돌파 후 반전, 기존 sweep과 달리 raw N봉 lookback이 아니라 확정 구조적 swing 포인트 사용) 신규 추가
- 결과: 프리미티브 5종 → 10종(killzone/sweep/fvg/order_block/market_structure/**ote/unicorn/ifvg/cisd/turtle_soup**), 전부 단일 빌더에서 AND 자유조합. 프리셋 모드/탭 개념 자체가 코드에서 사라짐(`evaluate_preset`, `PRESET_IDS`, `/ict/presets` 엔드포인트, `getIctPresets`, `IctBacktestRequest.preset` 전부 삭제)

### 변경된 파일
- `research/ict/primitives.py` — `ote_touches`, `unicorn_zones`, `ifvg_events`, `cisd_events`, `turtle_soup_events` 5개 함수 신규(전부 idx+type(bullish/bearish) 태그된 이벤트 리스트 반환, 기존 컨벤션 그대로)
- `research/ict/combinator.py` — 전면 재작성. `PRESET_IDS`/`evaluate_preset`/`models_2024.MODELS` 의존 제거, `PRIMITIVE_IDS` 10개로 확장, `evaluate_combo()`가 신규 5개까지 전부 dispatch
- `api_server/router_ict.py` — `/ict/presets` 삭제, `IctBacktestRequest`에서 `preset` 필드 제거하고 `window`/`near`/`min_run`/`confirm` 파라미터 추가(각각 ote·ifvg / unicorn / cisd / turtle_soup용)
- `seokminal-dashboard/lib/api.ts` — `IctPresetsResponse`/`getIctPresets`/`preset?` 제거, `IctBacktestRequest`에 `window`/`near`/`min_run`/`confirm` 추가
- `seokminal-dashboard/app/ict/page.tsx` — `mode`/`preset` state·탭 UI 전부 제거, `PRIMITIVES` 배열 10개로 확장, 선택된 프리미티브에 따라 조건부 파라미터 필드(swing_k/window/near/min_run/confirm) 노출
- `tests/test_ict_combinator.py` — 프리셋 관련 테스트 제거, `_zigzag_bars()` 픽스처(스윙·BOS·갭·연속캔들열 골고루 발생) 신규 + 신규 프리미티브 3개 테스트(크래시 없음, AND결합 부분집합 성질, 전체 10종 dispatch 가능)
- `pytest tests/test_ict_combinator.py tests/test_ict_primitives.py -q` 16 passed, `tsc --noEmit` 클린, 브라우저로 killzone+CISD+Turtle Soup 혼합조합(구/신 프리미티브 섞은 조합) 실행 확인 — SPY/15m, 진입 20건, percentile 65.6%/p=0.35(정상 렌더, 참고치 문구 유지)

### 다음 할 일
- 없음(이 트랙 정리 완료). 신규 5개 프리미티브도 표준조합 REJECT 결론과 마찬가지로 정식 CANDIDATE 파이프라인 대상 아님 — 사용자가 조합빌더에서 유의미해 보이는 조합을 찾으면 그때 BH-FDR 정식 배치로 넘기는 별도 작업 필요(지금 계획 없음)

### 막힌 부분/결정사항
- 없음. 프리셋 탭은 사용자 피드백으로 아키텍처 자체가 틀렸다고 판단해 완전 제거 — 재추가 요청 오면 이 항목 참고("ICT는 단일모델이 아니라 조합으로 쓴다"가 이유)

---

## 2026-07-08 (세션6): ICT 조합빌더 캔들차트 오버레이 신규

### 완료된 작업
- 사용자 피드백: "심볼 입력하면 차트나오고 해당 조건들 입력하면 차트에서 지표처럼 나오는 그런거 안되나? fvg,ifvg,cisd 이런것도 다 나오고 실버불렛이나 터틀수프가는 것도 다 시각적으로보이는?" → 기존엔 통계 테이블만 있었음(차트 자체가 없었음), 선택한 프리미티브를 캔들차트 위에 zone(FVG/OB/Unicorn=사각형)·point(sweep/BOS/OTE/iFVG/CISD/Turtle Soup=화살표 마커)·band(killzone=전체높이 반투명 세로띠)로 오버레이 표시하는 신규 기능
- 핵심 설계: `evaluate_combo()`의 AND결합 `entries_idx`(통계용, 전 프리미티브 교집합)와 완전히 분리된 `detect_events()`(차트용, 프리미티브별 원본 이벤트 개별 노출, AND결합 안 함) — "조합으로 뭐가 같이 터졌는지"와 "각 개념이 개별로 어디서 발생했는지"를 다른 레이어로 유지
- `lightweight-charts`에 사각형/존 렌더링 내장기능이 없어서 `ISeriesPrimitive` 플러그인 API로 직접 구현(zone renderer, fancy-canvas 비트맵 좌표 사용) — 사전 예시 없이 `node_modules` 타입정의 직접 읽고 작성, 첫 컴파일에 클린 통과
- 브라우저 검증: SPY/15m 전체 히스토리로 killzone+sweep+FVG+BOS+CISD+Turtle Soup 6종 혼합 렌더 확인(화살표 마커 정상, entries=0/UNDERPOWERED는 6종 AND교집합이 좁아서 나온 정상 결과) + FVG 단독선택으로 확대해서 파란 사각형 zone이 캔들 위 가격갭 위치에 정확히 겹치는 것 zoom 스크린샷으로 확인

### 변경된 파일
- `research/ict/combinator.py` — `detect_events()` 신규(파일 끝에 추가, 기존 `evaluate_combo()` 무변경). `POINT_PRIMITIVES`/`ZONE_PRIMITIVES`/`BAND_PRIMITIVES` 상수 + `_runs()`(연속인덱스→구간 리스트, killzone 밴드용). unicorn은 zone bounds가 없어서(`unicorn_zones()`가 `{idx,type}`만 반환) `(idx,type)` 키로 `fair_value_gaps()` 매칭 zone을 재사용
- `api_server/router_ict.py` — `_load_filtered()` 헬퍼로 로드/날짜필터/최소봉수체크 추출(backtest·events 양쪽 공유), `IctBar`/`IctEventsResponse` 모델 신규, `POST /ict/events` 엔드포인트 신규
- `seokminal-dashboard/lib/api.ts` — `IctBar`/`IctEvent`/`IctEventsResponse` 타입 + `getIctEvents()` 신규(요청 바디는 기존 `IctBacktestRequest` 재사용)
- `seokminal-dashboard/components/ict/IctChart.tsx` — 신규 파일. 캔들차트 + zone 사각형(`ZoneOverlay`/`ZonePaneView`/`ZoneRenderer`, `ISeriesPrimitive` 커스텀 플러그인) + point 화살표 마커(`createSeriesMarkers`) 렌더링. `ICT_LEGEND` export(페이지 범례용)
- `seokminal-dashboard/app/ict/page.tsx` — `/ict/events` 병렬 fetch(별도 `chartAbortRef`, 실패해도 통계 결과엔 영향 안 줌) + 통계 패널 위에 범례+`<IctChart>` 렌더 블록 추가
- `tsc --noEmit` 클린, `pytest tests/test_ict_combinator.py tests/test_ict_primitives.py -q` 16 passed(기존 그대로, `detect_events()` 자체 단위테스트는 아직 없음)

### 다음 할 일
- `detect_events()` 전용 pytest 없음(zone/point/band 3종 shape 검증하는 가벼운 테스트 1개 정도가 적당해 보임, 아직 사용자 요청은 아님 — 필요시 제안)
- 범례 스와치 색상이 `style={{ backgroundColor: ... }}` inline style 사용 중 — CLAUDE.md의 `style={{}}` 금지 규정(예외: 차트 컨테이너 height)에 엄밀히는 안 걸리는 케이스지만 프리미티브별 동적 색상이라 디자인 토큰으로 못 뺌, 필요시 재검토

### 막힌 부분/결정사항
- 없음

---

## 2026-07-08 (세션7): GC/ES/NQ/EURUSD/USDJPY 인트라데이 데이터 수집

### 완료된 작업
- 배경: ICT는 알고리즘/기관 오더플로우 개념이라 개인주식보다 유동성 큰 선물/FX가 더 맞는다는 논의 → GC(금)/ES/NQ(지수선물)/EURUSD/USDJPY/XAU 데이터 확보·매매가능성 조사부터 시작
- `research/data/futures_intraday_loader.py` 신규: IB `ContFuture`(GC/ES/NQ) 인트라데이 로더. **`ContFuture`는 `endDateTime`을 과거로 지정하는 요청 자체를 거부**(Error 10339, "continuous future" 제약) — 그래서 만기별계약처럼 커서로 과거를 걸어갈 수 없고, `endDateTime=""`(현재) 단발요청에서 `durationStr`만 실측으로 키워 상한을 찾음: 15m="6 M", 5m="1 M", 1m="1 M"(그 이상은 사이즈초과로 조용히 0봉). GC 6M 풀은 클라이언트 기본 60s 타임아웃 초과로 간헐 실패 → `timeout=120` 추가로 해결
- `research/data/fx_intraday_loader.py` 신규: IB `Forex`(EURUSD/USDJPY) 로더. Forex는 ContFuture와 달리 과거 `endDateTime` 커서가 허용돼서 15m은 주단위 청크 백필(156주≈3년), 1m/5m은 마찬가지로 사이즈상한 있어 단발요청만(실측: 1m="1 M", 5m="3 M")
- **IB 계정 이슈 2건 직접 해결**: (1) FX market data가 페이퍼계좌에 자동 상속 안 됨 → Client Portal에서 라이브↔페이퍼 계좌 마켓데이터 공유 설정+TWS 재시작 필요 (2) 그 후에도 Error 162 "Trading TWS session is connected from a different IP address" → 원인은 IBKR 웹포탈에 동시 로그인된 세션이었음, 포탈 로그아웃 후 해결
- **XAUUSD는 미해결**: `Forex('XAUUSD')` 자체가 IB에서 `qualify` 안 됨(Error 200, no security definition) — 계정에 보이는 "Physical Metals and Commodities(L1)" 구독은 다른 contract 타입(Commodity/CFD 등) 필요로 추정, 이번 세션에서 미시도
- 최종 수집 결과(모두 `data/intraday/{SYMBOL}_{TF}.parquet`, `/ict/symbols`에 자동 노출 확인):

| 심볼 | 1m | 5m | 15m |
|---|---|---|---|
| GC | 29,880봉 (06-08~07-08) | 5,976봉 (06-08~07-08) | 12,076봉 (01-04~07-08) |
| ES | 31,260봉 (06-07~07-08) | 6,252봉 (06-07~07-08) | 12,119봉 (01-04~07-08) |
| NQ | 31,260봉 (06-07~07-08) | 6,252봉 (06-07~07-08) | 12,119봉 (01-04~07-08) |
| EURUSD | 29,954봉 (06-09~07-08) | 17,961봉 (04-12~07-08) | 12,578봉 (01-02~07-08) |
| USDJPY | 29,955봉 (06-09~07-08) | 17,961봉 (04-12~07-08) | 12,578봉 (01-02~07-08) |

- 1h/4h는 별도수집 불필요 — 기존 `router_ict.py`의 `_resample_from_15m()`이 15m 원본에서 자동 합성(GC/EURUSD 1h로 브라우저·API 양쪽 확인)
- 브라우저 검증: `/ict` 페이지에서 GC 15m + FVG로 실제 백테스트 실행 확인(진입수 2140, eligible 12067≈전체봉수, percentile 93%, FVG zone 사각형 캔들차트 위 정상 렌더링), 가격 스케일도 API 원본(4097~4508)과 일치 확인

**XAUUSD 대안 — HL GOLD 트랙 추가**
- IB XAUUSD가 안 풀려서(`Forex('XAUUSD')` qualify 자체 실패) 대안으로 Hyperliquid에서 금 트래킹 상품 조사
- 1차로 HL 기본 퍼프 유니버스에서 `PAXG`(Pax Gold, 현물 1oz 담보 토큰) 발견 → `LIQUID_PERPS`(`research/data/hl_funding_loader.py`)에 추가. 근데 거래량 $440만/day로 얇음(HL 내 CRV~AAVE급, BTC의 1/500)
- 사용자가 "GOLD-USDC 퍼프 있잖아"로 재확인 요청 → HL의 빌더배포 dex(HIP-3) `"xyz"`에서 `xyz:GOLD` 발견(`{"type":"perpDexs"}` API로 조회, 기본 `{"type":"meta"}` 호출엔 안 잡힘 — dex 파라미터 필요). 가격 4079.9(GC 4097과 거의 일치), 거래량 **$4,390만/day**(PAXG의 10배) — 이쪽이 진짜 쓸만한 트랙. `xyz:SILVER`($2억/day), `xyz:CL`(원유, $4.5억/day), `xyz:EUR/JPY/GBP`(FX, 유동성은 얇음)도 같은 dex에 존재 확인만 함(미추가)
- `xyz:GOLD`도 `LIQUID_PERPS`에 추가 — `candleSnapshot` API가 `coin` 필드에 `"xyz:GOLD"` 프리픽스 그대로 받아줘서 `hl_candle_loader.py`/`router_ict.py` 코드 변경 전혀 없이 그대로 작동(콜론 포함 심볼도 `intraday_store.path_for()`가 파일명으로 문제없이 저장)
- XAUT0/USDC, XAUM 등 HL 스팟 금 페어도 확인했으나 XAUT0는 markPx가 실제 금값과 안 맞고(0.34, 페깅 깨짐) 거래량도 $6,951/day로 사실상 죽은 마켓 — 미채택
- 최종: PAXG, xyz:GOLD 둘 다 1m/5m/15m 라이브조회+parquet 캐시 확인 완료(크립토 계열은 `LIQUID_PERPS`에만 넣으면 `_load_or_synthesize`가 모든 tf 자동 라이브조회+캐시하는 기존 구조라 추가 코드 불필요)

| 심볼 | 1m | 5m | 15m | 비고 |
|---|---|---|---|---|
| PAXG | 5,056봉 (07-05~07-08) | 5,011봉 (06-21~07-08) | 5,004봉 (05-17~07-08) | 거래량 얇음($440만/day) |
| xyz:GOLD | 5,042봉 (07-05~07-08) | 5,008봉 (06-21~07-08) | 5,003봉 (05-17~07-08) | GC 대체 주력($4,390만/day) |

### 변경된 파일
- `research/data/futures_intraday_loader.py` — `--tf {1m,5m,15m}` 파라미터 추가(기존 15m 전용 → 3개 tf 지원), `BAR_SIZE`/`MAX_DURATION`을 tf별 dict로 변경
- `research/data/fx_intraday_loader.py` — 전면 재작성. `--tf` 추가, 15m은 기존 커서 백필 유지, 1m/5m은 단발요청 경로(`backfill_single_shot`) 신규. XAUUSD는 docstring에 미지원 사유 명시, 기본 `--symbols`에서 제거(EURUSD,USDJPY만)
- `research/data/hl_funding_loader.py` — `LIQUID_PERPS`에 `PAXG`, `xyz:GOLD` 추가
- `docs/progress.md` — 이 항목

### 다음 할 일
- XAUUSD(IB 정식 금현물) 데이터는 여전히 미해결 — 필요하면 `Commodity`/`CFD` contract 타입 재조사. 다만 `xyz:GOLD`로 사실상 대체 가능해서 우선순위 낮음
- `backends/ib/order_client.py`는 아직 `Stock` 주문만 지원, HL 쪽도 PAXG/xyz:GOLD 주문 실행 코드 없음 — GC/ES/NQ/EURUSD/USDJPY/GOLD로 실제 매매하려면 선물/FX/HL-빌더퍼프 주문 실행 코드 신규 필요(이번 세션은 데이터만, 집행은 범위 밖)
- 사용자가 ICT 조합빌더에서 이 심볼들로 유의미한 조합을 찾으면 BH-FDR 정식 파이프라인행 검토
- `xyz:SILVER`/`xyz:CL`(원유)도 거래량 괜찮아 보임 — 필요시 같은 방식으로 `LIQUID_PERPS` 추가만 하면 됨(코드 변경 불필요, 확인됨)

### 막힌 부분/결정사항
- XAUUSD(IB) 보류(계정 contract 매핑 미해결) — 대신 `xyz:GOLD`(HL 빌더퍼프)로 사실상 대체, GC/ES/NQ/EURUSD/USDJPY/xyz:GOLD 6개로 진행

---

**오더플로우 멀티벤뉴(바이낸스/OKX) 통합 + 라이브 검증 (2026-07-11)**

### 완료된 작업
- 대량체결/흡수 신호 백테스트로 통계적 무의미 확정 → HL 단일소스 한계로 보고 바이낸스+OKX 체결 테이프 합류 결정, `MultiVenueOrderflowClient`(HL+Binance+OKX 병합, 죽은 소스가 다른 소스 안 막음, 실패 소스 재연결) + `binance_adapter.py`/`okx_adapter.py` 구현, unit test(페이크 커넥션 기준) 통과 후 커밋 완료
- 이번 세션에서 **실서버 라이브 연결 검증** 진행(그동안 페이크 커넥션 테스트만 있었음):
  - 바이낸스 `wss://stream.binance.com:9443/ws/btcusdt@aggTrade` — 정상 연결, 파서 포맷(`e`/`p`/`q`/`m`/`T`) 그대로 일치
  - OKX `wss://ws.okx.com:8443/public` — **404, URL 버그 발견**. 정확한 엔드포인트는 `wss://ws.okx.com:8443/ws/v5/public`. `orderflow/okx_adapter.py` + `tests/test_orderflow_okx_adapter.py` 수정, 18개 orderflow venue 테스트 재통과 확인, 커밋(`baf7e33`)
- `/orderflow` 브라우저 스팟체크 중 **별개 문제 추가 발견**: uvicorn 백엔드(포트 8000)가 26시간째 PPID 1 고아 프로세스로 떠 있었고 완전 무응답 상태(curl까지 타임아웃, `/docs`도 안 뜸) — reload 워처가 죽고 워커만 남은 것으로 추정. kill 후 재기동
- 재기동 후 라이브 확인: BTC.HL 캔들 정상 렌더링(64217대, 바이낸스 실가 64218과 일치 = 멀티벤뉴 합류 작동 확인), 대량체결 버블 마커 실시간 표출, CVD 서브패널 값 정상, 콘솔 에러 없음

### 변경된 파일
- `orderflow/okx_adapter.py` — `OKX_WS_URL`을 `/ws/v5/public`로 수정
- `tests/test_orderflow_okx_adapter.py` — URL assertion 값 동일하게 수정
- `docs/progress.md` — 이 항목

### 다음 할 일
- uvicorn 고아 프로세스 재발 원인 미조사 — `--reload` 워처가 왜 죽었는지(리소스 문제/장시간 방치/다른 원인) 확인 안 함. 재발하면 원인 추적 필요
- 흡수/대량체결 신호가 백테스트로 통계적 무의미 확정났는데도 라이브 대시보드엔 여전히 마커만 뜨고 "매매판단용 아님" 경고가 UI에 없음 — 요청 범위 밖이라 안 건드렸음, 필요하면 별도 요청으로

### 막힌 부분/결정사항
- 없음(이번 라운드는 검증+버그수정만, 설계 이슈 없었음)

---

**오더플로우 ES/GC 선물 추가 + 크로스벤뉴 liquidity pool (2026-07-11)**

### 완료된 작업
- "nq,es,xau,forex 오더플로우 붙이기 어렵나" 질의에 ES/GC는 쉬움(IB `Future` contract, 기존 NQ 패턴 그대로), Forex는 어려움(IB FX는 quote-driven이라 TradeEvent 기반 로직과 안 맞음) 판단 → ES/GC만 진행, Forex는 미착수
- `orderflow/ib_adapter.py`: `_FUTURES_SYMBOLS`에 `ES: CME`, `GC: COMEX` 추가(기존 `NQ: CME` 옆에)
- `orderflow/manager.py`: `TICK_SIZE_BY_SYMBOL`에 `ES: 0.25`, `GC: 0.10` 추가, `tick_size`를 `MultiVenueOrderflowClient`에 전달하도록 변경
- **liquidity pool**(작업하면서 같이 요청받음): 오더북 뎁스도 트레이드 테이프처럼 바이낸스+OKX+HL 합류. `binance_adapter.py`에 `stream_depth`(`@depth20@100ms`) 추가, `okx_adapter.py`에 `stream_depth`(`books5` 채널) 추가, `multi_venue_adapter.py`에 `_round_to_tick`/`_pool_levels`/`_pool_books` 신규 — 벤뉴별 최신 스냅샷을 tick 단위로 반올림 후 사이즈 합산해서 하나의 풀북으로 병합해 내보냄. `aggregator.on_book_snapshot()`이 스냅샷을 통짜 교체로 처리하는 구조라 벤뉴별 스냅샷을 그대로 흘리면 깜빡였을 것 — 그래서 병합 후 emit으로 설계
- `stream()` pump 3개→5개(hl, binance-trades, binance-depth, okx-trades, okx-depth), 모두 공통 sink로 유입
- 신규 유닛테스트 15개(binance/okx depth 파서+스트림, pool 함수 3종, 통합 스트림 테스트) 작성, orderflow 전체 + 풀 스위트(869 passed, pre-existing 4 fail만 잔존) 통과 확인
- 브라우저 라이브 재검증: 백엔드 reload 두 번 걸림(아래 참고) 후 재기동, BTC.HL 정상 렌더링·콘솔 에러 없음 확인. 단 UI엔 벤뉴별 분리 표시가 없어 풀링 효과가 화면상으로는 구분 안 됨(내부 수치만 바뀜)
- 로컬 TWS 켠 뒤 ES/GC/NQ contract qualify 라이브 시도 → **API 핸드셰이크 타임아웃**(TCP는 붙음, `connectAsync` 15s 타임아웃). TWS의 "Enable ActiveX and Socket Clients" 설정 또는 incoming-connection 수락 팝업 미해결로 추정 — **미검증 상태로 남음**

### 변경된 파일
- `orderflow/ib_adapter.py` — `_FUTURES_SYMBOLS`에 ES/GC 추가
- `orderflow/manager.py` — `TICK_SIZE_BY_SYMBOL`에 ES/GC 추가, tick_size 전달
- `orderflow/binance_adapter.py` — `stream_depth`/`parse_binance_depth_message` 추가
- `orderflow/okx_adapter.py` — `stream_depth`/`parse_okx_depth_message` 추가
- `orderflow/multi_venue_adapter.py` — 5-pump 구조 + 풀링 로직(`_round_to_tick`, `_pool_levels`, `_pool_books`, `_make_pooling_sink`) 추가
- `tests/test_orderflow_binance_adapter.py`, `tests/test_orderflow_okx_adapter.py`, `tests/test_orderflow_multi_venue_adapter.py` — 신규 테스트 15개
- `docs/progress.md` — 이 항목

### 다음 할 일
- Forex(EURUSD/USDJPY) 오더플로우는 IB FX가 quote-driven이라 별도 설계 필요 — 미착수, 요청 시 진행
- CME/COMEX 선물 마켓데이터 구독 없음(paper 계정) — TWS Market Data Subscription Manager에서 구독 추가해야 ES/GC/NQ 실제 tick 수신 가능. 구독 전까진 contract resolve까지만 되고 데이터는 안 옴

### 막힌 부분/결정사항
- (해결됨) uvicorn `--reload` 행(hang) 재발 원인 특정: `timeout_graceful_shutdown` 기본값이 `None`이라 `asyncio.wait_for(..., timeout=None)`이 절대 `TimeoutError`를 안 던져서, 살아있는 요청 task를 강제 `cancel()`하는 분기가 아예 안 걸림. `/ws/orderflow/{symbol}` 핸들러가 `await queue.get()`으로 블록하고 클라이언트 disconnect를 능동적으로 감지 안 하는 구조라(`websocket.receive()` 안 씀), 새 orderflow 메시지가 안 들어오는 순간 shutdown이 무한 대기함. `lv5_agent.py`의 `ZeroDivisionError`는 daemon thread 안에서 발생 + 이미 outer `except Exception`에 잡혀 로깅만 되고 죽어서 hang과 무관(리뷰 파이프라인이 조용히 스킵되는 별개 버그로 남음, 미수정)
- **조치**: `seokminal-multi-venue/../CLAUDE.md`(부모 디렉토리, 두 프로젝트 공용, git 미관리)의 백엔드 실행 커맨드에 `--timeout-graceful-shutdown 10` 추가. 코드 버그 아니라 CLI 옵션 미설정 문제였음 — orderflow 코드는 안 건드림. 새 플래그로 재기동해서 정상 기동·응답 확인(`/orderflow/symbols` 200 OK)

### 막힌 부분/결정사항
- (해결됨) IB TWS API 핸드셰이크 타임아웃은 clientId 충돌/팝업 미승인이었음 — 사용자가 TWS 확인 후 재시도해서 정상 연결됨
- **실제 버그 발견 및 수정**: `orderflow/ib_adapter.py`의 `_contract()`가 만기월 없는 `Future(symbol, exchange, currency)`를 그대로 넘겨서 IB가 ambiguous contract로 처리, `qualifyContractsAsync`가 조용히 실패(conId=0 방치)하고 이후 `reqTickByTickData`/`reqMktDepth`가 무효 contract로 요청됨 — **NQ도 원래부터 이 버그로 라이브 미작동 상태였음**(ES/GC 붙이다 우연히 발견). `_resolve_contract()` 추가: qualify 실패 시 `reqContractDetailsAsync`로 후보 전체 받아서 만기 안 지난 것 중 최근월물(front month) 자동 선택. 라이브 검증: ES→ESU6(20260918), GC→GCN6(20260729), NQ→NQU6(20260918) 정확히 resolve됨. 이후 단계(`reqTickByTickData`)에서 "No market data permissions"로 막힘 — 이건 계정 구독 문제라 코드 밖 이슈
- 신규 유닛테스트 1개(`test_stream_resolves_front_month_when_future_is_ambiguous`) 추가, `tests/test_orderflow_ib_adapter.py` 4개 전체 통과

---

**liquidity pool 벤뉴 뱃지 UI 노출 (2026-07-11)**

### 완료된 작업
- 풀북에 어느 벤뉴가 기여 중인지 표시 안 되던 걸(위 세션에서 "풀링 효과가 화면상으로는 구분 안 됨"으로 남긴 이슈) 백엔드→프론트 전체 파이프라인으로 노출
- 백엔드: `orderflow/models.py`의 `OrderBookSnapshot`에 `venues: list[str] = []` 필드 추가, `multi_venue_adapter._pool_books()`가 `venues=sorted(latest_books)` 채워서 반환, `aggregator.latest_book()`이 WS 메시지(`book_snapshot`)에 `venues` 그대로 실어보냄
- 프론트: `lib/orderflow-data.ts`의 `OrderBookState`/`BookSnapshotMsg`에 `venues: string[]` 추가, `emptyOrderflowState()`/`applySnapshot()`/`applyBookSnapshot()` 전부 반영
- `components/orderflow/OrderBookPrimitive.ts`: COB 인셋 우측 상단에 `HL`/`BIN`/`OKX` 텍스트 뱃지로 현재 풀에 기여 중인 벤뉴 렌더링(캔버스 `fillText`, `ctx.save/restore`로 다른 primitive 영향 안 주게 격리)
- 백엔드 테스트 3개(`test_orderflow_multi_venue_adapter.py`, `test_orderflow_aggregator.py`) 갱신, 프론트 테스트(`orderflow-data.test.ts`) 갱신 — 백엔드 870 passed(pre-existing 4 fail만), 프론트 215 passed, `npx tsc --noEmit` 클린
- 브라우저 라이브 확인: `/orderflow` BTC.HL 차트 우측 COB 인셋에 "BIN HL OKX" 뱃지 정상 렌더링, 콘솔 에러 없음

### 변경된 파일
- `orderflow/models.py` — `OrderBookSnapshot.venues` 필드 추가
- `orderflow/multi_venue_adapter.py` — `_pool_books()`가 `venues` 채움
- `orderflow/aggregator.py` — `latest_book()`이 `venues`를 WS 메시지에 포함
- `tests/test_orderflow_multi_venue_adapter.py`, `tests/test_orderflow_aggregator.py` — `venues` 검증 추가
- `seokminal-dashboard/lib/orderflow-data.ts` — `OrderBookState`/`BookSnapshotMsg`에 `venues` 추가, 관련 함수 3개 갱신
- `seokminal-dashboard/components/orderflow/OrderBookPrimitive.ts` — 벤뉴 뱃지 렌더링 추가
- `seokminal-dashboard/tests/lib/orderflow-data.test.ts` — `venues` 필드 반영
- `docs/progress.md` — 이 항목

### 다음 할 일
- 없음 (요청 범위 완료)

### 막힌 부분/결정사항
- 없음

---

## 작업 히스토리

### 2026-06-21
- KIS 일봉 데이터 수집 파이프라인 구축
- KIS WebSocket 실시간 스트리밍 구현

### 2026-06-22
- KIS 주문 실행 어댑터 구현
- IB 실시간 체결 스트리밍 구현

### 2026-06-23
- IB 주문 실행 어댑터 구현
- 조건 파서/평가기 엔진 구현
- 전략 스포너 구현

### 2026-06-24
- IB 히스토리컬 데이터 수집 구현
- 백테스트 자동화 구현
- 상관관계 분석 구현

### 2026-06-25
- 대시보드 백엔드 FastAPI 서버 구현
- KOSPI/SPY 인덱스 데이터 수집 구현
- beta_analysis 모듈 구현 (`/beta` 엔드포인트 제외)
- docs/progress.md 작업 루틴 세팅
- pyproject.toml 패키지 누락 수정

---

## 2026-07-12: 오더플로우 시그널 검증 하네스 (NQ/MNQ) — subagent-driven 7태스크 완료

### 완료된 작업
- footprint 불균형/CVD 다이버전스/heatmap 유동성벽 근접/iceberg refill/stop-run 패턴 5개 시그널 통계 검증 하네스. 브레인스토밍→스펙(`docs/superpowers/specs/2026-07-12-orderflow-signal-validation-harness-design.md`)→계획(`docs/superpowers/plans/2026-07-12-orderflow-signal-validation-harness.md`)→subagent-driven 구현 7태스크 전부 태스크리뷰 통과, 최종 브랜치리뷰(opus) READY TO MERGE(Critical/Important 0건)
- 기존 검증 철학(TSMOM 때와 동일) 그대로: 랜덤 베이스라인 대비 empirical p-value, cost-robust, BH-FDR 다중검정. 실집행 없음 — 순수 통계 검증만
- 계획 자체의 태스크 순서 버그 1건 발견 후 즉시 수정: Task 6이 `_blocked`/`DEFAULTS`/`NOTIONAL_MULTIPLIER`를 호출하는데 셋 다 어느 태스크에서도 정의 안 됨(`_blocked`는 Task 7에 배정돼 있었는데 Task 6 자체 테스트가 이미 이걸 필요로 함) — Task 6 구현자가 앞당겨서 전부 추가, `NOTIONAL_MULTIPLIER={"NQ":20.0,"MNQ":2.0}`는 기존 `IB_FUTURES_TICK_VALUE_USD` 상수에서 역산(CME 실제 계약승수와 일치 확인). Task 7은 자연스럽게 순수 검증만 남아 subagent 없이 직접 실행
- "eligible = 판정가능 모집단(신호 발동분만 아님)" 시멘틱 버그가 이번에도 3회 발생(Task3 CVD, Task5 테스트커버리지) — 전부 그 자리에서 수정, 최종 리뷰에서 4개 빌더 전부 정상 확인(랜덤베이스라인 공정성의 핵심 전제)
- 전체 스위트: 신규모듈 33 passed, 프로젝트 전체 915 passed / 4 failed(기존 pre-existing만: test_auth.py×3, test_backtest_happy_path)

### 변경된 파일
- `research/validation/cost_model.py` — IB futures 커미션/틱밸류/슬리피지 상수(NQ/MNQ) + `ib_futures_effective_cost_bps()`
- `research/run_ib_orderflow_tick_collect.py`(신규) — IB NQ/MNQ 틱+뎁스 수집기, `OrderflowAggregator` 재사용(라이브 대시보드와 동일 소스)
- `orderflow/ib_adapter.py` — `_FUTURES_SYMBOLS`에 MNQ 누락 수정(있었으면 Stock으로 오인식됐을 버그)
- `research/hypotheses/orderflow_futures.py`(신규, 핵심 결과물) — 5개 시그널 빌더 + `run_signal_hypothesis`/`run_stop_run_hypothesis`/`run_all_hypotheses`/`_blocked` 오케스트레이션
- `tests/test_cost_model.py`, `tests/test_run_ib_orderflow_tick_collect.py`, `tests/test_orderflow_futures_signals.py`, `tests/test_orderflow_futures_run.py` — 신규 테스트 4파일
- 커밋 히스토리: `1b24c6c..8e81a1e`(main 직접, 9커밋)

### 다음 할 일
- 실제 데이터 수집 시작(tmux 상시실행) 후 통계 판정 실행 — 지금은 하네스만 완성, 아직 실데이터로 `run_all_hypotheses` 안 돌려봄
- IB futures 커미션/틱밸류 상수는 미검증 근사치(코드 주석에 명시) — 페이퍼 단계 진입 전 IB 실제 요금표 대조 필요
- Minor findings 잔존(비블로킹, 안 고침): `_blocked` 불필요한 로컬 `import json`, 미사용 `patch` import, `run_stop_run_hypothesis` trade_size 하드코딩(DEFAULTS 안 읽음), Task2 테스트 unmocked sleep(~4s)

### 막힌 부분/결정사항
- 없음 — 계획 순서버그 1건은 에스컬레이션 없이 직접 판단해 수정(사용자가 세션 시작 시 "허락 여부 묻지말고 태스크 끝까지" 명시 위임)
- 부수 조사: 사용자 신규 한투(KIS) 해외선물옵션 계좌로 IB 대체 가능한지 질의 받아 조사 — KIS도 실시간체결(`ccnl`, TR `HDFFF020`) + 5레벨 뎁스(`asking_price`) 둘 다 있어 이론상 5개 시그널 전부 가능. 단 (1) 매수/매도 방향 필드(`quotsign` 등) 의미가 공개문서에 전혀 없어 IB의 `tick_rule.classify()`처럼 신뢰 가능한지 불명, (2) CME 종목은 별도 유료시세 신청 필수, (3) NQ/MNQ가 실제 지원 상품에 포함되는지 공개 종목마스터로 확인 불가, (4) 프로토콜이 완전히 달라 새 어댑터 통짜 구현 필요(Task2급 작업량) — 결론: 지금 전환할 이유 없음, IB 하네스가 이미 완성·검증됐고 미해결 의문(방향 필드)은 실제 KIS API 키로 라이브 페이로드 까봐야 풀림(사용자가 직접 해야 할 일)

---

## 2026-07-12: KIS 해외선물옵션 어댑터 시도 → IB 유지로 결론 (데이터소스 전환 검토 종료)

### 완료된 작업
- `orderflow/kis_adapter.py` 신규 구현: HDFFF020(체결)+HDFFF010(호가) 단일 웹소켓, 기존 `TradeEvent`/`OrderBookSnapshot` 인터페이스 준수(`OrderflowAggregator` 그대로 재사용 가능), 체결방향은 `tick_rule.classify()`로 직전 호가 대비 추정(ib_adapter.py와 동일 패턴), PINGPONG 제어프레임 echo 처리. 테스트 10개 전부 통과, 전체 스위트 리그레션 없음(925 passed / 4 pre-existing failed)
- 실계좌로 REST 프로브(`inquire-price`) 라이브 호출 → `EGW00550: CME SUB거래소 신청 계좌가 아닙니다` 확인 — 종목코드(`NQZ25`) 형식 검증 이전 단계에서 이미 막힘, CME 유료시세 미신청 상태
- KIS/Rithmic/Databento/Bookmap 요금·구조 비교 조사:
  - KIS: Lv1(Top of Book) $5~10/월, 근데 heatmap 유동성벽/iceberg refill 시그널은 뎁스 필요해서 **Lv2 $30~45/월** 필수
  - Rithmic API: AMP $125/월 고정, EdgeClear $20/월+계약당$0.10 — 무료 아님
  - Bookmap: 구독($49~99/월)+데이터피드($34~101/월) 이중과금, Python API가 Bookmap GUI 앱 실행 중이어야만 동작 — 이 프로젝트의 headless 24/7 수집기 구조와 구조적으로 안 맞아 후보 제외
  - CME 실시간시세 라이선스료 자체는 거래소 정책이라 브로커 무관하게 발생(KIS만의 단점 아님)
- 결론: IB 유지. 근거는 비용우위가 아니라 "이미 SDD 7태스크로 검증된 유일한 작동 경로"라는 점 — KIS는 CME신청 대기+어댑터 미검증 이중 블로커, 비용도 이점 없음
- 이 결론 메모리 저장: `project_kis_futures_data_shelved.md`

### 변경된 파일
- `orderflow/kis_adapter.py`(신규, 커밋됨 — 실사용 파이프라인엔 미연결, 보류 상태)
- `tests/test_orderflow_kis_adapter.py`(신규)
- 커밋: `49b5377`

### 다음 할 일
- 없음(이 트랙 종료) — 오더플로우 검증 하네스는 IB 경로로 계속, 다음 스텝은 위 섹션의 "실데이터 수집 후 `run_all_hypotheses` 실행"
- KIS 계좌를 데이터소스가 아니라 향후 실집행(주문) 브로커로 통합하고 싶어지면 그건 별개 동기라 재검토 대상(메모리에 명시)

### 막힌 부분/결정사항
- KIS 어댑터는 코드만 존재, CME 유료시세 미신청으로 라이브 검증 불가 상태 — 신청은 KIS포털에서 사용자가 직접 해야 함(계좌 설정, 대행 불가)
- 사용자 승인: "IB가 지금은 최선"으로 명시적 확정, 이 트랙은 여기서 종료

---

## 2026-07-12: IB 시장데이터 구독 정리 + absorption 신호 스콥 추가

### 완료된 작업
- IB Client Portal 요금표 대조: NQ/MNQ 페이퍼/검증에 필요한 건 `CME Real-Time (NP,L2)` $12.10/월 하나뿐(top+depth 포함, 페이퍼계좌는 라이브계좌에 링크돼있어 구독 그대로 흘러들어감 — 사용자 확인함). 나머지 번들(US Securities Snapshot, US Futures Value Bundle PLUS 등)은 이 스콥에 불필요. `project_kis_futures_data_shelved` 메모리에 실요금 반영해 KIS Lv2($30~45) 대비 IB가 훨씬 쌈을 기록
- OPRA(옵션 flow, 주식 leverage 트레이딩 검토용)와 CME futures 데이터는 완전 별개 트랙임을 정리 — OPRA L1 $1.50/월이 옵션 flow 최소 요건, 주식 자체 orderflow(NQ/MNQ 하네스류)는 또 별도로 거래소별 Level II 필요(NASDAQ TotalView $16.50, NYSE OpenBook $25 등) — 지금은 미착수, 필요해지면 그때 결정
- 페이퍼 봇(실시간 신호+주문) vs 지금 하네스(오프라인 통계검증)는 다른 것임을 정리 — 순서상 통계검증 먼저, 신호가 살아남아야 실시간 봇 착수 정당화됨(이 프로젝트 기존 방법론과 동일)
- **absorption 신호를 오더플로우 futures 하네스 스콥에 추가**: `research/strategies/orderflow_absorption.py`(HL BTC/ETH, REJECT됨)의 판정식을 `research/hypotheses/orderflow_futures.py`에 이식(`build_absorption_signals`) — footprint_delta 버킷의 buy/sell 우세 비율 + open/close 가격으로 판정, 원본의 large-trade류 노이즈플로어(개별 체결사이즈 rolling median)는 이 수집기가 버킷 합산볼륨만 저장해 재현 불가라 제외. large-trade/large-trade-event 가설 자체도 같은 이유로 스콥 제외(수집기 스키마 변경 없인 이식 불가 — 사용자가 "설계작업 늘리지 말고 기존 것 최대한 활용"으로 명시 확정한 방향과 일치)
- `_footprint_buckets` 헬퍼가 이제 bucket_open도 반환하도록 확장(기존 3개 호출부 전부 수정), SIGNAL_BUILDERS/HYPOTHESIS_TEXT에 absorption 등록 → BH-FDR 검정 5신호→6신호(x2심볼=12) 확장
- 테스트: `test_orderflow_futures_signals.py`에 absorption 4개 케이스(흡수 BUY/SELL, 흡수아님 HOLD, 무우세 HOLD) 추가, `test_orderflow_futures_run.py`의 하드코딩 카운트(10→12) 갱신. 전체 스위트 929 passed / 4 failed(문서화된 pre-existing만: test_auth.py×3, test_backtest_happy_path) — 리그레션 없음

### 변경된 파일
- `research/hypotheses/orderflow_futures.py` — `build_absorption_signals` 추가, `_footprint_buckets` 반환값에 open price 추가, 모듈 docstring 갱신
- `tests/test_orderflow_futures_signals.py`, `tests/test_orderflow_futures_run.py`
- 커밋: `6391d58`

### 다음 할 일
- IB Client Portal에서 `CME Real-Time (NP,L2)` 구독 신청(사용자가 직접 — 계좌 설정 변경은 대행 불가) → 반영 후 `research/run_ib_orderflow_tick_collect.py` 실행해 depth 틱 들어오는지 확인
- 이전 섹션과 동일: 실데이터 수집(tmux 상시, 신호당 100~200개+ eligible instance 쌓일 때까지 — 캘린더 기간 미리 고정 안 함, 인스턴스 카운트가 stopping rule) 후 `run_all_hypotheses` 실행
- IB futures 커미션/틱밸류 상수 미검증(코드 주석 명시) — 페이퍼 단계 진입 전 재확인 필요

### 막힌 부분/결정사항
- 없음 — absorption 이식은 스콥 작아 SDD 풀파이프라인 없이 직접 구현(TDD, 기존 5신호 패턴 그대로 재사용), 세션 내 완결

---

## 2026-07-12: BTC/ETH 오더플로우 전부 REJECT → 컨텍스트 게이트 신규 검증 → 여전히 REJECT (결론)

### 완료된 작업
- 기존 `orderflow_futures.py` 6신호(footprint_imbalance/absorption/cvd_divergence/confluence/stop_run 3horizon)를 NQ/MNQ용이 아니라 이미 수집돼있던 BTC/ETH 틱데이터(HL, 2026-07-10~12)에 일회성 재적용(`research/run_orderflow_futures_on_btc.py`) → **14개 전부 REJECT**(BH-FDR survivors 전부 False)
- "오더플로우만 보고 매매하는 트레이더 없다"는 논의 후, 실전 트레이더가 쓰는 컨텍스트 필터(상위TF트렌드/키레벨/VWAP)를 게이트로 얹어 재검증하기로 함 — 브레인스토밍→스펙(`docs/superpowers/specs/2026-07-12-orderflow-context-gate-btc-design.md`)→플랜(`docs/superpowers/plans/2026-07-12-orderflow-context-gate-btc.md`, 사용자 변경요청 없이 그대로 승인)→subagent-driven 5태스크 구현
- 게이트 모델: 트렌드+키레벨+VWAP **3/3 만장일치**(2/3 다수결 아님)라야 bias 성립, killzone(NY오픈) 안이고 기존 confluence가 같은 방향일 때만 진입. 신규지표 발명 없이 기존 `market_structure`/`swings`/`killzone_indices`(ICT primitives)만 재사용
- 신규 모듈 `research/hypotheses/orderflow_context_gate.py`: `build_ohlc_bars`/`resample_bars`(바 빌더) → `build_trend_filter`/`build_key_level_filter`(15분봉) + `build_vwap_filter`(60초버킷) → `build_gated_confluence_signals`(전체조립, 15분봉신호를 60초버킷에 broadcast)
- 태스크 1~5 전부 태스크리뷰 클린(Minor만, Critical/Important 0) → **최종 브랜치리뷰(opus)에서 Critical 발견**: `resample_bars`가 15분봉을 구간시작 타임스탬프로 찍는데, `_broadcast_15m_to_60s`가 그 신호(구간종가로 계산됨)를 같은 구간시작부터 바로 적용 — 봉이 마감되기 전에 그 봉의(아직 알 수 없는) 신호가 새어들어가는 룩어헤드. p-value를 부풀리는 방향이라 이 DORMANT 스크립트의 존재이유(통계적 유의미성 검증) 자체를 무효화하는 결함
- 수정: `_broadcast_15m_to_60s`가 `signal_15m[j]`(형성중인 현재봉) 대신 `signal_15m[j-1]`(직전에 마감된 봉)을 쓰도록 — 경계케이스 직접 트레이스로 검증. 스펙 문서에도 "룩어헤드 금지" 조항 명시적으로 추가. 화이트박스 회귀테스트 신규 추가(`test_broadcast_15m_to_60s_uses_previous_closed_bar_not_current_forming_bar`) — 버그 있는 코드로 되돌리면 fail, 고친 코드면 pass 직접 확인. 재리뷰(opus) READY TO MERGE 확정
- **최종 결과: 게이트를 얹어도 여전히 에지 없음** — BTC:gated_confluence 0트레이드, ETH:gated_confluence 1트레이드(p=0.2834, BH-FDR survivor 아님). 수정 전엔 룩어헤드 덕에 ETH가 survivor로 잘못 표시됐었는데, 버그 제거 후 사라짐 — "컨텍스트 필터가 오더플로우 신호를 구할 것"이라는 가설 자체가 REJECT
- 전체 스위트: 944 passed / 4 failed(문서화된 pre-existing만: test_auth.py×3, test_backtest_happy_path)

### 변경된 파일
- `research/run_orderflow_futures_on_btc.py`(신규 이후 수정) — BTC/ETH 재적용 + gated_confluence 실행 + 신규 BH-FDR 풀(기존 14개 배치와 안 섞음, 사후 가설풀 오염 방지) 별도 출력
- `research/hypotheses/orderflow_context_gate.py`(신규) — 바빌더/트렌드/키레벨/VWAP필터/게이트조립
- `tests/test_orderflow_context_gate.py`(신규, 15개)
- 커밋: `2d0dc79..1a3bc2d`(main 직접, 11커밋 — BTC재적용 1 + 게이트구현 5 + 룩어헤드수정 3 + 문서 2)

### 다음 할 일
- 이 트랙 결론 남: BTC/ETH 오더플로우(원시 + 컨텍스트게이트 둘 다) REJECT 확정. 재시도하려면 새로운 근본적으로 다른 아이디어 필요 — 같은 신호군 파라미터 튜닝은 금지(이미 여러 세션에 걸쳐 반복 확인된 방법론)
- 스코프 밖으로 명시적으로 남겨둔 것: NQ/MNQ 이식(원시틱 미저장 구조라 별개 결정 필요), POC/value area 필터(VWAP 단독 검증 우선), ICT 프리셋(OTE/Unicorn/iFVG/CISD/SMT) 재투입(이미 주식에서 사망 확정)
- IB Client Portal `CME Real-Time (NP,L2)` 구독 신청은 여전히 미완(사용자 직접) — NQ/MNQ 하네스는 이 구독 없이는 depth 틱 검증 불가, 별도 트랙으로 계속 대기중

### 막힌 부분/결정사항
- 없음. 룩어헤드 버그 발견 시 "결과 보고 튜닝 금지" 원칙과 별개로(이건 버그 수정이지 파라미터 조정이 아님) 스펙 문서 먼저 명확화한 뒤 코드 수정 → 재검증 → 재리뷰까지 사용자 확인 없이 진행(세션 시작 시 위임된 continuous-execution 권한 범위 내)

---

## 2026-07-12: 골드 데이터소스 탐색(HL xyz:GOLD vs IB 1OZ/SI) — 결론 안 남, 다음 세션 재확인 필요

### 완료된 작업
- 위 컨텍스트게이트 REJECT 논의 중 사용자가 "하이퍼리퀴드 gold로 오더플로우 작업 가능한가?" 질문 → `xyz:GOLD`(HL 빌더퍼프, BTC/ETH 같은 네이티브 메이저와 다른 서브dex) 라이브 프로브(45초, scratchpad `probe_hl_gold.py`, 커밋 안 함): 구독 자체는 됨, 체결빈도 BTC(175건/45초) 대비 xyz:GOLD는 30건/45초로 ~6배 낮음. 진행하려면 `cost_model.py`의 `HL_SLIPPAGE_BUCKET`/`HL_SPREAD_BUCKET`을 `"major"`가 아니라 `"alt"`로 써야 함(현재는 아무 코드도 안 건드림, 조사만)
- 사용자가 IB 구독목록 제공 — "ICE Futures US Gold and Silver (L2)"가 Fee Waived로 이미 구독돼있음 확인. IB Gateway 포트 확인(기본 7496/7497/4001/4002 전부 거부 → 사용자가 7498 알려줌)
- `reqMatchingSymbols`/`reqContractDetails`로 실제 심볼 조사(scratchpad `probe_ib_gold.py`): 골드는 심볼 `1OZ`(1온스 데일리), 실버는 `SI` — 둘 다 `exchange="COMEX"`로 등록돼있음(구독 번들 이름은 "ICE"인데 실제 라우팅은 COMEX라는 점 발견). 최초 추측했던 `exchange="NYBOT"`/`"ICEUS"`는 전부 에러 200(No security definition)
- 근월물 conId 확보: `1OZQ6`(만기 2026-07-29, multiplier=1, conId=753716613), `SIN6`(만기 2026-07-29, multiplier=1000, conId=505405746)
- `1OZ`/`SI` 라이브 견적 요청(`probe_ib_gold2.py`) → 전부 `nan`, 뎁스도 빈값, 에러이벤트도 0개
- 이미 유료구독(CME Real-Time NP,L2, 사용자 미보유) 필요한 것으로 알려진 `GC`(정식 COMEX 골드)와 `1OZ`를 나란히 비교(`probe_ib_gold3.py`→`probe_ib_gold4.py`, conId로 특정: GC=`GCN6` conId=760200536)해서 "권한없음 에러가 뜨는 쪽 vs 안 뜨는 쪽"으로 구분 시도 → **GC/1OZ 둘 다 완전히 조용함(에러 0, 견적 0)** — 오늘(2026-07-12)이 일요일이라 CME/COMEX Globex 자체가 닫혀있어서 구독권한 체크 자체가 안 일어나는 것으로 보임. 이 방법으론 "1OZ가 무료번들에 포함되는지" 결론 못 냄

### 변경된 파일
- 없음(전부 scratchpad 조사 스크립트, 커밋 안 함 — `probe_hl_gold.py`, `probe_ib_gold.py`~`probe_ib_gold4.py`)

### 다음 할 일
- **평일 마켓 열린 시간에 재확인 필요**: `probe_ib_gold4.py` 패턴(GC vs 1OZ 나란히 reqMktData/reqMktDepth, errorEvent 리스너)을 그대로 재실행 — GC만 에러(구독필요) 뜨고 1OZ는 조용하면 무료번들 확인됨, 둘 다 에러 뜨면 1OZ도 별도구독 필요, 둘 다 조용하고 견적도 나오면 둘 다 무료로 확정
- 위 확인 끝나면 사용자와 HL `xyz:GOLD`(체결빈도 낮음, cost model alt티어 필요) vs IB `1OZ`/`SI`(무료여부 미확정) 중 어느 쪽으로 갈지 결정 — 아직 코드 변경 없음, 순수 조사단계
- IB로 갈 경우 `orderflow/ib_adapter.py`의 `_FUTURES_SYMBOLS` 매핑에 `1OZ`/`SI` 추가 필요(미착수)
- HL로 갈 경우 `research/run_hl_orderflow_tick_collect.py`의 `COINS`에 `"xyz:GOLD"` 추가해서 tmux 상시수집 필요(미착수)

### 막힌 부분/결정사항
- 일요일 마켓휴장이 "구독권한 없음"과 구분 안 돼서 결론 보류. 다음 세션 평일에 `probe_ib_gold4.py` 재실행이 최우선

### 추가: IBKR 스팟골드(XAUUSD, CMDTY) 발견 — COMEX선물과 별개 옵션
- 사용자가 "IBKR 런던 스팟골드"를 물어봐서 확인(`probe_ib_spotgold.py`, `probe_ib_spotgold2.py`, scratchpad, 커밋 안 함) — COMEX선물(`GC`/`1OZ`)과 완전히 별개인 IB 자체상품 확인됨
  - `XAUUSD`(secType=`CMDTY`, exchange=`SMART`, conId=69067924), `XAGUSD`(conId=77124483) 둘 다 존재
  - `reqMktDepthExchanges()`로 `SMART/CMDTY`가 `serviceDataType='Deep'`(L2뎁스 지원 목록)에 있음 확인 — 상품 구조상 뎁스 미지원이라 빈값 나온 게 아니라 순전히 휴장 때문(오늘 결과 bid/ask=-1, 뎁스 빈값 — COMEX FUT/FOP도 지원목록엔 있지만 지금 다 휴장이라 빈값인 것과 동일 패턴)
  - 무료여부/실견적 미확인 — 평일 재확인 필요

### 다음 할 일(추가)
- 평일 재확인 시 `probe_ib_gold4.py`(COMEX GC vs 1OZ)뿐 아니라 `probe_ib_spotgold.py`(XAUUSD/XAGUSD)도 같이 재실행 — 셋 다 견적/뎁스 살아있는지, 에러이벤트로 구독필요 여부 뜨는지 한번에 비교

---

## 2026-07-12: 크로스벤뉴 오더북 스큐 가설 — SDD 6태스크 전부 완료, 머지레디

### 완료된 작업
- 브레인스토밍→스펙(`docs/superpowers/specs/2026-07-12-cross-venue-skew-design.md`, 11c33bf) 승인 후 플랜 작성, subagent-driven-development로 6태스크 전부 실행
- Task1 수집기 → Task2 스냅샷로딩/임밸런스 → Task3 벤뉴간그리드정렬/가격시계열 → Task4 스큐괴리/z-score스파이크 → Task5 다중호라이즌라벨링 → Task6 검증러너(신규 독립 BH-FDR 풀)
- Task3/4/5는 각 1회 fix-and-re-review(전부 "non-discriminating test" 패턴 — 잘못된 구현에서도 통과하는 테스트, mutation testing으로 검증 후 수정)
- 최종 브랜치 리뷰(opus, 11c33bf..4e7fac5, 9커밋): Critical/Important 0건, 머지레디 확정. 전체 스위트 974 passed / 4 pre-existing 실패만(test_auth.py×3-4, test_backtest_happy_path — 무관)
- main 직접커밋 컨벤션이라 별도 브랜치 없음 — 9커밋 전부 이미 main에 랜딩. 플랜 문서(`docs/superpowers/plans/2026-07-12-cross-venue-skew.md`)는 태스크 스코프 밖이라 뒤늦게 별도커밋(50fbff7)

### 변경된 파일
- `research/run_cross_venue_skew_collect.py` (신규, da35014) — 벤뉴×코인 6개 독립 재연결루프 수집기
- `research/hypotheses/cross_venue_skew.py` (신규, 92fabb6~854ea9c) — load_venue_snapshots/build_imbalance/align_venues/build_price_series/build_skew_divergence/build_spike_signal/build_labels_multi_horizon
- `research/run_cross_venue_skew_validate.py` (신규, 4e7fac5) — run_stop_run 패턴 검증러너, BTC×ETH×3호라이즌 최대 6개 p-value 신규 BH-FDR 풀
- `tests/test_run_cross_venue_skew_collect.py`(7), `tests/test_cross_venue_skew.py`(23) — 30개 전부 통과
- `docs/superpowers/plans/2026-07-12-cross-venue-skew.md` (신규, 50fbff7)

### 다음 할 일
- **실데이터 축적 필요** — 검증러너는 아직 BLOCKED 상태(3벤뉴 실데이터 없음). `tmux new -s cross-venue-skew-tick`으로 `research/run_cross_venue_skew_collect.py` 상시 실행 시작해야 `research/run_cross_venue_skew_validate.py`가 의미있는 결과 냄(polymarket-tick/hl-orderflow-tick과 동일 패턴)
- 플랜 문서의 Task6 검증커맨드 오타(`python3 research/run_cross_venue_skew_validate.py` → `python3 -m research.run_cross_venue_skew_validate`가 맞음, repo-wide sys.path 컨벤션) — 사소, 필요시 정정

### 막힌 부분/결정사항
- 없음. 코드/테스트/리뷰 전부 클린 완료. 유일한 남은 게이트는 데이터 축적(시간 문제일 뿐 결정사항 아님)
- 작업 중 발견한 무관한 pre-existing uncommitted 변경(`jarvis/_state/*`, `research/agents/experiment_registry.jsonl`, `research/autoresearch/*`, 위 골드조사 섹션 포함 이 파일 자체의 기존 62줄)은 다른 세션/백그라운드 tmux 에이전트(seokminal-agent-*, polymarket-tick, hl-orderflow-tick) 소유로 판단, 손대지 않음

## 2026-07-15: 논문 기반 알파 마이닝 파이프라인 (Phase 133) — SDD 9태스크 전부 완료

### 완료된 작업
- 브레인스토밍→스펙(`docs/superpowers/specs/2026-07-15-paper-alpha-mining-design.md`) 승인 후 플랜 작성(`docs/superpowers/plans/2026-07-15-paper-alpha-mining.md`, e18921b), subagent-driven-development로 9태스크 전부 실행
- arXiv q-fin(PM/TR/ST/CP) 논문 자동 폴링(커서dedup, 재시도/백오프) → PDF텍스트추출 → LLM스펙추출(Claude CLI 서브프로세스 재사용, 신규 API키 불필요) → 자산커버리지필터(equity_intraday만 통과) → LLM코드생성(few-shot: 기존 strategies.py) → 스모크체크(exec+fixture OHLC, 크래시/전부-False·True/NaN/타입 차단) → `research/hypotheses/papers/`에 저장. 통과 못한 논문은 사유와 함께 `research/data/paper_pipeline/rejected.jsonl`에 기록
- 별도 러너(`run_paper_hypothesis_validate.py`)가 통과분을 기존 `runner.py` 제네릭 검증엔진에 태우고, 논문가설 전용 신규 격리 BH-FDR 풀(alpha=0.1)로 correction — 기존 수동가설 풀과 절대 안 섞음. CANDIDATE 나와도 라이브 집행은 기존 `arm_criteria` 게이트 그대로 통과해야 함
- Task 1/2/4/5/7/8은 각 1회 fix-and-re-review(마크다운 코드펜스 미제거, retry off-by-one, shape-validation 미처리 TypeError, 파일단위 exception 미격리 등 — 전부 plan 코드 자체의 robustness gap, 의도충돌 아님으로 판단 후 직접 수정). Task 3/6은 첫 리뷰 클린
- 전체 스위트 1074 passed / 4 pre-existing 실패만(test_auth.py×3, test_backtest_happy_path — 무관), main 직접커밋 컨벤션이라 별도 브랜치 없음

### 변경된 파일
- `research/papers/{__init__,llm_cli,arxiv_fetcher,coverage_filter,extract_spec,codegen_signal,smoke_check}.py` (신규)
- `research/run_paper_ingest.py`, `research/run_paper_hypothesis_validate.py` (신규)
- `pyproject.toml` (pdfplumber 의존성 + packages.find에 `research*` 추가)
- `tests/test_{llm_cli,arxiv_fetcher,coverage_filter,extract_spec,smoke_check,codegen_signal,run_paper_ingest,run_paper_hypothesis_validate}.py` (신규)

### 다음 할 일
- `python -m research.run_paper_ingest` 실제 1회 실행해서 라이브 arXiv 논문으로 파이프라인 end-to-end 검증(코드생성 품질/스모크체크 통과율 확인)
- 통과 가설 쌓이면 `python -m research.run_paper_hypothesis_validate`로 검증

### 막힌 부분/결정사항
- v1은 equity_intraday만(크립토/선물 코드생성 범위 밖), OS-level cron 자동화는 범위 밖(수동 트리거만)
- 최종 whole-branch 리뷰는 아직 미실행 — 다음 세션에서 `scripts/review-package e18921b <HEAD>`로 진행
- 스팟골드가 무료+뎁스 나오면 COMEX선물 경로(1OZ 무료여부 불확실)보다 더 확실한 대안일 수 있음 — 평일 데이터로 최종 결정

---

## 2026-07-16~17: KR turn-of-month 포트폴리오 paper_active 승격 + buyback v2 shadow forward 재확인 + US 내부자매수 재검 UNDERPOWERED 확정

### 완료된 작업
- `kr_turn_of_month_v1_PORTFOLIO` 재검증: data_gate PASS(real KRX PIT) → 포트레벨(월별 EW, 상관보정) 백테스트 재실행(n=84개월, net_mean=0.622%, random_pct=100%, p=0.002, WF전반 1.170%/후반 0.074% — 16배 감쇠 재확인) → `watchlist` → `paper_candidate`(config 동결, hash `a21e2aa...`) 전이. `jarvis/paper/deploy.py`의 `RUNNER_REGISTRY`에 등록된 `research.paper.tom_forward:generate`(monthly, hold=4일, envelope 비교)로 자동 forward 배선 완료 → `paper_active`(2026-07-16T17:26:33Z). `research/paper/tom_config.py`/`tom_forward.py`는 기존 코드 그대로 사용, 신규 작성 없음
- `kr_buyback_v2_regime_shadow`(레짐필터: 상승장 이벤트 제외) forward 재확인 — in-sample 개선 유지(net 1.575%→2.405%, 승률 50.7%→54.7%, n_v2=1170, v2_improves=true). forward(등록일 2026-07-03 이후)는 여전히 0건(buyback 공시 자체가 희소 이벤트라 14일로는 안 쌓임) — 승격 판단 보류. 스크립트가 FROZEN_DATE 기준 self-contained라 추가 wiring 불필요, 이벤트 쌓일 때까지 대기만 하면 됨
- US 내부자매수(Form4) buyback엣지 교차검증 재확인: 27개 대형주 유니버스 기준 총이벤트 24건/유효진입 13건 — **VERDICT UNDERPOWERED 확정**. 넓은 유니버스 없이는 재시도 무의미
- registry에서 buyback v2 shadow 중복 draft 항목 발견(`kr_buyback_x_regime_v2shadow` vs `kr_buyback_v2_regime_shadow`, 둘 다 2026-07-03 등록, config_hash 다름) — 실제 스크립트(`buyback_v2_forward.py`)가 참조하는 hypothesis_id는 후자, 전자는 죽은 중복. append-only 로그라 정리 안 함(위험 대비 이득 없음)

### 변경된 파일
- 없음(전부 registry 상태전이 + 기존 forward 스크립트 실행/확인 — 신규 코드 작성 없음)

### 다음 할 일
- tom forward: 매월 말 4일 보유 코호트 자동 누적 — 3개월(최소)~12개월(권장) 관찰 후 WF 후반 감쇠가 forward에서도 재현되는지가 KILL/유지 판단 기준
- buyback v2 shadow: 신규 buyback 공시 쌓일 때까지 대기, forward 이벤트 생기면 `research/paper/buyback_v2_forward.py` 재실행해 in-sample 개선 재현 여부 확인
- CB/BW 발행 = negative-drift 리스크필터(공시 후 하위5% 확인됨, 2026-07 초 검증) — 아직 아무 전략에도 안 묶임. buyback이나 다른 전략의 진입회피 필터로 붙이려면 v1은 동결이라 새 v3 shadow로 등록해야 함 — 미착수, 다음 세션 후보
- US 내부자매수 UNDERPOWERED — 유니버스 확장(현재 27개 대형주) 시 재시도 가능, 미착수
- `kr_buyback_size_decomp`, `tsmom_x_regime_v2shadow` — 스크립트 자체가 없음, 새로 설계 필요(가벼운 트랙 아님)

### 막힌 부분/결정사항
- 없음. buyback v2/CB-BW필터/내부자매수 유니버스확장/신규 분해가설 셋 다 "결정 대기"가 아니라 "데이터 축적 또는 설계작업 미착수"라 지금 할 게 없는 상태

## 2026-07-17: `/orderflow` 대시보드 신규 지표(체결속도+VWAP밴드) 조합 가설 1차 검증 — REJECT

### 완료된 작업
- 이번 세션 앞서 대시보드에 새로 붙인 두 라이브 지표(체결속도 패널 `tape_trades_per_sec`, day/week/month VWAP ±1σ/±2σ 밴드)를 처음으로 결합한 조합 가설 작성: `research/strategies/orderflow_tape_vwap.py`. 신호 = 체결속도가 rolling median(60봉) 대비 2.5배 이상 튀는 "버스트" 구간에서 가격이 day-VWAP ±1σ 밴드 밖이면 그 극단을 페이드(밴드위 버스트=SELL, 밴드아래 버스트=BUY). 체결속도는 `orderflow/aggregator.py`의 `TAPE_WINDOW_SEC`(10초 슬라이딩)를 그대로 import해 라이브 백엔드와 정의 일치, VWAP은 프론트(`computeVwapBands`)와 같은 ±1σ 개념이나 typical price를 봉 h/l/c 평균 대신 틱 price 자체로 계산(의도적 차이, 주석 명시)
- `research/validation/*`(engine/baselines/metrics/multiple_testing) 기존 하네스 그대로 재사용, 신규 검증 인프라 없음. `walk_forward.py`(closes만 받아 구간별 signal_fn 재계산)는 day-VWAP의 구간간 causal 누적과 안 맞아 미사용 — 대신 전체 이력 기준 계산된 거래를 진입시점 5구간으로 나누는 `_windowed_consistency()`로 대체(문서화된 의도적 이탈)
- 실행 러너 `research/run_orderflow_tape_vwap.py` 작성, HL 틱 8일치(2026-07-10~17, `research/data/hl_orderflow_tick/{BTC,ETH}_*.jsonl`)로 BTC.HL/ETH.HL 실행. 결과: BTC.HL 38거래 total_pnl=-26.42 p=0.3593(64.2%ile) → **INDISTINGUISHABLE**, ETH.HL 26거래(<30) → **UNDERPOWERED**(그마저 방향성 음수, p=0.982). 이 가설 전용 BH-FDR 풀(alpha=0.1)에서도 둘 다 생존 실패(0/2). 리포트: `research/reports/alpha/orderflow_tape_vwap_{BTC,ETH}.HL.{json,md}`
- 판정: **REJECT**(1차 생존조차 실패) — 기존 오더플로우 가설군(footprint/absorption/cvd/stop-run/wall/iceberg/confluence/gated_confluence, 전부 REJECT)과 동일 결론에 합류. "체결속도+VWAP 조합" 자체가 특별할 이유 없었다는 사전 예상대로

### 변경된 파일
- 신규: `research/strategies/orderflow_tape_vwap.py`, `research/run_orderflow_tape_vwap.py`
- 신규 리포트: `research/reports/alpha/orderflow_tape_vwap_BTC.HL.{json,md}`, `research/reports/alpha/orderflow_tape_vwap_ETH.HL.{json,md}`

### 다음 할 일
- TPO 마켓프로파일 / 스푸핑 휴리스틱 조합 가설은 보류 — L2 depth 수집(`research/data/hl_orderflow_depth/`)이 2026-07-17 하루치뿐이라 표본 부족, 1~2주 더 쌓일 때까지 대기(수집기는 이미 tmux 상시 실행 중, 추가 작업 불필요)
- ETH.HL은 UNDERPOWERED라 데이터만 더 쌓이면(현재 컬렉터가 계속 도는 중) 재실행 가치 있음 — 단, 파라미터(2.5배/60봉/±1σ)는 튜닝하지 않고 그대로 재실행만
- 이 결과로 오더플로우 트랙(HL 틱 기반) 가설이 사실상 모두 소진됨 — 다음 알파 탐색은 오더플로우 바깥 트랙(TSMOM/KR 포트폴리오 계열)이 우선순위 높음, 오더플로우는 depth 데이터 쌓일 때까지 휴면

### 막힌 부분/결정사항
- 없음. REJECT는 명확한 결과이지 막힘이 아님 — depth 데이터 부족만 "대기" 상태

## 2026-07-17: 오더플로우 트랙 전체 종합 — 배치 5개 합산 BH-FDR 감사(retrospective)

### 완료된 작업
- 지금까지 별도 풀로 돌렸던 오더플로우 배치 5개(①`run_orderflow_futures_on_btc.py` 14개: footprint_imbalance/absorption/cvd_divergence/confluence/stop_run×3horizon × BTC·ETH, ②같은 스크립트의 context-gate `gated_confluence` 2개, ③`orderflow_absorption.py`의 1분봉 dominance-ratio absorption 2개, ④같은 파일 `large_trade`(rolling p95 1분봉) 2개, ⑤`large_trade_event`(10/30/60s 고정청산) 6개, ⑥오늘 만든 `tape_vwap_fade` 2개) — 총 28개 p-value를 하나의 풀로 합쳐 `benjamini_hochberg(alpha=0.1)` 재실행(원래는 "새 가설은 별도 풀"이 기본 원칙이라 지금까지 안 섞었음, 이번엔 유저 요청으로 트랙 전체 조망 목적의 1회성 감사)
- IB(NQ/MNQ) `orderflow_futures_*` 리포트는 풀에서 제외 — IB 오더플로우 수집기가 실제로 가동된 적이 없어(수집 데이터 0) n_bars=20/n_trades=0~1짜리 사실상 더미값이라 HL 8일치 실데이터와 같은 풀에 넣으면 왜곡만 됨
- **결과: 28개 중 7개 생존**(threshold p<=0.01): `ETH:footprint_imbalance`(p=0.0100) + `large_trade_event` 6개 전부(BTC/ETH × 10s/30s/60s, 전부 p=0.002=하한선, 500회 랜덤런 전부를 이김)
- **그러나 7개 생존 전부 net PnL<=0** — `ETH:footprint_imbalance`는 총손익 -3,194.56(방향예측력은 유의하나 역시 비용 못 이김), `large_trade_event` 6개는 이미 개별 리포트에서 `SIGNAL-BUT-SUBCOST` 판정 확정돼 있었음(방향예측력 유의 + net PnL<=0). 즉 다중검정 보정을 통과한 신호가 있긴 하지만 **거래 가능한 알파는 여전히 0개** — `_verdict()` 스케일의 "EDGE CANDIDATE"(percentile>=95 and PnL>0) 기준을 만족하는 항목 없음
- 통계적 주의사항 기록: `large_trade_event`의 6개 생존은 같은 이벤트셋(대량체결 발생시점)에 대한 10s/30s/60s 3개 청산호라이즌 × 2심볼일 뿐 — 독립검정이 아니라 유사반복(pseudo-replication)이라 "실질 독립발견"은 사실상 2건(BTC 이벤트방향성, ETH 이벤트방향성)으로 봐야 함. BH-FDR은 완전독립을 가정하지 않지만(PRDS 조건에서도 유효) 해석 시 과대평가 주의
- 트랙 결론: HL 틱 데이터로 시도 가능한 오더플로우 방향예측 신호(footprint/absorption/cvd/stop-run/large-trade/confluence/context-gate/tape-vwap) 전부 REJECT 또는 SIGNAL-BUT-SUBCOST — **거래비용(HL taker 6bps)을 이기는 오더플로우 알파는 이번 세대의 데이터·신호 설계로는 없음**. 방향예측력 자체는 대량체결 이벤트 주변에서 재현성 있게 나타나지만(p=0.002 반복), HL taker 수수료+슬리피지 구조에서 그 정도 방향우위로는 net positive가 안 나옴

### 변경된 파일
- 없음(기존 리포트 재집계 + `run_orderflow_futures_on_btc.py` 1회 재실행뿐, 신규 코드 없음)

### 다음 할 일
- SIGNAL-BUT-SUBCOST 신호(large_trade_event, footprint_imbalance)를 살리려면 taker 대신 maker 체결(비용 6bps→1.5bps)로 재검증하는 경로가 있음 — 단 이벤트 반응형 신호라 maker로 제때 체결될지 자체가 의문이라 미착수(체결모델 재설계 필요, 가벼운 작업 아님)
- TPO/스푸핑은 여전히 depth 데이터 부족으로 보류(Phase 위 항목과 동일)
- 이걸로 오더플로우 트랙(HL 틱 기반) 1차 스크리닝은 사실상 마무리 — 추가 신호 아이디어보다는 TSMOM/KR 포트폴리오 등 이미 생존 신호 있는 트랙에 시간 쓰는 게 기대값 높음

### 막힌 부분/결정사항
- 없음. 감사 결과가 명확(REJECT/SUBCOST뿐, EDGE CANDIDATE 0개) — 막힌 게 아니라 결론이 난 것

## 2026-07-17: 오더플로우 프리미티브 8개 전조합 스윕(72개) — 수익률/승률 중심, 0/70 생존

### 완료된 작업
- 유저 지시("기존 조합까지 다 포함해서 너가 주도적으로 조합 만들어봐, 몇 개든 상관없어, 수익률/승률 중심")로 개별 검증됐던 8개 프리미티브(footprint_imbalance, absorption[노이즈플로어], cvd_divergence, large_trade[1분봉 p95], tape_vwap_fade, vwap_window[240봉 롤링], trend_15m, key_level_15m)를 하나의 60s bar 피처행렬 위에 통합하는 신규 모듈 `research/strategies/orderflow_signal_matrix.py` 작성. 기존 4개 구현이 버킷 키 방식이 서로 달라(`OrderflowAggregator`는 float `floor(ts/60)*60`, absorption/tape_vwap/context_gate는 int `ts//60`) 조합 시 정렬오류 위험 있어, 원시 틱을 단일 causal 패스로 한 번만 훑어 전부 같은 bar 인덱스에 얹는 방식 채택. 모든 임계값은 재조정 없이 기존 파일에서 그대로 import(`FOOTPRINT_IMBALANCE_RATIO=0.7`, `ABSORPTION_DOMINANCE_RATIO=0.7`, `TAPE_BURST_MULTIPLIER=2.5`, `VWAP_BAND_SIGMA=1.0` 등)
- 조합 생성 2종: ①페어와이즈 AND(둘 다 판정 가능+방향 일치할 때만 신호, `C(8,2)=28`개) ②killzone(13:30-15:00 UTC) 컨텍스트 게이트(단일 프리미티브 8개 각각). 심볼당 36개 × BTC/ETH = 72개. stop_run/large_trade_event/wall_proximity/iceberg_refill은 이벤트형이거나 depth 필요라 bar 행렬 스코프에서 제외(기존 모듈에서 이미 별도 검증됨)
- 러너 `research/run_orderflow_signal_matrix.py`로 8일치 HL 틱 전체 실행(BTC 2,047,637틱/10,259봉, ETH 1,169,738틱/10,260봉), 이 스윕 전용 BH-FDR 풀(다른 배치와 안 섞음)
- **결과: 70개 유효표본 중 BH-FDR 생존 0개.** 수익률 1위는 `BTC.HL:tape_vwap+trend_15m`(+87.88, 승률81.8%, p=0.014)이나 거래 11건뿐 → underpowered, 신뢰불가. PnL 양수인 조합은 전부 거래수<30(underpowered). **표본이 충분한 조합(n≥30) 전부 net PnL 음수** — 최고 승률조차 39.6%(`ETH.HL:cvd+killzone`, PnL -100.82), 최악은 `ETH.HL:footprint+large_trade` 1562건 PnL -1,722.84
- 판정: 조합을 8개→72개로 넓혀도 결론 불변. "표본 충분하면서 수익 나는 조합"이 하나도 없다는 건 검색 범위 문제가 아니라 이 8개 프리미티브 자체(1분봉/HL taker 6bps 비용구조)에 방향성 우위가 부족하다는 뜻으로 해석. 오더플로우 트랙(HL 틱 기반) 결론이 이전 두 배치(REJECT/SUBCOST뿐)와 완전히 합류 — 조합 차원에서도 재확인됨

### 변경된 파일
- 신규: `research/strategies/orderflow_signal_matrix.py`, `research/run_orderflow_signal_matrix.py`
- 리포트 파일 없음(스크리닝 전용 스크립트, stdout만 — 개별 확정 가설이 아니라 탐색이라 `build_report()` 미호출. 필요시 위 stdout 로그가 유일 기록)

### 다음 할 일
- 오더플로우 트랙(HL 틱 기반)은 프리미티브 단위·조합 단위 둘 다 소진 판단 — 추가 조합 탐색보다 depth 데이터(TPO/스푸핑)가 쌓이거나 새로운 데이터 소스(L2, 펀딩레이트 외 다른 축)가 생기기 전까진 이 트랙에 더 시간 안 씀
- TSMOM/KR 포트폴리오처럼 이미 생존 신호 있는 트랙 우선순위 유지(변경 없음)

### 막힌 부분/결정사항
- 없음. 72개 조합 스윕도 명확히 REJECT — "더 조합해봐야 하나 안 나온다"가 결론

## 2026-07-17: 3-way/4-way AND + 다수결 조합 스윕, 메이커비용 재검증, TPO 신규 가설 — 전부 REJECT

### 완료된 작업
- 유저가 72개(2-way) 스윕 결론("없다")을 재차 거부("그럴 리 없어, 3,4개로 조합해서 나올만한 거는?") → `combine_and_n()`(k-way 일반화 AND)을 `orderflow_signal_matrix.py`에 추가해 3-way(`C(8,3)=56`/심볼, 러너 `run_orderflow_signal_matrix_k3.py`) 실행. **결과: 112개 중 유효 99개, BH-FDR 0/99 생존.** n≥30 최고 승률도 54.0%(`BTC.HL:absorption+cvd+key_level_15m`, 37건, PnL -4.34)
- k가 커질수록 AND 교집합(공동 eligible)이 기하급수로 줄어 표본이 죽는 패턴이 3-way부터 뚜렷 — "AND가 너무 빡빡해 신호를 못 본 것" 가설과 "애초에 신호가 없는 것" 가설을 가르기 위해 4-way AND(`C(8,4)=70`/심볼) + 합의기준 낮춘 다수결(`combine_majority_vote`, 3/4/5/6-of-8, 4/심볼)을 같이 실행(`run_orderflow_signal_matrix_k4_majority.py`). **결과: 148개 중 유효 103개, BH-FDR 0/103 생존.** 다수결로 합의기준 낮추자 표본은 커졌으나(3-of-8: BTC 1365건/ETH 1449건) 승률이 8.7%/11.7%로 폭락, PnL도 -1580/-1628로 급격히 악화 — **"AND가 빡빡해서 숨겨진 신호를 놓쳤다" 가설은 기각**(기준 완화하니 오히려 더 나빠짐, 신호 자체가 없다는 쪽이 맞음)
- 유저 지시("비용모델 바꿔보기 / 다른 신호축 전환, 1,2 둘 다") 수행: ①이전 감사에서 BH-FDR 생존했던 7개(전부 net PnL<=0, SIGNAL-BUT-SUBCOST) — `ETH:footprint_imbalance` + `large_trade_event` 6개 — 를 taker(6.0bps) 대신 maker(3.0bps, `hl_effective_cost_bps(taker=False)`) 가정으로 재실행(`run_orderflow_maker_cost_retest.py`, `orderflow_absorption.py`의 `run_large_trade_event_hypothesis`에 `taker: bool` 파라미터 추가해 비용만 스위치 가능하게 함). **결과: 비용 절반으로 줄여도 전부 여전히 net PnL 음수** — 손실폭만 대략 절반(예: ETH footprint -3217→-1521, BTC large_trade 60s -135112→-65546), 부호는 하나도 안 바뀜. 비용이 병목이 아니라 신호 자체의 방향우위가 taker든 maker든 손실을 못 이길 만큼 약하다는 뜻(maker 체결은 이상화 가정 — 반응형 신호라 그 타이밍에 리밋오더가 실제 체결됐을지는 별개 문제, 결과는 "비용만 낮아지면 얼마나 회복되는지"의 상한치로만 해석)
- ②TPO/스푸핑(다른 신호축) 착수 전, 이전 세션들에서 반복해온 "TPO는 depth 데이터 부족으로 보류" 판단이 **틀렸음을 발견**해 정정 — `lib/orderflow-data.ts`의 `computeTpoProfile`을 직접 읽어보니 TPO는 체결틱(`FootprintCell`, 가격×60s버킷)만으로 계산되고 잔량/호가창(depth)은 전혀 안 씀. 즉 8일치 틱 데이터로 바로 백테스트 가능했던 걸 depth 부족 핑계로 계속 미뤄온 것 — 이번에 정정하고 실제 백테스트 진행
- TPO 프론트 로직(`TPO_PERIOD_SEC=1800`, `VALUE_AREA_PCT=0.7`, POC 탐욕확장 알고리즘)을 그대로 이식한 신규 가설 모듈 `research/strategies/orderflow_tpo.py` 작성 — 종가가 Value Area 밖(VAH 위/VAL 아래)이면 페이드(day-VWAP 밴드 페이드와 동일 직관, 다른 지표축). `MIN_WARMUP_PERIODS=4`(2시간)만 이 파일에서 새로 정한 사전값. 러너 `run_orderflow_tpo.py`로 BTC.HL/ETH.HL 8일치 실행. **결과: 승률은 68.2%/75.0%로 높지만 eligible 9587/9598건 중 실제 거래는 22/16건뿐 — VA 밖 이탈 자체가 드묾. underpowered, PnL도 음수(-45.28/-49.49), p=0.71/0.79로 랜덤과 무구분. BH-FDR 0/2 생존** → REJECT(승률 숫자만 보면 낚이지만 표본 붕괴로 무의미)
- 스푸핑: `research/data/hl_orderflow_depth/{BTC,ETH}_2026-07-17.jsonl`에 `grep -c "spoof_alert"` 재확인 — 여전히 하루치뿐(신규 파일 미생성), **spoof_alert 0건 그대로**. "데이터 더 쌓일 때까지 대기"가 아니라 "현재 휴리스틱(SPOOF_SIZE_MULTIPLIER=5.0배)이 하루 종일 라이브로 돌면서 단 한 번도 안 뜸"이 실제 결과 — 임계값이 너무 빡빡하거나(관찰 안 됨) 이 시장/사이즈대에서 해당 패턴 자체가 희귀할 가능성

### 변경된 파일
- 신규: `research/run_orderflow_signal_matrix_k3.py`, `research/run_orderflow_signal_matrix_k4_majority.py`, `research/run_orderflow_maker_cost_retest.py`, `research/strategies/orderflow_tpo.py`, `research/run_orderflow_tpo.py`
- 수정: `research/strategies/orderflow_signal_matrix.py`(`combine_and_n`/`combine_majority_vote`/`run_matrix_k`/`run_majority_matrix` 추가), `research/strategies/orderflow_absorption.py`(`run_large_trade_event_hypothesis`에 `taker: bool = True` 파라미터 추가, 하위호환)
- 신규 리포트: `research/reports/alpha/orderflow_tpo_{BTC,ETH}.HL.{json,md}`

### 다음 할 일
- 오더플로우 트랙(HL 틱): 2-way/3-way/4-way/다수결/메이커비용/TPO/스푸핑까지 전부 REJECT 또는 SIGNAL-BUT-SUBCOST — **탐색 범위·비용모델·신호축 세 방향 다 막다른 길 확인 완료**. 이 트랙에 더 시간 쓰는 건 기대값 낮음, TSMOM/KR 포트폴리오 트랙에 집중 권장
- 스푸핑은 임계값(5.0배) 완화나 다른 depth 신호(불균형, 유동성벽 두께 변화 등) 시도 여지는 있으나 이번 세션 스코프 밖 — 유저가 원하면 별도 트랙으로 새로 시작
- TPO는 30분 구간 대신 더 짧은 구간(예: 15분)으로 시도하면 eligible→실거래 전환율이 오를 수 있으나 이건 파라미터 튜닝이라(프론트 값 1800s에서 이탈) 임의로 하지 않음, 유저 승인 필요

### 막힌 부분/결정사항
- 없음. 세 방향(범위확장/비용모델/신호축전환) 다 명확히 REJECT — 오더플로우 트랙 1차 스크리닝은 사실상 완전히 마무리된 상태로 판단

## 2026-07-17: TSMOM 월간 forward-test 재실행 (15일 만에 갱신)

### 완료된 작업
- 마지막 실행이 07-02(15일 전)라 캐시 데이터 정체 확인 → `futures_loader.py`(TWS IB_PORT=7498로 재확인, 기본 7496 아님) 재실행해 32시장 일봉 07-17까지 pull → `research/paper/tsmom_forward.py --since 2026-06` 재실행
- config 미변경 확인(동결 그대로). **결과: 2026-06 -1.46%, 2026-07 -0.26%(월중) 둘 다 envelope 안(P10 -1.74%~P90 +2.94%), 이탈 없음.** Sharpe 0.557(직전 0.562와 거의 동일), regime_score 0.774→0.725로 소폭 하락(트렌드 강도 약간 약해짐 — TSMOM 본질상 reject 사유 아님, 관찰만). sleeve: softs 1위(0.818)로 순위 유지, rates 여전히 마이너스(-0.073)
- 판정: 정상 관찰 중, envelope 이탈 없음. 튜닝/개입 없음(규율 유지)

### 변경된 파일
- `research/paper/tsmom_forward_report.md`, `tsmom_forward_ledger.jsonl` 갱신(코드 변경 없음, 데이터만)

### 다음 할 일
- IB_PORT은 이 환경에서 **7498**(코드 기본값 7496 아님) — 다음에도 `IB_PORT=7498`로 실행할 것
- `tsmom_forward.py`는 로컬 캐시(`intraday_store`)만 읽음, IB 직접 연결 안 함 — 최신 데이터 반영하려면 `futures_loader.py`를 먼저 돌려야 함(순서: loader → forward)
- 다음 재실행은 자연스러운 월간 체크포인트(8월 초) 또는 유저 요청 시

### 막힌 부분/결정사항
- 없음

## 2026-07-18: AI 에이전트 잔고 안 움직임 + Polymarket 다각화 정산 멈춤 버그 2건

### 완료된 작업
- **유저 리포트**: "lv5 가상화폐 -42% 수익률인데 보유금액은 100 그대로" → `api_server/router_autopilot.py`의 `agent_performance()`/`agents_overview()` 둘 다 `cash = alloc - invested`로 계산해 realized_pnl을 아예 안 반영하고 있었음(143건 매매로 -42 USDC 손실 나도 cash는 그대로). `cash = alloc + realized_pnl - invested`로 수정. 브라우저로 재확인: 수익률 -41.79% / 현금 -41.69 USDC로 정상 반영.
- 같은 조사 중 2차 버그 발견: 위 두 함수 포함 `router_autopilot.py` 6곳이 `agent_store.read_cycles(agent_id, limit=1000)`로 최근 1000 cycle만 읽어 FIFO 성과 계산 — lv5 가상화폐는 이미 cycle 2399건 누적(5분 간격 상시 tick), 1000 캡을 넘어서면서 오래된 체결이 창밖으로 밀려나 거래건수·realized_pnl이 시간 지날수록 조용히 줄어드는 중이었음(재시작과 무관, 143→120건도 이 창 슬라이딩 때문). `god_mode.py`가 이미 같은 문제를 `limit=100000`으로 우회해둔 전례가 있어 동일하게 6곳 전부 100000으로 상향.
- **유저 리포트 2**: "폴리마켓 다각화 안 도는 것 같다, 만기 지난 게 결과 반영 안 됨" → 루프 자체(`polymarket_bot.py`의 `_loop`)는 매 tick(1시간)마다 정상 동작 중이었으나(`last_run` 계속 갱신), `polymarket/client.py`의 `get_market()`이 Gamma API `/markets?condition_ids=...` 호출 시 `closed` 파라미터를 안 넘겨서 — 이 API가 파라미터 미지정 시 암묵적으로 `closed=false`처럼 걸러버림 — 실제로 만기·정산된 마켓은 항상 빈 리스트로 응답받음. `_process_resolutions()`는 `None`을 "조회 실패, 다음 tick 재시도"로 처리해서 정산된 포지션이 영원히 큐에 남아있었음(15슬롯 중 6개가 최대 8일째 미정산 상태로 발견). `get_market()`이 `closed=false`→`closed=true` 순으로 재시도하도록 수정. 재시작(reload) 직후 자동 tick으로 즉시 검증: 7건 정산(realized_pnl 0→+31.36 USDC) + 빈 슬롯 7개 신규 배팅으로 자동 채움 확인.
- 세 버그 다 pytest 전체(1145 passed / pre-existing 5 fail 그대로) + 브라우저 라이브 확인 완료.

### 변경된 파일
- `api_server/router_autopilot.py` — `cash` 계산식 2곳 수정, `read_cycles` limit 1000→100000 6곳
- `polymarket/client.py` — `get_market()` open→closed 재시도 로직
- (dashboard) `seokminal-dashboard/app/agents/page.tsx` — 에이전트 카드 "자본" 라벨 → "배정"(배정 자본이지 현재 잔고 아님, 오늘 유저가 헷갈린 지점)

### 다음 할 일
- 포트폴리오 파이차트가 현금 음수일 때 0%로 클램프돼서 "계좌 거의 다 날림"이 시각적으로 안 보임 — UX 개선 여지 있음, 아직 미착수.

### 막힌 부분/결정사항
- 없음

---

## 2026-07-18: Polymarket 다각화 봇 — 만기 상한 필터 추가 + 커밋 정리

### 완료된 작업
- 위 정산 버그 고친 뒤 유저 확인: "지금도 30달러 이득이라매, 여기서 더 발전하면 되겠네 어차피 페이퍼인데" → 다각화 스코프는 이미 카테고리 무필터(전 종목 거래량순 스캔)였으나 만기 상한이 없어서(`min_days_to_resolution`만 있고 max 없음) 2027년 만기 같은 시장도 진입 대상이었음. `max_days_to_resolution`(기본 30일) 신규 필터 추가 + 스캔 후보 `get_markets(limit=300→500)`로 확대.
- 두 레포 전부 미커밋 상태였던 것 정리해서 커밋함(오늘 세션 버그픽스 3건 + Bloomberg UI 롤아웃 28파일 + 사이드바 수정 + 이번 만기상한 필터, 총 5커밋). 커밋 중 `research/data/{cross_venue_skew,polymarket_tick 등}` 20GB+ 틱 원자재 디렉토리가 gitignore 안 걸려있던 걸 발견 — `git add -A` 전에 잡아서 `.gitignore`에 추가, 커밋 안 되게 막음.
- pytest 전체(1146 passed / pre-existing 5 fail 그대로, 신규 `test_scan_and_enter_skips_too_far_maturity` 추가) + tsc 클린 + `--reload` 자동 반영 라이브 확인(`max_days_to_resolution: 30` status에 정상 노출).

### 변경된 파일
- `api_server/polymarket_bot.py` — `max_days_to_resolution` config 필드(기본 30) + `_scan_and_enter` 필터링, `get_markets` limit 300→500
- `tests/test_polymarket_bot.py` — `_market()`에 `days_out` 헬퍼 인자 추가, 만기상한 스킵 테스트 신규
- `.gitignore` — 20GB+ 틱/오더북 데이터 디렉토리 8개 추가
- (dashboard) `lib/api.ts`, `app/polymarket/page.tsx` — `max_days_to_resolution` 타입/진입필터 UI 필드

### 다음 할 일
- 없음 (요청받은 항목 전부 완료)

### 막힌 부분/결정사항
- `max_days_to_resolution` 기본값 30일은 임의 선택 — 유저가 UI에서 직접 튜닝 가능("최대잔여일" 필드로 노출됨)

---

## 2026-07-20: 폴리마켓 이벤트 내 후보군 합산 괴리 탐지 (신규 기능)

### 완료된 작업
- SNS 스캠 광고("크로스마켓 괴리 탐지") 검토 중 아이디어 자체는 유효 판단 → brainstorming으로 스코프 확정: "같은 이벤트 내 후보군 YES가격 합산 괴리"만(크로스*이벤트* 논리상관관계는 범위 밖), 접근법은 폴링 스캐너(WSS/하이브리드 대신)
- spec 작성/커밋(`docs/superpowers/specs/2026-07-20-polymarket-event-divergence-design.md`, `bab5ef1`) → plan 작성/커밋(`docs/superpowers/plans/2026-07-20-polymarket-event-divergence.md`, `810c343`). 플랜 자체 리뷰에서 spec 내부 불일치(`fee_buffer` 파라미터가 4·9절 "판단은 스캐너 책임 아님"과 모순) 발견해 fee_buffer 완전 제거로 해소, 에러처리 누락(`run_forever` try/except) 발견해 추가
- Subagent-Driven Development로 구현: Task1 `research/polymarket_event_divergence/collector.py`(group_by_event/compute_divergence/run_once, 순수함수+get_markets 재사용) — 리뷰 클린, 12/12 테스트. Task2 `research/run_polymarket_event_divergence_scan.py`(append_snapshots/run_forever, JSONL 적재+에러시 사이클스킵) — 리뷰 클린, 5/5 테스트
- Task2 implementer가 보고한 전체스위트 "557 passed"가 이상해서 직접 재검증 → 실제 1239개 중 1234 passed/5 failed(전부 기존 known failure: test_auth×3, test_backtest_happy_path, test_orderflow_ib_adapter×1), 회귀 없음 확인. implementer 보고 오류로 결론(코드 문제 아님)
- 최종 브랜치 리뷰(opus): Task1↔Task2 시그니처/스키마 정합, fee_buffer 전무, get_markets 필드계약 일치 전부 검증 — READY TO MERGE. → `origin/main` 푸시(`30862b5`)

### 변경된 파일
- 신규: `research/polymarket_event_divergence/{__init__.py,collector.py}`, `research/run_polymarket_event_divergence_scan.py`, `tests/test_polymarket_event_divergence_collector.py`, `tests/test_run_polymarket_event_divergence_scan.py`
- 문서: `docs/superpowers/specs/2026-07-20-polymarket-event-divergence-design.md`, `docs/superpowers/plans/2026-07-20-polymarket-event-divergence.md`
- `.gitignore` — `research/data/polymarket_event_divergence/*.jsonl` 추가(수집 원자재, 로컬 전용)

### 다음 할 일
- 이번 세션은 **데이터 수집까지만**(스코프 명시적) — 어느 divergence 크기가 실제 유효 시그널인지 판단 로직 없음. 데이터 쌓인 뒤 사람이 보고 임계치 결정 → 후속 `run_polymarket_arb_validation.py` 같은 검증 스크립트로 발전 가능(유저 요청 시)
- 최종 리뷰 Minor(안 고침, 참고만): `collector.py`의 `get_markets(limit=300)` 하드코딩 — 후보 많은 대형 이벤트가 300개 한도에 잘리면 인위적 divergence 부풀림 가능(스냅샷에 `n_markets` 기록되니 분석 단계에서 교차검증 필요, 명명상수화하면 좋음)
- 아직 tmux 상시구동 안 올림 — 이번 스코프 밖(스펙 §7에 명시), 필요시 유저 요청으로 별도 착수
- (이전 세션 이월, 미착수) `api_server/router_autopilot.py` 포트폴리오 파이차트 현금 음수시 0% 클램프 UX 이슈
- (이전 세션 이월, 미착수) `research/data/krx_api.py`의 `.env` 경로 불일치(`data/.env` vs 루트 `.env`) — 매번 수동 export 필요
- (이전 세션 이월, 미착수) `congress_forward.py`/`form4_forward.py` 여전히 미실행(exploratory 상태)

### 막힌 부분/결정사항
- 없음

## 2026-07-18: buyback 월간 forward-test 재실행 (16일 만에 갱신)

### 완료된 작업
- 유저 확인 후("더 해야하는 부분 있음?" → buyback도 정체 발견) KRX 가격(07-07까지 캐시) + DART 이벤트(07-16까지 이미 최신, 안 건드림) 갱신 시도 → `KRX_API_KEY` 환경변수/`data/.env` 둘 다 없어서 `pull_range` 실패
- 원인: `research/data/krx_api.py`의 `_cfg()` 폴백이 `data/.env`(=`seokminal-multi-venue/data/.env`)를 보는데, 실제 키는 프로젝트 루트 `seokminal-multi-venue/.env`에 있음 — 경로 불일치. 이번엔 셸에서 직접 export해서 우회(코드 수정 안 함, 버그 재현 확인만)
- KOSPI/KOSDAQ 가격 07-08~18(6거래일) pull 완료 → `research/paper/buyback_forward.py --since 2026-07` 실행했더니 forward 코호트 비어있음(정상 — hold=20거래일 미완결이라 7월 이벤트는 아직 청산 전) → `--since 2026-06`으로 재실행
- **결과: overall n=1603→1685(신규 이벤트 반영), 중앙값 -0.00086→+0.00011(제로 근방 유지, 팻테일이라 변동 큼, 예상 범위). 2026-06 코호트 n=90, 중앙값 +1.9% → envelope 안**(월코호트중앙값 P10 -3.0%~P90 +3.7%), 이탈 없음
- 판정: 정상 관찰 중. 튜닝/개입 없음

### 변경된 파일
- `research/paper/buyback_forward_report.md`, `buyback_forward_ledger.jsonl` 갱신(코드 변경 없음)
- `data/krx/{kospi,kosdaq}/*.parquet` 신규 6일치

### 다음 할 일
- **버그 아님이지만 불편**: `KRX_API_KEY` 쓰려면 매번 `export $(grep -E "^KRX_API_KEY=|^KRX_BASE_URL=" .env | xargs)` 수동 실행 필요(또는 `data/.env`에 키 복사해두면 `_cfg()` 폴백이 알아서 찾음) — 다음 세션에서도 이 이슈 반복될 것, 고치려면 `krx_api.py`의 폴백 경로를 프로젝트 루트 `.env`로 바꾸거나 `data/.env`에 심볼릭링크
- congress_forward.py/form4_forward.py는 여전히 미실행(config/ledger 없음, exploratory 상태) — 필요시 유저 요청 시 착수

### 막힌 부분/결정사항
- 없음

## 2026-07-21: 폴리마켓 샤프월렛 컨버전스 시그널 (설계→구현→리뷰→push 전체 완료)

### 완료된 작업
- `superpowers:brainstorming` → 스펙 작성(`docs/superpowers/specs/2026-07-20-polymarket-sharp-wallet-design.md`) → `superpowers:writing-plans` → 플랜 작성(`docs/superpowers/plans/2026-07-20-polymarket-sharp-wallet.md`) → 유저 선택으로 `superpowers:subagent-driven-development` 실행
- 6개 태스크 전부 구현+per-task 리뷰 클린(Task 2에서 실로직버그 2건 발견해 수정: `watch_until` 축소 방지 `max()` 처리, `wallet_rank`/`wallet_pnl`을 `is_anchor` 기준으로만 채움 — 둘 다 플랜 자체 샘플코드에 있던 버그였고 플랜의 산문 제약과는 안 모순되어 유저 에스컬레이션 없이 직접 수정)
- 최종 whole-branch 리뷰(opus, 백엔드+대시보드 diff 동시 검토) — HUD `polymarket_sharp_wallet_tick` 키/필드shape 크로스레포 일치, 전역 상수 전부 스펙과 일치, BH-FDR 풀 격리, no-trading 제약 확인 → **READY TO MERGE**, findings 0건
- 백엔드 전체 테스트 스위트 실행: 1270 pass, 5 fail(기존 pre-existing 4건 + `test_orderflow_ib_adapter.py` 무관 flake 1건, 이번 피처 커밋이 건드린 파일 아님을 확인)
- 두 repo 모두 `origin/main`으로 push 완료(직접 커밋 컨벤션, PR 없음)

### 변경된 파일
- 백엔드(`seokminal-multi-venue`, `fecb2b4..4561a40`, 7 커밋): `research/polymarket_sharp_wallet/{__init__,leaderboard}.py`, `research/run_polymarket_sharp_wallet_collect.py`, `research/hypotheses/polymarket_sharp_wallet.py`, `research/run_polymarket_sharp_wallet_validate.py`, `api_server/lab_api.py`(HUD 등록), 대응 테스트 5개 파일
- 대시보드(`seokminal-dashboard`, `e12fc91..2c63776`, 1 커밋): `lib/api.ts`(`polymarket_sharp_wallet_tick` 타입), `app/hud/page.tsx`(HUD 유닛 등록)

### 다음 할 일
- tmux 상시구동(`polymarket-sharp-wallet-tick` 세션) 아직 안 올림 — 다음 세션에 유저 요청 시 기동, 데이터 쌓이는 대로 `run_polymarket_sharp_wallet_validate.py`로 검증
- Minor(안 고침, 참고): 없음 — 최종 리뷰 findings 0건

### 막힌 부분/결정사항
- 없음

## 2026-07-21: 이월 잡일 2건 정리 (krx .env 경로, 포트폴리오 파이차트 마이너스 현금)

### 완료된 작업
- `research/data/krx_api.py`의 `_cfg()` .env 폴백 경로가 `data/.env`를 보고 있었는데 실제 키는 프로젝트 루트 `.env`에 있어서 매 세션 수동 export 필요했던 문제 수정 — 폴백 경로를 루트 `.env`로 변경, 테스트 2개 추가(`tests/test_krx_api_cfg.py`)
- 대시보드 `app/agents/page.tsx`의 `PortfolioPie`가 현금 음수일 때 `Math.max(cash,0)`으로 조용히 0%로 클램프돼 "계좌 거의 다 날림"이 시각적으로 안 보이던 UX 이슈 수정 — 마이너스일 때 빨간 경고줄로 실제 금액 노출. `lv5 가상화폐` 에이전트가 마침 라이브로 현금 -$129.31 상태라 브라우저에서 실제 렌더링 확인함(`현금 마이너스 $-129,31` 빨간 줄 정상 표시)

### 변경된 파일
- `seokminal-multi-venue`: `research/data/krx_api.py`, `tests/test_krx_api_cfg.py` (신규) — 커밋 `add345a`
- `seokminal-dashboard`: `app/agents/page.tsx` — 커밋 `c3826b8`

### 다음 할 일
- Nautilus 플랫폼 다음 엔진 sub-project 착수는 브레인스토밍 게이트 필요(뭘 만들지부터 정해야 함) — 유저 요청 시 착수
- `congress_forward.py`/`form4_forward.py` 여전히 미실행(exploratory 상태) — 필요시 유저 요청 시 착수

### 막힌 부분/결정사항
- 없음

## 2026-07-21: HUD collector 오탐 + dart_bot 무한 매도재시도 대응

### 완료된 작업
- `cross_venue_skew_tick` 수집기가 HUD상 dead로 보였던 원인 진단: tmux 세션이 죽었지만 실제 파이썬 프로세스는 PPID=1(launchd)로 reparent돼 20시간+ 정상 동작 중이었음(`_tmux_process_status`가 tmux 세션 존재 여부로만 판단 — 논tmux 고아 프로세스 감지 불가). 유저 승인받았으나 `kill -TERM` 자체가 auto-mode 클래시파이어에 하드 블록돼 유저 직접 실행 요청함 — **유저 응답 대기중, 아직 안 끝남**
- `dart_bot`이 유티아이(179900)를 5분마다 계속 매도 실패시키던 원인 규명: 07-08 매수 → 07-09 정상 손절매도(로컬 state에서도 정상 제거)됐는데, 이후 `dart_autobot.json`이 `positions` 키를 잃은 시점에 `_load()`의 1회 마이그레이션 로직이 재발동 — buy 로그만 스캔하고 sell을 반영 안 해서 이미 판 포지션을 그대로 복원. 이후 11일간 존재하지 않는 브로커 잔고를 계속 매도 시도 → "모의투자 잔고내역이 없습니다" 실패 로그만 무한 축적
- `api_server/dart_autobot.py`의 `_process_exits`에 desync 가드 추가: 매도 실패 메시지에 "잔고내역이 없습니다" 포함 시 로컬 state가 stale하다고 보고 포지션 드롭(재시도 중단), `kind:"desync"`로 로그 구분. 테스트 1개 추가(`test_sell_no_holdings_drops_stale_position`), `tests/test_dart_autobot_exits.py` 8/8 pass(신규 포함 7→8) — 실제로는 7개였고 신규 1개 추가로 7/7 → 커밋 시점 전체 실행 결과 7 passed
- `data/dart_autobot.json`에서 179900 stale 포지션 직접 제거(gitignore 대상, 커밋 불필요)

### 변경된 파일
- `seokminal-multi-venue`: `api_server/dart_autobot.py`, `tests/test_dart_autobot_exits.py` — 커밋 `f1e4e64`, push 완료

### 다음 할 일
- `cross_venue_skew_tick`: 유저가 `! kill -TERM 81256` 실행하면 → `POST /lab/collectors/cross_venue_skew_tick/restart` 호출해 tmux 세션으로 정상 편입, `/lab/status`로 `running:true` 확인, `tmux list-sessions`로 새 세션 확인
- Nautilus 플랫폼 다음 엔진 sub-project — 브레인스토밍 게이트 필요, 유저 요청 시 착수

### 막힌 부분/결정사항
- `kill -TERM`은 Claude Code auto-mode 클래시파이어가 유저 채팅 승인 이후에도 하드 블록 — 유저가 `!` 프리픽스로 직접 실행해야 함(세션 내 반복 확인된 제약)

## 2026-07-21: Polymarket 샤프월렛 confidence score — 설계+계획 완료, 구현 미착수

### 완료된 작업
- 유저가 준 SNS 마케팅 이미지 7장(IMG_9618~9624, 하이프 계정 — 수치는 연출로 판단, 참고용) 기반 기존 sharp-wallet convergence 기능 업그레이드 후보 6개 제시 → "시그널 스코어링/랭킹" 선택받음
- `superpowers:brainstorming` 풀 플로우로 설계 확정: 컨버전스 이벤트에 연속 0~100 confidence score 추가(기존 `convergence_bucket`은 안 건드림). 4개 컴포넌트(wallet_count/pnl_sum/notional/liquidity) 데이터셋 내 percentile 랭크 동일가중 평균. 범위는 연구/검증 전용, 라이브 알림 없음. 스펙 문서: `docs/superpowers/specs/2026-07-21-polymarket-sharp-wallet-scoring-design.md` (커밋 `e8ee32a`)
- `superpowers:writing-plans`로 구현 계획 작성: `docs/superpowers/plans/2026-07-21-polymarket-sharp-wallet-scoring.md` (커밋 `2cde86a`). Task 1 = `research/hypotheses/polymarket_sharp_wallet.py`에 `build_convergence_score()` 추가 + `build_labels_multi_horizon` score pass-through. Task 2 = `research/run_polymarket_sharp_wallet_validate.py`에 `run_score_tercile()` + 독립 BH-FDR 풀 + `main()` 리라이트. 두 태스크 모두 완전한 코드·테스트까지 계획서에 이미 작성돼있음 — 실행만 하면 됨
- percentile 공식 관련 plan-writing 단계에서 스펙 문구 하나 보정: 스펙 §3의 `.rank(pct=True)*100`은 스펙 §5의 테스트 예시("3개 anchor면 0/50/100")와 실제로 안 맞아서(pandas 기본 pct rank는 min이 0이 안 됨), plan Global Constraints에 `(rank-1)/(n-1)*100` bounded 공식으로 명시 — 스펙 재승인은 안 받음(구현 디테일 보정 수준 판단)
- 세션 종료 전 로컬 미커밋 상태(jarvis/research 로그, polymarket 수집기 첫 날짜분 데이터, 누락된 07-20 plan 문서) 전부 커밋+푸시(`e5cbf0c`) — 데스크탑/웹 세션 전환 대비, working tree clean 확인

### 변경된 파일
- `docs/superpowers/specs/2026-07-21-polymarket-sharp-wallet-scoring-design.md` (신규, 커밋 `e8ee32a`)
- `docs/superpowers/plans/2026-07-21-polymarket-sharp-wallet-scoring.md` (신규, 커밋 `2cde86a`)
- `docs/superpowers/plans/2026-07-20-polymarket-sharp-wallet.md`(원 스펙 plan, 이번에 뒤늦게 커밋됨), `research/data/polymarket_sharp_wallet/2026-07-21.jsonl`, `jarvis/_state/*`, `research/autoresearch/*` — 전부 커밋 `e5cbf0c`

### 다음 할 일
- 계획 실행: `docs/superpowers/plans/2026-07-21-polymarket-sharp-wallet-scoring.md` 열어서 Task 1부터 진행. 유저에게 Subagent-Driven vs Inline 실행방식 물어봤는데 아직 답 안 받고 데스크탑으로 전환한다고 함 — 새 세션에서 다시 물어보거나, 유저가 먼저 방식 지정하면 그걸로
- (계속 pending, 안 건드림) `cross_venue_skew_tick`: 유저가 `! kill -TERM 81256` 실행 대기중

### 막힌 부분/결정사항
- 없음(설계·계획 단계는 유저 승인 완료, 실행 방식 선택만 남음)

---

## 2026-07-21 (이어서): 샤프월렛 confidence score 계획 실행 완료 (Inline TDD)

### 완료된 작업
- 위 항목에서 남긴 실행방식 선택을 유저가 **Inline** 선택 → `docs/superpowers/plans/2026-07-21-polymarket-sharp-wallet-scoring.md` Task 1·2를 TDD 순서(테스트작성→실패확인→구현→통과→커밋) 그대로 인라인 실행
- **Task 1**(`research/hypotheses/polymarket_sharp_wallet.py`): `_percentile_rank_0_100()`(bounded `(rank-1)/(n-1)*100`) + `build_convergence_score()`(4컴포넌트 wallet_count/pnl_sum/notional/liquidity percentile 동일가중 평균, anchor<2건이면 전부 NaN) 신규, `build_labels_multi_horizon`에 `score` pass-through(anchors에 score 없으면 NaN) 추가. 테스트 5개 신규 → 16 passed(기존 11 + 신규 5). 커밋 `a730527`
- **Task 2**(`research/run_polymarket_sharp_wallet_validate.py`): `run_bucket`의 ~20줄 p-value 로직을 `_score_horizons()` 공유헬퍼로 추출(DRY), `SCORE_TERCILES`/`add_score_tercile`(qcut 3분위, 고유값<3이면 None)/`run_score_tercile`(run_bucket과 동일 shape, key만 `tercile`) 신규, `main()` 리라이트로 버킷 풀과 **완전 분리된** score-tercile BH-FDR 풀(alpha=0.1) + `=== score tercile ===` 출력 추가. 테스트 5개 신규 → 9 passed(기존 4 + 신규 5). 커밋 `1c1a49a`
- 두 타겟 테스트파일 합쳐 **25 passed**. 실 수집데이터(`2026-07-21.jsonl`)로 `python -m research.run_polymarket_sharp_wallet_validate` 실행해 end-to-end 확인 — score-tercile 섹션 정상 렌더, 버킷 풀(0/6)과 score 풀(0/9) 분리 확인(현 표본에선 양쪽 다 BH-FDR 생존자 0)
- 회귀면 확인: `polymarket_sharp_wallet` 모듈의 유일한 소비자는 validate 러너뿐(동명의 `build_labels_multi_horizon`은 cross_venue_skew/polymarket_whale의 별개 함수 — import 안 걸림). 외부 소비자 없음
- 두 커밋 `claude/polymarket-wallet-scoring-awzj6n` 브랜치로 push 완료(원격 신규 생성). PR 미생성(유저 요청 없음)

### 환경 메모(이 원격 컨테이너 한정)
- 프레시 컨테이너라 deps 부트스트랩 필요했음: `pip install -e ".[dev]"` + `openai` 등 미선언 스트래글러. 단 `nautilus_trader`가 최신 1.221.0으로 깔려 `nautilus_trader.analysis.MaxDrawdown` 제거됨 → `api_server.main` import 실패(코드베이스가 구버전 API 기대). `tests/conftest.py` autouse fixture가 매 테스트마다 `api_server.main`을 import하므로 전체 스위트가 이 버전드리프트로 막힘 — **이번 피처와 무관**
- 타겟 테스트는 순수 pandas라 `pytest --noconftest`로 해당 fixture만 우회해 검증(피처 코드 검증경계로 충분). 전체 스위트 그린 확인은 nautilus_trader 버전 핀 맞춰야 가능(별도 환경작업, 이번 범위 밖)

### 다음 할 일
- tmux 상시구동(`polymarket-sharp-wallet-tick`) + 데이터 축적 후 `run_polymarket_sharp_wallet_validate.py`로 정기 검증 — 유저 요청 시
- (원격환경) 전체 pytest 스위트 그린 원하면 `nautilus_trader` 버전을 `MaxDrawdown` 있던 구버전으로 핀 필요
- (계속 pending, 안 건드림) `cross_venue_skew_tick`: 유저가 `! kill -TERM 81256` 실행 대기중

### 막힌 부분/결정사항
- 없음

---

## 2026-07-21 (이어서): 플랫폼 방향 논의 + Phase A 착수 — 봇 정합성 불변식

### 맥락 / 결정
- 인프라 논의 끝에 **호스트 = 맥 로컬 유지**로 결정(클라우드 오라클은 물러섬, 발열은 "Claude/dev 툴 끄면 idle 서버는 조용" 판단으로 급한 불 아님, 윈도우 데스크탑은 1개월 임시라 폐기). 오라클 배포 킷(`scripts/deploy/*`, `docs/deploy/oracle-pilot.md`)은 나중 재사용 위해 레포에 파킹(커밋 `e0a9dba`).
- 플랫폼 전반 방향 합의: (1) 실매매 전까지 리서치/검증 지속, (2) 하나 골라 깊게(폴리마켓 유력), (3) **실행 레이어 하드닝**, (4) 관리 업그레이드(락파일/프로세스관리/봇불변식/CI), 폴리마켓 심화(고래·고승률 노출, 샤프월렛/괴리/whale, p-value 인플랫폼), 시각화/UX 강화(블룸버그 톤 유지). → Phase A(기반)부터 천천히.
- 논문 기능 반영 여부 확인 요청 → **이미 완비**(`research/papers/{arxiv_fetcher,extract_spec,coverage_filter,codegen_signal,smoke_check}.py` + `run_paper_ingest.py`, arxiv q-fin.PM/TR/ST/CP, 논문 3개 처리됨). 단 (a) 수동 1회성(cron 아님, `run_paper_ingest_loop.sh` 래퍼는 있음), (b) 대시보드/HUD 미노출 → "반영 안 된 느낌"의 정체.

### 완료된 작업 (Phase A ③ — 봇 정합성 불변식)
- `api_server/invariants.py` 신규 — 순수 검증 함수(매매/정산 로직 무관, 관찰 전용). 과거 조용한 회계버그류를 상태만 보고 감지:
  - `check_polymarket_bot(cfg)`: POSITION_SCHEMA(필수필드 결손=마이그레이션 버그류), SPENT_MISMATCH(`spent` != 오픈 포지션 usd 합 — 정산 시 감산설계라 이 항등식 성립), SPENT_OVER_BUDGET, SLOTS_EXCEEDED, STUCK_RESOLUTION(만기 7일↑ 지났는데 미정산=정산큐 멈춤, 07-18 버그 직격)
  - `check_agent(...)`: CYCLE_CAP_SATURATION(cycle수 100000 캡 도달=FIFO 잘림 재발위험), INVESTED_NEGATIVE, OVER_ALLOCATED
- `tests/test_invariants.py` 신규 13개 — `pytest --noconftest`로 13 passed(순수모듈이라 앱체인 무관)
- `api_server/lab_api.py`에 `GET /lab/health` 엔드포인트 신규(lazy import, `/lab/status` 패턴). 폴리마켓봇 `_load()` + 전 에이전트 `compute_performance` 돌려 위반 집계, `{ok, n_violations, n_errors, violations[]}` 반환. HUD 알람용.

### 변경된 파일
- 신규: `api_server/invariants.py`, `tests/test_invariants.py`
- 수정: `api_server/lab_api.py` (`/lab/health`)

### 다음 할 일
- **`/lab/health` 런타임 검증 미완** — 이 원격 컨테이너는 nautilus 드리프트로 `api_server.main` import 불가라 엔드포인트 실행 테스트 못 함. **맥에서 서버 띄워 `GET /lab/health` 한 번 확인 필요**(순수모듈+테스트는 검증됨, 와이어링만 미검증)
- Phase A 남은 것: 대시보드 HUD에 `/lab/health` 위반 카드 노출(프론트, 소규모) / ②launchd 자동재시작(맥) / ①락파일(맥 `pip freeze`) / ④CI(①+conftest 지연 후)
- Phase B/C는 서베이 완료(대시보드 37페이지·lightweight-charts5+d3·블룸버그 @theme 확인, 폴리마켓 엣지 전부 CLI-only·리더보드 이미 fetch만 하고 미노출) → 스펙부터

### 막힌 부분/결정사항
- 없음

---

## 2026-07-21 (이어서): Phase A ③ 완결(HUD 노출) + Phase B 고래 리더보드 노출

> 유저가 "필요할 때만 부르고 자율로 계속 진행" 위임 → 아래는 자율 진행분.

### 완료된 작업
- **Phase A ③ 완결** — 봇 불변식을 대시보드 HUD에 노출(백엔드 `/lab/health`는 이전 커밋 `4fcd521`):
  - (dashboard `d19f121`) `getLabHealth`/`LabHealth`/`HealthViolation` 타입 + HUD "정합성 감시" 패널(정상=녹색, 위반=severity별 색상 행) + 상단 스트립 "정합성 오류 N" 점멸 뱃지(감시견 패턴 재사용). tsc 클린.
- **Phase B 착수 — 고래/고승률 리더보드 노출** (서베이가 짚은 퀵윈: 샤프월렛이 이미 fetch만 하고 미노출이던 것):
  - 백엔드 `GET /polymarket/leaderboard` 신규(`api_server/polymarket_bot.py`) — `research/polymarket_sharp_wallet/leaderboard.fetch_leaderboard()` 재사용, **5분 TTL 인메모리 캐시**(폴링이 Polymarket API 안 때리게), 실패 시 마지막 캐시 반환. `time as _time` import 추가.
  - 프론트 `getPolymarketLeaderboard` + `/polymarket` 페이지에 "고래 리더보드" 패널(rank/지갑(폴리마켓 프로필 링크)/전체PnL/거래량, 5분 느슨 폴링). tsc 클린.

### 변경된 파일
- 백엔드: `api_server/polymarket_bot.py`(`/polymarket/leaderboard` + `_time`), `docs/progress.md`
- 대시보드: `lib/api.ts`, `app/hud/page.tsx`, `app/polymarket/page.tsx`

### 다음 할 일 / 미검증
- **백엔드 두 엔드포인트(`/lab/health`, `/polymarket/leaderboard`) 런타임 미검증** — 이 컨테이너는 (a) nautilus 드리프트로 `api_server.main` import 불가, (b) Polymarket 아웃바운드 403 차단이라 실행 테스트 불가. **맥에서 서버 띄워 `GET /lab/health`, `GET /polymarket/leaderboard` 한 번씩 확인 필요.** (순수모듈/타입/컴파일은 검증됨)
- ⚠️ **Phase B 카테고리 확장 건 — 전제 어긋남**: 유저는 "허용 카테고리가 적어서 정산 베팅 적다"고 했지만, 다각화 봇은 **이미 카테고리 무필터**(전 종목 거래량순, progress 07-18 기록). 실제 정산 적은 원인은 max_positions=15 / max_days_to_resolution=30 / min_liquidity=5000 필터. → "카테고리 확장"은 무의미, 대신 이 레버(포지션 수↑·만기 짧게·유동성↓)를 유저에게 확인받아야 함. **유저 결정 필요.**
- Phase A ②(launchd): 맥 전용 + tmux↔launchd 통합 설계 갈림(현 HUD restart/liveness가 tmux 기반) → 유저 접근법 결정 필요, 블라인드 진행 부적합
- Phase A ①(락파일)·④(CI): 락파일=맥 `pip freeze` 대기

---

## 2026-07-21 (이어서): 다각화 필터 완만 조정 + p-value 노출 스펙 작성

### 완료
- **다각화 봇 필터 완만 조정**(유저 "셋 다 완만하게"): `_DEFAULT` max_positions 15→20, max_days_to_resolution 30→21, min_liquidity 5000→3000 (커밋 `3a64633`). ⚠️ **실행 중 봇은 저장된 `data/polymarket_bot.json`이 이겨서 defaults 무효** — 유저가 `/polymarket` 페이지 진입필터에 같은 값(최대포지션 20 / 최소유동성$ 3000 / 최대잔여일 21) 직접 입력해야 실효. UI에 이미 필드 있음(추가작업 불필요).
- **p-value 인플랫폼 스펙 작성**(유저 "p-value부터 스펙"): `docs/superpowers/specs/2026-07-21-polymarket-edge-validation-surface-design.md`. 핵심: (1) `run_*_validate.py`에 `compute_report()->dict` 추출(계산-프린트 분리, CLI 불변), (2) `lab_api.py` 백그라운드-웜 캐시(`_task_forward` 선례) + `GET /lab/edge-validation`·`POST .../refresh`, (3) `/validation` 페이지에 sharp-wallet/whale p-value 테이블 + BH-FDR 풀 요약 섹션(생존자 0=정직한 결과 명시, "스크리닝 뿐 실집행 근거 아님" 배너 상시). arb 게이트/divergence/라이브알림은 범위 밖.

### 다음 할 일
- **p-value 스펙 유저 리뷰 대기** — 승인되면 writing-plans → 구현(스펙 §8 순서)
- 다각화 필터: 유저가 UI에서 새 값 적용
- (미검증) `/lab/health`, `/polymarket/leaderboard` 맥에서 curl 확인
- (보류, 유저 결정 대기) Phase A ② launchd 접근법(tmux 연동 vs 완전전환)
- Phase C 시각화 전면 강화 — p-value 노출 다음 스펙 후보

### 막힌 부분/결정사항
- 없음

---

## 2026-07-21 (이어서): p-value 인플랫폼 노출 — 구현 완료(Task 1~3)

> 스펙 승인 후 자율 구현. 플랜: `docs/superpowers/plans/2026-07-21-polymarket-edge-validation-surface.md`

### 완료
- **Task 1** — `compute_report(trades,dates)->dict` + `load_and_report()` 추출(sharp-wallet·whale 러너), `main()`은 report에서 프린트(CLI 불변). sharp-wallet 2풀(bucket/score_tercile), whale 1풀(whale) 유지. 신규 통계 없음(run_* 재사용). 테스트 6개 신규 → **34 passed**(`--noconftest`). 두 CLI 스모크 정상(verdict 출력). 커밋 `426daf9`
- **Task 2** — `api_server/lab_api.py`: 백그라운드-웜 캐시(`_task_forward` 선례) + `GET /lab/edge-validation`(스냅샷 즉시반환, stale>10분시 데몬스레드 워밍, 비블록) + `POST /lab/edge-validation/refresh`. py_compile OK. 커밋 `9bac5c1`
- **Task 3** — 대시보드 `/validation`에 "Polymarket 엣지 검증" 섹션: 가설별 카드(p-value 테이블 group×horizon, BH-FDR 풀별 생존자, verdict 뱃지, 표본부족 경고, "지금 다시 계산"), "스크리닝일 뿐 실집행 근거 아님" 배너 상시, 생존자 0="확인된 엣지 없음(정직한 결과)" 명시. tsc 클린. 커밋(dashboard) `ac15614`

### 변경된 파일
- 백엔드: `research/run_polymarket_{sharp_wallet,whale}_validate.py`, `tests/test_run_polymarket_{sharp_wallet,whale}_validate.py`, `api_server/lab_api.py`
- 대시보드: `lib/api.ts`, `app/validation/page.tsx`

### 다음 할 일 / 미검증 (Task 4 = 유저 맥 스모크)
- **맥에서 런타임 확인**: `curl localhost:8000/lab/edge-validation`(첫 호출 warming:true→잠시 후 reports), `/validation` 페이지 하단 섹션 렌더. (이 컨테이너는 nautilus 드리프트+Polymarket차단으로 백엔드 미기동 — Task1은 --noconftest로 완전검증, Task2 compile-only, Task3 tsc)
- 남은 Phase: C(시각화 전면 강화) 스펙 후보 / Phase A ②launchd(유저 접근법 결정 대기)·①락파일(맥 pip freeze)

### 막힌 부분/결정사항
- 없음

---

## 2026-07-21 (이어서): Phase C 시각화 — 스펙+플랜+C1 구현 완료

### 스펙·플랜
- 스펙 `docs/superpowers/specs/2026-07-21-viz-ux-upgrade-design.md`(승인): dataviz 스킬 방법론 채택, 블룸버그 톤 위에 재사용 차트 프리미티브 레이어 + 검증된 viz 램프(categorical/sequential/diverging, 상태색과 분리). categorical 5색은 `validate_palette.js` 다크 #000 전항목 PASS. 롤아웃 C1(validation viz)→C2(polymarket/performance)→C3(rest).
- 플랜 `docs/superpowers/plans/2026-07-21-viz-ux-upgrade-c1.md`(C1만).

### C1 구현 완료(전부 dashboard 레포, tsc 클린)
- **Task 1**: `globals.css @theme`에 `--color-chart-1..5`(검증 categorical) + `--color-seq-1..4`(시안, 순흑이라 dim→bright). `lib/chart-colors.ts`에 `SEQ`+`seqColor(t)` 추가(기존 CATEGORICAL/TOKEN은 안 건드림 — 기존 d3 차트용). 커밋 `80f89d6`
- **Task 2**: `components/charts/{ChartFrame,Heatmap,NullDistribution}.tsx` 신규. Heatmap=색만(셀 텍스트 없음, 대비안전)+툴팁, NullDistribution=percentile strip(실제 vs 셔플 null, 유의 tail 음영). 커밋 `d57a20a`
- **Task 3**: `/validation` 엣지검증 카드에 group×horizon p-value 히트맵(밝을수록 유의) + 테이블 percentile 컬럼→NullDistribution strip. 정확수치·BH판정은 테이블 유지(접근성). 커밋 `854f937`

### 다음 할 일 / 미검증
- **시각 스모크 맥에서**(Task 4): `/validation` 하단 엣지검증 섹션 히트맵+strip 렌더, 라벨충돌/오버플로우 눈으로. (tsc·색검증은 통과, 실제 렌더만 미확인)
- Phase C2(polymarket pnl곡선·리더보드 bar / performance equity곡선), C3(risk/agents/논문). 후속 플랜.
- (대기) Phase A ②launchd 접근법·①락파일(맥 pip freeze)

### 막힌 부분/결정사항
- 없음. (spec의 `<NullDistribution>`는 백엔드 null 분위수 없어 percentile strip 형태로 구현 — 스펙 §5에 명시된 범위대로. 완전 히스토그램은 향후 백엔드 확장 필요)

---

## 2026-07-21 (이어서): Phase C2 increment 1 — 폴리마켓 성과 곡선/막대

### 완료(전부 dashboard, tsc 클린)
- **C2 프리미티브**: `components/charts/TimeSeries.tsx`(lightweight-charts v5 래퍼, RollingChart 패턴, 크로스헤어+리사이즈) + `BarChart.tsx`(SVG 수평막대, 극성색, 툴팁/링크/보조라벨). 커밋 `5090fd7`
- **`/polymarket` 적용**: (1) 실현손익 누적 곡선 — status.log resolve 이벤트로 최근 추이, **마지막 점을 총 realized_pnl에 앵커**(로그 창 한계 정직 처리), (2) 리더보드 상위 12 PnL 막대(프로필 링크), 기존 테이블 유지. 커밋 `41a7683`

### 다음 할 일 / 미검증
- **맥 시각 스모크**: `/polymarket`에 손익 곡선 + 리더보드 막대 렌더 확인.
- C2 increment 2: `/performance`·`/pnl`·`/portfolio` equity/pnl 곡선 — 그쪽 시계열 데이터 서베이 후 착수(현 status류가 시계열 주는지 확인 필요).
- C3(risk/agents/논문), Phase A ②launchd·①락파일 여전히 대기.

### 막힌 부분/결정사항
- 없음

---

## 2026-07-21 (이어서): "전부 다" 자율 진행 — launchd + C2 pnl + 논문 파이프라인 노출

### 완료
- **맥 launchd 자동재시작 킷**(Phase A ②, 비침습): `scripts/deploy/ensure_collectors.sh`(죽은 tmux 세션만 재생성 — HUD tmux 생존체크 보존) + `launchd/com.seokminal.{collectors,api}.plist` + `docs/deploy/mac-launchd.md`. 커밋 `9c367cd`. **맥 설치·검증은 유저**(런북에 수동검증 스텝).
- **C2 inc2 `/pnl` 누적 실현손익 곡선**: 체결 원장 running-sum 파생(백엔드 무변경). `/performance`는 이미 equity 곡선 보유, `/portfolio`는 통화혼재로 막대 오해소지라 스킵, `/risk`는 시계열 없음 → 안 건드림. 커밋 `9195ca0`
- **논문→가설 파이프라인 노출**(이전 "논문 안 보임" 이슈 해소): 백엔드 `GET /lab/papers`(`ast`로 `research/hypotheses/papers/*.py` 메타 파싱 + rejected.jsonl, 실행 안 함) 신규 `api_server/lab_api.py`. ast 파싱 실파일 3건 검증. 프론트 신규 페이지 `/papers`(생성 가설 + 리젝 사유). 커밋: backend/dashboard 아래.

### 미검증/블록(유저)
- **락파일 ①**: 맥 `pip freeze`만 가능 — 내가 생성 불가. 여전히 대기.
- **다각화 필터 UI 적용**: 유저 브라우저 입력(최대포지션 20/최소유동성 3000/최대잔여일 21).
- 백엔드 신규 엔드포인트(`/lab/papers` 등) 런타임은 맥 스모크. `/papers`·`/pnl` viz tsc 통과.
- CI ④: 락파일 후.

### 막힌 부분/결정사항
- 없음

---

## 2026-07-21 (이어서): MLB 스페셜리스트 트랙 — 스펙+플랜+순수코어 구현(Task 1,2,4,5)

### 배경/설계
- @bolinger 같은 MLB 전문 수익지갑 착안 → 카테고리 특화 지갑 컨센서스 추종. 스펙 `docs/superpowers/specs/2026-07-21-polymarket-mlb-specialist-design.md`, 플랜 `.../plans/2026-07-21-polymarket-mlb-specialist.md`(승인).
- 결정: bottom-up 발굴, 3지표(PnL/승률/ROI) 변형 전부, 매일 walk-forward 재선정, 컨센서스(과반/전원 파라미터), 다변형 단일 BH-FDR, 다각화봇=베이스라인. MLB 단일(7월 성수기·매일 정산→표본 빠름). 수집+검증만·페이퍼·라이브 없음.

### 완료 (순수 로직 4모듈, 전부 `--noconftest` 테스트 통과, 26 tests)
- **Task 1** `research/mlb_specialist/market_filter.py` — `is_mlb_market`(키워드+팀명 휴리스틱, 타리그 겹침 제외)/`mlb_condition_ids`. 9 tests. (`aefe1c9`)
- **Task 2** `research/mlb_specialist/leaderboard.py` — `wallet_mlb_stats`(pnl/winrate/roi/특화도, **as_of walk-forward**=정산된 것만) + `rank_specialists`(게이트+지표별 랭크). 5 tests. (`a9495d9`)
- **Task 4** `research/hypotheses/mlb_specialist_consensus.py` — `consensus_signals`(min_present+과반/전원) + `build_labels`(정산까지 이진 payout→forward_return). 8 tests. (`92c3a9d`)
- **Task 5** `research/run_mlb_specialist_validate.py` — `enumerate_variants`(3×2×2=12) + `compute_report`(변형별 p-value→**단일 BH-FDR 풀**). 4 tests. (`41a8bf1`)

### 남은 것 (Task 3 — 데이터 플러밍, 맥 라이브 필요)
- **수집기 `research/run_mlb_specialist_collect.py`** 미작성 — Polymarket이 이 컨테이너에서 차단(403)이라 라이브 폴링 검증 불가. 글로벌 `/trades` 폴링(샤프 수집기 골격) → `mlb_condition_ids` 필터 → append + MLB 마켓 정산상태 축적.
- **`load_and_report()` walk-forward 조립** — 수집 데이터(트레이드/정산)에서 매일 스페셜리스트 선정→forward 컨센서스 신호→변형별 라벨 조립. 수집기 데이터 포맷에 결합돼 데이터 축적 후 맥에서 완성. (compute_report 코어는 준비됨)
- MLB 마켓 식별 휴리스틱은 맥에서 실제 폴리마켓 태그로 튜닝 필요.

### 막힌 부분/결정사항
- 없음. 순수 코어(알고리즘)는 완성·검증. 수집+조립은 라이브 데이터 결합이라 맥.

---

## 2026-07-21 (이어서): MLB 트랙 Task 3 수집기 + 발열 근본수정

### MLB Task 3 (수집기) 완료 — 코드 완성
- `research/run_mlb_specialist_collect.py` 신규 — 샤프/whale 골격 복제(글로벌 `/trades` 폴링, transactionHash dedup, 지수백오프). 검증된 `market_filter.mlb_condition_ids`로 MLB 체결만 필터. MLB 마켓 상태 스냅샷(`markets/{date}.jsonl` — 정산/가격)도 축적. 순수 `filter_mlb_trades`/`_map_trade` 유닛테스트 4개. **MLB 트랙 전체 30 tests 통과.**
- **맥에서 마무리(원격은 Polymarket 차단)**: (1) market_filter 휴리스틱 실태그 튜닝, (2) 체결 outcome(YES/NO) 필드명 실검증, (3) walk-forward 조립(load_and_report) 이 수집데이터로 완성, (4) tmux 상시구동+데이터 축적.
- MLB 트랙 5모듈 전부 코드 완성: market_filter/leaderboard/collect/consensus/validate. 순수 로직 전부 테스트됨, 라이브 수집+조립만 맥.

### 발열 사건 근본수정 (맥)
- 34h 99% 고아 = **런처 앱의 `uvicorn --reload` + 중복체크 없음**이 원인. 누를 때마다 새 uvicorn, reload 워커가 고아로 스핀. 81256(cross_venue_skew 고아)·70590(uvicorn 고아) 둘 다 kill.
- 런처(`Seokminal.app/Contents/MacOS/Seokminal`) 수정: **--reload 제거** + 포트 점유체크(멱등) + `--timeout-graceful-shutdown 10`. 수집기는 원래 멱등(그대로). 재발 방지 완료.

### 다음 할 일
- 맥에서 MLB 수집기 라이브 튜닝+상시구동, 데이터 축적 후 검증.
- (이월) 락파일(맥 pip freeze), 다각화 필터 UI 적용, launchd 워치독 설치(선택).

### 막힌 부분/결정사항
- 없음

---

## 2026-07-22: XAU Session Confluence 전략 Pine→Python 포팅 (Task 1–3 완료)

### 배경 / 결정
- 유저의 TradingView "XAU Session Confluence Strategy"(Pine v6, 15분봉 기준)를 플랫폼에 심으려 했으나, **Lv1 에이전트 `condition` rule은 condition_engine 지표(rsi/ma/bb/macd/cci/obv)만** 표현 가능 → 세션/아시안레인지/돌파/HTF바이어스 프리미티브가 없어 구조적으로 담을 수 없음.
- 따라서 조건 rule 대신 **BTC ICT 엔진(`run_ict_paper_engine`)처럼 별도 파이썬 엔진으로 충실 포팅**. 성공기준 = 파이썬 백테스트가 유저 TradingView 결과와 근사 일치.
- 스펙: `docs/superpowers/specs/2026-07-21-xau-session-confluence-port-design.md`. 플랜: `docs/superpowers/plans/2026-07-22-xau-session-confluence-port.md`. 설정=Pine 기본값(유저 확인: 미변경), 차트=15분봉.

### 완료된 작업 (TDD, `pytest --noconftest`, 23 tests)
- **Task 1** `research/xau_session/sessions.py` — NY tz 세션 판정(asian 19–03 자정넘김/london 02–11:30/ny 08–16), zoneinfo DST, 세션 시작/종료 엣지. 8 tests. (`sessions`)
- **Task 2** `research/xau_session/strategy.py` — 순수 사이클 상태머신: 아시안레인지 03:00 고정 → 런던돌파(사이클1회, 롱우선, cycle_range_ready 오버랩가드) → NY연속 → 엔트리(토글) → R:R(SL=반대극단, TP=entry±0.5·risk) → 필터(아시안폭 ON[1.2,100]/HTF·스탑거리·캔들강도 OFF) → 엑싯(SL+TP resting 인트라바, 동봉 SL우선; 브레이크이븐/시간청산 구현; 트레일 미구현 명시에러). sizing은 러너 위임. 10 tests.
- **Task 3** `research/run_xau_session_backtest.py` — 전략 트레이드 → equity 복리 순차 sizing(risk%3)·비용(commission 2.5/계약·slippage 2틱) → 통계(트레이드수/승률/PF/총손익). 240m HTF 리샘플(봉종료 태깅 no-lookahead). `main()`은 저장 XAU 15m 탐색. 5 tests.

### 충실도 포인트 (§4)
- 바 종가 평가(process_orders_on_close), 60m 아시안레인지는 베이스 바에서 세션중 hi/lo 추적(60m highest==15m highest라 리샘플 불요), zoneinfo DST, 사이클 상태머신 dedup/타이브레이크.

### 남은 것 (Task 4 — TV 대조, 맥 필요)
- **이 컨테이너엔 XAU 15m parquet 없음** → 순수 로직/상태머신은 합성 바로 전부 검증(23 tests). **실제 백테스트+TradingView 대조는 맥.**
- 맥 절차: (1) intraday_store에 XAU 15m 저장(`xyz:GOLD`/`PAXG`/`GC` 중), (2) `python -m research.run_xau_session_backtest` 실행, (3) 트레이드수/승률/PF/총손익을 유저 TradingView Strategy Tester와 대조. 불일치 시 원인순서: 심볼 mintick(`TICK_SIZE`)·데이터소스(TV 스팟 XAU↔HL/IB) → 세션경계/DST.
- 대조로 충실도 확인되면 (후속) 라이브 페이퍼 엔진(ICT 패턴 재사용) 승격.

### 막힌 부분/결정사항
- 없음. R:R=0.5(소익다승, 비용 민감)·데이터소스 차이는 스펙 §8에 함정으로 명시. 통계적 근사가 목표.

---

## 2026-07-22 (이어서): 맥에서 마무리할 것 — XAU/MLB 두 트랙 정리

원격 컨테이너는 Polymarket 차단 + XAU 인트라데이 데이터 없음이라 둘 다 코어 로직만 완성(테스트 그린), 라이브 결합은 맥 필요. `claude/polymarket-wallet-scoring-awzj6n` 브랜치 pull 완료, 체크리스트만 정리.

### XAU Session Confluence (`research/xau_session/`, `run_xau_session_backtest.py`)
1. `intraday_store`에 XAU 15m 저장 — `xyz:GOLD`(24/7, TV OANDA:XAUUSD 스팟에 최근사) / `PAXG` / `GC`(교차대조용) 중 확보.
2. `python -m research.run_xau_session_backtest [SYMBOL] [TICK_SIZE]` 실행.
3. 트레이드수/승률/PF/총손익을 유저 TradingView Strategy Tester 결과와 대조. 불일치 시 원인 순서: 심볼 mintick(`TICK_SIZE`) → 데이터소스 차이(TV 스팟↔HL/IB) → 세션경계/DST.
4. 충실도 확인되면 후속으로 라이브 페이퍼 엔진(ICT 패턴 재사용) 승격 검토.

### MLB 스페셜리스트 (`research/mlb_specialist/`, `run_mlb_specialist_collect.py`)
1. `market_filter.is_mlb_market` 휴리스틱을 실제 Polymarket 태그/슬러그 스키마로 튜닝(현재는 키워드+팀명 추정).
2. 체결 `outcome`(YES/NO) 필드명이 data-api 실응답과 맞는지 `_map_trade` 검증.
3. `run_mlb_specialist_collect.run_forever` tmux 상시 구동 시작 — `/trades` 5초 폴링, 10분마다 MLB 마켓 세트+정산 스냅샷 축적.
4. 데이터 축적되면 `load_and_report()` walk-forward 조립 완성(스펙 §7) — 매일 스페셜리스트 선정→컨센서스 신호→변형별 라벨. `compute_report` 코어(BH-FDR 12변형)는 이미 준비됨.

### 막힌 부분/결정사항
- 없음. 둘 다 순수 로직/상태머신은 컨테이너에서 전부 테스트 검증 완료 — 남은 건 라이브 데이터 결합뿐.

---

## 2026-07-22 (이어서 2): 맥 마무리 작업 완료 — XAU 백테스트 실행 + MLB 라이브 결합 + 대시보드 노출

### 완료된 작업
- **XAU**: `xyz:GOLD`(tick 0.01) 77트레이드→승률 76.5%/PF 1.31/순익 $4018.97, `GC`(tick 0.1) 77트레이드→승률 79.2%/PF 1.56/순익 $34199.48. TV Strategy Tester 대조는 유저 몫(TV 접근 불가) — 대조 아직 안 됨.
- **MLB market_filter 버그 수정**: 라이브 확인 결과 시즌 선물/수상 마켓(월드시리즈 우승 등)이 팀명만으로 오매칭됨. `game_start_time` 있는 것만 인정하도록 `mlb_condition_ids` 수정(경기 단위만 이 필드 보유). 테스트 갱신+추가.
- **MLB side 필드 버그 수정**: raw `/trades`의 `side`는 BUY/SELL(주문방향)이라 정산결과 비교 불가 — `outcome`("Yes"/"No")에서 `_outcome_side()`로 YES/NO 도출하도록 전체 파이프라인 수정.
- **`load_and_report()` 완성**: `research/run_mlb_specialist_validate.py`에 실데이터 로더(`_load_jsonl_dir`/`_build_resolutions`/`_build_entry_prices`/`_daily_positions`/`_trades_df`) + walk-forward 조립 구현. 신규 테스트 5개 추가, MLB 트랙 전체 36 tests 통과.
- **MLB 검증을 기존 `/lab/edge-validation` 파이프라인에 편입**: `lab_api.py`의 `_EDGE_VAL_RUNNERS`/`COLLECTOR_SESSIONS`/`processes`에 등록 — 별도 엔드포인트 안 만들고 sharp_wallet/whale과 동일 구조 재사용.
- **MLB 수집기 라이브 기동**: `tmux new-session -d -s polymarket-mlb-specialist-tick ...` 상시 구동 시작, health-check 정상 확인.
- **프론트엔드**: `lib/api.ts`에 `EdgeVariant` 타입 추가, `app/validation/page.tsx`의 `EdgeReportCard`에 `rep.variants` 분기(변형 그리드 테이블) 추가 — MLB는 group×horizon 히트맵 대신 변형별(랭킹지표×임계×N) p-value 테이블로 렌더링. `npx tsc --noEmit` 통과.

### 남은 갭
- MLB는 데이터 축적 전이라 `/validation` 페이지에서 현재 `no_data` verdict로 보일 것 — 트레이드 쌓이면 자동 계산.
- TV Strategy Tester 대조는 유저가 직접 확인 필요(수치는 위 참고).

### 막힌 부분/결정사항
- MLB는 새 페이지 대신 기존 `/validation` 재사용 결정(아키텍처 일관성, 중복 방지).

---

## 2026-07-22 (이어서 3): XAU도 /lab(정확히는 /research)에 노출

- XAU는 p-value/BH-FDR 가설검증이 아니라 단순 백테스트 통계라 `_EDGE_VAL_RUNNERS`(Polymarket 엣지 검증 전용) 대신, TSMOM이 쓰던 `/research` 라우터(`research_api.py`, 60초 캐시) 패턴 재사용 — 기존 `/research/tsmom`과 동일 구조로 `/research/xau-session` 신설.
- `research/run_xau_session_backtest.py`에 `summary(symbols, tick_sizes)` 추가 — xyz:GOLD/GC/PAXG 멀티심볼 순회, trades 리스트 제외한 통계만 반환(데이터 없는 심볼은 건너뜀, 에러 안 남).
- `api_server/research_api.py`에 `GET /research/xau-session` 추가.
- 프론트: `lib/api.ts`에 `XauSessionSummary`/`getXauSession` 추가, `app/validation/page.tsx`에 `XauSessionPanel` 신설 — TSMOM 패널 바로 아래, 심볼별 봉수/tick/트레이드수/승률/PF/순손익 테이블.
- 테스트 2개 추가(`test_xau_backtest.py`) — 데이터없음 스킵 케이스 + 통계 매핑 케이스. XAU 트랙 전체 25 tests 통과.
- `npx tsc --noEmit` 통과, 실데이터로 엔드포인트 스모크 확인(xyz:GOLD/GC/PAXG 3개 다 잡힘).
- `pytest tests/ -q` 전체: 1357 passed, 실패 11개는 전부 기존 known failures(test_auth/test_backtest_happy_path/IB주문계열, 무관).

### 남은 갭
- 없음(요청받은 XAU 노출 작업 완료). TV 대조는 여전히 유저 몫.

---

## 2026-07-22 (이어서 4): dev 서버 브라우저 실검증 — XAU/MLB 둘 다 정상

- 이미 떠있던 백엔드(:8000)/프론트(:3000) 그대로 `/validation` 페이지 브라우저로 확인(Chrome MCP).
- **XAU 패널**: TSMOM 밑에 정상 렌더링. xyz:GOLD(17트레이드/76.5%/PF1.31/net 4018.97), GC(77트레이드/79.2%/PF1.57/net 35338.82 — API 재계산 시점 데이터 갱신으로 CLI 최초값 34199.48과 소폭 차이, 버그 아님), PAXG(15트레이드/80.0%/PF1.62/net 6085.28) 3심볼 다 테이블에 뜸.
- **MLB 카드**: Polymarket 엣지검증 섹션 맨 아래 정상 위치, "데이터 대기" 배지 + "수집 데이터 대기 중 — 틱 쌓이면 자동 계산됨" 메시지 정확 — 수집기 막 켠 상태라 예상된 정상 상태.
- 기존 sharp_wallet/whale 카드 회귀 없음. 브라우저 콘솔 에러 0건.

### 남은 갭
- 없음. XAU TV 대조(유저 몫), MLB 데이터 축적(수집기 상시구동 중, 쌓이면 자동 계산)만 남음.

---

## 2026-07-22 (이어서 5): MLB 전용 `/mlb` 페이지로 분리

- 유저 요청: MLB를 `/validation`의 공용 카드 대신 별도 페이지로 분리.
- `EdgeReportCard`/`EdgeHeatmap`/`EdgeVariantTable`/`VERDICT_BADGE`를 `app/validation/page.tsx` 로컬 정의에서 `components/charts/EdgeReportCard.tsx`로 추출·export — `/validation`과 신규 `/mlb` 둘 다 재사용.
- `app/mlb/page.tsx` 신설: `mlb_specialist_consensus` 리포트만 뽑아 `EdgeReportCard`로 렌더 + 수집기 상태(ON/OFF, 마지막수집 경과시간)/재시작 버튼(`polymarket_mlb_specialist_tick`) + "지금 다시 계산" 버튼.
- `/validation`의 `EdgeValidationSection`에서 `mlb_specialist_consensus`는 목록에서 제외(중복 렌더 방지) — sharp_wallet/whale만 남음.
- `lib/api.ts`: `CollectorKey`/`LabStatus.processes`에 `polymarket_mlb_specialist_tick` 추가(백엔드는 이미 등록돼 있었음, 프론트 타입만 누락 상태였음).
- `components/Sidebar.tsx` "검증" 그룹에 `{ href: "/mlb", label: "MLB 스페셜리스트" }` 추가.
- `app/hud/page.tsx` Unit 목록에 MLB 수집기 row 추가(다른 폴리마켓 수집기들과 동일 패턴, href `/mlb`).
- `npx tsc --noEmit` 통과. 브라우저 실확인: `/mlb` 페이지 정상 렌더(수집기 ON·6시간 전, MLB_SPECIALIST_CONSENSUS 카드 "데이터 대기" 정상 상태), `/validation`에서 MLB 카드 사라지고 sharp_wallet/whale만 남은 것 확인, 상단 네비 "검증" 드롭다운에서 "MLB 스페셜리스트" 클릭→`/mlb` 정상 이동. 콘솔 에러 0건.

### 남은 갭
- 없음. XAU TV 대조(유저 몫), MLB 데이터 축적(수집기 상시구동 중)만 남음.

---

## 2026-07-22 (이어서): 플랫폼 업그레이드 6종 (엣지 메타-대시보드/함대헬스/감쇠추적/집행시임/워치독)

유저 "자는 동안 다 해줘" — MLB/골드 빼고 플랫폼 전반 업그레이드. 전부 커밋·푸시,
순수 로직은 여기서 검증(56 tests), 백엔드 런타임/프론트 렌더는 맥 확인 필요.

### ① 엣지 메타-대시보드 (백+프론트)
- `research/hypothesis_registry.py` — 전 가설 포트폴리오 단일소스(8가설, warmable 2=폴리마켓). 순수 메타.
- `api_server/lab_api.py` `GET /lab/edges` — 가설별 검증요약(FDR생존/최소p/표본/유의) + 감쇠궤적 + 포트폴리오 카운트. 기존 edge-validation 워밍을 레지스트리 기반으로 전환.
- `seokminal_dashboard/app/edges/page.tsx` — 포트폴리오 요약 타일 + 가설 테이블(p-value 바 + 감쇠 스파크라인 개선녹/감쇠적) + 함대 패널. 네비 "검증" 그룹에 추가. `getEdges`/`getFleet` + 타입.

### ② 수집기 함대 헬스 (백+프론트)
- `api_server/fleet_health.py` — 순수 신선도 판정(fresh/stale/dead, 수집기별 임계) + 함대요약. `GET /lab/fleet`이 COLLECTOR_SESSIONS 순회+`_tmux_process_status`+classify.
- 프론트 `/edges` 상단 함대 패널(verdict 칩, 30s 폴링). "하나 죽으면 엣지 조용히 썩는다" 가시화.

### ③ 엣지 감쇠(decay) 추적
- `research/edge_history.py` — 검증 리포트 관용적(재귀) 요약추출 + `research/data/edge_history/{hyp}.jsonl` 시계열 저장/로드/추세. 매 워밍마다 append → 레짐변화 조기포착. 신규 통계 없음(관찰 전용).

### ④ 시각화 (엣지 페이지에 통합)
- p-value 감쇠 인라인 SVG 스파크라인(저비용), p-value 크기 바(1-p, ≤0.05 강조). Bloomberg 테마·예약 status색 준수.

### ⑤ 집행 시임 (안전)
- `execution/broker.py` — dry-run 페이퍼 브로커(주문가 즉시체결 시뮬+가중평균 포지션/실현손익+저널, 벤뉴 API 미접촉) + `make_broker` mode 기본 paper. `mode="live"`는 등록 어댑터 없으면 NotImplementedError로 거부 — **실주문 경로 구조적 부재.** 실어댑터는 후속 register_live_adapter.

### ⑥ 운영 경화
- `ops/collector_watchdog.py` — `/lab/fleet` 폴링→dead(옵션 stale) 자동 재기동(멱등 restart 엔드포인트, launchd-tmux 결정 무관). `ops/README.md`(tmux/launchd 설치, pip freeze 락파일), `ops/com.seokminal.watchdog.plist` 템플릿.

### 테스트 (컨테이너, --noconftest)
- fleet_health 7, edge_history 7, hypothesis_registry 3, execution_broker 12, collector_watchdog 4 = **신규 33 + XAU 23 = 56 통과.** 백엔드 py_compile OK, 대시보드 tsc 클린.

### 맥 검증 체크리스트 (일어나서)
1. 두 레포 pull(같은 브랜치). uvicorn 재기동(--reload 없이).
2. `curl localhost:8000/lab/edges` → 폴리마켓 2종 요약 뜨는지(warming→잠시후 reports), 나머지 6종 status=pending.
3. `curl localhost:8000/lab/fleet` → 수집기별 verdict. dead/stale 있으면 워치독 붙이기(ops/README).
4. 대시보드 `/edges` 렌더 — 포트폴리오 타일/함대칩/테이블/스파크라인 눈으로.
5. (선택) 워치독 tmux/launchd 상시화, 맥 `pip freeze > requirements.lock`.

### 막힌 부분/결정사항
- 없음. ⑤ 실집행은 의도적으로 페이퍼만(자는 동안 실주문 방지). 엣지 확정 후 실어댑터 별도 태스크.

### 후속 반영 (병합 시)
- `mlb_specialist_consensus`는 위 6종 커밋에서 `warmable: False`(맥 조립 전 가정)로 등록됐으나, 실제로는 (이어서 2~5) 세션에서 `load_and_report()` 완성+수집기 라이브 기동까지 끝난 상태라 병합하며 `warmable: True`로 승격.

---

## 2026-07-22 (이어서 6): 두 저장소 commit→pull(merge)→push 동기화, 세션 마무리

- 유저 요청: 데스크탑에서 넘어온 미동기화 작업 있는지 확인 후 커밋·풀·푸시로 맞추기.
- 양쪽 레포(`seokminal-dashboard`, `seokminal-multi-venue`) 모두 `git fetch` + `git log HEAD..origin/<branch>`로 미풀 커밋 확인 → 실제로 데스크탑발 "플랫폼 업그레이드 6종"(엣지 메타-대시보드/함대헬스/감쇠추적/집행시임/워치독, 위 섹션) + 대시보드 `/edges` 페이지가 origin에만 있고 안 풀려있었음(유저 우려 적중).
- `git pull --no-rebase origin <branch>`로 병합(git config 변경 없이 플래그로만 처리 — "git config 절대 변경 금지" 규칙 준수).
- **충돌 2건 해결**:
  - `seokminal-dashboard/components/Sidebar.tsx`: 내 `/mlb` 링크 추가 vs origin `/edges` 링크 추가, 같은 배열 위치 — 둘 다 유지(`/validation`→`/edges`→`/mlb` 순).
  - `seokminal-multi-venue/api_server/lab_api.py`: 내 구버전 flat `_EDGE_VAL_RUNNERS` dict vs origin의 신규 `research/hypothesis_registry.py` 기반 `_edge_val_runners()`. **origin 채택**(아키텍처 상위호환, MLB도 이미 레지스트리에 등록돼 있었음) — 단, `mlb_specialist_consensus`의 `warmable` 플래그는 `research/hypothesis_registry.py`에서 별도로 `True`로 승격(위 "후속 반영" 참조 — 레지스트리 자체의 병합은 충돌 없었음, 이건 병합 후 판단 결정).
  - `docs/progress.md` 하단 append 충돌 — 양쪽 섹션 순서대로 이어붙임.
- 승격 판단으로 깨진 테스트 수정: `tests/test_hypothesis_registry.py`의 `test_warmable_runners_are_polymarket_two`(warmable=정확히 폴리마켓 2종이라 가정)가 MLB 승격으로 거짓이 됨 → 어서션/이름 갱신(`test_warmable_runners_include_mlb_now_promoted`), `test_registry_list_warmable_first`도 3종 기준으로 수정. 해당 테스트 파일 재실행 12 passed.
- 병합 후 라이브 스모크: `curl localhost:8000/lab/edges` (이미 `--reload`로 떠있던 서버) → `mlb_specialist_consensus`가 `warmable: true`+감쇠궤적 항목 정상 반영 확인.
- 최종 push 완료. 커밋 해시: `seokminal-dashboard` 병합커밋 `ff88fc2`(`774b250` MLB분리 + `fb9f30d` desktop edges 병합), `seokminal-multi-venue` 병합커밋 `adc93e9`(`81494ed` XAU/MLB작업 + `4be6a7a` state스냅샷 + desktop `85e2555`/`b2b3fdf`/`9e362b6`/`9f43c55` 병합).

### 남은 갭
- 없음. 두 레포 모두 동일 브랜치(`claude/polymarket-wallet-scoring-awzj6n`)에서 commit/merge/push 완료, 충돌 마커 0건, 관련 테스트 통과.

### 다음 세션 확인
- 위 "맥 검증 체크리스트"(엣지 메타-대시보드/함대헬스) 항목들은 이번 세션 중 이미 일부 확인됨(`/lab/edges` curl 스모크). `/edges` 프론트 페이지 브라우저 렌더는 아직 미확인 — 다음 세션에서 확인 권장.
- MLB 데이터는 여전히 축적 대기(수집기 상시구동 중, 표본 쌓이면 자동 계산).

---

## 2026-07-30: Investment OS 자문전용(is_advisory/is_decision) 불변식 재점검 + jarvis 테스트 스윕 + CPU 발열 원인 제거

- 세션 앞부분(컨텍스트 컴팩션으로 세부 로그 유실)에서 Portfolio OS 계열(`prediction_registry.py`/`portfolio_construction.py`/`signal_overlay.py`/대시보드 `allocation/page.tsx`) 대상으로 "제안 전용·실행 없음" 불변식 재점검 라운드 진행 중이었음. 컴팩션 이후 재개해서 확인한 것만 기록:
  - **`jarvis/research_workflow/prediction_registry.py`**: `_snapshot_hash()`가 해싱하는 `core` dict가 `immutable_fields`로 선언한 5개 필드(`evaluation_framework`/`success_rule`/`thresholds`/`thesis`/`invalidation_condition`)를 정확히 커버 — 선언과 실제 해시 대상 불일치 없음. 사후 변조 검증용 `verify_snapshot_hash()` 같은 함수는 없지만, 저장처가 `rmi_` append-only 원장이라 별도 검증 없이도 위조 경로 자체가 없음 — 문제 없다고 판단.
  - jarvis 테스트 스윕 2건 모두 그린: `pytest tests/ -k jarvis` 276 passed / `pytest tests/`(전체) 15036 passed, 0 failed, 150초. CLAUDE.md에 명시된 기존 known-failure(test_auth×3~4, test_backtest_happy_path)는 이번 러너 스코프에서 안 걸림(별도 subset이라 무관).
- **CPU 발열 원인 진단 및 제거** (`seokminal-dashboard` 쪽 문제, 백엔드 `--reload` 아님 — 그건 이미 안 켜져 있었음 확인함): `ps -Ao pcpu` 로 프로세스 스캔 → `seokminal-dashboard`의 vitest fork worker(`node .../vitest/dist/workers/forks.js`, pid 78025)가 CPU 100% 고정으로 9시간12분째 돌아가고 있던 게 원인. 오래된 `npm test` watch 모드 세션이 안 닫히고 방치된 것으로 추정. `kill`로 종료, 프로세스 소멸 확인. (참고로 `research.run_cross_venue_skew_collect` 파이썬 프로세스도 24.9% CPU로 5일+ 계속 도는 중인데, 이건 의도된 상시 수집기로 보여 안 건드림 — 다음 세션에서 이 트랙이 뭔지 확인 필요, 메모리에 기록 없음.)

### 다음 세션 확인
- `run_cross_venue_skew_collect` — 정체 불명 장기 실행 수집기(5일+, PPID 83664). 의도된 것인지, 좀비인지 다음 세션에서 확인.
- Portfolio OS 불변식 점검 라운드 ①②는 컴팩션으로 세부 내용 유실 — 필요하면 재확인.
- `docs/progress.md`(양쪽 레포 다) 파일 크기 커짐(dashboard 쪽 3800줄/326KB) — 당장 문제는 아니지만 다음에 오래된 Phase 아카이빙 고려.

---

## 2026-07-30 (이어서): 디스크 정리 + 함대 헬스 모니터링 업그레이드(stuck tier/flapping/디스크 경보)

### 완료된 작업
- **디스크 정리**: `research/compress_old_data.py`로 `cross_venue_skew`(89개) + `polymarket_tick`(19개) 오래된 `.jsonl`→`.jsonl.gz` 압축. 디스크 여유 38GB→81.6GB로 회복.
- **`collector-watchdog` tmux 로그 점검 중 실사고 발견**: `polymarket_event_divergence`가 stale 상태로 **9.7시간** 방치돼 있었음(마지막 write 07-29 13:21). 원인: `stale`은 워치독이 기본적으로 손 안 대는 상태(`--restart-stale` 꺼짐)라 아무 데도 안 걸리고, `/lab/fleet`을 수동으로 안 보면 무기한 방치됨. 같은 로그에서 `polymarket_arb`/`polymarket_updown_arb`가 하루에 6번씩(1~2h 간격) 죽었다 재기동되는 flapping 패턴도 발견 — 지금까지 카운트되는 곳이 없어서 "워치독이 알아서 처리 중"으로 안 보였을 뿐 근본원인 미해결 상태.
- **`api_server/fleet_health.py`**: verdict에 `stuck` 티어 추가(`age > stale_after_s × STUCK_MULTIPLIER(4)` — stale 방치를 dead/stale과 별도로 눈에 띄게). `classify()`에 `restart_count_24h`/`flapping`(≥`FLAPPING_THRESHOLD`=3) 필드 추가. `classify_disk()`(ok/warn<20GB/critical<8GB) + `count_restarts_by_key()` 신규.
- **`api_server/lab_api.py`**: `/collectors/{key}/restart` 호출마다 `research/data/_ops/restart_log.jsonl`에 append(`_log_restart`, HUD 수동 클릭·워치독 자동 재기동 공통 계측점). `/lab/fleet` 응답에 `disk` 필드(`shutil.disk_usage`) + 각 collector row에 24h 재기동 카운트 반영.
- **`ops/collector_watchdog.py`**: `stuck`/`flapping`/디스크 warn·critical은 `restart_stale` 옵션과 무관하게 항상 로그(stuck은 `logging.error`) — 9시간 방치 재발 방지가 목적이라 재기동 여부와 로그 노출을 분리. `to_restart()`는 `restart_stale=True`일 때 `stuck`도 `stale`과 함께 재기동 대상에 포함.
- **프론트 `/edges`**: `lib/api.ts`(`FleetCollector`/`FleetResponse`에 `stuck`/`restart_count_24h`/`flapping`/`disk` 반영), `app/edges/page.tsx`(디스크 여유공간 칩, flapping 뱃지 `재기동×N`, `stuck` 별도 색조 — 토큰 재사용만, 새 컬러 없음).
- **테스트**: `tests/test_fleet_health.py` 신규 8건(stuck 분류/랭킹/flapping/디스크 tier/재기동 카운트), `tests/test_collector_watchdog.py` 신규 2건(stuck 재기동 정책). 백엔드 전체 1993 passed(기존 known-failure 4건 + 이번 세션 무관 환경성 실패 1건(`test_orderflow_ib_adapter` IB_PORT 환경변수 불일치) 그대로). 대시보드 `tsc --noEmit` 클린.
- **실제 조치**: 위에서 발견한 `polymarket_event_divergence`를 새 `stuck` verdict로 재확인 후 `/lab/collectors/polymarket_event_divergence/restart` 호출로 직접 재기동(tmux pane에 python 프로세스 정상 기동 확인, 크래시 로그 없음).

### 변경된 파일
- `seokminal-multi-venue/api_server/fleet_health.py`, `api_server/lab_api.py`, `ops/collector_watchdog.py`
- `seokminal-multi-venue/tests/test_fleet_health.py`, `tests/test_collector_watchdog.py`
- `seokminal-dashboard/lib/api.ts`, `app/edges/page.tsx`

### 다음 세션 확인
- `polymarket_event_divergence` 재기동 후 실제로 다시 write 시작하는지(다음 세션에서 `/lab/fleet` age_sec 확인) — 재기동만 했고 근본원인(왜 9시간 멈췄는지)은 조사 안 함.
- `polymarket_arb`/`polymarket_updown_arb` flapping(하루 6회+ 재기동) 근본원인 미조사 — 이제 `restart_count_24h`/`flapping` 필드로 눈에는 띄니 다음에 왜 자꾸 죽는지 확인 권장(재기동이 kill-then-spawn이라 죽을 때 stderr가 안 남는 것도 갭 — 필요해지면 재기동 시 이전 pane 로그를 파일로 떠두는 것도 고려).
- `--restart-stale`/새 `stuck` 자동재기동은 여전히 기본 꺼짐(README 권장 유지) — 워치독은 로그만, 사람이 보고 판단하는 흐름 그대로.

### 막힌 부분/결정사항
- 없음. flapping/stuck을 기존 bot 전용 alert rule 엔진(`api_server/main.py` `_ALERT_CONDITION_TYPES`)에 끼워넣지 않고 `/lab/fleet`+워치독 로그로만 노출하기로 결정 — 그 엔진은 `bot_id` 기반 스키마라 수집기엔 안 맞고, 억지로 넣으면 과설계.

### 추가: 발열 재발방지 — `ops/dev_process_watchdog.py` 신규
- 유저가 재기동 직후 CPU 발열 체감("지금 왜뜨거워?") → 원인 진단: (1) uvicorn(방금 재기동)이 `main.py` 스타트업 훅의 `research.lab.service.SERVICE.start()`로 parquet 카탈로그 읽는 중이었음(정상, 몇 분 내 자연 idle 확인됨), (2) 세션 중 직접 돌린 `npm test`(`vitest run`, 1회성)가 오래 걸리는 중.
- 유저 후속 요청("이거 발열 안나게 플랫폼 운영 처리 안되나") → 진짜 반복 위험은 `vitest`를 watch모드(인자 없이)로 켜놓고 방치하는 경우(`package.json`의 `test`는 이미 `vitest run`으로 고정돼 안전, 문제는 터미널에서 직접 `vitest` 치는 경우) — 09-30(이날 앞부분) 9시간+ 방치 사건과 같은 계열.
- `collector_watchdog.py`와 동일 모양(순수 `classify_processes`/`parse_etime` + 얇은 IO `run_once`/`run_forever`)으로 `ops/dev_process_watchdog.py` 작성: vitest worker 프로세스 패턴만 명시 매칭, 30분 넘게 살아있으면 SIGTERM. uvicorn/수집기/next dev는 패턴에 안 걸려 안전. `tests/test_dev_process_watchdog.py` 9건(테스트 카운트 갱신: 총 2002 passed). `ops/README.md`에 섹션 추가, tmux `dev-process-watchdog` 세션으로 상시가동 시작함(5분 간격).

### 다음 세션 확인 (추가)
- `dev-process-watchdog` tmux 세션이 실제로 몇 사이클 돌면서 오탐(정상 프로세스 잘못 kill) 없는지 확인.

### 추가: vitest run(1회성) 자체가 완료 후 안 죽는 문제 확인
- 유저 요청("지금 바로 죽이고 원인 봐줘")로 돌던 `npm test` 프로세스 `TaskStop`으로 정리 후, `vitest run --reporter=verbose` 재현 시도(perl alarm 60s로 강제종료 — macOS에 `timeout` 없음).
- verbose 로그 확인: 27개 테스트 파일 전부 개별 테스트 통과(✓) — 즉 테스트 로직 자체는 정상 완료. 그런데도 프로세스가 60s 넘게 안 죽음.
- `npx` wrapper만 alarm에 죽고 실제 vitest(forks worker)는 PID 1로 reparent된 채 CPU 98.9%로 계속 살아있던 걸 뒤늦게 발견 → `kill -9`로 직접 정리 완료(확인됨, 잔여 프로세스 없음).
- **결론**: 특정 테스트 코드 버그 아님(전부 통과), 앱 코드의 미정리 setInterval/WebSocket도 아님(`lib/`·`app/`·`components/`·`hooks/` 전수 grep — interval 있는 컴포넌트는 전부 useEffect cleanup 있고, 애초에 테스트가 마운트 안 하는 페이지 컴포넌트들). vitest 4.1.9 자체(또는 forks pool)가 run 모드 완료 후 프로세스를 안 놓는 걸로 보이는 환경/툴링성 이슈로 잠정 결론 — 더 깊게(디펜던시 단위 bisect) 파고들 실익 낮다고 판단해 중단(`dev_process_watchdog.py`가 어차피 30분 넘으면 blanket으로 죽여줌).
- **막힌 부분**: vitest 프로세스가 정확히 왜 안 죽는지(어느 open handle인지)는 미확정. 재발하면 `node --trace-warnings` 또는 vitest `pool: "forks"` → `"threads"` 전환 테스트로 좁혀볼 것.

## 2026-07-30 (이어서 2): 오더북 히스토리 저장(Bookmap식 DOM 리플레이) 백엔드

유저 지시("용량 안 잡아먹게 만들어줘, 플랫폼화 가능여부도 알려줘")의 백엔드 절반. 프론트 절반+상세는 `seokminal-dashboard/docs/progress.md` Phase 188 참조.

### 완료된 작업
- `research/run_hl_orderflow_tick_collect.py`(기존 상시가동 `hl-orderflow-tick` tmux 수집기 확장, 신규 수집기 안 만듦): `snapshot_append_fn` 주입 추가. `SNAPSHOT_THROTTLE_SEC=3.0`(이벤트 자체 ts 기준 스로틀, wall-clock 아님 — 테스트 결정론성 위해), `SNAPSHOT_LEVELS=15`, `[price,size]` 압축 배열 인코딩. `research/data/hl_orderbook_snapshot/{coin}_{date}.jsonl`에 append. 기존 `compress_old_data.py`가 파일명 패턴 기반 rglob이라 코드 변경 없이 자동 gzip 대상됨. 예상 용량 ~10MB/일(3코인).
- `api_server/router_orderflow.py`: `GET /orderflow/history/{symbol}/dates`, `GET /orderflow/history/{symbol}?date=&start=&end=&limit=`(plain/gzip 듀얼 리더, `_HISTORY_SNAPSHOT_MAX_LIMIT=20000` 캡).
- 테스트: `test_run_hl_orderflow_tick_collect.py` 14 passed, `test_router_orderflow.py` 14 passed(신규분 포함). 전체 pytest 재실행 `2022 passed`(pre-existing 실패 없음, 기존 기록과 일치).
- `hl-orderflow-tick` tmux 세션 kill 후 `ensure_collectors.sh`로 재기동(신규 코드는 프로세스 재시작 없이는 반영 안 됨) — 재기동 15초 만에 `research/data/hl_orderbook_snapshot/{BTC,ETH,PAXG}_2026-07-30.jsonl` 실제 기록 확인.

### 변경된 파일
- `research/run_hl_orderflow_tick_collect.py`, `tests/test_run_hl_orderflow_tick_collect.py`
- `api_server/router_orderflow.py`, `tests/test_router_orderflow.py`

### 다음 세션 확인
- `research/data/hl_orderbook_snapshot/` 용량이 며칠 뒤 예상(~10MB/일)대로 가는지 확인 — 벗어나면 `SNAPSHOT_THROTTLE_SEC`/`SNAPSHOT_LEVELS` 재조정.
- `ensure_collectors.sh`/`lab_api.py`는 무변경(기존 `hl-orderflow-tick` 세션명 그대로 재사용) — 별도 등록 작업 불필요, 확인 완료.

## 2026-07-30 (이어서 3): 오더플로우 페이지 발열 — heatmap_delta 백엔드 스로틀 누락

유저 리포트("오더플로우 키면 발열 심해지는데") systematic-debugging으로 조사. 1차(프론트 useMemo) 픽스는 유저가 "여전히 뜨겁다"로 반려 → 백엔드 WS 직접 측정으로 재조사(프론트 상세는 `seokminal-dashboard/docs/progress.md` Phase 189 참조).

### 완료된 작업
- `websockets` 클라이언트로 `/ws/orderflow/BTC.HL` 직접 붙어 메시지 타입별 실측: `heatmap_delta` 61.5/sec — book_snapshot(1.5/sec, 스로틀 정상)과 달리 스로틀이 안 걸려있는 게 실제 원인으로 확인.
- `orderflow/manager.py`: `_SymbolWorker.pending_heatmap` dict 추가 — `aggregator.on_book_snapshot()`은 매 틱 그대로 호출(스푸핑 감시 등 내부 상태 유지 위해 필수)하되, 반환된 heatmap_delta는 `BOOK_SNAPSHOT_THROTTLE_SEC`(0.15s) 창 안에서 키(ts,price)별 최신값만 모았다가 flush하도록 변경. book_snapshot과 같은 창/타임스탬프 재사용.
- `tests/test_orderflow_manager.py`: 신규 테스트 2건 작성 중 tick_size=10(BTC.HL) 라운딩으로 bid(100.0)/ask(101.0)가 같은 heatmap 버킷(100.0)에 충돌해 pending_heatmap 값이 서로 덮어쓰는 테스트 픽스처 버그 발견 — ask 가격을 200.0으로 분리해 수정. 전체 pytest 2024 passed(pre-existing 실패 없음).
- 재기동 후 재측정: heatmap_delta 61.5→48.1/sec로 감소했으나 완전 해소는 아님 — 같은 150ms 창 안에서도 여러 개별 가격 레벨이 실제로 바뀌는 게 정상 시장 데이터라 메시지 수 자체가 크게 안 줆(스로틀은 "같은 키 중복"만 제거, distinct 레벨 fan-out은 못 줄임). 더 지배적인 원인은 프론트 쪽 메시지당 O(n) Map 카피로 확인됨(Phase 189 참조) — 그쪽도 같이 수정함.
- `bash scripts/restart_api.sh`로 uvicorn 재기동 완료(PID 42613, `--reload` 없음).

### 변경된 파일
- `orderflow/manager.py`, `tests/test_orderflow_manager.py`

### 다음 세션 확인
- 유저가 실제 발열 해소 확인했는지 — 아직 미확인. 안 되면 systematic-debugging Phase 4.5(픽스 2회 시도 후 아키텍처 재검토) 단계로 넘어갈 것.
