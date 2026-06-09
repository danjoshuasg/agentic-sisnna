"""Bóveda de tokens PII reversible (SPEC 7.1).

token ↔ valor real, cifrado con Fernet (VAULT_KEY en .env, fuera del repo). El
valor real NUNCA sale del perímetro: solo viaja el token `[TIPO_N]`. La
re-hidratación reemplaza tokens por su valor descifrado, local, tras el LLM.
"""

from __future__ import annotations

import functools
import os
import re

from cryptography.fernet import Fernet

TOKEN_RE = re.compile(r"\[[A-Z_]+_\d+\]")


@functools.lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.getenv("VAULT_KEY", "")
    if not key:
        raise RuntimeError("VAULT_KEY ausente en .env — la bóveda no puede cifrar")
    return Fernet(key.encode())


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode("utf-8"))


def decrypt(blob: bytes | memoryview | str) -> str:
    if isinstance(blob, memoryview):
        blob = bytes(blob)
    if isinstance(blob, str):
        blob = blob.encode("utf-8")
    return _fernet().decrypt(blob).decode("utf-8")


def store_token(conn, token: str, value: str, tipo: str, request_id: str) -> None:  # type: ignore[no-untyped-def]
    """Guarda token↔valor cifrado. Idempotente por token (ON CONFLICT DO NOTHING)."""
    conn.execute(
        "INSERT INTO token_vault (token, valor_cifrado, tipo_pii, request_id) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (token) DO NOTHING",
        (token, encrypt(value).decode("ascii"), tipo, request_id),
    )


def get_value(conn, token: str) -> str | None:  # type: ignore[no-untyped-def]
    row = conn.execute("SELECT valor_cifrado FROM token_vault WHERE token = %s", (token,)).fetchone()
    return decrypt(row[0]) if row else None


def rehydrate(conn, text: str) -> str:  # type: ignore[no-untyped-def]
    """Reemplaza cada token `[TIPO_N]` por su valor real desde la bóveda."""
    cache: dict[str, str] = {}

    def repl(m: re.Match[str]) -> str:
        tok = m.group(0)
        if tok not in cache:
            cache[tok] = get_value(conn, tok) or tok
        return cache[tok]

    return TOKEN_RE.sub(repl, text)
