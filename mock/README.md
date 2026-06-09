# Mock data — casos sintéticos SISNNA

**Todos los datos son sintéticos.** Nombres, DNI, direcciones y teléfonos son inventados; no corresponden a personas reales. Es el corolario de la regla del SPEC: *cero datos reales de NNA en la PoC*.

## Archivos

| Archivo | Qué es |
|---|---|
| `casos_sinteticos.yaml` | 12 casos de intake ciudadano. Cada uno trae el relato en lenguaje natural, su PII esperada y el resultado de triaje esperado. |

## Doble propósito

1. **Eval de triaje** (`eval/run_eval.py` → persona `ciudadano`): compara `nivel`, `derivacion` y `tipologias` que produce el bot contra `triaje_esperado`.
2. **Suite de no-fuga de PII** (`eval/pii_noleak.yaml` deriva de aquí): `pii_esperada` lista cada valor sensible que el **gateway de des-identificación** debe tokenizar antes de enviar el relato al LLM. El test verifica que el payload de egreso contenga **0** de esos valores en claro.

## Taxonomía (fiel al instrumento real)

- **Tipologías `t01..t11`** = columnas Riesgo / Desprotección Familiar del **Anexo N°02** (`CONTEXT/docs/anexo-02-valoracion-riesgo.md`).
- **Signos de alerta** (`salud_fisica.*`, `salud_mental.*`, `necesidades_basicas.*`) = **Anexo N°01** (`CONTEXT/docs/anexo-01-signos-alerta.md`).

## Cobertura

| Nivel | Derivación | Casos |
|---|---|---|
| `sin_riesgo_aparente` | `orientacion` | 001, 002 |
| `riesgo` | `DEMUNA_RDF` | 003, 004, 005, 006, 012 |
| `presuncion_desproteccion` | `UPE_DF` | 007, 008, 009, 010, 011 |

Incluye casos **borderline** (011, 012) que ejercitan la regla de seguridad: ante duda de gravedad, escalar a UPE y bajar confianza.

## Cómo extender

Añade un caso al final de `casos:` siguiendo el esquema. Mantén la PII obviamente falsa (DNI de 8 dígitos ficticios, teléfonos `+51 9########`) y marca `confianza_min` conservadora para los casos ambiguos.
