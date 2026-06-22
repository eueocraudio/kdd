-- =====================================================================
-- KDD — Marco 1: esquema do armazém (MySQL / InnoDB / utf8mb4)
-- Rodar no phpMyAdmin, dentro do banco u944249633_kdd.
-- =====================================================================

SET NAMES utf8mb4;

-- Áreas hierárquicas (parent_id auto-referenciado)
CREATE TABLE IF NOT EXISTS area (
  id        BIGINT PRIMARY KEY AUTO_INCREMENT,
  nome      VARCHAR(255) NOT NULL,
  parent_id BIGINT NULL,
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_area_parent FOREIGN KEY (parent_id) REFERENCES area(id),
  INDEX idx_area_parent (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Conceito: identidade no nível do SENTIDO
CREATE TABLE IF NOT EXISTS conceito (
  id        BIGINT PRIMARY KEY AUTO_INCREMENT,
  sentido   VARCHAR(500) NOT NULL,
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Rótulos/sinônimos de um conceito (N rótulos por sentido)
CREATE TABLE IF NOT EXISTS rotulo (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  conceito_id BIGINT NOT NULL,
  texto       VARCHAR(255) NOT NULL,
  principal   BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT fk_rotulo_conceito FOREIGN KEY (conceito_id) REFERENCES conceito(id),
  INDEX idx_rotulo_conceito (conceito_id),
  INDEX idx_rotulo_texto (texto)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- N–N conceito <-> área
CREATE TABLE IF NOT EXISTS conceito_area (
  conceito_id BIGINT NOT NULL,
  area_id     BIGINT NOT NULL,
  PRIMARY KEY (conceito_id, area_id),
  CONSTRAINT fk_ca_conceito FOREIGN KEY (conceito_id) REFERENCES conceito(id),
  CONSTRAINT fk_ca_area     FOREIGN KEY (area_id)     REFERENCES area(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Fonte (PDF). Dois status: processamento e aprovação.
CREATE TABLE IF NOT EXISTS fonte (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  titulo           VARCHAR(500),
  arquivo_caminho  VARCHAR(1024) NOT NULL,   -- nome do arquivo dentro de storage/pdfs
  status_proc      ENUM('pendente','processando','processado','erro')
                     NOT NULL DEFAULT 'pendente',
  status_aprovacao ENUM('pendente','aprovada','reprovada')
                     NOT NULL DEFAULT 'pendente',
  enviado_por      BIGINT NULL,
  criado_em        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_fonte_status_proc (status_proc),
  INDEX idx_fonte_status_aprov (status_aprovacao)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- N–N fonte <-> área (área inferida pelo bot)
CREATE TABLE IF NOT EXISTS fonte_area (
  fonte_id BIGINT NOT NULL,
  area_id  BIGINT NOT NULL,
  PRIMARY KEY (fonte_id, area_id),
  CONSTRAINT fk_fa_fonte FOREIGN KEY (fonte_id) REFERENCES fonte(id),
  CONSTRAINT fk_fa_area  FOREIGN KEY (area_id)  REFERENCES area(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Proposição: conceito_origem -[relacao]-> conceito_destino (pode cruzar áreas)
CREATE TABLE IF NOT EXISTS proposicao (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  conceito_origem  BIGINT NOT NULL,
  relacao          VARCHAR(255) NOT NULL,
  conceito_destino BIGINT NOT NULL,
  criado_em        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_prop_origem  FOREIGN KEY (conceito_origem)  REFERENCES conceito(id),
  CONSTRAINT fk_prop_destino FOREIGN KEY (conceito_destino) REFERENCES conceito(id),
  INDEX idx_prop_origem (conceito_origem),
  INDEX idx_prop_destino (conceito_destino)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Referência: evidência de que uma fonte sustenta uma proposição.
-- A VALIDADE vem do status_aprovacao da FONTE (aprovação por fonte, tudo-ou-nada).
CREATE TABLE IF NOT EXISTS referencia (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  proposicao_id BIGINT NOT NULL,
  fonte_id      BIGINT NOT NULL,
  criado_em     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_ref (proposicao_id, fonte_id),
  CONSTRAINT fk_ref_prop  FOREIGN KEY (proposicao_id) REFERENCES proposicao(id),
  CONSTRAINT fk_ref_fonte FOREIGN KEY (fonte_id)      REFERENCES fonte(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Proveniência de conceito (qual fonte introduziu o conceito)
CREATE TABLE IF NOT EXISTS conceito_fonte (
  conceito_id BIGINT NOT NULL,
  fonte_id    BIGINT NOT NULL,
  PRIMARY KEY (conceito_id, fonte_id),
  CONSTRAINT fk_cf_conceito FOREIGN KEY (conceito_id) REFERENCES conceito(id),
  CONSTRAINT fk_cf_fonte    FOREIGN KEY (fonte_id)    REFERENCES fonte(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Certeza por JOIN: nº de fontes APROVADAS que sustentam cada proposição (linear).
-- Reforço estrutural (caminhos corroborantes) entra numa v2.
-- IMPORTANTE: o COUNT é sobre f.id (lado da fonte APROVADA do LEFT JOIN),
-- não sobre r.fonte_id — senão referências de fontes pendentes/reprovadas
-- continuariam contando (reprovar deixaria de derrubar a certeza).
CREATE OR REPLACE VIEW vw_certeza_proposicao AS
SELECT
  p.id                  AS proposicao_id,
  COUNT(DISTINCT f.id)  AS fontes_aprovadas,
  COUNT(DISTINCT f.id)  AS certeza_bruta
FROM proposicao p
LEFT JOIN referencia r ON r.proposicao_id = p.id
LEFT JOIN fonte f      ON f.id = r.fonte_id AND f.status_aprovacao = 'aprovada'
GROUP BY p.id;
