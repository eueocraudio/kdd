# Especificação — Idioma e particularidades do país

> **Documento vivo / 1ª versão.** Deriva de [`especificacao.md`](especificacao.md) e
> [`universos.md`](universos.md). Última atualização: 2026-10-09.

## 1. O pedido

> "falta o idioma, idioma e pior, as particularidades do país."

Duas lacunas, e a segunda é a difícil. Hoje o armazém não tem nenhuma noção de idioma (tudo
é implicitamente pt-BR porque o repo é em português) e nenhuma de jurisdição.

**Por que o país é pior que o idioma:** idioma é **superfície** — a mesma ideia com outra
palavra. País pode mudar o **próprio sentido**, e sentido é a identidade do conceito. Idioma
é problema de apresentação; país é problema de identidade.

## 2. Três fenômenos que NÃO podem ser confundidos

| # | Fenômeno | Exemplo | Onde vive |
|---|---|---|---|
| 1 | Mesma ideia, palavra de outro idioma | Porta / Door / Puerta | `rotulo.idioma` |
| 2 | Mesma ideia, palavra de outro país, **mesmo idioma** | Celular (BR) / Telemóvel (PT) | `rotulo.idioma` = `pt-BR` / `pt-PT` (a tag BCP-47 já carrega a região) |
| 3 | **Sentido diferente**, ou só existe lá | CPF (só BR) · Imposto de Renda (BR) ≠ IRS (PT) · bilhão = 10⁹ (BR) ≠ 10¹² (PT antigo) | `conceito.pais` — **identidade** |
| 4 | Mesmos conceitos, relação só vale lá | maioridade penal → 18 anos (BR) | `proposicao.pais` |

Os casos 1 e 2 são **tradução**: um conceito, vários rótulos. Os casos 3 e 4 são **outra
coisa**: conceitos e proposições diferentes. Tratar "Imposto de Renda" e "IRS" como tradução
um do outro seria um erro de domínio — são institutos jurídicos distintos que se parecem.

## 3. Idioma — superfície, no rótulo

- `rotulo.idioma VARCHAR(16) NOT NULL DEFAULT 'pt-BR'` — tag estilo BCP-47 (`pt-BR`,
  `pt-PT`, `en`, `es-AR`). Validada contra `^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$`.
- Unicidade passa a `rotulo(conceito_id, idioma, texto)`: o mesmo texto pode repetir em
  idiomas diferentes ("Internet" em pt e en é o mesmo texto, dois rótulos).
- **Leitura com fallback**: `?idioma=en` prefere o rótulo em inglês, cai para o idioma-base
  do universo e, por fim, para qualquer um. **Nunca** devolve vazio só porque falta a
  tradução — um mapa meio traduzido continua navegável.

### O SENTIDO tem um idioma só, declarado pelo universo

`universo.idioma` (default `pt-BR`). Todo sentido daquele universo é escrito nele.

Assimetria deliberada: o sentido é a **string de identidade**, não texto de exibição.
Traduzir o sentido bifurcaria a identidade — "Categoria de sistema que gera texto" e
"Category of text-generating system" virariam **dois** conceitos, exatamente o que
`UNIQUE(universo_id, sentido)` existe para impedir. Então: sentido numa língua, rótulos em
quantas quiser.

## 4. País — identidade, com sentinela em vez de NULL

- `conceito.pais CHAR(2) NOT NULL DEFAULT ''` (ISO 3166-1 alfa-2 em maiúsculas: `BR`, `PT`).
- `proposicao.pais CHAR(2) NOT NULL DEFAULT ''`.
- **`''` = universal** (o caso comum: "TCP", "proteína" não têm país). Preenchido = só faz
  sentido naquela jurisdição.

### ⚠️ Por que sentinela `''` e não NULL

`UNIQUE(universo_id, pais, sentido)` com `pais` NULL **não funcionaria**: MySQL/MariaDB
tratam NULLs como distintos entre si, então daria para inserir duas vezes a mesma
`(universo, NULL, sentido)` e fragmentar a identidade em dois ids — justamente a invariante
que a migration 004 criou para garantir. Com `''` o índice morde. Mesma razão em
`proposicao`.

### ⚠️ O filtro de país é INCLUSIVO — ao contrário do universo

| | Semântica |
|---|---|
| universo | **igualdade estrita** — é outro plano, nada atravessa |
| país | **`pais IN ('', <escolhido>)`** — universal **mais** o do país escolhido |

Um leitor no Brasil vê os conceitos universais **e** os brasileiros, e nunca os que só
existem em Portugal. País **marca jurisdição dentro** de um plano; não cria plano. Confundir
as duas semânticas é o erro mais provável nesta camada.

Sem `?pais=`, a leitura traz **tudo** (universal e de todos os países), que é o
comportamento de hoje e mantém a retrocompatibilidade.

## 5. O que NÃO muda

- **Grau e esteio seguem por universo**, não por país: o grafo é um só dentro do universo
  (uma lei brasileira se relaciona com um conceito universal). `kdd_grau_max()` continua
  por universo.
  - Simplificação conhecida: uma relação bifurcada por país conta grau duas vezes. Aceitável
    — mais relações é mais pilar — e mais simples que um grau por país.
- **A certeza** não muda: ela é por proposição, e a proposição já carrega o país.
- **O bot** continua varrendo todos os universos; idioma e país vêm da extração, por fonte.

## 6. API

| Rota | Nota |
|---|---|
`GET /conceitos`, `/proposicoes`, `/esteios`, `/areas`, `/constelacao` | `?idioma=` escolhe o rótulo (com fallback); `?pais=` filtra inclusivo |
`GET /conceitos/{id}` | devolve `pais` e **todos** os rótulos com o `idioma` de cada um |
`POST /conceitos` | aceita `pais` e `idioma` (do rótulo principal) |
`POST /conceitos/{id}/rotulos` | aceita `idioma` — é como se traduz um conceito |
`POST /proposicoes` | aceita `pais` |
`POST /fontes/texto`, `POST /fontes` | aceitam `idioma` e `pais` da fonte: o padrão do que o bot extrair dela |
`POST /universos` | aceita `idioma` (base dos sentidos daquele universo) |

`fonte.idioma` e `fonte.pais` são o **padrão herdado** pelo que sai daquela fonte: um PDF da
legislação brasileira ingerido com `pais=BR` faz os conceitos dele nascerem `BR`, sem a IA
precisar acertar isso item por item.

## 7. Extração (bot)

`MAPA_SCHEMA` ganha `idioma` por conceito (do rótulo) e `pais` por conceito e por
proposição. O `SYSTEM` tem que ensinar a distinção do §2, que é onde um LLM erra sozinho:
tradução é o MESMO conceito com outro rótulo; instituição de um país é OUTRO conceito.

Quando a IA não informa, vale o padrão da fonte (§6).

## 8. Fora de escopo

Tradução automática de rótulos; sentido multilíngue (ver §3); embedding multilíngue — o
`nomic-embed-text` é majoritariamente inglês, então a similaridade entre idiomas é fraca e
fica pendente de um modelo multilíngue; casamento do catálogo de trilhas com acento/idioma.

## 9. Critérios de aceite

1. Migration idempotente; base existente vira `idioma='pt-BR'`, `pais=''` sem perder nada,
   e leitura sem `?idioma=`/`?pais=` responde como antes.
2. Um conceito com rótulos em pt-BR e en: `?idioma=en` devolve o inglês, `?idioma=es`
   (ausente) cai no fallback em vez de devolver vazio.
3. O mesmo texto de rótulo coexiste em dois idiomas no mesmo conceito.
4. Dois conceitos de **mesmo sentido** e países diferentes coexistem; repetir o mesmo
   `(universo, pais, sentido)` é barrado.
5. `?pais=BR` traz universais **e** brasileiros, e **não** traz os de PT.
6. A mesma tripla pode existir com `pais` diferente, com certezas independentes.
7. Fonte com `idioma`/`pais` propaga o padrão para o que o bot empurrar dela.
8. MCP e desktop deixam escolher idioma e país.
