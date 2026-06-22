#!/usr/bin/env python3
"""Gera um PDF de exemplo com texto extraível (pypdf), em Python puro.

Não tem dependências: monta um PDF mínimo válido com os offsets do xref
calculados na hora. Serve para testar o pipeline do bot ponta a ponta.

Uso: python exemplos/gerar_pdf_exemplo.py [saida.pdf]
"""
from __future__ import annotations

import sys
from pathlib import Path

# Linhas de texto do "documento". Cada uma vira um Tj numa nova linha.
LINHAS = [
    "Botafogo de Futebol e Regatas foi fundado em 1894 na cidade do Rio de Janeiro.",
    "O Botafogo manda seus jogos no Estadio Nilton Santos, conhecido como Engenhao.",
    "Joao Saldanha, jornalista e tecnico, torcia pelo Botafogo e nasceu no Rio Grande do Sul.",
    "O bairro de Botafogo fica na Zona Sul do Rio de Janeiro, as margens da Baia de Guanabara.",
    "Garrincha, idolo do clube, e considerado um dos maiores dribladores da historia do futebol.",
]


def _escape(texto: str) -> str:
    return texto.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def construir_pdf(linhas: list[str]) -> bytes:
    # Stream de conteudo: posiciona e escreve cada linha.
    corpo = ["BT", "/F1 14 Tf", "72 760 Td", "16 TL"]
    for i, ln in enumerate(linhas):
        if i > 0:
            corpo.append("T*")
        corpo.append(f"({_escape(ln)}) Tj")
    corpo.append("ET")
    conteudo = "\n".join(corpo).encode("latin-1")

    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(conteudo), conteudo),
    ]

    saida = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(saida))
        saida += b"%d 0 obj\n%s\nendobj\n" % (i, obj)

    xref_pos = len(saida)
    n = len(objetos) + 1
    saida += b"xref\n0 %d\n" % n
    saida += b"0000000000 65535 f \n"
    for off in offsets:
        saida += b"%010d 00000 n \n" % off
    saida += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % n
    saida += b"startxref\n%d\n%%%%EOF\n" % xref_pos
    return bytes(saida)


def main() -> int:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("botafogo.pdf")
    destino.write_bytes(construir_pdf(LINHAS))
    print(f"PDF de exemplo gerado: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
