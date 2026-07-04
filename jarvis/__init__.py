"""Jarvis Quant OS — 에이전틱 리서치·페이퍼·제한적 집행 시스템.

핵심 규칙: AI는 자유롭게 생각/연구/제안하되, **자기 집행 권한은 확장 못 한다.**
연구=자율, 검증=결정적, 집행=제한, 전부 감사가능.
"""
from __future__ import annotations

from jarvis.config import AUTONOMY_LEVEL, LEVEL_NAMES, live_execution_enabled


def boot() -> dict:
    """레지스트리·메모리 시드 + paper_candidate 자동 forward 배선(idempotent)."""
    from jarvis.memory import MarketMemory, seed_lessons
    from jarvis.registry.lifecycle import StrategyRegistry, seed_from_experiment_registry
    lessons = seed_lessons(MarketMemory())
    strategies = seed_from_experiment_registry(StrategyRegistry())
    # 시드된 paper_candidate = forward 러너 자동 연결(paper_active). 이미 배포된 건 skip.
    deployed = 0
    try:
        from jarvis.paper.deploy import auto_deploy_all
        deployed = auto_deploy_all().get("deployed", 0)
    except Exception:  # noqa: BLE001
        pass
    return {"lessons_seeded": lessons, "strategies_seeded": strategies, "auto_deployed": deployed}


def status() -> dict:
    return {
        "system": "Jarvis Quant OS",
        "initialized": True,
        "autonomy_level": AUTONOMY_LEVEL,
        "autonomy_name": LEVEL_NAMES.get(AUTONOMY_LEVEL, "?"),
        "live_execution": "enabled" if live_execution_enabled() else "disabled",
        "paper_monitoring": "enabled",
        "research_automation": "enabled",
        "strategy_registry": "active",
        "risk_governor": "active (dry-run)",
        "audit_log": "active",
    }


def banner() -> str:
    s = status()
    return (
        "Jarvis Quant OS initialized.\n"
        f"Current autonomy level: Level {s['autonomy_level']} ({s['autonomy_name']}).\n"
        f"Live execution: {s['live_execution']}.\n"
        "Paper monitoring: enabled.\n"
        "Research automation: enabled.\n"
        "Strategy registry: active.\n"
        "Risk governor: active in dry-run mode.\n"
        "Audit log: active."
    )
