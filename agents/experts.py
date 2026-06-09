"""Runner de expertos (ARCHITECTURE §4). Carga experts.yaml → ejecuta un experto.

GraphRAG híbrido: ensambla contexto (subgrafo KG por intención + chunks del corpus
filtrados por el scope del experto) y genera con citar-o-rehusar. El triaje delega
en app.triage.clasificar (salida TriajeResult). Slice A2 = triaje + copiloto_rdf;
los demás expertos reusan el mismo runner en A3.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.rag.generate import RespuestaExperto, generar, serializar_contexto
from app.rag.retriever import vector_search

EXPERTS_PATH = Path(__file__).resolve().parent / "experts.yaml"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Intención de traversal KG por experto (plantillas en kg/ontology.yaml).
_INTENCION = {
    "copiloto_rdf": "consulta_procedimiento", "copiloto_df": "consulta_procedimiento",
    "legal": "consulta_legal", "formatos": "consulta_formato", "compliance": "consulta_compliance",
}


def _registry() -> dict[str, dict]:
    data = yaml.safe_load(EXPERTS_PATH.read_text(encoding="utf-8"))
    return {e["id"]: e for e in data["expertos"]}


def _prompt(expert: dict) -> str:
    return (PROMPTS_DIR / Path(expert["prompt_ref"]).name).read_text(encoding="utf-8")


def run_expert(conn, expert_id: str, pregunta: str, persona: str = "operador"):  # type: ignore[no-untyped-def]
    """Ejecuta un experto sobre una pregunta des-identificada.
    triaje → TriajeResult; resto → RespuestaExperto (citar-o-rehusar)."""
    reg = _registry()
    if expert_id not in reg:
        raise ValueError(f"experto desconocido: {expert_id}")

    if expert_id == "triaje":
        from app.triage.clasificar import clasificar
        return clasificar(conn, pregunta)

    expert = reg[expert_id]
    scope = expert.get("scope_corpus", {})
    hits = vector_search(conn, pregunta, k=8, flujo=scope.get("flujo"), tipo_doc=scope.get("tipo_doc"))

    kg_texto = ""
    if "kg_query" in expert.get("tools", []):
        from kg.graphrag import serialize, subgraph
        sg = subgraph(conn, pregunta, _INTENCION.get(expert_id, "consulta_procedimiento"))
        kg_texto = serialize(sg)

    contexto = serializar_contexto(kg_texto, hits)
    fuentes = {h.source_path for h in hits}
    return generar(_prompt(expert), contexto, pregunta, fuentes)


def __getattr__(name: str):  # re-export para tests
    if name == "RespuestaExperto":
        return RespuestaExperto
    raise AttributeError(name)
