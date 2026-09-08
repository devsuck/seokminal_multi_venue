"""Research Capture 배치 CLI — 추적 전략의 현재 위원회 평가를 예측 레지스트리로 흘려보낸다.

research_scheduler.CYCLES["daily"]의 "research_ledger_sync" 태스크 실체. capture_tracked_research()가
단일 진입점이며 이 CLI는 그걸 commit=True로 매일 1회 부르는 배선일 뿐 — 새 로직 없음.
"""
from datetime import datetime, timezone

from jarvis.research_workflow.research_capture import capture_tracked_research


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    r = capture_tracked_research(now=_now(), commit=True)
    print("=" * 76)
    print(f"RESEARCH CAPTURE — 추적전략 {r['tracked_strategies']} · 신규캡처 {r['captured']} · "
          f"중복skip {r['skipped_duplicates']}")
    print("=" * 76)
    for fam, n in r["by_family"].items():
        print(f"  {fam:<20} {n}")
    for s in r["sample"]:
        print(f"[{s['confidence'] or '-':<6}] {s['strategy_id']:<24} family={s['family'] or '-'} "
              f"framework={s['framework']}")
    print(f"\n{r['note']}")


if __name__ == "__main__":
    main()
