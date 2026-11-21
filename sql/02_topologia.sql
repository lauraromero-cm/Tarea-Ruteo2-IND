-- 02_topologia.sql
-- Construye la tabla unificada de aristas (edges) a partir de las 4 capas
-- del levantamiento SUBTEL/NIC y genera la topologia de red con pgr_createTopology.
--
-- Tipos de tendido:
--   fibra      : fibra optica detectada  -> red EN OPERACION (transporta datos)
--   ferry      : trayecto en ferry       -> enlace maritimo (continuidad operacional)
--   postacion  : postacion electrica     -> infraestructura potencial (no operativa)
--   camino     : camino sin postacion    -> infraestructura potencial (no operativa)

DROP TABLE IF EXISTS edges CASCADE;

CREATE TABLE edges (
    id        bigserial PRIMARY KEY,
    tipo      text NOT NULL,
    operativo boolean NOT NULL,          -- true = parte de la red en operacion
    src_id    text,                      -- id original de la capa de origen
    geom      geometry(LineString, 4326),
    cost      double precision,          -- largo en metros (costo de ruteo)
    reverse_cost double precision,
    source    integer,
    target    integer,
    -- Probabilidad de falla del enlace: 0 POR DEFECTO (sin evento sismico).
    -- 05_modelo_falla.sql la actualiza con el modelo GMPE + fragilidad.
    p_fail    double precision NOT NULL DEFAULT 0
);

-- Volcamos cada capa (MultiLineString -> LineString con ST_Dump)
INSERT INTO edges (tipo, operativo, src_id, geom, cost, reverse_cost)
SELECT 'fibra', true, id::text, (ST_Dump(geom)).geom,
       ST_Length((ST_Dump(geom)).geom::geography),
       ST_Length((ST_Dump(geom)).geom::geography)
FROM fibra_optica_detectada;

INSERT INTO edges (tipo, operativo, src_id, geom, cost, reverse_cost)
SELECT 'ferry', true, id::text, (ST_Dump(geom)).geom,
       ST_Length((ST_Dump(geom)).geom::geography),
       ST_Length((ST_Dump(geom)).geom::geography)
FROM trayecto_en_ferry;

INSERT INTO edges (tipo, operativo, src_id, geom, cost, reverse_cost)
SELECT 'postacion', false, id::text, (ST_Dump(geom)).geom,
       ST_Length((ST_Dump(geom)).geom::geography),
       ST_Length((ST_Dump(geom)).geom::geography)
FROM postacion_electrica_detectada;

INSERT INTO edges (tipo, operativo, src_id, geom, cost, reverse_cost)
SELECT 'camino', false, id::text, (ST_Dump(geom)).geom,
       ST_Length((ST_Dump(geom)).geom::geography),
       ST_Length((ST_Dump(geom)).geom::geography)
FROM camino_sin_postacion_detectado;

CREATE INDEX edges_geom_gix ON edges USING gist (geom);
CREATE INDEX edges_source_idx ON edges (source);
CREATE INDEX edges_target_idx ON edges (target);
CREATE INDEX edges_tipo_idx   ON edges (tipo);

-- Topologia: genera la tabla edges_vertices_pgr y rellena source/target.
-- Tolerancia en grados (~0.005 deg ~= 555 m) para unir extremos digitalizados
-- manualmente que no coinciden exactamente (hueco tipico de digitalizacion).
-- Se calibro probando 0.001..0.02: 0.005 une huecos sin fusionar nodos
-- distintos (ver docs/INFORME.md).
SELECT pgr_createTopology('edges', 0.005::double precision, 'geom', 'id');

-- Grado de cada vertice (para identificar nodos de intercambio)
ALTER TABLE edges_vertices_pgr ADD COLUMN IF NOT EXISTS grado integer;
UPDATE edges_vertices_pgr v
SET grado = (SELECT count(*) FROM edges e WHERE e.source=v.id OR e.target=v.id);
