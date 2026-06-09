"""Schemas Pydantic de la API (SPEC 10)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    persona: Literal["operador", "ciudadano"] = "operador"
    mensaje: str = Field(min_length=1)
    flujo: str | None = None
    historial: list[dict] | None = None


class CitaOut(BaseModel):
    source_path: str
    ancla: str


class ChatResponse(BaseModel):
    tipo: str                              # respuesta | triaje | rehusa
    intencion: str
    flujo: str
    expertos: list[str]
    confianza: float
    respuesta: str | None = None
    citas: list[CitaOut] = []
    triaje: dict[str, Any] | None = None
    request_id: str
