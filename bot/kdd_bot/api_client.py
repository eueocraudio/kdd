"""Cliente HTTP do bot para o armazém KDD (lado de ingestão)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from .config import Config


class KddApiError(RuntimeError):
    pass


class KddClient:
    def __init__(self, config: Config, timeout: tuple[float, float] = (10.0, 60.0)) -> None:
        # timeout = (conexão, leitura): limita tanto o connect quanto respostas
        # que travam no meio do corpo (evita pendurar indefinidamente).
        self._cfg = config
        self._timeout = timeout
        self._s = requests.Session()
        self._s.headers.update({"X-Token": config.token})

    def _url(self, caminho: str) -> str:
        return f"{self._cfg.base_url}{caminho}"

    @staticmethod
    def _corpo_json(r: requests.Response) -> dict[str, Any]:
        """Decodifica o corpo como JSON; {} se vazio ou não-JSON (ex.: HTML de proxy)."""
        if not r.content:
            return {}
        try:
            data = r.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _ok(self, r: requests.Response) -> dict[str, Any]:
        if r.status_code >= 400:
            msg = self._corpo_json(r).get("erro") or (r.text[:500] if r.text else "")
            raise KddApiError(f"HTTP {r.status_code}: {msg}")
        return self._corpo_json(r)

    def listar_pendentes(self) -> list[dict[str, Any]]:
        r = self._s.get(self._url("/fontes"), params={"status_proc": "pendente"}, timeout=self._timeout)
        return self._ok(r).get("fontes", [])

    def baixar_pdf(self, fonte_id: int, destino: Path) -> Path:
        r = self._s.get(self._url(f"/fontes/{fonte_id}/arquivo"), timeout=self._timeout, stream=True)
        if r.status_code >= 400:
            raise KddApiError(f"HTTP {r.status_code} ao baixar PDF da fonte {fonte_id}")
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=8192):
                fh.write(chunk)
        return destino

    def atualizar_status(self, fonte_id: int, status_proc: str, areas: list[str] | None = None) -> dict[str, Any]:
        corpo: dict[str, Any] = {"status_proc": status_proc}
        if areas:
            corpo["areas"] = areas
        r = self._s.patch(self._url(f"/fontes/{fonte_id}"), json=corpo, timeout=self._timeout)
        return self._ok(r)

    def obter_catalogo(self) -> dict[str, Any]:
        """GET /catalogo — termos/paths conhecidos por trilha (Passo 1)."""
        r = self._s.get(self._url("/catalogo"), timeout=self._timeout)
        return self._ok(r)

    def enviar_mapa(self, fonte_id: int, conceitos: list[dict], proposicoes: list[dict]) -> dict[str, Any]:
        corpo = {"conceitos": conceitos, "proposicoes": proposicoes}
        r = self._s.post(self._url(f"/fontes/{fonte_id}/mapas"), json=corpo, timeout=self._timeout)
        return self._ok(r)

    # ── camada vetorial (docs/valor-conhecimento.md §6) ──

    def conceitos_sem_embedding(self, modelo: str) -> list[dict[str, Any]]:
        """GET /embeddings?faltando=1 — conceitos ainda sem vetor neste modelo."""
        r = self._s.get(self._url("/embeddings"), params={"modelo": modelo, "faltando": 1},
                        timeout=self._timeout)
        return self._ok(r).get("conceitos", [])

    def listar_embeddings(self, modelo: str) -> list[dict[str, Any]]:
        """GET /embeddings — todos os vetores do modelo (para o cosseno par a par)."""
        r = self._s.get(self._url("/embeddings"), params={"modelo": modelo},
                        timeout=(self._timeout[0], max(self._timeout[1], 180.0)))
        return self._ok(r).get("embeddings", [])

    def gravar_embedding(self, conceito_id: int, modelo: str, vetor: list[float]) -> dict[str, Any]:
        r = self._s.put(self._url(f"/conceitos/{conceito_id}/embedding"),
                        json={"modelo": modelo, "vetor": vetor}, timeout=self._timeout)
        return self._ok(r)

    def gravar_similares(self, modelo: str, pares: list[dict[str, Any]]) -> dict[str, Any]:
        """PUT /similares — SUBSTITUI os pares do modelo (recálculo integral)."""
        r = self._s.put(self._url("/similares"), json={"modelo": modelo, "pares": pares},
                        timeout=(self._timeout[0], max(self._timeout[1], 180.0)))
        return self._ok(r)
