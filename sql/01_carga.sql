-- 01_carga.sql
-- Habilita las extensiones espaciales y de ruteo.
-- La carga de los shapefiles (data/shp/*.shp) la realiza main.py con shp2pgsql
-- (o scripts/cargar_datos.py), porque shp2pgsql genera el SQL de insercion.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;
