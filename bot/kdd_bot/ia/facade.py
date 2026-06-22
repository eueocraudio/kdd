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
            # 'auto' NUNCA escolhe um backend pago sozinho (proteção de crédito):
            # usa o Ollama (local, sem custo). Para usar o Claude (backends 'cli' ou
            # 'claude', que consomem crédito), selecione explicitamente via --backend
            # ou KDD_IA_BACKEND.
            escolha = "ollama"

        # TEMPORÁRIO: Claude (backends 'claude' e 'cli') está desativado — só Ollama
        # por enquanto. Para reativar, restaure os ramos 'claude'/'cli' abaixo.
        if escolha in ("claude", "cli"):
            raise RuntimeError(
                f"Backend {escolha!r} desativado temporariamente — use 'ollama' "
                "(ou 'auto'). Ajuste KDD_IA_BACKEND ou --backend."
            )
        if escolha == "ollama":
            from .ollama_backend import OllamaBackend
            return IAFacade(OllamaBackend(config.ollama_url, config.ollama_model))
        raise RuntimeError(f"Backend de IA desconhecido: {config.backend!r}")
