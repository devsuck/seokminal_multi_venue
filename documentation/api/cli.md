# CLI Command Catalog

89 of the 110 public layers ship a command-line interface via a `__main__.py`, invoked as
`python -m jarvis.<layer> <command>`. The full, always-current list is produced by:

```bash
python -m jarvis.documentation cli
```

## Common command conventions

- **Dry-run by default.** Mutating commands take `--commit` to persist; without it, the command
  computes and prints the record but writes nothing.
- **Verification commands** are read-only: `verify` (chain/lifecycle/lineage), `replay`
  (determinism), `summary` (counts).
- **JSON output.** Commands print indented JSON for easy piping.

## Representative CLIs

```bash
# Research manager (P12.9): plan lifecycle
python -m jarvis.research_manager plan --name momentum-study --objective "test" --commit
python -m jarvis.research_manager task --plan <PLAN_ID> --name collect-data --commit
python -m jarvis.research_manager progress --task <TASK_ID> --percent 50 --commit
python -m jarvis.research_manager report --plan <PLAN_ID>        # is_binding=False
python -m jarvis.research_manager verify
python -m jarvis.research_manager replay

# Research control plane (P12.10): observe / health / anomaly (record-only)
python -m jarvis.research_control init --name pipeline --commit
python -m jarvis.research_control health --state <STATE_ID> --score 0.4 --commit
python -m jarvis.research_control anomaly --state <STATE_ID> --commit   # is_actionable=False

# Autonomous Research OS (P13): READ-ONLY integration
python -m jarvis.autonomous_research_os init --commit
python -m jarvis.autonomous_research_os connect --os <OS_ID> --commit
python -m jarvis.autonomous_research_os observe --os <OS_ID> --layer research_manager --commit
python -m jarvis.autonomous_research_os snapshot --os <OS_ID> --commit
python -m jarvis.autonomous_research_os verify

# Documentation (P16)
python -m jarvis.documentation gen        # regenerate API reference
python -m jarvis.documentation validate   # validate the documentation tree
python -m jarvis.documentation cli        # list CLI-bearing packages
python -m jarvis.documentation packages   # list all public packages
```

## Safety

No CLI can trade, place orders, deploy, allocate capital, promote a model, or mutate
permissions. Commands only record research/analysis or verify existing records. See
`documentation/api/configuration.md` for the autonomy gate.
