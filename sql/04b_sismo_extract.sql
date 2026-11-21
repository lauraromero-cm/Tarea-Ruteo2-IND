-- 04b_sismo_extract.sql
-- Extrae el epicentro desde el GeoJSON CRUDO (tabla staging 'sismo_geojson',
-- cargada por main.py desde data/sismo_maule_2010.geojson) usando operadores
-- jsonb y la funcion ST_GeomFromGeoJSON de PostGIS. Asi los valores provienen
-- del archivo del USGS y NO estan escritos a mano.

INSERT INTO sismo (id, lugar, mag, depth_km, fecha_utc, lon, lat, geom)
SELECT
    doc->>'id',
    doc->'properties'->>'place',
    (doc->'properties'->>'mag')::double precision,
    (doc->'geometry'->'coordinates'->>2)::double precision,     -- profundidad (km)
    to_timestamp((doc->'properties'->>'time')::bigint / 1000.0),-- epoch ms -> ts
    (doc->'geometry'->'coordinates'->>0)::double precision,      -- lon
    (doc->'geometry'->'coordinates'->>1)::double precision,      -- lat
    ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(doc->>'geometry')), 4326)
FROM sismo_geojson
ON CONFLICT (id) DO NOTHING;

CREATE INDEX IF NOT EXISTS sismo_geom_gix ON sismo USING gist (geom);

-- La tabla staging ya cumplio su proposito.
DROP TABLE IF EXISTS sismo_geojson CASCADE;
