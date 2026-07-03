"""Catálogo de trilhas (Passo 1): termos/paths conhecidos que valem como conceito.

Regras (docs/catalogo-trilhas.md):
- o catálogo vem da API (GET /catalogo) — termo → lista de trilhas (a trilha NÃO
  entra na identidade do conceito, só existe para curadoria);
- PATH (termo com "/" ou "\\"): substring, case-sensitive;
- TERMO (demais): palavra inteira, case-insensitive — ``cron`` não casa em
  ``crontab``; ``ssh`` casa ``SSH``;
- cada termo casado vira um conceito do MAPA_SCHEMA com sentido ESTÁVEL (a
  identidade do KDD é o sentido; mudar a frase criaria conceito novo a cada push).
"""
from __future__ import annotations

import re

SENTIDO_PATH = "Caminho/arquivo de sistema conhecido: {termo}"
SENTIDO_TERMO = "Termo técnico do catálogo de trilhas: {termo}"


def achatar_catalogo(catalogo: dict) -> dict[str, list[str]]:
    """``{trilhas: {slug: [termos]}}`` → ``{termo: [slugs]}`` (união das trilhas)."""
    plano: dict[str, list[str]] = {}
    for slug, termos in (catalogo.get("trilhas") or {}).items():
        if not isinstance(termos, list):
            continue
        for t in termos:
            t = str(t).strip()
            if not t:
                continue
            plano.setdefault(t, [])
            if slug not in plano[t]:
                plano[t].append(slug)
    return plano


def _e_path(termo: str) -> bool:
    return "/" in termo or "\\" in termo


def _casa(termo: str, texto: str) -> bool:
    if _e_path(termo):
        return termo in texto  # substring, case-sensitive
    # palavra inteira, case-insensitive; lookaround em vez de \b para termos que
    # começam/terminam em não-letra (ex.: "802.1Q")
    padrao = r"(?<!\w)" + re.escape(termo) + r"(?!\w)"
    return re.search(padrao, texto, flags=re.IGNORECASE) is not None


def conceitos_do_catalogo(texto: str, catalogo: dict) -> list[dict]:
    """Conceitos (formato do MAPA_SCHEMA) dos termos do catálogo achados no texto."""
    if not texto or not catalogo:
        return []
    conceitos = []
    for termo in achatar_catalogo(catalogo):
        if not _casa(termo, texto):
            continue
        sentido = (SENTIDO_PATH if _e_path(termo) else SENTIDO_TERMO).format(termo=termo)
        conceitos.append({"rotulo": termo, "sentido": sentido, "areas": []})
    return conceitos


def fundir_no_mapa(mapa: dict, extras: list[dict]) -> int:
    """Anexa ``extras`` a ``mapa["conceitos"]`` sem duplicar sentido (o push da API
    também dedupa por sentido; aqui é só para contagem/log honestos). Retorna
    quantos entraram de fato."""
    if not extras:
        return 0
    vistos = {str(c.get("sentido", "")).strip() for c in mapa.get("conceitos", [])}
    novos = 0
    for c in extras:
        if c["sentido"] in vistos:
            continue
        mapa.setdefault("conceitos", []).append(c)
        vistos.add(c["sentido"])
        novos += 1
    return novos
