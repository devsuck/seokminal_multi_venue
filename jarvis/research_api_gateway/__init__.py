"""jarvis.research_api_gateway — Research API Gateway Layer (P33). **통합 읽기 전용 API.**

통합 API 계층. 읽기 전용 서비스만 노출한다: 지식 질의·연구 요약·이력·지표·리포트·계보. Service Registry·Query Log·
Response Log·Reports·Lineage 를 소유한다.

**거래·배포·실행·승인·배분을 노출하지 않는다.** execution/broker/live_trading/portfolio_execution import·호출 없음.
READ ONLY · GATEWAY ≠ EXECUTION · QUERY ≠ MUTATION. 불변·append-only·해시체인·결정적·재현. 상위 계층(P10~P32)은
READ ONLY. 원장 rgw_ 접두사.
"""
from jarvis.research_api_gateway.engine import ResearchApiGatewayEngine  # noqa: F401
from jarvis.research_api_gateway.models import (  # noqa: F401
    FORBIDDEN_SERVICE_TYPES,
    SERVICE_TYPES,
    ArtifactRecord,
    ForbiddenServiceError,
    GatewayReportRecord,
    GatewaySummary,
    QueryRecord,
    ResponseRecord,
    ServiceRecord,
    UnknownEntityError,
    is_readonly_service,
)
