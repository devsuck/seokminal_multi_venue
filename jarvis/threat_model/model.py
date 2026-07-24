"""위협 모델 (P15) — 자산·신뢰 경계·공격면·위협 행위자·리스크 매트릭스·완화·잔여 리스크. **문서·분석 전용·결정적.**

Autonomous Quant Research OS 의 정적 위협 모델을 구조화해 제공한다. 실행 능력을 도입하지 않으며, 관찰·기록 전용 아키
텍처(거래·집행·배포·권한 변경 없음)를 전제로 리스크를 산정한다. 완전 additive.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# ── 리스크 등급 ──
LOW, MEDIUM, HIGH, CRITICAL = "LOW", "MEDIUM", "HIGH", "CRITICAL"


def risk_score(likelihood: int, impact: int) -> int:
    """리스크 점수 = likelihood(1..5) × impact(1..5)."""
    lk = max(1, min(5, int(likelihood)))
    im = max(1, min(5, int(impact)))
    return lk * im


def severity_of(score: int) -> str:
    """점수 → 등급(결정적 구간)."""
    if score >= 15:
        return CRITICAL
    if score >= 9:
        return HIGH
    if score >= 4:
        return MEDIUM
    return LOW


# ── 자산 ──
ASSETS = (
    {"id": "A1", "name": "append-only 해시체인 원장", "value": "HIGH"},
    {"id": "A2", "name": "연구 리포트·스냅샷·벤치마크 산출물", "value": "MEDIUM"},
    {"id": "A3", "name": "의존성·SBOM·라이선스 메타데이터", "value": "MEDIUM"},
    {"id": "A4", "name": "소스 코드 및 결정적 알고리즘", "value": "HIGH"},
    {"id": "A5", "name": "실행 경계(비활성 live_execution 게이트)", "value": "CRITICAL"},
)

# ── 신뢰 경계 ──
TRUST_BOUNDARIES = (
    {"id": "TB1", "name": "연구 계층(READ ONLY) ↔ 집행 계층(게이트)",
     "description": "P9~P13 연구 계층은 집행 능력이 없다. live_execution 은 사람 게이트."},
    {"id": "TB2", "name": "저장소 ↔ 외부 의존성/공급망",
     "description": "PyPI 의존성·서드파티 라이선스 유입 경계."},
    {"id": "TB3", "name": "원장 파일시스템 ↔ 프로세스",
     "description": "append-only 원장 쓰기/읽기 경계."},
    {"id": "TB4", "name": "개발자 커밋 ↔ CI/릴리스",
     "description": "코드·시크릿·아티팩트 유입 경계."},
)

# ── 공격면 ──
ATTACK_SURFACES = (
    {"id": "AS1", "name": "의존성 공급망(악성/취약 패키지)"},
    {"id": "AS2", "name": "하드코딩 시크릿 유출"},
    {"id": "AS3", "name": "원장 변조·해시체인 위조"},
    {"id": "AS4", "name": "역직렬화/eval 등 코드 실행 취약점"},
    {"id": "AS5", "name": "산출물 위·변조(리포트/스냅샷)"},
    {"id": "AS6", "name": "실행 경계 우회(권한 상승)"},
)

# ── 위협 행위자 ──
THREAT_ACTORS = (
    {"id": "TA1", "name": "외부 공격자", "motivation": "데이터 탈취·조작"},
    {"id": "TA2", "name": "악성 의존성 유지관리자", "motivation": "공급망 침투"},
    {"id": "TA3", "name": "내부자(오용/실수)", "motivation": "부주의·권한 오용"},
    {"id": "TA4", "name": "자동화 봇/스캐너", "motivation": "무차별 자격증명 탐색"},
)

# ── 위협(리스크 매트릭스 원천) ──
_THREATS = (
    {"id": "T1", "asset": "A1", "surface": "AS3", "actor": "TA1",
     "name": "원장 변조", "likelihood": 2, "impact": 5,
     "mitigations": ("SHA256 해시체인", "content_hash 재계산 검증", "결정적 replay", "복구는 새 파일"),
     "residual": "물리적 파일 접근 시 사본 위조 가능 — 오프사이트 검증 권장"},
    {"id": "T2", "asset": "A5", "surface": "AS6", "actor": "TA3",
     "name": "실행 경계 우회", "likelihood": 1, "impact": 5,
     "mitigations": ("연구 계층 실행 능력 없음", "live_execution 기본 False", "사람 게이트 arm",
                     "금지 동사/임포트 스캔"),
     "residual": "권한 정책 변경은 ADMIN_HUMAN_ONLY 수준 필요"},
    {"id": "T3", "asset": "A3", "surface": "AS1", "actor": "TA2",
     "name": "공급망 침투", "likelihood": 3, "impact": 4,
     "mitigations": ("SBOM 생성·검증", "의존성 감사", "라이선스 호환성", "핀 고정 권장"),
     "residual": "미고정 의존성 존재 시 업스트림 변조 위험"},
    {"id": "T4", "asset": "A4", "surface": "AS2", "actor": "TA4",
     "name": "시크릿 유출", "likelihood": 3, "impact": 4,
     "mitigations": ("시크릿 스캐너", "마스킹 보고", "플레이스홀더 무시"),
     "residual": "신규 패턴/난독 시크릿은 미탐 가능"},
    {"id": "T5", "asset": "A4", "surface": "AS4", "actor": "TA1",
     "name": "코드 실행 취약점", "likelihood": 2, "impact": 5,
     "mitigations": ("정적 분석(eval/exec/pickle/subprocess)", "AST 검사", "역직렬화 경고"),
     "residual": "동적 로딩 경로는 정적 분석 한계"},
    {"id": "T6", "asset": "A2", "surface": "AS5", "actor": "TA3",
     "name": "산출물 위·변조", "likelihood": 2, "impact": 3,
     "mitigations": ("아티팩트 체크섬", "is_binding=False 강제", "SBOM 직렬번호"),
     "residual": "체크섬 미검증 소비 시 위조본 수용 가능"},
)


@dataclass(frozen=True)
class Threat:
    id: str
    name: str
    asset: str
    surface: str
    actor: str
    likelihood: int
    impact: int
    score: int
    severity: str
    mitigations: tuple
    residual: str

    def to_dict(self) -> dict:
        return {**asdict(self), "mitigations": list(self.mitigations)}


def _threat(t: dict) -> Threat:
    score = risk_score(t["likelihood"], t["impact"])
    return Threat(id=t["id"], name=t["name"], asset=t["asset"], surface=t["surface"],
                  actor=t["actor"], likelihood=t["likelihood"], impact=t["impact"], score=score,
                  severity=severity_of(score), mitigations=t["mitigations"], residual=t["residual"])


def threats() -> list:
    """위협 목록(점수 내림차순·id 오름차순 정렬, 결정적)."""
    ts = [_threat(t) for t in _THREATS]
    ts.sort(key=lambda x: (-x.score, x.id))
    return ts


def risk_matrix() -> dict:
    """리스크 매트릭스 집계(등급별 카운트 + 위협 목록)."""
    ts = [t.to_dict() for t in threats()]
    by_sev: dict = {}
    for t in ts:
        by_sev[t["severity"]] = by_sev.get(t["severity"], 0) + 1
    return {"threats": ts, "count": len(ts), "by_severity": dict(sorted(by_sev.items())),
            "max_score": max((t["score"] for t in ts), default=0)}


def residual_risks() -> list:
    """잔여 리스크 목록(위협별)."""
    return [{"id": t.id, "name": t.name, "severity": t.severity, "residual": t.residual}
            for t in threats()]


def build_threat_model(*, generated_at: str = "") -> dict:
    """완전한 위협 모델(자산·신뢰경계·공격면·행위자·리스크 매트릭스·완화·잔여) — 결정적."""
    matrix = risk_matrix()
    return {
        "title": "Autonomous Quant Research OS — Threat Model (P15)",
        "generated_at": generated_at,
        "scope": "관찰·분석·기록 전용 연구 OS. 거래·집행·배포·권한변경 능력 없음.",
        "assets": [dict(a) for a in ASSETS],
        "trust_boundaries": [dict(b) for b in TRUST_BOUNDARIES],
        "attack_surfaces": [dict(s) for s in ATTACK_SURFACES],
        "threat_actors": [dict(a) for a in THREAT_ACTORS],
        "risk_matrix": matrix,
        "mitigations": {t["id"]: t["mitigations"] for t in matrix["threats"]},
        "residual_risks": residual_risks(),
        "asset_count": len(ASSETS), "threat_count": matrix["count"],
    }


def filter_by_severity(severity: str) -> list:
    """지정 등급 위협만 필터."""
    return [t.to_dict() for t in threats() if t.severity == severity]


def to_markdown(model: dict | None = None) -> str:
    """위협 모델 마크다운 렌더(결정적)."""
    m = model or build_threat_model()
    lines = [f"# {m['title']}", "", f"> {m['scope']}", "", "## Assets"]
    for a in m["assets"]:
        lines.append(f"- **{a['id']}** {a['name']} (value: {a['value']})")
    lines += ["", "## Trust Boundaries"]
    for b in m["trust_boundaries"]:
        lines.append(f"- **{b['id']}** {b['name']}")
    lines += ["", "## Risk Matrix"]
    for t in m["risk_matrix"]["threats"]:
        lines.append(f"- **{t['id']}** {t['name']} — {t['severity']} "
                     f"(L{t['likelihood']}×I{t['impact']}={t['score']})")
    lines += ["", "## Residual Risks"]
    for r in m["residual_risks"]:
        lines.append(f"- **{r['id']}** {r['name']}: {r['residual']}")
    return "\n".join(lines)
