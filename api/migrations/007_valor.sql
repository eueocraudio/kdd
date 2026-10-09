-- 007 — valor do conhecimento, esteios e camada vetorial (docs/valor-conhecimento.md).
-- Idempotente (MariaDB: ADD COLUMN / CREATE TABLE IF NOT EXISTS; CREATE OR REPLACE VIEW).

-- Tipo grosso do conceito (entidade | classe | processo | atributo | outro). NULL = desconhecido.
-- Preenchido pela IA na extração (só quando NULL) e corrigível no editor.
ALTER TABLE conceito ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) NULL;

-- Grau de cada conceito no grafo: base do "esteio" (quanto mais relações, mais pilar).
CREATE OR REPLACE VIEW vw_grau_conceito AS
SELECT
  c.id AS conceito_id,
  (SELECT COUNT(*) FROM proposicao p WHERE p.conceito_origem  = c.id) AS grau_saida,
  (SELECT COUNT(*) FROM proposicao p WHERE p.conceito_destino = c.id) AS grau_entrada,
  (SELECT COUNT(*) FROM conceito_fonte cf WHERE cf.conceito_id = c.id) AS fontes
FROM conceito c;

-- Embeddings (vetores) de alvos do armazém. Hoje só alvo_tipo='conceito'.
-- Vetor em JSON (a Hostinger não tem tipo VECTOR); a similaridade é calculada no bot.
CREATE TABLE IF NOT EXISTS embedding (
  alvo_tipo     VARCHAR(20)  NOT NULL,
  alvo_id       BIGINT       NOT NULL,
  modelo        VARCHAR(100) NOT NULL,
  dim           INT          NOT NULL,
  vetor         LONGTEXT     NOT NULL,
  atualizado_em TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (alvo_tipo, alvo_id, modelo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Pares de conceitos semelhantes (cosseno), recalculados pelo bot a cada passada.
-- Convenção: conceito_a < conceito_b.
CREATE TABLE IF NOT EXISTS conceito_similar (
  conceito_a    BIGINT        NOT NULL,
  conceito_b    BIGINT        NOT NULL,
  modelo        VARCHAR(100)  NOT NULL,
  similaridade  DECIMAL(6,5)  NOT NULL,
  calculado_em  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (conceito_a, conceito_b, modelo),
  INDEX idx_similar_b (conceito_b),
  CONSTRAINT fk_sim_a FOREIGN KEY (conceito_a) REFERENCES conceito(id) ON DELETE CASCADE,
  CONSTRAINT fk_sim_b FOREIGN KEY (conceito_b) REFERENCES conceito(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
