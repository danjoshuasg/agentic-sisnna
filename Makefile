# Makefile — PoC chatbot SISNNA. Ver SPEC.md §9.
PY ?= python3.13
VENV := .venv
BIN := $(VENV)/bin

.PHONY: venv install link migrate validate-formats ingest serve chat eval test lint clean

venv:
	$(PY) -m venv $(VENV)

install: venv
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e ".[dev]"

# Andamiaje liviano: solo lo necesario para validate-formats (sin ML/torch).
install-min: venv
	$(BIN)/pip install -U pip
	$(BIN)/pip install pyyaml jsonschema python-dotenv

link:                          ## acción externa — requiere INSFORGE_API_KEY + confirmación
	npx @insforge/cli link --project-id $$(grep INSFORGE_PROJECT_ID .env | cut -d= -f2)

migrate:
	$(BIN)/python -m app.db migrate

validate-formats:
	$(BIN)/python -m app.formats.validate

ingest:
	$(BIN)/python -m ingest.load

kg-load:
	$(BIN)/python -m kg.store

serve:
	$(BIN)/uvicorn app.main:app --reload --port 8000

chat:
	$(BIN)/python -m cli.chat

demo:                          ## server local + túnel Cloudflare → imprime LINK público (gratis)
	bash scripts/demo.sh

eval:
	$(BIN)/python -m eval.run_eval

eval-routing:
	$(BIN)/python -m eval.routing_eval

eval-experts:
	$(BIN)/python -m eval.expert_eval

eval-pipeline:
	$(BIN)/python -m eval.pipeline_eval

test:
	$(BIN)/pytest -q

lint:
	$(BIN)/ruff check . && $(BIN)/mypy app ingest

clean:
	rm -rf $(VENV) **/__pycache__ .pytest_cache .ruff_cache .mypy_cache

# --- Deploy a Insforge compute (Docker en Fly.io) — BILLABLE, acción externa ---
# Requiere flyctl en PATH (brew install flyctl). Secretos vía --env-file .env (gitignored).
# Memoria 4096: el modelo ONNX e5 + Presidio/spaCy residente no caben en el default 512MB.
SVC ?= sisnna-poc
deploy:                        ## construye (build remoto Fly) + despliega. Devuelve URL pública.
	npx -y @insforge/cli@latest compute deploy . --name $(SVC) --port 8000 \
		--memory 4096 --cpu shared-1x --region iad --env-file .env

deploy-url:                    ## lista servicios + URL
	npx -y @insforge/cli@latest compute list

deploy-stop:                   ## APAGA para no pagar ocioso (pasar SVC id de `make deploy-url`)
	npx -y @insforge/cli@latest compute stop $(SVC)

deploy-logs:
	npx -y @insforge/cli@latest compute events $(SVC)
