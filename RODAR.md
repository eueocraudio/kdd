# Como rodar (estado atual)

Tudo já está instalado e validado. O **único** item que falta para o bot rodar na
nuvem é a `ANTHROPIC_API_KEY`. Abaixo, o passo a passo para o dia em que ela chegar.

## Pré-requisitos já prontos
- `bot/.venv` — dependências instaladas (`anthropic`, `pypdf`, `requests`).
- `desktop/.venv` — `PySide6` instalado.
- `~/.env` — já tem `KDD_APP_URL`, `KDD_TOKEN_OPERADOR`/`_VALIDADOR`, credenciais de banco/SSH.
- API em produção no ar; armazém com **0 fontes pendentes**.
- PDF de exemplo: `bot/exemplos/botafogo.pdf` (gerável com `bot/exemplos/gerar_pdf_exemplo.py`).

## Quando a chave chegar (1 linha no ~/.env)
Acrescente ao `~/.env` (NÃO sobrescreva as outras chaves):

```
ANTHROPIC_API_KEY=sk-ant-...
```

O bot já está configurado para `claude-sonnet-4-6` e o backend `auto` passa a escolher
o Claude automaticamente assim que a chave existir.

## Teste ponta a ponta do bot (1 comando)
```bash
cd bot
.venv/bin/python exemplos/teste_ponta_a_ponta.py
```
Isso faz: upload do PDF de exemplo → roda o bot uma vez (baixa, extrai com pypdf,
chama o Claude, empurra o mapa via `POST /fontes/{id}/mapas`) → imprime os conceitos e
a constelação. A fonte fica `processado`; a **certeza só sobe** depois que o validador
aprovar (`POST /fontes/{id}/aprovar`).

## Bot em produção contínua
```bash
cd bot
.venv/bin/python main.py            # uma passada nas pendentes
.venv/bin/python main.py --loop     # fica observando
```

## Cliente desktop (consulta, somente leitura)
```bash
cd desktop
.venv/bin/python main.py
```

## Alternativa offline (sem chave): Ollama
Com o Ollama rodando e o modelo baixado, defina `KDD_IA_BACKEND=ollama` no `~/.env`.
É lento em CPU (máquina-alvo sem GPU), mas dispensa a chave da Anthropic.
