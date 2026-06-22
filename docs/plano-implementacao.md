# Plano de Implementação — KDD

> Deriva de [`especificacao.md`](especificacao.md). Ordem por dependência; cada marco tem
> objetivo, entregáveis e critérios de aceite. Detalhe alto no **Marco 1**; os seguintes
> serão expandidos quando chegarmos neles.
> Última atualização: 2026-06-21.

---

## Visão geral dos marcos

| # | Marco | Entrega central | Depende de |
|---|-------|-----------------|------------|
| **1** | **Fundação do Armazém** | Schema MySQL + Web API PHP (CRUD + ingestão + certeza por JOIN) | — |
| 2 | Cliente PySide (consulta) | Navegar áreas/constelação/mapas (somente leitura) | 1 |
| 3 | Bot (cérebro) | Fachada Ollama/Claude; 1 PDF → proposições+referências; push p/ API | 1 |
| 4 | Curadoria | Fila de fontes pendentes no PySide; aprovar/reprovar (cascata) | 1, 2, 3 |
| 5 | Versionamento & refinamentos | Diffs/changesets; desambiguação; pontes interdisciplinares | 1–4 |

**Princípio de fatiamento:** fechar o Marco 1 entrega um armazém funcional e testável por
HTTP **antes** de qualquer cliente ou IA. Bot e PySide podem então ser desenvolvidos em
paralelo contra a mesma API.

---

## Decisões técnicas

- ✅ **API em PHP puro** (sem framework) + **PDO**. Combina com "armazém passivo" e mantém
  simples.
- ✅ **API headless** — **sem telas/HTML**. É só Web API (JSON). A única interface visual do
  sistema é o **PySide**.
- ✅ **Sem autenticação/login.** Acesso por **liberação de token**, definido num **arquivo
  JSON de tokens liberados** (ex.: `tokens.json`). O gate da API valida o token recebido
  contra essa lista. Formato:
  ```json
  {
    "tokens": [
      { "token": "...", "descricao": "operador - wellington", "perfil": "operador" },
      { "token": "...", "descricao": "validador - fulano",    "perfil": "validador" }
    ]
  }
  ```
  `perfil` é organizacional (não é controle de acesso técnico nesta fase); o gate apenas
  confere se o token consta na lista. Arquivo fora do versionamento (`.gitignore`).
- ✅ **Armazenamento do PDF:** **arquivo em disco + caminho no banco** (não BLOB no MySQL).
- 🟡 **Migrations:** sugerido **scripts `.sql` versionados** (simples, sem dependências) —
  confirmar (alternativa: Phinx standalone).

---

## Marco 1 — Fundação do Armazém (detalhado)

### Objetivo
Web API PHP sobre MySQL que **guarda e serve** fontes, conceitos, áreas, proposições e
referências, expõe **certeza calculada no JOIN**, e suporta o **pipeline de ingestão**
(upload de PDF → bot baixa → bot devolve mapas). Sem cliente, sem IA: tudo exercitável via
HTTP (curl/Postman/testes).

### Esquema MySQL (DDL de referência)

```sql
-- Áreas hierárquicas (parent_id auto-referenciado)
CREATE TABLE area (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  nome        VARCHAR(255) NOT NULL,
  parent_id   BIGINT NULL,
  criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (parent_id) REFERENCES area(id)
);

-- Conceito: identidade no nível do SENTIDO
CREATE TABLE conceito (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  sentido     VARCHAR(500) NOT NULL,   -- descrição desambiguadora do sentido
  criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rótulos/sinônimos de um conceito (N rótulos por sentido)
CREATE TABLE rotulo (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  conceito_id BIGINT NOT NULL,
  texto       VARCHAR(255) NOT NULL,
  principal   BOOLEAN DEFAULT FALSE,
  FOREIGN KEY (conceito_id) REFERENCES conceito(id)
);

-- N–N conceito ↔ área (um conceito mora em várias áreas)
CREATE TABLE conceito_area (
  conceito_id BIGINT NOT NULL,
  area_id     BIGINT NOT NULL,
  PRIMARY KEY (conceito_id, area_id),
  FOREIGN KEY (conceito_id) REFERENCES conceito(id),
  FOREIGN KEY (area_id)     REFERENCES area(id)
);

-- Fonte (PDF). Dois status: processamento e aprovação.
CREATE TABLE fonte (
  id                 BIGINT PRIMARY KEY AUTO_INCREMENT,
  titulo             VARCHAR(500),
  arquivo_caminho    VARCHAR(1024) NOT NULL,         -- PDF em disco/objeto
  status_proc        ENUM('pendente','processando','processado','erro')
                       NOT NULL DEFAULT 'pendente',
  status_aprovacao   ENUM('pendente','aprovada','reprovada')
                       NOT NULL DEFAULT 'pendente',
  enviado_por        BIGINT,                          -- usuário operador
  criado_em          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- N–N fonte ↔ área (área inferida pelo bot)
CREATE TABLE fonte_area (
  fonte_id BIGINT NOT NULL,
  area_id  BIGINT NOT NULL,
  PRIMARY KEY (fonte_id, area_id),
  FOREIGN KEY (fonte_id) REFERENCES fonte(id),
  FOREIGN KEY (area_id)  REFERENCES area(id)
);

-- Proposição: conceito_origem —[relação]→ conceito_destino (pode cruzar áreas)
CREATE TABLE proposicao (
  id                 BIGINT PRIMARY KEY AUTO_INCREMENT,
  conceito_origem    BIGINT NOT NULL,
  relacao            VARCHAR(255) NOT NULL,
  conceito_destino   BIGINT NOT NULL,
  criado_em          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (conceito_origem)  REFERENCES conceito(id),
  FOREIGN KEY (conceito_destino) REFERENCES conceito(id)
);

-- Referência: evidência de que uma fonte sustenta uma proposição.
-- A VALIDADE vem do status_aprovacao da FONTE (aprovação é por fonte, tudo-ou-nada).
CREATE TABLE referencia (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  proposicao_id BIGINT NOT NULL,
  fonte_id      BIGINT NOT NULL,
  criado_em     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (proposicao_id, fonte_id),
  FOREIGN KEY (proposicao_id) REFERENCES proposicao(id),
  FOREIGN KEY (fonte_id)      REFERENCES fonte(id)
);

-- Proveniência de conceito (qual fonte introduziu o conceito) — para reforço/áreas
CREATE TABLE conceito_fonte (
  conceito_id BIGINT NOT NULL,
  fonte_id    BIGINT NOT NULL,
  PRIMARY KEY (conceito_id, fonte_id),
  FOREIGN KEY (conceito_id) REFERENCES conceito(id),
  FOREIGN KEY (fonte_id)    REFERENCES fonte(id)
);
```

> **Reconciliação importante (vs §4.1 da spec):** como a aprovação é **por fonte
> (tudo-ou-nada)**, o `status_aprovacao` vive na **`fonte`**, não na `referencia`.
> Reprovar a fonte exclui automaticamente todas as suas referências do JOIN de certeza —
> exatamente o efeito desejado, sem job de recálculo.

### Certeza por JOIN (view)

```sql
-- Certeza de uma proposição = nº de fontes APROVADAS que a sustentam (linear, COUNT).
-- Reforço estrutural entra numa v2 (caminhos corroborantes); aqui a base.
CREATE VIEW vw_certeza_proposicao AS
SELECT
  p.id                              AS proposicao_id,
  COUNT(DISTINCT f.id)              AS fontes_aprovadas,
  COUNT(DISTINCT f.id)              AS certeza_bruta   -- normalização vem na app/v2
FROM proposicao p
LEFT JOIN referencia r ON r.proposicao_id = p.id
LEFT JOIN fonte f      ON f.id = r.fonte_id
                      AND f.status_aprovacao = 'aprovada'
GROUP BY p.id;
-- ATENÇÃO: o COUNT é sobre f.id (lado APROVADO do LEFT JOIN), nunca r.fonte_id —
-- senão referências de fontes pendentes/reprovadas seguiriam contando e reprovar
-- não derrubaria a certeza. (Bug corrigido após teste do fluxo aprovar/reprovar.)
```

> Normalização para [0,1] (linear, com saturação barata `n/(n+k)` opcional) fica na
> camada PHP ou numa coluna calculada — decidir no detalhamento. Materializar como cache
> só se o volume exigir (§4.1).

### Endpoints da Web API (PHP)

**Ingestão / fontes**
- `POST   /fontes` — Operador faz upload do PDF → cria fonte `status_proc=pendente`.
- `GET    /fontes?status_proc=pendente` — Bot lista pendentes.
- `GET    /fontes/{id}/arquivo` — Bot baixa o PDF.
- `PATCH  /fontes/{id}` — atualizar `status_proc` e áreas inferidas (bot).
- `POST   /fontes/{id}/mapas` — **push do bot**: payload com conceitos (com desambiguação),
  proposições e referências extraídas; cria tudo numa transação e marca
  `status_proc=processado`.
- `POST   /fontes/{id}/aprovar` · `POST /fontes/{id}/reprovar` — Validador.

**Consulta (humanos e máquinas — sempre com scores)**
- `GET /areas` — árvore hierárquica.
- `GET /conceitos` · `GET /conceitos/{id}` — rótulos, áreas, fontes, **certeza**.
- `GET /proposicoes?conceito={id}` — com `certeza` (da view).
- `GET /constelacao` — visão macro (áreas + pontes).

### Tarefas (checklist)
- [x] Decidir framework (PHP puro), migrations (`.sql`), storage (arquivo), auth (token).
- [x] Estrutura PHP + conexão MySQL (PDO) + `migrations/001_schema.sql` (tabelas + view).
- [x] Gate de **token** lendo `tokens.json`; `.gitignore` + `tokens.example.json`.
- [x] Endpoints: `GET /health`, `GET /ping`, `POST /fontes`, `GET /fontes`,
  `GET /fontes/{id}`, `GET /fontes/{id}/arquivo` (upload/listar/baixar PDF).
- [x] **Schema criado** no banco `u944249633_kdd` (via `migrate.php` over SSH — 9 tabelas + view).
- [x] **Deploy** em produção na Hostinger (tudo em `public_html`, sensíveis bloqueados por
  `.htaccess`). Testado: `/health` 200, `/ping` 200 com token / 401 sem, `/fontes` GET/POST,
  download de PDF, e `/.env` `/tokens.json` `/src/*` retornando **403**. Pipeline
  upload→disco→MySQL→download validado ponta a ponta.
- [x] Seed mínimo em produção (Esportes>Futebol, Jornalismo, Geografia; homônimo
  Botafogo-time × Botafogo-bairro; ponte interdisciplinar João Saldanha→bairro).
- [ ] CRUD de áreas (subárvore via CTE recursivo) e conceitos/rótulos (escrita — futuro).
- [x] `POST /fontes/{id}/mapas` (transação de ingestão; desambiguação por (rótulo+área),
  destino inline idempotente; testado com o exemplo Botafogo, re-push não duplica).
- [x] Marcar processamento (`PATCH /fontes/{id}`, valida status_proc + grava áreas) e
  `POST /fontes/{id}/aprovar` · `/reprovar`.
- [x] **Certeza por JOIN validada em produção:** pendente→0, aprovada→1, reprovada→0
  (corrigida a view: `COUNT(DISTINCT f.id)`).
- [x] **Endpoints de consulta** (`src/handlers/consulta.php`), testados em produção:
  `GET /areas` (árvore via parent_id), `GET /conceitos` (+ `?q=` busca por rótulo, `?area=`),
  `GET /conceitos/{id}` (rótulos, áreas, fontes, proposições origem/destino com certeza),
  `GET /proposicoes?conceito=` (certeza da view), `GET /constelacao` (áreas+contagem,
  pontes interdisciplinares, homônimos). Certeza **exposta como `fontes_aprovadas`** (sinal
  linear); normalização [0,1] continua adiada (decisão da fórmula).
- [ ] Testes HTTP (coleção curl) cobrindo o fluxo completo.

> **Desambiguação por SENTIDO (resolvido):** o `POST /fontes/{id}/mapas` agora identifica
> conceito por **sentido exato** (`kdd_resolver_conceito` casa em `conceito.sentido`,
> garante o rótulo e cria novo quando o sentido não existe). Removido o antigo fallback
> só-por-rótulo que fundia homônimos. A **área deixou de ser critério de identidade** (volta
> a ser só dimensão N–N de classificação). Validado em produção: empurrar "Botafogo" com 3
> sentidos distintos reaproveita os 2 existentes (time, bairro) e cria o 3º — sem fusão; e o
> re-push é idempotente. *Limitação conhecida:* dentro de **um mesmo push**, proposições
> referenciam conceitos por `rotulo`, então dois sentidos com o mesmo rótulo no mesmo PDF
> colidem nesse namespace — o bot deve evitar, ou evoluir o payload para referência por id.

### Critérios de aceite
1. Subir um PDF via `POST /fontes` deixa a fonte **pendente** e o arquivo recuperável.
2. Simular o bot: listar pendentes, baixar PDF, `PATCH` para `processando`, e
   `POST /mapas` cria conceitos/proposições/referências numa transação → `processado`.
3. `GET /proposicoes` mostra **certeza = 0** enquanto a fonte está `pendente` de aprovação;
   após `aprovar`, a certeza **sobe**; após `reprovar`, **volta a cair** — tudo via JOIN,
   sem recálculo manual.
4. Dois PDFs aprovados sustentando a mesma proposição → certeza **maior** que com um só.
5. Conceitos homônimos (Botafogo-time × bairro) coexistem como **conceitos distintos**;
   um mesmo conceito aparece em **várias áreas** (N–N).
6. `GET /areas` retorna a hierarquia (pai → filhos) corretamente.

---

## Marco 2 — Cliente PySide (consulta) [resumo]
- Conectar na API; **navegar áreas (árvore), conceitos, proposições e a constelação**.
- Exibir **scores de certeza** junto. Somente leitura nesta fase.
- Entrega: usuário enxerga o conhecimento já existente no armazém.

## Marco 3 — Bot / cérebro [resumo]
- **Fachada de IA** (interface comum) com dois back-ends: **Ollama (Qwen 3.5)** e
  **Claude Sonnet 4.6** (API Anthropic).
- Loop: lista pendentes na API → baixa PDF → extrai conceitos/proposições/áreas →
  desambigua → `POST /fontes/{id}/mapas`.
- Começa **1 PDF por vez**.

## Marco 4 — Curadoria [resumo]
- PySide ganha **fila de fontes processadas pendentes de aprovação**.
- Validador **aprova/reprova a fonte** (cascata para todas as proposições).
- Visualizar impacto na certeza.

## Marco 5 — Versionamento & refinamentos [resumo]
- **Diffs/changesets** (autor bot/humano) com histórico.
- Refino de **desambiguação** e **pontes interdisciplinares** (mesmo sentido em várias áreas).
- Reforço estrutural na certeza (v2 da fórmula).

---

## Sugestão de primeiro passo concreto
Fechar as 4 decisões técnicas (framework, migrations, storage, auth) e, em seguida,
montar o esqueleto do projeto PHP + migrations das tabelas + seed. A partir daí, os
endpoints na ordem do checklist.
