"""Chunking con anclas de heading/artículo (SPEC 6).

Estrategia: dividir el markdown por encabezados (H1..H4) en secciones; cada
sección es un chunk con su `heading_path`. Secciones largas se parten por
párrafo respetando un presupuesto de caracteres; secciones diminutas se
fusionan con la siguiente. Metadatos derivados: `etapa` (del heading en docs de
flujo) y `articulo` (si el texto referencia "art. N" / "artículo N" inline).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ingest.sources import Source

MAX_CHARS = 1200
MIN_CHARS = 120

_HEADING = re.compile(r"^(#{1,4})\s+(.*\S)\s*$")
_ARTICULO = re.compile(r"\bart(?:[íi]culo)?\.?\s*(\d+)", re.IGNORECASE)
_ETAPA = re.compile(r"^#{2,4}\s+\d+\.\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ,/]+?)(?:\s*[—-]|$)")


@dataclass
class Chunk:
    ord: int
    texto: str
    heading_path: str
    etapa: str | None
    codigo_artefacto: str | None
    articulo: str | None


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _articulo_in(text: str) -> str | None:
    m = _ARTICULO.search(text)
    return f"art. {m.group(1)}" if m else None


def _etapa_from_path(path_parts: list[str]) -> str | None:
    """La etapa es el heading más profundo que matchea «N. NOMBRE» (docs de flujo)."""
    for part in reversed(path_parts):
        m = _ETAPA.match("### " + part if not part.startswith("#") else part)
        if m:
            return m.group(1).strip().title()
    return None


def _split_units(text: str) -> list[str]:
    """Párrafos (por línea en blanco); un párrafo > MAX se explota por líneas;
    una línea > MAX (tabla ASCII ancha) se corta duro. Garantiza unidad <= MAX."""
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        if len(para) <= MAX_CHARS:
            units.append(para)
            continue
        for line in para.splitlines():
            if len(line) <= MAX_CHARS:
                units.append(line)
            else:
                units.extend(line[i:i + MAX_CHARS] for i in range(0, len(line), MAX_CHARS))
    return [u for u in units if u.strip()]


def _flush(buf: list[str], heading_path: list[str], ordn: int, codigo: str | None) -> list[Chunk]:
    text = "\n".join(buf).strip()
    if not text:
        return []
    path_str = " > ".join(heading_path)
    etapa = _etapa_from_path(heading_path)
    chunks: list[Chunk] = []
    if len(text) <= MAX_CHARS:
        return [Chunk(ordn, text, path_str, etapa, codigo, _articulo_in(text))]
    # Sección larga: empaquetar unidades (párrafos/líneas) sin exceder MAX_CHARS.
    acc = ""
    for unit in _split_units(text):
        if acc and len(acc) + len(unit) + 1 > MAX_CHARS:
            chunks.append(Chunk(ordn, acc.strip(), path_str, etapa, codigo, _articulo_in(acc)))
            ordn += 1
            acc = unit
        else:
            acc = f"{acc}\n{unit}" if acc else unit
    if acc.strip():
        chunks.append(Chunk(ordn, acc.strip(), path_str, etapa, codigo, _articulo_in(acc)))
    return chunks


def chunk_markdown(text: str, source: Source) -> list[Chunk]:
    """Parte un markdown en chunks anclados por heading."""
    heading_stack: list[tuple[int, str]] = []   # (nivel, título)
    buf: list[str] = []
    chunks: list[Chunk] = []
    ordn = 0

    def current_path() -> list[str]:
        return [t for _, t in heading_stack]

    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            # cierra el buffer de la sección anterior
            new = _flush(buf, current_path(), ordn, source.codigo)
            if new:
                chunks.extend(new)
                ordn = new[-1].ord + 1
            buf = []
            level = len(m.group(1))
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, m.group(2)))
        else:
            buf.append(line)

    chunks.extend(_flush(buf, current_path(), ordn, source.codigo))

    # Fusiona chunks diminutos con el anterior del mismo heading_path.
    merged: list[Chunk] = []
    for c in chunks:
        if merged and len(c.texto) < MIN_CHARS and merged[-1].heading_path == c.heading_path:
            prev = merged[-1]
            prev.texto = f"{prev.texto}\n\n{c.texto}"
            prev.articulo = prev.articulo or c.articulo
        else:
            merged.append(c)
    for i, c in enumerate(merged):
        c.ord = i
    return merged


def chunk_source(source: Source) -> list[Chunk]:
    return chunk_markdown(source.path.read_text(encoding="utf-8"), source)


if __name__ == "__main__":
    from ingest.sources import registry

    total = 0
    for s in registry():
        cs = chunk_source(s)
        total += len(cs)
        print(f"{len(cs):3} chunks  {s.flujo or '-':4} {s.tipo_doc:11} {s.path.name}")
    print(f"\nTOTAL: {total} chunks")
