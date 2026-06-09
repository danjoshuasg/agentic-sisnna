"""Store del Knowledge Graph — kg_node / kg_edge + traversal CTE (ARCHITECTURE §5).

Carga kg/instances.yaml (validado contra kg/ontology.yaml), embebe la descripción
de cada nodo (entrada GraphRAG) y persiste en Insforge. Traversal = CTE recursivo
k-hop sobre kg_edge, siguiendo el conjunto de relaciones de la intención del router.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

KG_DIR = Path(__file__).resolve().parent
REPO = KG_DIR.parent
ONTOLOGY_PATH = KG_DIR / "ontology.yaml"
INSTANCES_PATH = KG_DIR / "instances.yaml"


# --- Ontología -------------------------------------------------------------
def load_ontology(path: Path = ONTOLOGY_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def traversal_template(intencion: str) -> dict[str, Any]:
    """Relaciones + hops a seguir según la intención (context-skill, §6)."""
    trav = load_ontology().get("traversal", {})
    return trav.get(intencion, {"relaciones": [], "hops": 1})


# --- Validación + carga ----------------------------------------------------
def validate_instances(instances: dict[str, Any], ontology: dict[str, Any]) -> list[str]:
    node_types = set(ontology["nodos"])
    edge_rels = set(ontology["aristas"])
    node_ids = {n["id"] for n in instances["nodos"]}
    errors: list[str] = []
    for n in instances["nodos"]:
        if n["tipo"] not in node_types:
            errors.append(f"nodo {n['id']}: tipo '{n['tipo']}' no está en la ontología")
    for e in instances["aristas"]:
        if e["rel"] not in edge_rels:
            errors.append(f"arista {e['de']}->{e['a']}: rel '{e['rel']}' no está en la ontología")
        if e["de"] not in node_ids:
            errors.append(f"arista rel={e['rel']}: nodo origen '{e['de']}' inexistente")
        if e["a"] not in node_ids:
            errors.append(f"arista rel={e['rel']}: nodo destino '{e['a']}' inexistente")
    return errors


def load_instances(conn, path: Path = INSTANCES_PATH, *, embed: bool = True) -> dict[str, int]:  # type: ignore[no-untyped-def]
    from app.db import vector_literal

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    ontology = load_ontology()
    errors = validate_instances(data, ontology)
    if errors:
        raise ValueError("instances.yaml inválido:\n" + "\n".join(f"  - {e}" for e in errors))

    nodos = data["nodos"]
    default_src = data.get("source_default")
    embeddings: list[list[float] | None] = [None] * len(nodos)
    if embed:
        from ingest.embed import embed_passages

        embeddings = embed_passages([n.get("descripcion", "") for n in nodos])  # type: ignore[assignment]

    for n, vec in zip(nodos, embeddings, strict=True):
        emb_sql, params_tail = ("%s::vector", [vector_literal(vec)]) if vec is not None else ("NULL", [])
        conn.execute(
            f"INSERT INTO kg_node (id, tipo, datos, descripcion, source_path, embedding) "
            f"VALUES (%s,%s,%s::jsonb,%s,%s,{emb_sql}) "
            f"ON CONFLICT (id) DO UPDATE SET tipo=EXCLUDED.tipo, datos=EXCLUDED.datos, "
            f"descripcion=EXCLUDED.descripcion, source_path=EXCLUDED.source_path, embedding=EXCLUDED.embedding",
            (n["id"], n["tipo"], json.dumps(n.get("datos", {})), n.get("descripcion"),
             n.get("source_path", default_src), *params_tail),
        )
    for e in data["aristas"]:
        conn.execute(
            "INSERT INTO kg_edge (src, dst, rel) VALUES (%s,%s,%s) ON CONFLICT (src,dst,rel) DO NOTHING",
            (e["de"], e["a"], e["rel"]),
        )
    return {"nodos": len(nodos), "aristas": len(data["aristas"])}


# --- Traversal -------------------------------------------------------------
def _sql_list(values: list[str]) -> str:
    return ",".join("'" + v.replace("'", "''") + "'" for v in values)


@dataclass
class Edge:
    src: str
    dst: str
    rel: str


def reach(conn, seeds: list[str], relaciones: list[str], hops: int) -> list[str]:  # type: ignore[no-untyped-def]
    """Nodos alcanzables k-hop desde `seeds` por `relaciones`, **no-dirigido**
    (sigue aristas en ambos sentidos: el vecindario de un plazo incluye su etapa).
    Incluye las semillas. CTE recursivo con guardia de ciclos."""
    if not seeds:
        return []
    if not relaciones:
        return list(dict.fromkeys(seeds))
    seeds_vals = ",".join("('" + s.replace("'", "''") + "')" for s in seeds)
    rels_sql = _sql_list(relaciones)
    sql = f"""
    WITH RECURSIVE r(node, depth, path) AS (
      SELECT s, 0, ARRAY[s] FROM (VALUES {seeds_vals}) AS t(s)
      UNION ALL
      SELECT nb.node, r.depth + 1, r.path || nb.node
      FROM r JOIN LATERAL (
        SELECT e.dst AS node FROM kg_edge e WHERE e.src = r.node AND e.rel IN ({rels_sql})
        UNION
        SELECT e.src AS node FROM kg_edge e WHERE e.dst = r.node AND e.rel IN ({rels_sql})
      ) nb ON true
      WHERE r.depth < {int(hops)} AND NOT nb.node = ANY(r.path)
    )
    SELECT DISTINCT node FROM r
    """
    rows = conn.execute(sql, unrestricted=True).fetchall()
    return [row[0] for row in rows]


def induced_edges(conn, node_ids: list[str], relaciones: list[str]) -> list[Edge]:  # type: ignore[no-untyped-def]
    """Aristas (de `relaciones`) cuyos dos extremos están en `node_ids`."""
    if not node_ids or not relaciones:
        return []
    ids_sql, rels_sql = _sql_list(node_ids), _sql_list(relaciones)
    rows = conn.execute(
        f"SELECT src, dst, rel FROM kg_edge "
        f"WHERE src IN ({ids_sql}) AND dst IN ({ids_sql}) AND rel IN ({rels_sql}) ORDER BY rel, src",
        unrestricted=True,
    ).fetchall()
    return [Edge(r[0], r[1], r[2]) for r in rows]


def fetch_nodes(conn, ids: list[str]) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    if not ids:
        return []
    rows = conn.execute(
        f"SELECT id, tipo, datos, descripcion, source_path FROM kg_node WHERE id IN ({_sql_list(ids)})",
        unrestricted=True,
    ).fetchall()
    return [{"id": r[0], "tipo": r[1], "datos": r[2], "descripcion": r[3], "source_path": r[4]} for r in rows]


if __name__ == "__main__":
    from app.db import connect

    with connect() as c:
        counts = load_instances(c)
    print(f"✓ KG cargado: {counts['nodos']} nodos, {counts['aristas']} aristas")
