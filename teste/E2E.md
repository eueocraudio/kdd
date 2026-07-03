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
