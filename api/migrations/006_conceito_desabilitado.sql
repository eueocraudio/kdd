-- 006 — desabilitar CONCEITO. Ao desabilitar (desabilitado=1), as PROPOSIÇÕES que o
-- envolvem (como origem OU destino) ficam inativas por CÁLCULO — não se apaga nada, e
-- reabilitar reverte. O mapa (GET /fontes/{id}/mapa) marca conceitos e relações
-- desabilitados. Idempotente (MariaDB: ADD COLUMN IF NOT EXISTS).
ALTER TABLE conceito ADD COLUMN IF NOT EXISTS desabilitado TINYINT NOT NULL DEFAULT 0;
