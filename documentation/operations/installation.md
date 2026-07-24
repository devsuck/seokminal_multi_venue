# Installation

This guide sets up the Autonomous Quant Research OS for local research, analysis,
and recording work. The system is research-only: it never trades, places orders,
deploys, or allocates capital.

## Prerequisites

- Python 3.11 (exact minor version; the project targets 3.11 features)
- git
- A POSIX shell (Linux or macOS recommended)

Verify your interpreter before continuing:

```bash
python --version   # expect Python 3.11.x
git --version
```

## Clone the repository

```bash
git clone <your-remote-url> seokminal_multi_venue
cd seokminal_multi_venue
```

The package root is `jarvis/`. Configuration and dependency declarations live in
`pyproject.toml`.

## Create a virtual environment

Always install into an isolated environment to avoid polluting system packages:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## Install with development extras

Runtime dependencies (requests, numpy, scipy, pandas, pydantic, fastapi,
uvicorn, websockets, pdfplumber, python-dotenv, ib_async, nautilus_trader) and
the dev extras (pytest, pytest-asyncio, httpx) install in one step:

```bash
pip install -e '.[dev]'
```

The quotes around `.[dev]` are required in most shells so the brackets are not
interpreted as a glob.

## Verify the installation

Run the full regression suite. A green run confirms the package imports and every
layer behaves deterministically:

```bash
python -m pytest jarvis -q
```

## The `_state/` directory

At runtime, layers write append-only, SHA256 hash-chained JSONL ledgers under a
shared `_state/` directory resolved by `jarvis.config.state_path(name)`. This
directory is ephemeral working data. It is safe to delete between runs and should
not be committed. See `documentation/operations/configuration.md` for how its
location is chosen.
