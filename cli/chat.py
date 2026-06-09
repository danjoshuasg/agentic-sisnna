"""Cliente CLI del PoC SISNNA (SPEC §9). Conversa contra la API /chat.

Uso:
  python -m cli.chat                          # modo interactivo (operador)
  python -m cli.chat --persona ciudadano      # triaje ciudadano
  python -m cli.chat -m "¿plazo de evaluación en riesgo?"   # one-shot
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

URL = os.getenv("API_URL", "http://localhost:8000")


def _render(data: dict) -> str:
    tipo = data["tipo"]
    rt = data.get("triaje")
    head = (f"[{data['intencion']} · flujo={data['flujo']} · expertos={data['expertos']} "
            f"· confianza={data['confianza']:.2f}]")
    if tipo == "triaje" and rt:
        out = [head, f"\nNIVEL: {rt['nivel']}   DERIVACIÓN: {rt['derivacion']}   confianza={rt['confianza']:.2f}",
               f"Tipologías: {rt['tipologias']}   Signos: {rt['signos_alerta']}",
               f"\n{rt['justificacion']}", f"\n⚠ {rt['disclaimer']}"]
        return "\n".join(out)
    if tipo == "rehusa":
        return f"{head}\n\n{data.get('respuesta', 'No está en el corpus.')}"
    citas = "\n".join(f"  · {c['source_path']} ({c['ancla']})" for c in data.get("citas", []))
    return f"{head}\n\n{data['respuesta']}\n\nFuentes:\n{citas}"


def _ask(mensaje: str, persona: str) -> None:
    try:
        resp = httpx.post(f"{URL}/chat", json={"persona": persona, "mensaje": mensaje}, timeout=120)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"Error contra {URL}: {exc}", file=sys.stderr)
        sys.exit(1)
    print(_render(resp.json()))


def main() -> None:
    ap = argparse.ArgumentParser(description="CLI del chatbot SISNNA")
    ap.add_argument("--persona", choices=["operador", "ciudadano"], default="operador")
    ap.add_argument("-m", "--mensaje", help="one-shot; si se omite, modo interactivo")
    args = ap.parse_args()

    if args.mensaje:
        _ask(args.mensaje, args.persona)
        return
    print(f"SISNNA chat · persona={args.persona} · {URL} · Ctrl-D para salir")
    while True:
        try:
            msg = input("\n> ").strip()
        except EOFError:
            print()
            break
        if msg:
            _ask(msg, args.persona)


if __name__ == "__main__":
    main()
