# KDD — Bot de Ingestão (Marco 3)

O "cérebro": lê PDFs pendentes do armazém, extrai um **mapa conceitual** com IA e
empurra conceitos/proposições de volta para a Web API (que ficam aguardando
aprovação humana). Roda numa máquina dedicada (Debian, Xeon E5-2685 v4, 32 GB, sem
GPU) — por isso a inferência local é lenta e o pipeline é assíncrono, 1 PDF por vez.

## Pipeline

`GET /fontes?status_proc=pendente` → `PATCH processando` → baixa PDF (`/arquivo`) →
extrai texto (pypdf) → **IA** → `PATCH areas` → `POST /fontes/{id}/mapas`
(→ `processado`). Em caso de falha, marca `status_proc=erro`.

## Fachada de IA (dois backends)

- **Claude** (nuvem, padrão `claude-sonnet-4-6`): extração estruturada via *tool use*
  com `tool_choice` forçado — JSON garantido pelo schema. Use para a extração que importa.
- **Ollama/Qwen 3.5** (local): HTTP com `format=json`. Barato, porém lento em CPU.

Seleção por `KDD_IA_BACKEND` = `claude` | `ollama` | `auto` (auto: Claude se houver
`ANTHROPIC_API_KEY`, senão Ollama).

## Configuração (ambiente ou `~/.env`)

| Chave | Default | Função |
|---|---|---|
| `KDD_APP_URL` | — | URL da Web API |
| `KDD_TOKEN_OPERADOR` | — | token (o bot age como operador) |
| `ANTHROPIC_API_KEY` | — | chave Anthropic (backend Claude) |
| `KDD_IA_BACKEND` | `auto` | `claude` \| `ollama` \| `auto` |
| `KDD_CLAUDE_MODEL` | `claude-sonnet-4-6` | modelo de nuvem |
| `KDD_OLLAMA_URL` | `http://localhost:11434` | endpoint do Ollama |
| `KDD_OLLAMA_MODEL` | `aravhawk/qwen3.5-opus-4.6` | modelo local (é um Qwen 3.5) |
| `KDD_MAX_CHARS_PDF` | `60000` | corte do texto enviado à IA |

## Executar

```bash
cd bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py            # uma passada
python main.py --loop     # contínuo
```
