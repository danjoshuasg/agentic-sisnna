"""Carga de definiciones de formato (formats/*.yaml). FORMATS-SPEC §5.

Responsabilidad: localizar y parsear los YAML. La validación contra el
meta-schema vive en validate.py; las proyecciones (json_schema/fill_spec/render)
se añaden en Slice A3 cuando el experto `formatos` las necesite.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

FORMATS_DIR = Path(__file__).resolve().parents[2] / "formats"
META_SCHEMA_PATH = FORMATS_DIR / "_meta-schema.yaml"


def _is_format_file(p: Path) -> bool:
    return p.suffix in {".yaml", ".yml"} and not p.name.startswith("_")


def load_format(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def iter_formats(formats_dir: Path = FORMATS_DIR) -> list[tuple[Path, dict[str, Any]]]:
    """Todas las definiciones de formato (excluye _meta-schema)."""
    return [(p, load_format(p)) for p in sorted(formats_dir.glob("*.y*ml")) if _is_format_file(p)]


def load_meta_schema(path: Path = META_SCHEMA_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)
