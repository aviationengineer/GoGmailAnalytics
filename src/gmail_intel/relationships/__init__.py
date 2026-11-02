"""Network analysis: relationship graph over people and organizations.

Nodes: people, organizations. Edges: communicated_with (weighted by
message count), works_at (person -> organization by email domain).
Metrics: degree centrality, most-connected, bridges (betweenness).
"""
from __future__ import annotations

import logging
from collections import defaultdict

log = logging.getLogger("gmail-intel.relationships")

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False


def build_graph(contacts: list[dict], orgs: list[dict]) -> dict:
    """Return a serializable graph summary; full nx graph when available."""
    org_by_domain = {o["domain"]: o["organization_id"] for o in orgs}
    edges = []
    for c in contacts:
        for em in [c["primary_email"]] + c.get("alternate_emails", []):
            domain = em.split("@", 1)[1] if "@" in em else ""
            oid = org_by_domain.get(domain)
            if oid:
                edges.append((c["contact_id"], oid, "works_at", 1))
    summary: dict = {
        "people": len(contacts),
        "organizations": len(orgs),
        "edges": len(edges),
        "most_connected": [],
        "bridges": [],
    }
    if not HAS_NX:
        log.warning("networkx not installed; returning summary only")
        return summary
    g = nx.Graph()
    for c in contacts:
        g.add_node(c["contact_id"], kind="person", name=c["full_name"])
    for o in orgs:
        g.add_node(o["organization_id"], kind="org", name=o["organization_name"])
    for a, b, kind, w in edges:
        g.add_edge(a, b, kind=kind, weight=w)
    if len(g):
        deg = nx.degree_centrality(g)
        top = sorted(deg.items(), key=lambda kv: kv[1], reverse=True)[:10]
        summary["most_connected"] = [
            {"node": n, "label": g.nodes[n].get("name", n), "centrality": round(s, 4)}
            for n, s in top]
        try:
            btw = nx.betweenness_centrality(g, k=min(200, len(g)))
            bridges = sorted(btw.items(), key=lambda kv: kv[1], reverse=True)[:5]
            summary["bridges"] = [
                {"node": n, "label": g.nodes[n].get("name", n),
                 "betweenness": round(s, 4)} for n, s in bridges if s > 0]
        except Exception as exc:  # pragma: no cover
            log.warning("betweenness failed: %s", exc)
    return summary
