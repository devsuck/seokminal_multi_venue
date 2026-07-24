# Getting Started

This guide walks a new developer from a clean checkout to a green test suite for
the Autonomous Quant Research OS. The project is an **additive, read-only research
and recording layer** built on top of an execution-capable trading platform. It
never trades, orders, deploys, allocates capital, promotes models, or mutates
permissions — it only observes, analyzes, and records.

## Prerequisites

- Python 3.11 (exact minor version; the codebase targets 3.11 features).
- A POSIX shell (`bash` / `zsh`). Windows users should use WSL2.
- `git` and `pip`.

## Clone and enter the repository

```bash
git clone <your-fork-or-origin-url> seokminal_multi_venue
cd seokminal_multi_venue
```

## Create a virtual environment and install dev dependencies

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

The editable install exposes the `jarvis/` package (111 subpackages, one per
research layer) plus the pytest-based test toolchain.

## Run the full test suite

```bash
python -m pytest jarvis -q
```

A clean checkout should be fully green. Tests are hermetic: they monkeypatch the
per-layer `state_path` to an isolated temp directory, so the shared `_state/`
ledger directory on disk is never touched by a test run.

## Run a layer CLI

Many layers ship a `__main__.py` and can be invoked directly. For example:

```bash
python -m jarvis.autonomous_research_os --help
python -m jarvis.autonomous_research_pipeline replay
```

## Validate the documentation

Documentation is machine-checked. Before committing any doc change run:

```bash
python -m jarvis.documentation validate
python -m jarvis.documentation gen
```

`validate` enforces the H1-first rule, balanced code fences, and the no-relative-link
policy. `gen` regenerates derived API docs from the layer manifests.

## Next steps

- Read `documentation/developer_guide/repository-structure.md` to learn the layout.
- Read `documentation/developer_guide/coding-standards.md` before writing code.
- Read `documentation/developer_guide/testing-guide.md` before adding tests.
