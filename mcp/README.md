# KDD — Servidor MCP

Expõe o armazém KDD como **ferramentas MCP**, para um agente de IA consultar (e, se liberado,
alimentar) a base de mapas conceituais sem saber de HTTP, rotas ou tokens.

Especificação: [`docs/mcp-servidor.md`](../docs/mcp-servidor.md).

## Instalar

```bash
cd mcp
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Precisa de `KDD_APP_URL` e `KDD_TOKEN_OPERADOR` (ou `KDD_TOKEN`) no ambiente ou em `~/.env` —
as mesmas chaves do resto do repo.

## Usar no Claude Code

O repo já traz um `.mcp.json` na raiz (escopo de projeto): abrir o projeto no Claude Code
oferece o servidor `kdd`. Para registrar à mão em qualquer cliente MCP:

```json
{
  "mcpServers": {
    "kdd": {
      "command": "/caminho/para/kdd/mcp/.venv/bin/python",
      "args": ["-m", "kdd_mcp"],
      "env": { "PYTHONPATH": "/caminho/para/kdd/mcp" }
    }
  }
}
```

Rodar direto (o stdio fica esperando o cliente; útil só para ver se sobe):

```bash
mcp/.venv/bin/python -m kdd_mcp     # log vai pro stderr; stdout é o canal do protocolo
```

## Ferramentas

**Leitura** (sempre): `listar_universos`, `listar_areas`, `buscar_conceitos`,
`obter_conceito`, `obter_contrapartes`, `listar_proposicoes`, `listar_esteios`,
`ver_constelacao`, `listar_semelhantes`, `obter_mapa_da_fonte`, `listar_fontes`.

As ferramentas de listagem aceitam `universo` (o slug): o armazém tem **universos
paralelos** (ver [`docs/universos.md`](../docs/universos.md)). Sem informar nada, trabalham
no universo `principal`.

**Escrita** (opcional): `ingerir_texto`, `criar_conceito`, `criar_proposicao`.

A escrita só é registrada com **as duas** condições: `KDD_MCP_ESCRITA=1` e
`KDD_TOKEN_VALIDADOR` presente. Sem isso o servidor sobe somente leitura e nem anuncia essas
ferramentas — o modelo não vê o que não pode usar. Nada aqui remove, desabilita, funde ou
divide conceito: isso é curadoria humana no desktop.

## Arquitetura: adaptador fino

```
cliente MCP ──stdio──> mcp/ (Python) ──HTTP+token──> api/ (PHP) ──> MySQL
```

O servidor **não** fala com o banco e **não** reimplementa regra de domínio. A `api/` é a
fonte da verdade: identidade por sentido, certeza, valor, changesets. Se uma ferramenta
precisar de algo que a API não serve, **o trabalho é na API**.

## Testar

```bash
bash teste/e2e_mcp.sh      # API local descartável + cliente MCP real (handshake e tools/call)
```
