-- 009 — IDIOMA e PAÍS (docs/idioma-pais.md).
--
-- Dois problemas de natureza DIFERENTE:
--   · IDIOMA é superfície → vive no RÓTULO. Porta/Door/Puerta = UM conceito, três rótulos.
--   · PAÍS pode mudar o SENTIDO → vive na IDENTIDADE. "Imposto de Renda" (BR) e "IRS" (PT)
--     não são tradução um do outro: são institutos distintos, logo conceitos distintos.
--
-- ⚠️ SENTINELA, NÃO NULL: pais = '' significa UNIVERSAL. Com NULL o índice
-- UNIQUE(universo_id, pais, sentido) NÃO morderia — MySQL/MariaDB tratam NULLs como
-- distintos entre si, então daria para inserir duas vezes a mesma (universo, NULL, sentido)
-- e fragmentar a identidade em dois ids, justamente o que a migration 004 veio impedir.
--
-- Idempotente (MariaDB). Base existente vira idioma='pt-BR', pais='' — nada se perde.

-- ── 1. Idioma-base do universo: a língua em que os SENTIDOS daquele universo são escritos.
-- O sentido é a string de IDENTIDADE, não texto de exibição: traduzi-lo bifurcaria o
-- conceito. Por isso sentido numa língua só, e rótulos em quantas quiser (§3 da spec).
ALTER TABLE universo ADD COLUMN IF NOT EXISTS idioma VARCHAR(16) NOT NULL DEFAULT 'pt-BR';

-- ── 2. IDIOMA no rótulo (tag estilo BCP-47: pt-BR, pt-PT, en, es-AR) ──
ALTER TABLE rotulo ADD COLUMN IF NOT EXISTS idioma VARCHAR(16) NOT NULL DEFAULT 'pt-BR';
UPDATE rotulo SET idioma = 'pt-BR' WHERE idioma IS NULL OR idioma = '';

-- Unicidade passa a incluir o idioma: o MESMO texto pode repetir em idiomas diferentes
-- ("Internet" em pt-BR e en é o mesmo texto, dois rótulos do mesmo conceito).
DROP INDEX IF EXISTS uq_rotulo_conceito_texto ON rotulo;
CREATE UNIQUE INDEX IF NOT EXISTS uq_rotulo_conceito_idioma_texto
  ON rotulo (conceito_id, idioma, texto);
CREATE INDEX IF NOT EXISTS idx_rotulo_idioma ON rotulo (idioma);

-- ── 3. PAÍS no conceito — entra na IDENTIDADE (ISO 3166-1 alfa-2; '' = universal) ──
ALTER TABLE conceito ADD COLUMN IF NOT EXISTS pais CHAR(2) NOT NULL DEFAULT '';
UPDATE conceito SET pais = '' WHERE pais IS NULL;

DROP INDEX IF EXISTS uq_conceito_universo_sentido ON conceito;
CREATE UNIQUE INDEX IF NOT EXISTS uq_conceito_universo_pais_sentido
  ON conceito (universo_id, pais, sentido);
CREATE INDEX IF NOT EXISTS idx_conceito_pais ON conceito (pais);

-- ── 4. PAÍS na proposição — a mesma tripla pode valer num país e não noutro,
-- com certezas independentes (ex.: maioridade penal -> 18 anos). '' = universal.
ALTER TABLE proposicao ADD COLUMN IF NOT EXISTS pais CHAR(2) NOT NULL DEFAULT '';
UPDATE proposicao SET pais = '' WHERE pais IS NULL;

DROP INDEX IF EXISTS uq_proposicao_tripla ON proposicao;
CREATE UNIQUE INDEX IF NOT EXISTS uq_proposicao_tripla_pais
  ON proposicao (conceito_origem, relacao, conceito_destino, pais);

-- ── 5. Padrão HERDADO por fonte: um PDF da legislação brasileira ingerido com pais=BR faz
-- os conceitos dele nascerem BR, sem a IA precisar acertar isso item por item.
ALTER TABLE fonte ADD COLUMN IF NOT EXISTS idioma VARCHAR(16) NOT NULL DEFAULT 'pt-BR';
ALTER TABLE fonte ADD COLUMN IF NOT EXISTS pais   CHAR(2)     NOT NULL DEFAULT '';
