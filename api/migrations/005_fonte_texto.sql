-- 005 — Ingestão de TEXTO com contexto (fonte não-PDF vinda de um site externo, ex.: o
-- cursohacker manda descrição + transcrição sob o contexto = nome do curso). Idempotente
-- (MariaDB: ADD COLUMN / CREATE INDEX IF NOT EXISTS).
--
--  · fonte.contexto — a "lente"/área-raiz da fonte (ex.: nome do curso). O bot adiciona as
--    áreas ACHADAS no texto; a raiz é o contexto (criado já na ingestão em POST /fontes/texto).
--  · fonte.ref — chave de idempotência do REMETENTE (ex.: "aula:<id>"). Reenvio do mesmo ref
--    ATUALIZA o texto e reprocessa, em vez de duplicar (índice único; múltiplos NULL para as
--    fontes de PDF/curadoria, que não têm ref).

ALTER TABLE fonte
  ADD COLUMN IF NOT EXISTS contexto VARCHAR(500) NULL,
  ADD COLUMN IF NOT EXISTS ref      VARCHAR(191) NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fonte_ref ON fonte (ref);
