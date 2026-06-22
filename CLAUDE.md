# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Língua

O usuário conversa em **português**. Código, comentários, mensagens de log e documentação deste repositório são em português — mantenha esse padrão.

## O que é o KDD

KDD (Knowledge Discovery in Databases) extrai conhecimento de PDFs e o representa como **Mapas Conceituais** (Novak) numa base navegável por humanos e máquinas, com curadoria humana. **Não** é sistema de ensino.

Três soluções sobre um núcleo comum (o "armazém"):

1. **`api/`** — Web API PHP + MySQL: a fonte da verdade. Versiona, gerencia aprovação, serve consulta. Headless (só JSON). **Em produção na Hostinger.**
2. **`desktop/`** — cliente PySide6 **somente leitura** (Marco 2): humanos navegam áreas/conceitos/constelação.
3. **`bot/`** — bot Python (Marco 3): lê PDFs pendentes, extrai mapas com IA e empurra propostas para aprovação humana.

`docs/especificacao.md` e `docs/plano-implementacao.md` têm a especificação completa e os marcos. **Modo de trabalho: especificar antes de codar.**

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
Em produção a Hostinger usa Apache + `.htaccess`; migrations rodam via phpMyAdmin ou `php migrate.php` por SSH. Deploy é via rsync+ssh (credenciais em `~/.env`).

### Bot (Python)
```bash
cd bot
.venv/bin/python main.py              # uma passada nas fontes pendentes
.venv/bin/python main.py --loop       # observa continuamente (--intervalo 120)
.venv/bin/python exemplos/teste_ponta_a_ponta.py   # teste e2e: upload PDF → roda bot → mostra mapa
```

### Desktop (Python/PySide6)
```bash
cd desktop
.venv/bin/python main.py
QT_QPA_PLATFORM=offscreen .venv/bin/python main.py   # headless (sem display)
```

Os venvs já existem em `bot/.venv` e `desktop/.venv` (gitignorados). Para recriar: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Não há framework de testes** (pytest etc.). A verificação é por scripts em `bot/exemplos/` que batem na API real.

## Fachada de IA (`bot/kdd_bot/ia/`)

`IAFacade.a_partir_de(config)` escolhe o backend por `KDD_IA_BACKEND`:
- `ollama` — `OllamaBackend`, local, HTTP com `format=json`. Modelo padrão `qwen2.5:7b-instruct` (~4.7 GB), dimensionado para a máquina-alvo (i5-6200U, ~11 GB RAM, sem GPU). Lento em CPU (~4–6 min/extração). Ver [[maquina-ollama-local]].
- `auto` (padrão) — resolve **sempre** para `ollama` (local, sem custo).
- `claude` — `ClaudeBackend`, nuvem, *tool use* forçado, padrão `claude-sonnet-4-6`. **DESATIVADO temporariamente** (ver abaixo).
- `cli` — `CliBackend`, usa o CLI `claude` em modo `-p --json-schema` sem `ANTHROPIC_API_KEY` própria. **Consome crédito do Claude Code. DESATIVADO temporariamente** (ver abaixo).

⚠️ **TEMPORÁRIO: Claude desativado.** Os backends `claude` e `cli` estão bloqueados — `--backend` só aceita `{auto, ollama}` (`main.py`) e a fachada levanta `RuntimeError` se `KDD_IA_BACKEND` vier como `claude`/`cli` (`facade.py`). Para reativar, restaure os ramos e as escolhas marcados com o comentário `TEMPORÁRIO` nesses dois arquivos.

**Proteção de crédito** (em `main.py`, inerte enquanto o Claude está desativado, mas mantida para a reativação): backends pagos (`cli`/`claude`) logam um WARNING e, sem `--max-fontes`, limitam a **1 fonte por execução**. Flags: `--backend {auto,ollama}` sobrepõe `KDD_IA_BACKEND`; `--max-fontes N` limita por execução (`0` = sem limite).

Todos os backends partilham `schema.py` (`MAPA_SCHEMA`, `SYSTEM`, `instrucao_usuario`) e a saída passa por `normalizar()`. **Ao adicionar/alterar um backend, o output tem que casar com `MAPA_SCHEMA`** (`{areas, conceitos[rotulo,sentido,areas], proposicoes[origem_rotulo,relacao,destino_rotulo,destino_sentido?]}`), que por sua vez espelha o payload da API.

## Decisões técnicas firmes

- Desktop = Python/PySide6 · API = **PHP puro + PDO** (sem framework) · Banco = **MySQL** (InnoDB/utf8mb4) · Bot = Python.
- API headless (só JSON, sem telas — a única UI é o PySide).
- PDF = arquivo+caminho em `api/storage/pdfs/` (não BLOB).
- Migrations = scripts `.sql` versionados em `api/migrations/`.
- Normalização da certeza para [0,1] está **adiada**; hoje expõe-se contagem linear (`fontes_aprovadas`).
