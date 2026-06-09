"""Tests del validador de formatos (FORMATS-SPEC 9)."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.formats.validate import validate_all

VALID = {
    "codigo": "X01", "nombre": "Ficha de prueba", "tipo": "ficha", "flujo": ["rdf"],
    "version": "2024.1", "vigencia_desde": "2024-01-01", "vigencia_hasta": None,
    "salida": {"formatos": ["json"], "plantilla": None},
    "secciones": [{"id": "s1", "tipo": "grupo_campos",
                   "campos": [{"id": "dni", "tipo": "texto", "sensible": True, "pii_tipo": "DNI"}]}],
}


def _write(tmp: Path, name: str, data: dict) -> None:
    (tmp / name).write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_real_formats_pass() -> None:
    assert validate_all() == []


def test_valid_synthetic_passes(tmp_path: Path) -> None:
    _write(tmp_path, "x01.yaml", VALID)
    assert validate_all(tmp_path) == []


def test_bad_pii_tipo_detected(tmp_path: Path) -> None:
    bad = {**VALID, "secciones": [{"id": "s1", "tipo": "grupo_campos",
           "campos": [{"id": "x", "tipo": "texto", "sensible": True, "pii_tipo": "PASAPORTE"}]}]}
    _write(tmp_path, "x01.yaml", bad)
    errors = validate_all(tmp_path)
    assert any("PASAPORTE" in e for e in errors)


def test_vigencia_overlap_detected(tmp_path: Path) -> None:
    _write(tmp_path, "a.yaml", {**VALID, "version": "1", "vigencia_desde": "2024-01-01", "vigencia_hasta": None})
    _write(tmp_path, "b.yaml", {**VALID, "version": "2", "vigencia_desde": "2024-06-01", "vigencia_hasta": None})
    errors = validate_all(tmp_path)
    assert any("solapada" in e for e in errors)


def test_missing_required_field_detected(tmp_path: Path) -> None:
    bad = {k: v for k, v in VALID.items() if k != "salida"}
    _write(tmp_path, "x01.yaml", bad)
    assert validate_all(tmp_path)
