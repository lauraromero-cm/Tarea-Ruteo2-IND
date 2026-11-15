-- 05_modelo_falla.sql
-- Modelo de falla probabilistico de cada enlace ante el terremoto M8.8.
-- =====================================================================
-- Pipeline de riesgo sismico estandar (dos etapas):
--
--   (1) GMPE / ley de atenuacion  -> intensidad del movimiento (PGA) en
--       cada enlace, segun magnitud M y distancia hipocentral R:
--          Campbell (1981):
--          PGA[g] = 0.0185 * exp(1.28 M) * (R + 0.147 exp(0.732 M))^(-1.75)
--          R = sqrt( R_epi^2 + h^2 )   (R_epi = dist. en superficie al
--                                        epicentro; h = profundidad focal)
--
--   (2) Curva de fragilidad lognormal (HAZUS / FEMA) -> probabilidad de
--       falla del enlace dado el PGA:
--          P_fail = Phi( ln(PGA/mu) / beta )
--       mu   = PGA mediano que produce dano (0.30 g, postacion/cable aereo)
--       beta = dispersion logaritmica (0.55)
--
-- Referencias:
--   Campbell, K.W. (1981). Near-source attenuation of peak horizontal
--     acceleration. BSSA 71(6).
--   FEMA/NIBS HAZUS-MH, Technical Manual: fragility (lognormal) de
--     componentes de comunicaciones y lifelines.
--   Esteva & Cornell: formulacion probabilistica del peligro sismico.
--   Boettcher et al. (IEEE): fallas correlacionadas gatilladas por un evento
--     (el sismo actua como fuente comun que correlaciona las fallas por zona).

-- --- Parametros del modelo (editables) ---
DROP TABLE IF EXISTS modelo_param CASCADE;
CREATE TABLE modelo_param (clave text PRIMARY KEY, valor double precision, nota text);
INSERT INTO modelo_param VALUES
 ('mu_pga',  0.30, 'PGA mediano de falla (g) - fragilidad lognormal'),
 ('beta',    0.55, 'dispersion logaritmica de la fragilidad'),
 ('pga_min_fail', 0.02, 'PGA bajo el cual P_fail se trunca a ~0');

-- --- Funcion CDF normal estandar (aprox. Abramowitz-Stegun 7.1.26) ---
CREATE OR REPLACE FUNCTION norm_cdf(z double precision)
RETURNS double precision LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  x    double precision := abs(z)/sqrt(2.0);
  t    double precision;
  poly double precision;
  erf  double precision;
BEGIN
  t    := 1.0/(1.0 + 0.3275911*x);
  poly := ((((1.061405429*t - 1.453152027)*t + 1.421413741)*t
            - 0.284496736)*t + 0.254829592)*t;
  erf  := 1.0 - poly*exp(-x*x);          -- erf(x) para x>=0
  RETURN 0.5*(1.0 + sign(z)*erf);
END;
$$;

-- --- GMPE Campbell (1981): PGA en g a partir de M y R hipocentral (km) ---
CREATE OR REPLACE FUNCTION pga_campbell(m double precision, r_km double precision)
RETURNS double precision LANGUAGE sql IMMUTABLE AS $$
  SELECT 0.0185 * exp(1.28*m) * power(r_km + 0.147*exp(0.732*m), -1.75);
$$;

-- --- Columnas del modelo en la tabla de aristas ---
ALTER TABLE edges ADD COLUMN IF NOT EXISTS dist_epi_km double precision;
ALTER TABLE edges ADD COLUMN IF NOT EXISTS r_hipo_km   double precision;
ALTER TABLE edges ADD COLUMN IF NOT EXISTS pga_g       double precision;
ALTER TABLE edges ADD COLUMN IF NOT EXISTS p_fail      double precision;

-- --- Calculo por enlace ---
WITH s AS (SELECT geom, mag, depth_km FROM sismo LIMIT 1),
     p AS (SELECT
             max(valor) FILTER (WHERE clave='mu_pga') mu,
             max(valor) FILTER (WHERE clave='beta')   beta,
             max(valor) FILTER (WHERE clave='pga_min_fail') pmin
           FROM modelo_param),
     calc AS (
        SELECT e.id,
               ST_Distance(e.geom::geography, s.geom::geography)/1000.0 AS de,
               s.mag, s.depth_km
        FROM edges e, s
     )
UPDATE edges e SET
  dist_epi_km = c.de,
  r_hipo_km   = sqrt(c.de^2 + c.depth_km^2),
  pga_g       = pga_campbell(c.mag, sqrt(c.de^2 + c.depth_km^2)),
  p_fail      = CASE
                  WHEN pga_campbell(c.mag, sqrt(c.de^2 + c.depth_km^2)) < p.pmin
                  THEN 0.0
                  ELSE greatest(0.0, least(1.0,
                       norm_cdf( ln( pga_campbell(c.mag, sqrt(c.de^2 + c.depth_km^2)) / p.mu) / p.beta )))
                END
FROM calc c, p
WHERE c.id = e.id;

-- Tabla resumen de probabilidades de falla (solo enlaces operativos)
DROP TABLE IF EXISTS edge_failure CASCADE;
CREATE TABLE edge_failure AS
SELECT id AS edge_id, tipo, source, target,
       round(dist_epi_km::numeric,1) AS dist_epi_km,
       round(pga_g::numeric,4)       AS pga_g,
       round(p_fail::numeric,5)      AS p_fail
FROM edges
WHERE operativo
ORDER BY p_fail DESC;
ALTER TABLE edge_failure ADD PRIMARY KEY (edge_id);
