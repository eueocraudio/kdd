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
