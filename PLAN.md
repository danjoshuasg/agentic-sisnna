# PLAN — Build PoC chatbot SISNNA (agentic GraphRAG + MoE)

> Plan de implementación. Deriva de `SPEC.md`, `ARCHITECTURE-AGENTIC.md`, `formats/FORMATS-SPEC.md`,
> `kg/ontology.yaml`, `agents/experts.yaml`, `eval/README.md`. Cada slice se prueba antes de avanzar.

---

## 0. Estado actual del repo

**Existe (config-as-data + specs + corpus):**
- Specs: `SPEC.md`, `ARCHITECTURE-AGENTIC.md`, `formats/FORMATS-SPEC.md`.
- Corpus íntegro: `CONTEXT/rdf-docs/`, `CONTEXT/desproteccion-docs/`, `CONTEXT/docs/` (formatos), resúmenes.
- Config declarativa: `agents/experts.yaml`, `kg/ontology.yaml`, `formats/_meta-schema.yaml` + 2 formatos
  ejemplo (`anexo-02.yaml`, `resolucion-04.yaml`).
- Eval/mock: `eval/{gold_questions,routing_set,pii_noleak}.yaml`, `mock/casos_sinteticos.yaml` (12 casos).

**NO existe (todo el código):**
- `pyproject.toml`, `Makefile`, `.env.example`, `app/`, `ingest/`, `cli/`, `tests/`, `migrations/`.
- `kg/instances.yaml`, `kg/store.py`, `kg/graphrag.py`.
- `agents/router.py`, `agents/experts.py`, `agents/synthesizer.py`, `agents/prompts/`.
- `app/formats/` (loader/validador/renderer), `app/security/`, `app/rag/`, `app/triage/`.

→ Greenfield de implementación sobre specs y config ya cerradas.

---

## 1. Decisiones

### Confirmadas (defaults del kickoff — aplican salvo objeción)
- Embeddings: `intfloat/multilingual-e5-large` (1024 dims), local, sin API-key en ingest.
- LLM: `claude-sonnet-4-6` (dev) / `claude-opus-4-8` (demo). Vía `LLM_MODEL` en `.env`.
- Graph store: Postgres + CTE recursivo (single datastore con el corpus vectorial).
- Router: LLM gating con salida estructurada (Pydantic `RouteDecision`).
- Render formatos: `markdown` + `json` (PDF/firma = fase posterior).
- Corpus legal íntegro: EXCLUIDO. Preguntas legales finas fuera de citas inline → **rehúsa**.

### Resueltas (sesión 2026-06-08)
1. **DB backend = Insforge, pgvector CONFIRMADO.** `vector` 0.7.4 disponible, `pgcrypto` 1.3 instalado.
   Single datastore, **sin Postgres aparte**. Insforge = Postgres vía **REST/PostgREST** (no connection string
   directa) → capa DB usa `POST /api/database/advance/rawsql`. `app/db.py` reescrito como cliente REST con shim
   estilo-psycopg. Base URL en `.env` (`INSFORGE_BASE_URL`). **No se usó `insforge link`** (no hizo falta).
2. **Embeddings runtime = fastembed / ONNX** (mismo `multilingual-e5-large`, sin torch, ~1GB vs ~3.5GB).
   Sin entrenamiento ni fine-tuning: solo inferencia. Verificado: dim 1024, recupera chunk correcto.
3. **Telemetría ampliada.** `access_log` registra acceso sensible **+ egreso-LLM + detecciones-PII** (sin valor real).
4. **Deploy A5 = Insforge `compute deploy`** (contenedor propio FastAPI+modelo, al lado de la DB). Caveat: `VAULT_KEY`
   en cloud solo aceptable para PoC sintético; producción → perímetro PE (SPEC 7.3). No ejecutar hasta A5.
5. **Orden de slices confirmado** (2).

### Estado de ejecución
- **Slice 0 — COMPLETO** (contra Insforge real). 6 tablas + pgvector + 203 chunks (rdf 154/df 17/comun 32, 27 docs,
  embeddings 1024d), ingest idempotente por sha256, audit hash-chain íntegro. `make validate-formats` verde.
  Tests locales 14/14. Bugs corregidos: `anexo-02.yaml` (YAML bool coercion), chunker (split línea para tablas anchas).
  Pendiente menor: arrancar `/health` HTTP (`make install && make serve`) — query subyacente ya verificada.
- **Slice 1 — Gateway PII COMPLETO.** `gateway.py` (Presidio + spaCy es + reconocedores PE: DNI/teléfono/correo/
  edad/fecha/dirección/institución/nombre-espaciado + gazetteer distritos + pase de nombre-por-contexto),
  `vault.py` (Fernet reversible), `audit.py` (acciones detección/egreso). **leak_count=0** sobre 17 casos
  (12 mock + 5 adversariales), re-hidratación reconstruye exacto, audit íntegro. Tests 36/36.
  Caveat conocido: recall-first → sobre-tokeniza (mislabels tipo, ej. teléfono→DIRECCION). Afinar precisión en
  slice de triaje. `/audit` HTTP = A5 (lógica `verify_chain` ya probada).
- **Slice A0 — Knowledge Graph (RDF) COMPLETO.** `kg/instances.yaml` (58 nodos, 62 aristas: flujo/5 etapas+recurrente/
  plazos Ley 32017/artefactos/compuertas con derivaciones/tipologías t01-t11/normas, trazables a `source_path`),
  `kg/store.py` (validación vs ontología + load con embeddings de nodo + `reach` BFS no-dirigido + `induced_edges`,
  CTE recursivo vía rawsql), `kg/graphrag.py` (entrada vectorial → traversal por intención → serialización con citas).
  Cargado en Insforge (58 nodos embebidos). Query estructural verificada: "plazo evaluación RDF" → subgrafo de 13
  nodos/12 aristas con `Etapa:rdf_evaluacion -tiene_plazo-> Plazo:rdf_evaluacion_5dh`. `make kg-load`. Tests 43/43.
- **Slice A1 — Router / gating COMPLETO.** `agents/router.py` (LLM gating con Claude `messages.parse` → Pydantic
  `RouteDecision{intencion,flujo,expertos,subgrafo_entrada,confianza}`; config-driven desde `experts.yaml`;
  `fuera_dominio`→rehúsa sin expertos; subgrafo_entrada vía KG vector seeds). Modelo = `LLM_MODEL` (.env), sin
  sampling params (portable opus-4-8/sonnet-4-6). Primera llamada real a Claude. `eval/routing_eval.py`:
  **routing_accuracy=0.92, flujo_accuracy=1.00, rechazo_fuera_dominio=1.00, k2=0.67** sobre 13 casos. El único
  miss (rt-009) es ambigüedad genuina (legal+copiloto_rdf vs legal+copiloto_df en comparación riesgo-vs-DF, ambos
  válidos; el synthesizer fusiona k=2 igual). Reconciliada inconsistencia repo: `flujo=comun` (eval/formatos) no
  estaba en el enum de ARCHITECTURE 3 → añadido. `make eval-routing`. Tests 47/47.
- **Slice A2 — Expertos triaje + copiloto_rdf COMPLETO.** `app/rag/{retriever,generate}.py` (vector_search con
  filtros + generación citar-o-rehusar con filtro anti-alucinación de citas), `agents/experts.py` (runner GraphRAG
  híbrido: subgrafo KG por intención + chunks del scope del experto), `agents/prompts/experto_{rdf,triaje}.md`,
  `app/triage/clasificar.py` (`TriajeResult` Pydantic alineado a Anexo 01/02, regla de seguridad de escalamiento).
  GraphRAG = contexto ensamblado (no tool-calling loop), más barato/predecible. `eval/expert_eval.py`:
  **copiloto_rdf respuesta_correcta=1.00, cita_valida=1.00, rechazo_fuera_corpus=True**; **triaje nivel=1.00,
  derivacion=1.00, tipologia=0.92, no_leak=1.00** (gateway PII antes del LLM). `make eval-experts`. Tests 53/53.
  Nota: `match_exacto_fuente=0.50` es artefacto — el corpus RDF tiene 3 docs de flujo solapados; el bot cita
  fuentes válidas/mejores (ej. resolucion-02.md para derivación a UPE) distintas a la única que fija el gold.
- **Decisión registrada:** deploy del demo para el PM = Insforge `compute deploy` → URL pública + Swagger/UI (A5);
  el PM nunca recibe API keys (secretos server-side).
- **Slice A3 — Expertos df/legal/formatos/compliance + KG DF COMPLETO.** `kg/instances.yaml` extendido con el
  flujo DF (Flujo:df + 10 etapas + plazos Arts 41/42-47/66/68/99-102 + Ley 32017 18m + medidas acogimiento +
  compuertas + Arts dl1297_52/reg_41/66/67/68 + actores UPE/CAR/Banco/Adopción) → **92 nodos, 100 aristas**,
  validado. `agents/prompts/experto_{df,legal,formatos,compliance}.md` (límites de rechazo SPEC 11 explícitos).
  Runner genérico de A2 reusado sin cambios. `eval/expert_eval.py` extendido a `gold()`:
  **accuracy=1.00** (copiloto_rdf/df/formatos/legal/compliance todos 1.00; gq-r01/r02 rehúsan). Triaje sigue
  nivel/derivacion=1.00, no_leak=1.00. Tests 55/55.
- **Slice A4 — Synthesizer + pipeline + audit de routing COMPLETO.** `agents/synthesizer.py` (fusión LLM de
  top-k con dedup de citas; si todos rehúsan→rehúsa; si uno responde→esa; ≥2→fusión coherente sin fuentes nuevas),
  `agents/pipeline.py` (orquestador end-to-end: gateway PII → router → experto(s) → synthesizer → re-hidratación,
  con audit de detección/route/expertos). `eval/pipeline_eval.py`: **k=2 (rt-008/009/010) fusionan sin citas
  duplicadas**; triaje con PII end-to-end re-hidrata nombres reales (LLM nunca los vio); fuera_dominio rehúsa;
  **audit chain íntegra** con entradas route+deteccion_pii+ver. `make eval-pipeline`. Tests 58/58.
- **Slice A5 — Integración + demo COMPLETO (salvo deploy externo).** `app/main.py` (/chat ejecuta el pipeline
  completo, /audit cadena para DPO, /health), `app/schemas.py`, `cli/chat.py` (cliente), `eval/run_eval.py`
  (reporte consolidado + gate de release), `README.md`, `Dockerfile` + `.dockerignore`. Verificado por HTTP:
  /health OK, /chat operador (cita correcta) + ciudadano (triaje+PII), /audit (cadena íntegra), CLI funcional.
  **`make eval` = GATE PASS** (leak_count=0; routing 0.92; expertos 1.00; triaje nivel/deriv 1.00). Tests 63/63.
  Bug corregido: /health castea COUNT (Insforge devuelve string).
  **Pendiente (acción externa, requiere OK + es billable):** `npx @insforge/cli compute deploy` con la imagen.
- **PoC COMPLETO end-to-end.** 8 slices, 63 tests, 5 evals de integración, gate de release verde.

---

## 2. Orden de slices (merge SPEC 15 + ARCHITECTURE 12)

```
Slice 0  → Infra (Insforge link + migraciones + ingest + validate-formats)
Slice 1  → Gateway PII (Presidio + PE + bóveda + audit hash-chain)
Slice A0 → KG (instances.yaml RDF + store + traversal CTE)
Slice A1 → Router / gating (RouteDecision)
Slice A2 → Expertos triaje + copiloto_rdf (GraphRAG híbrido)
Slice A3 → Expertos df/legal/formatos/compliance + KG del flujo DF
Slice A4 → Synthesizer (top-k, fusión, citar-o-rehusar) + audit de routing
Slice A5 → CLI + API integradas + make eval completo + README demo (<10 min)
```

Razón del orden: PII (Slice 1) es invariante dura que todo lo posterior asume → va antes del KG y router.
KG (A0) antes del router porque el router devuelve `subgrafo_entrada` (nodos KG). Router (A1) antes de expertos
porque despacha. Synthesizer (A4) cierra el fan-out. CLI/API/eval (A5) integra.

---

## 3. Detalle por slice

### Slice 0 — Infra
**Crear:** `pyproject.toml` (deps: fastapi, uvicorn, pydantic v2, anthropic, sentence-transformers,
psycopg/asyncpg, pgvector, presidio-analyzer/anonymizer, jinja2, pyyaml, cryptography, pytest, ruff, mypy),
`Makefile`, `.env.example`, `migrations/0001_init.sql` (tablas: `documento`, `chunk(embedding vector(1024))`,
`token_vault`, `access_log`, `kg_node`, `kg_edge`), `app/db.py`, `ingest/{sources,chunk,embed,load}.py`,
`app/formats/{loader,validate}.py`, `make validate-formats`.
**Corpus → chunks:** registry en `ingest/sources.py` con metadatos por 5 (flujo/etapa/articulo/artefacto/tipo_doc).
Chunking con anclas de heading/artículo. Upsert idempotente por `sha256`.
**Verificación:** `make validate-formats` pasa; `make ingest` siembra; `/health` reporta N chunks por flujo
(rdf/df/formatos). `make migrate` crea las 6 tablas.

### Slice 1 — Gateway PII
**Crear:** `app/security/gateway.py` (Presidio analyzer/anonymizer + reconocedores PE: DNI 8díg, RUC 11,
teléfono +51 / 9díg / fijo `(01)`, NOMBRE_NNA/ADULTO, DIRECCION, DISTRITO, EDAD, INSTITUCION, CENTRO_SALUD —
enum derivado de `formats/*.yaml` flag `sensible`/`pii_tipo` + `mock` taxonomía), `app/security/vault.py`
(token_vault cifrada Fernet, set/get, re-hidratación, token estable por request `[NNA_1]`...),
`app/security/audit.py` (append-only, hash-chain, `/audit` verificable).
**Verificación (crítica, bloquea release):** `eval/pii_noleak.yaml` → `leak_count == 0` sobre 12 casos mock +
5 adversariales (DNI espaciado, tel multi-formato, dirección en minúsculas/letras, correo+IE, nombre informal+fecha).
`rehidratacion_ok`. `/audit` encadena y detecta eslabón roto. Tests unit: set/get bóveda, hash-chain.

### Slice A0 — Knowledge Graph (RDF primero)
**Crear:** `kg/instances.yaml` (nodos/aristas del flujo RDF, autoría declarativa, trazable a `source_path`,
tipos de `ontology.yaml`), `kg/store.py` (carga a `kg_node`/`kg_edge` + traversal CTE recursivo + networkx
en memoria opcional), `kg/graphrag.py` (entrada vectorial → nodos semilla → traversal k-hop por intención).
**Verificación:** query estructural devuelve subgrafo correcto (ej. "plazo evaluación RDF" → `Plazo` vía
`Etapa:evaluacion -tiene_plazo->`). Test de traversal con subgrafo esperado.

### Slice A1 — Router / gating
**Crear:** `agents/router.py` (LLM gating → `RouteDecision{intencion,flujo,expertos,subgrafo_entrada,confianza}`,
top-k=1 default / k=2 si confianza baja o flujo==ambos, `fuera_dominio`→rehúsa sin invocar). Opera sobre
texto YA des-identificado.
**Verificación:** `eval/routing_set.yaml` (13 casos): `routing_accuracy`, `flujo_accuracy`, rechazo
`fuera_dominio` (rt-r01..r03), k=2 en rt-008..010.

### Slice A2 — Expertos triaje + copiloto_rdf
**Crear:** `agents/experts.py` (carga `experts.yaml` → agentes con tools/scope/prompt), tools compartidas
`kg_query`/`vector_search`/`formats_lookup`/`plazo_calc`, `agents/prompts/experto_{triaje,rdf}.md`,
`app/triage/clasificar.py` (`TriajeResult` Pydantic alineado a `anexo-02.yaml`), `app/rag/{retriever,prompts,generate}.py`.
GraphRAG híbrido: estructural del KG, narrativo del vector. Citar siempre o rehusar.
**Verificación:** `gold_questions` gq-001..006 (copiloto_rdf) con `cita_esperada`. Triaje sobre mock
casos 001-006 + 011/012: `nivel`/`derivacion`/`tipologias` esperados; regla de seguridad escala a UPE_DF.
No-fuga vigente (payload a experto sin PII real).

### Slice A3 — Expertos restantes + KG DF
**Crear:** prompts + wiring de `copiloto_df`, `legal`, `formatos`, `compliance`. Extender `kg/instances.yaml`
con el flujo DF (acogimiento, fase judicial, medidas, adoptabilidad). Formatos pendientes que los gold
necesiten (`formato-01.yaml`, `anexo-01.yaml`, etc.) según gq-012/013.
**Verificación:** gold_questions gq-007..014 + gq-r01/r02. Triaje mock casos 007-010 (UPE_DF). `legal`/`compliance`
rehúsan lo fuera de corpus (SPEC 11).

### Slice A4 — Synthesizer
**Crear:** `agents/synthesizer.py` (fusión top-k, dedup de citas, citar-o-rehusar; si ambos expertos rehúsan
→ rehúsa). Extender audit para registrar `RouteDecision` + expertos invocados + subgrafo visto.
**Verificación:** rt-008..010 (2 expertos) fusionan sin duplicar citas. Audit de routing en `/audit`.

### Slice A5 — Integración + demo
**Crear:** `app/main.py` (FastAPI `/chat` `/ingest` `/health` `/audit`), `cli/chat.py`, `eval/run_eval.py`
(corre los 4 sets → reporte), `README.md` demo, `make {serve,chat,eval,test}`.
**Verificación:** `make eval` completo verde. Demo end-to-end reproducible en <10 min (`make migrate ingest serve` +
CLI). Pipeline real: gateway PII → router → experto(s) → synthesizer → re-hidratación → respuesta+citas.

---

## 4. Invariantes que el código respeta en cada slice (SPEC 12-13, no negociables)
- Gateway PII ANTES de cualquier embedding/LLM. Router y expertos sobre TOKENS. Re-hidratación al final.
- Citar siempre o rehusar. Nunca inventar plazos/artículos/resoluciones/campos.
- Solo data sintética (`mock/casos_sinteticos.yaml`). CERO datos reales NNA.
- Formatos = dato (validados vs `_meta-schema.yaml`). Flag `sensible`/`pii_tipo` = fuente de verdad del gateway.
- Secretos solo en `.env`. Nunca en repo. No correr `insforge link` sin tu confirmación + key.

## 5. Riesgos
- **pgvector en Insforge no soportado** → fallback Postgres aparte (decisión bloqueante #1).
- **Presidio español + reconocedores PE**: nombres informales/edades coloquiales (caso 005, adv-005) son el
  punto frágil. Mitigación: reconocedores custom + lista de contexto, validar contra los 17 casos de no-fuga.
- **Router LLM gating** puede fallar k=2 en cruces de flujo (rt-008..010). Mitigación: few-shot en el prompt
  de gating con esos arquetipos.
- Build completo eleva superficie de fallo (aceptado): mitigado por slices verificables.
```
