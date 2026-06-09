"""Registro del corpus público (SPEC 5). Allowlist explícita — NO glob ciego.

Excluido a propósito (SPEC 5 gap, 11): leyes íntegras, brechas-seguridad,
fuentes, intentos-estado, índices, binarios. El bot cita artículos solo donde
los flujo.md los referencian inline; fuera de eso → rehúsa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTEXT = REPO / "CONTEXT"


@dataclass(frozen=True)
class Source:
    path: Path
    flujo: str | None          # rdf | df | comun | None
    tipo_doc: str              # flujo | ficha | informe | resolucion | plan | resumen
    codigo: str | None = None  # F01, A02, R04, PTI...


def _codigo_from(name: str) -> str | None:
    m = re.match(r"formato-(\d+)", name)
    if m:
        return f"F{int(m.group(1)):02d}"
    m = re.match(r"anexo-(\d+)", name)
    if m:
        return f"A{int(m.group(1)):02d}"
    m = re.match(r"informe-(\d+)", name)
    if m:
        return f"INF{int(m.group(1)):02d}"
    m = re.match(r"resolucion-(\d+)", name)
    if m:
        return f"R{int(m.group(1)):02d}"
    if name.startswith("pti"):
        return "PTI"
    return None


def _docs(pattern: str, tipo_doc: str, flujo: str | None) -> list[Source]:
    out: list[Source] = []
    for p in sorted((CONTEXT / "docs").glob(pattern)):
        if p.name.startswith("_"):
            continue
        out.append(Source(p, flujo, tipo_doc, _codigo_from(p.name)))
    return out


def registry() -> list[Source]:
    sources: list[Source] = [
        # --- Flujos ---
        Source(CONTEXT / "rdf-docs" / "flujo.md", "rdf", "flujo"),
        Source(CONTEXT / "rdf-docs" / "flujo-web-validacion.md", "rdf", "flujo"),
        Source(CONTEXT / "sisdna-rdf-2023-flujograma-riesgo.md", "rdf", "flujo"),
        Source(CONTEXT / "desproteccion-docs" / "flujo.md", "df", "flujo"),
        # --- Formatos / plantillas TDR (flujo RDF) ---
        *_docs("formato-*.md", "ficha", "rdf"),
        *_docs("anexo-*.md", "ficha", "rdf"),
        *_docs("informe-*.md", "informe", "rdf"),
        *_docs("resolucion-*.md", "resolucion", "rdf"),
        *_docs("pti.md", "plan", "rdf"),
        # --- Resúmenes ---
        Source(CONTEXT / "campos-formatos-resumen.md", None, "resumen"),
        Source(CONTEXT / "flujos_SISDNA_SISPE.md", None, "resumen"),
    ]
    missing = [s.path for s in sources if not s.path.exists()]
    if missing:
        raise FileNotFoundError("Fuentes del registro inexistentes:\n" + "\n".join(str(m) for m in missing))
    return sources


if __name__ == "__main__":
    for s in registry():
        print(f"{s.flujo or '-':5} {s.tipo_doc:11} {s.codigo or '-':5} {s.path.relative_to(REPO)}")
