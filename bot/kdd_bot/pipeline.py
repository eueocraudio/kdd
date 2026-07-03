"""Orquestração: para cada fonte pendente, extrai o mapa e empurra para a API."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from .api_client import KddClient
from .catalogo import conceitos_do_catalogo, fundir_no_mapa
from .config import Config
from .ia.facade import IAFacade
from .pdf import extrair_secoes, extrair_texto

log = logging.getLogger("kdd.bot")


class Pipeline:
    def __init__(self, config: Config, client: KddClient, ia: IAFacade) -> None:
        self._cfg = config
        self._client = client
        self._ia = ia
        self._catalogo_cache: dict | None = None   # carregado 1x por execução

    def _catalogo(self) -> dict:
        """Catálogo de trilhas (GET /catalogo), com cache por execução. Falha ao
        buscar (ex.: API sem a rota ainda) NÃO derruba o processamento — só loga
        e segue sem os conceitos automáticos."""
        if self._catalogo_cache is None:
            try:
                self._catalogo_cache = self._client.obter_catalogo()
                n = sum(len(v) for v in (self._catalogo_cache.get("trilhas") or {}).values())
                log.info("catálogo de trilhas carregado: %d termo(s)", n)
            except Exception as e:  # noqa: BLE001 — o catálogo é um extra
                log.warning("catálogo de trilhas indisponível (%s); seguindo sem ele", e)
                self._catalogo_cache = {}
        return self._catalogo_cache

    def processar_pendentes(self, limite: int | None = None) -> int:
        """Processa as fontes pendentes. ``limite`` > 0 processa no máximo essa
        quantidade nesta execução (proteção de crédito); None ou 0 = sem limite."""
        pendentes = self._client.listar_pendentes()
        total = len(pendentes)
        if limite is not None and limite > 0 and total > limite:
            log.info("fontes pendentes: %d (limitando a %d nesta execução)", total, limite)
            pendentes = pendentes[:limite]
        else:
            log.info("fontes pendentes: %d", total)
        ok = 0
        for fonte in pendentes:
            if self.processar_fonte(fonte):
                ok += 1
        return ok

    def processar_fonte(self, fonte: dict[str, Any]) -> bool:
        fid = int(fonte["id"])
        titulo = fonte.get("titulo") or f"fonte {fid}"
        log.info("[fonte %s] %r — iniciando (backend=%s)", fid, titulo, self._ia.backend_nome)
        try:
            self._client.atualizar_status(fid, "processando")

            with tempfile.TemporaryDirectory() as tmp:
                pdf = self._client.baixar_pdf(fid, Path(tmp) / f"fonte_{fid}.pdf")
                if self._cfg.chars_por_secao > 0:
                    return self._processar_em_secoes(fid, titulo, pdf)
                texto = extrair_texto(pdf, self._cfg.max_chars_pdf)

            if not texto.strip():
                raise RuntimeError("PDF sem texto extraível (talvez digitalizado/sem OCR).")

            mapa = self._ia.extrair_mapa(titulo, texto)
            log.info(
                "[fonte %s] extraído: %d áreas, %d conceitos, %d proposições",
                fid, len(mapa["areas"]), len(mapa["conceitos"]), len(mapa["proposicoes"]),
            )

            # Passo 1: termos do catálogo achados no texto viram conceitos, mesmo
            # que a IA não os tenha citado (docs/catalogo-trilhas.md).
            extras = conceitos_do_catalogo(texto, self._catalogo())
            n_cat = fundir_no_mapa(mapa, extras)
            if n_cat:
                log.info("[fonte %s] catálogo: +%d conceito(s) auto-adicionado(s)", fid, n_cat)

            if mapa["areas"]:
                self._client.atualizar_status(fid, "processando", areas=mapa["areas"])

            res = self._client.enviar_mapa(fid, mapa["conceitos"], mapa["proposicoes"])
            log.info("[fonte %s] enviado: %s", fid, res)
            return True

        except Exception as e:  # noqa: BLE001 — marca a fonte como erro e segue
            log.exception("[fonte %s] FALHOU: %s", fid, e)
            try:
                self._client.atualizar_status(fid, "erro")
            except Exception:  # noqa: BLE001
                log.error("[fonte %s] não consegui marcar status=erro", fid)
            return False

    def _processar_em_secoes(self, fid: int, titulo: str, pdf: Path) -> bool:
        """Extrai o documento inteiro em seções; empurra um mapa por seção.

        O push é idempotente e funde conceitos por SENTIDO, então conceitos
        repetidos entre seções se unificam e proposições recorrentes ganham
        certeza (mais referências da mesma fonte não duplicam, mas conceitos
        que reaparecem consolidam o mapa do documento).
        """
        secoes = extrair_secoes(
            pdf, self._cfg.chars_por_secao, self._cfg.max_chars_total, self._cfg.max_secoes
        )
        if not secoes:
            raise RuntimeError("PDF sem texto extraível (talvez digitalizado/sem OCR).")

        n = len(secoes)
        log.info("[fonte %s] modo seções: %d seção(ões) de ~%d chars",
                 fid, n, self._cfg.chars_por_secao)

        # Passo 1 no modo seções: casa o catálogo sobre TODAS as seções e manda os
        # conceitos num push extra ao final (só se alguma seção foi processada).
        extras_catalogo = conceitos_do_catalogo("\n".join(secoes), self._catalogo())

        total_c = total_p = 0
        for i, secao in enumerate(secoes, start=1):
            titulo_secao = f"{titulo} — seção {i}/{n}"
            try:
                mapa = self._ia.extrair_mapa(titulo_secao, secao)
            except Exception as e:  # noqa: BLE001 — uma seção ruim não derruba o todo
                log.warning("[fonte %s] seção %d/%d falhou (%s); seguindo", fid, i, n, e)
                continue
            if mapa["areas"]:
                self._client.atualizar_status(fid, "processando", areas=mapa["areas"])
            res = self._client.enviar_mapa(fid, mapa["conceitos"], mapa["proposicoes"])
            total_c += len(mapa["conceitos"])
            total_p += len(mapa["proposicoes"])
            log.info("[fonte %s] seção %d/%d: +%d conceitos, +%d proposições (push: %s)",
                     fid, i, n, len(mapa["conceitos"]), len(mapa["proposicoes"]), res.get("ok"))

        # Se TODAS as seções falharam nada foi empurrado (a API nunca marcou
        # processado): marca erro para não sumir da fila como falso sucesso — assim
        # a fonte fica reprocessável (POST /fontes/{id}/reprocessar só age sobre erro).
        if total_c == 0 and total_p == 0:
            self._client.atualizar_status(fid, "erro")
            log.error("[fonte %s] todas as %d seção(ões) falharam na extração; marcada como erro", fid, n)
            return False

        if extras_catalogo:
            res = self._client.enviar_mapa(fid, extras_catalogo, [])
            total_c += len(extras_catalogo)
            log.info("[fonte %s] catálogo: +%d conceito(s) auto-adicionado(s) (push: %s)",
                     fid, len(extras_catalogo), res.get("ok"))

        # garante status processado (cada push já marca, mas reforça)
        self._client.atualizar_status(fid, "processado")
        log.info("[fonte %s] concluído por seções: %d seções, %d conceitos e %d proposições enviados (brutos)",
                 fid, n, total_c, total_p)
        return True
