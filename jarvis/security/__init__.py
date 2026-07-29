"""jarvis.security — 시크릿·정적 보안 분석 (P15 Security & Compliance). **탐지·보고 전용·완전 additive.**

하드코딩 자격증명(API 키·비밀번호·개인키·토큰·AWS/OpenAI/GitHub/Slack/JWT/SSH) 탐지와 정적 위험 패턴(eval·exec·
pickle·subprocess shell·os.system·path traversal·unsafe deserialization) 분석을 제공한다. 코드를 실행하지 않고
자격증명을 저장·전송하지 않는다. 기존 P9~P14 모듈/원장 불변. 거래·집행·배포 능력 없음.
"""
from jarvis.security.report import scan_files, scan_source  # noqa: F401
from jarvis.security.secrets import (  # noqa: F401
    SecretFinding,
    redact,
    scan_line,
    scan_report,
    scan_text,
    shannon_entropy,
)
from jarvis.security.static import (  # noqa: F401
    StaticFinding,
    analyze_report,
    analyze_source,
    detect_path_traversal,
)
