"""Research Re-validation (P57) — 불완전 검증의 과거 실험을 **선택적으로** 재검증해 지식을 승격. **실행 없음.**

과거 실험은 검증이 불완전할 수 있다(예: Return·Sharpe 만 있고 Walk-Forward·Cost·Random Baseline 누락).
이 모듈은 누락 검증을 식별하고, **주입된 검증 하네스**가 실제로 산출한 값이 있으면 그것만 병합해 재수집(승격)한다.

절대 원칙(문서 §P57):
  · **없는 값을 지어내지 않는다.** 하네스가 반환한 수치만, 그것도 누락 집합에 한해 병합.
  · **하네스가 없으면(unavailable) INCOMPLETE 로 남는다.** 자동으로 채우지 않는다.
  · append-only 승격 — 원본 INCOMPLETE 는 보존되고, 재검증본은 버전을 올려 **새 판정 실험**으로 기록된다
    (이벤트 소싱 supersede). 새 저장소 없음(기존 P53 ingest 재사용).
  · 거래·집행·배포·자본배분 없음. 승격은 지식 판정일 뿐 사람 결정 필요.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from jarvis.research_ingestion import ledger
from jarvis.research_ingestion import models as M

REVALIDATION_SOURCE = "revalidation"


@dataclass(frozen=True)
class RevalidationPlan:
    strategy_name: str
    present: list
    missing: list
    revalidatable: bool          # 채울 누락이 있는가
    validation_complete: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RevalidationResult:
    strategy_name: str
    was_incomplete: bool
    missing_before: list
    filled: list                 # 하네스가 실제로 채운 지표
    missing_after: list
    upgraded: bool               # 재수집(승격)이 일어났는가
    status: str                  # COMPLETE | INCOMPLETE | ALREADY_COMPLETE | UNAVAILABLE
    new_outcome: str = ""
    new_ingestion_id: str = ""
    is_advisory: bool = True
    is_decision: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RevalidationBacklog:
    incomplete_count: int
    items: list = field(default_factory=list)   # {strategy_name, ingestion_id, missing_hint}

    def to_dict(self) -> dict:
        return asdict(self)


class ResearchRevalidationEngine:
    """불완전 검증 실험의 선택적 재검증. 하네스 주입 가능(없으면 INCOMPLETE 유지). 실행 권한 없음."""

    def __init__(self, engine=None) -> None:
        self._engine = engine

    def _eng(self):
        if self._engine is None:
            from jarvis.research_ingestion.engine import ResearchIngestionEngine
            self._engine = ResearchIngestionEngine()
        return self._engine

    def plan(self, record: dict) -> RevalidationPlan:
        """레코드의 검증 완전성 진단 — 무엇이 있고 무엇이 빠졌는가. 쓰기 없음."""
        rec = record or {}
        metrics = rec.get("metrics") or {}
        present = [m for m in M.REQUIRED_VALIDATIONS if m in metrics]
        missing = [m for m in M.REQUIRED_VALIDATIONS if m not in metrics]
        return RevalidationPlan(
            strategy_name=str(rec.get("strategy_name", "")).strip() or "unknown_strategy",
            present=present, missing=missing, revalidatable=bool(missing),
            validation_complete=not missing)

    def revalidate(self, record: dict, *, harness=None, now="", commit=False) -> RevalidationResult:
        """누락 검증을 하네스로 채워 승격(가능할 때만). **하네스 없으면 INCOMPLETE 유지, 조작 없음.**

        harness: callable(record) -> dict[str, number]. 실제로 계산된 검증 지표만 반환해야 한다.
                 이 엔진은 반환값 중 **누락 집합에 속한 수치만** 병합한다(그 외는 무시 — 조작 방지).
        """
        rec = dict(record or {})
        name = str(rec.get("strategy_name", "")).strip() or "unknown_strategy"
        metrics = dict(rec.get("metrics") or {})
        missing_before = [m for m in M.REQUIRED_VALIDATIONS if m not in metrics]

        if not missing_before:
            return RevalidationResult(
                strategy_name=name, was_incomplete=False, missing_before=[], filled=[],
                missing_after=[], upgraded=False, status="ALREADY_COMPLETE",
                note="이미 검증 완전 — 재검증 불필요.")

        if harness is None:
            # 하네스 없음 → 자동으로 채우지 않음. INCOMPLETE 유지(조작 금지).
            return RevalidationResult(
                strategy_name=name, was_incomplete=True, missing_before=missing_before,
                filled=[], missing_after=missing_before, upgraded=False, status="UNAVAILABLE",
                note="검증 하네스 없음 — INCOMPLETE 유지(없는 값을 지어내지 않음).")

        produced = harness(rec) or {}
        # **누락 집합에 한해, 수치만** 병합(하네스가 지어낸/무관 필드는 무시)
        filled = []
        for k in missing_before:
            if k in produced:
                num = M._num(produced[k])
                if num is not None:
                    metrics[k] = num
                    filled.append(k)
        missing_after = [m for m in M.REQUIRED_VALIDATIONS if m not in metrics]

        if not filled:
            return RevalidationResult(
                strategy_name=name, was_incomplete=True, missing_before=missing_before,
                filled=[], missing_after=missing_after, upgraded=False, status="INCOMPLETE",
                note="하네스가 유효한 누락 지표를 산출하지 못함 — INCOMPLETE 유지.")

        # 승격: 버전 올려 재수집(append-only supersede). 원본 INCOMPLETE 보존.
        base_ver = str(rec.get("strategy_version", "")).strip()
        upgraded_rec = dict(rec)
        upgraded_rec["metrics"] = metrics
        upgraded_rec["strategy_version"] = f"{base_ver}+reval" if base_ver else "reval"
        upgraded_rec["source"] = REVALIDATION_SOURCE
        prov = {"source_type": REVALIDATION_SOURCE, "source_file": "",
                "import_timestamp": now}
        res = self._eng().ingest(upgraded_rec, now, commit=commit, provenance=prov)
        status = "COMPLETE" if not missing_after else "INCOMPLETE"
        return RevalidationResult(
            strategy_name=name, was_incomplete=True, missing_before=missing_before,
            filled=filled, missing_after=missing_after,
            upgraded=(commit and not res.deduplicated), status=status,
            new_outcome=res.outcome, new_ingestion_id=res.ingestion_id,
            note=("검증 완전 — 판정 승격" if not missing_after
                  else "부분 보강 — 여전히 일부 누락(INCOMPLETE)."))

    def incomplete_backlog(self) -> RevalidationBacklog:
        """기존 수집 원장(ring_)에서 INCOMPLETE 실험을 목록화(사람 검토용 포인터). 읽기 전용."""
        items = []
        for r in ledger.read_ingestions():
            if r.get("validation_complete") is False and r.get("source_type") != REVALIDATION_SOURCE:
                items.append({"strategy_name": r.get("strategy_name", ""),
                              "ingestion_id": r.get("ingestion_id", ""),
                              "outcome": r.get("outcome", ""),
                              "source_type": r.get("source_type", "") or "live"})
        return RevalidationBacklog(incomplete_count=len(items), items=items)
