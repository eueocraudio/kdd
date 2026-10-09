# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Língua

O usuário conversa em **português**. Código, comentários, mensagens de log e documentação deste repositório são em português — mantenha esse padrão.

## O que é o KDD

KDD (Knowledge Discovery in Databases) extrai conhecimento de PDFs e o representa como **Mapas Conceituais** (Novak) numa base navegável por humanos e máquinas, com curadoria humana. **Não** é sistema de ensino.

Quatro soluções sobre um núcleo comum (o "armazém"):

1. **`api/`** — Web API PHP + MySQL: a fonte da verdade. Versiona, gerencia aprovação, serve consulta e recebe escrita de curadoria. Headless (só JSON). **Em produção na Hostinger** em `https://wellington.tec.br/kdd` — roda em **subdiretório**, por isso `request_path()` (`api/src/http.php`) desconta o prefixo do `SCRIPT_NAME`; sem isso toda rota cai em 404.
2. **`desktop/`** — cliente PySide6: navega áreas/conceitos/constelação/mapas (leitura) **e edita** (curadoria manual). Abas: "Áreas e Conceitos", "Mapas" (diagrama visual em `mapa.py`), "Fila" (status de processamento das fontes). O modo edição só aparece quando há `KDD_TOKEN_VALIDADOR` (ver Editor abaixo).
3. **`bot/`** — bot Python (Marco 3): lê PDFs pendentes, extrai mapas com IA e empurra propostas para aprovação humana.
4. **`mcp/`** — servidor MCP Python: expõe o armazém como **ferramentas** para agentes de IA (Claude Code etc.). **Adaptador fino sobre a API**, não um segundo backend — ver abaixo.

`docs/especificacao.md` e `docs/plano-implementacao.md` têm a especificação completa e os marcos; `docs/editor-mapas.md` especifica o editor manual; `docs/valor-conhecimento.md` a camada de valor/esteios/vetores; `docs/mcp-servidor.md` o servidor MCP; `docs/universos.md` os universos paralelos; `docs/idioma-pais.md` idioma e país; `docs/sentimento.md` o sentimento da proposição. **Modo de trabalho: especificar antes de codar.**

## Modelo de domínio (essencial para mexer no código)

- **Identidade do conceito é `(universo, SENTIDO)`**, não o rótulo. Dentro de um universo a identidade é o sentido: rótulos iguais com sentidos diferentes são conceitos diferentes (homônimos: ex. "Botafogo" time × bairro). A tabela `conceito` guarda `sentido`; `rotulo` é N-por-conceito. ⚠️ O universo entrou na identidade na migration 008 — ver a seção de universos abaixo.
- **Área é dimensão N–N** (`conceito_area`), nunca critério de identidade. Áreas são hierárquicas via `area.parent_id`.
- **Proposição** = tripla `conceito_origem -[relacao]-> conceito_destino` (pode cruzar áreas).
- **"Constelação"** interliga áreas via homônimos e pontes interdisciplinares.
- **Certeza** = nº de fontes **aprovadas** que sustentam uma proposição (view `vw_certeza_proposicao`). Aprovação é **por fonte, tudo-ou-nada**: `status_aprovacao` vive em `fonte`. Reprovar derruba a certeza sem recálculo. ⚠️ O COUNT da view é sobre `f.id` (lado aprovado do LEFT JOIN), **não** `r.fonte_id` — senão referências de fontes pendentes/reprovadas continuariam contando.
- Fonte tem **dois status independentes**: `status_proc` (pendente→processando→processado/erro, controlado pelo bot) e `status_aprovacao` (pendente→aprovada/reprovada). **Desde a camada de valor, o push aprova automaticamente** (ver abaixo) — o humano age por **veto**.
- **Tipo do conceito** (`conceito.tipo`): `entidade | classe | processo | atributo | outro`, ou `NULL`. Não é identidade nem classificação temática (isso é área) — é o **peso** do conceito na fórmula do valor. O bot preenche só quando está `NULL`; a curadoria manda.

## Valor do conhecimento, esteios e vetores (`docs/valor-conhecimento.md`)

Primeira camada que **lê** o grafo e produz informação nova, em vez de só guardar o que a IA extraiu. Decisões do idealizador que a moldaram: relação **não** se tipa (vocabulário fechado não cabe no domínio), o que entra está aprovado, e esteio é o conceito que sustenta muitas relações.

- **Valor 0–100 por proposição** (`api/src/valor.php`, `kdd_enriquecer_proposicoes`): `0,45·estrutura + 0,30·reforço + 0,25·esteio`, mais o bônus taxonômico abaixo. **estrutura** = média dos pesos do tipo da origem, da relação e do tipo do destino; **reforço** = `n/(n+1)` com n = fontes aprovadas; **esteio** = grau dos dois conceitos em escala log sobre o maior grau do armazém. Uma tripla entidade + verbo + classe é o teto; sem tipo + associação vaga é o piso.
- **A relação não é tipada** (vocabulário fechado não cabe no domínio), só classificada em quatro baldes por duas listas curáveis: **taxonômica** 1,0 (`KDD_RELACOES_TAXONOMICAS` — os verbos **pertencer, ser, estar, incluir** e parentes: conter, compor, fazer parte de), **verbal** 1,0 (ação específica), **vaga** 0,5 (`KDD_RELACOES_VAGAS` — relaciona-se com, associado a, tem, possui) e **vazia** 0,3 (token ≤ 3 letras fora das listas). ⚠️ As listas são checadas **antes** do corte por tamanho, senão "é" e "tem" cairiam em vazia. As listas trazem as flexões, porque a IA emite o verbo conjugado.
- **Bônus taxonômico**: relação de hierarquia ganha `+0,10 × (1 − base)` — sobre a **folga** até 100, nunca somado direto, então o valor jamais estoura. Razão: num mapa de Novak a hierarquia é o esqueleto, e esses verbos é que entregam a "classificação" do padrão de maior valor. Medido com as mesmas pontas, `pertence a` dá 87 contra 78 de `relaciona-se com`. `valor_detalhe` expõe `relacao_classe` e `bonus_taxonomico` para o curador ver o porquê.
- **Nada disso é persistido** — é cálculo em leitura sobre o grafo, que continua a única verdade. `GET /proposicoes`, `GET /conceitos/{id}` e `GET /fontes/{id}/mapa` devolvem `valor` + `valor_detalhe` e vêm ordenados por valor; conceitos ganham `tipo`, `grau` e `esteio`.
- **Aprovação automática** (decisão: "é impossível aprovar tanta informação; o que entrou está aprovado"): `POST /fontes/{id}/mapas` promove a fonte `pendente`→`aprovada` ao marcar `processado`. `reprovada` é respeitada (veto vence o bot). Desligável com `APROVACAO_AUTOMATICA=0` no `.env` da API.
- **`GET /esteios?limite=N`** — os conceitos-pilar, por grau decrescente (view `vw_grau_conceito`). Aba "Esteios" no desktop.
- **Camada vetorial**: embedding por conceito (`"<rótulo>: <sentido>"`) calculado **no bot** (`bot/kdd_bot/vetor.py`, `main.py --vetorizar`) via Ollama `/api/embed`, modelo `KDD_EMBED_MODEL` (padrão `nomic-embed-text`). Guardado como JSON na tabela `embedding` — a Hostinger não tem tipo VECTOR, e o PHP só guarda e serve. O cosseno par a par roda no bot (numpy se houver, Python puro senão) e os pares acima de `KDD_SIMILAR_MIN` (0,85) vão para `conceito_similar` via `PUT /similares`, que **substitui** os pares do modelo. Uso: achar **quase-duplicatas** que a identidade por sentido exato não pega, como sugestão de merge (`GET /similares`, `similares` no detalhe do conceito).
- ⚠️ Na .90 o Ollama é de **slot único atrás do rolhama**; `--vetorizar` bate direto no Ollama e pode colidir com os outros consumidores. Por isso hoje se roda do notebook contra a API, não no serviço da .90.

## Fluxo de ingestão (como as peças se conectam)

```
humano faz upload PDF → POST /fontes (operador)
bot: GET /fontes?status_proc=pendente → PATCH processando → GET /fontes/{id}/arquivo
   → pypdf extrai texto → IAFacade.extrair_mapa() → PATCH areas → POST /fontes/{id}/mapas
validador humano: POST /fontes/{id}/aprovar | /reprovar  → só então a certeza sobe
```

`POST /fontes/{id}/mapas` é uma transação que **SUBSTITUI** o mapa daquela fonte (commit 2606848): primeiro apaga os vínculos por-fonte (`conceito_fonte` e `referencia` daquele `fonte_id`; `fonte_area` é preservado — guarda a área-raiz/contexto), depois resolve conceitos por **sentido exato** (helper `kdd_resolver_conceito` em `api/src/handlers/fontes.php`) e faz upsert. Conceitos, proposições e áreas são globais e deduplicados — esse endpoint nunca os apaga, só o vínculo com a fonte. Limitações conhecidas:
- dentro de um mesmo push, proposições referenciam conceitos por rótulo (colisão se dois sentidos do mesmo rótulo no mesmo PDF);
- ⚠️ o REPLACE **conflita com o modo seções** do bot (abaixo), que faz vários pushes por fonte: cada push apaga os vínculos do anterior e sobra só o último (hoje, o do catálogo). Não ativar `--secoes`/`KDD_CHARS_POR_SECAO` em produção antes de resolver (ex.: só o 1º push da fonte limpa, ou acumular o mapa no bot e fazer um push único).

**Extração por seções** (`KDD_CHARS_POR_SECAO`/`--secoes CHARS`, `KDD_MAX_CHARS_TOTAL` (400k), `KDD_MAX_SECOES`/`--max-secoes`; padrão **desligado** = passada única truncada em `KDD_MAX_CHARS_PDF`=60k): `pdf.extrair_secoes` divide o texto inteiro respeitando parágrafos e `Pipeline._processar_em_secoes` faz 1 chamada de IA + 1 push por seção. Seção que falha só loga WARNING; se todas falharem a fonte vai para `erro` (reprocessável). O catálogo é casado sobre todas as seções e empurrado num push final.

`POST /fontes/{id}/reprocessar` (endpoint + botão "Reprocessar" na aba Fila) volta uma fonte com `status_proc=erro` para `pendente`, para o bot tentar de novo.

**Catálogo de trilhas (Passo 1)** (`api/data/catalogo_trilhas.json`, `GET /catalogo`, `bot/kdd_bot/catalogo.py`): termos técnicos e paths de sistema **conhecidos por trilha** (versionados/curáveis em PR) que valem como conceito por si só. Ao processar uma fonte, o bot casa esses termos no texto (path = substring case-sensitive; termo = palavra inteira case-insensitive) e **auto-adiciona** os encontrados como conceitos do mapa — mesmo que a IA não os tenha citado — com sentido ESTÁVEL (`Caminho/arquivo de sistema conhecido: …` / `Termo técnico do catálogo de trilhas: …`; a trilha NÃO entra na identidade). Buscado 1×/execução (cache no `Pipeline`); indisponível → WARNING e segue. A fonte segue a aprovação humana normal. Termos NOVOS (fora do catálogo) viram sugestão na aba KDD do cursohacker (Passo 2, no site). Detalhe em `docs/catalogo-trilhas.md`; teste `bot/exemplos/teste_catalogo.py`. **DEPLOYADO
2026-07-03:** API na Hostinger (`index.php`+`consulta.php`+`data/catalogo_trilhas.json` — o
`data/` não existia em prod, foi criado; `GET /catalogo` verificado 200 c/ token, 401 sem); bot
na .90 (`~/kdd_bot`, tar do `bot/`, `kdd_bot.service` reiniciado; usa o venv compartilhado
`/home/user/legendar/venv`, NÃO um `.venv` próprio) — confirmado alcançando `/catalogo` (137 termos).

**Ingestão de texto** (`POST /fontes/texto`, migration `005_fonte_texto.sql`): fonte não-PDF vinda de um site externo (ex.: cursohacker manda descrição + transcrição). `fonte.contexto` é a "lente"/área-raiz da fonte (ex.: nome do curso — criada já na ingestão; o bot adiciona as áreas achadas no texto por baixo). `fonte.ref` é a chave de idempotência do **remetente** (ex.: `aula:<id>`): reenviar o mesmo `ref` **atualiza** o texto e reprocessa, em vez de duplicar (índice único; múltiplos NULL para fontes PDF/curadoria).

**Dedup de PDF por hash** (migration `003_hash_fonte.sql`): `fonte.arquivo_hash` guarda o SHA-256 do arquivo, com índice único — reenviar o **mesmo conteúdo** é bloqueado. Fontes de curadoria não têm arquivo → `hash NULL` (o índice único permite múltiplos NULL).

## Onde está cada coisa

- **`api/index.php` é a tabela de rotas** (cadeia de `if`/`preg_match` por path+método) — a única lista completa dos endpoints; também expõe `GET /health` e `GET /ping`. `src/env.php` lê o `.env`; `db.php` dá o PDO; `auth.php` (`require_token`) resolve `{token, perfil}` em `tokens.json`; `http.php` tem `json_out`/`json_error`/`json_body`/`request_path`. Handlers: `fontes.php` (ingestão, status, aprovar/reprovar/reprocessar, push de mapas), `consulta.php` (leitura: árvore de áreas, conceitos, proposições, `GET /fontes/{id}/mapa`, constelação, catálogo), `editor.php` (escrita de curadoria).
- **Tabelas** (`001_schema.sql`): `area`, `conceito`, `rotulo`, `conceito_area`, `fonte`, `fonte_area`, `proposicao`, `referencia` (proposição×fonte — é o que a view conta), `conceito_fonte` (proveniência conceito×fonte), `changeset` (002) e a view `vw_certeza_proposicao`. Unicidades (004): `conceito.sentido`, `rotulo(conceito_id,texto)`, tripla da proposição. `migrate.php` remove linhas `--` e divide por `;` — nada de `;` dentro de strings nem `DELIMITER`; `ADD COLUMN/CREATE INDEX IF NOT EXISTS` é sintaxe MariaDB (a da Hostinger).
- **`bot/kdd_bot/`**: `config.py` (`Config.carregar`), `api_client.py` (`KddClient`), `pdf.py` (pypdf; também aceita `.txt`), `catalogo.py`, `pipeline.py` (`Pipeline`), `ia/` (fachada, backends, `schema.py`).
- **`desktop/kdd_desktop/`**: `app.py` (`MainWindow` com as 3 abas, `ConstelacaoDialog`, `ConceitoEditorDialog`, `FilaTab`), `mapa.py` (QGraphicsView do diagrama: `ConceitoNode`, `ProposicaoEdge`, `MapaView`, `MapaDialog`, `MapasTab`), `api_client.py`, `config.py`.
- **Docs**: `docs/README.md` é o **índice das especificações** — comece por ele, não pela `especificacao.md`, que é a fundação de junho/2026 e tem aviso no topo listando o que foi superado. `docs/decisoes-2026-10-09.md` registra as decisões, o que foi rejeitado e por quê, as assimetrias deliberadas e as armadilhas técnicas. `RODAR.md` é o guia de execução; `README.md`, `bot/README.md` e `desktop/README.md` foram reescritos em 2026-10-09 e estão corretos.

## Idioma e país (`docs/idioma-pais.md`)

Dois problemas de **natureza diferente**, e confundi-los é o erro mais provável aqui:

- **Idioma é SUPERFÍCIE** → vive em `rotulo.idioma` (tag BCP-47: `pt-BR`, `pt-PT`, `en`). Porta/Door/Puerta é **um** conceito com três rótulos. Unicidade do rótulo passou a `(conceito_id, idioma, texto)`, então o mesmo texto coexiste em idiomas diferentes. `?idioma=` escolhe com **fallback** (idioma pedido → mesma língua outra região → idioma-base do universo → principal): nunca devolve vazio por falta de tradução.
- **O SENTIDO tem uma língua só**, declarada em `universo.idioma`. O sentido é a string de **identidade**: traduzi-lo bifurcaria o conceito. Assimetria deliberada.
- **País pode mudar o SENTIDO** → entra na identidade: `conceito.pais` e `proposicao.pais`. "Imposto de Renda" (BR) e o equivalente português **não são tradução**, são institutos distintos. Identidade final: `(universo_id, pais, sentido)`.
- ⚠️ **Sentinela `''`, nunca NULL.** Com `pais` NULL o `UNIQUE(universo_id, pais, sentido)` **não morderia** — MySQL/MariaDB tratam NULLs como distintos, e daria para inserir duas vezes o mesmo trio, fragmentando a identidade. É a invariante que a migration 004 veio garantir.
- ⚠️ **O filtro de país é INCLUSIVO**, ao contrário do universo: `pais IN ('', <escolhido>)`. Um leitor no Brasil vê os universais **e** os brasileiros, nunca os de Portugal. País marca jurisdição **dentro** do plano; universo **é** o plano (igualdade estrita).
- `fonte.idioma`/`fonte.pais` são o **padrão herdado** pelo que o bot extrair dela: um PDF da legislação brasileira ingerido com `pais=BR` faz os conceitos nascerem BR, sem a IA acertar item a item. A IA pode sobrepor por item.
- **Merge entre países é proibido** (409), mesma razão do merge entre universos.
- ⚠️ `kdd_sql_rotulo()` (em `api/src/idioma.php`) **interpola** a tag de idioma no `ORDER BY` em vez de parametrizar, de propósito: ela aparece em ~16 queries com listas de parâmetros diferentes. É seguro porque `kdd_idioma_valido()` só deixa passar `[a-z]{2,3}(-[A-Za-z0-9]{2,8})?` — sem quote, espaço ou metacaractere possível.
- ⚠️ Em PHP, `$x = cond ? a : b` dentro de concatenação cai na **precedência do ternário** e a variável sai indefinida. Já quebrou o `/esteios` aqui: calcule o filtro numa linha separada.

## Sentimento da proposição (`docs/sentimento.md`)

Responde a duas perguntas que a base não respondia: "o que **ameaça** este conceito × o que o **protege**?" e "isso é **fato** ou **juízo de valor**?". Dois eixos independentes: `polaridade` (−1..+1) e `subjetividade` (0..1).

- ⚠️ **Medido em INGLÊS, nunca em português** (decisão do idealizador): pt-BR tem base pobre e erra muito. A relação é traduzida (`proposicao.relacao_en`, que a IA emite na mesma chamada da extração) e a medição roda sobre a forma inglesa.
- ⚠️ **Roda no BOT, não na API** (`bot/kdd_bot/sentimento.py`): a análise é Python e a Hostinger não tem Python. A API **não pontua** — valida, guarda e agrega. Um motor de pontuação só; um léxico em PHP divergiria do Python no primeiro ajuste. Mesma divisão da camada vetorial.
- **Pacotes**: `vaderSentiment` (polaridade — o padrão para inglês) e `TextBlob` (subjetividade; `.sentiment` **não** precisa de corpora do NLTK, então não há passo extra no deploy).
- ⚠️ **Por que há ajuste de domínio**: medido no armazém, o VADER puro acerta 7/13 porque pontua o **vocabulário** e não a **relação** (`firewall blocks traffic` = −0,23; `patch fixes vulnerability` = −0,23, arrastado pelo substantivo). TextBlob faz 3/13 em polaridade mas **13/13** em subjetividade. Composição final (13/13): polaridade do **verbo** manda, **agente malicioso inverte** o verbo (`ransomware encrypts files` ≠ `backup encrypts files`), VADER cobre o verbo desconhecido, TextBlob dá a subjetividade. `autoteste()` no módulo verifica isso.
- **Mora na REFERÊNCIA, não na proposição** (`referencia.polaridade`/`subjetividade`): duas fontes podem afirmar a mesma tripla com cargas diferentes. Fica no mesmo lugar da certeza, então **reprovar uma fonte remove a contribuição dela** sem recálculo, e `discordancia` mostra quando as fontes divergem. Sentimento **não** entra na identidade.
- ⚠️ **Sem medição o resultado é `nao_medida`, nunca "neutro"** — fabricar neutro faria uma lacuna parecer resultado.
- ⚠️ **A subjetividade desconta o valor; a polaridade NÃO.** `valor × (1 − 0,20 × subjetividade)`. Juízo vale menos como conhecimento que fato; mas descontar o negativo injetaria **viés otimista**, e "malware compromete sistema" é conhecimento de primeira. Omissão não penaliza, então a base existente não muda de valor.
- `GET /conceitos/{id}` separa `ameacas` e `protecoes`; `GET /proposicoes?polaridade=` filtra.

## Universos paralelos (`docs/universos.md`)

Vários **domínios de conhecimento isolados** no mesmo armazém. O mesmo rótulo **e** o mesmo sentido podem existir em cada um, como conceitos diferentes, com relações, certezas e valores próprios.

- ⚠️ **Isto inverteu uma decisão firme do projeto.** A identidade do conceito passou de `sentido` para **`(universo_id, sentido)`**. O universo é exatamente o critério de identidade que a área tinha proibição de ser. Dentro de um universo nada mudou: identidade = sentido, e área segue N–N sem poder de identidade. Área **classifica**; universo **separa**.
- **Escopo**: `conceito`, `area` e `fonte` têm `universo_id`. `rotulo`, `conceito_area`, `fonte_area`, `referencia` e `conceito_fonte` herdam do pai. `proposicao` **não** tem a coluna: deriva dos conceitos e **nunca cruza universo** (409 na escrita, em criar e editar). Ligação entre universos não é proposição, é **contraparte**.
- **Universo 1 = `principal`**, criado pela migration, que retroalimenta todas as linhas existentes. Requisição sem `?universo=` cai nele, então o desktop e o bot antigos continuam funcionando sem mudança.
- ⚠️ **`kdd_grau_max()` é POR UNIVERSO.** Se fosse global, um universo pequeno teria o esteio esmagado pelo maior hub do maior universo e o valor das proposições dele despencaria sem razão de domínio. É o ponto mais fácil de errar aqui. Por isso `kdd_info_conceitos()` devolve `universo_id` junto: uma listagem pode cruzar universos (contrapartes) e cada conceito precisa do `grau_max` do **seu** universo.
- ⚠️ **`kdd_fonte_curadoria()` é POR UNIVERSO.** Com uma fonte só, a curadoria feita no universo B apoiaria proposições de B numa fonte de A, e a certeza atravessaria a fronteira.
- **Unicidades por universo** (migration 008): `conceito(universo_id, sentido)`, `fonte(universo_id, ref)`, `fonte(universo_id, arquivo_hash)`. Trocar foi seguro porque o que era único globalmente continua único dentro do universo 1. Ganho de domínio no hash: **o mesmo PDF pode ser ingerido em dois universos** (ler o mesmo documento por duas lentes); reenviar no mesmo universo continua barrado. `area(universo_id, nome)` é índice **comum, não único**, de propósito: `area.nome` nunca foi único, e um UNIQUE sobre dado possivelmente duplicado faria a migration **falhar no meio** em produção, porque `migrate.php` não tem transação por arquivo.
- ⚠️ A forma idempotente de criar FK no MariaDB é `ADD FOREIGN KEY IF NOT EXISTS <nome> (col)`. `ADD CONSTRAINT IF NOT EXISTS <nome> FOREIGN KEY ...` é **erro de sintaxe**.
- **Contrapartes** (`GET /conceitos/{id}/contrapartes`) é o que torna os universos *paralelos* e não só isolados: acha o gêmeo nos outros universos por **rótulo** idêntico e por **vetor**. `conceito_similar` é a única tabela que cruza universos de propósito — o mesmo cosseno serve a dois fins, só muda a leitura: mesmo universo = duplicata a fundir, universos diferentes = contraparte. Daí o `?escopo=interno|externo|todos` em `GET /similares` (padrão `interno`) e o `mesmo_universo` em cada par. **Fusão entre universos é proibida** (409).
- **O bot não mudou**: ele varre as fontes pendentes de **todos** os universos (`GET /fontes` sem `?universo=` é global de propósito) e o push herda o universo da fonte, nunca do corpo.
- No desktop o universo é injetado em `_get` do cliente, num só lugar: trocar o seletor redireciona toda a leitura sem tocar nas chamadas da UI.

## Servidor MCP (`mcp/`, `docs/mcp-servidor.md`)

```
cliente MCP (Claude) ──stdio──> mcp/ (Python) ──HTTP+token──> api/ (PHP) ──> MySQL
```

- **Regra de ouro: adaptador fino.** O servidor MCP **não** fala com o MySQL e **não** reimplementa domínio. A `api/` é a fonte da verdade (identidade por sentido, certeza, valor, changesets). Uma segunda implementação da fórmula do valor divergiria no primeiro ajuste de peso. **Se uma ferramenta MCP precisar de algo que a API não serve, o trabalho é na API** — depois o MCP só ganha a ferramenta que expõe.
- **11 ferramentas de leitura** (`listar_universos`, `listar_areas`, `buscar_conceitos`, `obter_conceito`, `obter_contrapartes`, `listar_proposicoes`, `listar_esteios`, `ver_constelacao`, `listar_semelhantes`, `obter_mapa_da_fonte`, `listar_fontes`), todas anotadas `read_only_hint`. As de listagem aceitam `universo` (o slug).
- **3 de escrita** (`ingerir_texto`, `criar_conceito`, `criar_proposicao`) só são **registradas** com `KDD_MCP_ESCRITA=1` **e** `KDD_TOKEN_VALIDADOR` presente — sem isso o modelo nem vê que existem. Nenhuma é destrutiva: remover/desabilitar/merge/split continuam só na curadoria humana do desktop.
- O servidor manda `instructions` no handshake explicando o domínio (identidade = sentido, valor 0–100, esteio), então o agente chega orientado.
- ⚠️ Em stdio o **stdout é o canal do protocolo**: todo log vai para stderr, senão corrompe o JSON-RPC.
- Transporte stdio; `streamable-http` fica fora desta versão (exigiria autenticação própria e o MCP deixaria de ser adaptador fino). Não vai para a Hostinger. `.mcp.json` na raiz registra o servidor no escopo do projeto. SDK: `mcp` 2.x, onde a classe é `MCPServer` (era `FastMCP` no 1.x) e os campos são **snake_case** (`server_info`, `read_only_hint`, `structured_content`).

## Editor / curadoria manual (`api/src/handlers/editor.php`)

Contraparte de curadoria do bot: humano corrige o armazém **sem** depender de novo PDF (criar/editar/remover proposições, conceitos, rótulos, áreas, **merge** e **split** de conceitos). Todos os endpoints de escrita exigem **perfil validador** (`kdd_exigir_validador`).

- Edições de curadoria são atribuídas a uma **fonte sintética** `origem='curadoria'` (`kdd_fonte_curadoria`), criada já `status_proc=processado` + `status_aprovacao=aprovada` — por isso contam na certeza imediatamente.
- Toda escrita grava um **changeset** append-only (`kdd_log_changeset`: autor, perfil, ação, alvo, antes/depois em JSON) — auditoria da curadoria.
- **Desabilitar conceito** (`POST /conceitos/{id}/desabilitar` `{desabilitado: 0|1}` obrigatório, migration `006_conceito_desabilitado.sql`): marca `conceito.desabilitado`; nada é apagado e reabilitar reverte. As consultas expõem `desabilitado` no conceito e `desabilitada` **por cálculo** (origem OU destino desabilitado) nas proposições — o cliente marca/filtra; a certeza na view **não** muda (decisão: marcar, não esconder).
- No desktop, o modo edição (`ConceitoEditorDialog`, criar conceito/área) só aparece com `KDD_TOKEN_VALIDADOR`; sem ele o cliente é só leitura.

## Autenticação

**Sem login.** Acesso por **token** (header `X-Token:` ou `Authorization: Bearer`), validado contra `api/tokens.json` (ver `tokens.example.json`). Os perfis `operador`/`validador` são **organizacionais, não controle técnico** — qualquer token válido pode chamar qualquer rota. O bot age como operador (`KDD_TOKEN_OPERADOR`).

## Configuração e segredos

Repositório é **PÚBLICO**. Segredos vivem em `~/.env` (na home, não no repo) — ver `.env.example`. Tanto Python (`Config.carregar()` em `bot/` e `desktop/`) quanto a API leem chaves `KDD_*` do ambiente ou de `~/.env`. `KDD_TOKEN` é aceito como fallback genérico (bot: `KDD_TOKEN_OPERADOR`→`KDD_TOKEN`; desktop: `KDD_TOKEN`→`_OPERADOR`→`_VALIDADOR`). **Nunca** comite `.env` ou `tokens.json` (protegidos pelo `.gitignore`). No servidor, esses arquivos ficam dentro de `public_html` mas são bloqueados pelo `.htaccess`.

## Comandos

### API (PHP)
```bash
cd api
php migrate.php          # roda migrations/*.sql em ordem (idempotente: IF NOT EXISTS / CREATE OR REPLACE)
php -S localhost:8000    # servidor local (index.php é o front controller)
curl -H 'X-Token: <token>' localhost:8000/health   # smoke test (401 sem token)
```
Em produção a Hostinger usa Apache + `.htaccess`; migrations rodam via phpMyAdmin ou `php migrate.php` por SSH.

### Bot (Python)
```bash
cd bot
.venv/bin/python main.py              # uma passada nas fontes pendentes
.venv/bin/python main.py --loop       # observa continuamente (--intervalo 120)
.venv/bin/python main.py --backend rolhama --max-fontes 1    # backend/limite explícitos
.venv/bin/python main.py --secoes 15000 --max-secoes 3       # modo seções (ver ⚠️ conflito com o REPLACE acima)
.venv/bin/python exemplos/teste_ponta_a_ponta.py   # teste e2e: upload PDF → roda bot → mostra mapa
```

### Servidor MCP (Python)
```bash
cd mcp
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m kdd_mcp          # stdio: espera o cliente (log no stderr)
```

### Desktop (Python/PySide6)
```bash
./install-gui.sh         # instala SÓ o cliente GUI (Debian: libs de sistema + venv em desktop/.venv)
./run.sh                 # abre o cliente GUI
cd desktop && .venv/bin/python main.py                # equivalente direto
QT_QPA_PLATFORM=offscreen .venv/bin/python main.py    # headless (sem display)
```

Os venvs já existem em `bot/.venv`, `desktop/.venv` e `mcp/.venv` (gitignorados). Para recriar: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

### Deploy
- **API → Hostinger**: seguir `DEPLOY.md`. Regra **obrigatória**: só implantar no diretório que contém o arquivo-marcador (`96095eb4-….txt`) — sem marcador, **abortar**; nunca alterar/mover o marcador nem sobrescrever `.env`, `tokens.json` ou `storage/` do servidor. SSH por senha (`SSH_HOSTINGER_*` em `~/.env`).
- **Bot → .90** (a máquina do ollama): seguir `deploy/BOT-90.md` — tar+ssh do `bot/`, unit systemd `deploy/kdd_bot.service`, backend `rolhama`. Bot e desktop **não** vão pra Hostinger.

**Não há framework de testes** (pytest etc.). A verificação é por scripts que batem na API real:
- `bot/exemplos/` — scripts contra a **API de produção** (`teste_ponta_a_ponta.py`, `teste_catalogo.py`), usam `~/.env`.
- `teste/` — E2E num ambiente **local descartável**: cada script monta MySQL local + cópia da `api/` em scratch com `.env`/`tokens.json` apontando pro local (NUNCA toca em prod), roda migrations, sobe `php -S`, executa e derruba tudo.
  - `bash teste/e2e_catalogo.sh` — Passo 1, catálogo de trilhas (banco `kdd_local`, porta 8077). Ver `teste/E2E.md` e `teste/COMO_EXECUTAR.md`.
  - `bash teste/e2e_valor.sh` — camada de valor/esteios/vetores (banco `kdd_valor`, porta 8078, token de validador). Roda as migrations **2×** para provar idempotência e usa o Ollama local de verdade na parte vetorial (pula essa etapa se não houver Ollama). `LIMPAR=1` apaga o scratch e o banco ao final.
  - `bash teste/e2e_mcp.sh` — servidor MCP (banco `kdd_mcp_t`, porta 8080). Sobe o servidor como subprocesso e fala o protocolo **de verdade** com um cliente MCP (handshake, `tools/list`, `tools/call`). Exige o venv de `mcp/`.
  - `bash teste/e2e_universos.sh` — universos paralelos (banco `kdd_univ`, porta 8081). Prova o isolamento, o `grau_max` por universo, os 409 de proposição/merge entre universos e as contrapartes.
  - `bash teste/e2e_idioma_pais.sh` — idioma e país (banco `kdd_ip`, porta 8082). Prova o fallback de rótulo, a identidade por país, o filtro inclusivo e a herança do padrão da fonte.
  - `bash teste/e2e_sentimento.sh` — sentimento (banco `kdd_sent`, porta 8083). Roda o autoteste do motor, prova o não-medido, a discordância entre fontes, o efeito do veto e o desconto por subjetividade. Exige `vaderSentiment` e `textblob` no venv do bot.

## Fachada de IA (`bot/kdd_bot/ia/`)

`IAFacade.a_partir_de(config)` escolhe o backend por `KDD_IA_BACKEND`:
- `ollama` — `OllamaBackend`, local, HTTP direto com `format=json`. Modelo padrão `qwen2.5:7b-instruct` (~4.7 GB), dimensionado para a máquina-alvo (i5-6200U, ~11 GB RAM, sem GPU). Lento em CPU (~4–6 min/extração).
- `rolhama` — `RolhamaBackend`: **o backend do bot em produção (na .90)**. Não bate direto no ollama (colidiria com os outros consumidores do slot único): **enfileira** o pedido num canal do **webapi** (`enqueue` → UUID do job) e o worker **rolhama** (thread única) executa um por vez; a resposta é lida pelo job (`webapi.py` = transporte + MAC de autenticação; `bdd.py` = cifra ChaCha20-Poly1305 do payload, ponta a ponta). **Migrado do bddphp antigo** (que fazia canal um-por-um com 409/`remove()`) para a fila por job do webapi — ver `../rolhama/LEGADO.md`. Config: `ROLHAMA_WEBAPI_URL` (default `https://wellington.tec.br/rolhama`; `ROLHAMA_BDD_URL` ainda aceito como fallback), `ROLHAMA_BDD_KEY` (obrigatória, inalterada), `ROLHAMA_CHANNEL` (505 = canal reservado ao KDD) e `ROLHAMA_OLLAMA_MODEL` (em prod: `qwen2.5:14b-instruct`).
- `auto` (padrão) — resolve **sempre** para `ollama` (local, sem custo).
- `claude` — `ClaudeBackend`, nuvem, *tool use* forçado, padrão `claude-sonnet-4-6`. **DESATIVADO temporariamente** (ver abaixo).
- `cli` — `CliBackend`, usa o CLI `claude` em modo `-p --json-schema` sem `ANTHROPIC_API_KEY` própria. **Consome crédito do Claude Code. DESATIVADO temporariamente** (ver abaixo).

⚠️ **TEMPORÁRIO: Claude desativado.** Os backends `claude` e `cli` estão bloqueados — `--backend` só aceita `{auto, ollama, rolhama}` (`main.py`) e a fachada levanta `RuntimeError` se `KDD_IA_BACKEND` vier como `claude`/`cli` (`facade.py`). Para reativar, restaure os ramos e as escolhas marcados com o comentário `TEMPORÁRIO` nesses dois arquivos.

**Proteção de crédito** (em `main.py`, inerte enquanto o Claude está desativado, mas mantida para a reativação): backends pagos (`cli`/`claude`) logam um WARNING e, sem `--max-fontes`, limitam a **1 fonte por execução**. Flags: `--backend {auto,ollama,rolhama}` sobrepõe `KDD_IA_BACKEND`; `--max-fontes N` limita por execução (`0` = sem limite).

Todos os backends partilham `schema.py` (`MAPA_SCHEMA`, `SYSTEM`, `instrucao_usuario`) e a saída passa por `normalizar()`. **Ao adicionar/alterar um backend, o output tem que casar com `MAPA_SCHEMA`** (`{areas, conceitos[rotulo,sentido,areas], proposicoes[origem_rotulo,relacao,destino_rotulo,destino_sentido?]}`), que por sua vez espelha o payload da API.

## Decisões técnicas firmes

- Desktop = Python/PySide6 · API = **PHP puro + PDO** (sem framework) · Banco = **MySQL** (InnoDB/utf8mb4) · Bot = Python.
- API headless (só JSON, sem telas — a única UI é o PySide).
- PDF = arquivo+caminho em `api/storage/pdfs/` (não BLOB).
- Migrations = scripts `.sql` versionados em `api/migrations/`.
- Normalização da certeza para [0,1] está **adiada**; hoje expõe-se contagem linear (`fontes_aprovadas`).
