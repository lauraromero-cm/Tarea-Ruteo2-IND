-- 03_nodos_clave.sql
-- Identificacion de los NODOS CLAVE que generan, intercambian y reciben
-- informacion en la red (enunciado, punto 2).
--
-- Criterio (justificado en docs/INFORME.md):
--   La Internet chilena tiene topologia troncal norte-sur. Los nodos que
--   concentran generacion/intercambio/recepcion de trafico son:
--     - Santiago (Region Metropolitana): sede del PIT Chile / NAP, mayor
--       concentracion de data centers y trafico nacional  -> INTERCAMBIO
--     - Capitales regionales: agregan y distribuyen el trafico de su region
--       -> GENERACION / RECEPCION
--     - Ciudades con amparo de cables submarinos / puntos extremos de la
--       troncal (Valparaiso, Arica, Punta Arenas) -> ENTRADA/SALIDA
--   El estudio de resiliencia (U. de Chile / NIC, 2018) modela los nodos de
--   la red como comunas; aqui usamos el subconjunto de comunas-capital y
--   hubs por ser los puntos criticos de generacion/intercambio/recepcion.

DROP TABLE IF EXISTS nodos_clave CASCADE;
CREATE TABLE nodos_clave (
    cod        text PRIMARY KEY,
    nombre     text,
    rol        text,              -- generacion / intercambio / recepcion
    lon        double precision,
    lat        double precision,
    geom       geometry(Point,4326),
    vertex_id  integer,           -- nodo de la topologia mas cercano
    dist_m     double precision   -- distancia de la ciudad al nodo de red
);

INSERT INTO nodos_clave (cod, nombre, rol, lon, lat) VALUES
 ('ARI','Arica','recepcion',            -70.3126,-18.4783),
 ('IQQ','Iquique','recepcion',          -70.1503,-20.2141),
 ('ANF','Antofagasta','intercambio',    -70.4000,-23.6500),
 ('CLC','Calama','recepcion',           -68.9333,-22.4667),
 ('CPO','Copiapo','recepcion',          -70.3314,-27.3665),
 ('LSC','La Serena','intercambio',      -71.2489,-29.9078),
 ('VAP','Valparaiso','intercambio',     -71.6197,-33.0472),
 ('SCL','Santiago','intercambio',       -70.6483,-33.4569),
 ('RCG','Rancagua','recepcion',         -70.7443,-34.1708),
 ('TLC','Talca','recepcion',            -71.6554,-35.4264),
 ('CCP','Concepcion','intercambio',     -73.0498,-36.8270),
 ('CLL','Chillan','recepcion',          -72.1033,-36.6066),
 ('TCO','Temuco','intercambio',         -72.5904,-38.7359),
 ('VLD','Valdivia','recepcion',         -73.2459,-39.8142),
 ('ORN','Osorno','recepcion',           -73.1333,-40.5667),
 ('PMC','Puerto Montt','intercambio',   -72.9360,-41.4717),
 ('CAS','Castro','recepcion',           -73.7667,-42.4833),
 ('COY','Coyhaique','recepcion',        -72.0667,-45.5752),
 ('PAR','Punta Arenas','intercambio',   -70.9171,-53.1638);

UPDATE nodos_clave SET geom = ST_SetSRID(ST_MakePoint(lon,lat),4326);

-- Snap de cada nodo clave al vertice MAS CERCANO de la red EN OPERACION
WITH snap AS (
    SELECT n.cod,
           v.id AS vid,
           ST_Distance(n.geom::geography, v.the_geom::geography) AS d
    FROM nodos_clave n
    CROSS JOIN LATERAL (
        SELECT ev.id, ev.the_geom
        FROM edges_vertices_pgr ev
        WHERE EXISTS (SELECT 1 FROM edges e
                      WHERE e.operativo AND (e.source=ev.id OR e.target=ev.id))
        ORDER BY n.geom <-> ev.the_geom
        LIMIT 1
    ) v
)
UPDATE nodos_clave n
SET vertex_id = snap.vid,
    dist_m    = snap.d
FROM snap WHERE snap.cod = n.cod;
