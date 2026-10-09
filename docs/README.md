# Documentação do KDD — índice

O KDD extrai conhecimento de documentos e o representa como **Mapas Conceituais** (Novak)
numa base navegável por humanos e máquinas, com curadoria humana. **Não** é sistema de
ensino.

Para operar o repositório (comandos, deploy, armadilhas), o guia é o
[`CLAUDE.md`](../CLAUDE.md) na raiz. Esta pasta guarda as **especificações**, e o modo de
trabalho do projeto é **especificar antes de codar**.

## Fundação

| Documento | O que contém |
|---|---|
| [`especificacao.md`](especificacao.md) | visão geral, arquitetura, modelo de domínio, atores |
| [`plano-implementacao.md`](plano-implementacao.md) | marcos, DDL de referência, critérios de aceite |

⚠️ As duas são de 2026-06-21 e **precedem** as camadas abaixo. Onde divergirem, vale a spec
específica — cada uma marca o que mudou em relação à fundação.

## Camadas do armazém

| Documento | O que resolve | Marco |
|---|---|---|
| [`catalogo-trilhas.md`](catalogo-trilhas.md) | termos e caminhos conhecidos por trilha, versionados em PR, que valem como conceito por si | implantado |
| [`editor-mapas.md`](editor-mapas.md) | curadoria manual: corrigir o armazém sem depender de novo documento | implementado |
| [`valor-conhecimento.md`](valor-conhecimento.md) | **valor 0–100** por proposição, **esteios** (conceitos-pilar) e camada **vetorial** (quase-duplicatas) | implementado |
| [`universos.md`](universos.md) | **universos paralelos**: domínios de conhecimento isolados, com contrapartes entre eles | implementado |
| [`idioma-pais.md`](idioma-pais.md) | **idioma** (superfície, no rótulo) × **país** (pode mudar o sentido, entra na identidade) | implementado |
| [`sentimento.md`](sentimento.md) | **polaridade** e **subjetividade** da proposição, medidas em inglês | implementado |

## Interfaces e infraestrutura

| Documento | O que contém |
|---|---|
| [`mcp-servidor.md`](mcp-servidor.md) | servidor MCP: o armazém como ferramentas para agentes de IA |
| [`messageria-filas.md`](messageria-filas.md) | **diagnóstico**: como o processamento é disparado, e os dois furos da fila atual |

## Histórico

| Documento | O que contém |
|---|---|
| [`decisoes-2026-10-09.md`](decisoes-2026-10-09.md) | as nove decisões que criaram as camadas acima, **o que foi rejeitado e por quê**, e as assimetrias deliberadas |
| [`licoes-aprendidas.md`](licoes-aprendidas.md) | o que **deu errado**: armadilhas com a evidência medida, as lacunas de cobertura e o quadro de pendências abertas |

## As decisões que mais importam

Se você só vai ler cinco linhas antes de mexer no código, são estas:

1. **A identidade do conceito é `(universo, país, sentido)`** — não o rótulo. Rótulo é
   superfície e pode haver vários, em vários idiomas. Ver [`universos.md`](universos.md) §2 e
   [`idioma-pais.md`](idioma-pais.md) §4.
2. **O que entrou está aprovado.** O push do mapa já aprova a fonte; o humano age por
   **veto**, não por liberação. Ver [`valor-conhecimento.md`](valor-conhecimento.md) §4.
3. **O grafo é a única verdade.** Valor, esteio e sentimento são **derivados** em leitura,
   nunca editados à mão.
4. **Área classifica; universo separa.** Área é dimensão N–N sem poder de identidade.
5. **Fronteiras não se cruzam.** Proposição e fusão de conceito não atravessam universo nem
   país. A ponte entre universos é **contraparte**, não proposição.

## Onde cada coisa é medida

| Camada | Onde roda | Por quê |
|---|---|---|
| valor, esteio, certeza | **API** (PHP) | é regra de domínio; a API é a fonte da verdade |
| embeddings e similaridade | **bot** (Python) | a Hostinger não tem Python nem tipo vetorial |
| sentimento | **bot** (Python) | a análise é Python e roda sobre o **inglês** |

A API **não** pontua sentimento e o bot **não** calcula valor. Um motor por camada: duas
implementações divergiriam no primeiro ajuste de peso.

## Verificação

Não há framework de testes. A verificação é por scripts que sobem um ambiente **local
descartável** e batem na API de verdade — ver [`../teste/E2E.md`](../teste/E2E.md). São seis
suítes: catálogo, valor, MCP, universos, idioma/país e sentimento.
