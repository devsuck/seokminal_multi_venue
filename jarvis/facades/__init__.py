"""jarvis.facades — Consolidation Facades (C1). **읽기전용, 무손실 통합.**

과분할된 연구 모듈 계열(coordination 9 · oversight 5 · observability 3 · self_improvement 4)마다 **단일 참조점**을
제공해, 신규 개발·문서·온보딩이 계열당 1개만 보게 한다. 헌장 "Simplicity Over Complexity / Integration Before
Expansion" 실행.

**하부 모듈은 변경/삭제하지 않는다(프리즈 유지). 파사드는 얇은 레지스트리 — 새 엔진/원장/지능 계층이 아니다.**
거래·집행·배포 없음. 기존 P1~P45 불변.
"""
from jarvis.facades.engine import FacadeRegistry  # noqa: F401
from jarvis.facades.models import FAMILIES, FacadeInfo  # noqa: F401
