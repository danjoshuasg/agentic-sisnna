"""Tests del chunker — anclas de heading, etapa, artículo (SPEC §6)."""

from __future__ import annotations

from ingest.chunk import MAX_CHARS, chunk_markdown
from ingest.sources import Source, registry

MD = """# Flujo RDF

## Etapas

### 3. EVALUACIÓN — 5 días hábiles

Se evalúa el caso conforme al artículo 28 del DL 1297. Plazo de cinco días.

### 4. PTI Y SEGUIMIENTO — 10 días hábiles

Elaboración del plan de trabajo individual.
"""

SRC = Source(path=registry()[0].path, flujo="rdf", tipo_doc="flujo")


def test_heading_path_anclado() -> None:
    chunks = chunk_markdown(MD, SRC)
    eva = next(c for c in chunks if "evalúa el caso" in c.texto)
    assert "Etapas" in eva.heading_path
    assert "EVALUACIÓN" in eva.heading_path


def test_etapa_derivada() -> None:
    chunks = chunk_markdown(MD, SRC)
    eva = next(c for c in chunks if "evalúa el caso" in c.texto)
    assert eva.etapa is not None and "Evaluación" in eva.etapa


def test_articulo_extraido() -> None:
    chunks = chunk_markdown(MD, SRC)
    eva = next(c for c in chunks if "evalúa el caso" in c.texto)
    assert eva.articulo == "art. 28"


def test_ord_secuencial() -> None:
    chunks = chunk_markdown(MD, SRC)
    assert [c.ord for c in chunks] == list(range(len(chunks)))


def test_corpus_real_no_chunks_gigantes() -> None:
    from ingest.chunk import chunk_source

    for s in registry():
        for c in chunk_source(s):
            assert len(c.texto) <= MAX_CHARS * 2, f"{s.path.name} ord={c.ord} demasiado largo"
