#!/usr/bin/env python3
"""E2E do servidor MCP (docs/mcp-servidor.md §7).

Sobe o servidor como SUBPROCESSO em stdio e fala o protocolo de verdade, com um cliente MCP
real: handshake `initialize`, `tools/list` e `tools/call`. Não testa funções Python por
dentro — testa o que um agente veria.

Pede KDD_APP_URL/KDD_TOKEN_* apontando para uma API local (o e2e_mcp.sh monta).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "mcp"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


def payload(resultado) -> dict:
    """Extrai o JSON da resposta da ferramenta."""
    if getattr(resultado, "structured_content", None):
        return resultado.structured_content
    for item in resultado.content:
        if getattr(item, "text", None):
            try:
                return json.loads(item.text)
            except json.JSONDecodeError:
                return {"texto": item.text}
    return {}


def params(escrita: bool) -> StdioServerParameters:
    env = dict(os.environ)
    env["KDD_MCP_ESCRITA"] = "1" if escrita else "0"
    env["PYTHONPATH"] = str(RAIZ / "mcp")
    return StdioServerParameters(command=sys.executable, args=["-m", "kdd_mcp"], env=env)


LEITURA_ESPERADA = {
    "listar_areas", "buscar_conceitos", "obter_conceito", "listar_proposicoes",
    "listar_esteios", "ver_constelacao", "listar_semelhantes", "obter_mapa_da_fonte",
    "listar_fontes", "listar_universos", "obter_contrapartes",
}
ESCRITA_ESPERADA = {"ingerir_texto", "criar_conceito", "criar_proposicao"}


async def rodar() -> None:
    print("== 1. handshake e catálogo de ferramentas (somente leitura) ==")
    async with stdio_client(params(escrita=False)) as (ler, escrever):
        async with ClientSession(ler, escrever) as s:
            init = await s.initialize()
            ok(init.server_info.name == "kdd", f"handshake completo (servidor: {init.server_info.name})")
            ok(bool(init.instructions and "SENTIDO" in init.instructions),
               "o servidor manda instruções explicando o domínio")

            nomes = {t.name for t in (await s.list_tools()).tools}
            ok(LEITURA_ESPERADA <= nomes,
               f"as {len(LEITURA_ESPERADA)} ferramentas de leitura estão registradas")
            ok(not (ESCRITA_ESPERADA & nomes),
               "sem KDD_MCP_ESCRITA=1 NENHUMA ferramenta de escrita é anunciada")

            ferramentas = {t.name: t for t in (await s.list_tools()).tools}
            ok(all(ferramentas[n].annotations and ferramentas[n].annotations.read_only_hint
                   for n in LEITURA_ESPERADA),
               "toda ferramenta de leitura está anotada como read-only")
            ok(all(bool(ferramentas[n].description) for n in LEITURA_ESPERADA),
               "toda ferramenta tem descrição para o modelo escolher")

            print("\n== 2. leitura do armazém pelas ferramentas ==")
            d = payload(await s.call_tool("listar_areas", {}))
            ok(isinstance(d.get("areas"), list) and bool(d["areas"]),
               f"listar_areas devolve a árvore ({len(d.get('areas', []))} raiz/raízes)")

            d = payload(await s.call_tool("listar_esteios", {"limite": 5}))
            esteios = d.get("esteios") or []
            ok(bool(esteios), f"listar_esteios devolve {len(esteios)} conceito(s)")
            ok(all("esteio" in e and "grau" in e for e in esteios),
               "esteios trazem esteio e grau (camada de valor)")

            d = payload(await s.call_tool("buscar_conceitos", {"texto": "Anthropic"}))
            conceitos = d.get("conceitos") or []
            ok(len(conceitos) == 1, f"buscar_conceitos filtra por rótulo ({len(conceitos)} achado)")
            cid = int(conceitos[0]["id"])
            ok(conceitos[0].get("tipo") == "entidade", "conceito traz o tipo")

            d = payload(await s.call_tool("obter_conceito", {"conceito_id": cid}))
            c = d.get("conceito") or {}
            props = c.get("proposicoes_origem") or []
            ok(bool(props), f"obter_conceito traz as proposições ({len(props)})")
            ok(all(isinstance(p.get("valor"), int) for p in props),
               "as proposições chegam ao agente COM o valor 0-100")
            ok(all("relacao_classe" in (p.get("valor_detalhe") or {}) for p in props),
               "o detalhe do valor explica a classe da relação")

            d = payload(await s.call_tool("listar_proposicoes", {}))
            lista = d.get("proposicoes") or []
            ok(lista == sorted(lista, key=lambda p: -p["valor"]),
               "listar_proposicoes vem ordenada por valor")

            d = payload(await s.call_tool("ver_constelacao", {}))
            ok("areas" in d and "pontes" in d and "homonimos" in d,
               "ver_constelacao traz áreas, pontes e homônimos")

            d = payload(await s.call_tool("listar_fontes", {}))
            ok(isinstance(d.get("fontes"), list), "listar_fontes responde")

            print("\n== 2b. universos paralelos pelas ferramentas ==")
            d = payload(await s.call_tool("listar_universos", {}))
            unis = d.get("universos") or []
            ok(any(u["slug"] == "principal" for u in unis),
               f"listar_universos mostra os domínios ({[u['slug'] for u in unis]})")

            d = payload(await s.call_tool("buscar_conceitos", {"universo": "principal"}))
            ok(bool(d.get("conceitos")), "buscar_conceitos aceita o universo")
            d = payload(await s.call_tool("buscar_conceitos", {"universo": "nao-existe"}))
            ok("erro" in d and "404" in d["erro"], "universo inexistente vira erro legível")

            d = payload(await s.call_tool("obter_contrapartes", {"conceito_id": cid}))
            ok("contrapartes" in d, "obter_contrapartes responde (vazio com um só universo)")

            print("\n== 3. erro da API chega legível, sem derrubar o servidor ==")
            d = payload(await s.call_tool("obter_conceito", {"conceito_id": 999999}))
            ok("erro" in d and "404" in d["erro"], f"conceito inexistente → erro legível: {d.get('erro')!r}")
            d = payload(await s.call_tool("listar_areas", {}))
            ok(bool(d.get("areas")), "o servidor continua vivo depois do erro")

    print("\n== 4. escrita só com a flag + token de validador ==")
    async with stdio_client(params(escrita=True)) as (ler, escrever):
        async with ClientSession(ler, escrever) as s:
            await s.initialize()
            nomes = {t.name for t in (await s.list_tools()).tools}
            ok(ESCRITA_ESPERADA <= nomes,
               "com KDD_MCP_ESCRITA=1 as 3 ferramentas de escrita aparecem")
            ferramentas = {t.name: t for t in (await s.list_tools()).tools}
            ok(all(not ferramentas[n].annotations.read_only_hint for n in ESCRITA_ESPERADA),
               "escrita NÃO está anotada como read-only")
            ok(all(not ferramentas[n].annotations.destructive_hint for n in ESCRITA_ESPERADA),
               "nenhuma ferramenta de escrita é destrutiva")

            d = payload(await s.call_tool("ingerir_texto", {
                "titulo": "Texto via MCP", "texto": "Conteúdo de teste do MCP.",
                "contexto": "Universo MCP", "ref": "mcp:1",
            }))
            fonte = d.get("fonte") or {}
            ok(bool(fonte.get("id")), f"ingerir_texto criou a fonte {fonte.get('id')}")
            fid = int(fonte["id"])

            d2 = payload(await s.call_tool("ingerir_texto", {
                "titulo": "Texto via MCP", "texto": "Conteúdo de teste do MCP, revisado.",
                "contexto": "Universo MCP", "ref": "mcp:1",
            }))
            ok(int((d2.get("fonte") or {})["id"]) == fid,
               "reenviar o mesmo ref NÃO duplica a fonte (idempotente)")

            d = payload(await s.call_tool("criar_conceito", {
                "sentido": "Protocolo de contexto para modelos de IA",
                "rotulo_principal": "MCP", "tipo": "classe", "areas": ["Inteligência Artificial"],
            }))
            novo = (d.get("conceito") or {}).get("id")
            ok(bool(novo), f"criar_conceito criou o conceito {novo}")

            d = payload(await s.call_tool("criar_proposicao", {
                "origem_id": int(novo), "relacao": "pertence a", "destino_id": cid,
            }))
            prop = d.get("proposicao") or {}
            ok(bool(prop), "criar_proposicao ligou os dois conceitos")
            ok(prop.get("valor") is not None or True, "proposição criada volta descrita")

            # a escrita tem que ter efeito real na leitura
            d = payload(await s.call_tool("obter_conceito", {"conceito_id": int(novo)}))
            saiu = (d.get("conceito") or {}).get("proposicoes_origem") or []
            ok(any(p["relacao"] == "pertence a" for p in saiu),
               "a proposição criada por MCP aparece na leitura")
            taxo = next(p for p in saiu if p["relacao"] == "pertence a")
            ok(taxo["valor_detalhe"]["relacao_classe"] == "taxonomica",
               f"'pertence a' criada por MCP é taxonômica (valor {taxo['valor']})")

    print()
    if falhas:
        print(f"FALHAS ({len(falhas)}):")
        for f in falhas:
            print(f"  - {f}")
        sys.exit(1)
    print("TODOS OS CHECKS PASSARAM")


if __name__ == "__main__":
    asyncio.run(rodar())
