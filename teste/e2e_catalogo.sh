#!/usr/bin/env bash
# =============================================================================
# e2e_catalogo.sh — monta um ambiente KDD LOCAL do zero e roda o teste E2E do
# catálogo de trilhas (Passo 1). Documentado em teste/E2E.md.
#
# O QUE FAZ (idempotente):
#   1. instala deps que faltem (mariadb-server, php-cli/php-mysql/php-mbstring,
#      python3 + requests) — via apt/pip; pula o que já existe;
#   2. cria um banco MySQL LOCAL descartável (kdd_local) + usuário;
#   3. monta uma CÓPIA da api/ num diretório de scratch com .env/tokens.json
#      APONTANDO PARA O LOCAL — NUNCA toca no api/.env / api/tokens.json de PROD;
#   4. roda as migrations nessa cópia e copia o catálogo (api/data);
#   5. sobe a API local (php -S), roda bot/exemplos/teste_catalogo.py contra ela
#      (matcher offline + e2e sem LLM) e DERRUBA a API ao fim.
#
# SEGURANÇA: só mexe em banco/porta/dir LOCAIS. Não lê o ~/.env de produção; o
# teste recebe KDD_APP_URL/KDD_TOKEN_OPERADOR apontando para a instância local.
#
# USO:
#   bash teste/e2e_catalogo.sh            # monta tudo e roda
#   LIMPAR=1 bash teste/e2e_catalogo.sh   # idem + apaga o scratch/DB ao final
#
# Variáveis (têm padrão; exporte p/ sobrepor):
#   PORTA=8077  DB_NAME=kdd_local  DB_USER=kddlocal  DB_PASS=kddlocal123
#   SCRATCH=<tmp>/kdd_e2e   TOKEN=op_local_teste_123456
# =============================================================================
set -euo pipefail

# ---- diretórios do repo (o script vive em kdd/teste/) ----
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$AQUI/.." && pwd)"          # raiz do repo kdd
API_SRC="$RAIZ/api"
BOT_DIR="$RAIZ/bot"

# ---- parâmetros (LOCAIS, descartáveis) ----
PORTA="${PORTA:-8077}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-kdd_local}"
DB_USER="${DB_USER:-kddlocal}"
DB_PASS="${DB_PASS:-kddlocal123}"
TOKEN="${TOKEN:-op_local_teste_123456}"
SCRATCH="${SCRATCH:-${TMPDIR:-/tmp}/kdd_e2e}"
LIMPAR="${LIMPAR:-0}"

SRV_PID=""
limpar_saida() {
  [ -n "$SRV_PID" ] && kill "$SRV_PID" 2>/dev/null || true
  if [ "$LIMPAR" = "1" ]; then
    echo ">> LIMPAR=1: removendo scratch e banco local"
    rm -rf "$SCRATCH"
    sudo mariadb -e "DROP DATABASE IF EXISTS \`$DB_NAME\`;" 2>/dev/null || true
  fi
}
trap limpar_saida EXIT

echo "== KDD E2E do catálogo (Passo 1) =="
echo "   repo:    $RAIZ"
echo "   api:     http://127.0.0.1:$PORTA   db: $DB_NAME@$DB_HOST"
echo "   scratch: $SCRATCH"
echo

# -----------------------------------------------------------------------------
# 1) Dependências (instala só o que falta)
# -----------------------------------------------------------------------------
precisa_apt=()
command -v php >/dev/null       || precisa_apt+=(php-cli php-mysql)
php -m 2>/dev/null | grep -qi mbstring || precisa_apt+=(php-mbstring)
php -m 2>/dev/null | grep -qi pdo_mysql || precisa_apt+=(php-mysql)
command -v mariadbd >/dev/null || command -v mysqld >/dev/null || precisa_apt+=(mariadb-server mariadb-client)
command -v python3 >/dev/null   || precisa_apt+=(python3 python3-pip)
if [ "${#precisa_apt[@]}" -gt 0 ]; then
  echo ">> instalando deps: ${precisa_apt[*]}"
  sudo apt-get update -qq && sudo apt-get install -y "${precisa_apt[@]}"
fi

# Python: usa o venv do bot se existir; senão o python3 do sistema. requests é obrigatório.
PY="$BOT_DIR/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
if ! "$PY" -c "import requests" 2>/dev/null; then
  echo ">> instalando 'requests' para $PY"
  "$PY" -m pip install --user -q requests
fi

# -----------------------------------------------------------------------------
# 2) Banco local descartável
# -----------------------------------------------------------------------------
echo ">> subindo o MariaDB (se não estiver ativo) e criando $DB_NAME"
sudo systemctl start mariadb 2>/dev/null || sudo service mariadb start 2>/dev/null || true
sudo mariadb -e "
  CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER IF NOT EXISTS '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$DB_PASS';
  CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';
  GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'127.0.0.1';
  GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
  FLUSH PRIVILEGES;"

# -----------------------------------------------------------------------------
# 3) Cópia da API em scratch com .env/tokens LOCAIS (nunca toca os de PROD)
# -----------------------------------------------------------------------------
echo ">> montando cópia local da api/ em $SCRATCH"
rm -rf "$SCRATCH"
mkdir -p "$SCRATCH/storage/pdfs"
# copia o código da api, EXCLUINDO segredos de produção e storage real
cp -r "$API_SRC/." "$SCRATCH/"
rm -f "$SCRATCH/.env" "$SCRATCH/tokens.json"
rm -rf "$SCRATCH/storage/pdfs/"*  2>/dev/null || true
# garante o catálogo atualizado do repo
mkdir -p "$SCRATCH/data"
cp "$API_SRC/data/catalogo_trilhas.json" "$SCRATCH/data/"

cat > "$SCRATCH/.env" <<EOF
APP_ENV=local
APP_URL=http://127.0.0.1:$PORTA
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASS=$DB_PASS
DB_CHARSET=utf8mb4
PDF_STORAGE_PATH=$SCRATCH/storage/pdfs
TOKENS_FILE=$SCRATCH/tokens.json
EOF

cat > "$SCRATCH/tokens.json" <<EOF
{ "tokens": [ { "token": "$TOKEN", "descricao": "operador local (e2e)", "perfil": "operador" } ] }
EOF

# -----------------------------------------------------------------------------
# 4) Migrations na cópia local
# -----------------------------------------------------------------------------
echo ">> rodando migrations no banco local"
( cd "$SCRATCH" && php migrate.php )

# -----------------------------------------------------------------------------
# 5) Sobe a API, roda o teste, derruba a API
# -----------------------------------------------------------------------------
echo ">> subindo a API local em 127.0.0.1:$PORTA"
php -S "127.0.0.1:$PORTA" -t "$SCRATCH" > "$SCRATCH/server.log" 2>&1 &
SRV_PID=$!

# espera a API responder (até ~10s)
pronto=0
for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$PORTA/health" >/dev/null 2>&1; then pronto=1; break; fi
  sleep 0.5
done
if [ "$pronto" != "1" ]; then
  echo "ERRO: a API local não respondeu. Log:"; tail -20 "$SCRATCH/server.log"; exit 1
fi
echo "   API no ar (pid $SRV_PID)"

echo ">> rodando o teste do catálogo (matcher offline + e2e sem LLM)"
set +e
KDD_APP_URL="http://127.0.0.1:$PORTA" KDD_TOKEN_OPERADOR="$TOKEN" \
  "$PY" "$BOT_DIR/exemplos/teste_catalogo.py"
RC=$?
set -e

echo
if [ "$RC" = "0" ]; then echo "== E2E OK =="; else echo "== E2E FALHOU (rc=$RC) — server.log em $SCRATCH/server.log =="; fi
exit "$RC"
