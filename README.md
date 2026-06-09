# PoC Chatbot SISNNA — Agentic GraphRAG + MoE con gateway PII

Chatbot sobre el procedimiento **SISNNA** del MIMP (Perú) — riesgo de desprotección familiar (RDF, DEMUNA) y
desprotección familiar (DF, UPE) — que **cumple dos roles** con un mismo motor y **protege el dato sensible de
NNA frente a la API externa del LLM**.

1. **Copiloto del operador** (DEMUNA / UPE): responde sobre el procedimiento con **citas verificables** —
   plazos, resoluciones, campos de fichas, compuertas del flujo — o **rehúsa** si no está en el corpus.
2. **Triaje ciudadano**: recibe un relato en lenguaje natural y produce una **clasificación estructurada**
   (riesgo / desprotección / sin riesgo) con la **derivación sugerida** (DEMUNA / UPE). La decisión es humana.
3. **Capa de protección de datos**: un **gateway de des-identificación** tokeniza la PII antes de cualquier
   embedding o LLM, re-hidrata la respuesta localmente, y **audita** cada acceso (append-only, hash-chain).

> Tesis: un RAG anclado a un corpus curado + Knowledge Graph, obligado a **citar o rehusar**, con un gateway que
> impide la fuga de PII y telemetría de acceso, es lo bastante fiable y auditable para un dominio NNA — y por
> tanto para cualquier sector regulado.

## ¿Por qué no basta con "subir los PDF a un ChatGPT"?

La forma tradicional —pegar los documentos en ChatGPT (u otro asistente genérico) y preguntarle— **falla justo en lo
que un dominio sensible exige**. Cada feature de esta arquitectura ataca una de esas fallas:

| Dimensión | ChatGPT tradicional (subir PDFs / RAG plano) | **Este sistema** (agentic GraphRAG + MoE + gateway PII) |
|---|---|---|
| **Dato sensible de NNA** | El relato con nombre, DNI y dirección **viaja en claro** a una API externa (fuera de Perú) | **Tokenizado antes de salir**: el LLM solo ve `[NOMBRE_1]`; nunca el dato real. Re-hidratación local. Fuga verificada = **0** |
| **Alucinación** | Puede **inventar** un plazo, un artículo o una resolución con tono seguro | **Cita o rehúsa**: "no está en el corpus". Filtro anti-alucinación descarta citas no respaldadas |
| **Fuentes** | Difusas o inventadas; difícil saber de dónde salió la respuesta | Cada afirmación con su **fuente + sección** verificable contra el corpus |
| **Estructura del procedimiento** | Texto plano: pierde derivaciones, compuertas y plazos del flujo | **Knowledge Graph**: etapas, plazos, derivaciones y qué resolución toca, como datos estructurados |
| **Roles** | Un prompt genérico para todo | **MoE**: un router despacha a un experto por rol (operador / ciudadano) y por flujo (RDF / DF) |
| **Salida** | Prosa libre, no integrable | **Estructurada** (triaje: nivel / derivación / tipologías) → conectable a otros sistemas |
| **Auditoría** | Ninguna — no hay registro de qué dato se accedió | **Log append-only encadenado (hash-chain)** + endpoint `/audit` para el DPO |
| **Cumplimiento legal** (Ley 29733 · DS 016-2024-JUS) | **Incumple**: PII de un menor vulnerable a un tercero externo | Diseñado para cumplir; en producción la bóveda de PII vive en perímetro PE |
| **Costo de vectorizar** | API de embeddings: manda el corpus afuera y cobra | **Local** ($0, sin API-key, el corpus no sale) |
| **Versionado de fuentes** | No: lo que subiste, sin control | Corpus curado + **formatos como dato versionado** (cambian sin tocar código) |

**Lo que esto significa en una frase:** en un dominio NNA, mandar el relato de un niño con su nombre a una API
externa es inaceptable bajo la Ley 29733, y un asistente que **inventa** un plazo o una resolución es peor que no
tener asistente. Esta arquitectura existe para que el sistema sea **a la vez útil, no-filtrante y auditable** — el
mínimo para operar sobre dato sensible de un sujeto vulnerable, y por extensión sobre cualquier sector regulado.

## Arquitectura (pipeline de una consulta)

```
mensaje → [GATEWAY PII] → tokens → [ROUTER/gating] → experto(s) MoE → [SYNTHESIZER] → [RE-HIDRATACIÓN] → respuesta + citas
                │                        │                                                    │
          bóveda cifrada          subgrafo KG (GraphRAG)                              (transversal) AUDIT hash-chain
```

- **Gateway PII** (`app/security/`): Presidio + reconocedores PE (DNI, teléfono +51, nombres, direcciones,
  edades, instituciones) + bóveda Fernet reversible + audit encadenado. **El LLM solo ve tokens** `[NOMBRE_1]`.
- **Knowledge Graph** (`kg/`): grafo declarativo del SISNNA (92 nodos / 100 aristas, flujos RDF + DF) en
  Postgres; traversal CTE recursivo; GraphRAG híbrido (entrada vectorial → subgrafo por intención).
- **MoE** (`agents/`): router LLM (gating estructurado) despacha a 6 expertos
  (`triaje`, `copiloto_rdf`, `copiloto_df`, `legal`, `formatos`, `compliance`); synthesizer fusiona top-k.
- **Formatos como dato** (`formats/`): fichas/resoluciones en YAML validado; el flag `sensible` es la fuente de
  verdad del gateway PII.

## Stack

Python 3.11+ · FastAPI · **Insforge** (Postgres + pgvector vía REST) · embeddings **multilingual-e5-large** local
(fastembed/ONNX, sin torch) · **Claude** (`sonnet-4-6` dev / `opus-4-8` demo) · Presidio · Jinja2.

## Setup (demo reproducible < 10 min)

```bash
cp .env.example .env        # rellenar ANTHROPIC_API_KEY, INSFORGE_API_KEY, INSFORGE_BASE_URL, VAULT_KEY
make install                # venv + deps (incluye modelo ONNX ~1GB en el 1er ingest)
make validate-formats       # CI gate: valida formats/*.yaml contra el meta-schema
make migrate                # crea schema en Insforge (6 tablas + pgvector + pgcrypto)
make ingest                 # vectoriza el corpus público (203 chunks, idempotente por sha256)
make kg-load                # carga el Knowledge Graph (92 nodos / 100 aristas)
make serve                  # FastAPI en :8000  (/chat /audit /health /docs)
```

Generar `VAULT_KEY`: `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`

## Probar

```bash
# CLI
make chat                                          # interactivo (operador)
python -m cli.chat --persona ciudadano             # triaje ciudadano
python -m cli.chat -m "¿plazo de evaluación en riesgo?"

# HTTP (Swagger en http://localhost:8000/docs)
curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"persona":"operador","mensaje":"¿Quién declara judicialmente la desprotección familiar?"}'

curl "localhost:8000/audit?limit=10"               # cadena de acceso (DPO)
```

## Evaluación

```bash
make eval            # reporte consolidado con gate de release (leak_count==0 bloquea)
make test            # pytest unit + integración (sin red)
make eval-routing    # routing accuracy
make eval-experts    # gold por experto + triaje
make eval-pipeline   # synthesizer k=2 + audit end-to-end
```

Resultados de referencia: PII no-leak **leak_count=0**; routing_accuracy 0.92 / flujo 1.00 / rechazo 1.00;
gold de expertos **accuracy=1.00**; triaje nivel/derivación **1.00**, no_leak **1.00**.

## Invariantes (SPEC 12-13, no negociables)

- Gateway PII **antes** de cualquier embedding/LLM. Router y expertos operan sobre tokens. Re-hidratación al final.
- **Citar siempre o rehusar.** Nunca inventar plazos, artículos, resoluciones ni campos.
- **Solo data sintética** (`mock/casos_sinteticos.yaml`). Cero datos reales de NNA.
- Secretos solo en `.env` (nunca en repo). En producción, la `token_vault` con PII real debe vivir en perímetro PE.

## Estructura

```
app/      security/ (gateway, vault, audit) · rag/ (retriever, generate) · triage/ · formats/ · db.py · main.py · schemas.py
agents/   router.py · experts.py · synthesizer.py · pipeline.py · experts.yaml · prompts/
kg/       ontology.yaml · instances.yaml · store.py · graphrag.py
ingest/   sources.py · chunk.py · embed.py · load.py
formats/  _meta-schema.yaml · *.yaml
eval/     run_eval.py · routing_eval.py · expert_eval.py · pipeline_eval.py · *.yaml
cli/      chat.py
migrations/ tests/
```

Specs: `../SPEC.md`, `ARCHITECTURE-AGENTIC.md`, `formats/FORMATS-SPEC.md`. Plan y estado: `PLAN.md`.
