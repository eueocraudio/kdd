#!/usr/bin/env python3
"""E2E da camada de VALOR / ESTEIOS / VETORES (docs/valor-conhecimento.md).

Roda contra a API apontada por KDD_APP_URL (o e2e_valor.sh sobe uma LOCAL descartável).
NÃO aponte para produção: o teste cria fontes e conceitos.

Cobre as decisões do idealizador:
  II  valor 0–100 por proposição; entidade+verbo+classe no topo
  IV  o que entrou está aprovado (aprovação automática no push)
  V   esteio = conceito que sustenta muitas relações
  VII banco vetorial: quase-duplicata detectada por similaridade
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bot"))

import requests  # noqa: E402

BASE = os.environ["KDD_APP_URL"].rstrip("/")
TOKEN = os.environ.get("KDD_TOKEN_VALIDADOR") or os.environ["KDD_TOKEN_OPERADOR"]
H = {"X-Token": TOKEN}

falhas: list[str] = []


def ok(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


def req(metodo: str, caminho: str, **kw) -> dict:
    r = requests.request(metodo, f"{BASE}{caminho}", headers=H, timeout=60, **kw)
    if r.status_code >= 400:
        raise SystemExit(f"HTTP {r.status_code} em {metodo} {caminho}: {r.text[:400]}")
    return r.json()


print("== 1. ingestão de texto + push de mapa com tipos ==")
fonte = req("POST", "/fontes/texto", json={
    "titulo": "Fonte de teste — valor do conhecimento",
    "texto": "A Anthropic desenvolveu o Claude, um modelo de linguagem.",
    "contexto": "Teste de Valor",
    "ref": "teste-valor:1",
})["fonte"]
fid = int(fonte["id"])
antes = req("GET", f"/fontes/{fid}")["fonte"]
ok(antes["status_aprovacao"] == "pendente", "fonte nasce com aprovação pendente")

# Conceitos com TIPO: a tripla "entidade + verbo + classe" é a de maior valor (decisão II);
# a tripla "outro + 'é um' + outro" é o piso. Mesma certeza (1 fonte) nas duas.
mapa = req("POST", f"/fontes/{fid}/mapas", json={
    "conceitos": [
        {"rotulo": "Anthropic", "sentido": "Empresa de pesquisa em IA", "tipo": "entidade",
         "areas": ["Inteligência Artificial"]},
        {"rotulo": "Modelo de linguagem", "sentido": "Categoria de sistema de IA que gera texto",
         "tipo": "classe", "areas": ["Inteligência Artificial"]},
        {"rotulo": "Claude", "sentido": "Modelo de linguagem da Anthropic", "tipo": "entidade",
         "areas": ["Inteligência Artificial"]},
        {"rotulo": "Coisa vaga", "sentido": "Algo sem tipo definido", "areas": ["Inteligência Artificial"]},
        {"rotulo": "Outra coisa", "sentido": "Outro algo sem tipo", "areas": ["Inteligência Artificial"]},
    ],
    "proposicoes": [
        {"origem_rotulo": "Anthropic", "relacao": "desenvolveu", "destino_rotulo": "Claude"},
        {"origem_rotulo": "Claude", "relacao": "é um", "destino_rotulo": "Modelo de linguagem"},
        {"origem_rotulo": "Coisa vaga", "relacao": "é um", "destino_rotulo": "Outra coisa"},
        {"origem_rotulo": "Anthropic", "relacao": "classifica", "destino_rotulo": "Modelo de linguagem"},
    ],
})
ok(mapa["status_proc"] == "processado", "push deixa a fonte processada")

print("\n== 2. aprovação automática (decisão IV: entrou = aprovado) ==")
ok(mapa.get("status_aprovacao") == "aprovada", "push responde status_aprovacao=aprovada")
f = req("GET", f"/fontes/{fid}")["fonte"]
ok(f["status_aprovacao"] == "aprovada", "fonte está aprovada sem ação humana")

print("\n== 3. valor 0–100 por proposição (decisão II) ==")
props = req("GET", "/proposicoes")["proposicoes"]
ok(bool(props), f"{len(props)} proposição(ões) retornadas")
ok(all(isinstance(p.get("valor"), int) for p in props), "toda proposição tem 'valor' inteiro")
ok(all(0 <= p["valor"] <= 100 for p in props), "valor dentro de [0,100]")
ok(all("estrutura" in (p.get("valor_detalhe") or {}) for p in props), "valor_detalhe presente")

por_rel = {p["relacao"]: p for p in props}
forte = por_rel["desenvolveu"]      # entidade + verbo + entidade
classif = por_rel["classifica"]     # entidade + verbo + classe  ← a de maior valor
fraca = next(p for p in props if p["relacao"] == "é um" and p["origem"]["rotulo"] == "Coisa vaga")
ok(classif["valor"] > fraca["valor"],
   f"entidade+verbo+classe ({classif['valor']}) > sem tipo+cópula ({fraca['valor']})")
ok(classif["valor"] >= forte["valor"],
   f"destino 'classe' ({classif['valor']}) >= destino 'entidade' ({forte['valor']})")
ok(props == sorted(props, key=lambda p: -p["valor"]), "lista vem ordenada por valor")
print(f"     valores: " + ", ".join(f"{p['relacao']}={p['valor']}" for p in props))

print("\n== 3b. reforço da ligação hierárquica (pertencer/ser/estar/incluir) ==")
# Comparação CONTROLADA: mesmas duas pontas (logo mesmo esteio), mesmos tipos, mesma
# certeza. A ÚNICA diferença é o verbo da relação — isola o efeito da classe da relação.
req("POST", f"/fontes/{fid}/mapas", json={
    "conceitos": [
        {"rotulo": "Claude", "sentido": "Modelo de linguagem da Anthropic", "tipo": "entidade"},
        {"rotulo": "Modelo de linguagem", "sentido": "Categoria de sistema de IA que gera texto",
         "tipo": "classe"},
        {"rotulo": "Anthropic", "sentido": "Empresa de pesquisa em IA", "tipo": "entidade"},
    ],
    "proposicoes": [
        {"origem_rotulo": "Claude", "relacao": "pertence a", "destino_rotulo": "Modelo de linguagem"},
        {"origem_rotulo": "Claude", "relacao": "relaciona-se com", "destino_rotulo": "Modelo de linguagem"},
        {"origem_rotulo": "Anthropic", "relacao": "desenvolveu", "destino_rotulo": "Claude"},
        {"origem_rotulo": "Anthropic", "relacao": "classifica", "destino_rotulo": "Modelo de linguagem"},
        {"origem_rotulo": "Claude", "relacao": "é um", "destino_rotulo": "Modelo de linguagem"},
        {"origem_rotulo": "Coisa vaga", "relacao": "é um", "destino_rotulo": "Outra coisa"},
    ],
})
props2 = req("GET", "/proposicoes")["proposicoes"]
por_rel2 = {p["relacao"]: p for p in props2}

hier = por_rel2["pertence a"]
vaga = por_rel2["relaciona-se com"]
ok(hier["valor"] > vaga["valor"],
   f"'pertence a' ({hier['valor']}) vale MAIS que 'relaciona-se com' ({vaga['valor']}) "
   "nas mesmas pontas")
ok(hier["valor_detalhe"]["relacao_classe"] == "taxonomica", "'pertence a' é classificada taxonômica")
ok(vaga["valor_detalhe"]["relacao_classe"] == "vaga", "'relaciona-se com' é classificada vaga")
ok(hier["valor_detalhe"]["bonus_taxonomico"] > 0, "a ligação hierárquica recebe bônus > 0")
ok(vaga["valor_detalhe"]["bonus_taxonomico"] == 0, "a ligação vaga NÃO recebe bônus")

acao = por_rel2["desenvolveu"]
ok(acao["valor_detalhe"]["relacao_classe"] == "verbal", "'desenvolveu' segue verbal (ação)")
ok(acao["valor_detalhe"]["bonus_taxonomico"] == 0, "verbo de ação não recebe bônus taxonômico")

# 'é um' entre conceitos TIPADOS (entidade → classe) é o padrão da decisão II: topo da lista.
eum_forte = next(p for p in props2
                 if p["relacao"] == "é um" and p["origem"]["rotulo"] == "Claude")
eum_fraco = next(p for p in props2
                 if p["relacao"] == "é um" and p["origem"]["rotulo"] == "Coisa vaga")
ok(eum_forte["valor"] > eum_fraco["valor"],
   f"entidade 'é um' classe ({eum_forte['valor']}) > sem tipo 'é um' sem tipo ({eum_fraco['valor']})")
ok(all(p["valor"] <= 100 for p in props2), "o bônus nunca estoura 100")
print("     " + ", ".join(
    f"{p['relacao']}[{p['valor_detalhe']['relacao_classe'][:4]}]={p['valor']}" for p in props2))

print("\n== 4. esteios (decisão V: esteio sustenta muitas relações) ==")
esteios = req("GET", "/esteios?limite=10")["esteios"]
ok(bool(esteios), f"{len(esteios)} esteio(s) retornado(s)")
topo = esteios[0]
ok(topo["rotulo"] == "Anthropic" or topo["esteio"] == 100,
   f"o conceito de maior grau lidera (topo={topo['rotulo']}, esteio={topo['esteio']}%)")
graus = [int((e.get("grau") or {}).get("saida", 0)) + int((e.get("grau") or {}).get("entrada", 0))
         for e in esteios]
ok(graus == sorted(graus, reverse=True), "esteios ordenados por grau decrescente")
ok(all(0 <= e["esteio"] <= 100 for e in esteios), "esteio em [0,100]")

print("\n== 5. tipo no detalhe do conceito + curadoria do tipo ==")
cid_anthropic = next(e["id"] for e in esteios if e["rotulo"] == "Anthropic")
c = req("GET", f"/conceitos/{cid_anthropic}")["conceito"]
ok(c.get("tipo") == "entidade", "conceito traz o tipo que o bot mandou")
ok(isinstance(c.get("esteio"), int), "conceito traz esteio")
ok("similares" in c, "conceito traz a lista de similares (pode estar vazia)")

cid_vaga = next(p["origem"]["id"] for p in props if p["origem"]["rotulo"] == "Coisa vaga")
req("PATCH", f"/conceitos/{cid_vaga}", json={"tipo": "entidade"})
c2 = req("GET", f"/conceitos/{cid_vaga}")["conceito"]
ok(c2.get("tipo") == "entidade", "curadoria altera o tipo (PATCH /conceitos/{id})")

# re-push NÃO sobrescreve o tipo curado manualmente
req("POST", f"/fontes/{fid}/mapas", json={
    "conceitos": [{"rotulo": "Coisa vaga", "sentido": "Algo sem tipo definido", "tipo": "atributo"}],
    "proposicoes": [],
})
c3 = req("GET", f"/conceitos/{cid_vaga}")["conceito"]
ok(c3.get("tipo") == "entidade", "re-push do bot NÃO sobrescreve tipo definido por humano")

print("\n== 6. camada vetorial (decisão VII) ==")
# quase-duplicata: sentido diferente (logo, conceito diferente) mas semanticamente igual
req("POST", "/conceitos", json={
    "sentido": "Categoria de sistemas de IA que geram texto",
    "rotulo_principal": "Modelos de linguagem",
    "tipo": "classe",
    "areas": ["Inteligência Artificial"],
})

faltando = req("GET", "/embeddings?modelo=nomic-embed-text&faltando=1")["conceitos"]
ok(len(faltando) >= 6, f"{len(faltando)} conceito(s) sem vetor antes de vetorizar")

from kdd_bot.api_client import KddClient   # noqa: E402
from kdd_bot.config import Config          # noqa: E402
from kdd_bot.vetor import vetorizar        # noqa: E402

cfg = Config.carregar()
try:
    requests.get(f"{cfg.ollama_url}/api/tags", timeout=5).raise_for_status()
    tem_ollama = True
except Exception as e:  # noqa: BLE001
    print(f"  PULADO: Ollama indisponível ({e}) — etapa vetorial não verificada")
    tem_ollama = False

if tem_ollama:
    res = vetorizar(KddClient(cfg), cfg)
    ok(res["embutidos"] >= 6, f"{res['embutidos']} conceito(s) embutido(s)")
    ok(res["total"] >= 6, f"{res['total']} vetor(es) no armazém")

    restantes = req("GET", f"/embeddings?modelo={cfg.embed_model}&faltando=1")["conceitos"]
    ok(not restantes, "nenhum conceito ficou sem vetor")

    sims = req("GET", "/similares?min=0.8&limite=50")["similares"]
    ok(bool(sims), f"{len(sims)} par(es) semelhante(s) detectado(s)")
    rotulos = {(p["a"]["rotulo"], p["b"]["rotulo"]) for p in sims}
    achou = any("Modelo de linguagem" in par and "Modelos de linguagem" in par for par in rotulos)
    ok(achou, f"a quase-duplicata foi detectada (pares: {sorted(rotulos)[:3]})")

    c4 = req("GET", f"/conceitos/{cid_anthropic}")["conceito"]
    ok(isinstance(c4.get("similares"), list), "detalhe do conceito expõe similares")

    # idempotência: segunda passada não embute nada de novo
    res2 = vetorizar(KddClient(cfg), cfg)
    ok(res2["embutidos"] == 0, "2ª vetorização não reembute (idempotente)")

print("\n== 7. veto humano ainda derruba a certeza ==")
req("POST", f"/fontes/{fid}/reprovar")
props_depois = req("GET", "/proposicoes")["proposicoes"]
ok(all(p["fontes_aprovadas"] == 0 for p in props_depois), "reprovar zera as fontes aprovadas")
ok(all(p["valor"] < 100 for p in props_depois), "valor cai sem reforço de fonte")
rel_forte = next(p for p in props_depois if p["relacao"] == "classifica")
antes_valor = por_rel2["classifica"]["valor"]
ok(rel_forte["valor"] < antes_valor,
   f"a mesma proposição vale menos reprovada ({rel_forte['valor']} < {antes_valor})")
hier_depois = next(p for p in props_depois if p["relacao"] == "pertence a")
ok(hier_depois["valor_detalhe"]["bonus_taxonomico"] > hier["valor_detalhe"]["bonus_taxonomico"],
   "sem reforço de fonte o bônus taxonômico cresce (age sobre a folga até 100)")

print()
if falhas:
    print(f"FALHAS ({len(falhas)}):")
    for f_ in falhas:
        print(f"  - {f_}")
    sys.exit(1)
print("TODOS OS CHECKS PASSARAM")
