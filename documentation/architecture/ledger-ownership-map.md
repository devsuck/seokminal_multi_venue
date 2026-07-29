# Ledger Ownership Map

Every persistent ledger is a JSONL file under the shared `_state/` directory, addressed via
`jarvis.config.state_path(filename)`. Each file is owned by exactly one layer, identified by a
unique filename prefix. This map lists the recent layers; the pattern extends to all phases.

## Record shape (all ledgers)

```json
{
  "<id_field>": "TAG:sha1hex12",
  "...domain fields...": "...",
  "input_hash": "sha256:...",
  "previous_hash": "sha256:...  (or GENESIS for the first record)",
  "record_hash": "sha256:..."
}
```

`record_hash = content_hash(record)` where `content_hash` excludes
`{previous_hash, record_hash, report_hash}`. `previous_hash` links each record to its
predecessor, forming a tamper-evident chain.

## Ownership table (recent layers)

| Layer | Prefix | Representative ledgers | ID tags |
|---|---|---|---|
| `autonomous_research_pipeline` (P12.1) | `arp_` | `arp_registry`, `arp_objectives`, `arp_cycles` | pipeline/objective/cycle |
| `research_experience_memory` (P12.7) | `rxm_` | `rxm_memories`, `rxm_experiences`, `rxm_episodes` | memory/experience |
| `research_learning` (P12.8) | `rll_` | `rll_loops`, `rll_observations`, `rll_lessons` | loop/lesson |
| `research_manager` (P12.9) | `rmgr_` | `rmgr_plans`, `rmgr_tasks`, `rmgr_dependencies`, `rmgr_progress`, `rmgr_reports`, `rmgr_artifacts` | `RM*` |
| `research_control` (P12.10) | `rctl_` | `rctl_states`, `rctl_events`, `rctl_health`, `rctl_metrics`, `rctl_alerts`, `rctl_reports`, `rctl_artifacts` | `CT*` |
| `autonomous_research_os` (P13) | `aros_` | `aros_registry`, `aros_episodes`, `aros_snapshots`, `aros_views`, `aros_reports`, `aros_artifacts` | `AO*` |
| `decision_intelligence` | `di_` | `di_candidates`, `di_decision_sessions`, `di_frameworks` | decision |

## Stateless (non-owning) layers

P14 (`benchmark`, `cache`, `concurrency`, `resilience`, `profiling`, `diagnostics`), P15
(`security`, `compliance`, `integrity`, `sbom`, `dependency`, `license`, `threat_model`), and
P16 (`documentation`) are primarily **stateless analysis tools**. They read existing ledgers
and return dataclasses/reports without owning new persistent ledgers. The one exception is the
benchmark history file, which uses the isolated `bench_` prefix.

## Rules

- A prefix is claimed once and never reused by another layer (Phase 0 collision check).
- Ledgers are append-only: no record is ever updated or deleted.
- Cross-layer reads use `SOURCE_LEDGERS` / `SOURCE_LAYERS` maps and are read-only.

See `documentation/architecture/ownership-boundaries.md` for the ownership model and
`documentation/developer_guide/ledger-guide.md` for how to work with ledgers.
