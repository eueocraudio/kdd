-- 003 — Dedup de PDF por hash: guarda o SHA-256 do arquivo e impede reenvio/reprocesso
-- do mesmo conteúdo. Idempotente (MariaDB). Fontes de curadoria não têm arquivo → hash NULL
-- (o índice único permite múltiplos NULL).

ALTER TABLE fonte
  ADD COLUMN IF NOT EXISTS arquivo_hash CHAR(64) NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fonte_hash ON fonte (arquivo_hash);
