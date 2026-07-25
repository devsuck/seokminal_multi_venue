"""Historical Research Backfill Engine (P55) — 과거 퀀트 연구 결과를 기존 메모리로 임포트. **실행 없음.**

과거 연구(TSMOM·ORB·VWAP mean-reversion·buyback·liquidity·crypto·random baseline·walk-forward …)는
메모리 시스템 밖에 있어 recall/failure_intelligence 가 찾지 못했다. 이 임포터가 다양한 과거 파일
(JSON / JSONL / CSV)을 **얇은 매핑 계층**으로 정규화해 P54 어댑터 → P53 ingest() 로 흘려보낸다.

원칙(문서 §Constitution — Integration over Expansion, §P55):
  · **새 DB·병렬 연구 이력을 만들지 않는다.** 기존 experiment_tracking / research_memory_intelligence /
    research_ingestion / backtest_adapter 만 재사용.
  · **하나의 옛 포맷을 강요하지 않는다.** 필드 별칭 매핑 계층으로 흔한 형태를 흡수한다.
  · **누락 검증을 조작하지 않는다.** walk_forward·random_baseline·cost_impact 등이 없으면 INCOMPLETE
    로 남는다(P53 판정 그대로). 없는 값을 지어내지 않는다.
  · **멱등.** 동일 연구 내용은 파일명·임포트 시각과 무관하게 중복 지식을 만들지 않는다(내용 해시 기반).
  · provenance(source_type=historical_import·source_file·import_timestamp)로 원본 추적성 보존.
  · 거래·집행·브로커·자본배분 없음. Jarvis 는 연구 메모리 — 자율 집행자가 아니다.
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass, field

from jarvis.research_ingestion import models as M
from jarvis.research_ingestion.backtest_adapter import ingest_backtest

SOURCE_TYPE = "historical_import"

# ── 매핑 계층: 과거 연구 필드 별칭 → 표준 스키마 키 ──
_META_ALIASES = {
    "strategy_name": ("strategy_name", "strategy", "name", "strategy_id", "id"),
    "strategy_version": ("strategy_version", "version", "ver"),
    "hypothesis": ("hypothesis", "thesis", "description", "note", "notes"),
    "universe": ("universe", "market", "symbols", "instrument", "instrument_id"),
    "features": ("features", "factors", "signals"),
    "entry_rules": ("entry_rules", "entry", "entry_rule"),
    "exit_rules": ("exit_rules", "exit", "exit_rule"),
    "risk_rules": ("risk_rules", "risk", "risk_rule"),
    "outcome": ("outcome", "result", "verdict"),
    "lesson": ("lesson", "learning", "takeaway"),
    "root_cause": ("root_cause", "failure_reason", "reason"),
    "source": ("original_source", "data_source"),
}
# 표준 성능·검증 지표 별칭(값 계산 없음 — 존재하는 것만 옮긴다)
_METRIC_ALIASES = {
    "return": ("return", "total_return", "ann_return", "annual_return", "cagr",
               "net", "total_pnl_pct", "pnl_pct"),
    "sharpe": ("sharpe", "sharpe_ratio"),
    "max_drawdown": ("max_drawdown", "mdd", "maxdd", "max_dd"),
    "volatility": ("volatility", "vol", "annual_vol", "vol_annualized"),
    "walk_forward": ("walk_forward", "walkforward", "wf", "wf_consistency"),
    "out_of_sample": ("out_of_sample", "oos", "oos_sharpe"),
    "cost_impact": ("cost_impact", "cost", "cost_bps_impact"),
    "parameter_stability": ("parameter_stability", "param_stability", "stability"),
    "random_baseline": ("random_baseline", "random_percentile", "random_pct", "baseline"),
}
# 지표가 담겨 올 수 있는 중첩 컨테이너 키
_METRIC_CONTAINERS = ("metrics", "validation", "validation_results", "stats",
                      "results", "performance")
_PERIOD_START = ("start", "start_date", "from", "period_start", "begin")
_PERIOD_END = ("end", "end_date", "to", "period_end", "finish")


def _first(src: dict, keys):
    for k in keys:
        if k in src and src[k] not in (None, ""):
            return src[k]
    return None


def _collect_metrics(rec: dict) -> dict:
    """레코드(+중첩 컨테이너)에서 표준 지표만 뽑아낸다. 없는 값은 넣지 않는다(조작 금지)."""
    flat: dict = {}
    for c in _METRIC_CONTAINERS:
        if isinstance(rec.get(c), dict):
            flat.update(rec[c])
    # 최상위 평면 키도 포함(컨테이너 값이 우선하지 않도록 최상위를 마지막에)
    merged = {**flat, **{k: v for k, v in rec.items() if not isinstance(v, (dict, list))}}
    out: dict = {}
    for std, aliases in _METRIC_ALIASES.items():
        val = _first(merged, aliases)
        num = M._num(val)
        if num is not None:
            out[std] = num
    if rec.get("regime_dependent") is True or flat.get("regime_dependent") is True:
        out["regime_dependent"] = True
    return out


def _period(rec: dict) -> dict:
    p = rec.get("period")
    if isinstance(p, dict) and (p.get("start") or p.get("end")):
        return {"start": p.get("start", ""), "end": p.get("end", "")}
    dr = rec.get("date_range")
    if isinstance(dr, (list, tuple)) and len(dr) >= 2:
        return {"start": dr[0], "end": dr[1]}
    start, end = _first(rec, _PERIOD_START), _first(rec, _PERIOD_END)
    if start or end:
        return {"start": start or "", "end": end or ""}
    return {}


def _as_features(val) -> list:
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str) and val.strip():
        return [s.strip() for s in val.replace(";", ",").split(",") if s.strip()]
    return []


def map_record(rec: dict, *, field_map: dict | None = None) -> dict:
    """과거 연구 레코드 → P54/P53 context(정규화). 순수 매핑, 계산·조작 없음.

    field_map: 사용자 지정 별칭 오버라이드 {표준키: 원본키}. 지정 시 우선.
    """
    r = dict(rec or {})
    fm = field_map or {}
    ctx: dict = {}
    for std, aliases in _META_ALIASES.items():
        if std in fm and fm[std] in r:
            ctx[std] = r[fm[std]]
        else:
            val = _first(r, aliases)
            if val is not None:
                ctx[std] = val
    ctx["universe"] = "" if ctx.get("universe") is None else str(ctx.get("universe", ""))
    ctx["features"] = _as_features(ctx.get("features"))
    ctx["period"] = _period(r)
    ctx["metrics"] = _collect_metrics(r)
    ctx["source"] = str(ctx.get("source") or "").strip() or SOURCE_TYPE
    # 빈 문자열 메타는 제거(어댑터 기본값 사용)
    return {k: v for k, v in ctx.items() if v not in (None, "")}


# ── 파일 리더(포맷 감지) ──
def read_records(path: str) -> list[dict]:
    """확장자로 포맷 감지: .jsonl(줄당 객체) / .json(배열·객체) / .csv(행당 레코드)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".jsonl":
        out = []
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    out.append(json.loads(ln))
        return out
    if ext == ".csv":
        with open(path, encoding="utf-8", newline="") as f:
            return [dict(row) for row in csv.DictReader(f)]
    # .json (기본)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        # {"records": [...]} 또는 단일 레코드
        if isinstance(data.get("records"), list):
            return data["records"]
        return [data]
    return list(data)


@dataclass(frozen=True)
class ImportSummary:
    source_file: str
    record_count: int
    imported: int
    deduplicated: int
    incomplete: int
    failures: int
    successes: int
    errors: list = field(default_factory=list)
    ingestion_ids: list = field(default_factory=list)
    is_advisory: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


class HistoricalResearchImporter:
    """과거 연구 파일 → 기존 메모리(experiment_tracking/rmi) 백필. 실행/집행 권한 없음."""

    def __init__(self, engine=None) -> None:
        self._engine = engine

    def _eng(self):
        if self._engine is None:
            from jarvis.research_ingestion.engine import ResearchIngestionEngine
            self._engine = ResearchIngestionEngine()
        return self._engine

    def import_records(self, records, *, source_file="", now="", commit=False,
                       field_map=None) -> ImportSummary:
        rows = list(records or [])
        prov = {"source_type": SOURCE_TYPE, "source_file": source_file,
                "import_timestamp": now}
        eng = self._eng()
        imported = dedup = incomplete = fails = succ = 0
        errors: list = []
        iids: list = []
        for i, rec in enumerate(rows):
            try:
                ctx = map_record(rec, field_map=field_map)
                res = ingest_backtest({}, context=ctx, engine=eng, now=now,
                                      commit=commit, provenance=prov)
            except Exception as e:  # 개별 레코드 실패는 격리(백필 전체 중단 금지)
                errors.append({"index": i, "error": f"{type(e).__name__}: {e}"})
                continue
            iids.append(res.ingestion_id)
            if res.deduplicated:
                dedup += 1
            else:
                imported += 1
            if not res.validation_complete:
                incomplete += 1
            if res.memory_written == "failure":
                fails += 1
            elif res.memory_written == "success":
                succ += 1
        return ImportSummary(source_file=source_file, record_count=len(rows),
                             imported=imported, deduplicated=dedup, incomplete=incomplete,
                             failures=fails, successes=succ, errors=errors,
                             ingestion_ids=iids)

    def import_file(self, path, *, now="", commit=False, field_map=None) -> ImportSummary:
        records = read_records(path)
        return self.import_records(records, source_file=path, now=now, commit=commit,
                                   field_map=field_map)
