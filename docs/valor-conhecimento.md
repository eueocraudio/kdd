# Especificação — Valor do conhecimento, esteios e camada vetorial

> **Documento vivo / 1ª versão.** Deriva de [`especificacao.md`](especificacao.md). Responde à
> crítica do idealizador (2026-10-09): "até agora o projeto ficou só na extração (KD); o
> conhecimento é texto livre; falta construir informação a partir dos mapas".
> Itens **🟡 PENDENTE** precisam de decisão. Última atualização: 2026-10-09 (inclui a decisão III-b: verbos de hierarquia reforçam).

## 1. Decisões do idealizador (a base desta spec)

| # | Decisão | Consequência |
|---|---------|--------------|
| I | O projeto parou na extração. | Esta spec cria a primeira camada que **lê** o grafo e produz algo novo. |
| II | O conhecimento é texto livre; em vez de forçar tipos, **atribuir um valor 0–100%** a cada proposição. Valor máximo = *persona/organização/entidade* + *verbo* + *classificação*. | Novo campo derivado `valor` em toda proposição exposta pela API, com a fórmula em §3. |
| III | Relações não cabem num vocabulário fechado ("é parte", "é um", "participa", "compõe"… é complicado). | **Não** se tipa a relação. A fórmula só a classifica por heurística curável, em quatro classes (§3.1). |
| III-b | **Pertencer, ser, estar, incluir REFORÇAM** a ligação entre os conceitos. | Corrige a 1ª versão desta spec, que tratava esses verbos como cópula fraca. Viram classe **taxonômica**: peso de verbo forte **mais** um bônus (§3.2). |
| IV | É impossível aprovar tanta informação: **o que entrou está aprovado**. | Aprovação passa a ser **automática no processamento**; reprovar vira o veto humano (opt-out). |
| V | Síntese sim, mas levando em conta a **informação reforçada**: no mapa conceitual um **esteio** é um conceito fonte de inúmeras relações. | `esteio` por conceito (grau no grafo, escala log) entra na fórmula do valor e ganha endpoint próprio. |
| VI | Hoje é só grafo. | Mantém-se o grafo como verdade; o valor e os vetores são **derivados**, nunca editados à mão. |
| VII | Banco vetorial. | Embeddings de conceitos (rótulo + sentido) guardados no próprio MySQL; 1º uso: **conceitos semelhantes** (sugestão de merge / quase-duplicatas), que a identidade por sentido exato não pega. |

## 2. Modelo de dados (migration `007_valor.sql`)

- `conceito.tipo` `VARCHAR(20) NULL` — classe gramatical/ontológica grossa do conceito, preenchida
  pela IA na extração e corrigível no editor: `entidade` (nome próprio: pessoa, organização,
  lugar, produto, obra), `classe` (categoria/tipo/classificação), `processo` (ação, evento,
  método), `atributo` (propriedade, medida, valor), `outro`. `NULL` = desconhecido (dados antigos).
  Bot só preenche quando `NULL`; editor sobrescreve.
- View `vw_grau_conceito` — `grau_saida`, `grau_entrada`, `fontes` por conceito.
- `embedding` — `(alvo_tipo, alvo_id, modelo)` → `dim`, `vetor` (JSON), `atualizado_em`.
  Hoje `alvo_tipo='conceito'`; proposições ficam para depois.
- `conceito_similar` — `(conceito_a < conceito_b, modelo)` → `similaridade` (cosseno 0–1).
  Recalculada integralmente pelo bot a cada passada (`PUT /similares` substitui por modelo).

## 3. Fórmula do valor (0–100) — `api/src/valor.php`

`valor = 100 × (0,45·estrutura + 0,30·reforço + 0,25·esteio)`

- **estrutura** = média de três pesos:
  - origem por `tipo`: entidade 1,0 · classe 0,7 · processo 0,6 · atributo 0,4 · outro/NULL 0,5;
  - relação: pela **classe** (§3.1) — taxonômica 1,0 · verbal 1,0 · vaga 0,5 · vazia 0,3;
  - destino por `tipo`: classe 1,0 · entidade 0,8 · processo 0,7 · atributo 0,6 · outro/NULL 0,5.
  Entidade + verbo + classe ⇒ estrutura = 1,0 (a decisão II).
- **reforço** = `n/(n+1)` com `n` = fontes aprovadas (certeza da view): 0→0 · 1→0,5 · 2→0,67 · 3→0,75…
- **esteio** = 0,7·esteio(origem) + 0,3·esteio(destino), onde esteio(c) = `ln(1+grau)/ln(1+grau_max)`
  (grau = saída + entrada; `grau_max` = maior grau do armazém naquele instante). Escala log para
  um hub não achatar todo o resto.

### 3.1 Classes de relação (decisões III e III-b)

A relação **não** é tipada num vocabulário fechado. Ela é só classificada em quatro baldes, por
duas listas curáveis em `api/src/valor.php`. A comparação é feita sobre a forma normalizada
(minúsculas, sem acento, `_` → espaço), e as listas incluem as **flexões** porque a IA emite o
verbo conjugado, não o infinitivo.

| Classe | Peso | O que é | Exemplos |
|---|---|---|---|
| **taxonômica** | 1,0 **+ bônus** | **pertencer · ser · estar · incluir** e parentes (conter, compor, fazer parte de): dizem a que categoria o conceito pertence | pertence a, é, é um, é instância de, está em, inclui, abrange, contém, compõe, classifica-se como |
| **verbal** | 1,0 | verbo de ação, específico e informativo | desenvolveu, protege contra, executa |
| **vaga** | 0,5 | estrutural mas sem conteúdo: não diz o que o conceito é nem a que pertence | relaciona-se com, associado a, ligado a, refere-se a, tem, possui |
| **vazia** | 0,3 | token curtíssimo (≤ 3 letras) fora das listas | de, em, xyz |

As duas listas são checadas **antes** do corte por tamanho — senão "é" (ser) e "tem", ambas
curtas, nunca chegariam à lista e cairiam em "vazia".

`tem`/`possui` ficam em **vaga** por decisão prática: às vezes são meronímia ("carro tem rodas",
que seria taxonômico), às vezes atributo ("tem cor azul"). Na dúvida, não reforça.

### 3.2 Reforço da ligação hierárquica (decisão III-b)

Relação taxonômica ganha, além do peso de verbo forte, um **bônus** sobre o que falta para 100:

```
valor = base + 0,10 × (1 − base)
```

Nunca somado direto — assim o valor **jamais passa de 100** e o reforço é maior onde há folga.

**Por que reforçar:** num mapa de Novak a hierarquia é o esqueleto. Uma ligação dessas faz
trabalho duplo: afirma um fato **e** posiciona o conceito na hierarquia, o que torna o mapa
navegável. E são exatamente elas que entregam a "classificação" da decisão II — entidade +
verbo + classificação = o mais alto.

Medido no E2E, nas **mesmas duas pontas** (mesmos tipos, mesma certeza, mesmo esteio — só o
verbo muda): `pertence a` = **87** contra `relaciona-se com` = **78**.

`valor_detalhe` expõe `relacao_classe` e `bonus_taxonomico`, para o curador ver **por que**
aquela proposição vale o que vale.

A API devolve `valor` (inteiro) e `valor_detalhe` `{estrutura, reforco, esteio, relacao_classe,
bonus_taxonomico}` em cada
proposição (`GET /proposicoes`, `GET /conceitos/{id}`, `GET /fontes/{id}/mapa`), e `tipo`,
`grau` `{saida, entrada, fontes}` e `esteio` (0–100) em cada conceito.
**Nada é persistido**: é cálculo em leitura (o grafo é pequeno; se crescer, materializa-se).

## 4. Aprovação automática (decisão IV)

`POST /fontes/{id}/mapas`, ao marcar `processado`, também marca `status_aprovacao='aprovada'`
**se** ela estiver `pendente`. `reprovada` é respeitada (veto humano vence o bot). Desligável
com `APROVACAO_AUTOMATICA=0` no `.env` da API. `POST /fontes/{id}/aprovar|reprovar` continuam
existindo. Fonte de curadoria já nascia aprovada.

## 5. Esteios

`GET /esteios?limite=20` — conceitos ordenados por grau (desc), com `esteio` 0–100, rótulo,
sentido, tipo e áreas. É a lista dos "conceitos-pilar" do armazém.

## 6. Camada vetorial (decisão VII) — 1ª etapa

- **Onde calcula**: no bot (`kdd_bot/vetor.py`), via Ollama `/api/embed`, modelo
  `KDD_EMBED_MODEL` (padrão `nomic-embed-text`, 274 MB, rápido em CPU). Texto embutido:
  `"<rótulo principal>: <sentido>"`.
- **Onde guarda**: MySQL (`embedding`), vetor em JSON. A Hostinger não tem tipo VECTOR; o N é
  pequeno (centenas/milhares), então a similaridade é calculada no bot com numpy.
- **Fluxo** (`main.py --vetorizar`): `GET /embeddings?modelo=M&faltando=1` → embute os que faltam
  → `PUT /conceitos/{id}/embedding` → `GET /embeddings?modelo=M` (todos) → cosseno par a par →
  `PUT /similares` com os pares ≥ `KDD_SIMILAR_MIN` (padrão 0,85).
- **Consumo**: `GET /conceitos/{id}` traz `similares` (até 10); `GET /similares?min=&limite=`
  lista global (fila de sugestões de merge para o editor).
- 🟡 **PENDENTE**: na .90 o Ollama é de slot único atrás do rolhama; embeddings diretos podem
  colidir com outros consumidores. Opções: rodar `--vetorizar` no notebook contra a API de
  produção, ou abrir um canal de embeddings no rolhama.
- 🟡 **PENDENTE**: busca semântica (`?q=` por vetor) exige embutir a consulta em tempo real —
  o PHP não faz; o desktop poderia embutir via Ollama local. Fora desta etapa.

## 7. Fora de escopo (próximas etapas)

Síntese textual por conceito/área (LLM lê o subgrafo), esquemas/frames por tipo de conceito,
inferência transitiva, detecção de contradição. Cada uma vira spec própria quando a base
desta (valor + esteio + vetores) estiver estável em produção.

## 8. Critérios de aceite

1. Migration 007 idempotente; `php migrate.php` roda duas vezes sem erro.
2. Toda proposição da API traz `valor` 0–100 e `valor_detalhe`; entidade+verbo+classe com 1
   fonte e esteio médio dá valor > qualquer "outro + é um + outro" com a mesma certeza.
2-b. Nas mesmas pontas, um verbo de hierarquia (pertencer/ser/estar/incluir) vale **mais** que
   uma associação vaga, e o bônus nunca faz o valor passar de 100.
3. Push do bot com fonte `pendente` deixa a fonte `processado` **e** `aprovada`; reprovada
   permanece reprovada.
4. `main.py --vetorizar` contra API local preenche `embedding` e `conceito_similar`; dois
   conceitos com sentidos quase iguais aparecem em `GET /similares`.
5. Desktop mostra valor nas proposições, tipo/esteio no detalhe e os semelhantes.
