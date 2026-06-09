"""Triaje ciudadano (SPEC §8). Relato des-identificado → TriajeResult estructurado.

El relato YA pasó el gateway PII (tokens, no PII real). Mapea contra signos (Anexo
N°01) y tipologías (Anexo N°02), clasifica nivel + derivación, con regla de
seguridad: ante duda escala a UPE_DF y baja confianza. Salida Pydantic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from app.rag.generate import serializar_contexto
from app.rag.retriever import vector_search

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
PROMPT = (Path(__file__).resolve().parents[2] / "agents" / "prompts" / "experto_triaje.md").read_text(encoding="utf-8")

Nivel = Literal["sin_riesgo_aparente", "riesgo", "presuncion_desproteccion"]
Derivacion = Literal["orientacion", "DEMUNA_RDF", "UPE_DF"]


class TriajeResult(BaseModel):
    relato_resumen: str = Field(description="resumen des-identificado del relato")
    signos_alerta: list[str] = Field(description="códigos Anexo N°01, ej. necesidades_basicas.a")
    tipologias: list[str] = Field(description="códigos t01..t11 de la Tabla de Valoración")
    nivel: Nivel
    derivacion: Derivacion
    justificacion: str = Field(description="con citas al corpus (Anexo N°01/02)")
    confianza: float = Field(description="0..1; baja si hay duda de gravedad")
    disclaimer: str = Field(description="clasificación orientativa; la decisión es humana")


def _taxonomia_kg(conn) -> str:  # type: ignore[no-untyped-def]
    tipos = conn.execute(
        "SELECT id, datos->>'texto' FROM kg_node WHERE tipo='Tipologia' ORDER BY id", unrestricted=True
    ).fetchall()
    comp = dict(conn.execute("SELECT src, dst FROM kg_edge WHERE rel='competencia_de'", unrestricted=True).fetchall())
    lines = ["## Tipologías (Anexo N°02) y competencia (KG):"]
    for tid, texto in tipos:
        actor = "UPE (desprotección)" if comp.get(tid) == "Actor:upe" else (
            "DEMUNA (riesgo)" if comp.get(tid) == "Actor:demuna" else "según gravedad")
        lines.append(f"- {tid}: {texto} → {actor}")
    return "\n".join(lines)


def clasificar(conn, relato_deidentificado: str) -> TriajeResult:  # type: ignore[no-untyped-def]
    taxonomia = _taxonomia_kg(conn)
    hits = vector_search(conn, relato_deidentificado, k=6, tipo_doc="ficha", flujo="rdf")
    contexto = taxonomia + "\n\n" + serializar_contexto("", hits)
    user = f"{contexto}\n\n## RELATO (des-identificado)\n{relato_deidentificado}"

    resp = anthropic.Anthropic().messages.parse(
        model=LLM_MODEL, max_tokens=1500, system=PROMPT,
        messages=[{"role": "user", "content": user}], output_format=TriajeResult,
    )
    return resp.parsed_output
