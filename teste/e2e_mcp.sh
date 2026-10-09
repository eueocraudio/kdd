#!/usr/bin/env bash
# =============================================================================
# e2e_mcp.sh — E2E LOCAL do SERVIDOR MCP (docs/mcp-servidor.md §7).
#
# Mesma receita dos outros e2e: banco e API LOCAIS descartáveis, NUNCA produção.
# Popula o armazém local, depois sobe o servidor MCP como subprocesso e fala o
# protocolo de verdade (initialize / tools/list / tools/call) com um cliente MCP.
#
# Verifica: handshake; as 9 ferramentas de leitura anotadas read-only; escrita
# ausente sem KDD_MCP_ESCRITA=1 e presente com ela; valor/esteio chegando ao
# agente; erro de API virando texto legível; e idempotência de ingerir_texto.
#
# Requer o venv do MCP: python -m venv mcp/.venv && mcp/.venv/bin/pip install -r mcp/requirements.txt
#
# USO:  bash teste/e2e_mcp.sh            # monta, roda e deixa o scratch
#       LIMPAR=1 bash teste/e2e_mcp.sh   # idem + apaga scratch/DB ao final
# =============================================================================
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$AQUI/.." && pwd)"
API_SRC="$RAIZ/api"
BOT_DIR="$RAIZ/bot"
PY="$RAIZ/mcp/.venv/bin/python"

PORTA="${PORTA:-8080}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-kdd_mcp_t}"
DB_USER="${DB_USER:-kddlocal}"
DB_PASS="${DB_PASS:-kddlocal123}"
TOKEN="${TOKEN:-mcp_local_teste_123456}"
SCRATCH="${SCRATCH:-${TMPDIR:-/tmp}/kdd_e2e_mcp}"
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

echo ">> populando o armazém local (fonte + mapa com tipos)"
API="http://127.0.0.1:$PORTA"
curl -fsS -X POST "$API/fontes/texto" -H "X-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"titulo":"Fonte MCP","texto":"A Anthropic desenvolveu o Claude.","contexto":"Inteligência Artificial","ref":"seed:mcp"}' >/dev/null
curl -fsS -X POST "$API/fontes/1/mapas" -H "X-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"conceitos":[
        {"rotulo":"Anthropic","sentido":"Empresa de pesquisa em IA","tipo":"entidade","areas":["Inteligência Artificial"]},
        {"rotulo":"Claude","sentido":"Modelo de linguagem da Anthropic","tipo":"entidade","areas":["Inteligência Artificial"]},
        {"rotulo":"Modelo de linguagem","sentido":"Categoria de sistema de IA que gera texto","tipo":"classe","areas":["Inteligência Artificial","Linguística"]}],
      "proposicoes":[
        {"origem_rotulo":"Anthropic","relacao":"desenvolveu","destino_rotulo":"Claude"},
        {"origem_rotulo":"Claude","relacao":"pertence a","destino_rotulo":"Modelo de linguagem"},
        {"origem_rotulo":"Anthropic","relacao":"relaciona-se com","destino_rotulo":"Modelo de linguagem"}]}' >/dev/null
echo "   armazém populado"

echo ">> rodando o teste"
set +e
KDD_APP_URL="http://127.0.0.1:$PORTA" \
KDD_TOKEN_OPERADOR="$TOKEN" KDD_TOKEN_VALIDADOR="$TOKEN" \
  "$PY" "$AQUI/teste_mcp.py"
RC=$?
set -e

echo
if [ "$RC" = "0" ]; then
  echo "== E2E MCP OK =="
else
  echo "== E2E MCP FALHOU (rc=$RC) — log: $SCRATCH/server.log =="
  tail -20 "$SCRATCH/server.log"
fi
exit "$RC"
