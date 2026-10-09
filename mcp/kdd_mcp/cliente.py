"""Cliente HTTP da Web API do KDD, para o servidor MCP.

Adaptador FINO (docs/mcp-servidor.md §2): nenhuma regra de domínio aqui. A API é a fonte da
verdade — valor, certeza, identidade por sentido e changesets são calculados lá.
"""
from __future__ import annotations

from typing import Any

import requests


class KddErro(Exception):
    """Erro vindo da API, já com mensagem legível para o modelo ler."""


class KddCliente:
    def __init__(self, config) -> None:  # noqa: ANN001
        self._cfg = config
        self._s = requests.Session()
        self._s.headers.update({"X-Token": config.token, "Accept": "application/json"})

    # ── infraestrutura ──

    def _url(self, caminho: str) -> str:
        return f"{self._cfg.base_url}{caminho}"

    @staticmethod
    def _corpo(r: requests.Response) -> dict[str, Any]:
        try:
            dados = r.json()
            return dados if isinstance(dados, dict) else {"dados": dados}
        except ValueError:
            return {}

    def _checar(self, r: requests.Response) -> dict[str, Any]:
        if r.status_code == 401:
            raise KddErro(
                "HTTP 401: token recusado pela API do KDD. Confira KDD_TOKEN_OPERADOR "
                "(ou KDD_TOKEN) no ambiente ou em ~/.env."
            )
        if r.status_code >= 400:
            msg = self._corpo(r).get("erro") or (r.text[:300] if r.text else "sem detalhe")
            raise KddErro(f"HTTP {r.status_code}: {msg}")
        return self._corpo(r)

    def _get(self, caminho: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        limpos = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        try:
            r = self._s.get(self._url(caminho), params=limpos, timeout=self._cfg.timeout)
        except requests.RequestException as e:
            raise KddErro(f"Falha de rede ao chamar a API do KDD: {e}") from e
        return self._checar(r)

    def _post(self, caminho: str, corpo: dict[str, Any]) -> dict[str, Any]:
        """POST de curadoria: usa o token de VALIDADOR (a API exige esse perfil na escrita)."""
        cabecalhos = {"X-Token": self._cfg.token_validador or self._cfg.token}
        try:
            r = self._s.post(self._url(caminho), json=corpo, headers=cabecalhos,
                             timeout=self._cfg.timeout)
        except requests.RequestException as e:
            raise KddErro(f"Falha de rede ao escrever na API do KDD: {e}") from e
        return self._checar(r)

    # ── leitura ──

    def saude(self) -> dict[str, Any]:
        return self._get("/health")

    def universos(self) -> list[dict[str, Any]]:
        return self._get("/universos").get("universos", [])

    def conceitos(self, q: str = "", area: str = "", fonte: int | None = None,
                  universo: str = "") -> list[dict[str, Any]]:
        return self._get("/conceitos", {"q": q, "area": area, "fonte": fonte,
                                        "universo": universo}).get("conceitos", [])

    def conceito(self, conceito_id: int) -> dict[str, Any]:
        # id é global; a resposta diz o universo
        return self._get(f"/conceitos/{conceito_id}").get("conceito", {})

    def contrapartes(self, conceito_id: int) -> dict[str, Any]:
        return self._get(f"/conceitos/{conceito_id}/contrapartes")

    def areas(self, universo: str = "") -> list[dict[str, Any]]:
        return self._get("/areas", {"universo": universo}).get("areas", [])

    def proposicoes(self, conceito: int | None = None, universo: str = "") -> list[dict[str, Any]]:
        return self._get("/proposicoes", {"conceito": conceito,
                                          "universo": universo}).get("proposicoes", [])

    def esteios(self, limite: int = 20, universo: str = "") -> list[dict[str, Any]]:
        return self._get("/esteios", {"limite": limite, "universo": universo}).get("esteios", [])

    def constelacao(self, universo: str = "") -> dict[str, Any]:
        return self._get("/constelacao", {"universo": universo})

    def similares(self, minimo: float = 0.85, limite: int = 50,
                  escopo: str = "interno") -> list[dict[str, Any]]:
        return self._get("/similares", {"min": minimo, "limite": limite,
                                        "escopo": escopo}).get("similares", [])

    def mapa_da_fonte(self, fonte_id: int) -> dict[str, Any]:
        return self._get(f"/fontes/{fonte_id}/mapa")

    def fontes(self, status_proc: str = "", status_aprovacao: str = "",
               universo: str = "") -> list[dict[str, Any]]:
        return self._get("/fontes", {
            "status_proc": status_proc, "status_aprovacao": status_aprovacao,
            "universo": universo,
        }).get("fontes", [])

    # ── escrita (só registrada quando KDD_MCP_ESCRITA=1 + token de validador) ──

    def ingerir_texto(self, titulo: str, texto: str, contexto: str = "", ref: str = "",
                      universo: str = "") -> dict[str, Any]:
        corpo = {"titulo": titulo, "texto": texto}
        if contexto:
            corpo["contexto"] = contexto
        if ref:
            corpo["ref"] = ref
        if universo:
            corpo["universo"] = universo
        return self._post("/fontes/texto", corpo)

    def criar_conceito(self, sentido: str, rotulo_principal: str,
                       areas: list[str] | None = None, tipo: str = "",
                       universo: str = "") -> dict[str, Any]:
        corpo = {
            "sentido": sentido, "rotulo_principal": rotulo_principal,
            "areas": areas or [], "tipo": tipo or None,
        }
        if universo:
            corpo["universo"] = universo
        return self._post("/conceitos", corpo)

    def criar_proposicao(self, origem_id: int, relacao: str, destino_id: int) -> dict[str, Any]:
        return self._post("/proposicoes", {
            "origem_id": origem_id, "relacao": relacao, "destino_id": destino_id,
        })
