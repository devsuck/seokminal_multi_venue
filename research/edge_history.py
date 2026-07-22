"""엣지 감쇠(decay) 추적 — 검증 리포트 요약 추출 + 시계열 저장/로드.

각 가설 검증기(run_*_validate)의 리포트는 shape이 조금씩 다르다(sharp/whale은
groups+pools, mlb는 단일 BH-FDR 풀). 공통 요약을 관용적으로 뽑아
(min p-value / FDR 생존수 / 표본수 / 유의여부) 한 줄로 정규화하고, 매 검증 실행마다
`research/data/edge_history/{hyp}.jsonl`에 타임스탬프와 함께 append한다. 이렇게 쌓인
궤적으로 "엣지가 언제부터 시들었나"(레짐변화)를 돈 잃기 전에 포착한다.

신규 통계는 만들지 않는다 — 이미 계산된 리포트 필드를 재구조화만 한다(관찰 전용).
"""
from __future__ import annotations

import json
from pathlib import Path

_HISTORY_DIR = Path("research/data/edge_history")


def _collect(obj, key: str) -> list:
    """중첩 dict/list 어디에 있든 key의 모든 값을 재귀 수집."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and isinstance(v, (int, float)):
                out.append(v)
            else:
                out += _collect(v, key)
    elif isinstance(obj, list):
        for v in obj:
            out += _collect(v, key)
    return out


def summarize_report(report: dict) -> dict:
    """검증 리포트 → 공통 요약(shape 무관). 관찰 전용, 신규 통계 없음.

    반환: {hypothesis, verdict, min_p_value, n_survivors, n_tested, n_events, significant}.
    min_p_value=리포트 내 모든 p_value 중 최소(가장 강한 신호). n_survivors/n_tested=
    pools의 BH-FDR 생존/검정수 합. significant=생존>0."""
    hyp = report.get("hypothesis", "unknown")
    verdict = report.get("verdict")
    if report.get("error"):
        return {"hypothesis": hyp, "verdict": "error", "error": str(report["error"])[:200],
                "min_p_value": None, "n_survivors": 0, "n_tested": 0, "n_events": 0,
                "significant": False}
    p_values = [p for p in _collect(report, "p_value") if p is not None]
    n_survivors = sum(_collect(report, "n_survivors"))
    n_tested = sum(_collect(report, "n_tested"))
    n_events = sum(_collect(report, "n_events"))
    min_p = min(p_values) if p_values else None
    if verdict is None:
        verdict = "ok" if p_values else "no_data"
    return {
        "hypothesis": hyp,
        "verdict": verdict,
        "min_p_value": round(min_p, 5) if min_p is not None else None,
        "n_survivors": int(n_survivors),
        "n_tested": int(n_tested),
        "n_events": int(n_events),
        "significant": bool(n_survivors > 0),
    }


def record(hyp: str, summary: dict, ts: float, history_dir: Path | None = None) -> None:
    """요약을 시계열 파일에 append. ts는 호출측이 주입(스크립트/엔진에서 time.time()).
    동일 ts 중복 append는 막지 않음(로드시 최신 우선). 실패해도 조용히 넘어감(관찰용)."""
    d = history_dir or _HISTORY_DIR
    try:
        d.mkdir(parents=True, exist_ok=True)
        row = {"ts": float(ts), **{k: summary.get(k) for k in
               ("verdict", "min_p_value", "n_survivors", "n_tested", "n_events", "significant")}}
        with (d / f"{hyp}.jsonl").open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def load_trajectory(hyp: str, limit: int = 50, history_dir: Path | None = None) -> list[dict]:
    """가설의 최근 검증 궤적(오래된→최신 순, 최대 limit개). 없으면 []."""
    d = history_dir or _HISTORY_DIR
    path = d / f"{hyp}.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def trajectory_trend(traj: list[dict]) -> dict:
    """궤적 → 간단 추세 요약(대시보드 스파크라인 보조). 최근 min_p_value 방향."""
    ps = [(r["ts"], r["min_p_value"]) for r in traj if r.get("min_p_value") is not None]
    if len(ps) < 2:
        return {"points": len(ps), "direction": "flat", "latest_p": ps[-1][1] if ps else None}
    first, last = ps[0][1], ps[-1][1]
    direction = "improving" if last < first else ("decaying" if last > first else "flat")
    return {"points": len(ps), "direction": direction, "latest_p": last, "first_p": first}
