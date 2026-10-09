-- 008 — UNIVERSOS PARALELOS (docs/universos.md).
--
-- ⚠️ INVERTE uma decisão firme: a identidade do conceito passa de `sentido` para
-- `(universo_id, sentido)`. Dentro de um universo nada muda (identidade = sentido, área
-- segue N–N sem poder de identidade); o universo é o PLANO onde a área existe.
--
-- SEGURANÇA DA MIGRAÇÃO: cria o universo 1 = 'principal' e retroalimenta TODAS as linhas
-- existentes nele. Nenhum dado se move. Trocar UNIQUE(x) por UNIQUE(universo_id, x) é seguro
-- porque tudo que era único globalmente continua único dentro do universo 1.
--
-- Idempotente (MariaDB: CREATE TABLE/INDEX IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
-- DROP INDEX IF EXISTS, INSERT IGNORE).

-- ── 1. A tabela dos universos ──
CREATE TABLE IF NOT EXISTS universo (
  id        BIGINT PRIMARY KEY AUTO_INCREMENT,
  slug      VARCHAR(64)  NOT NULL,
  nome      VARCHAR(255) NOT NULL,
  descricao TEXT NULL,
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE UNIQUE INDEX IF NOT EXISTS uq_universo_slug ON universo (slug);

-- O universo 1 existe sempre: é o default de toda requisição que não escolhe universo,
-- o que mantém desktop e bot atuais funcionando sem alteração.
INSERT IGNORE INTO universo (id, slug, nome, descricao)
VALUES (1, 'principal', 'Principal',
        'Universo padrão — recebe tudo o que existia antes dos universos paralelos.');

-- ── 2. A coluna nos três objetos que carregam identidade ──
-- rotulo/conceito_area/fonte_area/referencia/conceito_fonte NÃO ganham a coluna: herdam o
-- universo do pai. proposicao também não: deriva dos conceitos, que são do mesmo universo
-- (invariante garantida na escrita pela API).
ALTER TABLE conceito ADD COLUMN IF NOT EXISTS universo_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE area     ADD COLUMN IF NOT EXISTS universo_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE fonte    ADD COLUMN IF NOT EXISTS universo_id BIGINT NOT NULL DEFAULT 1;

-- Retroalimentação explícita (o DEFAULT já cobre o ALTER, mas isto torna a intenção
-- verificável e conserta linha que algum caminho tenha deixado em 0/NULL).
UPDATE conceito SET universo_id = 1 WHERE universo_id IS NULL OR universo_id = 0;
UPDATE area     SET universo_id = 1 WHERE universo_id IS NULL OR universo_id = 0;
UPDATE fonte    SET universo_id = 1 WHERE universo_id IS NULL OR universo_id = 0;

-- ── 3. Unicidades que passam a ser POR UNIVERSO ──
-- A identidade do conceito. Era UNIQUE(sentido) global (migration 004).
DROP INDEX IF EXISTS uq_conceito_sentido ON conceito;
CREATE UNIQUE INDEX IF NOT EXISTS uq_conceito_universo_sentido ON conceito (universo_id, sentido);

-- Chave de idempotência do remetente (migration 005): um 'aula:42' por universo.
DROP INDEX IF EXISTS uq_fonte_ref ON fonte;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fonte_universo_ref ON fonte (universo_id, ref);

-- Dedup de PDF por conteúdo (migration 003) agora é por universo: ganho de domínio — o MESMO
-- documento pode ser lido por duas lentes diferentes, uma em cada universo. Reenviar no mesmo
-- universo continua barrado.
DROP INDEX IF EXISTS uq_fonte_hash ON fonte;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fonte_universo_hash ON fonte (universo_id, arquivo_hash);

-- ── 4. Índices de busca ──
-- area(universo_id, nome) é índice COMUM, não único, de propósito: area.nome nunca foi único
-- (o dedup é SELECT-antes-de-INSERT em kdd_upsert_area), e um UNIQUE sobre dado possivelmente
-- duplicado faria esta migration falhar NO MEIO em produção — migrate.php não tem transação
-- por arquivo. Ver docs/universos.md §4.
CREATE INDEX IF NOT EXISTS idx_area_universo_nome ON area (universo_id, nome);
CREATE INDEX IF NOT EXISTS idx_conceito_universo ON conceito (universo_id);
CREATE INDEX IF NOT EXISTS idx_fonte_universo ON fonte (universo_id);

-- ── 5. FKs (depois da retroalimentação, senão linha órfã barraria a constraint) ──
-- Sem ON DELETE: apagar um universo com conteúdo tem que falhar, não cascatear.
-- ⚠️ A forma idempotente aqui é `ADD FOREIGN KEY IF NOT EXISTS <nome> (col)`.
-- `ADD CONSTRAINT IF NOT EXISTS <nome> FOREIGN KEY ...` é ERRO DE SINTAXE no MariaDB.
ALTER TABLE conceito ADD FOREIGN KEY IF NOT EXISTS fk_conceito_universo (universo_id) REFERENCES universo(id);
ALTER TABLE area     ADD FOREIGN KEY IF NOT EXISTS fk_area_universo     (universo_id) REFERENCES universo(id);
ALTER TABLE fonte    ADD FOREIGN KEY IF NOT EXISTS fk_fonte_universo    (universo_id) REFERENCES universo(id);
