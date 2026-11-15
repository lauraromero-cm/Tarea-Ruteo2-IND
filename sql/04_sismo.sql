-- 04_sismo.sql
-- Carga del epicentro del terremoto M8.8 Maule (2010-02-27), obtenido del
-- catalogo USGS en formato GeoJSON (data/sismo_maule_2010.geojson).
-- El GeoJSON completo tambien se carga como registro para trazabilidad.

DROP TABLE IF EXISTS sismo CASCADE;
CREATE TABLE sismo (
    id        text PRIMARY KEY,
    lugar     text,
    mag       double precision,   -- magnitud Mw
    depth_km  double precision,   -- profundidad focal
    fecha_utc timestamptz,
    lon       double precision,
    lat       double precision,
    geom      geometry(Point,4326)
);

INSERT INTO sismo (id, lugar, mag, depth_km, fecha_utc, lon, lat, geom) VALUES
 ('official20100227063411530_30', '2010 Maule, Chile Earthquake',
  8.8, 22.9, '2010-02-27 06:34:11.530+00', -72.898, -36.122,
  ST_SetSRID(ST_MakePoint(-72.898,-36.122),4326));

CREATE INDEX sismo_geom_gix ON sismo USING gist (geom);
