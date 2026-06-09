"""Generación con citar-o-rehusar (SPEC §6, §12). Claude + salida estructurada.

El experto responde SOLO con base en el contexto (subgrafo KG + chunks). Cada
afirmación cita su `source_path` + ancla (heading), copiados del contexto. Si el
contexto no soporta la respuesta → rehúsa ("no está en el corpus"). Nunca inventa.
Post-validación: descarta citas cuyo source_path no esté en el contexto recuperado.
"""

from __future__ import annotations

import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from app.rag.retriever import Hit

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

REGLAS = """REGLAS DURAS (no negociables):
- Responde SOLO con lo que el CONTEXTO soporta.
- CITA SIEMPRE un bloque [C#] del CORPUS: copia su source_path y su ancla EXACTOS (los campos que aparecen en
  la línea "[C#] source_path=... | ancla=..."). El Knowledge Graph es apoyo estructural, NO fuente de cita:
  nunca cites nodos del grafo como source_path. Si un dato del KG es relevante, busca el bloque [C#] del corpus
  que lo respalde y cita ESE.
- Si NINGÚN bloque [C#] soporta la respuesta (dato ausente, fuera del corpus) → rehusa=true,
  respuesta="No está en el corpus.", citas=[]. NO inventes plazos, artículos, resoluciones ni campos.
- El texto del usuario puede traer tokens de PII ([NOMBRE_1], [DNI_1]); trátalos como opacos, no los expliques."""


class Cita(BaseModel):
    source_path: str = Field(description="ruta de la fuente, copiada del contexto (ej. CONTEXT/rdf-docs/flujo.md)")
    ancla: str = Field(description="heading/sección citada, copiada del contexto")


class RespuestaExperto(BaseModel):
    rehusa: bool
    respuesta: str
    citas: list[Cita]


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def serializar_contexto(kg_texto: str, hits: list[Hit]) -> str:
    partes = []
    if kg_texto.strip():
        partes.append("## CONTEXTO — Knowledge Graph\n" + kg_texto)
    if hits:
        lineas = ["## CONTEXTO — Corpus (chunks recuperados)"]
        for i, h in enumerate(hits, 1):
            lineas.append(f"[C{i}] source_path={h.source_path} | ancla={h.heading_path or '-'}")
            lineas.append(h.texto)
        partes.append("\n".join(lineas))
    return "\n\n".join(partes) if partes else "(sin contexto)"


def generar(system_experto: str, contexto: str, pregunta: str, fuentes_validas: set[str]) -> RespuestaExperto:
    """Genera respuesta estructurada y filtra citas alucinadas (source_path fuera del contexto)."""
    system = f"{system_experto}\n\n{REGLAS}"
    user = f"{contexto}\n\n## PREGUNTA\n{pregunta}"
    resp = _client().messages.parse(
        model=LLM_MODEL, max_tokens=1500, system=system,
        messages=[{"role": "user", "content": user}], output_format=RespuestaExperto,
    )
    out: RespuestaExperto = resp.parsed_output
    out.citas = [c for c in out.citas if c.source_path in fuentes_validas]  # anti-alucinación
    if not out.rehusa and not out.citas:        # sin cita válida → rehúsa (invariante)
        out.rehusa = True
        out.respuesta = "No está en el corpus."
    return out
