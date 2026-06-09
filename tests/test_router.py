"""Tests del router network-free: carga de registro + schema. (La accuracy contra
Claude se mide en eval/routing_eval.py — integración.)"""

from __future__ import annotations

from agents.router import RouteDecision, RouteDecisionLLM, _experts_registry, _system_prompt


def test_registry_carga_los_6_expertos() -> None:
    reg = _experts_registry()
    for eid in ["triaje", "copiloto_rdf", "copiloto_df", "legal", "formatos", "compliance"]:
        assert eid in reg


def test_system_prompt_incluye_politica_topk() -> None:
    sp = _system_prompt()
    assert "k=1 por defecto" in sp and "fuera_dominio" in sp


def test_route_decision_schema() -> None:
    d = RouteDecision(intencion="consulta_procedimiento", flujo="rdf", expertos=["copiloto_rdf"],
                      subgrafo_entrada=["Etapa:rdf_evaluacion"], confianza=0.9)
    assert d.expertos == ["copiloto_rdf"]


def test_route_decision_llm_valida_enums() -> None:
    d = RouteDecisionLLM(intencion="triaje", flujo="df", expertos=["triaje"], confianza=0.8)
    assert d.intencion == "triaje" and d.flujo == "df"
