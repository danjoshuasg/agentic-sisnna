"""Pipeline agentic end-to-end (ARCHITECTURE 2). El núcleo que orquesta todo:

  gateway PII → router → experto(s) → synthesizer → re-hidratación
  (transversal) audit append-only: detección PII, RouteDecision, expertos invocados.

Invariante: router y expertos SIEMPRE operan sobre texto des-identificado (tokens).
La re-hidratación (tokens → valores reales) ocurre al final, local, desde la bóveda.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from agents.router import RouteDecision, route
from agents.synthesizer import synthesize
from app.security.audit import append as audit_append
from app.security.gateway import deidentify
from app.security.vault import rehydrate


@dataclass
class Resultado:
    tipo: str                       # "triaje" | "respuesta" | "rehusa"
    decision: RouteDecision
    respuesta: str | None = None
    citas: list[dict] = field(default_factory=list)
    triaje: Any | None = None       # TriajeResult re-hidratado
    request_id: str = ""


def responder(conn, mensaje: str, persona: str = "operador") -> Resultado:  # type: ignore[no-untyped-def]
    from agents.experts import run_expert

    request_id = f"req-{uuid.uuid4().hex[:12]}"

    # 1) Gateway PII: des-identifica + bóveda + audita detecciones.
    deid = deidentify(mensaje, request_id=request_id, conn=conn)

    # 2) Router (sobre tokens) + audit de la decisión.
    decision = route(deid.text, persona, conn=conn)
    audit_append(conn, actor_id=request_id, accion="route", entidad="route_decision",
                 meta={"intencion": decision.intencion, "flujo": decision.flujo,
                       "expertos": decision.expertos, "confianza": decision.confianza,
                       "subgrafo_entrada": decision.subgrafo_entrada})

    # 3a) Fuera de dominio → rehúsa sin invocar expertos.
    if decision.intencion == "fuera_dominio" or not decision.expertos:
        return Resultado(tipo="rehusa", decision=decision, request_id=request_id,
                         respuesta="Esto no está en el corpus del procedimiento SISNNA.")

    # 3b) Triaje ciudadano → TriajeResult (re-hidratado para el operador).
    if "triaje" in decision.expertos:
        audit_append(conn, actor_id=request_id, accion="ver", entidad="experto", entidad_id="triaje")
        tr = run_expert(conn, "triaje", deid.text, persona)
        tr.relato_resumen = rehydrate(conn, tr.relato_resumen)
        tr.justificacion = rehydrate(conn, tr.justificacion)
        return Resultado(tipo="triaje", decision=decision, triaje=tr, request_id=request_id)

    # 3c) Expertos RAG (top-k) → synthesizer → re-hidratación.
    respuestas = []
    for eid in decision.expertos:
        audit_append(conn, actor_id=request_id, accion="ver", entidad="experto", entidad_id=eid,
                     meta={"subgrafo_entrada": decision.subgrafo_entrada})
        respuestas.append(run_expert(conn, eid, deid.text, persona))

    synth = synthesize(deid.text, respuestas)
    if synth.rehusa:
        return Resultado(tipo="rehusa", decision=decision, request_id=request_id, respuesta=synth.respuesta)

    return Resultado(
        tipo="respuesta", decision=decision, request_id=request_id,
        respuesta=rehydrate(conn, synth.respuesta),
        citas=[{"source_path": c.source_path, "ancla": c.ancla} for c in synth.citas],
    )
