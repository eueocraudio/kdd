"""Backend local: Ollama (Qwen 3.5), via HTTP, pedindo saída em JSON.

CPU-only e lento na máquina-alvo (Xeon E5-2685 v4, sem GPU); tolerável porque o
pipeline é assíncrono, 1 PDF por vez. Para a extração que importa, prefira Claude.
"""
from __future__ import annotations

import json
from typing import Any

import requests

from .schema import MAPA_SCHEMA, SYSTEM, instrucao_usuario


class OllamaBackend:
    nome = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 1800.0) -> None:
        self._url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def extrair_mapa(self, titulo: str, texto: str) -> dict[str, Any]:
        prompt = (
            instrucao_usuario(titulo, texto)
            + "\n\nResponda APENAS com um JSON que obedeça a este schema:\n"
            + json.dumps(MAPA_SCHEMA, ensure_ascii=False)
        )
        resp = requests.post(
            f"{self._url}/api/chat",
            json={
                "model": self._model,
                "format": "json",
                "stream": False,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        conteudo = resp.json().get("message", {}).get("content", "{}")
        try:
            return json.loads(conteudo)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Ollama devolveu JSON inválido: {e}") from e
