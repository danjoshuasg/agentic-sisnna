"""Gateway de des-identificación PII (SPEC §7.1). Corre ANTES de cualquier
embedding o LLM. Router y expertos ven solo tokens `[TIPO_N]`.

Presidio (spaCy es) + reconocedores PE custom (DNI, teléfono +51, edad, fecha,
dirección, institución, nombres espaciados) + gazetteer de distritos. Política:
**recall agresivo** — ante duda tokeniza (mejor sobre-tokenizar que fugar PII de
un NNA). Reemplazo propio para tokens estables por valor + persistencia en bóveda
+ audit de detecciones.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider

# --- Tipos operativos del gateway (token = [TIPO_N]) ------------------------
# Persona genérica = NOMBRE (NER no distingue NNA/adulto con fiabilidad; la
# distinción NNA/ADULTO del formato es para campos, no para no-fuga).
ENTITY_TO_TIPO: dict[str, str] = {
    "PERSON": "NOMBRE",
    "LOCATION": "DIRECCION",
    "PE_DNI": "DNI",
    "PE_TELEFONO": "TELEFONO",
    "PE_CORREO": "CORREO",
    "PE_EDAD": "EDAD",
    "PE_FECHA": "FECHA_NAC",
    "PE_DIRECCION": "DIRECCION",
    "PE_INSTITUCION": "INSTITUCION",
    "PE_NOMBRE_ESPACIADO": "NOMBRE",
    "PE_DISTRITO": "DISTRITO",
}

# Distritos Lima/Callao + departamentos que aparecen en los casos. Gazetteer
# ampliable; recall-first.
DISTRITOS = [
    "Villa El Salvador", "Villa María del Triunfo", "San Juan de Lurigancho",
    "San Juan de Miraflores", "Cercado de Lima", "Pueblo Libre", "El Agustino",
    "Carabayllo", "Chorrillos", "Ventanilla", "Rímac", "Comas", "Surco",
    "Santiago de Surco", "San Martín de Porres", "Los Olivos", "Ate", "Surquillo",
    "Miraflores", "Barranco", "La Victoria", "San Borja", "San Isidro", "Breña",
    "Independencia", "Puente Piedra", "Lurín", "Lurigancho", "Chosica", "Callao",
    "Bellavista", "La Molina", "Magdalena", "Jesús María", "Lince", "San Miguel",
    "Santa Anita", "El Tambo", "Arequipa", "Cusco", "Trujillo", "Chiclayo",
    "Piura", "Iquitos", "Lima",
]


def _pe_pattern_recognizers() -> list[PatternRecognizer]:
    P = Pattern
    recs = [
        # DNI: 8 dígitos, tolera espacios entre ellos ("7 0 8 4 5 1 2 3").
        PatternRecognizer(supported_entity="PE_DNI", supported_language="es", patterns=[
            P("dni", r"\b\d(?:[ ]?\d){7}\b", 0.85)]),
        # Teléfono PE: +51, móvil 9 díg., con guiones, fijo (01).
        PatternRecognizer(supported_entity="PE_TELEFONO", supported_language="es", patterns=[
            P("tel_51", r"\+?51[\s]?\d{9}\b", 0.9),
            P("tel_movil", r"\b9\d{2}[\s-]?\d{3}[\s-]?\d{3}\b", 0.85),
            P("tel_fijo", r"\(0?1\)[\s]?\d{3}[\s-]?\d{4}\b", 0.85)]),
        # Correo.
        PatternRecognizer(supported_entity="PE_CORREO", supported_language="es", patterns=[
            P("email", r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", 0.95)]),
        # Edad: "9 años", "7 añitos", "5 y 7 años".
        PatternRecognizer(supported_entity="PE_EDAD", supported_language="es", patterns=[
            P("edad", r"\b\d{1,2}(?:\s*y\s*\d{1,2})?\s*(?:años?|añitos?|añito|meses|mes)\b", 0.8)]),
        # Fecha dd/mm/aaaa.
        PatternRecognizer(supported_entity="PE_FECHA", supported_language="es", patterns=[
            P("fecha", r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", 0.85)]),
        # Dirección: prefijo de vía + hasta coma/fin (tolera número en letras).
        PatternRecognizer(supported_entity="PE_DIRECCION", supported_language="es", patterns=[
            P("via", r"\b(?:jr\.?|jir[oó]n|av\.?|avenida|calle|ca\.?|mz\.?|manzana|lt\.?|lote|"
                     r"pasaje|psje\.?|urb\.?|urbanizaci[oó]n|prolongaci[oó]n)\.?\s+[^,\n.]{1,60}", 0.75)]),
        # Institución educativa / centro.
        PatternRecognizer(supported_entity="PE_INSTITUCION", supported_language="es", patterns=[
            P("ie", r"\b(?:I\.?\s?E\.?|colegio|instituci[oó]n educativa|universidad|instituto|"
                    r"cuna|nido)\b[^,\n.]{0,50}", 0.7)]),
        # Nombre escrito espaciado letra por letra ("D I E G O R A M O S").
        PatternRecognizer(supported_entity="PE_NOMBRE_ESPACIADO", supported_language="es", patterns=[
            P("espaciado", r"\b(?:[A-ZÁÉÍÓÚÑ]\s+){2,}[A-ZÁÉÍÓÚÑ]\b", 0.8)]),
    ]
    # Distritos (gazetteer, case-insensitive).
    distrito_re = r"\b(?:" + "|".join(re.escape(d) for d in sorted(DISTRITOS, key=len, reverse=True)) + r")\b"
    recs.append(PatternRecognizer(supported_entity="PE_DISTRITO", supported_language="es", patterns=[
        Pattern("distrito", f"(?i){distrito_re}", 0.8)]))
    return recs


@functools.lru_cache(maxsize=1)
def _analyzer() -> AnalyzerEngine:
    config = {"nlp_engine_name": "spacy", "models": [{"lang_code": "es", "model_name": "es_core_news_md"}]}
    nlp_engine = NlpEngineProvider(nlp_configuration=config).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["es"])
    for rec in _pe_pattern_recognizers():
        analyzer.registry.add_recognizer(rec)
    return analyzer


# Entidades que pedimos al analyzer (spaCy PERSON/LOCATION + custom PE_*).
_ENTITIES = ["PERSON", "LOCATION"] + [e for e in ENTITY_TO_TIPO if e.startswith("PE_")]


# Nombre por contexto: tras rol/parentesco o en enumeración ("y X"). Captura
# SOLO el nombre (group 1) — spaCy md se pierde nombres sin contexto fuerte.
_NAME_AFTER = re.compile(
    r"(?:\b(?:sobrin[oa]s?|ni[ñn][oa]s?|hij[oa]s?|menor(?:es)?|adolescentes?|herman[oa]s?|"
    r"niet[oa]s?|vecin[oa]s?|padrastro|madrastra|espos[oa]s?|prim[oa]s?|t[ií][oa]s?|"
    r"alumn[oa]s?|beb[eé]s?|se\s+llama|me\s+llamo|mi\s+nombre\s+es|llamo|soy|nombre)\b[\s,:]+"
    r"|\sy\s+)"
    r"([A-ZÁÉÍÓÚ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]+){0,3})",
    re.UNICODE,
)


@dataclass
class _Span:
    start: int
    end: int
    entity_type: str
    score: float


def _context_name_spans(text: str) -> list[_Span]:
    spans: list[_Span] = []
    for m in _NAME_AFTER.finditer(text):
        spans.append(_Span(m.start(1), m.end(1), "PERSON", 0.7))
    return spans


@dataclass
class DeidResult:
    text: str                                   # texto des-identificado (tokens)
    mapping: dict[str, tuple[str, str]] = field(default_factory=dict)  # token -> (tipo, valor_real)
    detections: list[tuple[str, str]] = field(default_factory=list)    # (tipo, valor) en orden

    @property
    def leak_free_of(self) -> list[str]:
        return [v for _, v in self.detections]


def _resolve_overlaps(results) -> list:  # type: ignore[no-untyped-def]
    """Quita spans solapados: prioriza el más largo, luego mayor score."""
    ordered = sorted(results, key=lambda r: (r.start, -(r.end - r.start), -r.score))
    kept: list = []
    last_end = -1
    for r in ordered:
        if r.start >= last_end:
            kept.append(r)
            last_end = r.end
    return kept


def deidentify(text: str, request_id: str = "req", conn=None) -> DeidResult:  # type: ignore[no-untyped-def]
    """Detecta + tokeniza PII. Si `conn`, persiste en bóveda y audita detecciones.
    Tokens estables por valor dentro del request."""
    results = list(_analyzer().analyze(text=text, language="es", entities=_ENTITIES, allow_list=None))
    results += _context_name_spans(text)   # nombres por contexto (recall-first)
    spans = _resolve_overlaps(results)

    counters: dict[str, int] = {}
    value_to_token: dict[str, str] = {}
    mapping: dict[str, tuple[str, str]] = {}
    detections: list[tuple[str, str]] = []

    out = text
    for r in sorted(spans, key=lambda r: r.start, reverse=True):  # derecha→izquierda preserva offsets
        value = text[r.start:r.end]
        tipo = ENTITY_TO_TIPO.get(r.entity_type, r.entity_type)
        if value not in value_to_token:
            counters[tipo] = counters.get(tipo, 0) + 1
            token = f"[{tipo}_{counters[tipo]}]"
            value_to_token[value] = token
            mapping[token] = (tipo, value)
            detections.append((tipo, value))
        token = value_to_token[value]
        out = out[:r.start] + token + out[r.end:]

    if conn is not None:
        from app.security.audit import append
        from app.security.vault import store_token
        for token, (tipo, value) in mapping.items():
            store_token(conn, token, value, tipo, request_id)
        append(conn, actor_id=request_id, accion="deteccion_pii", entidad="texto",
               meta={"detecciones": len(mapping), "tipos": sorted({t for t, _ in detections})})

    return DeidResult(text=out, mapping=mapping, detections=detections)
