"""jarvis.threat_model — 위협 모델 (P15 Security & Compliance). **문서·분석 전용·완전 additive.**

자산·신뢰 경계·공격면·위협 행위자·리스크 매트릭스(likelihood×impact)·완화·잔여 리스크를 결정적으로 제공한다. 실행
능력을 도입하지 않으며, 관찰·기록 전용 아키텍처를 전제한다. 기존 P9~P14 모듈/원장 불변. 거래·집행·배포 능력 없음.
"""
from jarvis.threat_model.model import (  # noqa: F401
    ASSETS,
    ATTACK_SURFACES,
    THREAT_ACTORS,
    TRUST_BOUNDARIES,
    Threat,
    build_threat_model,
    filter_by_severity,
    residual_risks,
    risk_matrix,
    risk_score,
    severity_of,
    threats,
    to_markdown,
)
