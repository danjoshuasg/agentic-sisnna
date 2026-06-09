"""Reporte de evaluación consolidado (SPEC §14). `make eval`.

Corre las 4 capas y emite un reporte con gate de release:
  - PII no-leak (CRÍTICO, bloquea release si leak_count > 0)
  - Routing (router/gating)
  - Expertos (gold copiloto/legal/formatos/compliance + refusals)
  - Triaje (mock, con gateway PII antes)
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def noleak() -> dict:
    from app.security.gateway import deidentify

    mock = yaml.safe_load((REPO / "mock" / "casos_sinteticos.yaml").read_text(encoding="utf-8"))["casos"]
    adv = yaml.safe_load((REPO / "eval" / "pii_noleak.yaml").read_text(encoding="utf-8"))["casos_adversariales"]
    leaks = 0
    for caso in mock:
        out = deidentify(caso["relato"]).text.lower()
        leaks += sum(p["valor"].lower() in out for p in caso["pii_esperada"])
    for caso in adv:
        out = deidentify(caso["texto"]).text.lower()
        leaks += sum(v.lower() in out for v in caso["no_debe_aparecer"])
    return {"leak_count": leaks, "casos": len(mock) + len(adv)}


def main() -> int:
    from eval.expert_eval import gold, triaje_mock
    from eval.routing_eval import run as routing_run

    print("════════ EVAL SISNNA ════════\n")

    nl = noleak()
    print(f"① PII NO-LEAK (crítico): leak_count={nl['leak_count']} sobre {nl['casos']} casos "
          f"→ {'PASS' if nl['leak_count'] == 0 else 'FAIL'}")

    rt = routing_run()
    print(f"② ROUTING: routing_accuracy={rt['routing_accuracy']:.2f} flujo={rt['flujo_accuracy']:.2f} "
          f"rechazo={rt['rechazo_fuera_dominio']:.2f} k2={rt['k2_accuracy']:.2f}")

    g = gold()
    print(f"③ EXPERTOS (gold): accuracy={g['accuracy']:.2f} | "
          + " ".join(f"{e}={v:.2f}" for e, v in g["por_experto"].items()))

    tr = triaje_mock()
    print(f"④ TRIAJE: nivel={tr['nivel_acc']:.2f} derivacion={tr['derivacion_acc']:.2f} "
          f"tipologia={tr['tipologia_acc']:.2f} no_leak={tr['no_leak']:.2f}")

    gate_ok = nl["leak_count"] == 0
    print(f"\n════════ GATE DE RELEASE: {'✓ PASS' if gate_ok else '✗ FAIL (fuga de PII)'} ════════")
    return 0 if gate_ok else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
