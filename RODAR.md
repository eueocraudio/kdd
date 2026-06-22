# Como rodar (estado atual)

Tudo já está instalado e validado.

> ⚠️ **TEMPORÁRIO:** os backends do **Claude** (`claude` via API e `cli` via Claude Code)
> estão **desativados**. Por enquanto o bot só usa o **Ollama** local (offline, sem custo).
> Os trechos sobre o Claude abaixo ficam como referência para quando forem reativados.

## Pré-requisitos já prontos
- `bot/.venv` — dependências instaladas (`anthropic`, `pypdf`, `requests`).
- `desktop/.venv` — `PySide6` instalado.
- `~/.env` — já tem `KDD_APP_URL`, `KDD_TOKEN_OPERADOR`/`_VALIDADOR`, credenciais de banco/SSH.
- API em produção no ar.
- PDF de exemplo: `bot/exemplos/botafogo.pdf` (gerável com `bot/exemplos/gerar_pdf_exemplo.py`).
- Ollama rodando e o modelo baixado (ver seção abaixo).

## Rodar AGORA (Ollama local, sem chave)
É o que o `auto` usa por padrão. Com o Ollama no ar e o modelo baixado:

```bash
cd bot
.venv/bin/python main.py                       # uma passada (auto ⇒ ollama)
.venv/bin/python main.py --backend ollama      # explícito
.venv/bin/python main.py --backend ollama --loop   # fica observando
```

É lento em CPU (máquina-alvo sem GPU), mas dispensa qualquer chave e não consome crédito.

## Teste ponta a ponta do bot
Faz tudo numa tacada: upload do PDF de exemplo → roda o bot uma vez → imprime conceitos
e constelação. A fonte fica `processado`; a **certeza só sobe** depois que o validador
aprovar (`POST /fontes/{id}/aprovar`).

```bash
cd bot
KDD_IA_BACKEND=ollama .venv/bin/python exemplos/teste_ponta_a_ponta.py
```

## Cliente desktop (consulta, somente leitura)
```bash
cd desktop
.venv/bin/python main.py
```

## Ollama: instalação do modelo
Com o Ollama rodando, baixe o modelo configurado em `KDD_IA_OLLAMA_MODEL` (ou o padrão).
O bot fala com ele via HTTP (`KDD_IA_OLLAMA_URL`).

---

## (Desativado) Claude — reativação futura
Quando o Claude voltar a ser permitido, restaure os ramos `claude`/`cli` em
`bot/kdd_bot/ia/facade.py` e as escolhas de `--backend` em `bot/main.py` (procure pelos
comentários `TEMPORÁRIO`). Aí valem novamente:

```bash
cd bot
# CLI do Claude Code (sem ANTHROPIC_API_KEY própria; reaproveita a sessão local):
.venv/bin/python main.py --backend cli
# API da Anthropic (exige ANTHROPIC_API_KEY no ~/.env):
.venv/bin/python main.py --backend claude          # usa claude-sonnet-4-6 via API
```

> **Atenção: consomem crédito.** Em backend pago (`cli`/`claude`) o bot avisa e, **sem
> `--max-fontes`, processa no máximo 1 fonte por execução**. Use `--max-fontes N` para
> mais (ou `--max-fontes 0` para sem limite). O `auto` **nunca** escolhe um pago sozinho.
