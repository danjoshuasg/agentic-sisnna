"""Embeddings multilingües locales — multilingual-e5-large vía fastembed (ONNX).

ONNX en vez de torch: mismo modelo, instalación ~1GB, sin GPU. e5 es asimétrico
y requiere prefijos: "passage: " para documentos, "query: " para consultas.
fastembed NO los añade solo → se anteponen aquí. Sin API-key.
"""

from __future__ import annotations

import functools
import os

EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-large")
EMBED_DIM = 1024


@functools.lru_cache(maxsize=1)
def _model():  # type: ignore[no-untyped-def]
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=EMBED_MODEL)


def embed_passages(texts: list[str]) -> list[list[float]]:
    prefixed = [f"passage: {t}" for t in texts]
    return [v.tolist() for v in _model().embed(prefixed)]


def embed_query(text: str) -> list[float]:
    vec = next(iter(_model().embed([f"query: {text}"])))
    return vec.tolist()
