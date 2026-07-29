# Unified Data Provider Interface (P112)

> Integration only — a thin abstraction that normalizes different APIs. **Read-only, credential-free.**
> **Vendor logic stays outside the Provider (existing Layer A clients). No duplicate providers.**

## What it does — `jarvis/research_workflow/providers.py`
A common `Provider` protocol with four methods:

`fetch() · normalize() · validate() · health_check()`

`fetch(raw=None)` accepts already-fetched raw records (dependency injection) — `jarvis/` never calls a
vendor API, so it stays credential-free; the real fetch is done by the existing Layer A clients.
`normalize()` routes each raw record into the existing P96–101 adapters; `validate()` checks the
normalized shape; `health_check()` reports availability from env-var presence (no network call).

Concrete providers, each delegating normalization to an existing adapter:

| Provider | Category | Normalizes via |
|---|---|---|
| `MarketProvider` | market | `market_data_adapter.normalize` (P96) |
| `NewsProvider` | news | `news_intelligence.analyze_headline` (P97) |
| `FundamentalProvider` | fundamental/earnings | `earnings_intelligence.analyze_earnings` (P100) |
| `InsiderProvider` | insider/ownership | `insider_flow.analyze_transaction` (P98) |
| `MacroProvider` | macro | `event_stream.classify_event` (P86) |

`PROVIDER_CATALOG` encodes the P111 audit (19 providers) as static reference data; `provider_registry()`
returns it with per-provider availability + the `MISSING_INTEGRATIONS` gaps.

## Reuse & no-duplication
Reuses the existing Layer A vendor clients (KIS/IB/KRX/Finnhub/SEC/OpenDART/FRED/ECOS/…) and the P96–101
adapters. No new provider class hierarchy replacing `MarketDataProvider`; no vendor imports inside `jarvis/`;
no new store/ledger.

## Governance
Every payload `is_advisory=True`, `is_decision=False`. No `execute/trade/broker/order`.

## Validation
`test_integration_p111_120.py`: catalog ≥15 providers, the four-method interface, normalization routes to
existing adapters, health check shape.

## Files
`jarvis/research_workflow/providers.py`, `console_api.py` (`/console/data-capability-map`), this doc.
