-- 010 — SENTIMENTO da proposição (docs/sentimento.md).
--
-- ⚠️ O sentimento mora na REFERÊNCIA (par proposição × fonte), não na proposição: duas
-- fontes podem afirmar a MESMA tripla com enquadramento diferente, e o enquadramento é de
-- quem afirmou. É o mesmo lugar onde a CERTEZA já vive — então reprovar uma fonte remove a
-- contribuição dela do sentimento sem recálculo, igual à certeza.
--
-- Sentimento NÃO entra na identidade: a tripla é a mesma dita com frieza ou com carga.
-- Por isso NÃO há coluna de sentimento em `proposicao`.
--
-- Dois eixos INDEPENDENTES:
--   · polaridade     (-1..+1) a relação prejudica (-) ou beneficia (+) o destino
--   · subjetividade  ( 0..1 ) 0 = fato verificável, 1 = juízo de valor
--
-- NULL = não medido (distinto de 0.00 = medido como neutro). Base existente fica NULL e o
-- valor dela NÃO muda (omissão não penaliza — ver §4 da spec).
--
-- Idempotente (MariaDB).

ALTER TABLE referencia
  ADD COLUMN IF NOT EXISTS polaridade    DECIMAL(3,2) NULL,
  ADD COLUMN IF NOT EXISTS subjetividade DECIMAL(3,2) NULL;

-- Sentimento agregado por proposição, só sobre fontes APROVADAS.
--
-- ⚠️ Mesma armadilha documentada em vw_certeza_proposicao: o agregado é sobre o lado
-- APROVADO do LEFT JOIN (f.id), não sobre r.fonte_id — senão o enquadramento de uma fonte
-- reprovada continuaria pesando na média.
--
-- `discordancia` = amplitude da polaridade entre as fontes aprovadas (max - min). Alto
-- significa que as fontes divergem no enquadramento da MESMA afirmação — informação de
-- curadoria, não ruído a esconder.
CREATE OR REPLACE VIEW vw_sentimento_proposicao AS
SELECT
  p.id                                                   AS proposicao_id,
  AVG(CASE WHEN f.id IS NOT NULL THEN r.polaridade    END) AS polaridade,
  AVG(CASE WHEN f.id IS NOT NULL THEN r.subjetividade END) AS subjetividade,
  COUNT(CASE WHEN f.id IS NOT NULL AND r.polaridade IS NOT NULL THEN 1 END) AS fontes_medidas,
  COALESCE(
    MAX(CASE WHEN f.id IS NOT NULL THEN r.polaridade END) -
    MIN(CASE WHEN f.id IS NOT NULL THEN r.polaridade END), 0
  )                                                      AS discordancia
FROM proposicao p
LEFT JOIN referencia r ON r.proposicao_id = p.id
LEFT JOIN fonte f      ON f.id = r.fonte_id AND f.status_aprovacao = 'aprovada'
GROUP BY p.id;
