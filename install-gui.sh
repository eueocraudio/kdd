#!/usr/bin/env bash
#
# install-gui.sh — instala SÓ o cliente GUI (desktop PySide6) do KDD.
# Alvo: Debian. Cria um venv em desktop/.venv e instala as dependências
# (PySide6 + requests). Não toca em api/ nem bot/.
#
# Uso:  ./install-gui.sh
# Depois:  ./run.sh
#
set -euo pipefail
cd "$(dirname "$0")"

VENV="desktop/.venv"
REQ="desktop/requirements.txt"

echo "==> KDD — instalação do cliente GUI (desktop)"

# 1) Dependências de sistema (Debian) — apt-get install já é no-op para o que existe.
# Além do Python, as libs de runtime que o PySide6/Qt6 exige numa GUI no Debian
# (a wheel do PySide6 traz o Qt, mas depende destas libs do sistema).
pacotes=(python3 python3-venv python3-pip
         libgl1 libegl1 libxkbcommon0 libxcb-cursor0 libdbus-1-3 fontconfig)
echo "==> Instalando pacotes de sistema (requer sudo): ${pacotes[*]}"
sudo apt-get update
sudo apt-get install -y "${pacotes[@]}"

# 2) venv dedicado ao desktop.
if [ ! -x "$VENV/bin/python" ]; then
  echo "==> Criando venv em $VENV"
  python3 -m venv "$VENV"
else
  echo "==> venv já existe em $VENV (reutilizando)"
fi

echo "==> Instalando dependências Python ($REQ)"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$REQ"

# 3) Verificação.
echo "==> Verificando importações"
"$VENV/bin/python" - <<'PY'
import PySide6, requests
print(f"   PySide6 {PySide6.__version__} | requests {requests.__version__}")
PY

cat <<'MSG'

==> Pronto. Cliente GUI instalado.

    Antes de rodar, garanta no ~/.env:
      KDD_APP_URL=https://...            (URL da API em produção)
      KDD_TOKEN_OPERADOR=...             (token; ou KDD_TOKEN_VALIDADOR p/ modo edição)

    Para abrir a interface:
      ./run.sh
MSG
