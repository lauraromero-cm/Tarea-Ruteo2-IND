#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py - Punto de entrada del proyecto de resiliencia de la Internet chilena.

Permite:
  (1) cargar la BD  : extensiones, shapefiles, topologia (pgr_createTopology),
                      nodos clave, sismo y modelo de falla (main.sql).
  (2) calcular ATTR : antes y despues del terremoto M8.8 (Monte Carlo).
  (3) mostrar mapa  : servidor Flask + Leaflet con los enlaces, el daño del
                      sismo y los ATTR (antes/despues).

Uso:
  python main.py initdb        # construye toda la base de datos
  python main.py attr [-n N]   # calcula y muestra los ATTR
  python main.py serve         # levanta el mapa web (http://127.0.0.1:5000)
  python main.py all           # initdb + attr + serve

Conexion: variable de entorno RESIL_DSN
  (por defecto: host=localhost port=5432 user=postgres password=postgres dbname=resiliencia)
"""
import os, sys, json, subprocess, argparse
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
SQLDIR = os.path.join(HERE, "sql")
SHPDIR = os.path.join(HERE, "data", "shp")
GEOJSON_SISMO = os.path.join(HERE, "data", "sismo_maule_2010.geojson")

DBNAME = os.environ.get("RESIL_DB", "resiliencia")
# DSN para conectarse a la BD del proyecto. Por defecto apunta a una instalacion
# estandar (localhost:5432, rol postgres con password 'postgres' segun el README),
# de modo que `python3 main.py all` funcione desde un clon limpio sin exportar
# variables. Se puede sobreescribir con la variable de entorno RESIL_DSN.
DSN = os.environ.get("RESIL_DSN",
    f"host=localhost port=5432 user=postgres password=postgres dbname={DBNAME}")
# DSN de mantenimiento (para crear la BD) -> misma conexion pero db 'postgres'
ADMIN_DSN = os.environ.get("RESIL_ADMIN_DSN",
    "host=localhost port=5432 user=postgres password=postgres dbname=postgres")

LAYERS = [
    "fibra_optica_detectada",
    "postacion_electrica_detectada",
    "camino_sin_postacion_detectado",
    "trayecto_en_ferry",
]

def _psql_args(dsn):
    """Convierte un DSN keyword en argumentos de psql."""
    kv = dict(tok.split("=", 1) for tok in dsn.split())
    args = []
    if "host" in kv: args += ["-h", kv["host"]]
    if "port" in kv: args += ["-p", kv["port"]]
    if "user" in kv: args += ["-U", kv["user"]]
    if "dbname" in kv: args += ["-d", kv["dbname"]]
    return args

def _psql_env(dsn):
    """Si el DSN trae password=..., se lo pasa a psql via PGPASSWORD
    (psql no acepta la password como argumento de linea de comando)."""
    kv = dict(tok.split("=", 1) for tok in dsn.split())
    env = os.environ.copy()
    if "password" in kv:
        env["PGPASSWORD"] = kv["password"]
    return env

def run_sql_file(path, dsn=DSN):
    print(f"  -> {os.path.basename(path)}")
    subprocess.run(["psql", *_psql_args(dsn), "-q", "-v", "ON_ERROR_STOP=1",
                    "-f", path], env=_psql_env(dsn), check=True)

def run_sql(sql, dsn=DSN):
    subprocess.run(["psql", *_psql_args(dsn), "-q", "-v", "ON_ERROR_STOP=1",
                    "-c", sql], env=_psql_env(dsn), check=True)

# ---------------------------------------------------------------- sismo
def cargar_sismo():
    """Carga el epicentro PARSEANDO el GeoJSON del USGS (no se escriben las
    coordenadas a mano):
      1. 04_sismo.sql crea la tabla 'sismo' y la staging 'sismo_geojson'.
      2. Se lee el archivo data/sismo_maule_2010.geojson y se inserta su
         contenido CRUDO en 'sismo_geojson' (jsonb).
      3. 04b_sismo_extract.sql extrae id/mag/profundidad/fecha/coordenadas con
         operadores jsonb y la geometria con ST_GeomFromGeoJSON (PostGIS)."""
    run_sql_file(os.path.join(SQLDIR, "04_sismo.sql"))
    with open(GEOJSON_SISMO, encoding="utf-8") as f:
        doc = f.read()
    con = psycopg2.connect(DSN); cur = con.cursor()
    cur.execute("DELETE FROM sismo_geojson")
    cur.execute("INSERT INTO sismo_geojson(doc) VALUES (%s)", (doc,))
    con.commit(); con.close()
    run_sql_file(os.path.join(SQLDIR, "04b_sismo_extract.sql"))

# ---------------------------------------------------------------- initdb
def initdb():
    print("[1/7] Creando base de datos y extensiones...")
    try:
        run_sql(f"CREATE DATABASE {DBNAME};", dsn=ADMIN_DSN)
    except subprocess.CalledProcessError:
        print("      (la base ya existe, se reutiliza)")
    run_sql_file(os.path.join(SQLDIR, "01_carga.sql"))
    run_sql_file(os.path.join(SQLDIR, "00_pgr_createtopology_compat.sql"))

    print("[2/7] Cargando shapefiles con shp2pgsql...")
    for lyr in LAYERS:
        shp = os.path.join(SHPDIR, lyr + ".shp")
        # Se dropea la tabla aparte (en vez de usar "-d" de shp2pgsql) porque
        # en PostGIS >= 3.5 el DropGeometryColumn que genera "-d" lanza error
        # si la tabla todavia no existe.
        run_sql(f'DROP TABLE IF EXISTS "{lyr}" CASCADE;')
        sqlgen = subprocess.run(["shp2pgsql", "-I", "-s", "4326", "-c", shp, lyr],
                                capture_output=True, text=True, check=True)
        p = subprocess.run(["psql", *_psql_args(DSN), "-q", "-v", "ON_ERROR_STOP=1"],
                           input=sqlgen.stdout, text=True, env=_psql_env(DSN))
        if p.returncode != 0:
            sys.exit(f"Fallo cargando {lyr}")
        print(f"  -> {lyr}")

    print("[3/7] Construyendo topologia de red (pgr_createTopology)...")
    run_sql_file(os.path.join(SQLDIR, "02_topologia.sql"))
    print("[4/7] Identificando nodos clave...")
    run_sql_file(os.path.join(SQLDIR, "03_nodos_clave.sql"))
    print("[5/7] Cargando sismo M8.8 desde GeoJSON (USGS)...")
    cargar_sismo()
    print("[6/7] Aplicando modelo de falla (probabilidades por enlace)...")
    run_sql_file(os.path.join(SQLDIR, "05_modelo_falla.sql"))
    print("[7/7] Probabilidades calculadas en vivo en la BD.")
    print("      (main.sql es el entregable autocontenido equivalente: la misma")
    print("       infraestructura + probabilidades, cargable en una BD vacia.)")
    print("Base de datos construida OK.")

# ---------------------------------------------------------------- attr
def attr(trials=5000):
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "scripts", "attr.py"),
                    "-n", str(trials),
                    "--json", os.path.join(HERE, "data", "attr_resultados.json")],
                   check=True, env={**os.environ, "RESIL_DSN": DSN})

def leer_attr():
    con = psycopg2.connect(DSN); cur = con.cursor()
    cur.execute("SELECT resultado FROM attr_resultados ORDER BY id DESC LIMIT 1")
    row = cur.fetchone(); con.close()
    return row[0] if row else None

# ---------------------------------------------------------------- serve
def serve(host="127.0.0.1", port=5000):
    from flask import Flask, jsonify, render_template
    app = Flask(__name__, template_folder=os.path.join(HERE, "templates"))

    def q_geojson(sql):
        con = psycopg2.connect(DSN); cur = con.cursor()
        cur.execute(sql); feats = [r[0] for r in cur.fetchall()]; con.close()
        return {"type": "FeatureCollection", "features": feats}

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/edges")
    def api_edges():
        # Solo red en operacion; incluye p_fail para colorear el daño.
        return jsonify(q_geojson("""
            SELECT jsonb_build_object(
                'type','Feature',
                'geometry', ST_AsGeoJSON(geom)::jsonb,
                'properties', jsonb_build_object(
                    'id', id, 'tipo', tipo,
                    'p_fail', round(COALESCE(p_fail,0)::numeric,4),
                    'dist_epi_km', round(COALESCE(dist_epi_km,0)::numeric,1)))
            FROM edges WHERE operativo"""))

    @app.route("/api/edges_sinteticos")
    def api_edges_sinteticos():
        return jsonify(q_geojson("""
            SELECT jsonb_build_object(
                'type','Feature',
                'geometry', ST_AsGeoJSON(geom)::jsonb,
                'properties', jsonb_build_object(
                    'id', id, 'tipo', tipo))
            FROM edges WHERE NOT operativo"""))

    @app.route("/api/nodos")
    def api_nodos():
        return jsonify(q_geojson("""
            SELECT jsonb_build_object(
                'type','Feature',
                'geometry', ST_AsGeoJSON(geom)::jsonb,
                'properties', jsonb_build_object(
                    'cod',cod,'nombre',nombre,'rol',rol,'vertex_id',vertex_id))
            FROM nodos_clave"""))

    @app.route("/api/sismo")
    def api_sismo():
        return jsonify(q_geojson("""
            SELECT jsonb_build_object(
                'type','Feature',
                'geometry', ST_AsGeoJSON(geom)::jsonb,
                'properties', jsonb_build_object(
                    'lugar',lugar,'mag',mag,'depth_km',depth_km,
                    'fecha', fecha_utc::text))
            FROM sismo"""))

    @app.route("/api/attr")
    def api_attr():
        r = leer_attr()
        return jsonify(r if r else {"error": "ejecute: python main.py attr"})

    print(f"Mapa en http://{host}:{port}  (Ctrl+C para salir)")
    app.run(host=host, port=port, debug=False)

# ---------------------------------------------------------------- cli
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Resiliencia Internet chilena - Tarea 2")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("initdb")
    pa = sub.add_parser("attr"); pa.add_argument("-n", "--trials", type=int, default=5000)
    ps = sub.add_parser("serve"); ps.add_argument("--host", default="127.0.0.1"); ps.add_argument("--port", type=int, default=5000)
    pall = sub.add_parser("all"); pall.add_argument("-n", "--trials", type=int, default=5000)
    args = ap.parse_args()

    if args.cmd == "initdb":
        initdb()
    elif args.cmd == "attr":
        attr(args.trials)
    elif args.cmd == "serve":
        serve(args.host, args.port)
    elif args.cmd == "all":
        initdb(); attr(args.trials); serve()
    else:
        ap.print_help()
