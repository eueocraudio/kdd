"""Extração de texto de PDFs (pypdf)."""
from __future__ import annotations

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
