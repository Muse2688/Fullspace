"""Neo4j lineage export — answer "how is this system actually used".

The manifold decides *where* routing goes; a graph database is the natural
place to record *what actually happened* and analyze it afterwards. This
module exports a run's trajectory into Neo4j as:

    (:Run {id})-[:VISITED {step}]->(:Capability {id})
    (:Capability)-[:NEXT {run, step}]->(:Capability)     # consecutive hops
    (:Run)-[:ENDED_BY {reason}]->(:Capability)           # last capability

Once there, Cypher answers the observability questions directly — which
capabilities co-activate, which transitions dominate, which runs looped:

    // top transitions across all runs
    MATCH (a:Capability)-[n:NEXT]->(b:Capability)
    RETURN a.id, b.id, count(n) AS freq ORDER BY freq DESC LIMIT 10;

    // runs that hit the reteach loop
    MATCH (r:Run)-[:VISITED]->(c:Capability {id: 'teach'})
    WHERE (c)-[:NEXT*0..2]->(c) RETURN r.id;
"""

from __future__ import annotations

import uuid
from typing import Any, Optional


def export_trajectory_to_neo4j(
    trajectory: list[str],
    *,
    run_id: Optional[str] = None,
    step_groups: Optional[list[list[str]]] = None,
    terminated_by: Optional[str] = None,
    driver: Any = None,
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "password",
    label: str = "Capability",
) -> str:
    """Write one run's trajectory into Neo4j; returns the ``run_id`` used.

    Args:
        trajectory: flat list of visited capability ids, in order.
        run_id: stable identifier for the run (default: a fresh uuid4 hex).
        step_groups: per-step activation groups; when given, ``VISITED`` edges
            carry the group's step index and intra-group hops are recorded
            as ``NEXT`` transitions too (field/wavefront flows).
        terminated_by: run's termination reason (``ENDED_BY.reason``).
        driver: an existing ``neo4j.GraphDatabase`` driver (overrides uri/auth).
        uri / user / password: Neo4j connection when ``driver`` is not given.
        label: node label capabilities are stored under (should match
            ``Neo4jVectorIndex``'s if you also use it as your index).
    """
    if driver is None:
        from neo4j import GraphDatabase  # type: ignore

        driver = GraphDatabase.driver(uri, auth=(user, password))
    run_id = run_id or uuid.uuid4().hex

    hops: list[tuple[str, str, int]] = []  # (from, to, step)
    if step_groups:
        for i, group in enumerate(step_groups):
            for a, b in zip(group, group[1:]):        # intra-group transitions
                hops.append((a, b, i))
            if i + 1 < len(step_groups):              # group -> next group's head
                hops.append((group[-1], step_groups[i + 1][0], i))
    else:
        hops = [(a, b, i) for i, (a, b) in enumerate(zip(trajectory, trajectory[1:]))]

    def _tx(tx):
        tx.run(f"MERGE (r:Run {{id: $rid}})", rid=run_id)
        for cid in dict.fromkeys(trajectory):          # unique, order-preserving
            tx.run(f"MERGE (c:{label} {{id: $cid}})", cid=cid)
        for i, cid in enumerate(trajectory):
            tx.run(
                f"MATCH (r:Run {{id: $rid}}), (c:{label} {{id: $cid}})"
                " MERGE (r)-[v:VISITED {{seq: $seq}}]->(c)"
                " ON CREATE SET v.step = $step",
                rid=run_id, cid=cid, seq=i, step=i,
            )
        for a, b, step in hops:
            tx.run(
                f"MATCH (a:{label} {{id: $a}}), (b:{label} {{id: $b}})"
                " CREATE (a)-[:NEXT {run: $rid, step: $step}]->(b)",
                rid=run_id, a=a, b=b, step=step,
            )
        if trajectory and terminated_by:
            tx.run(
                f"MATCH (r:Run {{id: $rid}}), (c:{label} {{id: $cid}})"
                " CREATE (r)-[:ENDED_BY {reason: $reason}]->(c)",
                rid=run_id, cid=trajectory[-1], reason=terminated_by,
            )

    with driver.session() as s:
        s.execute_write(_tx)
    return run_id
