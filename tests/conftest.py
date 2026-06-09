"""Carga .env para los tests (VAULT_KEY, INSFORGE_*)."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
