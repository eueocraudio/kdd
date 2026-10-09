# Especificação — Análise de sentimento da proposição

> **Documento vivo / 2ª versão.** Deriva de [`valor-conhecimento.md`](valor-conhecimento.md).
> A 1ª versão media em **português** e foi descartada pelo idealizador: *"não usar análise de
> sentimento em português, vai dar merda; tem que traduzir a proposição, que em EN tem mais
> assertividade, existem inúmeras bases em EN."* Esta versão mede em inglês, com pacote de
> mercado. Última atualização: 2026-10-09.

## 1. O pedido e o risco dele

> "me pediram aqui de última hora: análise de sentimento da proposição"

O risco é entregar um número de "positivo/negativo" solto, decorativo. Numa base de
**conhecimento curado**, sentimento só vale se responder a pergunta que hoje não tem
resposta. Então a spec parte do que se quer perguntar:

- "o que **ameaça** este conceito?" × "o que o **protege**?"
- "esta afirmação é **fato** ou **juízo de valor**?"

A primeira é **polaridade da relação**. A segunda é **subjetividade**. Eixos independentes:
"backup protege dados" é positivo e factual; "Linux é melhor que Windows" é positivo e
subjetivo.

## 2. ⚠️ Medido em INGLÊS, com pacote de mercado, e no BOT

Análise de sentimento em pt-BR tem base pobre e erra muito. As bases, léxicos e modelos
maduros são em inglês. Então a proposição é **traduzida** para a forma canônica inglesa e a
medição acontece lá. O português nunca é analisado diretamente.

**Onde roda:** no `bot/` (Python), nunca na API. Mesma divisão da camada vetorial — Python
analisa, PHP guarda e agrega; a Hostinger não tem Python. E um motor de pontuação só: um
léxico em PHP divergiria do Python no primeiro ajuste.

**Pacotes** (`bot/kdd_bot/sentimento.py`):

| Pacote | Serve para | Por quê |
|---|---|---|
| **vaderSentiment** | polaridade | o mais usado para inglês (também embarcado no NLTK); lexicon+regras, determinístico, sem baixar modelo |
| **TextBlob** | subjetividade | `.sentiment.subjectivity` dá o eixo fato×juízo direto, e **não precisa de corpora do NLTK** — zero passo extra no deploy |

**A tradução** vem de `relacao_en`, que a IA emite por proposição (instrução nova no `SYSTEM`,
custo zero: mesma chamada da extração). Sem ela, um mapa de apoio pt→en cobre os verbos
frequentes. Sem nenhuma das duas, o sentimento sai **não medido** — ver §3.

### ⚠️ Por que ainda existe um ajuste de domínio

Medido nas proposições do próprio armazém (`kdd_bot.sentimento.autoteste()`), o VADER puro
acerta **7/13** e erra exatamente nos casos de domínio, porque pontua o **vocabulário da
frase** e não a **relação**:

| proposição | VADER | problema |
|---|---|---|
| `ransomware encrypts files` | 0,00 | não sabe que isso é péssimo |
| `firewall blocks traffic` | −0,23 | "blocks" é ruim em inglês geral, mas bloquear é bom em segurança |
| `patch fixes vulnerability` | −0,23 | o substantivo "vulnerability" arrasta a frase, embora a relação (fixes) seja boa |

O TextBlob é pior ainda em polaridade (**3/13**, devolve 0,00 para quase tudo), mas acerta
**13/13** em subjetividade — que é o eixo dele.

Então a composição final:

1. **polaridade do VERBO** manda quando o verbo é conhecido — é ele que diz se a origem ajuda
   ou prejudica o destino;
2. **agente malicioso inverte o verbo**: o mesmo verbo muda de valência conforme quem age —
   `backup encrypts files` é bom, `ransomware encrypts files` é péssimo. Lista curta de
   agentes (malware, ransomware, attacker, trojan…), porque é padrão frequente e barato;
3. **VADER** sobre a frase quando o verbo não está no mapa;
4. **TextBlob** para a subjetividade, sempre.

Resultado: **13/13** no mesmo conjunto. O que não couber nessas regras fica para a IA, que
mede por fonte e enxerga contexto que nenhum léxico enxerga.

## 3. Onde o sentimento mora: na REFERÊNCIA, não na proposição

Duas fontes podem afirmar a **mesma tripla** com enquadramento diferente: um manual técnico
diz "engenharia social explora confiança" de forma neutra; um panfleto diz o mesmo com carga.
A tripla é a mesma; o enquadramento é de **quem afirmou**.

Então o sentimento vive em `referencia` (proposição × fonte), exatamente onde a **certeza** já
vive. Consequências que saem de graça:

- a proposição expõe um sentimento **agregado** sobre as fontes **aprovadas**, numa view irmã
  de `vw_certeza_proposicao`;
- **reprovar uma fonte remove a contribuição dela**, sem recálculo — mesma mecânica da certeza;
- fontes que discordam ficam visíveis em `discordancia`, em vez de uma esmagar a outra.

⚠️ **Sentimento NÃO entra na identidade.** A tripla é a mesma dita com frieza ou com carga —
não há coluna de sentimento em `proposicao`.

⚠️ **Sem medição, o resultado é `nao_medida`, nunca "neutro".** Fabricar neutro esconderia a
ausência de análise e faria uma lacuna parecer um resultado.

## 4. ⚠️ Como o sentimento toca o VALOR — e como não toca

| | Afeta o valor? | Por quê |
|---|---|---|
| **subjetividade** | **sim, desconta** | juízo de valor vale menos como conhecimento que fato. É a tese da camada de valor levada a sério. |
| **polaridade** | **não** | um fato negativo vale tanto quanto um positivo. Descontar o negativo injetaria **viés otimista** no armazém — "malware compromete sistema" é conhecimento de primeira. |

Essa assimetria é o ponto central da spec. O desconto:

```
valor = valor_com_bônus × (1 − 0,20 × subjetividade)
```

Multiplicativo e limitado: subjetividade 0 não muda nada, 1 tira 20%. Omissão conta como 0 —
**nenhuma penalização por falta de medição**, então a base existente não muda de valor.

Medido no E2E, mesma forma de tripla e mesmas pontas: fato **77**, juízo **62**.

## 5. Modelo de dados (migrations `010` e `011`)

```sql
referencia.polaridade     DECIMAL(3,2) NULL   -- -1.00 .. 1.00
referencia.subjetividade  DECIMAL(3,2) NULL   --  0.00 .. 1.00
proposicao.relacao_en     VARCHAR(191) NULL   -- substrato da análise
```

NULL = não medido (distinto de 0,00 = medido como neutro).

`vw_sentimento_proposicao` agrega os dois eixos **só sobre fontes aprovadas**, com
`fontes_medidas` e `discordancia` (amplitude da polaridade: alto = as fontes divergem).

⚠️ O JOIN tem a mesma forma do de `vw_certeza_proposicao`, e a mesma armadilha documentada: o
agregado é sobre o lado **aprovado** do LEFT JOIN (`f.id`), não sobre `r.fonte_id` — senão o
enquadramento de uma fonte reprovada continuaria pesando.

`relacao_en` serve a **dois** fins: substrato do sentimento, e caminho para a classificação de
relação (taxonômica/vaga) ficar independente do idioma da fonte — hoje o léxico de
`valor.php` é só pt-BR, o que fica fraco num universo em inglês (🟡 pendente).

## 6. API

- Toda proposição ganha `sentimento: {polaridade, subjetividade, fontes_medidas,
  discordancia, rotulo, origem}`.
- `POST /fontes/{id}/mapas` aceita `relacao_en`, `polaridade` e `subjetividade` por
  proposição — é o bot entregando o que mediu.
- `POST /proposicoes` aceita os três: é o curador corrigindo o que a IA leu.
- `GET /proposicoes?polaridade=negativa|positiva|neutra` filtra.
- `GET /conceitos/{id}` separa **`ameacas`** e **`protecoes`**: as proposições que chegam ao
  conceito com polaridade negativa e positiva. É a leitura que motivou a camada (§1).

## 7. Fora de escopo

Sentimento de conceito (só proposição tem enquadramento); sentimento do texto-fonte inteiro;
detecção de ironia; modelo transformer — o gargalo medido é **domínio**, não tamanho de
modelo, e um modelo treinado em resenhas cometeria o mesmo erro do "patch fixes
vulnerability"; tradução dos RÓTULOS (hoje usa-se o rótulo em inglês quando existe, ver
[`idioma-pais.md`](idioma-pais.md)).

## 8. Critérios de aceite

1. Migrations idempotentes; base existente fica sem sentimento e com **valor inalterado**.
2. O autoteste do módulo acerta a polaridade em todos os casos de referência.
3. Proposição sem forma inglesa sai **não medida**, nunca neutra.
4. Duas fontes com polaridades opostas na mesma tripla ⇒ média perto de 0 e `discordancia` alta.
5. **Reprovar** a fonte remove a contribuição dela do agregado.
6. Subjetividade alta **reduz** o valor; polaridade negativa **não** reduz.
7. `GET /conceitos/{id}` lista `ameacas` e `protecoes`.
8. O filtro `?polaridade=` funciona e recusa valor inválido.
