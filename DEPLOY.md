# DEPLOY — KDD

Só a **API** (`api/`) é implantada em produção (Hostinger). O `bot/` roda na máquina
de IA (Ollama) e o `desktop/` é cliente local — nenhum dos dois vai pra Hostinger.

## Regra do diretório-alvo (OBRIGATÓRIA)

O ponto de instalação em produção é **o diretório que contém o arquivo-marcador**:

```
96095eb4-24eb-4fec-a3c6-fceeab340e47.txt
```

- **Se o marcador não existe no diretório, NÃO faça deploy** (é o diretório errado).
- **NUNCA** altere, mova ou remova esse arquivo. Ele não é do KDD — é o selo que
  identifica o alvo. O deploy só envia os arquivos da API, jamais o marcador.

Diretório atual (migrado em 2026-07-04 — saindo do subdomínio auto-gerado da Hostinger,
indo pro domínio próprio; ver `~/desenv/rolhama/CORRECAO.md` pelo mesmo tipo de migração
feita antes pro bddphp):

```
/home/u944249633/domains/wellington.tec.br/public_html/kdd/
```

Isso bate com `KDD_APP_URL=https://wellington.tec.br/kdd` (em `~/.env`). Como a API passou a
rodar sob **subdiretório** (antes vivia na raiz do domínio `paleturquoise-dunlin-206466.
hostingersite.com/`), `request_path()` (`api/src/http.php`) precisou descontar o prefixo do
`SCRIPT_NAME` antes de comparar rotas — sem isso toda rota cai em 404 (mesmo bug do bddphp).

O marcador (`96095eb4-…txt`) e o conteúdo antigo **ainda existem** em
`/home/u944249633/domains/paleturquoise-dunlin-206466.hostingersite.com/public_html/`
(não apagados ainda — pendente de decisão de quando desligar de vez esse domínio).

## Acesso SSH (Hostinger)

Credenciais em `~/.env` (chaves `SSH_HOSTINGER_*`); a senha NUNCA vai no repo.

```
Host  212.1.209.207   Port 65002   User u944249633
```

A chave `~/.ssh/cursohacker_ed25519` **não** está autorizada nesta conta; hoje o
acesso é por **senha** (`SSH_HOSTINGER_PASSWORD`). Com `sshpass`:

```bash
export SSHPASS="$(grep -E '^SSH_HOSTINGER_PASSWORD=' ~/.env | cut -d= -f2-)"
SSH='sshpass -e ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -p 65002 u944249633@212.1.209.207'
```

## Procedimento

1. **Confirmar o alvo** (aborta se o marcador não existir):
   ```bash
   DIR=~/domains/wellington.tec.br/public_html/kdd
   $SSH "test -f $DIR/96095eb4-24eb-4fec-a3c6-fceeab340e47.txt && echo ALVO_OK || echo ABORTA"
   ```
2. **Enviar os arquivos da API** — apenas o código; **nunca** `.env`, `tokens.json`,
   `storage/` nem o marcador. O servidor tem `rsync`; local pode não ter (usar `scp`):
   ```bash
   # via scp (arquivos alterados), preservando config e storage do servidor
   sshpass -e scp -P 65002 -o PreferredAuthentications=password -o PubkeyAuthentication=no \
     api/index.php  api/src/http.php  api/src/handlers/fontes.php  api/src/handlers/editor.php \
     u944249633@212.1.209.207:"$DIR/…"   # respeitar a subárvore src/handlers
   sshpass -e scp -P 65002 … api/migrations/004_unicidade.sql u944249633@212.1.209.207:"$DIR/migrations/"
   ```
3. **Migrations** — antes de aplicar a 004, checar duplicatas (ela cria índices
   `UNIQUE`; falha se houver duplicata). Depois:
   ```bash
   $SSH "cd $DIR && php migrate.php"
   ```

## O que preservar no servidor (nunca sobrescrever)

- `96095eb4-24eb-4fec-a3c6-fceeab340e47.txt` (marcador — imutável)
- `.env`, `tokens.json` (segredos de produção)
- `storage/pdfs/` (PDFs enviados)
