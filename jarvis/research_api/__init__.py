"""jarvis.research_api — Research Intelligence API Backend (P10.29). **읽기 전용.**

대시보드·AI 에이전트용 백엔드 인터페이스 계층. 상위 계층(P10.23~P10.28)을 **READ ONLY** 로 참조(파일 기반,
import 없음)해 시스템 상태·연구 타임라인·전략 계보·알파/리스크/에이전트 요약·거버넌스 리포트를 결정적 조회 API
로 제공하고 API 스키마·Query Registry·대시보드 데이터 뷰·엔드포인트 메타·접근 로그를 남긴다.

**API·데이터 접근 전용 — 거래 실행 없음.** POST 실행·trade·order·deployment 엔드포인트 없음. GET(읽기)만.
execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk controller import·
호출 없음. READ ≠ WRITE · QUERY ≠ EXECUTE · API ≠ TRADE. 접근 감사 원장은 append-only 해시체인·결정적·재현.
물리 원장은 rapi_ 접두사.
"""
from jarvis.research_api.engine import ResearchAPIEngine  # noqa: F401
from jarvis.research_api.models import (  # noqa: F401
    ALLOWED_METHODS,
    ENDPOINT_META,
    ENDPOINT_SCHEMAS,
    FORBIDDEN_METHODS,
    FORBIDDEN_VERBS,
    AccessLogRecord,
    APIResponse,
    APISummary,
    EndpointRecord,
    ForbiddenEndpoint,
    ImmutableEndpointError,
    ImmutableQueryError,
    ImmutableSchemaError,
    ImmutableViewError,
    InvalidEndpointMethod,
    QueryRecord,
    SchemaRecord,
    UnknownEndpointError,
    ViewRecord,
)
