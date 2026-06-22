"""Extração de texto de documentos (PDF via pypdf; TXT direto).

O tipo é detectado pelo CONTEÚDO (assinatura %PDF), porque o nome do arquivo
baixado pelo bot não preserva a extensão original.
"""
from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader


def _e_pdf(caminho: Path) -> bool:
    try:
        with open(caminho, "rb") as fh:
            return fh.read(5).startswith(b"%PDF")
    except OSError:
        return False


def _texto_de_pdf(caminho: Path, max_chars: int) -> str:
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


def _texto_bruto(caminho: Path, max_chars: int) -> str:
    """Texto do documento (PDF ou TXT), truncado em ``max_chars``."""
    if _e_pdf(caminho):
        return _texto_de_pdf(caminho, max_chars)
    # TXT (ou qualquer texto): lê como UTF-8, tolerante a bytes inválidos
    return caminho.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def extrair_texto(caminho: Path, max_chars: int = 60000) -> str:
    """Texto do documento (PDF/TXT), truncado para caber no contexto."""
    return _texto_bruto(caminho, max_chars)


def extrair_texto_completo(caminho: Path, max_chars_total: int = 400000) -> str:
    """Texto completo (cap de segurança alto), para divisão em seções."""
    return _texto_bruto(caminho, max_chars_total)


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
    """Texto completo do documento dividido em seções para extração incremental."""
    return dividir_em_secoes(
        extrair_texto_completo(caminho, max_chars_total), chars_por_secao, max_secoes
    )
