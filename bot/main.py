#!/usr/bin/env python3
"""Bot KDD — ponto de entrada.

Uso:
  python main.py            # processa as fontes pendentes uma vez
  python main.py --loop     # fica observando, processando a cada intervalo
  python main.py --loop --intervalo 120
"""
from __future__ import annotations

import argparse
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
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = Config.carregar()
        client = KddClient(config)
        ia = IAFacade.a_partir_de(config)
    except RuntimeError as e:
        print(f"Configuração inválida: {e}", file=sys.stderr)
        return 1

    pipeline = Pipeline(config, client, ia)

    if not args.loop:
        pipeline.processar_pendentes()
        return 0

    logging.getLogger("kdd.bot").info("modo loop: a cada %ds", args.intervalo)
    while True:
        try:
            pipeline.processar_pendentes()
        except Exception:  # noqa: BLE001 — loop resiliente
            logging.getLogger("kdd.bot").exception("erro na varredura; seguindo")
        time.sleep(args.intervalo)


if __name__ == "__main__":
    sys.exit(main())
