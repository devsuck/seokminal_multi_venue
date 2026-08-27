"""파이프라인 층간 판정 불일치 감시 — autoresearch vs jarvis registry.

왜 필요한가(2026-08-27): autoresearch 루프는 `auto_fac_kr_size_smb` 등 3건을
5주 넘게 매 실행 CANDIDATE로 판정했는데, jarvis registry에는 같은 3건이
`rejected`로 박혀 있었다. 두 층이 정반대 결론을 들고 공존했지만 어느 쪽도
상대를 안 봐서 아무도 눈치채지 못했다(원인은 `backtest.py`의 지표 키 미스매치).

여기서 잡는 것:
  1. verdict_conflict — 실험원장은 candidate인데 registry는 rejected/blocked
  2. reasonless_rejection — critic이 내린 rejected인데 근거(critic_flags)가 비어 있음
     (`seed:` 계열 전이는 reason 문자열에 사유가 있으므로 대상 아님 — 오탐을 내면
      감시가 늑대소년이 되고, 그게 애초에 이 버그가 5주간 숨은 이유다)
  3. stale_candidate — candidate인데 registry에 아예 등재조차 안 됨

실행: PYTHONPATH=. python3 research/check_pipeline_consistency.py
종료코드: 불일치 0건이면 0, 있으면 1 (크론/CI에서 알람 걸 수 있게).
"""
from __future__ import annotations

import argparse
import json
import sys

from jarvis.registry import StrategyRegistry
from research.agents.experiment_registry import load_all

# 실험원장 candidate가 registry에서 이 상태면 충돌로 본다.
_NEGATIVE_STATES = {"rejected", "blocked_by_data", "killed", "retired"}
# registry가 실험원장 id에 붙이는 접두사(autoresearch 배선 관례).
_ID_PREFIXES = ("", "auto_")


def _latest_by_hypothesis() -> dict[str, dict]:
    """hypothesis_id별 최신 실험 결과 1건."""
    latest: dict[str, dict] = {}
    for row in load_all():
        hid = row.get("hypothesis_id")
        if hid:
            latest[hid] = row  # load_all은 append 순서 → 마지막이 최신
    return latest


def _registry_state(reg: StrategyRegistry, hypothesis_id: str) -> dict | None:
    """접두사 변형을 훑어 registry 상태를 찾는다."""
    candidates = [hypothesis_id]
    for prefix in _ID_PREFIXES:
        if prefix and hypothesis_id.startswith(prefix):
            candidates.append(hypothesis_id[len(prefix):])
        elif prefix:
            candidates.append(prefix + hypothesis_id)
    for sid in candidates:
        state = reg.state(sid)
        if state:
            return state
    return None


def _rejection_events(path: str) -> list[dict]:
    """registry 원장에서 `to == rejected` 전이 이벤트만. 폴드 상태엔 evidence가 없다."""
    events: list[dict] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("to") == "rejected":
                    events.append(event)
    except FileNotFoundError:
        return []
    return events


def find_inconsistencies() -> list[dict]:
    """불일치 목록. 각 항목: {kind, hypothesis_id, detail}."""
    reg = StrategyRegistry()
    issues: list[dict] = []

    # 1·3 — 실험원장 candidate가 registry에서 어떻게 취급되는지
    for hid, row in _latest_by_hypothesis().items():
        is_candidate = (row.get("status") == "candidate"
                        or str(row.get("verdict", "")).endswith("CANDIDATE"))
        if not is_candidate:
            continue
        state = _registry_state(reg, hid)
        if state is None:
            issues.append({"kind": "stale_candidate", "hypothesis_id": hid,
                           "detail": "실험원장 candidate인데 registry 미등재"})
            continue
        if state.get("status") in _NEGATIVE_STATES:
            issues.append({
                "kind": "verdict_conflict", "hypothesis_id": hid,
                "detail": (f"실험원장 candidate(p={row.get('p')}, "
                           f"pct={row.get('percentile')}) vs "
                           f"registry {state.get('status')}"),
            })

    # 2 — critic이 내린 근거 없는 rejected
    # 폴드된 state는 evidence를 안 들고 있어서 원장 이벤트를 직접 훑는다.
    for event in _rejection_events(reg.path):
        if not str(event.get("reason", "")).startswith("critic:"):
            continue  # seed/수동 전이는 reason 문자열이 사유를 담는다
        evidence = event.get("evidence") or {}
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except ValueError:
                evidence = {}
        if not evidence.get("critic_flags"):
            issues.append({
                "kind": "reasonless_rejection",
                "hypothesis_id": event.get("strategy_id"),
                "detail": "critic rejected인데 critic_flags 근거 없음",
            })
    return issues


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="research.check_pipeline_consistency")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = ap.parse_args(argv)

    issues = find_inconsistencies()
    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2))
    else:
        if not issues:
            print("✅ 층간 판정 불일치 없음")
        else:
            print(f"⚠️  불일치 {len(issues)}건\n")
            for kind in ("verdict_conflict", "reasonless_rejection", "stale_candidate"):
                group = [i for i in issues if i["kind"] == kind]
                if not group:
                    continue
                print(f"── {kind} ({len(group)}건)")
                for i in group:
                    print(f"   {i['hypothesis_id']}: {i['detail']}")
                print()
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
