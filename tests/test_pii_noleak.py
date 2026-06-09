"""Suite crítica de no-fuga PII (SPEC 7, 14). Bloquea release.

leak_count debe ser 0: ningún valor real de PII aparece en el texto des-
identificado (el payload que saldría al embedder/LLM). Fuentes: 12 casos mock +
5 adversariales.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.security.gateway import deidentify

REPO = Path(__file__).resolve().parents[1]
MOCK = yaml.safe_load((REPO / "mock" / "casos_sinteticos.yaml").read_text(encoding="utf-8"))
NOLEAK = yaml.safe_load((REPO / "eval" / "pii_noleak.yaml").read_text(encoding="utf-8"))


def _leaks(text: str, values: list[str]) -> list[str]:
    out = deidentify(text).text.lower()
    return [v for v in values if v.lower() in out]


@pytest.mark.parametrize("caso", MOCK["casos"], ids=lambda c: c["id"])
def test_mock_no_leak(caso: dict) -> None:
    values = [p["valor"] for p in caso["pii_esperada"]]
    leaks = _leaks(caso["relato"], values)
    assert not leaks, f"{caso['id']} fugó: {leaks}"


@pytest.mark.parametrize("caso", NOLEAK["casos_adversariales"], ids=lambda c: c["id"])
def test_adversarial_no_leak(caso: dict) -> None:
    leaks = _leaks(caso["texto"], caso["no_debe_aparecer"])
    assert not leaks, f"{caso['id']} fugó: {leaks}"
