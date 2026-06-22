# KDD — Bot de Ingestão (Marco 3)

O "cérebro": lê PDFs pendentes do armazém, extrai um **mapa conceitual** com IA e
empurra conceitos/proposições de volta para a Web API (que ficam aguardando
aprovação humana). Roda numa máquina dedicada (Debian, Xeon E5-2685 v4, 32 GB, sem
GPU) — por isso a inferência local é lenta e o pipeline é assíncrono, 1 PDF por vez.

## Pipeline

`GET /fontes?status_proc=pendente` → `PATCH processando` → baixa PDF (`/arquivo`) →
extrai texto (pypdf) → **IA** → `PATCH areas` → `POST /fontes/{id}/mapas`
(→ `processado`). Em caso de falha, marca `status_proc=erro`.

## Fachada de IA (três backends)

- **Claude** (nuvem, padrão `claude-sonnet-4-6`): extração estruturada via *tool use*
  com `tool_choice` forçado — JSON garantido pelo schema. Use para a extração que importa.
- **Ollama/Qwen 3.5** (local): HTTP com `format=json`. Barato, porém lento em CPU.
- **CLI** (`claude` por linha de comando): reaproveita a sessão do Claude Code já
  instalado na máquina, **sem precisar de `ANTHROPIC_API_KEY`**. Pede saída estruturada
  com `--json-schema` (o CLI devolve em `structured_output`). Bom para testar o pipeline.

Seleção por `--backend` (linha de comando, sobrepõe a env) ou `KDD_IA_BACKEND` =
`claude` | `ollama` | `cli` | `auto`.

> **Proteção de crédito.** `auto` resolve **sempre** para `ollama` (local, sem custo) —
> **nunca** escolhe um backend pago sozinho. Os backends pagos (`cli`/`claude`) só rodam
> quando selecionados explicitamente, avisam com um WARNING e, sem `--max-fontes`,
> processam no máximo **1 fonte por execução**. Use `--max-fontes N` para mais
> (`--max-fontes 0` = sem limite).

## Testar com o Claude pela linha de comando (sem chave de API)

Se o CLI `claude` (Claude Code) estiver instalado e logado nesta máquina, dá para rodar
o bot inteiro sem `ANTHROPIC_API_KEY`, usando o backend `cli`:

```bash
cd bot

# 1) Sobe um PDF como o operador faria (vira fonte 'pendente'):
.venv/bin/python -c "
import requests; from pathlib import Path
from kdd_bot.config import Config
cfg = Config.carregar()
pdf = Path.home()/'Downloads'/'MEU_ARQUIVO.pdf'
r = requests.post(f'{cfg.base_url}/fontes', headers={'X-Token': cfg.token},
    files={'arquivo': (pdf.name, pdf.open('rb'), 'application/pdf')},
    data={'titulo': 'Meu título'}, timeout=120)
print(r.status_code, r.json())
"

# 2) Roda o bot uma vez usando o CLI como backend de IA:
KDD_IA_BACKEND=cli .venv/bin/python main.py
```

O backend `cli` roda o `claude` num diretório temporário (não carrega o `CLAUDE.md`/memória
do projeto) e usa `KDD_CLAUDE_MODEL` como `--model`. Para um teste isolado só da extração:

```bash
KDD_IA_BACKEND=cli .venv/bin/python -c "
from kdd_bot.ia.cli_backend import CliBackend
print(CliBackend('claude-sonnet-4-6').extrair_mapa('Teste', 'Texto a analisar...'))
"
```

## Configuração (ambiente ou `~/.env`)

| Chave | Default | Função |
|---|---|---|
| `KDD_APP_URL` | — | URL da Web API |
| `KDD_TOKEN_OPERADOR` | — | token (o bot age como operador) |
| `ANTHROPIC_API_KEY` | — | chave Anthropic (backend Claude) |
| `KDD_IA_BACKEND` | `auto` | `claude` \| `ollama` \| `cli` \| `auto` (auto ⇒ ollama; ver proteção de crédito) |
| `KDD_CLAUDE_MODEL` | `claude-sonnet-4-6` | modelo de nuvem |
| `KDD_OLLAMA_URL` | `http://localhost:11434` | endpoint do Ollama |
| `KDD_OLLAMA_MODEL` | `aravhawk/qwen3.5-opus-4.6` | modelo local (é um Qwen 3.5) |
| `KDD_MAX_CHARS_PDF` | `60000` | corte do texto enviado à IA |

## Executar

```bash
cd bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py                       # uma passada (backend = auto ⇒ ollama)
python main.py --backend cli         # Claude via CLI (pago); limita a 1 fonte
python main.py --backend cli --max-fontes 5   # processa até 5 nesta execução
python main.py --loop                # contínuo
```
