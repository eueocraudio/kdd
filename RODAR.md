# Como rodar (estado atual)

Tudo já está instalado e validado. Há **três** formas de dar IA ao bot: o **CLI do
Claude** (roda hoje, sem chave própria), a **API da Anthropic** (precisa de
`ANTHROPIC_API_KEY`) e o **Ollama** local (offline, sem custo). Escolha o método com
`--backend` ou `KDD_IA_BACKEND`.

## Pré-requisitos já prontos
- `bot/.venv` — dependências instaladas (`anthropic`, `pypdf`, `requests`).
- `desktop/.venv` — `PySide6` instalado.
- `~/.env` — já tem `KDD_APP_URL`, `KDD_TOKEN_OPERADOR`/`_VALIDADOR`, credenciais de banco/SSH.
- API em produção no ar.
- PDF de exemplo: `bot/exemplos/botafogo.pdf` (gerável com `bot/exemplos/gerar_pdf_exemplo.py`).

## Rodar AGORA, sem chave (Claude pela linha de comando)
Se o CLI `claude` (Claude Code) estiver instalado e logado nesta máquina, o bot roda
sem `ANTHROPIC_API_KEY` — reaproveita essa sessão:

```bash
cd bot
.venv/bin/python main.py --backend cli            # uma passada nas pendentes
.venv/bin/python main.py --backend cli --loop      # fica observando
```

> **Atenção: consome crédito do Claude Code.** Por isso, em backend pago (`cli`/`claude`)
> o bot avisa e, **sem `--max-fontes`, processa no máximo 1 fonte por execução**. Use
> `--max-fontes N` para mais (ou `--max-fontes 0` para sem limite).

## Quando a chave chegar (API da Anthropic)
Acrescente ao `~/.env` (NÃO sobrescreva as outras chaves):

```
ANTHROPIC_API_KEY=sk-ant-...
```

E selecione o backend explicitamente (o `auto` **não** escolhe um pago sozinho):

```bash
cd bot
.venv/bin/python main.py --backend claude          # usa claude-sonnet-4-6 via API
.venv/bin/python main.py --backend claude --max-fontes 0   # sem limite por execução
```

## Teste ponta a ponta do bot
Faz tudo numa tacada: upload do PDF de exemplo → roda o bot uma vez → imprime conceitos
e constelação. A fonte fica `processado`; a **certeza só sobe** depois que o validador
aprovar (`POST /fontes/{id}/aprovar`).

```bash
cd bot
# escolha o método de IA pela env (o script lê KDD_IA_BACKEND):
KDD_IA_BACKEND=cli .venv/bin/python exemplos/teste_ponta_a_ponta.py     # sem chave
# ANTHROPIC_API_KEY=sk-ant-... KDD_IA_BACKEND=claude .venv/bin/python exemplos/teste_ponta_a_ponta.py
```

## Bot em produção contínua
```bash
cd bot
.venv/bin/python main.py                      # padrão: auto ⇒ ollama (local, sem custo)
.venv/bin/python main.py --backend cli --loop  # contínuo via Claude CLI (pago; cap de 1/ciclo)
```

## Cliente desktop (consulta, somente leitura)
```bash
cd desktop
.venv/bin/python main.py
```

## Alternativa offline (sem chave): Ollama
É o que o `auto` usa por padrão. Com o Ollama rodando e o modelo baixado, basta
`--backend ollama` (ou `KDD_IA_BACKEND=ollama`). É lento em CPU (máquina-alvo sem GPU),
mas dispensa qualquer chave e não consome crédito.
