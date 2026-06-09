"""Router / gating del MoE (ARCHITECTURE §3). Primera llamada a Claude.

Corre DESPUÉS del gateway PII: opera sobre texto des-identificado (tokens), nunca
PII real. Clasifica intención + flujo y selecciona expertos (top-k). `fuera_dominio`
rehúsa sin invocar expertos. Salida estructurada (Pydantic) vía messages.parse.

Modelo = LLM_MODEL del .env (sonnet-4-6 dev / opus-4-8 demo). Sin sampling params
(portable: opus-4-8 los rechaza). Registro de expertos = agents/experts.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import anthropic
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

EXPERTS_PATH = Path(__file__).resolve().parent / "experts.yaml"
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

Intencion = Literal[
    "triaje", "consulta_procedimiento", "consulta_legal",
    "consulta_formato", "consulta_compliance", "fuera_dominio",
]
Flujo = Literal["rdf", "df", "ambos", "comun", "indeterminado"]
ExpertoId = Literal["triaje", "copiloto_rdf", "copiloto_df", "legal", "formatos", "compliance"]


class RouteDecisionLLM(BaseModel):
    """Lo que decide el LLM gating."""
    intencion: Intencion
    flujo: Flujo
    expertos: list[ExpertoId] = Field(description="top-k; 1 por defecto, 2 si ambiguo o cruza flujos; vacío si fuera_dominio")
    confianza: float = Field(description="0..1")


class RouteDecision(BaseModel):
    """Decisión completa: añade los nodos KG semilla (entrada GraphRAG)."""
    intencion: Intencion
    flujo: Flujo
    expertos: list[str]
    subgrafo_entrada: list[str]
    confianza: float


def _experts_registry() -> str:
    data = yaml.safe_load(EXPERTS_PATH.read_text(encoding="utf-8"))
    lines = []
    for e in data["expertos"]:
        scope = e.get("scope_corpus", {})
        lines.append(f"- {e['id']} (persona={e['persona']}): {e['desc']} [scope_corpus={scope}]")
    return "\n".join(lines)


def _system_prompt() -> str:
    return f"""Eres el ROUTER de un sistema MoE para el procedimiento SISNNA de Perú (riesgo de
desprotección familiar = RDF, ejecuta la DEMUNA; desprotección familiar = DF, ejecuta la UPE).
Clasificas cada mensaje del usuario y despachas a expertos. El texto ya está DES-IDENTIFICADO
(la PII viene como tokens [NOMBRE_1], [DNI_1], etc.) — NO intentes recuperar PII.

Expertos disponibles:
{_experts_registry()}

Mapeo intención → experto base:
- triaje → triaje (relato ciudadano que pide canalizar/clasificar un caso).
- consulta_procedimiento → copiloto_rdf (si flujo rdf) o copiloto_df (si flujo df).
- consulta_legal → legal (qué artículo/norma fundamenta algo).
- consulta_formato → formatos (qué campos/artefactos lleva una etapa o ficha).
- consulta_compliance → compliance (manejo de dato sensible, "¿puedo compartir/derivar esto?").
- fuera_dominio → expertos vacío (no es del dominio SISNNA/NNA): NO invocar expertos, confianza alta.

flujo: rdf (riesgo, DEMUNA, NNA convive con familia), df (desprotección, UPE, acogimiento/judicial/
adoptabilidad, NNA sin cuidado parental), ambos (cruza ambos flujos), comun, indeterminado (fuera
de dominio). flujo=comun SOLO para consultas de compliance/manejo de dato sensible que no fijan un
flujo. Una consulta de FORMATO o de PROCEDIMIENTO de un flujo concreto lleva su flujo (ej. "Formato
N°01 de recepción" es de RDF → flujo=rdf), NUNCA comun.

Política top-k:
- k=1 por defecto.
- k=2 cuando la consulta GENUINAMENTE necesita el ámbito de un segundo experto:
  * procedimiento que cruza RDF→DF (derivación, transición) → [copiloto_rdf, copiloto_df], flujo=ambos.
  * pregunta que CITA una norma (Ley/DL/DS) o pregunta qué plazo "aplica legalmente" comparando riesgo
    vs desprotección → intencion=consulta_legal, expertos=[legal, copiloto_df], flujo=ambos.
  * pregunta que mezcla CAMPOS de un formato + su fundamento LEGAL → [formatos, legal].
- persona ciudadano que narra un caso concreto → casi siempre triaje (k=1).

Devuelve SIEMPRE la estructura pedida. confianza ∈ [0,1] (baja si ambiguo)."""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()  # ANTHROPIC_API_KEY del entorno


def route(mensaje: str, persona: str = "operador", *, conn=None,  # type: ignore[no-untyped-def]
          historial: list[dict] | None = None, k_seeds: int = 3) -> RouteDecision:
    """Clasifica el mensaje des-identificado y selecciona expertos + subgrafo semilla."""
    user = f"persona={persona}\nmensaje: {mensaje}"
    if historial:
        ctx = "\n".join(f"{h['rol']}: {h['texto']}" for h in historial[-4:])
        user = f"historial:\n{ctx}\n\n{user}"

    resp = _client().messages.parse(
        model=LLM_MODEL,
        max_tokens=1024,
        system=_system_prompt(),
        messages=[{"role": "user", "content": user}],
        output_format=RouteDecisionLLM,
    )
    decision: RouteDecisionLLM = resp.parsed_output

    # fuera_dominio nunca invoca expertos (no quema tokens ni alucina).
    expertos = [] if decision.intencion == "fuera_dominio" else list(decision.expertos)

    subgrafo: list[str] = []
    if conn is not None and decision.intencion != "fuera_dominio":
        from kg.graphrag import entry_nodes
        subgrafo = entry_nodes(conn, mensaje, k_seeds)

    return RouteDecision(
        intencion=decision.intencion, flujo=decision.flujo, expertos=expertos,
        subgrafo_entrada=subgrafo, confianza=decision.confianza,
    )


if __name__ == "__main__":
    d = route("¿Cuántos días tengo para la etapa de evaluación en riesgo?", "operador")
    print(d.model_dump_json(indent=2))
