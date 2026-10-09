# E2E — ambiente local + teste do catálogo de trilhas (Passo 1)

Como **montar do zero um KDD local** e rodar o teste ponta-a-ponta do catálogo de
trilhas (Passo 1 — ver [`docs/catalogo-trilhas.md`](../docs/catalogo-trilhas.md)).
Um único script faz tudo: `teste/e2e_catalogo.sh`.

> **Por que um ambiente local?** O Passo 1 (bot consome `GET /catalogo` e materializa
> conceitos) precisa exercitar API + banco + bot juntos. Rodar contra **produção**
> escreveria fontes/conceitos reais e depende do deploy já ter a rota. O script sobe uma
> instância **descartável** (banco `kdd_local`, cópia da `api/` em scratch, porta 8077) e
> **nunca toca** no `api/.env`/`api/tokens.json` de produção nem no `~/.env`.

## TL;DR

```bash
cd ~/desenv/kdd
bash teste/e2e_catalogo.sh            # monta o ambiente e roda o teste
LIMPAR=1 bash teste/e2e_catalogo.sh   # idem, e apaga o scratch + o banco ao final
```

Saída esperada no fim: `== E2E OK ==` (18 asserts PASS).

## O que o script faz (idempotente)

1. **Deps** — instala só o que falta: `mariadb-server/-client`, `php-cli`, `php-mysql`
   (`pdo_mysql`), **`php-mbstring`** (o `POST /fontes/{id}/mapas` usa `mb_strtolower`;
   sem ela dá **HTTP 500** local — a Hostinger já tem), e `requests` para o Python
   (usa `bot/.venv` se existir, senão o `python3` do sistema).
2. **Banco local** — sobe o MariaDB e cria `kdd_local` + usuário `kddlocal` (descartável).
3. **Cópia da API em scratch** (`$TMPDIR/kdd_e2e`) — copia a `api/` EXCLUINDO os segredos
   e gera um `.env`/`tokens.json` **locais** apontando para o banco/porta/storage locais.
   A `api/` de produção fica intocada.
4. **Migrations** — roda `php migrate.php` na cópia (cria o schema no `kdd_local`).
5. **Sobe a API** (`php -S 127.0.0.1:8077`), **roda o teste** e **derruba a API** ao fim
   (via `trap EXIT`).

## O teste (`bot/exemplos/teste_catalogo.py`)

Duas partes:

- **A) Matcher offline** (sempre roda, sem rede/LLM) — os casos de casamento do catálogo:
  path por substring **case-sensitive** (`/etc/passwd` casa; `/ETC/PASSWD` não);
  termo por **palavra inteira case-insensitive** (`ssh` casa `SSH`; **`cron` NÃO casa em
  `crontab`**); `802.1Q` com pontuação nas bordas; sentido estável por tipo; dedup por
  sentido ao fundir no mapa.
- **B) E2E sem LLM** (só com a API local no ar) — sobe uma **fonte de texto** contendo um
  path e um termo do catálogo real, roda o `Pipeline` com uma **IA _stub_** (mapa vazio,
  para isolar o efeito do catálogo) e confere via `GET /fontes/{id}/mapa` que os dois
  termos viraram conceito. Como só o catálogo popula o mapa, o teste prova o Passo 1 sem
  depender de modelo nenhum.

A parte B só roda quando há `KDD_APP_URL` + `KDD_TOKEN_OPERADOR` no ambiente — o script os
injeta apontando para a instância local. Rodar `teste_catalogo.py` **sem** essas variáveis
executa só a parte A (útil como teste de unidade do matcher).

## Parâmetros (variáveis de ambiente, todas com padrão)

| Var | Padrão | O que é |
|---|---|---|
| `PORTA` | `8077` | porta do `php -S` local |
| `DB_NAME`/`DB_USER`/`DB_PASS` | `kdd_local`/`kddlocal`/`kddlocal123` | banco local descartável |
| `DB_HOST`/`DB_PORT` | `127.0.0.1`/`3306` | conexão MySQL |
| `TOKEN` | `op_local_teste_123456` | token operador da instância local |
| `SCRATCH` | `$TMPDIR/kdd_e2e` | onde a cópia da API é montada |
| `LIMPAR` | `0` | `1` = apaga scratch + banco ao final |

## Rodar só uma parte à mão

```bash
# só o matcher (parte A), sem subir nada:
python3 bot/exemplos/teste_catalogo.py

# contra uma API local já no ar (ex.: subida pelo próprio script noutro terminal):
KDD_APP_URL=http://127.0.0.1:8077 KDD_TOKEN_OPERADOR=op_local_teste_123456 \
  python3 bot/exemplos/teste_catalogo.py
```

## Solução de problemas

- **`HTTP 500` no `POST /fontes/{id}/mapas`** → falta `php-mbstring` (o script instala; se
  rodou antes da instalação, rode de novo).
- **API não sobe** → `SCRATCH/server.log` tem o erro do `php -S`. Porta ocupada? Use
  `PORTA=8078 bash teste/e2e_catalogo.sh`.
- **`Token inválido`/`401`** → o `tokens.json` local é gerado pelo script; não confunda com
  o de produção. O `TOKEN` do env tem que casar com o injetado (padrão já casa).
- **Banco não conecta** → confirme o MariaDB no ar (`sudo systemctl status mariadb`). Em
  Qubes AppVM, `/usr` e `/var/lib/mysql` não persistem no reboot — o script reinstala e
  recria o banco a cada execução.

---

# E2E — valor, esteios e camada vetorial

Segundo script no mesmo molde: `teste/e2e_valor.sh`. Verifica a camada que **lê** o grafo
e produz informação (ver [`docs/valor-conhecimento.md`](../docs/valor-conhecimento.md)).

```bash
cd ~/desenv/kdd
bash teste/e2e_valor.sh            # monta o ambiente e roda o teste
LIMPAR=1 bash teste/e2e_valor.sh   # idem, e apaga o scratch + o banco ao final
```

Ambiente próprio para não colidir com o do catálogo: banco `kdd_valor`, porta **8078**,
scratch `$TMPDIR/kdd_e2e_valor`, e o token local tem perfil **validador** (o teste também
exercita escrita de curadoria). Saída esperada: `== E2E VALOR OK ==`.

Diferenças em relação ao `e2e_catalogo.sh`:

- roda `php migrate.php` **duas vezes** — a migration `007_valor.sql` tem que ser idempotente;
- usa o **Ollama local de verdade** na parte vetorial (modelo `KDD_EMBED_MODEL`, padrão
  `nomic-embed-text` — `ollama pull nomic-embed-text`). Sem Ollama no ar, essa etapa é
  **pulada** com aviso e o resto do teste continua valendo.

## O que o teste (`teste/teste_valor.py`) cobre

1. **Aprovação automática** — fonte nasce `pendente`; depois do push está `aprovada`, sem
   ação humana. É a decisão "o que entrou está aprovado".
2. **Valor 0–100** — toda proposição traz `valor` e `valor_detalhe`; a lista vem ordenada
   por valor. Compara triplas na **mesma certeza**: entidade + verbo + classe fica no topo
   (85 na rodada de referência), conceitos sem tipo ligados por cópula ficam no piso (53).
3. **Reforço hierárquico** — comparação **controlada**: as mesmas duas pontas (logo mesmos
   tipos, mesma certeza e mesmo esteio), mudando só o verbo. `pertence a` dá 87 contra 78 de
   `relaciona-se com`; o verbo de ação não recebe bônus; e o bônus nunca estoura 100.
4. **Esteios** — `GET /esteios` ordena por grau decrescente e o conceito mais conectado
   lidera com esteio 100%.
5. **Tipo e curadoria** — o tipo que o bot mandou aparece no conceito; `PATCH /conceitos/{id}`
   altera; e um **re-push do bot NÃO sobrescreve** tipo definido por humano.
6. **Vetores** — `vetorizar()` embute os conceitos que faltam, grava os pares e deixa a fila
   vazia; uma quase-duplicata plantada de propósito ("Modelo de linguagem" × "Modelos de
   linguagem", sentidos diferentes logo conceitos diferentes) é detectada com ~98% de
   similaridade; a segunda passada não reembute nada.
7. **Veto** — `POST /fontes/{id}/reprovar` zera as fontes aprovadas e o valor da mesma
   proposição cai (85 → 70), provando que o reforço por fonte continua pesando.


---

# E2E — servidor MCP

Terceiro script no mesmo molde: `teste/e2e_mcp.sh` (banco `kdd_mcp_t`, porta **8080**,
scratch `$TMPDIR/kdd_e2e_mcp`). Verifica o servidor MCP (`mcp/`, spec
[`docs/mcp-servidor.md`](../docs/mcp-servidor.md)).

```bash
cd ~/desenv/kdd
bash teste/e2e_mcp.sh            # monta, popula, roda
LIMPAR=1 bash teste/e2e_mcp.sh   # idem + apaga o scratch e o banco
```

Exige o venv do MCP:

```bash
cd mcp && python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

O que o teste (`teste/teste_mcp.py`) faz de diferente: ele **não** chama funções Python por
dentro. Sobe o servidor como **subprocesso em stdio** e fala o protocolo com um cliente MCP
real, então mede o que um agente de verdade veria.

1. **Handshake** — `initialize` completa, o servidor se identifica como `kdd` e manda as
   `instructions` que explicam o domínio.
2. **Catálogo** — `tools/list` traz as 9 ferramentas de leitura, todas com descrição e
   anotadas `read_only_hint`.
3. **Escrita fechada por padrão** — sem `KDD_MCP_ESCRITA=1` nenhuma ferramenta de escrita é
   anunciada; com a flag, as 3 aparecem, não read-only e não destrutivas.
4. **A camada de valor chega ao agente** — as proposições vêm com `valor` 0–100 e
   `relacao_classe`, e a lista vem ordenada por valor.
5. **Erro vira texto** — pedir um conceito inexistente devolve `HTTP 404: Conceito não
   encontrado` como resultado legível, e o servidor continua vivo para a chamada seguinte.
6. **Escrita tem efeito real** — `ingerir_texto` com o mesmo `ref` duas vezes não duplica; e
   a proposição criada por MCP reaparece na leitura, classificada como taxonômica.


---

# E2E — universos paralelos

Quarto script no mesmo molde: `teste/e2e_universos.sh` (banco `kdd_univ`, porta **8081**,
scratch `$TMPDIR/kdd_e2e_univ`). Spec: [`docs/universos.md`](../docs/universos.md).

```bash
cd ~/desenv/kdd
bash teste/e2e_universos.sh            # monta, roda
LIMPAR=1 bash teste/e2e_universos.sh   # idem + apaga o scratch e o banco
```

O que `teste/teste_universos.py` cobre:

1. **Retrocompatibilidade** — a migration cria `principal` e leitura **sem** `?universo=`
   cai nele, então desktop e bot antigos seguem funcionando.
2. **Criação e validação** — slug repetido dá 409, slug malformado dá 400, e universo
   desconhecido dá **404** em vez de cair no padrão em silêncio.
3. **O mesmo sentido, dois conceitos** — "Porta" com texto de sentido idêntico existe nos
   dois universos como ids diferentes.
4. **Nada vaza** — conceitos, áreas, proposições, fontes e constelação ficam cada um no seu
   universo. E o mesmo rótulo no universo vizinho **não** conta como homônimo.
5. **Esteio relativo ao universo** — o universo grande tem hub de grau 7 e o pequeno de grau
   2, e **cada um** tem esteio 100% no seu topo: o pequeno não é esmagado pelo grande.
6. **Fronteiras** — proposição e merge entre universos são recusados com 409; dentro do
   mesmo universo seguem permitidos.
7. **Curadoria não vaza certeza** — a fonte sintética de curadoria é uma por universo.
8. **O mesmo PDF em dois universos** — aceito nos dois (duas lentes sobre o mesmo
   documento), barrado no reenvio ao mesmo universo.
9. **Contrapartes** — acha o gêmeo no universo paralelo e nunca devolve algo do próprio.
10. **Escopo dos semelhantes** — `interno`/`externo`/`todos` separam fila de fusão de lista
    de contrapartes; escopo inválido dá 400.

Além do script, a troca de universo no **desktop** foi verificada headless: o seletor lista
os dois universos, trocar isola conceitos e áreas, a aba Esteios acompanha, e voltar restaura
a visão anterior.


---

# E2E — idioma e país

`teste/e2e_idioma_pais.sh` (banco `kdd_ip`, porta **8082**). Spec:
[`docs/idioma-pais.md`](../docs/idioma-pais.md).

Cobre: retrocompatibilidade (base nasce `pt-BR`/universal); recusa de tag e código
malformados com 400; um conceito com rótulos em quatro idiomas, inclusive o **mesmo texto**
em `pt-BR` e `pt-PT`; escolha do rótulo por idioma **com fallback** quando falta a tradução;
mesmo sentido em países diferentes virando conceitos distintos; merge entre países barrado;
o **filtro inclusivo** de país (BR traz universal + BR, nunca PT); a mesma tripla valendo num
país e não noutro; e a fonte propagando `idioma`/`pais` como padrão do que o bot extrai,
com a IA podendo sobrepor por item.

---

# E2E — sentimento da proposição

`teste/e2e_sentimento.sh` (banco `kdd_sent`, porta **8083**). Spec:
[`docs/sentimento.md`](../docs/sentimento.md). Exige `vaderSentiment` e `textblob` no venv
do bot (`cd bot && .venv/bin/pip install -r requirements.txt`).

1. **O motor** — roda o `autoteste()` de `kdd_bot.sentimento` nas proposições de referência
   e confere que a relação é traduzida para inglês antes de medir.
2. **Não medido ≠ neutro** — proposição sem forma inglesa sai `nao_medida`.
3. **O desconto é só da subjetividade** — mesma forma de tripla e mesmas pontas: fato 77,
   juízo 62. O fato **negativo** não sofre desconto nenhum.
4. **Discordância** — duas fontes com polaridades opostas na mesma tripla se anulam na média
   e a amplitude fica alta.
5. **O veto funciona** — reprovar a fonte remove a contribuição dela do agregado, mesma
   mecânica da certeza.
6. **Ameaças e proteções** — o conceito separa o que o ataca do que o defende.
7. **Filtro** — `?polaridade=` traz só o pedido e recusa valor inválido.
