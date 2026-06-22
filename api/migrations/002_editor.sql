-- 002 — Suporte ao Editor Manual de Mapas (ver docs/editor-mapas.md)
-- Decisão (A): a curadoria humana é uma FONTE de origem 'curadoria', já aprovada.
-- Assim a proposição editada à mão ganha uma referência e entra na certeza pelo
-- mesmo JOIN, sem caso especial. Idempotente (MariaDB: IF NOT EXISTS no ADD COLUMN).

-- Origem da fonte: 'pdf' (ingestão do bot) ou 'curadoria' (edição humana)
ALTER TABLE fonte
  ADD COLUMN IF NOT EXISTS origem ENUM('pdf','curadoria') NOT NULL DEFAULT 'pdf';

-- Fonte de curadoria não tem PDF — permite caminho nulo
ALTER TABLE fonte MODIFY COLUMN arquivo_caminho VARCHAR(1024) NULL;

-- Auditoria append-only: cada operação do editor é um delta atribuído a um autor.
-- Atende ao versionamento (spec §4.3); o 'undo' fica para depois.
CREATE TABLE IF NOT EXISTS changeset (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  autor       VARCHAR(255) NOT NULL,
  perfil      VARCHAR(50)  NULL,
  acao        VARCHAR(50)  NOT NULL,
  alvo_tipo   VARCHAR(50)  NOT NULL,
  alvo_id     BIGINT       NULL,
  antes       JSON         NULL,
  depois      JSON         NULL,
  criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX IF NOT EXISTS idx_changeset_alvo ON changeset (alvo_tipo, alvo_id);
