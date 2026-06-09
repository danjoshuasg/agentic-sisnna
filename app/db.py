"""Capa DB — cliente REST de Insforge (PostgREST + rawsql).

Insforge expone Postgres vía REST (no connection string directa). pgvector 0.7.4
disponible (se habilita en migrate). Este módulo da un shim estilo-psycopg
(`conn.execute(sql, params).fetchone()/.fetchall()`) sobre `POST
/api/database/advance/rawsql`, para que audit.py/load.py usen la misma interfaz.

Conversión: placeholders psycopg `%s` → pg `$1,$2,...`. Casts de tipo
(`%s::jsonb`, `%s::vector`) se escriben inline en el SQL y sobreviven la conversión.
`vector_literal()` serializa un embedding a literal pgvector.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.getenv("INSFORGE_BASE_URL", "").rstrip("/")
API_KEY = os.getenv("INSFORGE_API_KEY", "")
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

_PLACEHOLDER = re.compile(r"%s")


def _to_pg_params(sql: str) -> str:
    """`%s` secuenciales → `$1,$2,...` (preserva `%s::jsonb` → `$1::jsonb`)."""
    counter = iter(range(1, 10_000))
    return _PLACEHOLDER.sub(lambda _: f"${next(counter)}", sql)


def vector_literal(vec: list[float]) -> str:
    """Embedding → literal pgvector. Usar con cast `%s::vector`."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


class _Cursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple]:
        return self._rows


class InsforgeConn:
    """Shim de conexión. Cada execute() es un statement atómico (sin transacción
    multi-statement); suficiente para el PoC mono-actor."""

    def __init__(self) -> None:
        if not BASE_URL or not API_KEY:
            raise RuntimeError("Faltan INSFORGE_BASE_URL / INSFORGE_API_KEY en .env")
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            timeout=60,
        )

    def execute(self, sql: str, params: tuple | list = (), *, unrestricted: bool = False) -> _Cursor:
        query = _to_pg_params(sql)
        endpoint = "/api/database/advance/rawsql" + ("/unrestricted" if unrestricted else "")
        resp = self._client.post(endpoint, json={"query": query, "params": list(params)})
        if resp.status_code >= 400:
            raise RuntimeError(f"rawsql {resp.status_code}: {resp.text[:400]}\nSQL: {query[:200]}")
        data = resp.json()
        rows = [tuple(r.values()) for r in data.get("rows", [])]  # orden = orden del SELECT
        return _Cursor(rows)

    def commit(self) -> None:  # autocommit por statement; no-op
        pass

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> InsforgeConn:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def connect() -> InsforgeConn:
    return InsforgeConn()


def migrate() -> None:
    sqls = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sqls:
        raise FileNotFoundError(f"Sin migraciones en {MIGRATIONS_DIR}")
    with connect() as conn:
        for path in sqls:
            print(f"→ aplicando {path.name}")
            # DDL (CREATE EXTENSION/TABLE) requiere modo unrestricted en Insforge.
            conn.execute(path.read_text(encoding="utf-8"), unrestricted=True)
    print(f"✓ {len(sqls)} migración(es) aplicada(s)")


def list_tables() -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY table_name",
            unrestricted=True,
        ).fetchall()
    return [r[0] for r in rows]


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "migrate"
    if cmd == "migrate":
        migrate()
        print("tablas:", ", ".join(list_tables()))
    elif cmd == "tables":
        print("\n".join(list_tables()))
    else:
        print(f"comando desconocido: {cmd}", file=sys.stderr)
        sys.exit(2)
