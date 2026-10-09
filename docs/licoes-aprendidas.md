# Lições aprendidas — 2026-10-09

> Armadilhas que **custaram depuração** ou que só apareceram numa varredura de revisão, com a
> evidência de cada uma. Diferente de [`decisoes-2026-10-09.md`](decisoes-2026-10-09.md), que
> registra *o que* foi decidido: aqui está o que **deu errado** e o que generaliza.
> Última atualização: 2026-10-09.

## 1. ⚠️ `ON DUPLICATE KEY UPDATE` + campo ausente = perda silenciosa

**Defeito ativo, introduzido nesta sessão.** Ao acrescentar sentimento à `referencia`, troquei

```sql
INSERT IGNORE INTO referencia (proposicao_id, fonte_id) VALUES (?, ?)
```

por

```sql
INSERT INTO referencia (proposicao_id, fonte_id, polaridade, subjetividade)
VALUES (?, ?, ?, ?)
ON DUPLICATE KEY UPDATE polaridade = VALUES(polaridade),
                        subjetividade = VALUES(subjetividade)
```

Quando o push **não traz** os campos, eles chegam como `NULL` e o `UPDATE` **sobrescreve a
medição anterior com NULL**.

Medido contra a API local:

| passo | polaridade | fontes medidas | valor |
|---|---|---|---|
| 1º push, com sentimento | −1 | 1 | 82 |
| 2º push da mesma fonte, sem os campos | **NULL** | **0** | — |

Dispara em três situações **reais**, não hipotéticas:

- bot rodando sem `vaderSentiment`/`textblob` instalados — é o estado da máquina de
  inferência até alguém instalar;
- reprocessamento de fonte com erro;
- qualquer cliente antigo que ainda não mande os campos novos.

**Correção**: `COALESCE(VALUES(polaridade), polaridade)`, que só sobrescreve quando vem valor.

🟡 **Decisão pendente**: com `COALESCE` deixa de ser possível **apagar** uma medição errada
mandando `NULL`. Para ter as duas coisas, é preciso um campo explícito de limpeza
(ex.: `"limpar_sentimento": true`). Não corrigido ainda.

**O que generaliza:** ao acrescentar coluna opcional a um upsert, o caminho
"reenvio **sem** o campo novo" é um caso de teste obrigatório. `INSERT IGNORE` preserva por
acidente; `ON DUPLICATE KEY UPDATE` destrói por padrão.

## 2. ⚠️ Seis suítes verdes e nenhuma pegou o item 1

Esta é a lição mais desconfortável do dia. Os testes cobriam:

- primeiro push **com** os campos novos → passou;
- push **sem** os campos, em proposição nova → passou (sai "não medida", correto).

E não cobriam: **push sem os campos sobre uma medição que já existia**. A combinação
"campo opcional" × "operação idempotente repetida" ficou fora.

**O que generaliza:** teste de idempotência não é só "rodar duas vezes e ver se duplica". É
rodar duas vezes **com payloads diferentes** — o segundo mais pobre que o primeiro — e
verificar o que sobrou. Vale para o push de mapa, para `PUT /similares` e para qualquer
upsert.

## 3. Camada nova levada até o fim na API e parada antes dos clientes

Varredura de cobertura dos quatro componentes:

| Camada | API | testes | MCP | desktop |
|---|---|---|---|---|
| valor, esteios, vetores | sim | sim | sim | sim |
| universos | sim | sim | sim | sim |
| idioma e país | sim | sim | **não** | **não** |
| sentimento | sim | sim | **não** | **não** |

Consequência concreta: um agente via MCP **não** consegue filtrar por país, escolher idioma,
nem perguntar "o que ameaça este conceito" — a leitura que **motivou** a camada de sentimento.
E o desktop não mostra polaridade em lugar nenhum, nem no diagrama nem no detalhe.

**O que generaliza:** API verde com teste verde **não** significa funcionalidade entregue. A
camada só existe para quem a consome. Um quadro de cobertura por componente, como o de cima,
deveria ser montado **ao fechar** cada camada, não numa varredura posterior.

🟡 **Pendente**: as duas lacunas.

## 4. `grau_max` global esmagaria o universo pequeno

Ao introduzir universos, `kdd_grau_max()` ainda era global. O esteio é
`ln(1+grau)/ln(1+grau_max)`, então um universo novo e pequeno teria **todo** o seu esteio
medido contra o maior hub do maior universo, e o valor das proposições dele despencaria sem
nenhuma razão de domínio.

Achado por raciocínio sobre a fórmula, antes de rodar. Hoje há teste: dois universos de
tamanhos diferentes, e **cada um** tem esteio 100% no seu topo.

**O que generaliza:** toda métrica **normalizada por um máximo** precisa que o escopo do
máximo seja revisto quando se acrescenta uma dimensão de particionamento. O mesmo valeria para
média, percentil ou z-score.

## 5. Fonte sintética única vazaria certeza entre universos

`kdd_fonte_curadoria()` criava **uma** fonte de curadoria por autor. Com universos, a
curadoria feita no universo B apoiaria proposições de B numa fonte de A — e a certeza
atravessaria a fronteira que é o ponto inteiro dos universos paralelos.

**O que generaliza:** objeto **sintético/singleton** (fonte de curadoria, usuário "sistema",
área "sem categoria") precisa ser multiplicado junto com a dimensão nova. É o tipo de linha
que ninguém lembra de particionar porque "é só uma".

## 6. Sentinela em vez de NULL, por causa do índice único

`conceito.pais` usa `''` para "universal", não `NULL`. Com `NULL`, o
`UNIQUE(universo_id, pais, sentido)` **não morderia**: MySQL/MariaDB tratam NULLs como
distintos entre si, então daria para inserir duas vezes o mesmo trio e **fragmentar a
identidade** em dois ids — exatamente a invariante que a migration 004 veio garantir.

**O que generaliza:** se a coluna entra num índice único, "ausência" precisa ser um **valor**,
não NULL.

## 7. Idempotência de DDL: a sintaxe exata importa

| O que eu escrevi | Resultado |
|---|---|
| `ALTER TABLE t ADD CONSTRAINT IF NOT EXISTS fk FOREIGN KEY (c) REFERENCES u(id)` | **erro de sintaxe** no MariaDB |
| `ALTER TABLE t ADD FOREIGN KEY IF NOT EXISTS fk (c) REFERENCES u(id)` | funciona |

A primeira forma passou na 1ª execução da migration e quebrou na 2ª, que é o pior modo de
falhar — parece idempotente até não ser.

**O que generaliza:** migration tem de ser executada **duas vezes** no teste, sempre. E
`migrate.php` não tem transação por arquivo, então uma falha no meio deixa o banco
parcialmente migrado — por isso `area(universo_id, nome)` ficou índice **comum**: um UNIQUE
sobre dado possivelmente duplicado falharia no meio, em produção.

## 8. Precedência do ternário em PHP dentro de concatenação

```php
// ERRADO: a atribuição acontece DEPOIS do ternário, e $filtro sai indefinida
"... WHERE x = ?" . ($filtro = f($pais) ? " AND $filtro" : '') . " ORDER BY ..."
```

Quebrou o `GET /esteios` com HTTP 500. **O que generaliza:** calcular numa linha separada;
atribuição embutida em expressão concatenada é ilegível e erra.

## 9. Ferramenta de NLP pontua o vocabulário, não a relação

Benchmark nas proposições do próprio armazém:

| Motor | Polaridade | Subjetividade |
|---|---|---|
| vaderSentiment puro | 7/13 | não tem o eixo |
| TextBlob puro | 3/13 | **13/13** |
| composição final | **13/13** | **13/13** |

As falhas do VADER não são aleatórias:

| proposição | VADER | por quê |
|---|---|---|
| `firewall blocks traffic` | −0,23 | "blocks" é ruim em inglês geral, bom em segurança |
| `patch fixes vulnerability` | −0,23 | o substantivo "vulnerability" arrasta a frase |
| `ransomware encrypts files` | 0,00 | não sabe que isso é péssimo |

**O que generaliza:** o gargalo é **domínio, não tamanho de modelo** — um transformer treinado
em resenhas erraria igual no "patch fixes vulnerability". E o mesmo verbo muda de valência
conforme **quem age**: `backup encrypts files` × `ransomware encrypts files`. Por isso a
composição final mede a polaridade do **verbo**, com inversão por agente malicioso, e deixa o
pacote cobrir o caso desconhecido.

**Corolário de método:** afirmação sobre qualidade de ferramenta precisa de medição no
**próprio domínio**. Números de benchmark público não transferem.

## 10. O stdout do stdio é o canal do protocolo

No servidor MCP, qualquer `print()` corromperia o JSON-RPC. Todo log vai para **stderr**.
Parece óbvio escrito assim, e não é na hora de depurar um handshake que falha sem mensagem.

**Também**: o SDK `mcp` 2.x renomeou `FastMCP` para `MCPServer` e passou os campos para
snake_case (`server_info`, `read_only_hint`, `structured_content`). Inspecionar a API
instalada custou menos que confiar na memória — e a mensagem de erro do próprio pacote
apontou a migração.

## Resumo das pendências abertas

| # | Pendência | Gravidade |
|---|---|---|
| 1 | reenvio sem sentimento apaga a medição | **defeito ativo**, provado, correção de 1 linha |
| — | fila sem reivindicação atômica e sem prazo de validade | defeito latente ([`messageria-filas.md`](messageria-filas.md)) |
| 3 | MCP sem idioma, país e sentimento | lacuna de cobertura |
| 3 | desktop sem sentimento | lacuna de cobertura |
| — | substituição do mapa conflita com o modo seções | latente, modo desligado por padrão |
| — | léxico de classe de relação só em pt-BR | enfraquece universo em inglês |
| — | nada desta sessão implantado em produção | 7 migrations pendentes |
