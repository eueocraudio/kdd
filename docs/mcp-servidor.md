# Especificação — Servidor MCP do KDD

> **Documento vivo / 1ª versão.** Deriva de [`especificacao.md`](especificacao.md) e
> [`valor-conhecimento.md`](valor-conhecimento.md). Última atualização: 2026-10-09.

## 1. O que é e por que existe

Quarta solução do repo (`mcp/`), ao lado de `api/`, `desktop/` e `bot/`. Expõe o armazém KDD
como **ferramentas MCP** (Model Context Protocol), para que um agente de IA — Claude Code, o
app desktop do Claude, qualquer cliente MCP — **consulte e alimente** a base de mapas
conceituais sem precisar saber HTTP, rotas ou tokens.

A especificação sempre disse que o armazém é "navegável por humanos **e máquinas**". Até agora
a parte "máquinas" era a Web API crua: o agente precisava montar URL, header de token e
interpretar JSON. O MCP troca isso por ferramentas nomeadas e descritas, que o modelo escolhe
sozinho.

**Não substitui a Web API.** É um **adaptador** sobre ela.

## 2. Decisão de arquitetura: adaptador fino, nunca um segundo backend

```
cliente MCP (Claude) ──stdio──> mcp/ (Python) ──HTTP+token──> api/ (PHP) ──> MySQL
```

O servidor MCP **não** fala com o MySQL e **não** reimplementa nada de domínio. Motivos:

- a `api/` é a **fonte da verdade** (identidade por sentido, certeza, changesets, aprovação);
- a fórmula do valor vive em `api/src/valor.php`. Uma segunda implementação divergiria no
  primeiro ajuste de peso — e já ajustamos os pesos duas vezes;
- o banco de produção está na Hostinger, atrás do mesmo `.htaccess` e tokens.

Consequência prática: **toda regra nova entra na API**, e o MCP só ganha a ferramenta que a
expõe. Se uma ferramenta MCP precisar de algo que a API não serve, o trabalho é na API.

## 3. Transporte e execução

- **stdio** (padrão): o cliente sobe o processo. É o caso de uso local (Claude Code/desktop).
- `streamable-http` fica disponível pelo SDK, mas **não** é alvo desta versão: exigiria
  autenticação própria, e aí o MCP deixaria de ser adaptador fino.

Não vai para a Hostinger (como `bot/` e `desktop/`). Roda na máquina de quem usa o agente.

## 4. Ferramentas

Nomes e descrições em português (padrão do repo). Leitura é `read_only_hint=True`.
As ferramentas de listagem aceitam `universo` (slug); sem ele, atuam no `principal`.

### Leitura (sempre disponível)

| Ferramenta | API por baixo | Para quê |
|---|---|---|
| `listar_universos` | `GET /universos` | os domínios isolados ([`universos.md`](universos.md)) |
| `obter_contrapartes` | `GET /conceitos/{id}/contrapartes` | o gêmeo do conceito nos universos paralelos |
| `buscar_conceitos` | `GET /conceitos?q=&area=` | achar conceito por rótulo/área |
| `obter_conceito` | `GET /conceitos/{id}` | detalhe: sentido, rótulos, áreas, proposições com **valor**, tipo, esteio, semelhantes |
| `listar_areas` | `GET /areas` | árvore de áreas |
| `listar_proposicoes` | `GET /proposicoes` | proposições ordenadas por valor |
| `listar_esteios` | `GET /esteios` | conceitos-pilar (maior grau) |
| `ver_constelacao` | `GET /constelacao` | visão macro: áreas, pontes interdisciplinares, homônimos |
| `listar_semelhantes` | `GET /similares` | quase-duplicatas (fila de merge) |
| `obter_mapa_da_fonte` | `GET /fontes/{id}/mapa` | o mapa conceitual de um documento |
| `listar_fontes` | `GET /fontes` | fila: status de processamento e aprovação |

### Escrita (desligada por padrão)

| Ferramenta | API por baixo | Observação |
|---|---|---|
| `ingerir_texto` | `POST /fontes/texto` | idempotente por `ref`; a fonte entra na fila do bot |
| `criar_conceito` | `POST /conceitos` | exige perfil validador |
| `criar_proposicao` | `POST /proposicoes` | exige validador; conceitos por **id** |

**Por que desligada por padrão:** o KDD é base **curada**; deixar um agente escrever sem
supervisão contraria o princípio. Some-se a aprovação automática (um push já conta na certeza)
e um agente alucinando viraria conhecimento "certo". Então:

```
KDD_MCP_ESCRITA=1  +  KDD_TOKEN_VALIDADOR presente  ⇒  ferramentas de escrita registradas
```

Faltando qualquer um dos dois, o servidor sobe **somente leitura** e nem anuncia as
ferramentas de escrita — o modelo não vê o que não pode usar. Nenhuma escrita é destrutiva:
não há remover, desabilitar, merge nem split por MCP (isso é curadoria humana no desktop).

🟡 **PENDENTE**: expor `aprovar`/`reprovar` fonte por MCP. Hoje fora — é o único ato de
**veto** humano que sobrou depois da aprovação automática.

## 5. Configuração

Mesmas chaves do resto do repo (ambiente ou `~/.env`), via um `Config` próprio espelhando o
do bot:

| Chave | Default | Função |
|---|---|---|
| `KDD_APP_URL` | — | URL da Web API (obrigatória) |
| `KDD_TOKEN_OPERADOR` / `KDD_TOKEN` | — | token de leitura (obrigatório) |
| `KDD_TOKEN_VALIDADOR` | — | habilita escrita, junto com a flag |
| `KDD_MCP_ESCRITA` | `0` | `1` registra as ferramentas de escrita |
| `KDD_MCP_TIMEOUT` | `30` | timeout HTTP em segundos |

## 6. Tratamento de erro

Erro de HTTP/rede volta como **texto de erro da ferramenta**, nunca exceção crua: o modelo
precisa ler a mensagem e decidir. Mensagens em português, prefixadas com o status (ex.:
`HTTP 404: Conceito não encontrado`). Um 401 diz explicitamente que o token não serve.

## 7. Critérios de aceite

1. `mcp/.venv/bin/python -m kdd_mcp` sobe em stdio e completa o handshake `initialize`.
2. `tools/list` devolve as 11 ferramentas de leitura; sem `KDD_MCP_ESCRITA=1` **não** aparece
   nenhuma de escrita; com a flag + token de validador, aparecem as 3.
3. `buscar_conceitos` e `obter_conceito` devolvem os campos da camada de valor (`valor`,
   `relacao_classe`, `esteio`).
4. Erro de API (404, 401) chega ao cliente como texto legível, sem derrubar o servidor.
5. `ingerir_texto` com o mesmo `ref` duas vezes não duplica fonte.
