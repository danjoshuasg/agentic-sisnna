"""Tests del primitivo audit hash-chain (SPEC §7.2) con conn en memoria."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.security import audit


class _Result:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple]:
        return self._rows


class FakeConn:
    """Emula lo justo que usa audit.py: SELECT last hash, INSERT, SELECT all."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._id = 0

    def execute(self, sql: str, params: tuple = ()) -> _Result:
        s = " ".join(sql.split())
        if s.startswith("SELECT hash FROM access_log ORDER BY id DESC"):
            return _Result([(self.rows[-1]["hash"],)] if self.rows else [])
        if s.startswith("INSERT INTO access_log"):
            actor, accion, entidad, entidad_id, meta, hash_prev, h = params
            self._id += 1
            self.rows.append({"id": self._id, "actor_id": actor, "accion": accion, "entidad": entidad,
                              "entidad_id": entidad_id, "meta": json.loads(meta), "hash_prev": hash_prev, "hash": h})
            return _Result([])
        if s.startswith("SELECT id, actor_id"):
            return _Result([(r["id"], r["actor_id"], r["accion"], r["entidad"], r["entidad_id"],
                             r["meta"], r["hash_prev"], r["hash"]) for r in self.rows])
        raise AssertionError(f"SQL no emulado: {s}")


def test_chain_grows_and_verifies() -> None:
    conn = FakeConn()
    audit.append(conn, actor_id="ingest", accion="ingest", entidad="documento", entidad_id="flujo.md",
                 meta={"chunks": 14})
    audit.append(conn, actor_id="op1", accion="ver", entidad="chunk", entidad_id="c1")
    ok, broken = audit.verify_chain(conn)
    assert ok and broken is None
    assert conn.rows[0]["hash_prev"] is None          # génesis
    assert conn.rows[1]["hash_prev"] == conn.rows[0]["hash"]


def test_tamper_detected() -> None:
    conn = FakeConn()
    audit.append(conn, actor_id="ingest", accion="ingest", entidad_id="a")
    audit.append(conn, actor_id="ingest", accion="ingest", entidad_id="b")
    conn.rows[0]["entidad_id"] = "MODIFICADO"          # romper un eslabón
    ok, broken = audit.verify_chain(conn)
    assert not ok and broken == 1


def test_accion_invalida_rechazada() -> None:
    conn = FakeConn()
    with pytest.raises(ValueError):
        audit.append(conn, actor_id="x", accion="borrar_todo")


def test_no_pii_en_meta() -> None:
    """El audit nunca debe recibir el valor real; meta lleva solo conteos/refs."""
    conn = FakeConn()
    audit.append(conn, actor_id="ingest", accion="ingest", entidad_id="flujo.md", meta={"sha256": "abc", "chunks": 14})
    assert "relato" not in json.dumps(conn.rows[0]["meta"])
