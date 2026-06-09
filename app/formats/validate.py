"""Validador de formatos — CI gate `make validate-formats` (FORMATS-SPEC 9).

Por cada formats/*.yaml:
  1. valida contra _meta-schema.yaml (JSON Schema draft 2020-12, con format: date).
  2. cruza cada `pii_tipo` usado contra el enum del gateway (app.security.pii_types).
  3. verifica vigencia no solapada para el mismo `codigo`.

Exit 0 si todo pasa; exit 1 si algo falla (bloquea merge).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from app.formats.loader import iter_formats, load_meta_schema
from app.security.pii_types import PII_TYPES


def _collect_pii_tipos(node: Any) -> list[str]:
    """Recorre la definición y junta todos los valores `pii_tipo` no nulos."""
    found: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "pii_tipo" and isinstance(v, str):
                found.append(v)
            else:
                found.extend(_collect_pii_tipos(v))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_pii_tipos(item))
    return found


def _vigencia_overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a_start, a_end = a["vigencia_desde"], a.get("vigencia_hasta")
    b_start, b_end = b["vigencia_desde"], b.get("vigencia_hasta")
    a_end = a_end or "9999-12-31"
    b_end = b_end or "9999-12-31"
    return a_start <= b_end and b_start <= a_end


def validate_all(formats_dir: Path | None = None) -> list[str]:
    """Devuelve lista de errores (vacía = todo OK)."""
    meta = load_meta_schema()
    validator = Draft202012Validator(meta, format_checker=FormatChecker())
    formats = iter_formats() if formats_dir is None else iter_formats(formats_dir)

    errors: list[str] = []
    by_codigo: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for path, definition in formats:
        name = path.name
        for err in sorted(validator.iter_errors(definition), key=lambda e: e.path):
            loc = "/".join(str(p) for p in err.path) or "(raíz)"
            errors.append(f"{name}: [{loc}] {err.message}")

        for pii in _collect_pii_tipos(definition):
            if pii not in PII_TYPES:
                errors.append(f"{name}: pii_tipo '{pii}' no existe en el enum del gateway (app.security.pii_types)")

        if isinstance(definition, dict) and "codigo" in definition:
            by_codigo[definition["codigo"]].append(definition)

    for codigo, defs in by_codigo.items():
        for i in range(len(defs)):
            for j in range(i + 1, len(defs)):
                if _vigencia_overlaps(defs[i], defs[j]):
                    errors.append(
                        f"codigo {codigo}: vigencia solapada entre "
                        f"v{defs[i].get('version')} y v{defs[j].get('version')}"
                    )
    return errors


def main() -> int:
    formats = iter_formats()
    errors = validate_all()
    if errors:
        print(f"✗ validate-formats: {len(errors)} error(es)\n")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"✓ validate-formats: {len(formats)} formato(s) válido(s) contra _meta-schema.yaml")
    for path, d in formats:
        print(f"  - {path.name}: {d.get('codigo')} «{d.get('nombre')}» v{d.get('version')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
