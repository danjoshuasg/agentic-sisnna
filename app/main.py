"""FastAPI — PoC chatbot SISNNA (SPEC §9). Endpoints: /health /chat /audit.

/chat ejecuta el pipeline agentic completo (gateway PII → router → expertos →
synthesizer → re-hidratación). /audit expone la cadena de acceso para el DPO.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.schemas import ChatRequest, ChatResponse

app = FastAPI(title="SISNNA PoC Chatbot", version="0.1.0")
_UI = Path(__file__).resolve().parent / "web" / "index.html"


@app.get("/", response_class=HTMLResponse)
def ui() -> str:
    """UI web simple para el operador / ciudadano (sin Swagger)."""
    return _UI.read_text(encoding="utf-8")


def _chunk_counts() -> dict[str, int]:
    from app.db import connect

    with connect() as conn:
        rows = conn.execute(
            "SELECT COALESCE(flujo, 'comun') AS flujo, COUNT(*) FROM chunk GROUP BY 1 ORDER BY 1"
        ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def _vault_ok() -> bool:
    key = os.getenv("VAULT_KEY", "")
    if not key:
        return False
    try:
        from cryptography.fernet import Fernet

        Fernet(key.encode())
        return True
    except Exception:
        return False


@app.get("/health")
def health() -> dict[str, object]:
    db_ok, chunks, error = True, {}, None
    try:
        chunks = _chunk_counts()
    except Exception as exc:  # DB no migrada/sembrada todavía
        db_ok, error = False, str(exc)
    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "chunks_por_flujo": chunks,
        "total_chunks": sum(chunks.values()),
        "embed_model": os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-large"),
        "llm_model": os.getenv("LLM_MODEL", "claude-sonnet-4-6"),
        "vault": "ready" if _vault_ok() else "no_key",
        "error": error,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """Pipeline agentic completo. El gateway PII corre antes de cualquier LLM."""
    from agents.pipeline import responder
    from app.db import connect

    try:
        with connect() as conn:
            r = responder(conn, req.mensaje, req.persona)
    except Exception as exc:  # noqa: BLE001 — superficie de error de demo
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(
        tipo=r.tipo, intencion=r.decision.intencion, flujo=r.decision.flujo,
        expertos=r.decision.expertos, confianza=r.decision.confianza,
        respuesta=r.respuesta, citas=r.citas,
        triaje=r.triaje.model_dump() if r.triaje is not None else None,
        request_id=r.request_id,
    )


@app.get("/audit")
def audit(limit: int = 50) -> dict[str, object]:
    """Cadena de acceso a dato sensible (DPO/auditor). Verifica integridad hash-chain."""
    from app.db import connect
    from app.security.audit import verify_chain

    with connect() as conn:
        integra, roto = verify_chain(conn)
        rows = conn.execute(
            "SELECT id, actor_id, accion, entidad, entidad_id, meta, ts, hash "
            "FROM access_log ORDER BY id DESC LIMIT %s", (limit,),
        ).fetchall()
    return {
        "cadena_integra": integra,
        "eslabon_roto": roto,
        "total": len(rows),
        "entradas": [{"id": r[0], "actor_id": r[1], "accion": r[2], "entidad": r[3],
                      "entidad_id": r[4], "meta": r[5], "ts": str(r[6]), "hash": r[7][:16] + "…"}
                     for r in rows],
    }
