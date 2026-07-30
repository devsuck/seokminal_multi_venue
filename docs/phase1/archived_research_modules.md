# Archived Research Modules — Phase1 STEP3-B

9 modules retained on disk (NOT deleted) per explicit user instruction citing possible
future migration. Each module's `__init__.py` docstring carries an `ARCHIVED (Phase1
STEP3-B, 2026-07-31)` marker documenting the same evidence recorded here. All 9 have
zero real import statements, zero runtime/scheduler/dashboard dependency, and no
backing state files — evidence alone would support REMOVE, same bar as the 37
REMOVE_CANDIDATE modules deleted in Commits 1–3. They are archived rather than deleted
solely because the user's STEP3 approval named them explicitly for retention.

## security_audit AUDIT_TARGETS cluster (5 modules)

Consumed only via `security_audit`'s dynamic `AUDIT_TARGETS` importlib scan — a test
utility that sits outside default `pyproject` testpaths and never runs by default. No
static imports anywhere else in the repo.

- **research_agent_coordination** (P26) — no ledger files (`racd_*.jsonl`).
- **research_monitoring** (P23) — also listed in `system_integration` LAYER_REGISTRY (catalog string, not import). No ledger files (`rmon_*.jsonl`).
- **research_reliability** (P24) — also referenced by `system_integration`'s cross-layer hash-check test. No ledger files (`rel_*.jsonl`).
- **research_resource_manager** (P32) — no ledger files (`rrm_*.jsonl`).
- **research_strategy_generation** (P29) — no ledger files (`rsg_*.jsonl`).

**Migration note:** if `security_audit` scanning is ever revived as a real, scheduled
process, these 5 are its documented consumers. Otherwise they are safe candidates for
full removal in a later phase, together with `security_audit` itself.

## Fully isolated modules (4 modules)

No consumer of any kind found — not even a declarative ledger string-key reference or
catalog mention.

- **research_agents** (P11.1) — string-fixture default + declarative ledger refs only; no `ragt_*.jsonl`.
- **research_loop** (C5) — zero hits anywhere outside its own directory; most isolated module found in the full Phase1 audit.
- **research_memory** (P10.14) — zero real imports; distinct from the protected `jarvis.research_memory_intelligence` package (name-collision risk, disambiguated during audit — do not confuse the two). Only static-name mention is a label in the dashboard's `research-os-manifest.json`.
- **research_validation** (P10.9) — zero real imports; fully unrelated to the protected `jarvis.research_workflow` / `research/autoresearch` validation engine (no shared code paths). Evidence alone supports REMOVE; retained per explicit user override.

**Migration note:** no active consumer identified for any of these 4. Re-evaluate for
full removal in a later phase once the "possible future migration" the user cited has
either happened or been ruled out.

## Verification (2026-07-31, post-marker)

- `python3 -c "import jarvis.<module>"` — all 9 import cleanly, no errors.
- `pytest tests/ -q` — 2033 passed (unchanged from pre-archive baseline).
- `registry_hash` — unchanged (`sha1:5069a54942fd5b5f326a6cbd24ad96af3547d504`).
- `governance.validate_all()` — all 5 domains passed.

## Cross-reference

Full evidence trail for these 9 (plus the 37 REMOVE_CANDIDATE and 4 KEEP modules) is in
[`research_namespace_inventory.md`](./research_namespace_inventory.md).
