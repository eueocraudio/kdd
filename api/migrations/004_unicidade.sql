-- 004 — Unicidade estrutural das invariantes do domínio.
-- Até aqui a "identidade = sentido" (e a não-duplicação de rótulos/triplas) era
-- só best-effort na aplicação (SELECT-depois-INSERT, sujeito a TOCTOU sob
-- concorrência bot × curador). Estes índices UNIQUE tornam a invariante uma
-- garantia do banco. Idempotente (MariaDB: CREATE ... IF NOT EXISTS).
--
-- ⚠️ PRÉ-REQUISITO: a base NÃO pode ter duplicatas, senão o CREATE falha. O código
-- sempre desduplicou por SELECT antes de inserir, então bases normais passam. Se
-- desconfiar, rode antes as verificações abaixo (devem retornar 0 linhas):
--
--   SELECT sentido, COUNT(*) c FROM conceito GROUP BY sentido HAVING c > 1;
--   SELECT conceito_id, texto, COUNT(*) c FROM rotulo GROUP BY conceito_id, texto HAVING c > 1;
--   SELECT conceito_origem, relacao, conceito_destino, COUNT(*) c
--     FROM proposicao GROUP BY conceito_origem, relacao, conceito_destino HAVING c > 1;

-- Identidade do conceito é o SENTIDO (Novak/spec): um sentido, um conceito.
CREATE UNIQUE INDEX IF NOT EXISTS uq_conceito_sentido ON conceito (sentido);

-- Um rótulo não se repete dentro do mesmo conceito.
CREATE UNIQUE INDEX IF NOT EXISTS uq_rotulo_conceito_texto ON rotulo (conceito_id, texto);

-- A proposição é a tripla (origem, relacao, destino): não duplica.
CREATE UNIQUE INDEX IF NOT EXISTS uq_proposicao_tripla
  ON proposicao (conceito_origem, relacao, conceito_destino);
