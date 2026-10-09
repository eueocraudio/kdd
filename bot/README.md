# KDD — Bot de Ingestão

O "cérebro": lê documentos pendentes do armazém, extrai um **mapa conceitual** com IA, mede o
**sentimento** das proposições e empurra tudo de volta para a Web API.

Roda numa máquina dedicada (Debian, sem GPU) — por isso a inferência é lenta e o pipeline é
assíncrono, um documento por vez.

## Pipeline

```
GET /fontes?status_proc=pendente  →  PATCH processando  →  baixa o arquivo
  →  extrai texto (pypdf)  →  IA  →  catálogo de trilhas  →  mede sentimento
  →  PATCH areas  →  POST /fontes/{id}/mapas   (→ processado + aprovada)
```

Falha marca `status_proc=erro`, e a aba Fila do desktop devolve para `pendente`.

⚠️ **Não há messageria**: é polling a cada 60 s, e a fila é a tabela `fonte`. Há dois furos
conhecidos e **não corrigidos** (sem reivindicação atômica; fonte travada em `processando`
não volta) — diagnóstico em [`../docs/messageria-filas.md`](../docs/messageria-filas.md).

## Backends de IA (`kdd_bot/ia/`)

`IAFacade.a_partir_de(config)` escolhe por `KDD_IA_BACKEND`:

| Backend | O que é |
|---|---|
| `ollama` | local, HTTP direto com `format=json`. Padrão `qwen2.5:7b-instruct`. Lento em CPU (~4–6 min/extração). |
| `rolhama` | **o de produção.** Não bate direto no Ollama (o slot é único e colidiria com os outros consumidores): enfileira o pedido num canal do rolhama e o worker executa um por vez. |
| `auto` (padrão) | resolve **sempre** para `ollama` — nunca escolhe um backend pago sozinho. |
| `claude`, `cli` | ⚠️ **DESATIVADOS temporariamente.** Para reativar, restaure os ramos marcados com `TEMPORÁRIO` em `main.py` e `ia/facade.py`. |

Todos partilham `ia/schema.py` (`MAPA_SCHEMA`, `SYSTEM`) e a saída passa por `normalizar()`.
**Ao mexer num backend, o output tem de casar com `MAPA_SCHEMA`**, que espelha o payload da API.

## Sentimento (`kdd_bot/sentimento.py`)

⚠️ Medido em **inglês**, nunca em português: pt-BR tem base pobre e erra muito. A relação é
traduzida (`relacao_en`, que a IA emite na mesma chamada) e a medição roda sobre o inglês com
**vaderSentiment** (polaridade) e **TextBlob** (subjetividade).

Autoteste do motor, com os casos que motivaram o ajuste de domínio:

```bash
.venv/bin/python -m kdd_bot.sentimento
```

Detalhe e os números medidos em [`../docs/sentimento.md`](../docs/sentimento.md).

## Configuração (ambiente ou `~/.env`)

| Chave | Default | Função |
|---|---|---|
| `KDD_APP_URL` | — | URL da Web API |
| `KDD_TOKEN_OPERADOR` | — | token (o bot age como operador) |
| `KDD_IA_BACKEND` | `auto` | `auto` \| `ollama` \| `rolhama` |
| `KDD_OLLAMA_URL` | `http://localhost:11434` | endpoint do Ollama |
| `KDD_OLLAMA_MODEL` | `qwen2.5:7b-instruct` | modelo local |
| `ROLHAMA_WEBAPI_URL` | `https://wellington.tec.br/rolhama` | concentrador |
| `ROLHAMA_BDD_KEY` | — | obrigatória no backend `rolhama` |
| `ROLHAMA_CHANNEL` | `505` | canal reservado ao KDD |
| `ROLHAMA_OLLAMA_MODEL` | `qwen2.5:14b-instruct` | modelo em produção |
| `KDD_MAX_CHARS_PDF` | `60000` | corte do texto enviado à IA |
| `KDD_CHARS_POR_SECAO` | `0` | `>0` ativa extração por seções (⚠️ ver `CLAUDE.md`) |
| `KDD_EMBED_MODEL` | `nomic-embed-text` | modelo de embedding (`--vetorizar`) |
| `KDD_SIMILAR_MIN` | `0.85` | cosseno mínimo para gravar dois conceitos como semelhantes |

## Executar

```bash
cd bot
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python main.py                      # uma passada nas pendentes
.venv/bin/python main.py --loop               # contínuo (--intervalo 120)
.venv/bin/python main.py --vetorizar          # embute conceitos e recalcula semelhantes
.venv/bin/python main.py --backend rolhama --max-fontes 1
```

Flags: `--backend {auto,ollama,rolhama}` · `--max-fontes N` (0 = sem limite) ·
`--secoes CHARS` · `--max-secoes N` · `--vetorizar`.
