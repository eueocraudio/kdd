"""Cliente HTTP dos endpoints de consulta do armazém KDD."""
from __future__ import annotations

from typing import Any

import requests

from .config import Config


class KddApiError(RuntimeError):
    pass


class KddClient:
    def __init__(self, config: Config, timeout: float = 20.0) -> None:
        self._cfg = config
        self._timeout = timeout
        self._s = requests.Session()
        self._s.headers.update({"X-Token": config.token, "Accept": "application/json"})

    def _get(self, caminho: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._cfg.base_url}{caminho}"
        try:
            r = self._s.get(url, params=params, timeout=self._timeout)
        except requests.RequestException as e:  # rede
            raise KddApiError(f"Falha de rede: {e}") from e
        if r.status_code >= 400:
            msg = r.json().get("erro") if r.headers.get("content-type", "").startswith("application/json") else r.text
            raise KddApiError(f"HTTP {r.status_code}: {msg}")
        return r.json()

    def pode_editar(self) -> bool:
        """True se há token de validador configurado (editor exige escrita)."""
        return bool(self._cfg.token_validador)

    def _escrita(self, metodo: str, caminho: str, corpo: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST/PATCH/DELETE com o token de VALIDADOR (escrita do editor)."""
        if not self._cfg.token_validador:
            raise KddApiError("Defina KDD_TOKEN_VALIDADOR para editar (perfil validador).")
        url = f"{self._cfg.base_url}{caminho}"
        cab = {"X-Token": self._cfg.token_validador, "Accept": "application/json"}
        try:
            r = self._s.request(metodo, url, json=corpo, headers=cab, timeout=self._timeout)
        except requests.RequestException as e:
            raise KddApiError(f"Falha de rede: {e}") from e
        if r.status_code >= 400:
            msg = r.json().get("erro") if r.headers.get("content-type", "").startswith("application/json") else r.text
            raise KddApiError(f"HTTP {r.status_code}: {msg}")
        return r.json()

    # --- Endpoints de consulta ---
    def saude(self) -> dict[str, Any]:
        return self._get("/health")

    def areas(self) -> list[dict[str, Any]]:
        return self._get("/areas").get("areas", [])

    def conceitos(self, q: str | None = None, area: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if q:
            params["q"] = q
        if area:
            params["area"] = area
        return self._get("/conceitos", params).get("conceitos", [])

    def conceito(self, conceito_id: int) -> dict[str, Any]:
        return self._get(f"/conceitos/{conceito_id}").get("conceito", {})

    def proposicoes(self, conceito: int | None = None) -> list[dict[str, Any]]:
        params = {"conceito": conceito} if conceito else None
        return self._get("/proposicoes", params).get("proposicoes", [])

    def constelacao(self) -> dict[str, Any]:
        return self._get("/constelacao")

    # --- Endpoints de escrita (editor; exigem perfil validador) ---
    def criar_conceito(self, sentido: str, rotulo_principal: str, areas: list[str]) -> dict[str, Any]:
        return self._escrita("POST", "/conceitos",
                              {"sentido": sentido, "rotulo_principal": rotulo_principal, "areas": areas})

    def editar_conceito(self, conceito_id: int, sentido: str) -> dict[str, Any]:
        return self._escrita("PATCH", f"/conceitos/{conceito_id}", {"sentido": sentido})

    def add_rotulo(self, conceito_id: int, texto: str, principal: bool = False) -> dict[str, Any]:
        return self._escrita("POST", f"/conceitos/{conceito_id}/rotulos",
                             {"texto": texto, "principal": principal})

    def rotulo_principal(self, rotulo_id: int) -> dict[str, Any]:
        return self._escrita("PATCH", f"/rotulos/{rotulo_id}", {"principal": True})

    def remover_rotulo(self, rotulo_id: int) -> dict[str, Any]:
        return self._escrita("DELETE", f"/rotulos/{rotulo_id}")

    def add_area_conceito(self, conceito_id: int, nome: str) -> dict[str, Any]:
        return self._escrita("POST", f"/conceitos/{conceito_id}/areas", {"nome": nome})

    def rem_area_conceito(self, conceito_id: int, area_id: int) -> dict[str, Any]:
        return self._escrita("DELETE", f"/conceitos/{conceito_id}/areas/{area_id}")

    def merge_conceito(self, alvo_id: int, outro_id: int) -> dict[str, Any]:
        return self._escrita("POST", f"/conceitos/{alvo_id}/merge", {"outro_id": outro_id})

    def split_conceito(self, conceito_id: int, sentido_novo: str,
                       rotulo_ids: list[int], proposicao_ids: list[int]) -> dict[str, Any]:
        return self._escrita("POST", f"/conceitos/{conceito_id}/split",
                             {"sentido_novo": sentido_novo, "rotulo_ids": rotulo_ids,
                              "proposicao_ids": proposicao_ids})

    def criar_proposicao(self, origem_id: int, relacao: str, destino_id: int) -> dict[str, Any]:
        return self._escrita("POST", "/proposicoes",
                             {"origem_id": origem_id, "relacao": relacao, "destino_id": destino_id})

    def editar_proposicao(self, prop_id: int, origem_id: int, relacao: str, destino_id: int) -> dict[str, Any]:
        return self._escrita("PATCH", f"/proposicoes/{prop_id}",
                             {"origem_id": origem_id, "relacao": relacao, "destino_id": destino_id})

    def remover_proposicao(self, prop_id: int) -> dict[str, Any]:
        return self._escrita("DELETE", f"/proposicoes/{prop_id}")

    def criar_area(self, nome: str, parent_id: int | None = None) -> dict[str, Any]:
        return self._escrita("POST", "/areas", {"nome": nome, "parent_id": parent_id})
