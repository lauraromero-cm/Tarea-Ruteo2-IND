-- 00_pgr_createtopology_compat.sql
-- Funcion de compatibilidad pgr_createTopology para pgRouting 4.x
-- ---------------------------------------------------------------
-- pgRouting 4.0 ELIMINO la funcion pgr_createTopology (ver notas de
-- migracion 3.x -> 4.0: las funciones "deprecated" de topologia fueron
-- retiradas y reemplazadas por pgr_extractVertices).
-- Como el enunciado exige construir la topologia con pgr_createTopology,
-- reimplementamos aqui una funcion con esa MISMA firma y comportamiento:
--   * genera la tabla <tabla>_vertices_pgr con los nodos de la red
--   * rellena las columnas source/target de la tabla de aristas
--   * usa una tolerancia (en grados) para unir extremos que no coinciden
--     exactamente, igual que el pgr_createTopology clasico.
-- El snapping por tolerancia se hace con ST_ClusterDBSCAN (eps = tolerancia),
-- que agrupa los extremos cercanos en un mismo nodo.

CREATE OR REPLACE FUNCTION pgr_createTopology(
    edge_table  text,
    tolerance   double precision,
    the_geom    text DEFAULT 'geom',
    id          text DEFAULT 'id',
    source      text DEFAULT 'source',
    target      text DEFAULT 'target',
    rows_where  text DEFAULT 'true',
    clean       boolean DEFAULT false
) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
    vtable text := edge_table || '_vertices_pgr';
    sql    text;
    nver   bigint;
    nedg   bigint;
BEGIN
    -- 1. Reset columnas source/target
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS %I integer', edge_table, source);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS %I integer', edge_table, target);
    EXECUTE format('UPDATE %I SET %I = NULL, %I = NULL', edge_table, source, target);

    -- 2. Reunir todos los extremos de las aristas (inicio y fin)
    DROP TABLE IF EXISTS _pgr_endpoints;
    EXECUTE format($f$
        CREATE TEMP TABLE _pgr_endpoints AS
        SELECT %1$I AS eid, 'S'::text AS ori, ST_StartPoint(%2$I) AS pt FROM %3$I WHERE %2$I IS NOT NULL
        UNION ALL
        SELECT %1$I AS eid, 'E'::text AS ori, ST_EndPoint(%2$I)   AS pt FROM %3$I WHERE %2$I IS NOT NULL
    $f$, id, the_geom, edge_table);

    -- 3. Clustering por tolerancia: cada grupo de extremos cercanos = un nodo
    DROP TABLE IF EXISTS _pgr_clustered;
    EXECUTE format($f$
        CREATE TEMP TABLE _pgr_clustered AS
        SELECT eid, ori, pt,
               ST_ClusterDBSCAN(pt, eps := %L, minpoints := 1) OVER () AS cid
        FROM _pgr_endpoints
    $f$, tolerance);

    -- 4. Construir la tabla de vertices (id = cluster + 1, geometria = centroide)
    EXECUTE format('DROP TABLE IF EXISTS %I CASCADE', vtable);
    EXECUTE format($f$
        CREATE TABLE %1$I (
            id       bigserial PRIMARY KEY,
            cnt      integer,
            chk      integer,
            ein      integer,
            eout     integer,
            the_geom geometry(Point,4326),
            x        double precision,
            y        double precision
        )
    $f$, vtable);
    EXECUTE format($f$
        INSERT INTO %1$I (id, cnt, the_geom, x, y)
        SELECT cid + 1,
               count(*),
               ST_SetSRID(ST_Centroid(ST_Collect(pt)),4326),
               ST_X(ST_Centroid(ST_Collect(pt))),
               ST_Y(ST_Centroid(ST_Collect(pt)))
        FROM _pgr_clustered
        GROUP BY cid
    $f$, vtable);
    EXECUTE format('SELECT setval(pg_get_serial_sequence(%L,''id''), (SELECT max(id) FROM %I))', vtable, vtable);
    EXECUTE format('CREATE INDEX %I ON %I USING gist (the_geom)', vtable||'_geom_gix', vtable);

    -- 5. Rellenar source/target de cada arista
    EXECUTE format($f$
        UPDATE %1$I e SET %2$I = c.cid + 1
        FROM _pgr_clustered c WHERE c.eid = e.%3$I AND c.ori='S'
    $f$, edge_table, source, id);
    EXECUTE format($f$
        UPDATE %1$I e SET %2$I = c.cid + 1
        FROM _pgr_clustered c WHERE c.eid = e.%3$I AND c.ori='E'
    $f$, edge_table, target, id);

    EXECUTE format('SELECT count(*) FROM %I', vtable) INTO nver;
    EXECUTE format('SELECT count(*) FROM %I WHERE %I IS NOT NULL AND %I IS NOT NULL',
                   edge_table, source, target) INTO nedg;

    DROP TABLE IF EXISTS _pgr_endpoints;
    DROP TABLE IF EXISTS _pgr_clustered;

    RETURN format('OK: %s vertices, %s aristas con source/target (tabla %s)', nver, nedg, vtable);
END;
$$;
