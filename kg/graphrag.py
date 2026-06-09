"""GraphRAG híbrido (ARCHITECTURE 5). Entrada vectorial → traversal → contexto.

1. La query (des-identificada) se embebe → nodos semilla por similitud sobre las
   descripciones de nodo.
2. Desde las semillas, traversal k-hop por las relaciones de la intención.
3. El subgrafo (nodos + aristas) se serializa compacto, con cita por nodo
   (id + source_path), para pasarlo como contexto al experto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kg.store import Edge, fetch_nodes, induced_edges, reach, traversal_template


def entry_nodes(conn, query: str, k: int = 3) -> list[str]:  # type: ignore[no-untyped-def]
    """Top-k nodos semilla por similitud coseno contra la query des-identificada."""
    from app.db import vector_literal
    from ingest.embed import embed_query

    qv = vector_literal(embed_query(query))
    rows = conn.execute(
        f"SELECT id FROM kg_node WHERE embedding IS NOT NULL "
        f"ORDER BY embedding <=> '{qv}'::vector LIMIT {int(k)}",
        unrestricted=True,
    ).fetchall()
    return [r[0] for r in rows]


@dataclass
class SubGraph:
    seeds: list[str]
    nodes: list[dict[str, Any]]
    edges: list[Edge]
    dropped: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def subgraph(conn, query: str, intencion: str, *, k: int = 3,  # type: ignore[no-untyped-def]
             hops: int | None = None, max_nodes: int = 30, seeds: list[str] | None = None) -> SubGraph:
    template = traversal_template(intencion)
    relaciones = template.get("relaciones", [])
    hop = hops if hops is not None else template.get("hops", 1)
    seed_ids = seeds if seeds is not None else entry_nodes(conn, query, k)

    reached = reach(conn, seed_ids, relaciones, hop)
    # Semillas primero (prioridad de presupuesto), luego el resto del vecindario.
    ordered = list(dict.fromkeys(seed_ids + reached))
    dropped = max(0, len(ordered) - max_nodes)         # presupuesto de contexto (no silent caps)
    node_ids = ordered[:max_nodes]
    nodes = fetch_nodes(conn, node_ids)
    return SubGraph(seeds=seed_ids, nodes=nodes, edges=induced_edges(conn, node_ids, relaciones),
                    dropped=dropped)


def serialize(sg: SubGraph) -> str:
    """Subgrafo → texto compacto con citas (para contexto del experto)."""
    by_id = {n["id"]: n for n in sg.nodes}
    lines = ["# Subgrafo KG"]
    lines.append("\n## Nodos")
    for n in sg.nodes:
        src = f"  [fuente: {n['source_path']}]" if n.get("source_path") else ""
        marca = " (semilla)" if n["id"] in sg.seeds else ""
        lines.append(f"- {n['id']} «{n.get('descripcion','')}»{marca}{src}")
    lines.append("\n## Relaciones")
    for e in sg.edges:
        dst_desc = by_id.get(e.dst, {}).get("descripcion", "")
        lines.append(f"- {e.src} —{e.rel}→ {e.dst}  ({dst_desc[:60]})")
    if sg.dropped:
        lines.append(f"\n(se omitieron {sg.dropped} nodos por presupuesto de contexto)")
    return "\n".join(lines)


if __name__ == "__main__":
    from app.db import connect

    with connect() as c:
        sg = subgraph(c, "¿cuántos días tengo para la evaluación en riesgo?", "consulta_procedimiento")
        print(serialize(sg))
