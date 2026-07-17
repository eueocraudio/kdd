"""Backend rolhama: extrai o mapa via o CONCENTRADOR rolhama (webapi -> ollama na .90).

Em vez de bater direto no ollama (o que colidiria com os outros consumidores no slot
único), enfileira o pedido num canal do rolhama (webapi PHP+MySQL): `enqueue` devolve o
UUID do job e o worker (thread única) executa UM por vez e publica a resposta, lida pelo
job. Manda `format=json` para forçar JSON válido (saída estruturada) — o modelo default é
o qwen2.5:14b-instruct. A saída passa por `normalizar` na fachada, como os outros backends.

O payload continua cifrado ponta a ponta pelo `bdd.py` (ChaCha20-Poly1305 por
`(part, canal)`); o `webapi.py` cuida só do transporte e do MAC de autenticação (K_auth).
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from . import bdd, webapi
from .schema import MAPA_SCHEMA, SYSTEM, instrucao_usuario


class RolhamaBackend:
    nome = "rolhama"

    def __init__(self, url: str, key: str, channel: int, model: str = "",
                 wait_total: float = 3600.0, poll: int = 30) -> None:
        if not key:
            raise RuntimeError("Backend rolhama: defina ROLHAMA_BDD_KEY no ambiente ou ~/.env.")
        self._url = url
        self._key = key                                    # necessário para o k_auth do webapi
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

        # Fila por canal: enfileira o pedido cifrado e acompanha o MEU job pelo UUID.
        # Sem 409/remove() — a fila aceita vários jobs; o worker executa um por vez.
        api = webapi.ClientAPI(self._url, self._channel, webapi.k_auth(self._key, self._channel))
        job = api.enqueue(bdd.seal(self._secret, "request", self._channel,
                                   json.dumps(pedido, ensure_ascii=False).encode("utf-8")))

        t0 = time.time()
        while time.time() - t0 < self._wait_total:
            resp = api.response(job, wait=self._poll)
            if resp is not None:
                texto_resp = bdd.open_blob(self._secret, "response", self._channel, resp).decode("utf-8", "replace")
                try:
                    return json.loads(texto_resp)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"rolhama devolveu JSON inválido: {e}") from e
        raise RuntimeError(f"rolhama: sem resposta após {self._wait_total:.0f}s (job {job}, canal {self._channel})")
