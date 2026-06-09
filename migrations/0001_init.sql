-- =============================================================================
-- Migración inicial — schema PoC SISNNA (SPEC 6 + ARCHITECTURE-AGENTIC 5 + audit ampliado)
-- Idempotente: create ... if not exists. Embeddings dim 1024 (multilingual-e5-large).
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;          -- pgvector (verificar en Insforge — PLAN 1.1)
CREATE EXTENSION IF NOT EXISTS pgcrypto;        -- gen_random_uuid

-- --- Corpus ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documento (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_path TEXT UNIQUE NOT NULL,
    flujo       TEXT,                            -- rdf | df | comun | null
    tipo_doc    TEXT,                            -- flujo | ficha | informe | resolucion | resumen | plan
    sha256      TEXT NOT NULL,                   -- idempotencia de ingest
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunk (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    documento_id     UUID NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
    ord              INTEGER NOT NULL,
    texto            TEXT NOT NULL,
    heading_path     TEXT,                       -- "## Etapa 2 > ### Valoración"
    flujo            TEXT,
    tipo_doc         TEXT,
    etapa            TEXT,
    codigo_artefacto TEXT,                        -- F01, A02, R04, PTI
    articulo         TEXT,                        -- "art. 28" si el chunk lo referencia inline
    embedding        vector(1024),
    UNIQUE (documento_id, ord)
);
CREATE INDEX IF NOT EXISTS chunk_flujo_idx ON chunk (flujo);
CREATE INDEX IF NOT EXISTS chunk_embedding_idx ON chunk USING hnsw (embedding vector_cosine_ops);

-- --- Bóveda PII reversible (SPEC 7.1) --------------------------------------
CREATE TABLE IF NOT EXISTS token_vault (
    token         TEXT PRIMARY KEY,              -- [NOMBRE_1], [DNI_2]
    valor_cifrado TEXT NOT NULL,                 -- Fernet(valor_real) base64, VAULT_KEY en .env
    tipo_pii      TEXT NOT NULL,                 -- NOMBRE_NNA, DNI, ...
    request_id    TEXT NOT NULL,                 -- token estable POR request (SPEC 7.1)
    creado_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS token_vault_request_idx ON token_vault (request_id);

-- --- Audit append-only hash-chain (SPEC 7.2, ampliado: egreso + detecciones) -
CREATE TABLE IF NOT EXISTS access_log (
    id         BIGSERIAL PRIMARY KEY,
    actor_id   TEXT NOT NULL,
    accion     TEXT NOT NULL,                    -- ver | des_identificar | re_hidratar | egreso_llm | deteccion_pii | ingest | route
    entidad    TEXT,                             -- chunk | token | documento | route_decision
    entidad_id TEXT,
    meta       JSONB,                            -- nº detecciones, modelo, expertos... NUNCA valor real (SPEC 11)
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    hash_prev  TEXT,
    hash       TEXT NOT NULL                     -- sha256(hash_prev || campos) — tamper-evident
);

-- --- Knowledge Graph (ARCHITECTURE 5) --------------------------------------
CREATE TABLE IF NOT EXISTS kg_node (
    id          TEXT PRIMARY KEY,                -- "Etapa:rdf_valoracion"
    tipo        TEXT NOT NULL,                   -- Flujo | Etapa | Artefacto | ... (ontology.yaml)
    datos       JSONB NOT NULL DEFAULT '{}',     -- campos según tipo
    descripcion TEXT,                            -- para embedding de entrada (GraphRAG)
    source_path TEXT,                            -- trazabilidad
    embedding   vector(1024)
);
CREATE INDEX IF NOT EXISTS kg_node_tipo_idx ON kg_node (tipo);
CREATE INDEX IF NOT EXISTS kg_node_embedding_idx ON kg_node USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS kg_edge (
    id    BIGSERIAL PRIMARY KEY,
    src   TEXT NOT NULL REFERENCES kg_node(id) ON DELETE CASCADE,
    dst   TEXT NOT NULL REFERENCES kg_node(id) ON DELETE CASCADE,
    rel   TEXT NOT NULL,                         -- tiene_etapa | produce | ... (ontology.yaml)
    datos JSONB NOT NULL DEFAULT '{}',
    UNIQUE (src, dst, rel)
);
CREATE INDEX IF NOT EXISTS kg_edge_src_idx ON kg_edge (src);
CREATE INDEX IF NOT EXISTS kg_edge_rel_idx ON kg_edge (rel);
