"""Tests de la bóveda PII (SPEC §7.1): cifrado reversible + re-hidratación."""

from __future__ import annotations

from app.security import vault


class _Result:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None


class FakeConn:
    """Emula token_vault en memoria (INSERT ON CONFLICT, SELECT por token)."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, str, str]] = {}  # token -> (cifrado, tipo, req)

    def execute(self, sql: str, params: tuple = ()) -> _Result:
        s = " ".join(sql.split())
        if s.startswith("INSERT INTO token_vault"):
            token, cifrado, tipo, req = params
            self.store.setdefault(token, (cifrado, tipo, req))  # ON CONFLICT DO NOTHING
            return _Result([])
        if s.startswith("SELECT valor_cifrado FROM token_vault WHERE token"):
            (token,) = params
            return _Result([(self.store[token][0],)] if token in self.store else [])
        raise AssertionError(f"SQL no emulado: {s}")


def test_encrypt_decrypt_round_trip() -> None:
    blob = vault.encrypt("Lucía Ramos")
    assert vault.decrypt(blob) == "Lucía Ramos"
    assert b"Luc" not in blob and "Lucía" not in blob.decode("ascii")  # cifrado, no claro


def test_store_and_get() -> None:
    conn = FakeConn()
    vault.store_token(conn, "[NOMBRE_1]", "Carmen Huamán", "NOMBRE", "req1")
    assert vault.get_value(conn, "[NOMBRE_1]") == "Carmen Huamán"
    assert vault.get_value(conn, "[DNI_9]") is None


def test_store_idempotente() -> None:
    conn = FakeConn()
    vault.store_token(conn, "[DNI_1]", "70845123", "DNI", "req1")
    vault.store_token(conn, "[DNI_1]", "OTRO", "DNI", "req1")  # ON CONFLICT: no pisa
    assert vault.get_value(conn, "[DNI_1]") == "70845123"


def test_rehydrate() -> None:
    conn = FakeConn()
    vault.store_token(conn, "[NOMBRE_1]", "Sofía Vargas", "NOMBRE", "r")
    vault.store_token(conn, "[EDAD_1]", "6 años", "EDAD", "r")
    texto = "La niña [NOMBRE_1] de [EDAD_1] fue derivada."
    assert vault.rehydrate(conn, texto) == "La niña Sofía Vargas de 6 años fue derivada."


def test_rehydrate_token_desconocido_se_conserva() -> None:
    conn = FakeConn()
    assert vault.rehydrate(conn, "texto con [NOMBRE_9] huérfano") == "texto con [NOMBRE_9] huérfano"
