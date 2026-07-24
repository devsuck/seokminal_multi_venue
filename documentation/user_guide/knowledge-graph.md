# Knowledge Graph

This guide explains how research knowledge and artifact lineage are represented,
traversed, and verified in the Autonomous Quant Research OS. Knowledge is a graph
of nodes and edges; artifacts with parent links form lineage DAGs. Traversal is
deterministic, and lineage is verifiable via `jarvis.integrity`.

## Nodes, edges, and lineage

- A node is a knowledge item or a research artifact (a plan, an experiment
  output, an evaluation verdict).
- An edge connects related nodes; a parent link records provenance.
- Chains of parent links form a lineage DAG that traces every artifact back to
  its origin.

```text
PLAN-1 --produces--> EXPERIMENT-1 --produces--> EVAL-1 --supports--> DECISION-1
   ^                                                                     |
   +--------------------------- lineage ---------------------------------+
```

## 1. Build and inspect the graph

The knowledge layer (`jarvis.research_kg`) is assembled from ledger events, and
`jarvis.autonomous_research_os` exposes read-only knowledge views over it.

```bash
python -m jarvis.autonomous_research_os connect --commit
python -m jarvis.autonomous_research_os view --commit
```

## 2. Deterministic traversal

Traversal visits nodes in a stable, deterministic order, so the same query
always returns the same path. This makes lineage answers reproducible.

```python
# conceptual deterministic traversal
def ancestors(node, edges):
    seen = []
    stack = [node]
    while stack:
        n = stack.pop()
        for parent in sorted(edges.get(n, [])):  # sorted -> deterministic
            if parent not in seen:
                seen.append(parent)
                stack.append(parent)
    return seen
```

## 3. Verify lineage integrity

`jarvis.integrity` checks the lineage DAG for structural defects:

- dangling edges (an edge pointing to a missing node),
- orphan artifacts (a node with no reachable origin),
- cycles (a lineage that loops, which must never happen in a DAG).

```bash
python -m jarvis.autonomous_research_os verify
```

A clean verification means every artifact has intact, acyclic provenance and the
knowledge view can be trusted for audit and reporting.
