# BTC.HL ICT+오더플로우 페이퍼 트레이딩 엔진 — Design Spec

**작성:** 2026-07-20. 유저가 처음엔 "합쳐서 자동매매"를 요청했으나, 이 조합
(ICT+오더플로우)이 아직 0/30 표본 미검증 상태이고 프로젝트 자체의 집행
안전장치(`jarvis/execution/*`, `jarvis/risk/governor.py`)가 AI의 집행권한
자기확장을 막도록 설계돼 있다는 점을 근거로 실거래 자동화는 거절, **페이퍼
트레이딩으로 스코프 확정**. 목적은 저널을 사람이 한 줄씩 채우는 대신, 조건
충족 시 로봇이 24시간 감시하다 자동으로 페이퍼 진입/청산하고 저널에 스스로
기록하게 하는 것.

## 1. 배경

`docs/orderflow-journal.csv`(0/30 표본)를 채우려면 사람이 계속 화면을
보고 있어야 하는데 비현실적. ICT 구조적 신호(CISD/iFVG/Order Block —
`research/ict/primitives.py`에 이미 구현됨)와 라이브 오더플로우 반전
트리거를 결합해 "어디서·언제 진입할지"를 자동 판단하고, 페이퍼로만
체결·기록한다.

**중요:** `research/agents/experiment_registry.jsonl`의 `ict_cisd_final`/
`ict_ifvg_final`은 미국 주식 15분봉·오더플로우 없는 단일 프리미티브 조합을
BH-FDR로 검증해 REJECT된 기록이다. 이번 트랙은 자산(BTC.HL)·타임프레임
(멀티)·조합(오더플로우 컨플루언스 추가)이 전부 달라 별개 가설이며, 애초에
백테스트가 불가능(과거 L2 뎁스 데이터 미보유)해 BH-FDR이 아니라 저널
30건 누적 후 평균 R(기대값) 판단으로 검증한다 — 승률 아님.

## 2. 신호 로직

### 2.1 프리미티브 선택
CISD, iFVG, Order Block만 사용(`research/ict/primitives.py` 재사용).

### 2.2 오더플로우 트리거 — 역할 분리 AND (안1)
기존 저널 템플릿의 8개 트리거를 3역할로 나눴던 것 중, v1은 **게이팅
트리거만 자동화 대상**으로 좁힌다:

- **반전형(게이팅, 필수 자동화)**: 흡수·스탑런·다이버전스 — CISD 옆에서
  하나라도 뜨면 진입 확정
- **레벨근거**: v1에서 자동화 스킵. HTF OB/iFVG 존 자체가 이미
  "왜 이 레벨이냐"의 답이라 저널의 `level_basis` 필드는 존 타입(OB/iFVG)을
  그대로 기록
- **방향확신 태그(임밸런스/대량체결)**: v1 스킵, `note`에 나중에 필요하면
  수동/v2로 추가

### 2.3 멀티 타임프레임
- **HTF(15분봉, HL candleSnapshot REST 폴링)**: OB/iFVG 존 감지 — "어디"
- **LTF(1분봉, 기존 60초 footprint 버킷 재사용)**: CISD 타이밍 + 반전형
  오더플로우 트리거 컨플루언스 — "언제"

**컨플루언스 윈도우**: 존 안에서 CISD와 반전형 트리거가 서로 5분(LTF 5개
바) 이내에 함께 뜨면 컨플루언스로 인정. 임의 기본값 — 30건 채운 뒤 튜닝
검토 대상(코드에 상수로 분리, 하드코딩 안 함).

### 2.4 진입/청산 규칙
- **진입**: 가격이 유효 HTF 존(OB/iFVG) 안에 있고, LTF에서 CISD + 반전형
  트리거가 컨플루언스 윈도우 내 함께 발생 → 즉시 페이퍼 진입
- **스탑**: 존 반대쪽 끝(구조적 무효화 지점)
- **목표**: 고정 R배수 아님 — HTF 스윙(`primitives.swings()`)에서 진입가
  기준 다음 반대편 유동성 레벨(불리시면 진입가 위 최근접 swing high,
  베어리시면 진입가 아래 최근접 swing low)을 목표로 삼는다. 아직 그런
  스윙이 안 잡혀 있으면 목표를 정할 수 없으므로 그 진입은 건너뛴다
- **존 무효화**: 진입 전 가격이 존 반대쪽으로 종가 기준 이탈하면 그 존
  폐기, 재감시 대기

## 3. 상태머신

단일 포지션만 추적(겹치면 저널 채점이 꼬임):

- **FLAT**: 15분봉 마감마다 존 갱신. 가격이 유효 존 진입하면 감시 모드 —
  LTF에서 CISD+반전트리거 컨플루언스 확인 → 조건 충족 시 IN_POSITION 전환
- **IN_POSITION**: 매 틱마다 스탑/목표 터치 체크 → 터치 시 청산, `result_r`
  계산, 저널 CSV에 한 줄 append, FLAT 복귀

## 4. 아키텍처

```
research/ict/paper/htf_zones.py        ← HL candleSnapshot(15m) 폴링,
                                           order_block+ifvg로 존 추적/무효화
research/ict/paper/reversal_triggers.py ← 흡수(orderflow_absorption.py 활성화)
                                           +스탑런+다이버전스 라이브 포팅
                                           (lib/orderflow-data.ts 임계값 이식)
research/ict/paper/ltf_signal.py        ← 1분봉 CISD + reversal_triggers
                                           컨플루언스 판정
research/ict/paper/state_machine.py     ← FLAT/IN_POSITION, 진입/청산, 2R
research/ict/paper/journal_writer.py    ← 완료 트레이드 1행 CSV append
research/ict/paper/position_state.py    ← 크래시 복구용 오픈포지션 상태파일
research/run_ict_paper_engine.py        ← 진입점, tmux 상시구동
```

### 데이터 흐름

```
기존 WS 어댑터(orderflow/*_adapter.py, 이미 라이브)
  → aggregator(footprint 60초 버킷)
  → reversal_triggers: 매 버킷마다 흡수/스탑런/다이버전스 판정
  → htf_zones: 15분봉 마감마다 존 갱신(REST 폴링)
  → state_machine: 존 + LTF 시그널 + 실시간가 소비
      FLAT: 컨플루언스 충족 시 진입, position_state.py에 오픈포지션 기록
      IN_POSITION: 스탑/목표 터치 시 청산
  → journal_writer: 청산 완료 시 docs/orderflow-journal.csv(프론트 repo)에
                     한 행 append(진입+청산 정보 한번에)
```

저널 파일은 프론트엔드 repo(`seokminal-dashboard/docs/orderflow-journal.csv`)에
있으므로 `journal_writer.py`는 절대경로 설정(config)으로 크로스-repo 경로를
받는다.

## 5. 에러 처리

- WS 재연결: 기존 어댑터 재연결 로직 그대로 재사용(신규 로직 없음)
- REST 폴링(HL candleSnapshot) 실패: 로그+백오프 재시도, 프로세스는 안 죽음
  — 그 사이클만 존 갱신 스킵, 기존 존 유지
- **크래시 복구**: IN_POSITION 중 프로세스가 죽으면 진행 중인 페이퍼
  포지션을 통째로 잃는다 — `position_state.py`가 진입 시점에 진입가/스탑/
  목표/존 정보를 작은 json 상태파일에 기록, 재시작 시 이 파일이 있으면
  IN_POSITION 상태로 복원 후 감시 재개. 청산 완료(저널 append) 시 상태파일
  삭제

## 6. 테스트 계획

- `reversal_triggers.py`: 합성 버킷 시퀀스로 흡수/스탑런/다이버전스 각각
  발동/비발동 케이스 유닛테스트(`orderflow_absorption.py` 기존 테스트
  패턴 재사용)
- `htf_zones.py`: 합성 15분봉으로 OB/iFVG 존 생성·무효화 유닛테스트
- `state_machine.py`: 스크립트 가격경로로 FLAT→진입→스탑청산,
  FLAT→진입→목표청산 두 경로 검증 + 저널 append 호출 검증
- `position_state.py`: 상태파일 저장 후 재로드 시 IN_POSITION 정확 복원되는
  크래시 복구 시나리오 1개
- 라이브 WS/REST 호출은 테스트에서 하지 않음(기존 `test_orderflow_binance_adapter.py`
  FakeConnect 패턴 그대로 재사용)

## 7. Out of scope

- 레벨근거(아이스버그/gex벽/유동성클러스터)·방향확신(임밸런스/대량체결)
  트리거의 자동화 포팅 — v2 후보, 30건 결과 보고 필요성 재판단
- 실거래/자동집행 — 페이퍼 전용. 라이브 전환은 이번 스펙 범위 밖이며,
  기존 `jarvis/execution/*` 안전게이트를 반드시 통과해야 함(별도 요청 필요)
- 컨플루언스 윈도우(5분) 등 상수 튜닝 — 30건 미만 상태에서 튜닝 금지
  (다른 트랙들과 동일 원칙: 표본 쌓기 전 튜닝 안 함)
- 프론트엔드 UI(라이브 포지션 패널 등) — 이번 스펙은 백엔드 엔진+저널
  기록까지만. 필요해지면 별도 스펙
