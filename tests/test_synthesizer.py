"""Tests network-free del synthesizer: rehúsa-si-todos-rehúsan, dedup, paso-único.
(La fusión LLM de ≥2 respuestas se prueba en eval/pipeline_eval.py — integración.)"""

from __future__ import annotations

from agents.synthesizer import _dedup, synthesize
from app.rag.generate import Cita, RespuestaExperto

C1 = Cita(source_path="CONTEXT/rdf-docs/flujo.md", ancla="3. EVALUACIÓN")
C1_dup = Cita(source_path="CONTEXT/rdf-docs/flujo.md", ancla="3. EVALUACIÓN")
C2 = Cita(source_path="CONTEXT/desproteccion-docs/flujo.md", ancla="PTI")


def test_todos_rehusan_rehusa() -> None:
    out = synthesize("q", [RespuestaExperto(rehusa=True, respuesta="No está en el corpus.", citas=[]),
                           RespuestaExperto(rehusa=True, respuesta="No está en el corpus.", citas=[])])
    assert out.rehusa and out.citas == []


def test_un_solo_experto_responde_dedup() -> None:
    out = synthesize("q", [RespuestaExperto(rehusa=False, respuesta="5 días.", citas=[C1, C1_dup]),
                           RespuestaExperto(rehusa=True, respuesta="No está en el corpus.", citas=[])])
    assert not out.rehusa and len(out.citas) == 1 and out.respuesta == "5 días."


def test_dedup_por_source_y_ancla() -> None:
    out = _dedup([C1, C1_dup, C2])
    assert len(out) == 2
