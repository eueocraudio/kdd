#!/usr/bin/env python3
"""Bot KDD — ponto de entrada.

Uso:
  python main.py            # processa as fontes pendentes uma vez
  python main.py --loop     # fica observando, processando a cada intervalo
  python main.py --loop --intervalo 120
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
import time

from kdd_bot.api_client import KddClient
from kdd_bot.config import Config
from kdd_bot.ia.facade import IAFacade
from kdd_bot.pipeline import Pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Bot de ingestão KDD")
    parser.add_argument("--loop", action="store_true", help="processar continuamente")
    parser.add_argument("--intervalo", type=int, default=60, help="segundos entre varreduras no modo loop")
    parser.add_argument(
        "--backend",
        # TEMPORÁRIO: Claude (claude/cli) desativado — só Ollama por enquanto.
        # Para reativar, restaure as escolhas ["auto", "claude", "ollama", "cli"].
        choices=["auto", "ollama"],
        help="backend de IA (sobrepõe KDD_IA_BACKEND; padrão: o do ambiente/~/.env)",
    )
    parser.add_argument(
        "--max-fontes",
        type=int,
        default=None,
        help="máximo de fontes por execução (proteção de crédito; 0 = sem limite). "
             "Em backend pago (cli/claude) sem este parâmetro, o padrão é 1.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("kdd.bot")

    try:
        config = Config.carregar()
        if args.backend:
            config = dataclasses.replace(config, backend=args.backend)
        client = KddClient(config)
        ia = IAFacade.a_partir_de(config)
    except RuntimeError as e:
        print(f"Configuração inválida: {e}", file=sys.stderr)
        return 1

    # Proteção de crédito: backends pagos avisam e, sem --max-fontes, limitam a 1/execução.
    PAGOS = {"cli", "claude"}
    limite = args.max_fontes
    if ia.backend_nome in PAGOS:
        log.warning("backend PAGO em uso: %s — cada fonte consome crédito.", ia.backend_nome)
        if limite is None:
            limite = 1
            log.warning(
                "sem --max-fontes: limitando a 1 fonte nesta execução (proteção de crédito). "
                "Use --max-fontes N para processar mais, ou --max-fontes 0 para sem limite."
            )

    pipeline = Pipeline(config, client, ia)

    if not args.loop:
        pipeline.processar_pendentes(limite)
        return 0

    log.info("modo loop: a cada %ds", args.intervalo)
    while True:
        try:
            pipeline.processar_pendentes(limite)
        except Exception:  # noqa: BLE001 — loop resiliente
            log.exception("erro na varredura; seguindo")
        time.sleep(args.intervalo)


if __name__ == "__main__":
    sys.exit(main())
