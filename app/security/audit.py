"""Audit append-only con hash-chain (SPEC 7.2). Primitivo tamper-evident.

Cada registro: hash = sha256(hash_prev || canonical(campos)). Romper un eslabón
se detecta al re-verificar la cadena. NUNCA se loggea el valor real de PII
(SPEC 11): `meta` lleva conteos/tokens/modelo, jamás el relato.

Slice 0 lo usa para ingest. Slice 1 añade acciones ver/des_identificar/
re_hidratar/egreso_llm/deteccion_pii sobre este mismo primitivo.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

ACCIONES = {
    "ingest", "route", "ver", "des_identificar", "re_hidratar", "egreso_llm", "deteccion_pii",
}


def _row_hash(hash_prev: str, actor_id: str, accion: str, entidad: str | None,
              entidad_id: str | None, meta: dict[str, Any] | None) -> str:
    payload = json.dumps(
        {"prev": hash_prev, "actor": actor_id, "accion": accion, "entidad": entidad,
         "entidad_id": entidad_id, "meta": meta or {}},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _last_hash(conn) -> str:  # type: ignore[no-untyped-def]
    row = conn.execute("SELECT hash FROM access_log ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else ""  # génesis = cadena vacía


def append(conn, *, actor_id: str, accion: str, entidad: str | None = None,  # type: ignore[no-untyped-def]
           entidad_id: str | None = None, meta: dict[str, Any] | None = None) -> str:
    if accion not in ACCIONES:
        raise ValueError(f"acción no permitida: {accion}")
    prev = _last_hash(conn)
    h = _row_hash(prev, actor_id, accion, entidad, entidad_id, meta)
    conn.execute(
        "INSERT INTO access_log (actor_id, accion, entidad, entidad_id, meta, hash_prev, hash) "
        "VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)",
        (actor_id, accion, entidad, entidad_id, json.dumps(meta or {}), prev or None, h),
    )
    return h


def verify_chain(conn) -> tuple[bool, int | None]:  # type: ignore[no-untyped-def]
    """Recalcula la cadena. Devuelve (íntegra, id_del_primer_eslabón_roto)."""
    rows = conn.execute(
        "SELECT id, actor_id, accion, entidad, entidad_id, meta, hash_prev, hash "
        "FROM access_log ORDER BY id ASC"
    ).fetchall()
    prev = ""
    for r in rows:
        rid, actor, accion, entidad, entidad_id, meta, hash_prev, h = r
        if (hash_prev or "") != prev:
            return False, rid
        expected = _row_hash(prev, actor, accion, entidad, entidad_id, meta)
        if expected != h:
            return False, rid
        prev = h
    return True, None
