"""Research Archive Discovery (P56) — 과거 연구 자산을 **발견**한다(자동 임포트하지 않음). **실행 없음.**

디렉터리를 읽기 전용으로 훑어 과거 연구 후보 파일(JSON/JSONL/CSV/Markdown/Python 결과)을 찾고, 각 파일에서
전략·지표를 가볍게 감지해 **Research Import Manifest** 를 만든다. Manifest 는 사람 검토용 제안일 뿐이며
**발견 ≠ 임포트** — 이 모듈은 어떤 원장에도 쓰지 않는다(P55 import-history 가 사람 승인 후 실제 임포트).

원칙(문서 §Constitution — Integration over Expansion, §P56):
  · 새 DB·새 원장 없음. 순수 정적 분석(integration_audit 와 같은 읽기 전용 성격).
  · 감지는 P55 매핑 계층(map_record/_collect_metrics)을 재사용 — 별칭·중첩 컨테이너 흡수.
  · 누락 검증을 지어내지 않는다 — 지표 없으면 confidence NONE, 검증 불완전이면 INCOMPLETE 로 표시.
  · 거래·집행·브로커·자본배분 없음. 발견은 후보 목록화일 뿐 사람이 결정한다.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field

from jarvis.research_ingestion import models as M
from jarvis.research_ingestion.history_importer import (
    _METRIC_ALIASES,
    _collect_metrics,
    map_record,
    read_records,
)

SUPPORTED_EXT = (".json", ".jsonl", ".csv", ".md", ".markdown", ".py")
# 기본 탐색 위치(존재하는 것만) — 문서 §P56 검색 위치
DEFAULT_ROOTS = ("research", "experiments", "results", "reports", "production_review",
                 "beta_analysis", "analysis")
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".next", "_state", ".venv",
              "venv", "catalog", "data", "dist", "build"}
_MAX_BYTES = 2_000_000   # 파일당 읽기 상한(대형/바이너리 방지)

CONF_HIGH, CONF_MEDIUM, CONF_LOW, CONF_NONE = "HIGH", "MEDIUM", "LOW", "NONE"
VS_COMPLETE, VS_INCOMPLETE, VS_NONE = "COMPLETE", "INCOMPLETE", "NONE"

# md/py 텍스트에서 지표를 뽑기 위한 별칭 역색인
_ALIAS_TO_STD = {alias: std for std, aliases in _METRIC_ALIASES.items() for alias in aliases}
_NUM = r"-?\d+(?:\.\d+)?"


def _scan_text_metrics(text: str) -> dict:
    """Markdown/Python 텍스트에서 'alias: number' / 'alias = number' 패턴으로 지표 추출(계산 없음)."""
    out: dict = {}
    low = text.lower()
    for alias, std in _ALIAS_TO_STD.items():
        if std in out:
            continue
        m = re.search(rf"\b{re.escape(alias)}\b\s*[:=]\s*({_NUM})", low)
        if m:
            num = M._num(m.group(1))
            if num is not None:
                out[std] = num
    return out


def _detect_strategy_from_text(text: str, fallback: str) -> str:
    # Markdown 제목(# ...) 또는 'strategy: X' 우선, 없으면 파일명
    for pat in (r"(?m)^#{1,3}\s*(?:strategy\s*[:\-]?\s*)?([A-Za-z0-9_][\w \-/]{1,48})",
                r"(?i)\bstrategy(?:_name)?\s*[:=]\s*([A-Za-z0-9_][\w \-]{1,48})"):
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return fallback


def _confidence(strategy: str, metrics: dict) -> str:
    n = len(metrics)
    named = bool(strategy and strategy != "unknown")
    if named and n >= 6:
        return CONF_HIGH
    if named and n >= 1:
        return CONF_MEDIUM
    if n >= 3:
        return CONF_MEDIUM
    if n >= 1 or named:
        return CONF_LOW
    return CONF_NONE


def _validation_status(metrics: dict) -> str:
    if not metrics:
        return VS_NONE
    v = M.validate_backtest({"strategy_name": "x", "metrics": metrics})
    return VS_COMPLETE if v["validation_complete"] else VS_INCOMPLETE


@dataclass(frozen=True)
class DiscoveryCandidate:
    file: str
    file_type: str
    record_count: int
    detected_strategy: str
    detected_metrics: dict
    metric_count: int
    confidence: str
    validation_status: str
    import_candidate: bool           # 발견≠임포트 — 사람 검토용 제안 플래그
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveryManifest:
    roots: list
    files_scanned: int
    candidate_count: int
    by_confidence: dict
    candidates: list = field(default_factory=list)
    requires_human_review: bool = True
    is_advisory: bool = True
    disclaimer: str = ("Discovery lists candidates only — 발견은 임포트가 아니다. "
                       "실제 임포트는 사람 승인 후 import-history 로만.")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["candidates"] = [c.to_dict() if isinstance(c, DiscoveryCandidate) else c
                           for c in self.candidates]
        return d


def _analyze_structured(path: str, ext: str) -> tuple:
    """JSON/JSONL/CSV → (record_count, strategy, metrics). P55 매핑 재사용."""
    records = read_records(path)
    if not records:
        return 0, "", {}
    # 가장 지표가 풍부한 레코드를 대표로(간단·결정적)
    best_ctx, best_metrics = {}, {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        m = _collect_metrics(rec)
        if len(m) > len(best_metrics):
            best_metrics = m
            best_ctx = map_record(rec)
    strat = str(best_ctx.get("strategy_name", "")).strip()
    return len(records), strat, best_metrics


def _analyze_text(path: str, ext: str) -> tuple:
    """Markdown/Python → (record_count=1, strategy, metrics) 정규식 감지(best-effort, 저신뢰)."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        text = f.read(_MAX_BYTES)
    metrics = _scan_text_metrics(text)
    base = os.path.splitext(os.path.basename(path))[0]
    strat = _detect_strategy_from_text(text, base)
    return (1 if (metrics or strat) else 0), strat, metrics


def analyze_file(path: str) -> DiscoveryCandidate | None:
    """단일 파일 감지 → 후보(감지 실패·비지원·오류 시 None). 읽기 전용."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXT:
        return None
    try:
        if os.path.getsize(path) > _MAX_BYTES and ext in (".json", ".jsonl", ".csv"):
            return DiscoveryCandidate(file=path, file_type=ext.lstrip("."), record_count=0,
                                      detected_strategy="", detected_metrics={}, metric_count=0,
                                      confidence=CONF_NONE, validation_status=VS_NONE,
                                      import_candidate=False, note="파일이 너무 큼 — 건너뜀")
        if ext in (".md", ".markdown", ".py"):
            rc, strat, metrics = _analyze_text(path, ext)
        else:
            rc, strat, metrics = _analyze_structured(path, ext)
    except Exception as e:  # noqa: BLE001 — 개별 파일 오류 격리(스캔 중단 금지)
        return DiscoveryCandidate(file=path, file_type=ext.lstrip("."), record_count=0,
                                  detected_strategy="", detected_metrics={}, metric_count=0,
                                  confidence=CONF_NONE, validation_status=VS_NONE,
                                  import_candidate=False, note=f"{type(e).__name__}: {e}")
    conf = _confidence(strat, metrics)
    vstatus = _validation_status(metrics)
    # import_candidate: 전략명+지표가 있어 임포트를 검토할 가치가 있을 때만(그래도 사람 승인 필수)
    candidate = conf in (CONF_HIGH, CONF_MEDIUM) and bool(strat) and bool(metrics)
    return DiscoveryCandidate(
        file=path, file_type=ext.lstrip("."), record_count=rc, detected_strategy=strat,
        detected_metrics=metrics, metric_count=len(metrics), confidence=conf,
        validation_status=vstatus, import_candidate=candidate)


def _iter_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in SUPPORTED_EXT:
                yield os.path.join(dirpath, fn)


def discover(roots=None, *, base=".", include_empty=False, max_files=5000) -> DiscoveryManifest:
    """루트들을 훑어 Research Import Manifest 생성. **읽기 전용 — 아무 원장에도 쓰지 않는다.**

    roots: 탐색 디렉터리 목록(없으면 DEFAULT_ROOTS 중 존재하는 것). base: 상대경로 기준.
    include_empty: 감지 실패 파일도 목록에 포함할지(기본 False — 후보만).
    """
    if roots:
        search = [r if os.path.isabs(r) else os.path.join(base, r) for r in roots]
    else:
        search = [os.path.join(base, r) for r in DEFAULT_ROOTS
                  if os.path.isdir(os.path.join(base, r))]
    scanned = 0
    cands: list = []
    for root in search:
        if not os.path.isdir(root):
            continue
        for path in _iter_files(root):
            if scanned >= max_files:
                break
            scanned += 1
            c = analyze_file(path)
            if c is None:
                continue
            if include_empty or c.confidence != CONF_NONE:
                cands.append(c)
    cands.sort(key=lambda c: ({CONF_HIGH: 0, CONF_MEDIUM: 1, CONF_LOW: 2, CONF_NONE: 3}[c.confidence],
                              -c.metric_count, c.file))
    by_conf: dict = {}
    for c in cands:
        by_conf[c.confidence] = by_conf.get(c.confidence, 0) + 1
    return DiscoveryManifest(
        roots=[os.path.normpath(r) for r in search], files_scanned=scanned,
        candidate_count=len(cands), by_confidence=dict(sorted(by_conf.items())),
        candidates=cands)


class ResearchArchiveDiscovery:
    """과거 연구 자산 발견기(읽기 전용). 실행·임포트 권한 없음 — Manifest 만 만든다."""

    def discover(self, roots=None, *, base=".", include_empty=False) -> DiscoveryManifest:
        return discover(roots, base=base, include_empty=include_empty)

    def analyze_file(self, path: str):
        return analyze_file(path)
