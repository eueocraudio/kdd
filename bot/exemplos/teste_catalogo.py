#!/usr/bin/env python3
"""Teste do Passo 1 (catálogo de trilhas) — docs/catalogo-trilhas.md.

Duas partes:
  A) OFFLINE (sempre roda, sem rede/LLM): casos do matcher —
     path case-sensitive, palavra inteira case-insensitive, cron × crontab,
     dedup por sentido ao fundir no mapa.
  B) E2E SEM LLM (só se houver API local + token): sobe uma fonte de texto com
     termos do catálogo, roda o Pipeline com uma IA *stub* (mapa vazio) e confere
     via GET /fontes/{id}/mapa que os conceitos do catálogo foram materializados.

Uso:
  bot/.venv/bin/python exemplos/teste_catalogo.py
  KDD_APP_URL=http://localhost:8000 KDD_TOKEN_OPERADOR=... \\
    bot/.venv/bin/python exemplos/teste_catalogo.py     # inclui a parte B
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kdd_bot.catalogo import (
    achatar_catalogo,
    conceitos_do_catalogo,
    fundir_no_mapa,
)

CATALOGO_FAKE = {
    "trilhas": {
        "linux-sysadmin": ["/etc/passwd", "cron", "SSH", "umask"],
        "noc": ["VLAN", "802.1Q", "SSH"],   # SSH em 2 trilhas (união)
    }
}

_falhas: list[str] = []


def checa(cond: bool, descricao: str) -> None:
    print(("  PASS: " if cond else "  FALHA: ") + descricao)
    if not cond:
        _falhas.append(descricao)


def parte_a_offline() -> None:
    print("=== A) matcher offline ===")

    plano = achatar_catalogo(CATALOGO_FAKE)
    checa(sorted(plano["SSH"]) == ["linux-sysadmin", "noc"], "SSH acumula as 2 trilhas (união)")

    # path: substring case-sensitive
    r = [c["rotulo"] for c in conceitos_do_catalogo("cat /etc/passwd | wc -l", CATALOGO_FAKE)]
    checa("/etc/passwd" in r, "path /etc/passwd casa por substring")
    r = [c["rotulo"] for c in conceitos_do_catalogo("olha o /ETC/PASSWD", CATALOGO_FAKE)]
    checa("/etc/passwd" not in r, "path é case-sensitive (/ETC/PASSWD não casa)")

    # termo: palavra inteira, case-insensitive
    r = [c["rotulo"] for c in conceitos_do_catalogo("configure o SSH e a VLAN", CATALOGO_FAKE)]
    checa("SSH" in r and "VLAN" in r, "termos SSH e VLAN casam")
    r = [c["rotulo"] for c in conceitos_do_catalogo("acesso via ssh remoto", CATALOGO_FAKE)]
    checa("SSH" in r, "termo é case-insensitive (ssh casa SSH)")

    # palavra inteira: cron NÃO casa dentro de crontab
    r = [c["rotulo"] for c in conceitos_do_catalogo("editando o crontab do sistema", CATALOGO_FAKE)]
    checa("cron" not in r, "cron NÃO casa dentro de crontab (palavra inteira)")
    r = [c["rotulo"] for c in conceitos_do_catalogo("agende no cron, por favor", CATALOGO_FAKE)]
    checa("cron" in r, "cron casa como palavra isolada")

    # termo com pontuação nas bordas (802.1Q)
    r = [c["rotulo"] for c in conceitos_do_catalogo("tag 802.1Q no trunk", CATALOGO_FAKE)]
    checa("802.1Q" in r, "802.1Q casa mesmo com ponto/dígito")

    # sentido estável e por tipo
    c_path = conceitos_do_catalogo("/etc/passwd", CATALOGO_FAKE)[0]
    c_termo = conceitos_do_catalogo("SSH", CATALOGO_FAKE)[0]
    checa(c_path["sentido"].startswith("Caminho/arquivo"), "sentido de path é o rótulo estável de path")
    checa(c_termo["sentido"].startswith("Termo técnico"), "sentido de termo é o rótulo estável de termo")
    checa(c_path["areas"] == [], "conceito do catálogo entra sem áreas (trilha não é área)")

    # fundir_no_mapa: dedup por sentido
    mapa = {"conceitos": [{"rotulo": "SSH", "sentido": c_termo["sentido"], "areas": []}]}
    extras = conceitos_do_catalogo("use SSH e VLAN", CATALOGO_FAKE)
    novos = fundir_no_mapa(mapa, extras)
    checa(novos == 1, "fundir_no_mapa não duplica o sentido já presente (SSH), só entra VLAN")
    checa(any(c["rotulo"] == "VLAN" for c in mapa["conceitos"]), "VLAN foi anexado ao mapa")


class _IAStub:
    """Backend de IA que devolve mapa VAZIO — isola o efeito do catálogo."""
    nome = "stub"

    def extrair_mapa(self, titulo: str, texto: str) -> dict:
        return {"areas": [], "conceitos": [], "proposicoes": []}


def parte_b_e2e() -> bool:
    """Retorna True se rodou (API disponível); False se pulou."""
    from kdd_bot.config import Config
    try:
        cfg = Config.carregar()
    except Exception as e:  # noqa: BLE001
        print(f"=== B) e2e — PULADO (sem config: {e}) ===")
        return False

    import requests
    from kdd_bot.api_client import KddClient
    from kdd_bot.ia.facade import IAFacade
    from kdd_bot.pipeline import Pipeline

    print(f"=== B) e2e sem LLM — API: {cfg.base_url} ===")
    hdr = {"X-Token": cfg.token}

    # confirma que a API tem a rota /catalogo (senão o Passo 1 nem existe no servidor)
    rc = requests.get(f"{cfg.base_url}/catalogo", headers=hdr, timeout=15)
    if rc.status_code == 404:
        checa(False, "GET /catalogo existe no servidor (404 = deploy sem a rota)")
        return True
    catalogo = rc.json()
    termos = [t for lst in (catalogo.get("trilhas") or {}).values() for t in lst]
    checa(bool(termos), "GET /catalogo devolve termos")
    if not termos:
        return True

    # escolhe um path e um termo do catálogo real p/ montar o texto da fonte
    path = next((t for t in termos if "/" in t or "\\" in t), termos[0])
    termo = next((t for t in termos if "/" not in t and "\\" not in t), termos[-1])
    ref = "teste_catalogo:passo1"
    texto = (
        f"Aula de laboratório. Editamos {path} e configuramos {termo} no servidor. "
        "Texto propositalmente pobre em conceitos para a IA (stub) não achar nada."
    )

    r = requests.post(
        f"{cfg.base_url}/fontes/texto", headers=hdr,
        json={"contexto": "Teste Catálogo (Passo 1)", "texto": texto,
              "origem": "teste_catalogo", "ref": ref},
        timeout=30,
    )
    r.raise_for_status()
    fid = int((r.json().get("fonte") or r.json())["id"])
    print(f"  fonte de texto criada/atualizada: id={fid} (ref={ref})")

    # roda o Pipeline com a IA stub — só o catálogo deve popular o mapa
    client = KddClient(cfg)
    ok = Pipeline(cfg, client, IAFacade(_IAStub())).processar_fonte(
        {"id": fid, "titulo": "Teste Catálogo (Passo 1)"})
    checa(ok, "Pipeline processou a fonte com sucesso")

    mapa = requests.get(f"{cfg.base_url}/fontes/{fid}/mapa", headers=hdr, timeout=30).json()
    rotulos = _rotulos_do_mapa(mapa)
    checa(path in rotulos, f"path do catálogo ({path}) virou conceito no mapa da fonte")
    checa(termo in rotulos, f"termo do catálogo ({termo}) virou conceito no mapa da fonte")
    return True


def _rotulos_do_mapa(mapa: dict) -> set[str]:
    """Coleta rótulos do payload de GET /fontes/{id}/mapa, tolerante ao formato."""
    rotulos: set[str] = set()
    conc = mapa.get("conceitos") or mapa.get("mapa", {}).get("conceitos") or []
    for c in conc:
        if isinstance(c, dict):
            for chave in ("rotulo", "rotulos"):
                v = c.get(chave)
                if isinstance(v, str):
                    rotulos.add(v)
                elif isinstance(v, list):
                    rotulos.update(str(x.get("texto", x) if isinstance(x, dict) else x) for x in v)
    return rotulos


def main() -> int:
    parte_a_offline()
    parte_b_e2e()
    print()
    if _falhas:
        print(f"FALHOU: {len(_falhas)} assert(s)")
        return 1
    print("OK: todos os asserts passaram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
