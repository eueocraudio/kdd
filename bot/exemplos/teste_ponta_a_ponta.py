#!/usr/bin/env python3
"""Teste ponta a ponta do bot, usando o PDF de exemplo.

Faz tudo o que um operador + o bot fariam, numa tacada:
  1. gera/garante o PDF de exemplo (exemplos/botafogo.pdf);
  2. faz upload via POST /fontes (vira fonte pendente);
  3. roda o bot UMA vez (baixa, extrai, chama a IA, empurra o mapa);
  4. consulta a API e imprime os conceitos e a constelação resultantes.

Pré-requisitos no ~/.env (ou ambiente):
  KDD_APP_URL, KDD_TOKEN_OPERADOR e — para o backend Claude — ANTHROPIC_API_KEY.
Sem ANTHROPIC_API_KEY e sem Ollama, o passo 3 falha de propósito (marca a fonte
como 'erro') e o script avisa.

Uso:
  bot/.venv/bin/python exemplos/teste_ponta_a_ponta.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from kdd_bot.api_client import KddClient
from kdd_bot.config import Config
from kdd_bot.ia.facade import IAFacade
from kdd_bot.pipeline import Pipeline
from exemplos.gerar_pdf_exemplo import construir_pdf, LINHAS

PDF = Path(__file__).with_name("botafogo.pdf")


def _cabecalho(cfg: Config) -> dict[str, str]:
    return {"X-Token": cfg.token}


def main() -> int:
    cfg = Config.carregar()
    print(f"API: {cfg.base_url} | backend: {cfg.backend} | Claude key? {bool(cfg.anthropic_api_key)}")

    if not PDF.is_file():
        PDF.write_bytes(construir_pdf(LINHAS))
    print(f"PDF: {PDF} ({PDF.stat().st_size} bytes)")

    # 1) upload (papel do operador)
    with PDF.open("rb") as fh:
        resp = requests.post(
            f"{cfg.base_url}/fontes",
            headers=_cabecalho(cfg),
            files={"arquivo": ("botafogo.pdf", fh, "application/pdf")},
            data={"titulo": "Botafogo (exemplo)"},
            timeout=60,
        )
    resp.raise_for_status()
    fonte = resp.json().get("fonte", resp.json())  # a API responde {"fonte": {...}}
    fid = int(fonte["id"])
    print(f"[upload] fonte criada: id={fid} status={fonte.get('status_proc')}")

    # 2) roda o bot uma vez
    client = KddClient(cfg)
    ia = IAFacade.a_partir_de(cfg)
    print(f"[bot] backend de IA: {ia.backend_nome} — processando pendentes...")
    ok = Pipeline(cfg, client, ia).processar_pendentes()
    print(f"[bot] fontes processadas com sucesso: {ok}")

    # 3) mostra o resultado
    print("\n=== CONCEITOS no armazém ===")
    conc = requests.get(f"{cfg.base_url}/conceitos", headers=_cabecalho(cfg), timeout=30).json()
    for c in conc.get("conceitos", conc if isinstance(conc, list) else []):
        print(" -", c)

    print("\n=== CONSTELAÇÃO ===")
    const = requests.get(f"{cfg.base_url}/constelacao", headers=_cabecalho(cfg), timeout=30).json()
    print(const)

    print(
        "\nDica: a fonte fica 'processado' mas a certeza só sobe após o validador "
        f"aprovar (POST /fontes/{fid}/aprovar)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
