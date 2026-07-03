# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Língua

O usuário conversa em **português**. Código, comentários, mensagens de log e documentação deste repositório são em português — mantenha esse padrão.

## O que é o KDD

KDD (Knowledge Discovery in Databases) extrai conhecimento de PDFs e o representa como **Mapas Conceituais** (Novak) numa base navegável por humanos e máquinas, com curadoria humana. **Não** é sistema de ensino.

Três soluções sobre um núcleo comum (o "armazém"):

1. **`api/`** — Web API PHP + MySQL: a fonte da verdade. Versiona, gerencia aprovação, serve consulta e recebe escrita de curadoria. Headless (só JSON). **Em produção na Hostinger.**
2. **`desktop/`** — cliente PySide6: navega áreas/conceitos/constelação/mapas (leitura) **e edita** (curadoria manual). Abas: "Áreas e Conceitos", "Mapas" (diagrama visual em `mapa.py`), "Fila" (status de processamento das fontes). O modo edição só aparece quando há `KDD_TOKEN_VALIDADOR` (ver Editor abaixo).
3. **`bot/`** — bot Python (Marco 3): lê PDFs pendentes, extrai mapas com IA e empurra propostas para aprovação humana.

`docs/especificacao.md` e `docs/plano-implementacao.md` têm a especificação completa e os marcos; `docs/editor-mapas.md` especifica o editor manual. **Modo de trabalho: especificar antes de codar.**

## Modelo de domínio (essencial para mexer no código)

- **Identidade do conceito é o SENTIDO, não o rótulo.** Rótulos iguais com sentidos diferentes são conceitos diferentes (homônimos: ex. "Botafogo" time × bairro). A tabela `conceito` guarda `sentido`; `rotulo` é N-por-conceito.
- **Área é dimensão N–N** (`conceito_area`), nunca critério de identidade. Áreas são hierárquicas via `area.parent_id`.
- **Proposição** = tripla `conceito_origem -[relacao]-> conceito_destino` (pode cruzar áreas).
- **"Constelação"** interliga áreas via homônimos e pontes interdisciplinares.
- **Certeza** = nº de fontes **aprovadas** que sustentam uma proposição (view `vw_certeza_proposicao`). Aprovação é **por fonte, tudo-ou-nada**: `status_aprovacao` vive em `fonte`. Reprovar derruba a certeza sem recálculo. ⚠️ O COUNT da view é sobre `f.id` (lado aprovado do LEFT JOIN), **não** `r.fonte_id` — senão referências de fontes pendentes/reprovadas continuariam contando.
- Fonte tem **dois status independentes**: `status_proc` (pendente→processando→processado/erro, controlado pelo bot) e `status_aprovacao` (pendente→aprovada/reprovada, controlado pelo validador humano).

## Fluxo de ingestão (como as peças se conectam)

```
humano faz upload PDF → POST /fontes (operador)
bot: GET /fontes?status_proc=pendente → PATCH processando → GET /fontes/{id}/arquivo
   → pypdf extrai texto → IAFacade.extrair_mapa() → PATCH areas → POST /fontes/{id}/mapas
validador humano: POST /fontes/{id}/aprovar | /reprovar  → só então a certeza sobe
```

`POST /fontes/{id}/mapas` é uma transação idempotente: resolve conceitos por **sentido exato** (helper `kdd_resolver_conceito` em `api/src/handlers/fontes.php`), faz upsert, e re-push **não duplica**. Limitação conhecida: dentro de um mesmo push, proposições referenciam conceitos por rótulo (colisão se dois sentidos do mesmo rótulo no mesmo PDF).

`POST /fontes/{id}/reprocessar` (endpoint + botão "Reprocessar" na aba Fila) volta uma fonte com `status_proc=erro` para `pendente`, para o bot tentar de novo.

**Catálogo de trilhas (Passo 1)** (`api/data/catalogo_trilhas.json`, `GET /catalogo`, `bot/kdd_bot/catalogo.py`): termos técnicos e paths de sistema **conhecidos por trilha** (versionados/curáveis em PR) que valem como conceito por si só. Ao processar uma fonte, o bot casa esses termos no texto (path = substring case-sensitive; termo = palavra inteira case-insensitive) e **auto-adiciona** os encontrados como conceitos do mapa — mesmo que a IA não os tenha citado — com sentido ESTÁVEL (`Caminho/arquivo de sistema conhecido: …` / `Termo técnico do catálogo de trilhas: …`; a trilha NÃO entra na identidade). Buscado 1×/execução (cache no `Pipeline`); indisponível → WARNING e segue. A fonte segue a aprovação humana normal. Termos NOVOS (fora do catálogo) viram sugestão na aba KDD do cursohacker (Passo 2, no site). Detalhe em `docs/catalogo-trilhas.md`; teste `bot/exemplos/teste_catalogo.py`. **DEPLOYADO
2026-07-03:** API na Hostinger (`index.php`+`consulta.php`+`data/catalogo_trilhas.json` — o
`data/` não existia em prod, foi criado; `GET /catalogo` verificado 200 c/ token, 401 sem); bot
na .90 (`~/kdd_bot`, tar do `bot/`, `kdd_bot.service` reiniciado; usa o venv compartilhado
`/home/user/legendar/venv`, NÃO um `.venv` próprio) — confirmado alcançando `/catalogo` (137 termos).

**Ingestão de texto** (`POST /fontes/texto`, migration `005_fonte_texto.sql`): fonte não-PDF vinda de um site externo (ex.: cursohacker manda descrição + transcrição). `fonte.contexto` é a "lente"/área-raiz da fonte (ex.: nome do curso — criada já na ingestão; o bot adiciona as áreas achadas no texto por baixo). `fonte.ref` é a chave de idempotência do **remetente** (ex.: `aula:<id>`): reenviar o mesmo `ref` **atualiza** o texto e reprocessa, em vez de duplicar (índice único; múltiplos NULL para fontes PDF/curadoria).

**Dedup de PDF por hash** (migration `003_hash_fonte.sql`): `fonte.arquivo_hash` guarda o SHA-256 do arquivo, com índice único — reenviar o **mesmo conteúdo** é bloqueado. Fontes de curadoria não têm arquivo → `hash NULL` (o índice único permite múltiplos NULL).

## Editor / curadoria manual (`api/src/handlers/editor.php`)

Contraparte de curadoria do bot: humano corrige o armazém **sem** depender de novo PDF (criar/editar/remover proposições, conceitos, rótulos, áreas, **merge** e **split** de conceitos). Todos os endpoints de escrita exigem **perfil validador** (`kdd_exigir_validador`).

- Edições de curadoria são atribuídas a uma **fonte sintética** `origem='curadoria'` (`kdd_fonte_curadoria`), criada já `status_proc=processado` + `status_aprovacao=aprovada` — por isso contam na certeza imediatamente.
- Toda escrita grava um **changeset** append-only (`kdd_log_changeset`: autor, perfil, ação, alvo, antes/depois em JSON) — auditoria da curadoria.
- **Desabilitar conceito** (`POST /conceitos/{id}/desabilitar` `{desabilitado: 0|1}` obrigatório, migration `006_conceito_desabilitado.sql`): marca `conceito.desabilitado`; nada é apagado e reabilitar reverte. As consultas expõem `desabilitado` no conceito e `desabilitada` **por cálculo** (origem OU destino desabilitado) nas proposições — o cliente marca/filtra; a certeza na view **não** muda (decisão: marcar, não esconder).
- No desktop, o modo edição (`ConceitoEditorDialog`, criar conceito/área) só aparece com `KDD_TOKEN_VALIDADOR`; sem ele o cliente é só leitura.

## Autenticação

**Sem login.** Acesso por **token** (header `X-Token:` ou `Authorization: Bearer`), validado contra `api/tokens.json` (ver `tokens.example.json`). Os perfis `operador`/`validador` são **organizacionais, não controle técnico** — qualquer token válido pode chamar qualquer rota. O bot age como operador (`KDD_TOKEN_OPERADOR`).

## Configuração e segredos

Repositório é **PÚBLICO**. Segredos vivem em `~/.env` (na home, não no repo) — ver `.env.example`. Tanto Python (`Config.carregar()` em `bot/` e `desktop/`) quanto a API leem chaves `KDD_*` do ambiente ou de `~/.env`. **Nunca** comite `.env` ou `tokens.json` (protegidos pelo `.gitignore`). No servidor, esses arquivos ficam dentro de `public_html` mas são bloqueados pelo `.htaccess`.

## Comandos

### API (PHP)
```bash
cd api
php migrate.php          # roda migrations/*.sql em ordem (idempotente: IF NOT EXISTS / CREATE OR REPLACE)
php -S localhost:8000    # servidor local (index.php é o front controller)
```
Em produção a Hostinger usa Apache + `.htaccess`; migrations rodam via phpMyAdmin ou `php migrate.php` por SSH.

### Bot (Python)
```bash
cd bot
.venv/bin/python main.py              # uma passada nas fontes pendentes
.venv/bin/python main.py --loop       # observa continuamente (--intervalo 120)
.venv/bin/python exemplos/teste_ponta_a_ponta.py   # teste e2e: upload PDF → roda bot → mostra mapa
```

### Desktop (Python/PySide6)
```bash
./install-gui.sh         # instala SÓ o cliente GUI (Debian: libs de sistema + venv em desktop/.venv)
./run.sh                 # abre o cliente GUI
cd desktop && .venv/bin/python main.py                # equivalente direto
QT_QPA_PLATFORM=offscreen .venv/bin/python main.py    # headless (sem display)
```

Os venvs já existem em `bot/.venv` e `desktop/.venv` (gitignorados). Para recriar: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

### Deploy
- **API → Hostinger**: seguir `DEPLOY.md`. Regra **obrigatória**: só implantar no diretório que contém o arquivo-marcador (`96095eb4-….txt`) — sem marcador, **abortar**; nunca alterar/mover o marcador nem sobrescrever `.env`, `tokens.json` ou `storage/` do servidor. SSH por senha (`SSH_HOSTINGER_*` em `~/.env`).
- **Bot → .90** (a máquina do ollama): seguir `deploy/BOT-90.md` — tar+ssh do `bot/`, unit systemd `deploy/kdd_bot.service`, backend `rolhama`. Bot e desktop **não** vão pra Hostinger.

**Não há framework de testes** (pytest etc.). A verificação é por scripts em `bot/exemplos/` que batem na API real.

## Fachada de IA (`bot/kdd_bot/ia/`)

`IAFacade.a_partir_de(config)` escolhe o backend por `KDD_IA_BACKEND`:
- `ollama` — `OllamaBackend`, local, HTTP direto com `format=json`. Modelo padrão `qwen2.5:7b-instruct` (~4.7 GB), dimensionado para a máquina-alvo (i5-6200U, ~11 GB RAM, sem GPU). Lento em CPU (~4–6 min/extração).
- `rolhama` — `RolhamaBackend`: **o backend do bot em produção (na .90)**. Não bate direto no ollama (colidiria com os outros consumidores do slot único): sela o pedido num canal do bddphp e o concentrador **rolhama** (thread única) executa um por vez e devolve a resposta (`bdd.py` é o cliente). Config: `ROLHAMA_BDD_URL`, `ROLHAMA_BDD_KEY` (obrigatória), `ROLHAMA_CHANNEL` (505 = canal reservado ao KDD) e `ROLHAMA_OLLAMA_MODEL` (em prod: `qwen2.5:14b-instruct`).
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
