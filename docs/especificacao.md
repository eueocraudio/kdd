# Especificação — KDD (Knowledge Discovery in Databases)

> **Documento vivo / rascunho.** Construído incrementalmente a partir da descrição do
> idealizador. Itens marcados como **🟡 PENDENTE** ainda precisam de decisão.
> Última atualização: 2026-06-21.

---

## 1. Visão geral

Plataforma que **extrai conhecimento de documentos PDF e o representa como Mapas
Conceituais**, expondo esse conhecimento como uma **base de conhecimento navegável
por humanos e por máquinas**, com **curadoria humana** e **versionamento**.

O conhecimento é organizado por **áreas** (domínios) e o conjunto de áreas se
interliga formando uma **"constelação"** de conhecimento.

### 1.1 Fundamentação teórica
- **Mapas Conceituais (Joseph Novak):** conceitos ligados por relações nomeadas,
  formando proposições, com estrutura hierárquica.
- **Aprendizagem Significativa (David Ausubel):** ancoragem de conhecimento novo em
  estrutura existente (subsunçores). *Base conceitual; o sistema não tem objetivo de
  ensino (ver Escopo).*

### 1.2 Propósito (decidido)
- ✅ **(A)** Gerar mapas conceituais **automaticamente** a partir dos PDFs.
- ✅ **(C)** Servir como **base de conhecimento consultável** — por humanos e por
  **outros programas** (integração futura: humanos *e* máquinas navegam).
- ❌ **(B)** Apoiar a aprendizagem do usuário — **FORA DE ESCOPO** (o usuário já domina
  o conteúdo).

---

## 2. Arquitetura — três soluções em torno de um núcleo

```
   [BOT com IA]                    [App PySide]                 [Outros programas
  lê PDFs, gera        humanos consultam, editam,               (futuro, máquinas)]
  mapas, faz PUSH      aprovam/reprovam mudanças                        |
        |                          |                                    |
        +-------------> [WEB API + Banco de Dados] <-------------------+
                          núcleo / fonte da verdade
                          versiona e gerencia aprovação
```

| # | Solução | Papel |
|---|---------|-------|
| 1 | **Web API + Banco** | **Armazém passivo.** Guarda e serve mapas/constelação, scores de confiança e versionamento. **Não calcula** (ver tensão em §4.1). Serve humanos (via app) e máquinas (integração). |
| 2 | **App PySide** | **Olhos e mãos do humano.** Consultar, navegar, editar e **moderar fontes** (aprovar/reprovar) — governança contra fontes ruins. Versionado. |
| 3 | **Bot com IA** | **Cérebro.** Recebe massa de PDFs → **infere as áreas** → gera mapas → **calcula a certeza** → faz **push** do resultado já calculado para o armazém. |

**Separação de responsabilidades:** **Bot = cérebro** (extrai, infere áreas, calcula
certeza) · **API = armazém** (guarda + serve, incl. scores) · **PySide = olhos/mãos do
humano** (vê + modera fontes).

**Padrão central:** grafo de conhecimento **probabilístico** com **curadoria humana no
loop** — a IA *propõe e calcula*, o humano *modera fontes*, tudo *versionado*.

---

## 3. Modelo de domínio

### 3.1 Conceito (sentido)
- A identidade do conceito vive no nível do **sentido**, não do rótulo.
- O par **(rótulo + área)** desambigua, mas o mesmo sentido pode ter vários rótulos
  (sinônimos/apelidos) e pertencer a várias áreas.
- Exemplos:
  - `Botafogo (time)` → **um** conceito, pertence às áreas {Futebol, Jornalismo}.
  - `Botafogo (bairro)` → **outro** conceito.

### 3.2 Área (dimensão / namespace)
- Toda concepção de conhecimento se dá dentro de uma ou mais **áreas**.
- Relação **N–N**: um conceito pode pertencer a **mais de uma área**.

### 3.3 Proposição (relação)
- `Conceito A —[relação nomeada]→ Conceito B`.
- Pode **cruzar áreas** (liga conceitos de áreas diferentes) — é um dos mecanismos da
  "constelação".

### 3.4 Constelação
- Estrutura macro que interliga as áreas:
  `proposição → mapa/área (estrela) → constelação (todas as áreas interligadas)`.
- A interligação ocorre por **dois fenômenos que coexistem** (mundo real):
  - **(a) Homônimos:** mesmo rótulo, sentidos diferentes (Botafogo bairro × time).
  - **(b) Pontes interdisciplinares:** mesmo sentido, várias áreas (Botafogo-time em
    Futebol e Jornalismo).

### 3.5 Fonte (documento)
- Cada PDF é uma **fonte**. A **área da fonte é inferida pelo bot** (o humano apenas
  aponta o bot para uma massa de PDFs; o bot diz quais são as áreas do conhecimento).
- A área da fonte **propaga** para os conceitos/proposições dela extraídos: um conceito
  nasce na área da fonte e **ganha novas áreas** conforme aparece em fontes de outras
  áreas. → É assim que o N–N conceito↔área se forma na prática.
  - Ex.: `Botafogo (time)` nasce em Futebol e ganha Jornalismo ao surgir numa fonte
    jornalística.
- ✅ Uma fonte pode pertencer a **várias áreas**.

### 3.6 Incerteza e Certeza (transversal) — princípio central

Confiança é **numérica, contínua, ∈ [0,1]** (escala científica).

**A certeza é EMERGENTE, não declarada.** Fundamento: racionalidade limitada de
**Herbert Simon** — o humano não acessa a verdade absoluta, apenas *satisfaz*. Logo a
certeza do sistema **não** vem de um carimbo humano de "isto é verdade":

> **Quanto mais fontes e mais conceitos reforçam uma ligação, maior a certeza dela.**
> A certeza é a convergência/corroboração de evidências.

Consequências:
- **Dinâmica:** a confiança de uma proposição **sobe sozinha** conforme novas fontes a
  corroboram, e **cai** quando uma fonte é removida/reprovada. A aprovação humana não
  "congela" em certo.

**Função de certeza (decidido):**
- Insumos: **(1) contagem de fontes/referências** que afirmam a ligação **+ (2) reforço
  estrutural** (outros conceitos/caminhos no grafo que corroboram indiretamente). Ambos.
- Forma: **linear** (decisão por desempenho — leve). Curva logarítmica seria conceitualmente
  melhor (saturação) mas é pesada. Opção futura barata se necessário: saturação `n/(n+k)`.

A incerteza aparece em pontos distintos, tratados separadamente:

| Onde mora a incerteza | Exemplo |
|---|---|
| **Identidade** (resolução de entidade) | "Esse 'Botafogo' do PDF novo é o time existente, o bairro, ou um conceito novo?" |
| **Pertencimento a área** | "Esse conceito pertence mesmo à área Jornalismo?" |
| **Proposição/relação** | "Botafogo —fundado_em→ 1894 está correto?" |
| **Rótulo/sinônimo** | "'Fogão' é apelido do mesmo conceito Botafogo-time?" |

### 3.7 Proveniência
- A confiança depende de rastrear **quantas/quais fontes** sustentam cada conceito e
  proposição → proveniência é **obrigatória** (insumo do cálculo de certeza), não
  opcional.
- ✅ Proveniência no nível do **PDF (fonte)** basta — não precisa rastrear
  trecho/página/citação.

---

## 4. Versionamento, curadoria e recálculo (núcleo)

A IA propõe e calcula; o humano **modera fontes**; tudo fica versionado.

**Natureza da aprovação humana (decidido):** a curadoria **não** desconfia do cálculo —
desconfia de **outro humano** injetando **fontes ruins** (cenário multiusuário). É
**governança/moderação de fontes**, não checagem de fato.

### 4.1 ✅ Resolução: certeza calculada no JOIN (na leitura)
A tensão "armazém passivo × certeza dinâmica" some porque a **certeza não é armazenada
pronta** — ela é **derivada no momento da leitura, via JOIN/agregação**:
- O armazém guarda **fatos atômicos**: proposições e **referências** (qual fonte sustenta
  o quê) + **status de aprovação** de cada uma.
- A certeza de uma proposição = JOIN que **conta as referências aprovadas** (mais reforço
  estrutural). Linear → `COUNT`, barato.
- **Reprovar fonte ruim** = apenas marcar a referência como reprovada. O próximo JOIN
  **não a conta** e a certeza **cai sozinha**. Nenhum job de recálculo necessário. ✅
- Trade-off de escala: calcular no JOIN a cada leitura pode pesar; mitigação por
  **view materializada / cache** (sem mudar o modelo).
- ✅ **CONFIRMADO** — o **bot extrai e sobe a evidência** (proposições + referências); a
  **certeza é derivada no JOIN**, na leitura, e **não é gravada** pelo bot.

### 4.2 Granularidade da aprovação (decidido)
- ✅ Unidade de curadoria = **mapa + fonte juntos** (a submissão do bot a partir de um
  PDF). **Tudo ou nada:** ao aprovar, **todas as proposições daquela fonte ficam
  aprovadas** (cascata); sem aprovação parcial.
- Casa com o JOIN (§4.1): a certeza conta **referências de fontes aprovadas**. Reprovar a
  fonte → suas referências saem do JOIN → certeza cai. Aprovar → entram.
- 🟡 CONFIRMAR — terminologia "mapa" tem dois sentidos:
  - **Submissão/Contribuição** = pacote `fonte → proposições` que o bot sobe e o validador
    aprova (o que se aprova).
  - **Mapa da Área** = visão acumulada de uma área (a "estrela" da constelação, §3.4) que
    emerge das submissões aprovadas.

### 4.3 Versionamento
- ✅ **Modelo de versão: diffs/changesets** (tipo commits git) — cada mudança é um delta
  atribuído a um autor (bot ou humano), não snapshots inteiros.
- 🟡 PENDENTE — **Conflitos:** com aprovação no nível da fonte + diffs, tende a ser raro;
  provável tratamento simples (a confirmar).
- ✅ **Papéis:** dois perfis humanos definidos (§6) — Operador × Validador.

---

## 5. Requisitos não-funcionais / decisões técnicas

- ✅ **Exposição da confiança:** os scores são **armazenados e servidos** pela API; as
  máquinas/consumidores recebem o conhecimento **junto com os scores** (decidem o quanto
  confiar). A API não "esconde" nem "limpa" — ela entrega o calculado.
### 5.1 Stack (decidido)
- **App Desktop (cliente):** Python + **PySide**.
- **Web API (armazém):** **PHP**.
- **Banco de dados:** **MySQL** (relacional — JOIN nativo, casa com a certeza por JOIN §4.1).
- **Bot (cérebro):** ✅ **Python** (ecossistema de IA; fala com a API PHP por HTTP).

### 5.2 IA / LLM (decidido)
- **Dois provedores via uma FACHADA** (abstração para trocar sem reescrever o bot):
  - **LOCAL — Ollama**, rodando **Qwen 3.5** (pesos abertos, Alibaba). Barato e privado;
    bom para volume/rascunho. Imagem usada: `aravhawk/qwen3.5-opus-4.6`.
    - ⚠️ **Atenção ao nome:** o sufixo `opus-4.6` é rótulo de marketing do autor da imagem
      na comunidade — **NÃO é o Claude Opus**. O modelo real é Qwen 3.5. A Anthropic não
      distribui Claude pelo Ollama. Não confundir "Opus local" — é Qwen.
  - **NUVEM — Claude (Anthropic API)**, para extração de alta qualidade.
    - Modelo escolhido: **Claude Sonnet 4.6** (`claude-sonnet-4-6`) — capaz e bem mais
      econômico que o Opus para esse volume.
- ⚠️ Nota importante: **Ollama não roda Claude**. Claude (Opus/Sonnet/Haiku) é proprietário
  e só via API da Anthropic; Ollama serve apenas modelos abertos. A fachada é o que permite
  usar os dois lados de forma intercambiável.

### 5.3 Topologia / Implantação
- O **bot/cérebro roda numa máquina dedicada**, **separada do desktop** do usuário.
  - Specs: **Debian · Xeon E5-2685 v4 (~16 núcleos, Broadwell) · 32 GB DDR4 · sem GPU.**
  - ⚠️ **Inferência só em CPU** → LLM local é **lento**. Tolerável porque o pipeline é
    **assíncrono e 1 PDF por vez**. Implicações:
    - Preferir **Qwen menor quantizado (7B–14B, Q4)** no Ollama para velocidade razoável;
      modelos 30B+ cabem em 32 GB mas rodam a poucos tokens/s. Checar o tamanho da imagem
      `aravhawk/qwen3.5-opus-4.6`.
    - Sem GPU, é natural **pender para o Claude Sonnet** na extração que importa, usando o
      Ollama para tarefas leves/auxiliares.
- A **Web API roda na Hostinger** (PHP+MySQL+Apache compartilhado); o bot acessa por HTTPS.
  - O bot **não** roda na Hostinger (sem processos longos/GPU). Migrations via phpMyAdmin.
  - Segurança: só `public/` exposto; `src/`, `tokens.json`, `.env`, `storage/pdfs/`
    fora do web root.
  - **Layout concreto na Hostinger** (SSH cai em `/home/u944249633/`; só `public_html` é
    servido):
    ```
    /home/u944249633/domains/paleturquoise-dunlin-206466.hostingersite.com/
    ├── public_html/     ← conteúdo de api/public/  (index.php, .htaccess)
    ├── src/             ← fora da web
    ├── migrations/
    ├── storage/pdfs/    ← fora da web
    ├── .env             ← fora da web
    └── tokens.json      ← fora da web
    ```
    Os caminhos relativos no código (`dirname(__DIR__)`) resolvem certo: `public_html` é o
    `public/`, e o restante fica um nível acima (não acessível por URL).
- O **PySide envia o PDF** para essa máquina de processamento.
- ✅ **Roteamento do PDF até o bot: via armazém (opção i).** A **Web API intermedia**:
  o PySide faz **upload do PDF para a API** (que guarda o PDF + marca "pendente"); a
  máquina do bot **baixa da API** os pendentes, processa, e **devolve os mapas** para a
  API. Tudo passa pelo armazém — canal único, desacoplado.
  - Implica que o armazém também guarda o **PDF bruto** e um **status de processamento**
    (pendente → processando → processado) por fonte.

### 5.4 Modelagem de dados (decidido)
- ✅ **Escala (inicial):** começa **1 PDF por vez**; dimensionar depois.
- ✅ **Representação interna: tabelas relacionais puras** no MySQL (sem extensão de grafo).
  O grafo/constelação emerge das tabelas de junção; travessia via JOIN / CTE recursivo
  quando preciso.
- ✅ **Áreas hierárquicas:** uma área tem **área-pai** (ex.: Esportes → Futebol → Times).
  Modelado com `area.parent_id` auto-referenciado; subárvores via CTE recursivo.

> Esboço de tabelas (a detalhar na Fase 3): `area(id, nome, parent_id)`,
> `conceito(id, sentido…)`, `rotulo(id, conceito_id, texto)`,
> `conceito_area(conceito_id, area_id)` [N–N], `fonte(id, pdf, status, …)`,
> `fonte_area(fonte_id, area_id)` [N–N], `proposicao(id, conceito_origem, relacao,
> conceito_destino)`, `referencia(id, proposicao_id, fonte_id, status_aprovacao)`,
> `versao/changeset(…)`. Certeza = agregação (JOIN/COUNT) sobre `referencia` de fontes
> aprovadas.

---

## 6. Atores

**Dois perfis de humanos (separação de funções proposital):**
- **Perfil 1 — Operador do bot ("carregador"):** alimenta o bot com PDFs e sobe os mapas
  gerados. É o ponto onde fontes ruins podem entrar (depende do caráter do operador).
- **Perfil 2 — Validador/Responsável:** valida e **aprova/reprova** o que subiu — vigia o
  operador. Operador ≠ validador.

Demais atores:
- **Bot de IA:** cérebro — extrai, infere áreas, sobe proposições + referências.
- **Outros programas (máquinas):** consumidores via API (integração futura), recebem o
  conhecimento **com os scores**.
- 🟡 PENDENTE — consulta de leitura por terceiros: perfil próprio? acesso público/anônimo?

---

## 7. Decisões pendentes (índice)
1. Granularidade da aprovação (§4)
2. Modelo de versão (§4)
3. Tratamento de conflitos (§4)
4. Proveniência (§3.6)
5. Representação / banco (§5)
6. Estrutura de áreas: plana × hierárquica (§5)
7. Escala (§5)
8. Stack (§5)
9. Abordagem de IA/extração (§5)
10. Representação da incerteza: numérica × qualitativa; persiste após aprovação? (§3.5)
