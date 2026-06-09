"""Eval de expertos Slice A2: copiloto_rdf (gold) + triaje (mock).

gold_rdf: gq-001..006 → precision_citas (source + ancla), rechazo correcto.
triaje_mock: cada relato pasa por el gateway PII (des-identificación), luego triaje
→ nivel/derivacion/tipologías esperados + escalamiento de seguridad. Verifica también
que el payload al LLM no llevó PII real (no-leak).
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
GOLD = yaml.safe_load((REPO / "eval" / "gold_questions.yaml").read_text(encoding="utf-8"))["preguntas"]
MOCK = yaml.safe_load((REPO / "mock" / "casos_sinteticos.yaml").read_text(encoding="utf-8"))["casos"]


# Hechos clave por pregunta (subconjunto de respuesta_clave; respuesta correcta = todos presentes).
CLAVES = {
    "gq-001": ["5 días"], "gq-002": ["05"], "gq-003": ["02", "upe"],
    "gq-004": ["correlativo", "acreditaci"], "gq-005": ["demuna", "psicólog"],
    "gq-006": ["9 mes", "12 mes"],
    "gq-007": ["tutela"], "gq-008": ["10 día"], "gq-009": ["20 día"],
    "gq-010": ["juzgado", "52"], "gq-011": ["5 día", "3 día"],
    "gq-012": ["11"], "gq-013": ["afectado"], "gq-014": ["1297", "3"],
}


def gold() -> dict:
    """Corre cada gold question por su experto esperado. RAG experts (no triaje/null).
    debe_rehusar → verifica rechazo; resto → respuesta correcta + cita válida."""
    from agents.experts import run_expert
    from app.db import connect

    casos = [q for q in GOLD if q.get("experto_esperado") not in (None, "triaje")]
    por_experto: dict[str, list[bool]] = {}
    rows = []
    with connect() as c:
        for q in casos:
            exp = q["experto_esperado"]
            r = run_expert(c, exp, q["pregunta"], q.get("persona", "operador"))
            if q["debe_rehusar"]:
                ok = r.rehusa
                detalle = f"rehusa={r.rehusa}"
            else:
                resp_ok = all(k.lower() in r.respuesta.lower() for k in CLAVES[q["id"]]) and not r.rehusa
                cite_ok = (not r.rehusa) and len(r.citas) >= 1
                ok = resp_ok and cite_ok
                cited = ", ".join(sorted({ci.source_path.split("/")[-1] for ci in r.citas})) or "—"
                detalle = f"resp_ok={resp_ok} cita={cite_ok} | {cited}"
            por_experto.setdefault(exp, []).append(ok)
            rows.append({"id": q["id"], "exp": exp, "rehusar": q["debe_rehusar"], "ok": ok, "detalle": detalle})

    n = len(casos)
    return {
        "n": n,
        "accuracy": sum(r["ok"] for r in rows) / n,
        "por_experto": {e: sum(v) / len(v) for e, v in por_experto.items()},
        "rows": rows,
    }


def triaje_mock() -> dict:
    from app.db import connect
    from app.security.gateway import deidentify
    from app.triage.clasificar import clasificar

    ok_nivel, ok_deriv, ok_tipo, ok_leak, rows = 0, 0, 0, 0, []
    with connect() as c:
        for caso in MOCK:
            esp = caso["triaje_esperado"]
            deid = deidentify(caso["relato"])                       # gateway PII primero
            leak = [p["valor"] for p in caso["pii_esperada"] if p["valor"].lower() in deid.text.lower()]
            ok_leak += len(leak) == 0
            r = clasificar(c, deid.text)
            nivel_hit = r.nivel == esp["nivel"]
            deriv_hit = r.derivacion == esp["derivacion"]
            esp_t = set(esp.get("tipologias", []))
            tipo_hit = esp_t.issubset(set(r.tipologias)) if esp_t else (len(r.tipologias) == 0)
            ok_nivel += nivel_hit
            ok_deriv += deriv_hit
            ok_tipo += tipo_hit
            rows.append({"id": caso["id"], "nivel": f"{esp['nivel']}→{r.nivel}", "n": nivel_hit,
                         "deriv": f"{esp['derivacion']}→{r.derivacion}", "d": deriv_hit,
                         "tipo": f"{sorted(esp_t)}→{sorted(r.tipologias)}", "t": tipo_hit, "leak": not leak})
    n = len(MOCK)
    return {"n": n, "nivel_acc": ok_nivel / n, "derivacion_acc": ok_deriv / n,
            "tipologia_acc": ok_tipo / n, "no_leak": ok_leak / n, "rows": rows}


if __name__ == "__main__":
    print("=== GOLD (todos los expertos RAG + refusals) ===")
    g = gold()
    for r in g["rows"]:
        flag = "✓" if r["ok"] else "✗"
        tag = "[REHÚSA]" if r["rehusar"] else ""
        print(f"{flag} {r['id']} [{r['exp']}] {tag} {r['detalle']}")
    print(f"\naccuracy={g['accuracy']:.2f} | por experto: "
          + " ".join(f"{e}={v:.2f}" for e, v in g["por_experto"].items()) + "\n")

    print("=== TRIAJE (mock, gateway PII primero) ===")
    t = triaje_mock()
    for r in t["rows"]:
        flag = "✓" if r["n"] and r["d"] and r["t"] else "✗"
        print(f"{flag} {r['id']}: {r['nivel']} | {r['deriv']} | tipo {r['tipo']} | leak_free={r['leak']}")
    print(f"\nnivel_acc={t['nivel_acc']:.2f} derivacion_acc={t['derivacion_acc']:.2f} "
          f"tipologia_acc={t['tipologia_acc']:.2f} no_leak={t['no_leak']:.2f}")
