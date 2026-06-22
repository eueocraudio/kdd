"""Extração de texto de PDFs (pypdf)."""
from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader


def extrair_texto(caminho: Path, max_chars: int = 60000) -> str:
    """Concatena o texto das páginas, truncando em ``max_chars`` para caber no contexto."""
    leitor = PdfReader(str(caminho))
    partes: list[str] = []
    total = 0
    for pagina in leitor.pages:
        txt = (pagina.extract_text() or "").strip()
        if not txt:
            continue
        partes.append(txt)
        total += len(txt)
        if total >= max_chars:
            break
    return "\n\n".join(partes)[:max_chars]


def extrair_texto_completo(caminho: Path, max_chars_total: int = 400000) -> str:
    """Texto de todas as páginas (cap de segurança alto, para divisão em seções)."""
    leitor = PdfReader(str(caminho))
    partes: list[str] = []
    total = 0
    for pagina in leitor.pages:
        txt = (pagina.extract_text() or "").strip()
        if not txt:
            continue
        partes.append(txt)
        total += len(txt)
        if total >= max_chars_total:
            break
    return "\n\n".join(partes)[:max_chars_total]


def dividir_em_secoes(texto: str, chars_por_secao: int = 15000, max_secoes: int = 0) -> list[str]:
    """Divide o texto em seções de até ``chars_por_secao``, respeitando parágrafos.

    Acumula parágrafos (separados por linha em branco) até o limite; um parágrafo
    maior que o limite vira uma seção própria. ``max_secoes`` > 0 limita a quantidade.
    """
    paragrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    secoes: list[str] = []
    buffer = ""
    for p in paragrafos:
        if buffer and len(buffer) + len(p) + 2 > chars_por_secao:
            secoes.append(buffer)
            buffer = p
        else:
            buffer = f"{buffer}\n\n{p}" if buffer else p
    if buffer:
        secoes.append(buffer)
    if max_secoes > 0:
        secoes = secoes[:max_secoes]
    return secoes


def extrair_secoes(
    caminho: Path,
    chars_por_secao: int = 15000,
    max_chars_total: int = 400000,
    max_secoes: int = 0,
) -> list[str]:
    """Texto completo do PDF dividido em seções para extração incremental."""
    return dividir_em_secoes(
        extrair_texto_completo(caminho, max_chars_total), chars_por_secao, max_secoes
    )
