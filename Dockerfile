# Imagen del PoC SISNNA para Insforge `compute deploy` (Slice A5).
# Hornea el modelo ONNX (e5-large) y el modelo spaCy es para arranque rápido.
# Secretos (ANTHROPIC_API_KEY, INSFORGE_*, VAULT_KEY) se inyectan como env al desplegar,
# NUNCA se hornean en la imagen.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e .

# Pre-baja modelos (capa cacheada): spaCy es + ONNX e5-large.
RUN python -m spacy download es_core_news_md \
    && python -c "from fastembed import TextEmbedding; TextEmbedding('intfloat/multilingual-e5-large')"

COPY . .

EXPOSE 8000
# El corpus y el KG ya están en Insforge (make ingest / kg-load se corren una vez, fuera de la imagen).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
