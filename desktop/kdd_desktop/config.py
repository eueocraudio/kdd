"""Configuração do cliente desktop.

Lê as credenciais do ambiente; se ausentes, faz fallback para o ``~/.env`` do
usuário (mesmo arquivo usado no deploy da API), procurando as chaves ``KDD_*``.
Nada de segredo embutido no código.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parser mínimo de .env (KEY=VALUE), tolerante a aspas e comentários."""
    valores: dict[str, str] = {}
    if not path.is_file():
        return valores
    for linha in path.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        valores[chave] = valor
    return valores


@dataclass(frozen=True)
class Config:
    base_url: str
    token: str
    token_validador: str = ""   # exigido só pelo editor (escrita); vazio = só leitura

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
        # consulta aceita qualquer token válido; preferimos o de operador
        token = pega("KDD_TOKEN", "KDD_TOKEN_OPERADOR", "KDD_TOKEN_VALIDADOR")
        # o editor (escrita) exige perfil validador (spec §6)
        token_validador = pega("KDD_TOKEN_VALIDADOR")

        if not base_url or not token:
            raise RuntimeError(
                "Defina KDD_APP_URL e um token (KDD_TOKEN_OPERADOR/VALIDADOR) "
                "no ambiente ou em ~/.env."
            )
        return Config(base_url=base_url, token=token, token_validador=token_validador)
