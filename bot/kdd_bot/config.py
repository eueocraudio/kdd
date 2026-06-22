"""Configuração do bot.

Credenciais vêm do ambiente; fallback para ``~/.env`` (chaves ``KDD_*``).
A chave da Anthropic pode vir como ``ANTHROPIC_API_KEY`` ou ``KDD_ANTHROPIC_API_KEY``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_env_file(path: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    if not path.is_file():
        return valores
    for linha in path.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


@dataclass(frozen=True)
class Config:
    base_url: str
    token: str
    backend: str            # "claude" | "ollama" | "auto"
    claude_model: str
    anthropic_api_key: str
    ollama_url: str
    ollama_model: str
    max_chars_pdf: int

    @staticmethod
    def carregar() -> "Config":
        arquivo = _parse_env_file(Path.home() / ".env")

        def pega(*chaves: str, padrao: str = "") -> str:
            for c in chaves:
                if os.environ.get(c):
                    return os.environ[c]
            for c in chaves:
                if arquivo.get(c):
                    return arquivo[c]
            return padrao

        base_url = pega("KDD_APP_URL").rstrip("/")
        # o bot age como OPERADOR (empurra mapas; quem aprova é o validador humano)
        token = pega("KDD_TOKEN_OPERADOR", "KDD_TOKEN")
        if not base_url or not token:
            raise RuntimeError("Defina KDD_APP_URL e KDD_TOKEN_OPERADOR no ambiente ou em ~/.env.")

        return Config(
            base_url=base_url,
            token=token,
            backend=pega("KDD_IA_BACKEND", padrao="auto").lower(),
            claude_model=pega("KDD_CLAUDE_MODEL", padrao="claude-sonnet-4-6"),
            anthropic_api_key=pega("ANTHROPIC_API_KEY", "KDD_ANTHROPIC_API_KEY"),
            ollama_url=pega("KDD_OLLAMA_URL", padrao="http://localhost:11434").rstrip("/"),
            ollama_model=pega("KDD_OLLAMA_MODEL", padrao="aravhawk/qwen3.5-opus-4.6"),
            max_chars_pdf=int(pega("KDD_MAX_CHARS_PDF", padrao="60000")),
        )
