"""Eval del router (ARCHITECTURE 10). Corre routing_set.yaml → métricas.

routing_accuracy: el experto esperado está entre los elegidos.
flujo_accuracy: el flujo coincide.
rechazo: los casos fuera_dominio no invocan expertos.
k2_accuracy: en casos top_k=2, se eligen ≥2 expertos cubriendo el esperado.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from agents.router import route

ROUTING_SET = Path(__file__).resolve().parent / "routing_set.yaml"


def run() -> dict:
    casos = yaml.safe_load(ROUTING_SET.read_text(encoding="utf-8"))["casos"]
    rows, ok_routing, ok_flujo, ok_rechazo, n_rechazo, ok_k2, n_k2 = [], 0, 0, 0, 0, 0, 0

    for c in casos:
        esp = c["esperado"]
        persona = "ciudadano" if esp["intencion"] == "triaje" else "operador"
        d = route(c["query"], persona)
        exp_set = set(esp["expertos"])
        got_set = set(d.expertos)

        routing_hit = exp_set.issubset(got_set) if exp_set else (len(got_set) == 0)
        flujo_hit = d.flujo == esp["flujo"]
        ok_routing += routing_hit
        ok_flujo += flujo_hit
        if esp["intencion"] == "fuera_dominio":
            n_rechazo += 1
            ok_rechazo += len(got_set) == 0
        if esp.get("top_k") == 2:
            n_k2 += 1
            ok_k2 += routing_hit and len(got_set) >= 2

        rows.append({"id": c["id"], "exp_int": esp["intencion"], "got_int": d.intencion,
                     "exp_fl": esp["flujo"], "got_fl": d.flujo,
                     "exp_exp": esp["expertos"], "got_exp": d.expertos,
                     "routing": routing_hit, "flujo": flujo_hit})

    n = len(casos)
    return {
        "n": n,
        "routing_accuracy": ok_routing / n,
        "flujo_accuracy": ok_flujo / n,
        "rechazo_fuera_dominio": ok_rechazo / n_rechazo if n_rechazo else None,
        "k2_accuracy": ok_k2 / n_k2 if n_k2 else None,
        "rows": rows,
    }


if __name__ == "__main__":
    r = run()
    for row in r["rows"]:
        flag = "✓" if row["routing"] and row["flujo"] else "✗"
        print(f"{flag} {row['id']}: int {row['exp_int']}→{row['got_int']} | "
              f"flujo {row['exp_fl']}→{row['got_fl']} | exp {row['exp_exp']}→{row['got_exp']}")
    print(f"\nrouting_accuracy={r['routing_accuracy']:.2f} flujo_accuracy={r['flujo_accuracy']:.2f} "
          f"rechazo={r['rechazo_fuera_dominio']:.2f} k2={r['k2_accuracy']:.2f}")
