"""가설 스펙 + SEED 큐 (자체생각의 재료).

data_mode:
  real_event     — 실 KRX/DART 이벤트 family. LAB 라이브 루프가 event_study+레드팀으로 검증.
  real_registry  — 이미 검증된 실험 리플레이(진짜 evidence). precomputed_id로 registry 조회.
  blocked        — 데이터 게이트. audit이 BLOCKED_BY_DATA 반환(파이프 미구축).
  synthetic_demo — LAB 라이브 루프 아님. jarvis 배치 파이프라인(BH-FDR 데모/테스트)이
                   _demo_specs로 소비하는 합성 스펙(edge_bps/seed로 시계열 심음).

LAB 루프 시드(_seed) = real_event_queue() + blocked만. 합성은 시드되지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Hypothesis:
    id: str
    name: str
    family: str          # event | trend | factor | carry
    market: str          # KR | US | CRYPTO | FUTURES
    thesis: str          # 왜 엣지가 있을 수 있나
    kill: str            # 무엇이 이 가설을 죽이나(사전 정의)
    entry: str
    hold: str
    universe: str
    cost_bps: float
    data_mode: str
    precomputed_id: str | None = None
    n_trades: int = 0
    holding: list[int] = field(default_factory=list)
    edge_bps: float = 0.0     # jarvis 배치 데모용 합성 드리프트(bps). 0=순수노이즈.
    seed: int = 0

    def public(self) -> dict:
        d = asdict(self)
        # 합성 파라미터는 UI에 노출 불필요
        for k in ("edge_bps", "seed"):
            d.pop(k, None)
        return d


# 사전등록 큐. CB/BW(사용자 아이디어) 포함 — 해소는 데이터 게이트에 실제로 막힘.
SEED_QUEUE: list[Hypothesis] = [
    Hypothesis(
        id="cb_bw_overhang_release_v1",
        name="KR CB/BW 오버행 해소",
        family="event", market="KR",
        thesis="희석 오버행(전환사채/BW)이 상환·소각·전환완료로 해소되면 매도압력 제거 → buyback과 같은 공급 이벤트 family. 반등 가능.",
        kill="해소 이벤트를 원발행 회차와 linkage 불가 + 미상환 잔액 재구성 불가 → BLOCKED_BY_DATA.",
        entry="해소 공시 익일 시가", hold="20d / 60d", universe="KR 소중형(PIT survivorship-free)",
        cost_bps=50.0, data_mode="blocked",
    ),
    Hypothesis(
        id="cb_bw_issuance_negdrift_v1",
        name="KR CB/BW 발행 음의드리프트",
        family="event", market="KR",
        thesis="CB/BW 발행결정 = 희석/리픽싱 악재. 발행 익일부터 음의 드리프트(회피 연구, 억지 숏 아님).",
        kill="발행 후 드리프트가 random과 구분 안 되면 REJECT.",
        entry="발행공시 익일 시가", hold="20d", universe="KR 전체(DART cvbdIsDecsn)",
        cost_bps=50.0, data_mode="synthetic_demo",
        n_trades=40, holding=[20], edge_bps=-45.0, seed=101,
    ),
    Hypothesis(
        id="kr_earnings_surprise_pead_v1",
        name="KR 실적 서프라이즈 PEAD",
        family="event", market="KR",
        thesis="어닝 서프라이즈 후 사후표류(PEAD). 발표 익일 진입.",
        kill="비용 후 net 음수 or random 미달.",
        entry="실적발표 익일 시가", hold="10d", universe="KR 중대형",
        cost_bps=40.0, data_mode="synthetic_demo",
        n_trades=45, holding=[10], edge_bps=120.0, seed=200,
    ),
    Hypothesis(
        id="us_overnight_drift_v1",
        name="US 오버나잇 드리프트",
        family="factor", market="US",
        thesis="종가매수 익일시가매도(오버나잇 수익 편중 가설).",
        kill="비용 후 소멸 or random 구분불가(잘 알려진 팩터 = 붐빔).",
        entry="종가", hold="3d", universe="US 대형 ETF",
        cost_bps=5.0, data_mode="synthetic_demo",
        n_trades=90, holding=[3], edge_bps=12.0, seed=305,
    ),
]


def real_event_queue() -> list["Hypothesis"]:
    """실 이벤트 family 큐 (data_mode=real_event) — Auto-Research 실엔진 후보.
    합성 데모 대체: 실 KRX/DART 이벤트를 event_study+레드팀으로 루프에서 검증."""
    from research.scanner.families import FAMILIES
    out: list[Hypothesis] = []
    for fam_id, fam in FAMILIES.items():
        out.append(Hypothesis(
            id=f"real_{fam_id}", name=fam["thesis"][:22], family="event", market="KR",
            thesis=fam["thesis"], kill="매칭 random·비용·레드팀 통제 실패 시 폐기(사전정의)",
            entry="공시 익일 시가", hold="20거래일", universe="KR 전종목(PIT·survivorship-free)",
            cost_bps=40.0, data_mode="real_event", precomputed_id=fam_id))
    return out


def known_edges() -> list[dict]:
    """실제 registry에서 이미 판정난 실험 = 축적된 지식(LEARN 패널)."""
    from research.agents.experiment_registry import load_all
    latest: dict = {}
    for e in load_all():
        hid = e.get("hypothesis_id")
        if hid:
            latest[hid] = e
    return list(latest.values())
