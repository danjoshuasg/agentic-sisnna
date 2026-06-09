# Eval data — capa de evaluación del PoC

Conjuntos que `eval/run_eval.py` consume para verificar cada capa del sistema. Toda la data es **sintética** y trazable al corpus real (`CONTEXT/`).

## Mapa de archivos

| Archivo | Capa que evalúa | Métrica clave |
|---|---|---|
| `gold_questions.yaml` | Copiloto operador (RAG / expertos) | `precision_citas`, `tasa_rechazo` |
| `routing_set.yaml` | Router / gating (MoE) | `routing_accuracy`, `flujo_accuracy`, rechazo `fuera_dominio` |
| `pii_noleak.yaml` | Gateway de des-identificación (SPEC 7) | `leak_count` = 0, `rehidratacion_ok` |
| `../mock/casos_sinteticos.yaml` | Triaje ciudadano + fuente de PII no-leak | `nivel`/`derivacion`/`tipologias` esperados |

> El triaje no tiene archivo propio en `eval/`: su set son los 12 casos de `mock/casos_sinteticos.yaml`, que ya traen `triaje_esperado` y `pii_esperada`. Evita duplicar.

## Cobertura por experto (gold + routing)

| Experto | gold_questions | routing_set |
|---|---|---|
| `triaje` | (mock) | rt-001, rt-007 |
| `copiloto_rdf` | gq-001..006 | rt-002, rt-008, rt-010 |
| `copiloto_df` | gq-007..011 | rt-003, rt-008, rt-009 |
| `legal` | gq-014, gq-r02 | rt-004, rt-009, rt-010 |
| `formatos` | gq-012, gq-013 | rt-005, rt-010 |
| `compliance` | gq-r01 | rt-006 |
| (rechazo / fuera dominio) | gq-r01..r05 | rt-r01..r03 |

## Invariantes que la eval protege

1. **Citar o rehusar** — toda afirmación cita fuente; lo no soportado se rehúsa (gq-r01..r05).
2. **Cero fuga de PII** — `pii_noleak` debe dar `leak_count == 0` (bloquea release).
3. **Routing correcto** — k=1 directo, k=2 en ambigüedad/cruce de flujos (rt-008..010), rehúse fuera de dominio.
4. **Escalamiento de gravedad** — triaje ante duda escala a UPE_DF (mock casos 011, 012).

## Cómo extender

- Nueva pregunta-oro: añade a `gold_questions.yaml` con `cita_esperada` verificable (path real en `CONTEXT/`). Si es fuera de corpus, marca `debe_rehusar: true` + `motivo`.
- Nuevo caso de routing: añade a `routing_set.yaml` con el `experto_esperado` del registro `agents/experts.yaml`.
- Mantén toda PII obviamente sintética.
