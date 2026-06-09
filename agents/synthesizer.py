"""Synthesizer del MoE (ARCHITECTURE §2). Fusiona respuestas de top-k expertos.

Reglas: si TODOS rehúsan → rehúsa. Si solo uno responde → esa respuesta (citas
deduplicadas). Si ≥2 responden → fusión LLM en una respuesta coherente, sin
duplicar citas y sin introducir fuentes nuevas (solo las que los expertos citaron).
"""

from __future__ import annotations

import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from app.rag.generate import Cita, RespuestaExperto

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

SYNTH_SYSTEM = """Eres el SYNTHESIZER de un sistema MoE del procedimiento SISNNA. Recibes la PREGUNTA y las
respuestas de varios expertos, cada una con sus citas. Produce UNA sola respuesta unificada y coherente para
el operador.
REGLAS:
- Integra lo que los expertos aportan; si se complementan, combínalos sin repetir. Si uno rehúsa y otro
  responde, usa el que responde.
- Conserva y DEDUPLICA las citas (no repitas la misma source_path+ancla). Cita SOLO fuentes que ya aparezcan
  en las respuestas de los expertos — NO agregues fuentes ni datos nuevos.
- Si NINGÚN experto aporta información soportada → rehusa=true, respuesta="No está en el corpus.", citas=[]."""


def _dedup(citas: list[Cita]) -> list[Cita]:
    vistas, out = set(), []
    for c in citas:
        k = (c.source_path, c.ancla)
        if k not in vistas:
            vistas.add(k)
            out.append(c)
    return out


def synthesize(pregunta: str, respuestas: list[RespuestaExperto]) -> RespuestaExperto:
    answered = [r for r in respuestas if not r.rehusa]
    if not answered:
        return RespuestaExperto(rehusa=True, respuesta="No está en el corpus.", citas=[])
    if len(answered) == 1:
        r = answered[0]
        return RespuestaExperto(rehusa=False, respuesta=r.respuesta, citas=_dedup(r.citas))

    fuentes_validas = {c.source_path for r in answered for c in r.citas}
    bloques = []
    for i, r in enumerate(answered, 1):
        cites = "; ".join(f"{c.source_path} | {c.ancla}" for c in r.citas)
        bloques.append(f"### Experto {i}\n{r.respuesta}\nCITAS: {cites}")
    user = f"## PREGUNTA\n{pregunta}\n\n" + "\n\n".join(bloques)

    resp = anthropic.Anthropic().messages.parse(
        model=LLM_MODEL, max_tokens=3000, system=SYNTH_SYSTEM,
        messages=[{"role": "user", "content": user}], output_format=RespuestaExperto,
    )
    out: RespuestaExperto = resp.parsed_output
    out.citas = _dedup([c for c in out.citas if c.source_path in fuentes_validas])
    if not out.rehusa and not out.citas:
        out.citas = _dedup([c for r in answered for c in r.citas])  # fallback: une las de los expertos
    return out
