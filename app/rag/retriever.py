"""Retriever vectorial — tool `vector_search` (ARCHITECTURE §2). top-k + filtros.

Recupera chunks del corpus por similitud coseno (pgvector) con filtros opcionales
de metadatos (flujo, tipo_doc). Devuelve cada chunk con su `source_path` y
`heading_path` para que el experto cite la fuente (citar-o-rehusar).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Hit:
    texto: str
    source_path: str
    heading_path: str | None
    etapa: str | None
    codigo: str | None
    articulo: str | None
    score: float


def vector_search(conn, query: str, *, k: int = 6, flujo: str | list[str] | None = None,  # type: ignore[no-untyped-def]
                  tipo_doc: str | list[str] | None = None) -> list[Hit]:
    from app.db import vector_literal
    from ingest.embed import embed_query

    qv = vector_literal(embed_query(query))
    where, params = [], []

    def _filtro(col: str, val: str | list[str] | None) -> None:
        if val is None:
            return
        vals = [val] if isinstance(val, str) else val
        where.append(f"c.{col} = ANY(ARRAY[{','.join('%s' for _ in vals)}])")
        params.extend(vals)

    _filtro("flujo", flujo)
    _filtro("tipo_doc", tipo_doc)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = conn.execute(
        f"SELECT c.texto, d.source_path, c.heading_path, c.etapa, c.codigo_artefacto, c.articulo, "
        f"1 - (c.embedding <=> '{qv}'::vector) AS score "
        f"FROM chunk c JOIN documento d ON d.id = c.documento_id "
        f"{where_sql} ORDER BY c.embedding <=> '{qv}'::vector LIMIT {int(k)}",
        tuple(params), unrestricted=True,
    ).fetchall()
    return [Hit(r[0], r[1], r[2], r[3], r[4], r[5], float(r[6])) for r in rows]
