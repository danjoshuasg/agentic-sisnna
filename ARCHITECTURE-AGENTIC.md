# SPEC — Capa agentic: Mixture of Experts (router) + Knowledge Graph

> Especificación de arquitectura complementaria a `SPEC.md`. **Reemplaza el RAG plano de `SPEC.md 6`** por un sistema **GraphRAG + MoE agentic**: un router despacha cada consulta a expertos especializados, que razonan sobre un **grafo de conocimiento** del SISNNA + recuperación vectorial.
> Consume: corpus (`SPEC 5`), formatos (`formats/FORMATS-SPEC.md`), gateway PII (`SPEC 7`).

---

## 1. Decisión registrada

| Pregunta | Decisión |
|---|---|
| ¿Qué es "MoE" aquí? | **Router agentic de expertos** (mixture-of-experts a nivel de aplicación, no de pesos del modelo). |
| Alcance en el PoC | **Build completo** — router + todos los expertos + KG. Estructurado en slices (12). |
| Árbol de conocimiento / context-skill | **Knowledge Graph explícito** (entidades + relaciones) encima del corpus. |

**Nota de costo/riesgo (aceptada por el usuario):** el build completo eleva la superficie de fallo de un PoC. Mitigación: slices incrementales (router + 2 expertos antes de los 6), cada uno verificable; el grafo se autora declarativamente (corpus pequeño y curado), no se extrae con NLP frágil.

---

## 2. Arquitectura

```
                      mensaje de usuario (persona)
                                │
                    ┌───────────▼───────────┐
                    │  GATEWAY PII (SPEC 7) │   tokeniza PII ANTES de todo
                    └───────────┬───────────┘   (router y expertos ven solo tokens)
                                │ texto des-identificado
                    ┌───────────▼───────────┐
                    │   ROUTER / GATING      │   clasifica: persona, intención, flujo
                    │  (top-k experts)       │   → selecciona experto(s) + subgrafo
                    └───────────┬───────────┘
              ┌─────────────────┼─────────────────┐
        ┌─────▼─────┐     ┌─────▼─────┐      ┌─────▼─────┐
        │ EXPERTO A │ ... │ EXPERTO B │      │ EXPERTO C │   cada uno: prompt + tools
        │ (triaje)  │     │ (RDF)     │      │ (legal)   │   + scope de corpus/KG
        └─────┬─────┘     └─────┬─────┘      └─────┬─────┘
              └─────────────────┼─────────────────┘
                    ┌───────────▼───────────┐
                    │   SYNTHESIZER          │   fusiona, dedup, citar-o-rehusar
                    └───────────┬───────────┘
                    ┌───────────▼───────────┐
                    │  RE-HIDRATACIÓN PII    │   tokens → valores reales (bóveda)
                    └───────────┬───────────┘
                                ▼  respuesta + citas (al operador)
        (transversal) AUDIT append-only: decisión de routing, expertos, accesos
```

Herramientas compartidas que los expertos invocan: `kg_query` (grafo), `vector_search` (corpus), `formats_lookup` (registro de formatos), `plazo_calc` (motor de plazos).

---

## 3. Router / gating

Función de gating del MoE. Corre **después** del gateway PII (opera sobre tokens, nunca PII real).

- **Entrada:** mensaje des-identificado + `persona` (operador|ciudadano) + historial.
- **Salida (estructurada, Pydantic):**
  ```
  RouteDecision(
    intencion: Literal["triaje","consulta_procedimiento","consulta_legal",
                       "consulta_formato","consulta_compliance","fuera_dominio"],
    flujo: Literal["rdf","df","ambos","indeterminado"],
    expertos: list[str],          # top-k; 1 por defecto, 2 si ambigüo o cruza flujos
    subgrafo_entrada: list[str],  # nodos KG de entrada (ids)
    confianza: float
  )
  ```
- **Política top-k:** k=1 por defecto. k=2 cuando `confianza` baja o `flujo == "ambos"` (ej. transición RDF→DF, derivación DEMUNA→UPE). El synthesizer fusiona.
- **Implementación:** LLM gating con salida estructurada (Claude, barato y flexible). Alternativa: router por embeddings (nearest-expert) — 13.
- **`fuera_dominio` → rehúsa** sin invocar expertos (no quema tokens ni alucina).

---

## 4. Expertos (Mixture of Experts)

Registro declarativo en `agents/experts.yaml` (config como dato). Cada experto = ámbito + herramientas + filtro de corpus/KG + ref de prompt.

| Experto | Persona | Ámbito | Tools | Scope KG/corpus |
|---|---|---|---|---|
| `triaje` | ciudadano | Relato → `TriajeResult` (tipologías Anexo 02, derivación) | kg_query, formats_lookup, vector_search | SignoAlerta, Tipologia, Actor |
| `copiloto_rdf` | operador | Procedimiento RDF: etapas, plazos, compuertas, qué resolución toca | kg_query, vector_search, plazo_calc | `flujo=rdf` |
| `copiloto_df` | operador | Procedimiento DF: acogimiento, fase judicial, adoptabilidad | kg_query, vector_search, plazo_calc | `flujo=df` |
| `legal` | ambos | Citas a DL 1297 / reglamento / leyes; "¿qué artículo fundamenta X?" | kg_query, vector_search | NormaLegal, Articulo |
| `formatos` | operador | Qué campos/artefactos lleva una etapa; estructura de fichas/resoluciones | formats_lookup, kg_query | Artefacto + registro `formats/` |
| `compliance` | ambos | Manejo de dato sensible, plazos, brechas; "¿puedo compartir esto?" | kg_query, vector_search, plazo_calc | NormaLegal (29733), Plazo, Medida |

Reglas comunes a todo experto (heredan de `SPEC 12`): **citar siempre o rehusar**; nunca inventar plazos/artículos/campos; trabajar sobre tokens, nunca PII real.

---

## 5. Knowledge Graph (el "árbol de conocimiento")

Grafo dirigido sobre el dominio SISNNA. **No es un árbol** (hay convergencias: una norma fundamenta varias etapas) — es un grafo. Ontología completa en `kg/ontology.yaml`.

### Tipos de nodo

`Flujo` · `Etapa` · `Artefacto` · `Actor` · `Tipologia` · `SignoAlerta` · `Medida` · `Plazo` · `NormaLegal` · `Articulo` · `Compuerta` (decisión).

### Relaciones (aristas)

```
Flujo      -tiene_etapa->        Etapa
Etapa      -produce->            Artefacto
Etapa      -tiene_plazo->        Plazo
Etapa      -decision->           Compuerta
Compuerta  -deriva_a->           Etapa | Actor
Artefacto  -fundamentado_en->    Articulo
Plazo      -definido_por->       NormaLegal | Articulo
SignoAlerta-indica->             Tipologia
Tipologia  -clasifica_como->     {riesgo | desproteccion}
Tipologia  -competencia_de->     Actor          (DEMUNA | UPE)
Medida     -dispuesta_en->       Etapa
Actor      -ejecuta->            Flujo
Articulo   -pertenece_a->        NormaLegal
```

### Fuente y construcción

- **Autoría declarativa**, no extracción NLP: el corpus es pequeño y curado (`CONTEXT/`). Los nodos/aristas se escriben en YAML (`kg/ontology.yaml` + `kg/instances.yaml`), validados contra el meta-schema de la ontología. Trazable a la fuente (`source_path` por nodo).
- **Store:** tablas `kg_node` / `kg_edge` en Postgres (Insforge), traversal con CTE recursivo. Single datastore, alinea con el corpus vectorial. *(Neo4j = 13 si la complejidad de queries lo justifica.)*

### GraphRAG híbrido

- **Entrada vectorial:** la query (des-identificada) se embebe → nodos de entrada por similitud sobre las descripciones de nodo.
- **Traversal:** desde los nodos de entrada, expandir k-hop por las relaciones relevantes a la intención (ej. `consulta_procedimiento` sigue `tiene_etapa`/`decision`/`tiene_plazo`; `consulta_legal` sigue `fundamentado_en`/`definido_por`).
- **Contexto al experto:** el subgrafo (nodos + aristas + chunks vinculados) se serializa compacto y se pasa como contexto. Lo estructural (plazos, derivaciones, qué resolución) sale del grafo; lo narrativo (signos en un relato) del vector. Cada afirmación cita su nodo/chunk fuente.

---

## 6. Context-skill — navegación del grafo

El "context-skill" es la política que decide **qué subgrafo cargar** por query (evita meter todo el contexto):

1. Router fija `intencion` + `subgrafo_entrada` (nodos semilla).
2. Plantilla de traversal por intención (qué relaciones seguir, cuántos hops).
3. Ranking del subgrafo por relevancia (distancia al nodo semilla + score vectorial).
4. Presupuesto de contexto: top-N nodos/chunks; lo descartado se loggea (`SPEC` regla "no silent caps").

---

## 7. Integración con capas existentes

- **Gateway PII (`SPEC 7`):** corre **antes** del router. Router y expertos ven solo tokens. Re-hidratación tras el synthesizer. Las queries al KG son estructurales (sin PII).
- **Formatos (`FORMATS-SPEC.md`):** el experto `formatos` usa `formats_lookup`; los nodos `Artefacto` del KG referencian las definiciones `formats/*.yaml`.
- **Citar-o-rehusar:** se mantiene como invariante en cada experto y en el synthesizer.
- **Audit (`SPEC 7.2`):** se extiende para registrar la `RouteDecision` y los expertos invocados (qué experto vio qué subgrafo).

---

## 8. Stack (adiciones)

| Componente | Elección | Por qué |
|---|---|---|
| Grafo store | Postgres `kg_node`/`kg_edge` + CTE recursivo (Insforge) | Single datastore; suficiente para corpus curado. |
| Router | LLM gating (Claude) con salida estructurada | Flexible, barato; estructurable con Pydantic. |
| Orquestación | Llamadas async + synthesizer propio | Evita framework pesado; reusa patrones del vault. |
| Traversal | SQL recursivo / `networkx` en memoria | PoC: cargar el grafo (pequeño) en memoria es válido. |

Prior art propio: `brain/30-components/cross-cutting/multi-agent-orchestration-patterns` (scope IN/OUT, handover, verify-twice).

---

## 9. Estructura de archivos (adiciones a `SPEC 10`)

```
poc-chatbot/
  ARCHITECTURE-AGENTIC.md      # este documento
  agents/
    experts.yaml               # registro declarativo de expertos
    router.py                  # gating + RouteDecision
    synthesizer.py             # fusión + citar-o-rehusar
    experts.py                 # carga experts.yaml → agentes
  kg/
    ontology.yaml              # tipos de nodo/arista (meta-schema del grafo)
    instances.yaml             # nodos/aristas del dominio (autoría declarativa)
    store.py                   # kg_node/kg_edge + traversal
    graphrag.py                # entrada vectorial + traversal + serialización
  app/
    rag/                       # (queda como tool vector_search; ya no es el core)
```

---

## 10. Pruebas (adiciones a `SPEC 14`)

- **Routing accuracy:** set etiquetado de consultas → `intencion`/`flujo`/`expertos` esperados.
- **KG traversal:** queries estructurales con subgrafo esperado (ej. "plazo evaluación RDF" → nodo `Plazo:5dh` vía `Etapa:evaluacion -tiene_plazo->`).
- **Experto end-to-end:** por experto, gold Q&A con cita esperada y rechazo fuera de ámbito.
- **No-fuga PII (sigue vigente):** el payload a cualquier experto/LLM no contiene PII real.
- **Synthesizer:** ante 2 expertos, fusión sin duplicar citas; si ambos rehúsan → rehúsa.

---

## 11. Decisiones abiertas

1. **Graph store:** Postgres+CTE (recomendado, single datastore) vs Neo4j (si traversal se vuelve complejo).
2. **Router:** LLM gating (recomendado) vs embedding-router (más barato, menos flexible) vs híbrido.
3. **top-k de expertos:** default k=1, k=2 en ambigüedad. ¿Permitir k=3?
4. **KG: autoría vs extracción.** PoC = autoría declarativa. Extracción asistida por LLM desde el corpus = fase posterior (con validación humana).
5. **Synthesizer cuando expertos discrepan:** ¿gana mayor confianza, o se muestran ambas con sus citas?

---

## 12. Slices de construcción (build completo, escalonado)

1. **Slice A0** — KG: `ontology.yaml` + `instances.yaml` (RDF) + store + traversal CTE. Verificable: query estructural devuelve subgrafo correcto.
2. **Slice A1** — Router (gating + `RouteDecision`) sobre texto des-identificado. Verificable: routing accuracy en set etiquetado.
3. **Slice A2** — 2 expertos reales (`triaje` + `copiloto_rdf`) con GraphRAG híbrido. Verificable: gold por experto + no-fuga.
4. **Slice A3** — Expertos restantes (`copiloto_df`, `legal`, `formatos`, `compliance`) + KG de DF.
5. **Slice A4** — Synthesizer (top-k, fusión, citar-o-rehusar) + audit de routing.
6. **Slice A5** — CLI/API integradas + eval completo + pulido de demo.

Cada slice se prueba antes de avanzar.

---

## 13. Relación con `SPEC.md`

- **Reemplaza `6` (RAG plano)** por GraphRAG + MoE. El retriever vectorial queda como **tool** (`vector_search`), no como el core.
- Mantiene intactos: gateway PII (7), corpus (5), formatos, citar-o-rehusar, audit, solo-sintético.
- Añade módulos `agents/` y `kg/` y sus comandos/pruebas.
