-- 011 — RELAÇÃO EM INGLÊS: substrato para análise léxica (docs/sentimento.md).
--
-- POR QUÊ: análise de sentimento em português tem pouca base e erra muito. As bases, léxicos
-- e modelos maduros são em INGLÊS. Então a proposição é TRADUZIDA e o sentimento é medido
-- sobre a forma inglesa, não sobre o português.
--
-- `relacao_en` é a forma canônica em inglês do verbo da relação ("explora" -> "exploits").
-- Serve a DOIS fins:
--   1. substrato do sentimento (polaridade/subjetividade medidas em inglês);
--   2. classificação da relação (taxonômica/vaga) independente do idioma da fonte — hoje o
--      léxico de valor.php é só pt-BR, o que quebraria num universo em inglês.
--
-- NULL = sem tradução. Nesse caso o sentimento sai **não medido**, NUNCA "neutro":
-- fabricar neutro esconderia a ausência de análise.
--
-- Idempotente (MariaDB).

ALTER TABLE proposicao ADD COLUMN IF NOT EXISTS relacao_en VARCHAR(191) NULL;
CREATE INDEX IF NOT EXISTS idx_proposicao_relacao_en ON proposicao (relacao_en);
