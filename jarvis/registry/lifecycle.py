"""전략 생애주기 FSM — 결정적. draft→live 직행 불가, rejected 부활 불가.

전이는 append-only 이벤트로만. 현재상태 = 이벤트 폴드.
가드: sanity_check_only는 절대 paper_candidate 못 됨(플래그). live-side 전이는 사람 approver 필수.
config_hash 동결: paper_candidate 도달 시 frozen. 이후 변경은 ADMIN_HUMAN_ONLY.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from enum import Enum

from jarvis.audit import record
from jarvis.config import CODE_VERSION, state_path

_REG = "registry.jsonl"


class Status(str, Enum):
    DRAFT = "draft"
    DATA_AUDIT_PASSED = "data_audit_passed"
    BLOCKED_BY_DATA = "blocked_by_data"
    SANITY_CHECK_ONLY = "sanity_check_only"
    BACKTESTED = "backtested"
    WATCHLIST = "watchlist"
    REJECTED = "rejected"
    PAPER_CANDIDATE = "paper_candidate"
    PAPER_CANDIDATE_FWD = "paper_candidate_forward_test_required"
    PAPER_ACTIVE = "paper_active"
    PAPER_FAILED = "paper_failed"
    PAPER_RETIRED = "paper_retired"
    LIVE_CANDIDATE = "live_candidate"
    MICRO_LIVE = "micro_live"
    CONSTRAINED_LIVE = "constrained_live"
    RETIRED = "retired"


STATUSES = [s.value for s in Status]

# 합법 전이표. 없으면 IllegalTransition.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    Status.DRAFT: {Status.DATA_AUDIT_PASSED, Status.BLOCKED_BY_DATA, Status.SANITY_CHECK_ONLY, Status.REJECTED},
    Status.BLOCKED_BY_DATA: {Status.DRAFT, Status.RETIRED},
    Status.SANITY_CHECK_ONLY: {Status.BACKTESTED, Status.REJECTED, Status.RETIRED},
    Status.DATA_AUDIT_PASSED: {Status.BACKTESTED, Status.REJECTED},
    Status.BACKTESTED: {Status.WATCHLIST, Status.REJECTED},
    Status.WATCHLIST: {Status.PAPER_CANDIDATE, Status.REJECTED, Status.RETIRED},
    Status.PAPER_CANDIDATE: {Status.PAPER_CANDIDATE_FWD, Status.PAPER_ACTIVE, Status.REJECTED, Status.RETIRED},
    Status.PAPER_CANDIDATE_FWD: {Status.PAPER_ACTIVE, Status.REJECTED, Status.RETIRED},
    Status.PAPER_ACTIVE: {Status.LIVE_CANDIDATE, Status.PAPER_FAILED, Status.PAPER_RETIRED},
    Status.PAPER_FAILED: {Status.RETIRED},
    Status.PAPER_RETIRED: {Status.RETIRED},
    Status.LIVE_CANDIDATE: {Status.MICRO_LIVE, Status.PAPER_ACTIVE, Status.RETIRED},
    Status.MICRO_LIVE: {Status.CONSTRAINED_LIVE, Status.PAPER_ACTIVE, Status.RETIRED},
    Status.CONSTRAINED_LIVE: {Status.MICRO_LIVE, Status.PAPER_ACTIVE, Status.RETIRED},
    Status.REJECTED: {Status.RETIRED},   # 부활 불가(paper/live 절대 못 감)
    Status.RETIRED: set(),               # 종단
}

# 사람 approver 필수 전이(live-side).
_HUMAN_APPROVAL_REQUIRED = {Status.LIVE_CANDIDATE, Status.MICRO_LIVE, Status.CONSTRAINED_LIVE}


def _v(s) -> str:
    return s.value if isinstance(s, Status) else str(s)


def config_hash(config: dict) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]


class IllegalTransition(Exception):
    pass


class StrategyRegistry:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or state_path(_REG)

    # ── 저장/폴드 ────────────────────────────────────────────
    def _events(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def _append(self, ev: dict) -> dict:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
        return ev

    def _fold_state(self, strategy_id: str, events: list[dict]) -> dict | None:
        cur = None
        for ev in events:
            if ev.get("strategy_id") != strategy_id:
                continue
            cur = {
                "strategy_id": strategy_id,
                "status": ev["to"],
                "name": ev.get("name", cur["name"] if cur else strategy_id),
                "config_hash": ev.get("config_hash") or (cur or {}).get("config_hash"),
                "frozen": ev.get("frozen", (cur or {}).get("frozen", False)),
                "flags": ev.get("flags", (cur or {}).get("flags", [])),
                "data_version": ev.get("data_version") or (cur or {}).get("data_version"),
                "last_reason": ev.get("reason"),
                "updated_at": ev.get("timestamp"),
            }
        return cur

    def state(self, strategy_id: str) -> dict | None:
        return self._fold_state(strategy_id, self._events())

    def all_current(self) -> list[dict]:
        events = self._events()  # 파일 1회만 읽음
        ids: list[str] = []
        seen: set[str] = set()
        for ev in events:
            sid = ev.get("strategy_id")
            if sid and sid not in seen:
                seen.add(sid); ids.append(sid)
        return [s for i in ids if (s := self._fold_state(i, events)) is not None]

    def list(self, status: str | None = None) -> list[dict]:
        rows = self.all_current()
        return [r for r in rows if status is None or r["status"] == status]

    # ── 등록/전이 ────────────────────────────────────────────
    def register(self, strategy_id: str, name: str, config: dict,
                 data_version: str = "unknown", asset_class: str = "", family: str = "") -> dict:
        if self.state(strategy_id) is not None:
            raise IllegalTransition(f"{strategy_id} 이미 존재(재등록 불가)")
        ev = self._transition_event(strategy_id, None, Status.DRAFT, "registered",
                                    name=name, config=config, data_version=data_version,
                                    asset_class=asset_class, family=family)
        return self._append(ev)

    def transition(self, strategy_id: str, to, reason: str, *,
                   evidence: dict | None = None, approver: str | None = None,
                   data_version: str | None = None, config: dict | None = None) -> dict:
        st = self.state(strategy_id)
        if st is None:
            raise IllegalTransition(f"{strategy_id} 미등록")
        frm = st["status"]
        to_v = _v(to)
        allowed = {_v(x) for x in ALLOWED_TRANSITIONS.get(Status(frm), set())}
        if to_v not in allowed:
            self._deny(strategy_id, frm, to_v, "illegal_transition")
            raise IllegalTransition(f"{strategy_id}: {frm} → {to_v} 불법(허용: {sorted(allowed)})")

        # sanity_check_only 이력이면 paper_candidate 영구 차단
        flags = list(st.get("flags") or [])
        if frm == Status.SANITY_CHECK_ONLY.value or "sanity_only" in flags:
            if "sanity_only" not in flags:
                flags.append("sanity_only")
            if to_v in (Status.PAPER_CANDIDATE.value, Status.PAPER_CANDIDATE_FWD.value):
                self._deny(strategy_id, frm, to_v, "sanity_only_cannot_paper")
                raise IllegalTransition(f"{strategy_id}: sanity_check_only는 paper_candidate 불가")

        # live-side는 사람 approver 필수
        if to_v in {s.value for s in _HUMAN_APPROVAL_REQUIRED} and not approver:
            self._deny(strategy_id, frm, to_v, "human_approval_required")
            raise IllegalTransition(f"{strategy_id}: {to_v} 전이엔 사람 approver 필수")

        ev = self._transition_event(strategy_id, frm, to_v, reason, evidence=evidence,
                                    approver=approver, data_version=data_version,
                                    config=config, prev=st, flags=flags)
        self._append(ev)
        record({"layer": "registry", "action": "transition", "strategy_id": strategy_id,
                "from": frm, "to": to_v, "reason": reason, "approver": approver,
                "config_hash": ev.get("config_hash"), "result": "committed"})
        return ev

    # ── 내부 ─────────────────────────────────────────────────
    def _transition_event(self, sid, frm, to, reason, *, name=None, config=None,
                          data_version=None, evidence=None, approver=None,
                          asset_class="", family="", prev=None, flags=None) -> dict:
        prev = prev or {}
        to_v = _v(to)
        # config 동결: paper_candidate 도달 시 hash 고정. 이후 config 무시(변경은 ADMIN).
        frozen = prev.get("frozen", False)
        chash = prev.get("config_hash")
        if config is not None and not frozen:
            chash = config_hash(config)
        if to_v in (Status.PAPER_CANDIDATE.value, Status.PAPER_CANDIDATE_FWD.value):
            frozen = True
        return {
            "strategy_id": sid, "name": name or prev.get("name") or sid,
            "from": frm, "to": to_v, "reason": reason,
            "evidence": evidence or {}, "approver": approver,
            "asset_class": asset_class or prev.get("asset_class", ""),
            "family": family or prev.get("family", ""),
            "config_hash": chash, "frozen": frozen,
            "flags": flags if flags is not None else (prev.get("flags") or []),
            "data_version": data_version or prev.get("data_version") or "unknown",
            "code_version": CODE_VERSION,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def _deny(self, sid, frm, to, reason) -> None:
        record({"layer": "registry", "action": "transition", "strategy_id": sid,
                "from": frm, "to": to, "reason": reason, "result": "denied"})


def seed_from_experiment_registry(reg: StrategyRegistry | None = None) -> int:
    """기존 research registry에서 초기 시드(idempotent per hypothesis_id). 반환=추가 수."""
    reg = reg or StrategyRegistry()
    try:
        from research.agents.experiment_registry import load_all
    except Exception:
        return 0

    # Get set of already-registered hypothesis_ids (idempotent: skip already-registered ones)
    existing_ids: set[str] = {s.get("strategy_id") for s in reg.all_current() if s.get("strategy_id")}

    # Load latest experiment entries, keeping only one per hypothesis_id
    try:
        experiments = load_all()
    except Exception:
        return 0

    latest: dict = {}
    for e in experiments:
        hid = e.get("hypothesis_id")
        if hid:
            latest[hid] = e

    added = 0
    for hid, e in latest.items():
        # Skip if already registered
        if hid in existing_ids:
            continue

        cfg = {"hypothesis_id": hid, "verdict": e.get("verdict", "")}
        reg.register(hid, name=hid, config=cfg,
                     data_version=str(e.get("data_quality", "unknown")))
        st = str(e.get("status", ""))
        # research status → 생애주기 대략 매핑(안전측: paper_candidate 이상은 안 올림).
        if st.startswith("blocked"):
            reg.transition(hid, Status.BLOCKED_BY_DATA, "seed: blocked_by_data")
        elif st == "rejected":
            reg.transition(hid, Status.DATA_AUDIT_PASSED, "seed")
            reg.transition(hid, Status.BACKTESTED, "seed")
            reg.transition(hid, Status.REJECTED, f"seed: {e.get('verdict','rejected')[:60]}")
        elif st.startswith("paper_candidate") or st == "candidate":
            reg.transition(hid, Status.DATA_AUDIT_PASSED, "seed")
            reg.transition(hid, Status.BACKTESTED, "seed")
            reg.transition(hid, Status.WATCHLIST, "seed")
            reg.transition(hid, Status.PAPER_CANDIDATE, f"seed: {e.get('verdict','')[:60]}",
                           evidence={"random_pct": e.get("random_pct"), "p": e.get("p")})
        added += 1
    return added
