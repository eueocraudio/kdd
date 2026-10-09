#!/usr/bin/env python3
"""E2E dos UNIVERSOS PARALELOS (docs/universos.md §8).

Roda contra a API apontada por KDD_APP_URL (o e2e_universos.sh sobe uma LOCAL descartável).
NÃO aponte para produção.
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


def req(metodo: str, caminho: str, esperado: int | None = None, **kw):
    r = requests.request(metodo, f"{BASE}{caminho}", headers=H, timeout=60, **kw)
    if esperado is not None:
        if r.status_code != esperado:
            raise SystemExit(f"esperava HTTP {esperado} em {metodo} {caminho}, "
                             f"veio {r.status_code}: {r.text[:300]}")
        return r.json()
    if r.status_code >= 400:
        raise SystemExit(f"HTTP {r.status_code} em {metodo} {caminho}: {r.text[:300]}")
    return r.json()


def status(metodo: str, caminho: str, **kw) -> tuple[int, dict]:
    r = requests.request(metodo, f"{BASE}{caminho}", headers=H, timeout=60, **kw)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


print("== 1. o universo padrão existe e a base antiga responde sem ?universo= ==")
d = req("GET", "/universos")
slugs = {u["slug"] for u in d["universos"]}
ok("principal" in slugs, f"universo 'principal' criado pela migration (slugs: {sorted(slugs)})")
ok(d["padrao"] == "principal", "a API declara 'principal' como padrão")
# sem ?universo= tudo continua funcionando (retrocompatibilidade do desktop/bot)
ok(req("GET", "/conceitos")["universo"]["slug"] == "principal",
   "leitura sem ?universo= cai no principal")

print("\n== 2. criar um segundo universo ==")
d = req("POST", "/universos", 201, json={
    "slug": "medicina", "nome": "Medicina", "descricao": "Universo paralelo de teste",
})
u2 = d["universo"]
ok(u2["slug"] == "medicina", f"universo 'medicina' criado (id {u2['id']})")
c, _ = status("POST", "/universos", json={"slug": "medicina", "nome": "Dup"})
ok(c == 409, "slug repetido é recusado com 409")
c, _ = status("POST", "/universos", json={"slug": "NÃO VALE", "nome": "x"})
ok(c == 400, "slug inválido é recusado com 400")
c, _ = status("GET", "/conceitos?universo=inexistente")
ok(c == 404, "universo desconhecido dá 404 em vez de cair no padrão em silêncio")


def semear(universo: str, rotulo_extra: str, n_props: int) -> int:
    """Cria uma fonte e um mapa num universo. Devolve o id da fonte."""
    f = req("POST", "/fontes/texto", json={
        "titulo": f"Fonte {universo}", "texto": "texto", "contexto": f"Raiz {universo}",
        "ref": "seed:1", "universo": universo,
    })["fonte"]
    conceitos = [
        {"rotulo": "Porta", "sentido": "SENTIDO COMPARTILHADO ENTRE UNIVERSOS",
         "tipo": "classe", "areas": [f"Área {universo}"]},
        {"rotulo": rotulo_extra, "sentido": f"Conceito só de {universo}",
         "tipo": "entidade", "areas": [f"Área {universo}"]},
    ]
    props = [{"origem_rotulo": rotulo_extra, "relacao": "pertence a", "destino_rotulo": "Porta"}]
    # n_props extra para dar graus diferentes aos dois universos
    for i in range(n_props):
        conceitos.append({"rotulo": f"{universo}-{i}", "sentido": f"Satélite {i} de {universo}",
                          "tipo": "entidade"})
        props.append({"origem_rotulo": f"{universo}-{i}", "relacao": "pertence a",
                      "destino_rotulo": "Porta"})
    req("POST", f"/fontes/{f['id']}/mapas", json={"conceitos": conceitos, "proposicoes": props})
    return int(f["id"])


print("\n== 3. o MESMO sentido vira conceitos distintos em universos distintos ==")
semear("principal", "Rede", 1)
semear("medicina", "Anatomia", 6)

cp = req("GET", "/conceitos?universo=principal&q=Porta")["conceitos"]
cm = req("GET", "/conceitos?universo=medicina&q=Porta")["conceitos"]
ok(len(cp) == 1 and len(cm) == 1, "'Porta' existe em cada universo")
id_p, id_m = int(cp[0]["id"]), int(cm[0]["id"])
ok(id_p != id_m, f"são conceitos DIFERENTES ({id_p} x {id_m}) apesar do sentido idêntico")
ok(cp[0]["sentido"] == cm[0]["sentido"], "o sentido é literalmente o mesmo texto")

print("\n== 4. nada vaza entre universos ==")
rotulos_p = {c["rotulos"] for c in req("GET", "/conceitos?universo=principal")["conceitos"]}
rotulos_m = {c["rotulos"] for c in req("GET", "/conceitos?universo=medicina")["conceitos"]}
ok("Rede" in str(rotulos_p) and "Rede" not in str(rotulos_m), "conceito do principal não aparece em medicina")
ok("Anatomia" in str(rotulos_m) and "Anatomia" not in str(rotulos_p), "e vice-versa")

areas_p = {a["nome"] for a in req("GET", "/areas?universo=principal")["areas"]}
areas_m = {a["nome"] for a in req("GET", "/areas?universo=medicina")["areas"]}
ok(not (areas_p & areas_m), f"áreas não se misturam ({sorted(areas_p)} x {sorted(areas_m)})")

props_p = req("GET", "/proposicoes?universo=principal")["proposicoes"]
props_m = req("GET", "/proposicoes?universo=medicina")["proposicoes"]
ids_p = {p["id"] for p in props_p}
ids_m = {p["id"] for p in props_m}
ok(not (ids_p & ids_m), f"proposições não se misturam ({len(ids_p)} x {len(ids_m)})")

fontes_p = req("GET", "/fontes?universo=principal")["fontes"]
ok(all(f["universo_id"] == 1 for f in fontes_p), "fontes filtram por universo")
todas = req("GET", "/fontes")["fontes"]
ok(len({f["universo_id"] for f in todas}) == 2,
   "SEM ?universo= a fila traz todos os universos (é assim que o bot varre)")

const_p = req("GET", "/constelacao?universo=principal")
ok(all("medicina" not in str(a["nome"]) for a in const_p["areas"]),
   "constelação é do universo pedido")
ok(not any(h["rotulo"] == "Porta" for h in const_p["homonimos"]),
   "'Porta' em outro universo NÃO é homônimo (é contraparte)")

print("\n== 5. esteio é relativo ao universo (grau_max por universo) ==")
e_p = req("GET", "/esteios?universo=principal")["esteios"]
e_m = req("GET", "/esteios?universo=medicina")["esteios"]
topo_p = next(c for c in e_p if c["rotulo"] == "Porta")
topo_m = next(c for c in e_m if c["rotulo"] == "Porta")
grau = lambda c: c["grau"]["saida"] + c["grau"]["entrada"]  # noqa: E731
ok(grau(topo_m) > grau(topo_p),
   f"medicina é maior: grau {grau(topo_m)} contra {grau(topo_p)} do principal")
ok(topo_p["esteio"] == 100 and topo_m["esteio"] == 100,
   "o maior hub de CADA universo tem esteio 100% — o universo pequeno não é esmagado "
   f"pelo grande (principal={topo_p['esteio']}%, medicina={topo_m['esteio']}%)")

print("\n== 6. proposição e fusão NÃO cruzam universos ==")
c, d = status("POST", "/proposicoes", json={"origem_id": id_p, "relacao": "é", "destino_id": id_m})
ok(c == 409, f"proposição entre universos recusada com 409 ({d.get('erro', '')[:60]}...)")
c, d = status("POST", f"/conceitos/{id_p}/merge", json={"outro_id": id_m})
ok(c == 409, f"merge entre universos recusado com 409 ({d.get('erro', '')[:60]}...)")
# dentro do mesmo universo continua funcionando
c, _ = status("POST", "/proposicoes", json={"origem_id": id_p, "relacao": "contém",
                                           "destino_id": int(next(
                                               x["id"] for x in req("GET", "/conceitos?universo=principal")["conceitos"]
                                               if x["rotulos"] == "Rede"))})
ok(c == 201, "proposição DENTRO do mesmo universo segue permitida")

print("\n== 7. curadoria não vaza certeza entre universos ==")
fontes_m = req("GET", "/fontes?universo=medicina")["fontes"]
cur_m = [f for f in fontes_m if f["titulo"].startswith("Curadoria")]
cur_p = [f for f in req("GET", "/fontes?universo=principal")["fontes"]
         if f["titulo"].startswith("Curadoria")]
ok(bool(cur_p), "a fonte de curadoria do principal existe")
ok(all(f["universo_id"] == 1 for f in cur_p), "e pertence ao universo principal")
ok(not cur_m, "medicina não ganhou fonte de curadoria do outro universo")

print("\n== 8. o mesmo PDF entra em dois universos, mas não duplica no mesmo ==")
import io  # noqa: E402
conteudo = b"%PDF-1.4 conteudo identico para os dois universos"


def upload(universo: str):
    return requests.post(f"{BASE}/fontes", headers=H, timeout=60,
                         files={"arquivo": ("doc.pdf", io.BytesIO(conteudo), "application/pdf")},
                         data={"titulo": "Mesmo doc", "universo": universo})


r1 = upload("principal")
ok(r1.status_code == 201, f"1º upload no principal: {r1.status_code}")
r2 = upload("medicina")
ok(r2.status_code == 201, f"MESMO conteúdo aceito em medicina: {r2.status_code} "
                          "(ler o mesmo documento por duas lentes)")
r3 = upload("principal")
ok(r3.status_code == 409, f"reenviar no MESMO universo é barrado: {r3.status_code}")

print("\n== 9. mesmo 'ref' pode existir nos dois universos ==")
f_p = req("GET", "/fontes?universo=principal")["fontes"]
f_m = req("GET", "/fontes?universo=medicina")["fontes"]
ok(any(f["titulo"] == "Raiz principal" for f in f_p) and
   any(f["titulo"] == "Raiz medicina" for f in f_m),
   "as duas fontes com ref='seed:1' coexistem, uma por universo")

print("\n== 10. contrapartes: o gêmeo no universo paralelo ==")
d = req("GET", f"/conceitos/{id_p}/contrapartes")
ok(d["conceito"]["universo"]["slug"] == "principal", "a base diz de que universo parte")
alvos = {c["id"] for c in d["contrapartes"]}
ok(id_m in alvos, f"achou 'Porta' de medicina como contraparte (por {[c['casamento'] for c in d['contrapartes'] if c['id'] == id_m]})")
ok(all(c["universo"]["slug"] != "principal" for c in d["contrapartes"]),
   "contraparte é SEMPRE de outro universo")
ok(d["por_rotulo"] >= 1, f"casou por rótulo ({d['por_rotulo']})")

print("\n== 11. escopo dos semelhantes separa fusão de contraparte ==")
for escopo in ("interno", "externo", "todos"):
    c, dd = status("GET", f"/similares?escopo={escopo}&min=0.1")
    ok(c == 200 and dd.get("escopo") == escopo, f"escopo={escopo} aceito")
c, _ = status("GET", "/similares?escopo=xpto")
ok(c == 400, "escopo inválido dá 400")

print()
if falhas:
    print(f"FALHAS ({len(falhas)}):")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("TODOS OS CHECKS PASSARAM")
