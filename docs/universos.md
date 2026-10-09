# Especificação — Universos paralelos (múltiplos domínios)

> **Documento vivo / 1ª versão.** Deriva de [`especificacao.md`](especificacao.md).
> Última atualização: 2026-10-09.

## 1. O pedido e a leitura dele

> "precisamos ter múltiplos domínios e ter algo bem parecido com universo paralelo"

Leitura: o armazém precisa hospedar **vários domínios de conhecimento independentes**, que
coexistem sem se contaminar. O mesmo rótulo **e** o mesmo sentido podem existir em cada um,
em paralelo, com relações, certezas e valores próprios. É um **universo** por domínio.

"Domínio" aqui é **domínio de conhecimento**, não domínio web. Se mais adiante cada universo
for servido sob um site próprio (`wellington.tec.br/kdd`, cursohacker, …), o `slug` do
universo é o gancho para isso — mas é questão de **deploy**, não de modelo de dados, e fica
fora desta spec.

## 2. ⚠️ Esta spec INVERTE uma decisão firme

O `CLAUDE.md` e a especificação dizem, com toda a razão até aqui:

> **Identidade do conceito é o SENTIDO, não o rótulo.**
> **Área é dimensão N–N, nunca critério de identidade.**

Universo **é** o critério de identidade que a área tinha proibição de ser. A identidade passa
de `sentido` para **`(universo, sentido)`**:

```
antes:  UNIQUE (sentido)
agora:  UNIQUE (universo_id, sentido)
```

Isso é deliberado e tem que ficar explícito, porque é o inverso do que o projeto afirmava.
O que **não** muda: dentro de um universo a identidade continua sendo o sentido, e a área
continua sendo dimensão N–N sem poder de identidade. O universo não é "uma área grande": é o
plano onde a área existe.

**Por que não resolver com área-raiz.** Já existe algo nessa direção: `fonte.contexto` é a
"lente"/área-raiz da fonte. Mas área é N–N e não isola nada — com `UNIQUE(sentido)` global,
dois domínios que definissem "Porta" com o mesmo sentido viravam **um** conceito, e mesmo com
sentidos diferentes tudo dividia o mesmo grafo: homônimos, pontes, esteio e `grau_max`
misturados. Área classifica; universo **separa**.

## 3. O que é paralelo e o que é isolado

| Objeto | Escopo |
|---|---|
`conceito`, `area`, `fonte` | **do universo** (coluna `universo_id`) |
`rotulo`, `conceito_area`, `fonte_area` | do pai (herdam o universo) |
`proposicao` | **do universo**, por derivação: só liga conceitos do MESMO universo |
`referencia`, `conceito_fonte` | do par (fonte e conceito são do mesmo universo) |
`embedding` | por conceito (logo, do universo dele) |
`conceito_similar` | **pode CRUZAR universos** — é de propósito, ver §5 |

**Proposição nunca cruza universo.** Validado na escrita (API recusa com 409). É o que mantém
cada universo com sua própria verdade: certeza, valor e esteio calculados só com o que existe
ali. Ligação entre universos não é proposição, é **contraparte** (§5).

### O esteio é relativo ao universo

`esteio(c) = ln(1+grau) / ln(1+grau_max)`. Se `grau_max` fosse global, um universo novo e
pequeno teria todo o seu esteio esmagado pelo maior hub do maior universo, e o valor das
proposições dele despencaria sem nenhuma razão de domínio. Então **`grau_max` passa a ser por
universo** (`kdd_grau_max($pdo, $universoId)`, cache por universo). Esse é o ponto mais
fácil de errar nesta mudança.

## 4. Modelo de dados (migration `008_universos.sql`)

```sql
universo(id, slug UNIQUE, nome, descricao, criado_em)
```

- `conceito.universo_id`, `area.universo_id`, `fonte.universo_id` — `NOT NULL`, default 1.
- Universo **1 = `principal`**, criado pela migration; todas as linhas existentes são
  retroalimentadas nele. **Nenhum dado de produção se move.**
- Unicidades que passam a incluir o universo: `conceito(universo_id, sentido)`,
  `fonte(universo_id, ref)`, `fonte(universo_id, arquivo_hash)`.
  - Trocar essas é **seguro**: tudo que era único globalmente continua único dentro do
    universo 1.
  - Ganho de domínio no hash: **o mesmo PDF pode ser ingerido em dois universos** — ler o
    mesmo documento por duas lentes é justamente o caso de uso.
- `area(universo_id, nome)` ganha só um índice **comum**, não único: `area.nome` nunca foi
  único (o dedup é `SELECT`-antes-de-`INSERT` em `kdd_upsert_area`), e criar um UNIQUE sobre
  dado possivelmente duplicado faria a migration **falhar no meio** em produção —
  `migrate.php` não tem transação por arquivo.

## 5. Contrapartes: o que torna os universos "paralelos"

Isolar é metade. A outra metade é poder **comparar**: ver o mesmo conceito existindo em dois
universos, com relações diferentes. Duas pontes, nenhuma delas proposição:

1. **Por rótulo** — mesmo texto de rótulo em universos distintos (exato, sem acento/caixa).
2. **Por vetor** — a camada vetorial ([`valor-conhecimento.md`](valor-conhecimento.md) §6) já
   calcula cosseno par a par **sem olhar universo**. Um par cujos dois lados estão em
   universos diferentes **não** é candidato a fusão: é contraparte. O mesmo cálculo serve aos
   dois fins, só muda a leitura.

`GET /conceitos/{id}/contrapartes` devolve as duas coisas, cada item dizendo o universo, a
origem do casamento (`rotulo` | `vetor`) e a similaridade quando houver.

`GET /similares` passa a marcar `mesmo_universo` em cada par, e aceita
`?escopo=interno|externo|todos` (padrão `interno`) — assim a fila de merge do curador não se
mistura com a lista de contrapartes.

**Fusão entre universos é proibida** (`POST /conceitos/{id}/merge` recusa com 409): fundir
destruiria o isolamento que é o ponto da coisa.

## 6. API

Resolução do universo em `kdd_universo_req()`: `?universo=<slug ou id>` nas leituras, campo
`universo` no corpo das escritas. Ausente ⇒ **`principal`**, o que mantém o desktop e o bot
atuais funcionando sem mudar nada. Universo desconhecido ⇒ 404.

| Rota | Nota |
|---|---|
`GET /universos` | lista, com contagem de conceitos/fontes |
`POST /universos` | validador; `{slug, nome, descricao}` |
`GET /conceitos`, `/areas`, `/proposicoes`, `/esteios`, `/constelacao`, `/fontes` | filtram pelo universo |
`GET /conceitos/{id}`, `/fontes/{id}/mapa` | id é global; a resposta **diz** o universo |
`GET /conceitos/{id}/contrapartes` | o par paralelo (§5) |
`POST /fontes`, `/fontes/texto`, `/conceitos`, `/areas` | aceitam `universo` |
`POST /fontes/{id}/mapas` | universo vem **da fonte**, nunca do corpo |
`POST /proposicoes` | 409 se os conceitos forem de universos diferentes |

O bot **não muda**: ele varre as fontes pendentes de todos os universos e o push herda o
universo da fonte.

## 7. Fora de escopo

Mover conceito entre universos; universo hierárquico (universo dentro de universo); permissão
por universo (o acesso segue sendo por token, organizacional); servir cada universo sob um
domínio web próprio.

## 8. Critérios de aceite

1. Migration idempotente (roda 2×), cria `principal` e retroalimenta tudo nele; base
   existente continua respondendo igual **sem** passar `?universo`.
2. O mesmo `sentido` pode existir em dois universos, como conceitos distintos.
3. Leitura filtrada por universo não vaza conceito/proposição/área/fonte do outro.
4. `esteio` de um universo pequeno **não** é afetado pelo tamanho do outro (`grau_max` por
   universo).
5. Proposição entre universos é recusada com 409; merge entre universos também.
6. O mesmo PDF (mesmo hash) entra em dois universos; reenviar no **mesmo** universo é barrado.
7. `contrapartes` acha o conceito gêmeo no outro universo por rótulo e por vetor.
8. MCP e desktop deixam escolher o universo.
