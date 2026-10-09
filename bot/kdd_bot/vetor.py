"""Camada VETORIAL do KDD (docs/valor-conhecimento.md §6).

Embute cada conceito (``"<rótulo>: <sentido>"``) com um modelo de *embedding* do Ollama e
calcula a similaridade de cosseno par a par, gravando na API os pares acima do limiar.

Por que aqui e não na API: a Hostinger não tem tipo VECTOR nem Ollama — o PHP só guarda e
serve. O N é pequeno (centenas/milhares de conceitos), então o produto interno roda aqui.

1º uso: **quase-duplicatas** (sugestão de merge). A identidade do conceito é o SENTIDO
EXATO, então dois sentidos quase iguais ("Protocolo de rede da camada de transporte" ×
"Protocolo da camada de transporte em redes") viram conceitos distintos sem que nada
acuse — é isso que a similaridade pega.

Sem numpy a similaridade é calculada em Python puro (mais lento, mesmo resultado).
"""
from __future__ import annotations

import logging
import math
from typing import Any, Iterable

import requests

log = logging.getLogger(__name__)

try:  # numpy é opcional (não está no requirements do bot)
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None


def texto_do_conceito(conceito: dict[str, Any]) -> str:
    """Texto que representa o conceito no espaço vetorial: rótulo + sentido."""
    rotulo = (conceito.get("rotulo") or "").strip()
    sentido = (conceito.get("sentido") or "").strip()
    if rotulo and sentido and sentido != rotulo:
        return f"{rotulo}: {sentido}"
    return rotulo or sentido


def embutir(textos: list[str], url: str, modelo: str, timeout: float = 120.0) -> list[list[float]]:
    """Chama o Ollama ``/api/embed`` (lote) e devolve um vetor por texto.

    Cai para o endpoint legado ``/api/embeddings`` (um texto por chamada) se o servidor
    for antigo e não conhecer ``/api/embed``.
    """
    if not textos:
        return []
    r = requests.post(f"{url}/api/embed", json={"model": modelo, "input": textos}, timeout=timeout)
    if r.status_code == 404:
        log.info("Ollama sem /api/embed; usando /api/embeddings (1 por chamada)")
        saida = []
        for t in textos:
            rr = requests.post(f"{url}/api/embeddings", json={"model": modelo, "prompt": t}, timeout=timeout)
            rr.raise_for_status()
            saida.append([float(x) for x in rr.json()["embedding"]])
        return saida
    r.raise_for_status()
    dados = r.json()
    vetores = dados.get("embeddings") or []
    if len(vetores) != len(textos):
        raise RuntimeError(f"Ollama devolveu {len(vetores)} vetores para {len(textos)} textos")
    return [[float(x) for x in v] for v in vetores]


def _normalizar_matriz(vetores: list[list[float]]):
    """Normaliza cada vetor para norma 1 — aí o cosseno é só o produto interno."""
    if _np is not None:
        m = _np.asarray(vetores, dtype="float32")
        normas = _np.linalg.norm(m, axis=1, keepdims=True)
        normas[normas == 0] = 1.0
        return m / normas
    saida = []
    for v in vetores:
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        saida.append([x / n for x in v])
    return saida


def pares_semelhantes(
    ids: list[int], vetores: list[list[float]], minimo: float = 0.85, max_pares: int = 5000
) -> list[dict[str, Any]]:
    """Pares (a<b) com cosseno ≥ ``minimo``, do mais parecido para o menos.

    Dimensões divergentes (troca de modelo no meio do caminho) são descartadas: compara-se
    só o grupo da dimensão mais comum.
    """
    if len(ids) < 2:
        return []

    dims = {}
    for v in vetores:
        dims[len(v)] = dims.get(len(v), 0) + 1
    dim = max(dims, key=lambda d: dims[d])
    if len(dims) > 1:
        log.warning("vetores com dimensões diferentes %s; usando só dim=%d", dict(dims), dim)
        filtrados = [(i, v) for i, v in zip(ids, vetores) if len(v) == dim]
        ids = [i for i, _ in filtrados]
        vetores = [v for _, v in filtrados]
        if len(ids) < 2:
            return []

    m = _normalizar_matriz(vetores)
    pares: list[dict[str, Any]] = []

    if _np is not None:
        sim = m @ m.T
        n = len(ids)
        iu = _np.triu_indices(n, k=1)
        valores = sim[iu]
        acima = _np.nonzero(valores >= minimo)[0]
        # ordena os que passaram, do maior para o menor
        acima = acima[_np.argsort(-valores[acima])]
        for k in acima[:max_pares]:
            i, j = int(iu[0][k]), int(iu[1][k])
            a, b = ids[i], ids[j]
            if a > b:
                a, b = b, a
            pares.append({"a": a, "b": b, "similaridade": round(float(valores[k]), 5)})
        return pares

    n = len(ids)
    for i in range(n):
        for j in range(i + 1, n):
            s = sum(x * y for x, y in zip(m[i], m[j]))
            if s >= minimo:
                a, b = ids[i], ids[j]
                if a > b:
                    a, b = b, a
                pares.append({"a": a, "b": b, "similaridade": round(float(s), 5)})
    pares.sort(key=lambda p: -p["similaridade"])
    return pares[:max_pares]


def vetorizar(cliente, config, lote: int = 32) -> dict[str, int]:
    """Passada completa: embute o que falta, recalcula os semelhantes e grava.

    Devolve ``{"embutidos": n, "total": n, "pares": n}``.
    """
    modelo = config.embed_model
    url = config.ollama_url

    faltando = cliente.conceitos_sem_embedding(modelo)
    log.info("vetorização: %d conceito(s) sem vetor no modelo %s", len(faltando), modelo)

    embutidos = 0
    for inicio in range(0, len(faltando), lote):
        bloco = faltando[inicio:inicio + lote]
        textos = [texto_do_conceito(c) for c in bloco]
        try:
            vetores = embutir(textos, url, modelo)
        except Exception as e:  # noqa: BLE001 — um lote ruim não derruba a passada
            log.warning("lote %d-%d falhou ao embutir (%s); seguindo", inicio, inicio + len(bloco), e)
            continue
        for conceito, vetor in zip(bloco, vetores):
            try:
                cliente.gravar_embedding(int(conceito["id"]), modelo, vetor)
                embutidos += 1
            except Exception as e:  # noqa: BLE001
                log.warning("conceito %s: falha ao gravar vetor (%s)", conceito.get("id"), e)
        log.info("vetorização: %d/%d embutidos", embutidos, len(faltando))

    todos = cliente.listar_embeddings(modelo)
    ids = [int(e["conceito_id"]) for e in todos]
    vetores = [e["vetor"] for e in todos]
    pares = pares_semelhantes(ids, vetores, config.similar_min)
    log.info("vetorização: %d conceito(s) vetorizado(s), %d par(es) ≥ %.2f",
             len(ids), len(pares), config.similar_min)

    if ids:
        cliente.gravar_similares(modelo, pares)
    return {"embutidos": embutidos, "total": len(ids), "pares": len(pares)}
