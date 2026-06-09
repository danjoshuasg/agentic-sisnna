"""Tests network-free de la capa de expertos A2 (la accuracy vs Claude vive en
eval/expert_eval.py — integración)."""

from __future__ import annotations

from agents.experts import _INTENCION, _prompt, _registry
from app.rag.generate import Cita, RespuestaExperto, serializar_contexto
from app.rag.retriever import Hit
from app.triage.clasificar import TriajeResult


def test_registry_tiene_6_expertos() -> None:
    reg = _registry()
    assert set(reg) == {"triaje", "copiloto_rdf", "copiloto_df", "legal", "formatos", "compliance"}


def test_prompt_copiloto_rdf_carga() -> None:
    assert "COPILOTO RDF" in _prompt(_registry()["copiloto_rdf"])


def test_todos_los_prompts_cargan() -> None:
    for eid, exp in _registry().items():
        if eid == "triaje":
            continue
        assert len(_prompt(exp)) > 100, f"prompt vacío/ausente para {eid}"


def test_intencion_traversal_mapea() -> None:
    assert _INTENCION["copiloto_rdf"] == "consulta_procedimiento"
    assert _INTENCION["legal"] == "consulta_legal"


def test_serializar_contexto_numera_chunks() -> None:
    hits = [Hit("texto evaluación", "CONTEXT/rdf-docs/flujo.md", "Etapas > 3. EVALUACIÓN", "Evaluación", None, None, 0.8)]
    ctx = serializar_contexto("# Subgrafo KG\n- Etapa:rdf_evaluacion", hits)
    assert "[C1]" in ctx and "CONTEXT/rdf-docs/flujo.md" in ctx and "Knowledge Graph" in ctx


def test_respuesta_experto_schema() -> None:
    r = RespuestaExperto(rehusa=False, respuesta="5 días hábiles.",
                         citas=[Cita(source_path="CONTEXT/rdf-docs/flujo.md", ancla="3. EVALUACIÓN")])
    assert r.citas[0].source_path.endswith("flujo.md")


def test_triaje_result_schema() -> None:
    t = TriajeResult(relato_resumen="x", signos_alerta=["necesidades_basicas.a"], tipologias=["t08"],
                     nivel="riesgo", derivacion="DEMUNA_RDF", justificacion="...", confianza=0.6,
                     disclaimer="orientativo")
    assert t.nivel == "riesgo" and t.derivacion == "DEMUNA_RDF"
