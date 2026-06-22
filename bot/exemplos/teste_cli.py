#!/usr/bin/env python3
"""Teste ponta a ponta do bot via backend CLI (Claude pela linha de comando).

Sobe um PDF que você indicar, roda o bot SÓ para essa fonte usando o backend `cli`
(o CLI `claude`/Claude Code, sem precisar de ANTHROPIC_API_KEY) e mostra o resultado.

Uso:
  bot/.venv/bin/python exemplos/teste_cli.py CAMINHO/DO/ARQUIVO.pdf
  bot/.venv/bin/python exemplos/teste_cli.py ~/Downloads/meu.pdf --titulo "Meu título"
  bot/.venv/bin/python exemplos/teste_cli.py meu.pdf --backend ollama   # outro backend

Pré-requisitos no ~/.env (ou ambiente): KDD_APP_URL e KDD_TOKEN_OPERADOR.
Para o backend `cli`, o CLI `claude` precisa estar instalado e logado nesta máquina.

ATENÇÃO: `cli`/`claude` consomem crédito. Este script processa UMA fonte (a que você
subir), então o gasto é de exatamente uma extração.
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from kdd_bot.api_client import KddClient
from kdd_bot.config import Config
from kdd_bot.ia.facade import IAFacade
from kdd_bot.pipeline import Pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste ponta a ponta do bot (1 PDF) via backend CLI")
    parser.add_argument("pdf", type=Path, help="caminho do PDF a ingerir")
    parser.add_argument("--titulo", help="título da fonte (padrão: nome do arquivo)")
    parser.add_argument(
        "--backend",
        default="cli",
        choices=["cli", "claude", "ollama", "auto"],
        help="backend de IA (padrão: cli)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    pdf = args.pdf.expanduser()
    if not pdf.is_file():
        print(f"PDF não encontrado: {pdf}", file=sys.stderr)
        return 1

    cfg = dataclasses.replace(Config.carregar(), backend=args.backend)
    ia = IAFacade.a_partir_de(cfg)
    titulo = args.titulo or pdf.stem
    print(f"API: {cfg.base_url} | backend: {ia.backend_nome} | PDF: {pdf} ({pdf.stat().st_size} bytes)")
    if ia.backend_nome in {"cli", "claude"}:
        print("⚠️  backend PAGO — esta execução consome crédito (1 extração).")

    # 1) upload (papel do operador). A API responde {"fonte": {...}}.
    with pdf.open("rb") as fh:
        resp = requests.post(
            f"{cfg.base_url}/fontes",
            headers={"X-Token": cfg.token},
            files={"arquivo": (pdf.name, fh, "application/pdf")},
            data={"titulo": titulo},
            timeout=120,
        )
    resp.raise_for_status()
    fonte = resp.json().get("fonte", resp.json())
    fid = int(fonte["id"])
    print(f"[upload] fonte criada: id={fid} status={fonte.get('status_proc')}")

    # 2) processa SÓ esta fonte (não toca nas outras pendentes)
    client = KddClient(cfg)
    if not Pipeline(cfg, client, ia).processar_fonte(fonte):
        print(f"[bot] FALHOU ao processar a fonte {fid} (veja o log acima).", file=sys.stderr)
        return 1

    # 3) resumo do resultado
    det = requests.get(f"{cfg.base_url}/fontes/{fid}", headers={"X-Token": cfg.token}, timeout=30).json()
    f = det.get("fonte", det)
    print("\n=== RESULTADO ===")
    print(f"fonte {fid}: {f.get('titulo')}")
    print(f"status: {f.get('status_proc')} / aprovação: {f.get('status_aprovacao')}")
    print(f"áreas: {f.get('areas')}")
    print(
        f"\nMapa no armazém. Para a certeza subir, aprove: "
        f"POST {cfg.base_url}/fontes/{fid}/aprovar"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
