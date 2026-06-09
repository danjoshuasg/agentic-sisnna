"""Eval del pipeline end-to-end (Slice A4): synthesizer k=2 + audit de routing.

Verifica:
- k=2 (rt-008/009/010): el synthesizer fusiona en UNA respuesta, sin duplicar citas.
- triaje: pipeline completo con PII → re-hidratación, sin fuga en el egreso.
- fuera_dominio: rehúsa sin invocar expertos.
- audit: cadena íntegra con entradas route + deteccion_pii + ver (expertos).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from agents.pipeline import responder
from app.db import connect
from app.security.audit import verify_chain

REPO = Path(__file__).resolve().parents[1]
ROUTING = yaml.safe_load((REPO / "eval" / "routing_set.yaml").read_text(encoding="utf-8"))["casos"]
MOCK = yaml.safe_load((REPO / "mock" / "casos_sinteticos.yaml").read_text(encoding="utf-8"))["casos"]


def run() -> None:
    k2 = [c for c in ROUTING if c["esperado"].get("top_k") == 2]
    with connect() as c:
        print("=== Synthesizer k=2 ===")
        for caso in k2:
            r = responder(c, caso["query"], "operador")
            claves = [(ci["source_path"], ci["ancla"]) for ci in r.citas]
            sin_dup = len(claves) == len(set(claves))
            ok = r.tipo == "respuesta" and len(r.decision.expertos) >= 2 and sin_dup and len(r.citas) >= 1
            print(f"{'✓' if ok else '✗'} {caso['id']}: expertos={r.decision.expertos} "
                  f"citas={len(r.citas)} sin_dup={sin_dup} | {(r.respuesta or '')[:80]}")

        print("\n=== Triaje end-to-end (con PII) ===")
        caso = next(c for c in MOCK if c["id"] == "caso-008")          # violencia sexual → UPE_DF
        r = responder(c, caso["relato"], "ciudadano")
        tr = r.triaje
        rehidratado = any(p["valor"] in (tr.relato_resumen or "") for p in caso["pii_esperada"])
        print(f"{'✓' if r.tipo=='triaje' else '✗'} caso-008: nivel={tr.nivel} derivacion={tr.derivacion} "
              f"| re-hidrata nombres reales: {rehidratado}")

        print("\n=== Fuera de dominio ===")
        r = responder(c, "¿Cuál es la capital de Francia?", "operador")
        print(f"{'✓' if r.tipo=='rehusa' and not r.decision.expertos else '✗'} "
              f"intencion={r.decision.intencion} expertos={r.decision.expertos}")

        print("\n=== Audit ===")
        ok, broken = verify_chain(c)
        cnt = {a: c.execute(f"SELECT count(*) FROM access_log WHERE accion='{a}'").fetchone()[0]
               for a in ["route", "deteccion_pii", "ver"]}
        print(f"cadena íntegra: {ok} | entradas: {cnt}")


if __name__ == "__main__":
    run()
