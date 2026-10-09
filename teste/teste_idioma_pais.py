#!/usr/bin/env python3
"""E2E de IDIOMA e PAÍS (docs/idioma-pais.md §9).

A tese: idioma é SUPERFÍCIE (vive no rótulo, não muda o conceito); país pode mudar o
SENTIDO (entra na identidade). O teste separa os dois.
"""
from __future__ import annotations

import os
import sys

import requests

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


print("== 1. retrocompatibilidade: base nasce pt-BR / universal ==")
u = req("GET", "/universos")["universos"][0]
ok(u["idioma"] == "pt-BR", f"universo traz o idioma-base ({u['idioma']})")
d = req("GET", "/conceitos")
ok(d["idioma"] is None and d["pais"] is None,
   "sem ?idioma=/?pais= a resposta diz que não houve filtro")

print("\n== 2. validação recusa entrada suja em vez de ignorar ==")
for ruim in ["pt_BR", "PT-br", "x", "pt-BR'%20OR%201=1"]:
    c, _ = status("GET", f"/conceitos?idioma={ruim}")
    ok(c == 400, f"idioma {ruim!r} recusado com 400")
for ruim in ["BRA", "b", "1X"]:
    c, _ = status("GET", f"/conceitos?pais={ruim}")
    ok(c == 400, f"pais {ruim!r} recusado com 400")

print("\n== 3. IDIOMA é superfície: um conceito, vários rótulos ==")
porta = req("POST", "/conceitos", json={
    "sentido": "Abertura em parede para passagem",
    "rotulo_principal": "Porta", "idioma": "pt-BR", "tipo": "classe",
})["conceito"]
cid = int(porta["id"])
for texto, idioma in [("Door", "en"), ("Puerta", "es"), ("Porta", "pt-PT")]:
    req("POST", f"/conceitos/{cid}/rotulos", json={"texto": texto, "idioma": idioma})

c = req("GET", f"/conceitos/{cid}")["conceito"]
idiomas = {r["idioma"] for r in c["rotulos"]}
ok(idiomas == {"pt-BR", "en", "es", "pt-PT"}, f"4 rótulos, 4 idiomas, 1 conceito ({sorted(idiomas)})")
ok(sorted(c["idiomas"]) == sorted(idiomas), "o conceito lista os idiomas que tem")
# "Porta" existe em pt-BR e pt-PT: MESMO texto, idiomas diferentes
textos_porta = [r for r in c["rotulos"] if r["texto"] == "Porta"]
ok(len(textos_porta) == 2, "o MESMO texto coexiste em dois idiomas (pt-BR e pt-PT)")

print("\n== 4. escolha do rótulo por idioma, com fallback ==")
def rotulo_em(idioma: str | None) -> str:
    q = f"?idioma={idioma}" if idioma else ""
    achados = [x for x in req("GET", f"/conceitos{q}")["conceitos"] if int(x["id"]) == cid]
    return achados[0]["rotulo"]

ok(rotulo_em("en") == "Door", f"?idioma=en devolve 'Door' (veio {rotulo_em('en')!r})")
ok(rotulo_em("es") == "Puerta", f"?idioma=es devolve 'Puerta'")
ok(rotulo_em("de") in {"Porta", "Door", "Puerta"},
   f"?idioma=de (ausente) cai no FALLBACK em vez de vir vazio (veio {rotulo_em('de')!r})")
ok(bool(rotulo_em(None)), "sem ?idioma= também devolve um rótulo")

print("\n== 5. PAÍS entra na identidade: mesmo sentido, países diferentes ==")
SENT = "Tributo sobre a renda das pessoas físicas"
a = req("POST", "/conceitos", json={
    "sentido": SENT, "rotulo_principal": "Imposto de Renda", "pais": "BR", "tipo": "classe",
})["conceito"]
b = req("POST", "/conceitos", json={
    "sentido": SENT, "rotulo_principal": "IRS", "pais": "PT", "tipo": "classe",
})["conceito"]
ok(int(a["id"]) != int(b["id"]), f"MESMO sentido + países diferentes = 2 conceitos ({a['id']} x {b['id']})")
ok(a["pais"] == "BR" and b["pais"] == "PT", "cada um guarda o seu país")
c_, d_ = status("POST", "/conceitos", json={
    "sentido": SENT, "rotulo_principal": "Dup", "pais": "BR",
})
ok(c_ == 409, "repetir (universo, pais, sentido) é barrado com 409")

print("\n== 6. merge entre países é proibido ==")
c_, d_ = status("POST", f"/conceitos/{a['id']}/merge", json={"outro_id": b["id"]})
ok(c_ == 409, f"não se funde BR com PT ({d_.get('erro','')[:55]}...)")
c_, _ = status("POST", f"/conceitos/{a['id']}/merge", json={"outro_id": cid})
ok(c_ == 409, "nem conceito de país com conceito universal")

print("\n== 7. filtro de país é INCLUSIVO (≠ universo, que é estrito) ==")
def ids_com_pais(pais: str | None) -> set[int]:
    q = f"?pais={pais}" if pais else ""
    return {int(x["id"]) for x in req("GET", f"/conceitos{q}")["conceitos"]}

br = ids_com_pais("BR")
pt = ids_com_pais("PT")
todos = ids_com_pais(None)
ok(int(a["id"]) in br and cid in br,
   "?pais=BR traz o brasileiro E o universal (semântica inclusiva)")
ok(int(b["id"]) not in br, "?pais=BR NÃO traz o que é só de PT")
ok(int(b["id"]) in pt and cid in pt and int(a["id"]) not in pt, "e o espelho vale para PT")
ok(br != pt and br < todos and pt < todos, "sem filtro vem tudo; cada país vem um subconjunto")

print("\n== 8. a mesma tripla pode valer num país e não noutro ==")
maioridade = req("POST", "/conceitos", json={
    "sentido": "Idade a partir da qual se responde penalmente", "rotulo_principal": "Maioridade penal",
    "tipo": "classe",
})["conceito"]
dezoito = req("POST", "/conceitos", json={
    "sentido": "Número de anos: dezoito", "rotulo_principal": "18 anos", "tipo": "atributo",
})["conceito"]
p_br = req("POST", "/proposicoes", json={
    "origem_id": maioridade["id"], "relacao": "é", "destino_id": dezoito["id"], "pais": "BR",
})["proposicao"]
p_uni = req("POST", "/proposicoes", json={
    "origem_id": maioridade["id"], "relacao": "é", "destino_id": dezoito["id"],
})["proposicao"]
ok(int(p_br["id"]) != int(p_uni["id"]),
   f"mesma tripla, países diferentes = proposições diferentes ({p_br['id']} x {p_uni['id']})")
ok(p_br["pais"] == "BR" and p_uni["pais"] == "", "cada uma guarda o seu país")

props_br = {int(p["id"]) for p in req("GET", "/proposicoes?pais=BR")["proposicoes"]}
props_pt = {int(p["id"]) for p in req("GET", "/proposicoes?pais=PT")["proposicoes"]}
ok(int(p_br["id"]) in props_br and int(p_uni["id"]) in props_br,
   "?pais=BR nas proposições também é inclusivo")
ok(int(p_br["id"]) not in props_pt and int(p_uni["id"]) in props_pt,
   "a proposição brasileira não aparece em PT, a universal sim")

print("\n== 9. fonte propaga idioma/país como PADRÃO do que o bot extrai ==")
f = req("POST", "/fontes/texto", json={
    "titulo": "Legislação brasileira", "texto": "texto", "contexto": "Direito",
    "ref": "lei:1", "idioma": "pt-BR", "pais": "BR",
})["fonte"]
ok(f["pais"] == "BR" and f["idioma"] == "pt-BR", "a fonte guarda o padrão herdado")
# o push NÃO informa pais nos itens: tem que herdar da fonte
req("POST", f"/fontes/{f['id']}/mapas", json={
    "conceitos": [
        {"rotulo": "Habeas corpus", "sentido": "Remédio constitucional contra prisão ilegal",
         "tipo": "classe"},
        {"rotulo": "Constituição", "sentido": "Norma fundamental do Estado", "tipo": "classe"},
    ],
    "proposicoes": [{"origem_rotulo": "Habeas corpus", "relacao": "pertence a",
                     "destino_rotulo": "Constituição"}],
})
mapa = req("GET", f"/fontes/{f['id']}/mapa")
ok(all(c["pais"] == "BR" for c in mapa["conceitos"]),
   "os conceitos herdaram pais=BR sem a IA informar nada")
ok(all(p["pais"] == "BR" for p in mapa["proposicoes"]),
   "as proposições também herdaram")

# e a IA pode SOBREPOR por item
req("POST", f"/fontes/{f['id']}/mapas", json={
    "conceitos": [
        {"rotulo": "Habeas corpus", "sentido": "Remédio constitucional contra prisão ilegal",
         "tipo": "classe"},
        {"rotulo": "Due process", "sentido": "Garantia processual geral", "tipo": "classe",
         "pais": "", "idioma": "en"},
    ],
    "proposicoes": [{"origem_rotulo": "Habeas corpus", "relacao": "pertence a",
                     "destino_rotulo": "Due process", "pais": ""}],
})
mapa2 = req("GET", f"/fontes/{f['id']}/mapa")
due = [c for c in mapa2["conceitos"] if c["rotulo"] == "Due process"]
ok(bool(due) and due[0]["pais"] == "", "a IA pode sobrepor o padrão e marcar universal")

print("\n== 10. esteios e mapa também respeitam idioma/país ==")
e = req("GET", "/esteios?idioma=en&pais=BR")
ok(e["idioma"] == "en" and e["pais"] == "BR", "esteios ecoam os filtros")
ok(all(x["pais"] in ("", "BR") for x in e["esteios"]), "e só trazem universal + BR")
rot = {x["rotulo"] for x in req("GET", "/esteios?idioma=en")["esteios"]}
ok("Door" in rot or "Due process" in rot, f"o rótulo sai no idioma pedido ({sorted(rot)[:4]})")

print()
if falhas:
    print(f"FALHAS ({len(falhas)}):")
    for x in falhas:
        print(f"  - {x}")
    sys.exit(1)
print("TODOS OS CHECKS PASSARAM")
