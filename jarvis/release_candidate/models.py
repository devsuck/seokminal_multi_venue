"""Jarvis Research Platform v1.0 Release Candidate 자료형 (P40) — 릴리스 준비. **실행 없음.**

Jarvis Research Platform v1.0 릴리스 후보를 준비한다: VERSION·릴리스 노트·아키텍처 요약·기능 인벤토리·테스트 요약·보안
요약·알려진 한계. 완전 저장소 테스트·보안 스캔·무결성·재현·의존성 검증을 실행한다. **연구 시스템 완료. 라이브 실행 없음.
자율 거래 없음. 연구 보조만.** RELEASE CANDIDATE · NO LIVE EXECUTION · RESEARCH ASSISTANCE ONLY. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json

# ── 버전 ──
VERSION = "1.0.0-rc.1"
PLATFORM_NAME = "Jarvis Research Platform"

# ── 릴리스 산출물(7종) ──
RELEASE_ARTIFACTS = (
    "VERSION",
    "RELEASE_NOTES.md",
    "ARCHITECTURE_SUMMARY.md",
    "FEATURE_INVENTORY.md",
    "TEST_SUMMARY.md",
    "SECURITY_SUMMARY.md",
    "KNOWN_LIMITATIONS.md",
)

# ── 릴리스 게이트 검증 단계 ──
RELEASE_GATES = ("system_integrity", "security_audit", "production_readiness", "replay_validation",
                 "dependency_validation")

# ── 상태 선언(불변) ──
STATUS_STATEMENTS = (
    "Research system completed.",
    "No live execution.",
    "No autonomous trading.",
    "No broker connectivity.",
    "No deployment authority.",
    "Research assistance only.",
)

# ── 알려진 한계 ──
KNOWN_LIMITATIONS = (
    "관찰·기록·분석 전용 — 실험·거래·배포를 실행하지 않는다(설계상 의도).",
    "모든 실행·승인·배분은 사람이 외부에서 수행하며 시스템은 기록만 한다.",
    "결정적 재현을 위해 ID 에 월클럭을 사용하지 않는다(입력 다이제스트 기반).",
    "상위 계층은 파일 읽기(JSONL)로만 소비 — 실시간 스트리밍·이벤트 버스 없음.",
    "브로커·시장 데이터·라이브 포트폴리오 연결이 없다(설계상 금지).",
)


def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def artifact_hash(content) -> str:
    return _digest({"content": content})


def is_release_artifact(name) -> bool:
    return name in RELEASE_ARTIFACTS
