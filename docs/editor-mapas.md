# Especificação — Editor Manual de Mapas (PySide)

> **Documento vivo / rascunho.** Deriva de [`especificacao.md`](especificacao.md) e
> [`plano-implementacao.md`](plano-implementacao.md). Especifica a parte **"editar"** do
> papel do cliente PySide (§2 da spec), hoje adiada — o Marco 2 entregou só leitura.
> Itens **🟡 PENDENTE** precisam de decisão do idealizador.
> Última atualização: 2026-06-22.

---

## 1. Motivação

O bot extrai mapas automaticamente, mas a extração — sobretudo com o LLM local (Qwen
7B em CPU) — produz ruído: proposições com destino órfão (`destino_rotulo` que não casa
com nenhum conceito), sentidos quase-duplicados, rótulos errados, áreas mal atribuídas.
Hoje a **única** forma de corrigir é reprovar a fonte inteira (tudo-ou-nada) e reprocessar
— grosso demais para curadoria fina.

O **editor manual** dá ao humano "mãos" sobre o armazém: corrigir, complementar e
desambiguar o conhecimento **sem** depender de um novo PDF. É a contraparte de curadoria
do papel "olhos e mãos do humano" (spec §2).

### 1.1 Escopo

✅ **No escopo:**
- Criar/editar/remover **proposições** manualmente.
- Criar conceito; editar `sentido`; gerir **rótulos** (adicionar/remover/marcar principal).
- Gerir o N–N **conceito↔área** (incluir/excluir áreas de um conceito).
- **Mesclar** dois conceitos duplicados num só (caso comum pós-extração).
- **Desambiguar** homônimos (separar sentidos colados pelo mesmo rótulo).
- CRUD de **áreas** (criar/renomear/mover na hierarquia).

❌ **Fora do escopo (por ora):**
- Editar o texto/arquivo do PDF de uma fonte (a fonte é imutável; reprocessa-se).
- Aprovar/reprovar fontes — isso é a **fila de curadoria** (Marco 4), complementar mas
  distinto deste editor.
- Edição colaborativa em tempo real / multiusuário simultâneo (ver §7 conflitos).

---

## 2. A tensão central — e como o editor a respeita

A certeza é **emergente**, não declarada: deriva no JOIN da contagem de **fontes
aprovadas** que sustentam cada proposição (spec §4.1, view `vw_certeza_proposicao`). Uma
edição humana **não é um PDF** — então, se ela criasse proposições "soltas", essas
ligações não teriam proveniência nem entrariam na conta de certeza, quebrando o princípio.

**🟢 Resolução proposta (recomendada): curadoria humana é uma _fonte_.**

Toda edição manual é atribuída a uma **fonte de curadoria** — uma `fonte` de origem
humana, sem PDF, que funciona como qualquer outra evidência:

- A proposição criada/corrigida à mão recebe uma `referencia` apontando para essa fonte
  de curadoria.
- A fonte de curadoria nasce **já aprovada** (o validador é quem edita; ver §6), então a
  proposição entra na certeza naturalmente — **sem caso especial no JOIN**.
- Remover uma proposição à mão = remover a referência da fonte de curadoria (e a
  proposição, se ficar órfã de toda referência).
- Proveniência preservada: dá para distinguir "afirmado por PDF X" de "curado pelo humano
  Y", e a certeza continua sendo convergência de evidências (humano conta como uma).

Vantagens: o modelo de certeza/proveniência permanece **uniforme** (uma proposição é
sustentada por fontes, ponto); nada de flag "is_manual" espalhada pelo JOIN.

**Alternativas consideradas (🟡 a confirmar):**
- **(B) Override autoritativo:** edição humana sobrepõe a certeza calculada (carimbo de
  verdade). — Rejeitada: contradiz frontalmente a certeza emergente (spec §3.6, Simon).
- **(C) Edição fora do modelo de fontes:** proposições manuais sem referência. — Rejeitada:
  ficariam invisíveis à certeza e à proveniência.

> **Decisão a confirmar com o idealizador:** adotar (A) "curadoria como fonte". O resto
> desta spec assume (A).

---

## 3. Impacto no modelo de dados

Mínimo, justamente porque (A) reaproveita o modelo de fontes.

- **`fonte`** ganha uma distinção de **origem**: `origem ENUM('pdf','curadoria')` (ou
  tabela/flag equivalente). `curadoria` não tem `arquivo_caminho` (NULL) e nasce
  `status_proc='processado'`, `status_aprovacao='aprovada'`.
  - 🟡 PENDENTE: uma fonte de curadoria por humano (perene, acumulativa) **ou** uma por
    sessão/changeset de edição? Recomenda-se **uma por autor humano** (simples; a auditoria
    fina fica no changeset, abaixo).
- **Versionamento (changesets, spec §4.3, ainda não implementado):** cada operação do
  editor é um **delta atribuído a um autor**. Tabela sugerida:
  ```sql
  changeset(id, autor, tipo, alvo_tipo, alvo_id, antes JSON, depois JSON, criado_em)
  ```
  Permite histórico e desfazer. Para a 1ª versão do editor pode-se entregar **auditoria
  append-only** (registrar o delta) e deixar o *undo* para depois.
- Tabelas existentes reutilizadas sem mudança: `conceito`, `rotulo`, `conceito_area`,
  `proposicao`, `referencia`, `area`, `conceito_fonte`.

**Mesclagem de conceitos** (operação nova, sem coluna nova): reaponta `rotulo`,
`conceito_area`, `proposicao` (origem e destino), `referencia`/`conceito_fonte` do conceito
B para o A, depois remove B. Deve ser **transacional** e idempotente.

---

## 4. Operações (casos de uso)

| # | Operação | Efeito no armazém |
|---|----------|-------------------|
| O1 | Criar proposição A —[rel]→ B | cria `proposicao` (se nova) + `referencia` p/ fonte de curadoria |
| O2 | Editar relação/origem/destino de uma proposição | novo `proposicao` resolvido + move a referência; remove a antiga se órfã |
| O3 | Remover proposição | apaga a referência da curadoria; apaga a `proposicao` se ficar sem referências |
| O4 | Criar conceito (sentido + rótulo + áreas) | `conceito` + `rotulo`(principal) + `conceito_area` |
| O5 | Editar `sentido` de um conceito | UPDATE `conceito.sentido` (+ changeset) |
| O6 | Gerir rótulos | INSERT/DELETE `rotulo`; marcar `principal` |
| O7 | Gerir áreas do conceito | INSERT/DELETE `conceito_area` |
| O8 | Mesclar conceito B em A | reaponta tudo de B→A; remove B (transacional) |
| O9 | Desambiguar (separar homônimos) | cria conceito novo; move rótulos/proposições selecionados para ele |
| O10 | CRUD de área | INSERT/UPDATE/DELETE `area` (valida ciclo em `parent_id`) |

**Resolução de conceito por destino:** ao criar/editar proposição, o editor deve permitir
escolher o conceito de destino **por id** (busca por rótulo+sentido na UI), eliminando a
limitação conhecida do push do bot (colisão de rótulo dentro de um payload — plano §M1).

---

## 5. Endpoints novos da API

A API hoje só escreve via ingestão (`POST /fontes/{id}/mapas`) e moderação
(`aprovar`/`reprovar`); CRUD direto de conceitos/áreas está marcado como futuro no plano.
O editor exige endpoints de escrita granular (todos exigem token; ver §6):

**Proposições**
- `POST   /proposicoes` — cria; corpo `{origem_id, relacao, destino_id}`; gera referência de curadoria. (O1)
- `PATCH  /proposicoes/{id}` — edita relação/origem/destino. (O2)
- `DELETE /proposicoes/{id}` — remove (referência + proposição órfã). (O3)

**Conceitos / rótulos / áreas do conceito**
- `POST   /conceitos` — `{sentido, rotulo_principal, areas[]}`. (O4)
- `PATCH  /conceitos/{id}` — edita `sentido`. (O5)
- `POST   /conceitos/{id}/rotulos` · `DELETE /rotulos/{id}` · `PATCH /rotulos/{id}` (principal). (O6)
- `POST   /conceitos/{id}/areas` · `DELETE /conceitos/{id}/areas/{area_id}`. (O7)
- `POST   /conceitos/{id}/merge` — `{outro_id}` mescla outro→id. (O8)
- `POST   /conceitos/{id}/split` — desambigua (move rótulos/proposições p/ conceito novo). (O9)

**Áreas**
- `POST /areas` · `PATCH /areas/{id}` · `DELETE /areas/{id}` (valida ciclo/filhos). (O10)

Todas as escritas: **transacionais**, registram **changeset**, e respondem o objeto
resultante (para a UI atualizar sem refetch geral). Reaproveitar o helper
`kdd_resolver_conceito` onde fizer sentido.

---

## 6. Perfis e permissões

Hoje o token é organizacional, não controle técnico (spec §6; qualquer token válido chama
qualquer rota). O editor mexe direto na verdade do armazém, então:

- ✅ Editar é ação de **Validador** (o curador), não de Operador. Recomenda-se que as rotas
  de escrita granular passem a **exigir perfil `validador`** — primeira vez que o perfil
  vira controle técnico de fato.
- 🟡 PENDENTE: tornar a checagem de perfil obrigatória **só** nessas rotas, mantendo o resto
  aberto, ou introduzir verificação de perfil em toda a API. Recomenda-se o escopo mínimo
  (só as rotas do editor).

---

## 7. Versionamento, auditoria e conflitos

- **Auditoria:** toda operação grava um `changeset` (autor + antes/depois). Atende a spec
  §4.3 (diffs/changesets atribuídos a autor) — começa append-only; *undo* depois.
- **Conflitos (multiusuário):** com edição por validador e operações pequenas, raro. 1ª
  versão usa **last-write-wins** + auditoria; *optimistic locking* (campo de versão por
  conceito/proposição) fica como melhoria 🟡.
- **Interação com reprovação de fonte PDF:** se uma proposição tem referência de uma fonte
  PDF *e* de curadoria, reprovar o PDF **não** a derruba (a curadoria humana ainda a
  sustenta). Isso é o comportamento desejado e cai naturalmente do modelo (A).

---

## 8. UI no cliente PySide

O cliente é hoje só leitura (`api_client.py` só tem `_get`; tabela `NoEditTriggers`). O
editor adiciona um **modo de edição** (alternável), preservando a navegação atual.

- **Painel de conceito (edição):** editar sentido; lista de rótulos (add/remover/principal);
  chips de áreas (add/remover); botões **Mesclar…** e **Desambiguar…**.
- **Painel de proposições:** tabela editável das proposições do conceito (origem fixa);
  adicionar linha (escolher relação + destino por busca), editar, remover. Mostrar a
  **certeza** ao lado e como ela muda após salvar.
- **Diálogo Mesclar:** escolhe conceito-alvo (busca por rótulo/sentido), prévia do que será
  reapontado, confirma.
- **Árvore de áreas:** menu de contexto criar/renomear/mover/excluir.
- **Feedback:** toda gravação mostra resultado e erros da API; idealmente um painel de
  histórico (changesets) por conceito.
- `api_client.py` ganha os métodos de escrita (POST/PATCH/DELETE) correspondentes ao §5.

---

## 9. Encaixe no plano de marcos

Este editor cruza **Marco 4 (curadoria)** e **Marco 5 (versionamento)**. Sugestão:

- **M4 (curadoria):** fila de fontes pendentes + aprovar/reprovar **e** as operações de
  edição O1–O3, O5–O7 (proposições, sentido, rótulos, áreas) — o grosso do valor.
- **M5 (versionamento):** changesets/undo, **merge/split** (O8/O9) e CRUD de áreas (O10),
  que são mais delicados e se beneficiam do histórico.

🟡 Confirmar com o idealizador se vira um marco próprio ("Marco 4.5 — Editor") ou se entra
fatiado em M4/M5 como acima.

---

## 10. Decisões pendentes (índice)
1. **(A) Curadoria como fonte** vs override autoritativo (§2) — *recomendado A*.
2. Granularidade da fonte de curadoria: por autor × por sessão (§3).
3. Changeset com *undo* já na v1, ou só auditoria append-only primeiro (§3, §7).
4. Perfil `validador` como controle técnico só nas rotas do editor (§6).
5. Tratamento de conflito: LWW vs optimistic locking (§7).
6. Posição no plano: marco próprio vs fatiado em M4/M5 (§9).

---

## 11. Critérios de aceite
1. Criar uma proposição à mão a deixa visível em `GET /proposicoes` **com certeza ≥ 1**
   (sustentada pela fonte de curadoria aprovada).
2. Remover essa proposição à mão **derruba** a certeza/some a ligação, via o mesmo JOIN —
   sem job de recálculo.
3. Mesclar dois conceitos duplicados reaponta **todas** as proposições/rótulos/áreas e não
   deixa órfãos; operação transacional (falha → rollback total).
4. Desambiguar separa um homônimo em dois conceitos sem perder proposições.
5. Reprovar uma fonte **PDF** não derruba proposição que também tem referência de
   **curadoria** (a humana sustenta).
6. Toda edição fica registrada (changeset com autor e antes/depois) e auditável.
7. O cliente PySide alterna entre **navegar** (leitura) e **editar** sem regressão da
   navegação atual.
