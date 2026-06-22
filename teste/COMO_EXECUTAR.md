# Como executar os testes do bot (2 casos)

Sequência de comandos efetivamente usada para extrair o mapa conceitual do PDF
`~/Downloads/sistema_distribuído_de_processamento_em_LAN-v0.9.pdf`, em dois backends
de IA. Todos os comandos rodam a partir de `bot/` (onde está o venv e o `main.py`).

Pré-requisitos comuns (já prontos no `~/.env`):
- `KDD_APP_URL` — URL da Web API em produção.
- `KDD_TOKEN_OPERADOR` — token (o bot age como operador).
- `bot/.venv` com `requests`, `pypdf`, `anthropic`.

O fluxo é sempre o mesmo: **subir o PDF** (vira fonte `pendente`) → **rodar o bot**
(baixa, extrai texto com pypdf, chama a IA, empurra o mapa via `POST /fontes/{id}/mapas`).
O que muda entre os casos é só o backend de IA (`KDD_IA_BACKEND`).

---

## Caso 1 — Claude pela linha de comando (backend `cli`, sem `ANTHROPIC_API_KEY`)

Reaproveita o CLI `claude` (Claude Code) já instalado e logado na máquina.

```bash
cd bot

# (opcional) smoke-test isolado só da extração:
KDD_IA_BACKEND=cli .venv/bin/python -c "
from kdd_bot.ia.cli_backend import CliBackend
print(CliBackend('claude-sonnet-4-6').extrair_mapa('Teste', 'Texto curto para validar o JSON...'))
"

# 1) upload do PDF (papel do operador) -> cria fonte 'pendente'
.venv/bin/python -c "
import requests; from pathlib import Path
from kdd_bot.config import Config
cfg = Config.carregar()
pdf = Path.home()/'Downloads'/'sistema_distribuído_de_processamento_em_LAN-v0.9.pdf'
r = requests.post(f'{cfg.base_url}/fontes', headers={'X-Token': cfg.token},
    files={'arquivo': (pdf.name, pdf.open('rb'), 'application/pdf')},
    data={'titulo': 'Sistema distribuído de processamento em LAN (v0.9)'}, timeout=120)
print(r.status_code, r.json())
"

# 2) roda o bot uma vez usando o CLI como backend de IA
KDD_IA_BACKEND=cli .venv/bin/python main.py

# 3) (curadoria) aprovar a fonte para a certeza subir — troque {id} pelo id retornado
.venv/bin/python -c "
import requests; from kdd_bot.config import Config
cfg = Config.carregar()
print(requests.post(f'{cfg.base_url}/fontes/{id}/aprovar', headers={'X-Token': cfg.token}).json())
"
```

Resultado obtido: ~4 min, **5 áreas, 60 conceitos, 65 proposições**. Após aprovar,
as 65 proposições passaram de `fontes_aprovadas=0` para `=1` (certeza tudo-ou-nada por fonte).

---

## Caso 2 — Ollama local com modelo básico (backend `ollama`)

Máquina de teste com ~8 GB livres e **sem GPU** → modelo pequeno e CPU-only (lento).
Instalação do Ollama em **modo usuário** (sem root, sem systemd), descartável.

```bash
# --- instalar Ollama em ~/ollama-test (sem root) ---
mkdir -p ~/ollama-test && cd ~/ollama-test
# baixa o asset oficial mais recente do GitHub (tar.zst) e extrai
url=$(curl -fsSL https://api.github.com/repos/ollama/ollama/releases/latest \
      | grep -oE '"browser_download_url": *"[^"]*ollama-linux-amd64.tar.zst"' \
      | sed 's/.*"\(https[^"]*\)"/\1/')
curl -fsSL -o ollama.tar.zst "$url"
tar --zstd -xf ollama.tar.zst        # cria bin/ e lib/

# --- subir o servidor em background, modelos contidos na pasta de teste ---
export OLLAMA_MODELS=$HOME/ollama-test/models
export OLLAMA_HOST=127.0.0.1:11434
nohup ./bin/ollama serve > ~/ollama-test/serve.log 2>&1 &
sleep 4 && curl -fsS http://localhost:11434/api/version    # confere que subiu

# --- baixar um modelo básico bom em JSON (~1.9 GB) ---
./bin/ollama pull qwen2.5:3b-instruct
```

```bash
cd ~/desenv/kdd/bot

# (opcional) smoke-test isolado da extração via Ollama:
KDD_OLLAMA_MODEL=qwen2.5:3b-instruct .venv/bin/python -c "
from kdd_bot.ia.ollama_backend import OllamaBackend
b = OllamaBackend('http://localhost:11434', 'qwen2.5:3b-instruct')
print(b.extrair_mapa('Teste', 'Texto curto para validar o JSON...'))
"

# 1) upload do PDF -> nova fonte 'pendente'
.venv/bin/python -c "
import requests; from pathlib import Path
from kdd_bot.config import Config
cfg = Config.carregar()
pdf = Path.home()/'Downloads'/'sistema_distribuído_de_processamento_em_LAN-v0.9.pdf'
r = requests.post(f'{cfg.base_url}/fontes', headers={'X-Token': cfg.token},
    files={'arquivo': (pdf.name, pdf.open('rb'), 'application/pdf')},
    data={'titulo': 'Sistema distribuído em LAN (v0.9) — via Ollama 3B'}, timeout=120)
print(r.status_code, r.json())
"

# 2) roda o bot com o backend Ollama.
#    KDD_MAX_CHARS_PDF limita o texto: o contexto padrão do Ollama é 4096 tokens,
#    então cortamos o PDF (~15k tokens) para caber sem truncar/estourar.
KDD_IA_BACKEND=ollama KDD_OLLAMA_MODEL=qwen2.5:3b-instruct KDD_MAX_CHARS_PDF=12000 \
  .venv/bin/python main.py
```

Notas do Caso 2:
- Qualidade visivelmente inferior à do Claude; serve para validar o pipeline offline.
- Para encerrar o servidor de teste: `pkill -f 'ollama serve'`. Para remover tudo:
  `rm -rf ~/ollama-test`.
