"""Fachada que escolhe o backend de IA e normaliza a saída."""
from __future__ import annotations

from typing import Any, Protocol

from ..config import Config
from .schema import normalizar


class Backend(Protocol):
    nome: str
    def extrair_mapa(self, titulo: str, texto: str) -> dict[str, Any]: ...


class IAFacade:
    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    @property
    def backend_nome(self) -> str:
        return self._backend.nome

    def extrair_mapa(self, titulo: str, texto: str) -> dict[str, Any]:
        """Retorna {areas, conceitos, proposicoes} já normalizado para a API."""
        return normalizar(self._backend.extrair_mapa(titulo, texto))

    @staticmethod
    def a_partir_de(config: Config) -> "IAFacade":
        escolha = config.backend
        if escolha == "auto":
            escolha = "claude" if config.anthropic_api_key else "ollama"

        if escolha == "claude":
            from .claude_backend import ClaudeBackend
            return IAFacade(ClaudeBackend(config.anthropic_api_key, config.claude_model))
        if escolha == "ollama":
            from .ollama_backend import OllamaBackend
            return IAFacade(OllamaBackend(config.ollama_url, config.ollama_model))
        raise RuntimeError(f"Backend de IA desconhecido: {config.backend!r}")
