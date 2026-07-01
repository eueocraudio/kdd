"""Backend rolhama: extrai o mapa via o CONCENTRADOR rolhama (bddphp -> ollama na .90).

Em vez de bater direto no ollama (o que colidiria com os outros consumidores no slot
único), sela o pedido num canal do bddphp; o concentrador rolhama (thread única) executa
UM por vez e devolve a resposta. Manda `format=json` para forçar JSON válido (saída
estruturada) — o modelo default é o qwen2.5:14b-instruct. A saída passa por `normalizar`
na fachada, como os outros backends.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from . import bdd
from .schema import MAPA_SCHEMA, SYSTEM, instrucao_usuario


class RolhamaBackend:
    nome = "rolhama"

    def __init__(self, url: str, key: str, channel: int, model: str = "",
                 wait_total: float = 3600.0, poll: int = 30) -> None:
        if not key:
            raise RuntimeError("Backend rolhama: defina ROLHAMA_BDD_KEY no ambiente ou ~/.env.")
        self._url = url
        self._secret = hashlib.sha256(key.encode()).digest()
        self._channel = int(channel)
        self._model = model or ""
        self._wait_total = float(wait_total)
        self._poll = int(poll)

    def extrair_mapa(self, titulo: str, texto: str) -> dict[str, Any]:
        prompt = (
            SYSTEM + "\n\n"
            + instrucao_usuario(titulo, texto)
            + "\n\nResponda APENAS com um JSON (sem markdown, sem texto ao redor) que "
            "obedeça a este schema:\n"
            + json.dumps(MAPA_SCHEMA, ensure_ascii=False)
        )
        pedido: dict[str, Any] = {"prompt": prompt, "format": "json"}
        if self._model:
            pedido["model"] = self._model

        c = bdd.Client(self._url, self._secret)
        # canal é um-por-um: limpa restos antes de selar.
        c.remove("request", self._channel)
        c.remove("response", self._channel)
        status = c.send("request", self._channel,
                        json.dumps(pedido, ensure_ascii=False).encode("utf-8"))
        if status != 201:
            raise RuntimeError(f"rolhama: PUT request devolveu {status} (canal {self._channel} ocupado?)")

        t0 = time.time()
        while time.time() - t0 < self._wait_total:
            resp = c.receive("response", self._channel, wait=self._poll)
            if resp is not None:
                texto_resp = resp.decode("utf-8", "replace")
                try:
                    return json.loads(texto_resp)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"rolhama devolveu JSON inválido: {e}") from e
        raise RuntimeError(f"rolhama: sem resposta após {self._wait_total:.0f}s (canal {self._channel})")
