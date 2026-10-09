# KDD — Knowledge Discovery in Databases

Extrai conhecimento de documentos e o representa como **Mapas Conceituais** (Novak) numa base
navegável por **humanos e máquinas**, com curadoria humana. **Não** é sistema de ensino.

A ideia central: a identidade de um conceito é o seu **sentido**, não o rótulo. "Botafogo"
time e "Botafogo" bairro são conceitos diferentes com o mesmo rótulo. Em cima disso, o
armazém calcula quanto cada afirmação **vale**, quais conceitos **sustentam** o mapa, e
mantém **domínios isolados** que podem ser comparados entre si.

## As quatro soluções

| Pasta | O que é |
|---|---|
| **`api/`** | Web API em PHP + MySQL — a **fonte da verdade**. Headless, só JSON. Em produção. |
| **`desktop/`** | Cliente PySide6 — navega e **edita** o armazém (curadoria manual). |
| **`bot/`** | Lê documentos pendentes, extrai o mapa com IA e empurra para o armazém. |
| **`mcp/`** | Servidor MCP — expõe o armazém como **ferramentas para agentes de IA**. |

## Por onde começar

| Se você quer… | Leia |
|---|---|
| operar o repositório: comandos, deploy, armadilhas | [`CLAUDE.md`](CLAUDE.md) |
| entender o domínio e as camadas | [`docs/README.md`](docs/README.md) — o índice das especificações |
| só rodar o que já existe | [`RODAR.md`](RODAR.md) |
| verificar que nada quebrou | [`teste/E2E.md`](teste/E2E.md) — seis suítes locais e descartáveis |
| saber por que as coisas são como são | [`docs/decisoes-2026-10-09.md`](docs/decisoes-2026-10-09.md) |

## O que o armazém sabe fazer

- **Valor 0–100** por afirmação, combinando a estrutura da tripla, o reforço por fontes e o
  quanto os conceitos sustentam o mapa.
- **Esteios**: os conceitos-pilar, os que concentram mais relações.
- **Camada vetorial**: acha quase-duplicatas que a identidade por sentido exato não pega.
- **Universos paralelos**: domínios isolados onde o mesmo conceito pode existir de formas
  diferentes, com **contrapartes** ligando um ao outro.
- **Idioma e país**: idioma é superfície (vive no rótulo); país pode mudar o sentido e entra
  na identidade.
- **Sentimento** por afirmação: o que **ameaça** um conceito × o que o **protege**, e se
  aquilo é fato ou juízo de valor.

## Configuração

Segredos ficam em `~/.env`, nunca no repositório — **este repo é público**. Ver
[`.env.example`](.env.example). Acesso à API é por **token** (sem login).
