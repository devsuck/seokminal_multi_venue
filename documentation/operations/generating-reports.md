# Generating Reports

The research OS emits several kinds of reports. Every report is non-binding
(`is_binding=False`): a VALIDATED report documents analysis, it never authorizes
a trade, deployment, or allocation.

## Layer report records

Each layer records its findings as append-only JSONL entries in a SHA256
hash-chained ledger under `_state/`, resolved via `jarvis.config.state_path`.
Records are produced as a side effect of running a layer's normal commands
(plan, verify, replay, summary). For example:

```bash
python -m jarvis.research_manager summary
```

## Security and compliance reports (P15)

Source and file scanning:

```python
from jarvis.security import scan_files, scan_source
findings = scan_source(open('jarvis/config.py').read())
```

Dependency and SBOM reporting:

```python
from jarvis.dependency import scan_dependencies, build_report
from jarvis.sbom import sbom_from_dependencies, verify_sbom

deps = scan_dependencies()
report = build_report(deps)
sbom = sbom_from_dependencies(deps)
assert verify_sbom(sbom) is True
```

License inventory, threat model, and compliance:

```python
from jarvis.license import build_inventory
from jarvis.threat_model import build_threat_model
from jarvis.compliance import run_compliance

inventory = build_inventory()
threats = build_threat_model()
result = run_compliance()
```

Ledger integrity underpins all of the above:

```python
from jarvis.integrity import verify_ledger
```

## API reference documentation (P16)

Regenerate the API reference and validate the docs tree:

```bash
python -m jarvis.documentation gen
python -m jarvis.documentation validate
```

`gen` rewrites the generated reference from source. `validate` enforces the
documentation format rules (single H1 first line, balanced code fences, no
relative cross-file links). Run both before publishing; the ordered release flow
is in `documentation/operations/validation-workflow.md`.
