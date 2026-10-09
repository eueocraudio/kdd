#!/usr/bin/env bash
# =============================================================================
# e2e_valor.sh — E2E LOCAL da camada de VALOR / ESTEIOS / VETORES
# (docs/valor-conhecimento.md). Mesma receita do e2e_catalogo.sh: banco e API
# LOCAIS e descartáveis — NUNCA toca em produção.
#
# O QUE VERIFICA
#   1. migrations (incl. 007) rodam e são idempotentes (roda 2x);
#   2. push de mapa com `tipo` nos conceitos → fonte fica processado E APROVADA
#      (decisão IV: o que entrou está aprovado);
#   3. valor 0–100 em toda proposição; entidade+verbo+classe vale MAIS que
#      outro+"é um"+outro com a mesma certeza (decisão II);
#   4. GET /esteios ordena pelos conceitos de maior grau (decisão V);
#   5. camada vetorial: `main.py --vetorizar` embute os conceitos no Ollama e
#      grava os pares semelhantes; quase-duplicata aparece em GET /similares
#      (decisão VII). Esta etapa é PULADA se não houver Ollama com o modelo.
#
# USO:  bash teste/e2e_valor.sh            # monta, roda e deixa o scratch
#       LIMPAR=1 bash teste/e2e_valor.sh   # idem + apaga scratch/DB ao final
# =============================================================================
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$AQUI/.." && pwd)"
API_SRC="$RAIZ/api"
BOT_DIR="$RAIZ/bot"
PY="$BOT_DIR/.venv/bin/python"

PORTA="${PORTA:-8078}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-kdd_valor}"
DB_USER="${DB_USER:-kddlocal}"
DB_PASS="${DB_PASS:-kddlocal123}"
TOKEN="${TOKEN:-val_local_teste_123456}"
SCRATCH="${SCRATCH:-${TMPDIR:-/tmp}/kdd_e2e_valor}"
SRV_PID=""

limpar() {
  [ -n "$SRV_PID" ] && kill "$SRV_PID" 2>/dev/null || true
  if [ "${LIMPAR:-0}" = "1" ]; then
    sudo mariadb -e "DROP DATABASE IF EXISTS \`$DB_NAME\`;" 2>/dev/null || true
    rm -rf "$SCRATCH"
  fi
}
trap limpar EXIT

echo ">> banco local descartável: $DB_NAME"
sudo systemctl start mariadb 2>/dev/null || sudo service mariadb start 2>/dev/null || true
sudo mariadb -e "
  DROP DATABASE IF EXISTS \`$DB_NAME\`;
  CREATE DATABASE \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';
  CREATE USER IF NOT EXISTS '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$DB_PASS';
  GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
  GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'127.0.0.1';
  FLUSH PRIVILEGES;"

echo ">> cópia local da api/ em $SCRATCH"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH/storage/pdfs"
cp -r "$API_SRC/." "$SCRATCH/"
rm -f "$SCRATCH/.env" "$SCRATCH/tokens.json"
rm -rf "$SCRATCH/storage/pdfs/"* 2>/dev/null || true

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

# token de VALIDADOR: o teste também exercita escrita de curadoria (tipo do conceito)
cat > "$SCRATCH/tokens.json" <<EOF
{ "tokens": [ { "token": "$TOKEN", "descricao": "validador local (e2e valor)", "perfil": "validador" } ] }
EOF

echo ">> migrations (2x — checando idempotência)"
( cd "$SCRATCH" && php migrate.php >/dev/null && php migrate.php >/dev/null )
echo "   migrations OK nas duas passadas"

echo ">> subindo API local em 127.0.0.1:$PORTA"
php -S "127.0.0.1:$PORTA" -t "$SCRATCH" > "$SCRATCH/server.log" 2>&1 &
SRV_PID=$!
pronto=0
for _ in $(seq 1 20); do
  curl -fsS "http://127.0.0.1:$PORTA/health" >/dev/null 2>&1 && { pronto=1; break; }
  sleep 0.5
done
[ "$pronto" = "1" ] || { echo "ERRO: API local não respondeu:"; tail -20 "$SCRATCH/server.log"; exit 1; }
echo "   API no ar (pid $SRV_PID)"

echo ">> rodando o teste"
set +e
KDD_APP_URL="http://127.0.0.1:$PORTA" \
KDD_TOKEN_OPERADOR="$TOKEN" KDD_TOKEN_VALIDADOR="$TOKEN" \
  "$PY" "$AQUI/teste_valor.py"
RC=$?
set -e

echo
if [ "$RC" = "0" ]; then
  echo "== E2E VALOR OK =="
else
  echo "== E2E VALOR FALHOU (rc=$RC) — log: $SCRATCH/server.log =="
  tail -20 "$SCRATCH/server.log"
fi
exit "$RC"
