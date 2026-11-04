"""Reference-group graph: Watts-Strogatz small world (k=6, p=0.1), seeded (plan: "Agents").

Neighbours on this graph are the reference group for every mechanism. `connected_watts_strogatz_graph` needs
n > k; for tiny populations (tests) the graph degrades to a complete graph, and a report warning says so.
"""
from __future__ import annotations

import networkx as nx

DEFAULT_K = 6
DEFAULT_P = 0.1


def small_world(n: int, seed: int, k: int = DEFAULT_K, p: float = DEFAULT_P) -> tuple[nx.Graph, str | None]:
    """(graph on nodes 0..n-1, warning or None)."""
    if n <= 0:
        return nx.Graph(), "empty population"
    if n <= k:
        return nx.complete_graph(n), f"population {n} <= k={k}: using a complete graph instead of Watts-Strogatz"
    return nx.connected_watts_strogatz_graph(n, k, p, seed=seed), None
