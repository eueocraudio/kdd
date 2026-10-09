#!/usr/bin/env python3
"""E2E do SENTIMENTO da proposição (docs/sentimento.md §8).

Teses verificadas:
  · a medição é feita no BOT, em INGLÊS (vaderSentiment + TextBlob); a API só guarda/agrega;
  · sem forma inglesa o sentimento é NÃO MEDIDO, nunca "neutro";
  · o sentimento mora na REFERÊNCIA, então reprovar a fonte remove a contribuição dela;
  · SUBJETIVIDADE desconta o valor; POLARIDADE não (seria viés otimista).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bot"))

import requests  # noqa: E402

from kdd_bot.sentimento import analisar, autoteste, disponivel  # noqa: E402

BASE = os.environ["KDD_APP_URL"].rstrip("/")
TOKEN = os.environ.get("KDD_TOKEN_VALIDADOR") or os.environ["KDD_TOKEN_OPERADOR"]
H = {"X-Token": TOKEN}

falhas: list[str] = []


def ok(cond: bool, msg: str) -> None:
    print(("  OK   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


def req(metodo: str, caminho: str, **kw):
    r = requests.request(metodo, f"{BASE}{caminho}", headers=H, timeout=60, **kw)
    if r.status_code >= 400:
        raise SystemExit(f"HTTP {r.status_code} em {metodo} {caminho}: {r.text[:300]}")
    return r.json()


def status(metodo: str, caminho: str, **kw):
    r = requests.request(metodo, f"{BASE}{caminho}", headers=H, timeout=60, **kw)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


print("== 1. o motor de análise (pacotes de mercado, em inglês) ==")
ok(disponivel(), "vaderSentiment e TextBlob instalados no venv do bot")
acertos, total = autoteste()
ok(acertos == total, f"autoteste de polaridade: {acertos}/{total}")

r = analisar("explora", None, "malware", "vulnerability")
ok(r is not None and r["relacao_en"] == "exploits",
   "a relação é traduzida para inglês antes de medir")
ok(analisar("xpto que nao existe") is None,
   "sem forma inglesa NÃO se mede (e não se finge neutro)")

print("\n== 2. push grava o sentimento por FONTE, não na proposição ==")
f1 = req("POST", "/fontes/texto", json={
    "titulo": "Manual de segurança", "texto": "t", "contexto": "Segurança", "ref": "sec:1",
})["fonte"]
mapa = {
    "conceitos": [
        {"rotulo": "Malware", "sentido": "Programa malicioso", "tipo": "entidade"},
        {"rotulo": "Sistema", "sentido": "Conjunto computacional alvo", "tipo": "entidade"},
        {"rotulo": "Backup", "sentido": "Cópia de segurança de dados", "tipo": "entidade"},
        {"rotulo": "Dados", "sentido": "Informação armazenada", "tipo": "entidade"},
    ],
    "proposicoes": [
        {"origem_rotulo": "Malware", "relacao": "compromete", "destino_rotulo": "Sistema",
         "relacao_en": "compromises", "polaridade": -1.0, "subjetividade": 0.0},
        {"origem_rotulo": "Backup", "relacao": "protege", "destino_rotulo": "Dados",
         "relacao_en": "protects", "polaridade": 1.0, "subjetividade": 0.0},
        {"origem_rotulo": "Backup", "relacao": "é melhor que", "destino_rotulo": "Malware",
         "relacao_en": "is better than", "polaridade": 0.5, "subjetividade": 0.9},
        {"origem_rotulo": "Malware", "relacao": "é um", "destino_rotulo": "Sistema",
         "relacao_en": "is a"},
    ],
}
req("POST", f"/fontes/{f1['id']}/mapas", json=mapa)

props = {p["relacao"]: p for p in req("GET", "/proposicoes")["proposicoes"]}
ok(all("sentimento" in p for p in props.values()), "toda proposição traz o bloco sentimento")

neg = props["compromete"]["sentimento"]
pos = props["protege"]["sentimento"]
ok(neg["rotulo"] == "negativa" and neg["polaridade"] == -1.0,
   f"'compromete' é negativa ({neg['polaridade']})")
ok(pos["rotulo"] == "positiva" and pos["polaridade"] == 1.0,
   f"'protege' é positiva ({pos['polaridade']})")
ok(neg["fontes_medidas"] == 1 and neg["origem"] == "fontes",
   "o sentimento vem das fontes que mediram")

sem = props["é um"]["sentimento"]
ok(sem["polaridade"] is None and sem["rotulo"] == "nao_medida",
   "proposição sem medição sai NÃO MEDIDA, não neutra")

print("\n== 3. SUBJETIVIDADE desconta o valor; POLARIDADE não ==")
juizo = props["é melhor que"]
ok(juizo["sentimento"]["subjetividade"] == 0.9, "o juízo de valor tem subjetividade alta")
ok(juizo["valor_detalhe"]["desconto_subjetividade"] > 0,
   f"e sofre desconto no valor ({juizo['valor_detalhe']['desconto_subjetividade']})")
ok(props["compromete"]["valor_detalhe"]["desconto_subjetividade"] == 0,
   "o fato NEGATIVO não sofre desconto nenhum (nada de viés otimista)")

# comparação controlada: mesmo par de conceitos, mesma classe de relação, muda a subjetividade
f2 = req("POST", "/fontes/texto", json={
    "titulo": "Par controlado", "texto": "t", "contexto": "Segurança", "ref": "sec:2",
})["fonte"]
req("POST", f"/fontes/{f2['id']}/mapas", json={
    "conceitos": [
        {"rotulo": "Firewall", "sentido": "Filtro de tráfego de rede", "tipo": "entidade"},
        {"rotulo": "Rede", "sentido": "Infraestrutura de comunicação", "tipo": "classe"},
        {"rotulo": "Antivirus", "sentido": "Programa de detecção de malware", "tipo": "entidade"},
    ],
    "proposicoes": [
        {"origem_rotulo": "Firewall", "relacao": "pertence a", "destino_rotulo": "Rede",
         "relacao_en": "belongs to", "polaridade": 0.0, "subjetividade": 0.0},
        {"origem_rotulo": "Antivirus", "relacao": "pertence a", "destino_rotulo": "Rede",
         "relacao_en": "belongs to", "polaridade": 0.0, "subjetividade": 1.0},
    ],
})
todas = req("GET", "/proposicoes")["proposicoes"]
fato = next(p for p in todas if p["origem"]["rotulo"] == "Firewall")
opin = next(p for p in todas if p["origem"]["rotulo"] == "Antivirus")
ok(fato["valor"] > opin["valor"],
   f"mesma tripla-forma: fato vale {fato['valor']} e juízo vale {opin['valor']}")
ok(abs(opin["valor_detalhe"]["desconto_subjetividade"] - 0.20) < 0.01,
   "subjetividade 1,0 desconta exatamente 20%")

print("\n== 4. duas fontes discordam no enquadramento ==")
f3 = req("POST", "/fontes/texto", json={
    "titulo": "Outra visão", "texto": "t", "contexto": "Segurança", "ref": "sec:3",
})["fonte"]
req("POST", f"/fontes/{f3['id']}/mapas", json={
    "conceitos": [
        {"rotulo": "Malware", "sentido": "Programa malicioso", "tipo": "entidade"},
        {"rotulo": "Sistema", "sentido": "Conjunto computacional alvo", "tipo": "entidade"},
    ],
    "proposicoes": [
        {"origem_rotulo": "Malware", "relacao": "compromete", "destino_rotulo": "Sistema",
         "relacao_en": "compromises", "polaridade": 1.0, "subjetividade": 0.0},
    ],
})
s = {p["relacao"]: p["sentimento"] for p in req("GET", "/proposicoes")["proposicoes"]}["compromete"]
ok(s["fontes_medidas"] == 2, f"as duas fontes contam ({s['fontes_medidas']})")
ok(abs(s["polaridade"]) < 0.25, f"polaridades opostas se anulam na média ({s['polaridade']})")
ok(s["discordancia"] >= 1.5, f"e a DISCORDÂNCIA fica alta ({s['discordancia']})")

print("\n== 5. reprovar a fonte remove a contribuição dela ==")
req("POST", f"/fontes/{f3['id']}/reprovar")
s2 = {p["relacao"]: p["sentimento"] for p in req("GET", "/proposicoes")["proposicoes"]}["compromete"]
ok(s2["fontes_medidas"] == 1, f"só a fonte aprovada conta ({s2['fontes_medidas']})")
ok(s2["polaridade"] == -1.0, f"a polaridade volta para a da fonte válida ({s2['polaridade']})")
ok(s2["discordancia"] == 0.0, "e a discordância zera")

print("\n== 6. ameaças x proteções no conceito ==")
cid_sistema = next(p["destino"]["id"] for p in req("GET", "/proposicoes")["proposicoes"]
                   if p["destino"]["rotulo"] == "Sistema")
c = req("GET", f"/conceitos/{cid_sistema}")["conceito"]
ok("ameacas" in c and "protecoes" in c, "o conceito separa ameaças e proteções")
ok(any(a["relacao"] == "compromete" for a in c["ameacas"]),
   f"'compromete' aparece como AMEAÇA de Sistema ({len(c['ameacas'])} ameaça(s))")

cid_dados = next(p["destino"]["id"] for p in req("GET", "/proposicoes")["proposicoes"]
                 if p["destino"]["rotulo"] == "Dados")
c2 = req("GET", f"/conceitos/{cid_dados}")["conceito"]
ok(any(p["relacao"] == "protege" for p in c2["protecoes"]),
   f"'protege' aparece como PROTEÇÃO de Dados ({len(c2['protecoes'])} proteção(ões))")

print("\n== 7. filtro por polaridade ==")
neg_l = req("GET", "/proposicoes?polaridade=negativa")["proposicoes"]
pos_l = req("GET", "/proposicoes?polaridade=positiva")["proposicoes"]
ok(all(p["sentimento"]["rotulo"] == "negativa" for p in neg_l) and bool(neg_l),
   f"?polaridade=negativa traz só negativas ({len(neg_l)})")
ok(all(p["sentimento"]["rotulo"] == "positiva" for p in pos_l) and bool(pos_l),
   f"?polaridade=positiva traz só positivas ({len(pos_l)})")
c_, _ = status("GET", "/proposicoes?polaridade=xpto")
ok(c_ == 400, "polaridade inválida dá 400")

print()
if falhas:
    print(f"FALHAS ({len(falhas)}):")
    for x in falhas:
        print(f"  - {x}")
    sys.exit(1)
print("TODOS OS CHECKS PASSARAM")
