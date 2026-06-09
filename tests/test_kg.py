"""Tests del Knowledge Graph (Slice A0): validación vs ontología, plantillas,
integridad de referencias. (El traversal CTE se prueba en integración contra DB.)
"""

from __future__ import annotations

from pathlib import Path

import yaml

from kg.store import INSTANCES_PATH, load_ontology, traversal_template, validate_instances

REPO = Path(__file__).resolve().parents[1]          # poc-chatbot/ (formats/ aquí)
CORPUS_ROOT = Path(__file__).resolve().parents[2]   # MIMP-SISNNA/ (CONTEXT/ aquí)
INSTANCES = yaml.safe_load(INSTANCES_PATH.read_text(encoding="utf-8"))
ONTOLOGY = load_ontology()


def test_instances_validan_contra_ontologia() -> None:
    assert validate_instances(INSTANCES, ONTOLOGY) == []


def test_detecta_tipo_invalido() -> None:
    bad = {"nodos": [{"id": "X:1", "tipo": "Inexistente"}], "aristas": []}
    assert any("tipo" in e for e in validate_instances(bad, ONTOLOGY))


def test_detecta_rel_invalida() -> None:
    bad = {"nodos": [{"id": "Flujo:rdf", "tipo": "Flujo"}, {"id": "Etapa:x", "tipo": "Etapa"}],
           "aristas": [{"de": "Flujo:rdf", "a": "Etapa:x", "rel": "no_existe"}]}
    assert any("rel" in e for e in validate_instances(bad, ONTOLOGY))


def test_detecta_endpoint_inexistente() -> None:
    bad = {"nodos": [{"id": "Flujo:rdf", "tipo": "Flujo"}],
           "aristas": [{"de": "Flujo:rdf", "a": "Etapa:fantasma", "rel": "tiene_etapa"}]}
    assert any("destino" in e for e in validate_instances(bad, ONTOLOGY))


def test_flujo_df_presente() -> None:
    ids = {n["id"] for n in INSTANCES["nodos"]}
    for nid in ["Flujo:df", "Etapa:df_declaracion_provisional", "Plazo:df_car_urgencia_10dh",
                "Medida:df_acogimiento_residencial", "Articulo:dl1297_52"]:
        assert nid in ids, f"falta nodo DF {nid}"
    rels = {(e["de"], e["rel"], e["a"]) for e in INSTANCES["aristas"]}
    assert ("Actor:upe", "ejecuta", "Flujo:df") in rels
    assert ("Etapa:df_acceso_expediente", "tiene_plazo", "Plazo:df_acceso_5dh") in rels


def test_traversal_template_por_intencion() -> None:
    assert "tiene_plazo" in traversal_template("consulta_procedimiento")["relaciones"]
    assert "fundamentado_en" in traversal_template("consulta_legal")["relaciones"]
    assert "indica" in traversal_template("triaje")["relaciones"]


def test_formato_ref_apunta_a_archivo_existente() -> None:
    for n in INSTANCES["nodos"]:
        ref = n.get("datos", {}).get("formato_ref")
        if ref:
            assert (REPO / ref).exists(), f"{n['id']}: formato_ref inexistente {ref}"


def test_source_path_existe() -> None:
    default = INSTANCES.get("source_default")
    for n in INSTANCES["nodos"]:
        src = n.get("source_path", default)
        assert src and (CORPUS_ROOT / src).exists(), f"{n['id']}: source_path inexistente {src}"
