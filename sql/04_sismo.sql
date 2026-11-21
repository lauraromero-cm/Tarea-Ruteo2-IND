-- 04_sismo.sql
-- Tablas del epicentro del terremoto M8.8 Maule (2010-02-27).
-- Las coordenadas NO se escriben a mano: se cargan PARSEANDO el GeoJSON del
-- catalogo USGS (data/sismo_maule_2010.geojson, evento
-- official20100227063411530_30). main.py inserta el GeoJSON crudo en la tabla
-- staging 'sismo_geojson' y 04b_sismo_extract.sql extrae los campos con
-- operadores jsonb y la geometria con ST_GeomFromGeoJSON (PostGIS).

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

-- Tabla staging: recibe el GeoJSON crudo tal como viene del USGS (lo carga
-- main.py leyendo el archivo; no se transcribe ningun valor a mano).
DROP TABLE IF EXISTS sismo_geojson CASCADE;
CREATE TABLE sismo_geojson (doc jsonb);
