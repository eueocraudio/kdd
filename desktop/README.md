# KDD — Cliente Desktop

Aplicação PySide6 para **navegar e editar** o armazém KDD.

## Abas

| Aba | O que faz |
|---|---|
| **Áreas e Conceitos** | árvore de áreas (multi-seleção = união), busca por rótulo, detalhe do conceito com proposições, **valor**, tipo, esteio e semelhantes |
| **Mapas** | o diagrama visual (`mapa.py`): nós arrastáveis, setas rotuladas, espessura e cor pelo **valor** da proposição |
| **Fila** | status de processamento e aprovação das fontes, com Reprocessar e aprovar/reprovar |
| **Esteios** | os conceitos-pilar por grau, e a fila de **quase-duplicatas** candidatas a fusão |

Na barra há o seletor de **universo**: trocar redireciona toda a leitura do cliente (áreas,
conceitos, proposições, fila, esteios).

## Modo edição

O cliente é **somente leitura** até existir `KDD_TOKEN_VALIDADOR` no ambiente. Com o token,
aparecem o editor de conceito (sentido, tipo, rótulos, áreas, proposições, merge e split),
criar conceito e área, e aprovar/reprovar fonte.

## Configuração

Lê do ambiente ou do `~/.env`:

- `KDD_APP_URL` — URL da Web API.
- `KDD_TOKEN_OPERADOR` (ou `KDD_TOKEN`) — token de leitura.
- `KDD_TOKEN_VALIDADOR` — **habilita o modo edição**.

Nenhum segredo fica no código.

## Executar

```bash
./install-gui.sh    # na raiz: libs de sistema (Debian) + venv em desktop/.venv
./run.sh            # abre a interface
```

Equivalente direto, e o modo headless para teste:

```bash
cd desktop && .venv/bin/python main.py
QT_QPA_PLATFORM=offscreen .venv/bin/python main.py
```

## Como a certeza e o valor aparecem

A **certeza** é o nº de fontes aprovadas que sustentam a proposição. O **valor** 0–100
combina a estrutura da tripla, esse reforço e o esteio dos conceitos, e colore a aresta no
diagrama: verde alto, amarelo médio, cinza baixo. Detalhe em
[`../docs/valor-conhecimento.md`](../docs/valor-conhecimento.md).
