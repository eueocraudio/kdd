# KDD — Cliente Desktop (Marco 2)

Aplicação PySide6 **somente leitura** para navegar o armazém KDD: áreas
(hierárquicas), conceitos (busca por rótulo e filtro por área), detalhe do
conceito com proposições e **certeza**, e a visão de **constelação** (pontes
interdisciplinares + homônimos).

## Configuração

Lê do ambiente ou do `~/.env` (mesmas chaves do deploy da API):

- `KDD_APP_URL` — URL da Web API.
- `KDD_TOKEN_OPERADOR` (ou `KDD_TOKEN` / `KDD_TOKEN_VALIDADOR`) — token liberado.

Nenhum segredo fica no código.

## Executar

```bash
cd desktop
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Escopo

Só consulta. Edição/curadoria (aprovar/reprovar, versionamento) entram no Marco 4.
A certeza é exibida como **nº de fontes aprovadas** que sustentam cada proposição
(sinal linear da view `vw_certeza_proposicao`).
