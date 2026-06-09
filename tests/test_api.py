"""Tests network-free de la capa API/CLI (schemas + render)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import ChatRequest, ChatResponse
from cli.chat import _render


def test_chat_request_default_persona() -> None:
    r = ChatRequest(mensaje="hola")
    assert r.persona == "operador"


def test_chat_request_rechaza_mensaje_vacio() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(mensaje="")


def test_chat_response_serializa() -> None:
    r = ChatResponse(tipo="respuesta", intencion="consulta_procedimiento", flujo="rdf",
                     expertos=["copiloto_rdf"], confianza=0.9, respuesta="5 días.",
                     citas=[{"source_path": "CONTEXT/rdf-docs/flujo.md", "ancla": "3. EVALUACIÓN"}],
                     request_id="req-x")
    assert r.citas[0].source_path.endswith("flujo.md")


def test_cli_render_respuesta() -> None:
    out = _render({"tipo": "respuesta", "intencion": "consulta_procedimiento", "flujo": "rdf",
                   "expertos": ["copiloto_rdf"], "confianza": 0.9, "respuesta": "5 días hábiles.",
                   "citas": [{"source_path": "CONTEXT/rdf-docs/flujo.md", "ancla": "3. EVALUACIÓN"}]})
    assert "5 días hábiles." in out and "flujo.md" in out


def test_cli_render_triaje() -> None:
    out = _render({"tipo": "triaje", "intencion": "triaje", "flujo": "df", "expertos": ["triaje"],
                   "confianza": 0.8, "triaje": {"nivel": "presuncion_desproteccion", "derivacion": "UPE_DF",
                   "tipologias": ["t10"], "signos_alerta": [], "justificacion": "j", "confianza": 0.8,
                   "disclaimer": "orientativo"}})
    assert "UPE_DF" in out and "presuncion_desproteccion" in out
