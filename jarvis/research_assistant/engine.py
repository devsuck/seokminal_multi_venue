"""Personal Research Assistant Engine (P44) — 개인 연구 어시스턴트. **분석만, 결정·승인·집행 없음.**

기존 원장을 READ ONLY 로 읽어 일일 요약·실험 요약·실패 분석·지식 리캡·진행 요약·잠재 연구 영역을 만든다.
**투자 결정·전략 승인·행동 실행을 하지 않는다.** ASSISTANT ANALYZES · DOES NOT DECIDE / APPROVE / EXECUTE.
execution/broker/live_trading import·호출 없음. 엔진은 execute()/trade()/deploy()/allocate()/approve()/decide() 를
노출하지 않는다. 결정적. 리더 주입 가능(테스트·통합). 산출 스냅샷은 자체 ras_ 원장에만 append.
"""
from __future__ import annotations

from jarvis.research_assistant import ledger
from jarvis.research_assistant import models as M
from jarvis.research_assistant.models import (
    GENESIS,
    AdvisoryNoteRecord,
    AssistantReportRecord,
    AssistantSummary,
    DailySummary,
    ExperimentSummary,
    FailureAnalysis,
    KnowledgeRecap,
    PotentialAreas,
    ProgressSummary,
    content_hash,
    input_digest,
)

# 실패 클러스터가 잠재 영역 제안으로 승격되는 최소 근거 수
_AREA_MIN_EVIDENCE = 2
_RECENT = 5


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchAssistantEngine:
    """개인 연구 어시스턴트. 기존 원장 READ ONLY 분석·요약. 결정/승인/집행 권한 없음.

    reader(source_name)->list[dict] 주입 가능(테스트 격리·통합). 기본은 ras_ 리더로 실제 원장 파일 읽기.
    """

    def __init__(self, reader=None) -> None:
        self._reader = reader or ledger.read_source

    def _read(self, name) -> list:
        try:
            return list(self._reader(name) or [])
        except Exception:  # noqa: BLE001
            return []

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ══════════════ 일일 요약 ══════════════
    def daily_summary(self) -> DailySummary:
        counts = {name: len(self._read(name)) for name in sorted(M.SOURCES)}
        total = sum(counts.values())
        active = sum(1 for v in counts.values() if v > 0)
        headline = (f"총 {total}개 기록 · 활성 소스 {active}/{len(counts)}"
                    if total else "아직 기록이 없습니다(신규 로컬 환경).")
        return DailySummary(total_records=total, active_sources=active, source_counts=counts,
                            headline=headline)

    # ══════════════ 최근 실험 요약 ══════════════
    def experiment_summary(self, limit: int = 20) -> ExperimentSummary:
        runs = self._read("experiment_runs")
        results = self._read("experiment_results")
        by_metric: dict = {}
        for r in results:
            metric = M.first_field(r, ("metric", "name", "kind")) or "unknown"
            by_metric.setdefault(metric, []).append(M.first_field(r, ("value", "score")))
        metric_stats = {m: M.numeric_stats(vals) for m, vals in sorted(by_metric.items())}
        headline = (f"실험 실행 {len(runs)}건 · 결과 {len(results)}건 · 지표 {len(metric_stats)}종"
                    if runs or results else "최근 실험 기록이 없습니다.")
        return ExperimentSummary(run_count=len(runs), result_count=len(results),
                                 metric_stats=metric_stats, headline=headline)

    # ══════════════ 실패 분석 ══════════════
    def failure_analysis(self) -> FailureAnalysis:
        failures = list(self._read("failures"))
        for inc in self._read("incidents"):
            failures.append(inc)
        # 실험 결과 중 실패 신호가 있는 것도 포함
        for r in self._read("experiment_results"):
            status = M.first_field(r, ("status", "outcome", "passed"))
            if status and (M.is_failure_signal(status) or str(status).lower() == "false"):
                failures.append(r)
        clusters: dict = {}
        for f in failures:
            reason = (M.first_field(f, ("reason", "category", "pattern", "type", "metric"))
                      or "unknown")
            clusters[reason] = clusters.get(reason, 0) + 1
        clusters = dict(sorted(clusters.items(), key=lambda kv: (-kv[1], kv[0])))
        findings = [f"'{reason}' 관련 {n}건" for reason, n in clusters.items()]
        suggested = [f"'{reason}' 원인 검토 권장(근거 {n}건)"
                     for reason, n in clusters.items() if n >= _AREA_MIN_EVIDENCE]
        return FailureAnalysis(failure_count=len(failures), clusters=clusters, findings=findings,
                               suggested_reviews=suggested)

    # ══════════════ 지식 리캡 ══════════════
    def knowledge_recap(self) -> KnowledgeRecap:
        memories = self._read("memories")
        lessons = self._read("lessons")
        patterns = self._read("patterns")
        topics = []
        for rec in (memories + lessons + patterns):
            t = M.first_field(rec, ("topic", "title", "summary", "name", "key"))
            if t:
                topics.append(t)
        recent_topics = sorted(set(topics))[:_RECENT]
        headline = (f"지식 {len(memories)} · 교훈 {len(lessons)} · 패턴 {len(patterns)}"
                    if (memories or lessons or patterns) else "축적된 지식 기록이 없습니다.")
        return KnowledgeRecap(memory_count=len(memories), lesson_count=len(lessons),
                              pattern_count=len(patterns), recent_topics=recent_topics,
                              headline=headline)

    # ══════════════ 연구 진행 요약 ══════════════
    def progress_summary(self) -> ProgressSummary:
        stage_counts = {
            "experiments": len(self._read("experiments")),
            "experiment_runs": len(self._read("experiment_runs")),
            "knowledge": len(self._read("memories")) + len(self._read("lessons")),
            "models": len(self._read("models")),
            "validations": len(self._read("validations")),
            "successes": len(self._read("successes")),
            "failures": len(self._read("failures")),
        }
        notes = []
        if stage_counts["experiment_runs"]:
            notes.append(f"실험 파이프라인 활동 {stage_counts['experiment_runs']}건")
        if stage_counts["knowledge"]:
            notes.append(f"지식 자산 {stage_counts['knowledge']}건 축적")
        if stage_counts["validations"]:
            notes.append(f"모델 검증 {stage_counts['validations']}건")
        if not notes:
            notes.append("초기 단계 — 아직 축적된 연구 활동이 적습니다.")
        return ProgressSummary(stage_counts=dict(sorted(stage_counts.items())), progress_notes=notes)

    # ══════════════ 잠재 연구 영역 ══════════════
    def potential_areas(self) -> PotentialAreas:
        """실패 클러스터·지표 변동성에서 결정적으로 '가능한 다음 검토'를 제안. **결정 아님 — 사람 검토용.**"""
        areas = []
        fa = self.failure_analysis()
        for reason, n in fa.clusters.items():
            if n >= _AREA_MIN_EVIDENCE and reason != "unknown":
                areas.append({"area": f"Investigate {reason}",
                              "rationale": f"실패/이슈 {n}건이 '{reason}' 에 집중",
                              "evidence": n})
        # 지표 변동성(범위 큼) → 안정성 검토 제안
        es = self.experiment_summary()
        for metric, st in es.metric_stats.items():
            if st["count"] >= _AREA_MIN_EVIDENCE and (st["max"] - st["min"]) > 0:
                spread = round(st["max"] - st["min"], 6)
                areas.append({"area": f"Review stability of {metric}",
                              "rationale": f"'{metric}' 범위 {spread}(min {st['min']}~max {st['max']})",
                              "evidence": st["count"]})
        areas.sort(key=lambda a: (-a["evidence"], a["area"]))
        return PotentialAreas(areas=areas)

    # ══════════════ 메모리 등뼈(C2) — 통합 회상 ══════════════
    # 검색 시 각 소스 레코드의 참조 ID 후보
    _REF_FIELDS = ("run_id", "experiment_id", "result_id", "memory_id", "lesson_id", "pattern_id",
                   "failure_id", "success_id", "incident_id", "model_id", "validation_id", "id",
                   "topic", "title", "name")

    def recall(self, topic, limit: int = 5) -> "RecallResult":
        """흩어진 지식 원장 전체(실험/결과/실패/교훈/기억/패턴/인시던트/모델/검증)에서 topic 을 결정적으로 검색.

        헌장 "Memory Is The Competitive Advantage" — '모멘텀 예전에 해봤어? 왜 실패했지?'의 답.
        **READ ONLY 분석·회상만.** 결정/승인/집행 없음.
        """
        t = (topic or "").strip().lower()
        source_hits: dict = {}
        total = 0
        if t:
            for name in sorted(M.SOURCES):
                hits = []
                for rec in self._read(name):
                    blob = M.record_text(rec).lower()
                    if t in blob:
                        hits.append({"ref": M.first_field(rec, self._REF_FIELDS) or "?",
                                     "text": M.record_text(rec)[:140]})
                if hits:
                    source_hits[name] = hits[:limit]
                    total += len(hits)
        tried = total > 0
        if not t:
            headline = "검색어가 비어 있습니다."
        elif tried:
            where = ", ".join(f"{k}({len(v)})" for k, v in sorted(source_hits.items()))
            headline = f"'{topic}' 관련 {total}건 발견 — {where}. 사람 검토 필요."
        else:
            headline = f"'{topic}' 관련 축적 기록 없음 — 아직 시도 안 함(또는 원장 비어 있음)."
        return M.RecallResult(topic=topic, total_hits=total, tried_before=tried,
                              source_hits=dict(sorted(source_hits.items())),
                              sources_hit=sorted(source_hits), headline=headline)

    def have_we_tried(self, topic) -> dict:
        """'이 아이디어 예전에 해봤어?' 예/아니오 + 근거 요약. 결정 아님."""
        r = self.recall(topic)
        return {"topic": topic, "tried_before": r.tried_before, "evidence": r.total_hits,
                "where": r.sources_hit, "headline": r.headline,
                "is_decision": False, "is_advisory": True}

    # ══════════════ Failure Intelligence — 실패 분류·근본원인·재발방지 ══════════════
    # 카테고리별 교훈(문서 "Lessons Learned" — 정적·결정적)
    _LESSONS = {
        M.FAIL_OVERFITTING: "인샘플 과적합 의심 — walk-forward·out-of-sample 우선, 파라미터 수 최소화.",
        M.FAIL_DATA_LEAKAGE: "룩어헤드/데이터 누설 의심 — 피처 시점 정합·미래정보 차단 재점검.",
        M.FAIL_REGIME_CHANGE: "레짐 변화에 취약 — regime-robust 검증·기간 분할 재평가.",
        M.FAIL_COST_SENSITIVITY: "거래비용 민감 — 비용 반영 백테스트·회전율 축소 검토.",
        M.FAIL_LIQUIDITY: "유동성 문제 — 체결 가능 규모·거래량 필터 재설정.",
        M.FAIL_POOR_HYPOTHESIS: "가설 자체가 약함 — 랜덤 베이스라인 대비 엣지 재확인, 신호 재정의.",
        M.FAIL_TIMING: "타이밍/지연 문제 — 진입 시점·지연 가정 재검토.",
        M.FAIL_RISK_CONCENTRATION: "리스크 집중 — 상관·편중 제한, 분산 제약 추가.",
        M.FAIL_PARAMETER_INSTABILITY: "파라미터 불안정 — 민감도 분석·안정 구간만 채택.",
        M.FAIL_UNCLASSIFIED: "미분류 — 실패 사유를 구조화해 재기록 필요.",
    }

    def _failure_records(self) -> list:
        """실패 소스(실패 원장·인시던트·실패 신호 결과)를 모아 분류체계로 태깅."""
        out = []
        for src in ("failures", "incidents"):
            for rec in self._read(src):
                text = M.record_text(rec)
                out.append({"ref": M.first_field(rec, self._REF_FIELDS) or "?",
                            "category": M.classify_failure(text), "text": text[:160], "source": src})
        for r in self._read("experiment_results"):
            status = M.first_field(r, ("status", "outcome", "passed"))
            if status and (M.is_failure_signal(status) or str(status).lower() == "false"):
                text = M.record_text(r)
                out.append({"ref": M.first_field(r, self._REF_FIELDS) or "?",
                            "category": M.classify_failure(text), "text": text[:160],
                            "source": "experiment_results"})
        return out

    def failure_intelligence(self) -> "FailureIntelligenceResult":
        """실패를 9종 분류체계로 구조화 — '왜 실패했나' + 카테고리별 교훈. **분석만, 결정 아님.**

        Agentic Research Evolution 문서: "Learn Why did this fail, not only Did this fail."
        """
        recs = self._failure_records()
        by_cat: dict = {}
        for r in recs:
            by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
        by_cat = dict(sorted(by_cat.items(), key=lambda kv: (-kv[1], kv[0])))
        top = next(iter(by_cat), M.FAIL_UNCLASSIFIED) if by_cat else M.FAIL_UNCLASSIFIED
        lessons = [f"{cat}: {self._LESSONS.get(cat, '')} ({n}건)" for cat, n in by_cat.items()]
        return M.FailureIntelligenceResult(
            total_failures=len(recs), by_category=by_cat, records=recs[:50],
            top_category=top, lessons=lessons)

    def mistake_check(self, topic) -> dict:
        """'이 아이디어, 예전에 같은 실수 했나?' — 주제 관련 과거 실패를 분류체계로 회수. 재발 방지.

        문서: "avoid repeating previous mistakes". **결정 아님 — 사람 검토용.**
        """
        t = (topic or "").strip()
        hits = []
        cats: dict = {}
        for r in self._failure_records():
            if t and t.lower() in r["text"].lower():
                hits.append(r)
                cats[r["category"]] = cats.get(r["category"], 0) + 1
        cats = dict(sorted(cats.items(), key=lambda kv: (-kv[1], kv[0])))
        made = len(hits) > 0
        if not t:
            headline = "검색어가 비어 있습니다."
        elif made:
            where = ", ".join(f"{c}({n})" for c, n in cats.items())
            headline = (f"'{topic}' 관련 과거 실패 {len(hits)}건 — 유형: {where}. "
                        "같은 실수 반복 주의(사람 검토).")
        else:
            headline = f"'{topic}' 관련 과거 실패 기록 없음(또는 원장 비어 있음)."
        return {"topic": topic, "made_this_mistake": made, "failure_count": len(hits),
                "by_category": cats, "headline": headline,
                "is_advisory": True, "is_decision": False}

    # ══════════════ 어시스턴트 중심화(C3) — 질의 라우터 ══════════════
    def ask(self, question) -> dict:
        """자연어 질문 → 결정적 인텐트 라우팅 → 기존 능력으로 응답. **분석·회상만, 결정/승인/집행 없음.**

        헌장 "The Assistant Is The Primary Interface". LLM/외부호출 없음 — 키워드 기반 결정적 라우팅.
        지원 예: "예전에 X 해봤어?" · "왜 실패했어?" · "이번 주 뭐 바뀌었어?" · "다음에 뭘 볼까?" · "뭘 배웠어?"
        """
        q = (question or "").strip()
        ql = q.lower()
        topic = M.extract_topic(q)

        def has(*kw):
            return any(k in ql for k in kw)

        def wrap(intent, answer, data):
            return {"question": q, "intent": intent, "topic": topic, "answer": answer,
                    "data": data, "is_advisory": True, "is_decision": False,
                    "disclaimer": "어시스턴트는 분석·회상만 한다 — 투자 결정·전략 승인·집행 없음(사람이 결정)."}

        if not q:
            return wrap("empty", "질문이 비어 있습니다.", {})
        # 1) 같은 실수 반복? (재발 방지) — 'mistake' 신호는 recall 보다 우선
        if has("mistake", "repeat", "같은 실수", "반복", "실수 했"):
            r = self.mistake_check(topic)
            return wrap("mistake", r["headline"], r)
        # 2) 예전에 해봤나 / 이미 시도?
        if has("tried", "already", "before", "예전", "해봤", "이미", "했나"):
            r = self.have_we_tried(topic)
            return wrap("recall", r["headline"], r)
        # 2) 왜 실패? — 분류체계(Failure Intelligence) 포함
        if has("fail", "실패", "왜 안", "why did", "안 됐"):
            fi = self.failure_intelligence()
            data = fi.to_dict()
            if topic:
                data["mistake_check"] = self.mistake_check(topic)
                ans = (f"'{topic}' 관련 실패 {data['mistake_check']['failure_count']}건 · "
                       f"전체 실패 {fi.total_failures}건 · 상위 유형 {fi.top_category}. 사람 검토 필요.")
            else:
                ans = (f"실패 {fi.total_failures}건 · 상위 유형 {fi.top_category} · "
                       f"유형 {len(fi.by_category)}종.")
            return wrap("failure", ans, data)
        # 3) 이번 주/최근 뭐 바뀌었나
        if has("this week", "이번", "recent", "최근", "changed", "바뀐", "무슨 일", "new"):
            es = self.experiment_summary().to_dict()
            d = self.daily_summary().to_dict()
            return wrap("recent", f"활동: 실험 {es['run_count']} · 결과 {es['result_count']} · 총 기록 {d['total_records']}.",
                        {"experiments": es, "daily": d})
        # 4) 다음에 뭘 볼까
        if has("next", "다음", "review", "검토", "봐야", "추천", "should i"):
            pa = self.potential_areas()
            ans = (f"가능한 다음 검토 {len(pa.areas)}건: " + ", ".join(a["area"] for a in pa.areas[:3])
                   if pa.areas else "제안할 영역이 아직 없습니다(원장 비어 있음).")
            return wrap("next_areas", ans, pa.to_dict())
        # 5) 뭘 배웠나 / 지식
        if has("learn", "배운", "배웠", "knowledge", "지식", "lesson"):
            kr = self.knowledge_recap()
            return wrap("knowledge", kr.headline, kr.to_dict())
        # 6) 주제어가 있으면 회상, 없으면 개요
        if topic:
            r = self.recall(topic)
            return wrap("recall", r.headline, r.to_dict())
        d = self.daily_summary()
        return wrap("overview", d.headline, d.to_dict())

    def suggested_questions(self) -> list:
        """어시스턴트 예시 질문(헌장 예시). 정적·결정적."""
        return [
            "What changed this week?",
            "Have we already tried momentum?",
            "Why did it fail?",
            "What should I review next?",
            "What did we learn?",
        ]

    # ══════════════ 번들 리포트 + 기록 ══════════════
    def build_bundle(self) -> dict:
        return {
            "daily": self.daily_summary().to_dict(),
            "experiments": self.experiment_summary().to_dict(),
            "failures": self.failure_analysis().to_dict(),
            "knowledge": self.knowledge_recap().to_dict(),
            "progress": self.progress_summary().to_dict(),
            "potential_areas": self.potential_areas().to_dict(),
        }

    def generate_report(self, scope="DAILY", now="", *, commit=False) -> AssistantReportRecord:
        """모든 요약을 묶은 리포트 스냅샷(결정적 digest). **is_advisory=True·is_decision=False.**"""
        bundle = self.build_bundle()
        daily = self.daily_summary()
        rid = M.report_id(scope, now)
        rec = AssistantReportRecord(
            report_id=rid, scope=scope, total_records=daily.total_records,
            experiment_run_count=bundle["experiments"]["run_count"],
            failure_count=bundle["failures"]["failure_count"],
            knowledge_count=(bundle["knowledge"]["memory_count"]
                             + bundle["knowledge"]["lesson_count"]
                             + bundle["knowledge"]["pattern_count"]),
            potential_area_count=len(bundle["potential_areas"]["areas"]),
            bundle_digest=M.content_digest(bundle), is_advisory=True, is_decision=False,
            requires_human_review=True, disclaimer=M.DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        return AssistantReportRecord(**rec)

    def record_advisory(self, area, rationale="", evidence_count=0, now="",
                        *, commit=False) -> AdvisoryNoteRecord:
        """자문 노트 기록(비구속). **is_binding=False — 결정/승인 아님.**"""
        seq = len(ledger.read_notes())
        nid = M.note_id(area, seq)
        rec = AdvisoryNoteRecord(
            note_id=nid, area=area, rationale=rationale, evidence_count=int(evidence_count),
            is_binding=False, requires_human_review=True, created_at=now,
            input_hash=input_digest(area, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.note_exists, ledger.notes_head, ledger.append_note, nid, rec,
                         commit=commit)
        return AdvisoryNoteRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.research_assistant.verify import verify_chain
        return verify_chain()

    def summary(self, now="") -> AssistantSummary:
        return AssistantSummary(timestamp=now, report_count=len(ledger.read_reports()),
                                note_count=len(ledger.read_notes()))
