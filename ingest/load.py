"""Upsert idempotente del corpus a pgvector (SPEC §6).

Idempotencia por `sha256` del documento: si el contenido no cambió, se salta.
Si cambió, se borran sus chunks y se re-insertan. Registra cada ingest en el
audit (hash-chain) — sin valor real de PII (el corpus es público, sin PII).
"""

from __future__ import annotations

import hashlib

from app.db import vector_literal
from ingest.chunk import chunk_source
from ingest.embed import embed_passages
from ingest.sources import REPO, Source, registry


def _doc_sha(source: Source) -> str:
    return hashlib.sha256(source.path.read_bytes()).hexdigest()


def _upsert_document(conn, source: Source, sha: str) -> tuple[str, bool]:  # type: ignore[no-untyped-def]
    """Devuelve (documento_id, changed)."""
    rel = str(source.path.relative_to(REPO))
    row = conn.execute("SELECT id, sha256 FROM documento WHERE source_path = %s", (rel,)).fetchone()
    if row and row[1] == sha:
        return str(row[0]), False
    if row:
        conn.execute("UPDATE documento SET sha256=%s, flujo=%s, tipo_doc=%s, ingested_at=now() WHERE id=%s",
                     (sha, source.flujo, source.tipo_doc, row[0]))
        conn.execute("DELETE FROM chunk WHERE documento_id=%s", (row[0],))
        return str(row[0]), True
    new = conn.execute(
        "INSERT INTO documento (source_path, flujo, tipo_doc, sha256) VALUES (%s,%s,%s,%s) RETURNING id",
        (rel, source.flujo, source.tipo_doc, sha),
    ).fetchone()
    return str(new[0]), True


def ingest() -> dict[str, int]:
    from app.db import connect
    from app.security.audit import append as audit_append

    counts: dict[str, int] = {}
    with connect() as conn:
        for source in registry():
            sha = _doc_sha(source)
            doc_id, changed = _upsert_document(conn, source, sha)
            if not changed:
                continue
            chunks = chunk_source(source)
            vectors = embed_passages([c.texto for c in chunks])
            for c, vec in zip(chunks, vectors, strict=True):
                conn.execute(
                    "INSERT INTO chunk (documento_id, ord, texto, heading_path, flujo, tipo_doc, "
                    "etapa, codigo_artefacto, articulo, embedding) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                    (doc_id, c.ord, c.texto, c.heading_path, source.flujo, source.tipo_doc,
                     c.etapa, c.codigo_artefacto, c.articulo, vector_literal(vec)),
                )
            counts[source.flujo or "comun"] = counts.get(source.flujo or "comun", 0) + len(chunks)
            audit_append(conn, actor_id="ingest", accion="ingest", entidad="documento",
                         entidad_id=str(source.path.name), meta={"sha256": sha, "chunks": len(chunks)})
        conn.commit()
    return counts


if __name__ == "__main__":
    result = ingest()
    if not result:
        print("✓ ingest: corpus ya actualizado (sin cambios por sha256)")
    else:
        for flujo, n in sorted(result.items()):
            print(f"  {flujo:6} {n} chunks")
        print(f"✓ ingest: {sum(result.values())} chunks (re)insertados")
