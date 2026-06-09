# SPEC — Formatos configurables del SISNNA (definición declarativa en YAML)

> Especificación complementaria al `SPEC.md` raíz. Define cómo se modelan los **formatos de salida** (fichas, anexos, informes, resoluciones, PTI) de forma **configurable**, de modo que su **contenido** cambie sin tocar código.

---

## 1. Problema

En el Estado, los formatos del SISNNA son **estables en la forma** (título, secciones, campos, bloque de firma, estructura VISTO/CONSIDERANDO/SE RESUELVE) pero **volátiles en el contenido**: una modificatoria de DS o una RM nueva agrega/quita campos, cambia opciones de un enum, reescribe un considerando, ajusta un plazo citado.

Si los formatos están hardcodeados (Pydantic/HTML/PDF en código), cada cambio de redacción exige modificar código, testear y redeployar — inviable para un sistema que el propio Estado debe mantener vivo. **Objetivo: el contenido del formato es dato, no código.**

Fuente de los arquetipos reales: `CONTEXT/docs/` (transcripción del TDR SisDNA 2023).

---

## 2. Principios

1. **Declarativo** — un formato es una definición de datos (YAML), no una clase ni una plantilla incrustada en código.
2. **Single source of truth** — una definición por formato genera *todo*: validación de la instancia, especificación de llenado para el LLM, y el documento renderizado. No se duplica la estructura en tres lugares.
3. **Versionado** — cada definición lleva `version` + `vigencia_desde`. El motor selecciona la versión vigente por fecha. Cada instancia llenada guarda con qué versión se generó (trazabilidad legal).
4. **Meta-schema validado** — las definiciones YAML se validan contra un **meta-schema** (`_meta-schema.yaml`). Un analista puede editarlas con guardrails; un YAML mal formado se rechaza en CI antes de llegar a producción.
5. **PII-aware** — cada campo declara `sensible` + `pii_tipo`. Esa marca es la **fuente de verdad del gateway de des-identificación** (`SPEC.md 7`): el gateway sabe qué tokenizar y el audit qué registrar a partir del formato, no de reglas paralelas.
6. **Separación contenido / forma / lógica** — contenido y wording en YAML; forma (layout) en un renderer genérico compartido (porque la forma casi no cambia) con override opcional por formato; lógica (validación, condicionales, versionado) en el motor.

---

## 3. Por qué YAML + meta-schema (alternativas evaluadas)

| Opción | Veredicto |
|---|---|
| **Hardcode en código** (Pydantic/Jinja embebido) | ✗ Cada cambio de redacción = code change + deploy. Rompe el objetivo. |
| **Definiciones en BD** | ~ Editable en caliente, pero difícil de versionar/diff/revisar. Útil más adelante con un editor no-dev encima; sobra para el PoC. |
| **JSON** | ~ Funciona, pero sin comentarios ni multilínea cómodo. Peor para que un analista edite prosa legal. |
| **DSL completo** (XForms / FHIR Questionnaire) | ✗ Sobre-ingeniería: tooling pesado y curva alta para un dominio de formularios simples. |
| **YAML + meta-schema** (elegido) | ✓ Editable por humano (comentarios, prosa multilínea), versionable en git (PR + diff + historial), validable con guardrails. El 80/20. |

**Prior art** (convergen en "form as data", validamos contra ellos sin copiar su peso): JSON Schema + JSON Forms, Formio, FHIR Questionnaire, patrón "form-as-data" de GOV.UK. Adoptamos la versión ligera: YAML declarativo validado por meta-schema, render genérico.

Migración futura: si se necesita edición por no-devs, se monta un editor que escribe estos mismos YAML (o se migra a BD con el mismo esquema). El contrato no cambia.

---

## 4. Lenguaje de definición

Contrato completo en `_meta-schema.yaml`. Resumen.

### Cabecera del formato

```yaml
codigo: A02
nombre: "Informe de valoración de riesgo"
tipo: ficha            # ficha | informe | resolucion | plan
flujo: [rdf]           # rdf | df | comun
etapa: valoracion
version: "2023.1"
vigencia_desde: "2023-01-01"
vigencia_hasta: null
supersede: null        # "A02@2018.1"
base_legal: ["DL 1297", "RM 189-2021-MIMP"]
requiere_firma: true
firmantes: [psicologo, trabajador_social, abogado]
interoperabilidad: false   # recuadro rojo del TDR (campos de interop DEMUNA↔UPE↔SisDNA)
salida:
  formatos: [json, markdown]   # html/pdf en fase posterior
  plantilla: null              # null = renderer genérico; o ruta a Jinja override
secciones: [ ... ]
```

### Tipos de sección

- `grupo_campos` — conjunto de `campos`. Puede ser `repetible` (con `min`/`max`) para bloques que se repiten (ej. "afectado puede ser 1 o más").
- `checklist` — `items` marcables (Anexo N°01: signos de alerta).
- `tabla` — `columnas` + `filas` (Anexo N°02: tipologías × {Riesgo, Desprotección}).
- `texto_libre` — un `campo` narrativo (resumen de hechos).
- `prosa` — cuerpo con `plantilla` Jinja y slots (cuerpo de las resoluciones: VISTO/CONSIDERANDO/SE RESUELVE con boilerplate citado + variables).

Toda sección admite `visible_si` (condicional) — ej. el bloque "informante entidad" del Formato N°01 solo aparece si `informante.tipo == 'entidad'`.

### Campo

```yaml
- id: dni
  label: "DNI"
  tipo: texto            # texto|texto_largo|entero|fecha|booleano|enum|enum_multi|adjunto
  requerido: false
  sensible: true         # → gateway PII (SPEC 7)
  pii_tipo: DNI
  patron: '^\d{8}$'
  opciones: null         # lista para enum
  permite_otros: false   # añade "Otros (describa)"
  visible_si: null
  ayuda: null
```

### Bloques repetibles y condicionales (arquetipo Formato N°01)

```yaml
- id: afectados
  titulo: "Afectado / afectada"
  tipo: grupo_campos
  repetible: true
  min: 1
  max: null
  campos: [ ... ]        # nombres, dni, edad, direccion, ...
```

---

## 5. Qué genera una definición (3 proyecciones)

Una sola definición alimenta tres salidas, sin duplicar estructura:

1. **JSON Schema de instancia** — valida los datos llenados (tipos, requeridos, patrones, enums). Se usa en la API antes de persistir/renderizar.
2. **Fill-spec para el LLM** — descripción compacta de qué campos llenar y sus reglas, para que el bot extraiga del relato (triaje) o asista al operador. Marca campos `sensible` para que el valor real **nunca** se mande al LLM (se trabaja sobre tokens, `SPEC 7`).
3. **Documento renderizado** — `markdown`/`html` (PDF en fase posterior). Fichas: renderer genérico que recorre secciones. Resoluciones: plantilla `prosa` (Jinja) con los slots interpolados.

```
formato.yaml ──┬─▶ to_json_schema()  → validación de instancia
               ├─▶ to_fill_spec()    → extracción/llenado asistido por LLM (PII-safe)
               └─▶ render(instancia, target) → documento (md/html/pdf)
```

---

## 6. Arquetipos cubiertos (ejemplos reales incluidos)

| Arquetipo | Sección dominante | Ejemplo en este repo |
|---|---|---|
| Ficha-checklist | `checklist` | (Anexo N°01 — pendiente; ver mock para signos) |
| Ficha-tabla + datos | `tabla` + `grupo_campos` | **`anexo-02.yaml`** (tipologías × Riesgo/DF, ata con el triaje) |
| Ficha-datos repetible/condicional | `grupo_campos` repetible + `visible_si` | (Formato N°01 — snippets en 4; def completa pendiente) |
| Resolución-plantilla | `prosa` (Jinja) | **`resolucion-04.yaml`** (VISTO/CONSIDERANDO/SE RESUELVE) |

---

## 7. Versionado y cambio de contenido

Flujo cuando una RM/DS cambia el contenido (no la forma):

1. Analista edita el YAML (agrega campo, cambia opción de enum, reescribe un considerando).
2. Bumpea `version` y fija `vigencia_desde` (y `vigencia_hasta` de la versión anterior; `supersede`).
3. CI corre `make validate-formats` → valida contra el meta-schema. Si falla, rechaza el PR.
4. El motor sirve, para una fecha dada, la versión vigente. Las instancias ya generadas conservan su `formato_version` → un expediente viejo se re-renderiza con la versión con la que nació.

**Sin redeploy de código.** Es exactamente el "configurable" que pide el caso de uso.

---

## 8. Integración con el chatbot y el gateway PII

- **Gateway PII (`SPEC 7`):** la política de qué tokenizar se **deriva** de los campos `sensible: true` del registro de formatos. Una sola fuente; nada de listas de PII paralelas que se desincronizan.
- **Copiloto operador:** responde "¿qué campos lleva el Formato N°01?" / "¿qué tipologías están en el Anexo N°02?" leyendo el registro (y opcionalmente vectorizándolo en el corpus).
- **Triaje ciudadano:** mapea lo extraído del relato al `anexo-02.yaml` (tipologías + valoración global) → produce el `TriajeResult` ya alineado al instrumento oficial.
- **PoC hermano (`poc/DESIGN.md`):** el mismo registro alimenta la generación de resoluciones firmadas. El registro es **cross-PoC**.

---

## 9. Guardrails

- `make validate-formats` — valida todos los `formats/*.yaml` contra `_meta-schema.yaml`. Corre en CI; bloquea merge si falla.
- Cada `pii_tipo` usado debe existir en el enum de tipos PII del gateway (chequeo cruzado).
- `version` + `vigencia_desde` obligatorios; `vigencia` no solapada para el mismo `codigo`.
- Tests: una definición de ejemplo renderiza a md sin slots sin resolver; `to_json_schema` rechaza una instancia inválida.

---

## 10. Estructura de archivos

```
poc-chatbot/formats/
  FORMATS-SPEC.md          # este documento
  _meta-schema.yaml        # contrato que valida las definiciones
  anexo-02.yaml            # ejemplo: ficha-tabla (tipologías × Riesgo/DF)
  resolucion-04.yaml       # ejemplo: resolución-plantilla (prosa Jinja)
  # pendientes: formato-01.yaml, anexo-01.yaml, informe-03.yaml, pti.yaml, resolucion-{01..11}.yaml
```

El motor que consume esto vive en `app/formats/` (loader + validador + renderer + proyecciones) — fuera del alcance de esta especificación, que define el **contrato de datos**.

---

## 11. Decisiones abiertas

1. **Target de render en PoC.** Recomendado: `markdown` (demo legible, diff-able) + `json`. PDF (weasyprint) y firma → fase posterior / PoC hermano.
2. **Motor de plantillas para `prosa`.** Recomendado: Jinja2 (estándar, seguro con autoescape, conocido). 
3. **Gramática de `visible_si`.** PoC: mini-expresión `campo operador valor` evaluada por un parser acotado (sin `eval`). Documentar operadores soportados (`==`, `!=`, `in`).
4. **Editor no-dev / migración a BD.** Fuera del PoC; el contrato YAML se mantiene si luego se monta UI o BD.
5. **Lengua originaria / i18n.** Los formatos del Estado pueden requerir versión en lengua originaria (campo `Lengua/Idioma/dialecto` aparece en los originales). ¿Se modela como variantes de definición o como capa de traducción? — diferir.

---

## 12. Relación con el SPEC raíz

Esta especificación **extiende** `SPEC.md`:
- Añade el módulo `formats/` y `app/formats/` a la estructura.
- El gateway PII (`7`) consume los flags `sensible` de aquí.
- El triaje (`8`) produce su salida alineada a `anexo-02.yaml`.
- Añade `make validate-formats` a los comandos y a la suite de pruebas.

Pendiente de confirmar antes de avanzar con `eval/gold_questions.yaml`: 11.1 (target render) y 11.3 (gramática condicional).
