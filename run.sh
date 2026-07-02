#!/usr/bin/env bash
#
# run.sh — abre SÓ o cliente GUI (desktop PySide6) do KDD.
# Requer que ./install-gui.sh já tenha rodado (venv em desktop/.venv).
#
# Uso:  ./run.sh
#
set -euo pipefail
cd "$(dirname "$0")"

PY="desktop/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "venv não encontrado ($PY)." >&2
  echo "Rode primeiro:  ./install-gui.sh" >&2
  exit 1
fi

# desktop/ vira sys.path[0] ao rodar main.py, então 'import kdd_desktop' funciona.
exec "$PY" desktop/main.py "$@"
