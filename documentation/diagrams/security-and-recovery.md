# Diagram — Security Model & Recovery Flow

## Security model (P15, read-only)

```mermaid
flowchart TB
  SRC["source code / docs"] --> SECRET["security.secrets<br/>secret scanner (masked)"]
  SRC --> STATIC["security.static<br/>AST: eval/exec/pickle/subprocess/os.system"]
  DEPS["pyproject.toml"] --> DEP["dependency audit"]
  DEP --> SBOM["sbom.generate + verify"]
  DEP --> LIC["license inventory + compatibility"]
  LEDG["ledgers / artifacts"] --> INT["integrity.verify_ledger + artifact checks"]
  SECRET --> REP["deterministic reports"]
  STATIC --> REP
  SBOM --> REP
  LIC --> REP
  INT --> REP
  REP --> COMP["compliance checklists"]
  REP --> TM["threat_model risk matrix"]
```

## Recovery flow (P14 resilience, originals immutable)

```mermaid
flowchart LR
  L["ledger file"] --> SCAN["scan_ledger<br/>find first corruption"]
  SCAN --> PR["partial_replay<br/>valid prefix"]
  PR --> CP["recover_to_copy(src → NEW dst)"]
  CP -->|refuses overwrite / same-path| SAFE["source unchanged"]
  SCAN --> DIAG["diagnose_corruption"]
  CP --> VERIFY["scan recovered copy → intact"]
```

## Notes

All security and recovery tools are read-only over the data they inspect; recovery writes only
to a new file. See `documentation/adr/0009-security-architecture.md` and
`documentation/architecture/read-only-boundaries.md`.
