"""Configuração do servidor MCP do KDD.

Espelha o ``Config`` do bot (``bot/kdd_bot/config.py``): credenciais vêm do ambiente, com
fallback para ``~/.env``. Nenhum segredo no código — o repositório é PÚBLICO.
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
    token: str                 # token de leitura (operador serve)
    token_validador: str       # vazio = sem escrita
    escrita: bool              # KDD_MCP_ESCRITA=1 E token_validador presente
    timeout: float

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
        token = pega("KDD_TOKEN_OPERADOR", "KDD_TOKEN", "KDD_TOKEN_VALIDADOR")
        if not base_url or not token:
            raise RuntimeError(
                "Defina KDD_APP_URL e um token (KDD_TOKEN_OPERADOR ou KDD_TOKEN) "
                "no ambiente ou em ~/.env."
            )

        token_validador = pega("KDD_TOKEN_VALIDADOR")
        # Escrita exige OS DOIS: a flag explícita e um token de validador. Ver
        # docs/mcp-servidor.md §4 — base curada não aceita escrita de agente por acidente.
        escrita = pega("KDD_MCP_ESCRITA", padrao="0") == "1" and bool(token_validador)

        try:
            timeout = float(pega("KDD_MCP_TIMEOUT", padrao="30"))
        except ValueError as e:
            raise RuntimeError("KDD_MCP_TIMEOUT precisa ser um número (segundos).") from e

        return Config(
            base_url=base_url,
            token=token,
            token_validador=token_validador,
            escrita=escrita,
            timeout=timeout,
        )
