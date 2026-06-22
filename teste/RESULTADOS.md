# Resultados dos testes do bot (ingestão ponta a ponta)

Registro do que foi exercitado em 2026-06-21, validando o pipeline de ingestão do bot
(Marco 3) contra a Web API em produção. A sequência de comandos está em
[`COMO_EXECUTAR.md`](COMO_EXECUTAR.md); o contrato de saída da IA, em
[`mapa_schema.json`](mapa_schema.json) (+ [`exemplo_mapa.json`](exemplo_mapa.json)).

PDF de teste: `~/Downloads/sistema_distribuído_de_processamento_em_LAN-v0.9.pdf` (3,3 MB).

## Pipeline validado

`POST /fontes` (upload, fonte `pendente`) → `PATCH processando` → `GET /fontes/{id}/arquivo`
→ extração de texto (pypdf) → **fachada de IA** (`extrair_mapa`) → `PATCH areas`
→ `POST /fontes/{id}/mapas` (`processado`). Saída sempre normalizada por `normalizar()`
para casar com `mapa_schema.json`.

## Caso 1 — backend `cli` (Claude pela linha de comando)

- Usa o CLI `claude` (Claude Code) já logado na máquina, com `--json-schema` →
  resposta no campo `structured_output`. **Não precisa de `ANTHROPIC_API_KEY`.**
- Modelo: `claude-sonnet-4-6`. Roda num diretório temporário (não carrega o
  `CLAUDE.md`/memória do projeto).
- **Resultado (fonte 8):** ~4 min · **5 áreas, 60 conceitos, 65 proposições**.
  Áreas inferidas: Sistemas Distribuídos, Ciência da Computação, Redes de Computadores,
  Arquitetura de Software, Processamento Paralelo e Distribuído.
- Extração de alta qualidade, com sentidos desambiguantes e até detalhes de
  implementação do protótipo (Python, FastAPI, UV, Deque, nó mestre/trabalhador).

### Curadoria / certeza (validada neste caso)

- `POST /fontes/8/aprovar` → `status_aprovacao: aprovada` (HTTP 200).
- Proposições com `fontes_aprovadas > 0`: **4 → 69** (Δ +65, exatamente as da fonte 8):
  as triplas passaram de `✓0` para `✓1`.
- Confirma o modelo de certeza da spec: **aprovação por fonte, tudo-ou-nada**, agregada
  por JOIN sobre referências de fontes aprovadas (`vw_certeza_proposicao`). Reprovar
  derruba a certeza na mesma medida, sem recálculo.

### Reexecução via `teste_cli.py` (fonte 10)

O mesmo PDF foi reingerido pelo script reutilizável `bot/exemplos/teste_cli.py`
(que sobe um PDF indicado e roda só aquela fonte no backend `cli`):

- ~5,5 min · **5 áreas, 68 conceitos, 68 proposições** → `processado`.
- Áreas: Sistemas Distribuídos, Redes de Computadores, Engenharia de Software,
  Arquitetura de Software, Computação Paralela.
- Ao aprovar a fonte 10, proposições com certeza > 0 foram de **69 → 137** (Δ +68).

**Evidência forte da limitação "sinônimos não se fundem":** todas as 68 proposições
da fonte 10 subiram `0 → 1` (e **não** `1 → 2`), apesar de a fonte 8 já ter ingerido
o mesmo PDF. Os sentidos gerados nesta extração ficaram ligeiramente diferentes dos
da fonte 8, então **criaram conceitos/proposições novos em vez de reforçar os
existentes**. Duas ingestões do mesmo conteúdo **dobraram o grafo** em vez de aumentar
a certeza das mesmas arestas — argumento concreto para uma etapa de merge por
similaridade de sentido no Marco 4.

## Caso 2 — backend `ollama` (modelo local básico)

- Ollama instalado em **modo usuário** (sem root/systemd) em `~/ollama-test`; descartável.
- Máquina de teste: ~8 GB livres, **sem GPU** → CPU-only e lento. Contexto padrão do
  Ollama = **4096 tokens**, por isso o texto foi limitado (`KDD_MAX_CHARS_PDF=12000`).
- Modelo: `qwen2.5:3b-instruct` (~1,9 GB), escolhido por ser pequeno e bom em JSON.
- **Smoke-test isolado:** devolveu JSON **válido no schema** em ~89 s para um trecho curto.
  Qualidade visivelmente inferior à do Claude (ex.: relação espúria
  `Botafogo —[fundado_em]→ Botafogo de Futebol e Regatas`), mas funcional.
- **Run completo (fonte 9):** ~6m36s no CPU (texto cortado em 12k chars). Extração
  **magra**: 2 áreas, 6 conceitos, 1 proposição — e a única proposição foi **descartada**
  (0 chegaram ao armazém, provavelmente por referenciar conceito não resolvido).
  Comparado ao `cli`/Claude (60 conceitos, 65 proposições), o modelo 3B com contexto
  truncado entrega muito pouco do PDF.
- **Falha típica de modelo pequeno:** a fonte 9 terminou ligada a áreas **off-topic**
  (Futebol, Jornalismo, Entretenimento) — o 3B "papagaiou" os exemplos embutidos no
  próprio prompt/schema (`"ex.: Futebol, Jornalismo"`) em vez de inferir do texto.
- **Conclusão prática:** o backend `ollama` valida o caminho offline do pipeline, mas
  para extração de qualidade num PDF real é preciso modelo maior e mais contexto
  (`num_ctx`); o 3B serve só para testar a mecânica, não para produção.

## Observações de domínio (para o Marco 4 — curadoria)

- **Sinônimos não se fundem:** como a identidade do conceito é o **sentido**, fontes
  diferentes sobre o mesmo tema geram quase-duplicatas (`Sistema Distribuído` ×
  `Sistema distribuído`; `Tolerância a Falhas` × `Tolerância a falhas (Resiliência)`).
  É o comportamento esperado, mas indica necessidade de uma etapa de merge por
  similaridade de sentido (ou curadoria humana) para consolidar.
- O endpoint `GET /conceitos` retorna a chave `rotulos` (plural, concatenado por
  `GROUP_CONCAT`), não `rotulo`.

## Ambiente

- API em produção (Hostinger), acessada como **operador** via `KDD_TOKEN_OPERADOR`.
- `bot/.venv`: `requests`, `pypdf`, `anthropic`. Seleção de backend por `KDD_IA_BACKEND`
  (`claude` | `ollama` | `cli` | `auto`).
- Seed de demonstração (Botafogo) convive na base; foi a origem das 4 proposições que
  já tinham certeza antes da aprovação da fonte 8.
