# Tarea 2 — Resiliencia de la Internet chilena ante un sismo M8.8

Modelo de red de la infraestructura de fibra óptica chilena (datos SUBTEL/NIC,
proyecto *Yafún* / estudio CORFO 15BPE-47225) sobre **PostgreSQL + PostGIS +
pgRouting**, con cálculo del **ATTR** (*Average Two-Terminal Reliability*,
fiabilidad promedio de dos terminales; Boettcher et al., IEEE 2018) de la red
antes y después del terremoto **M8.8 del Maule (2010)**, y visualización web en
**Leaflet**.

## Requisitos

- PostgreSQL 14+ con **PostGIS** y **pgRouting**
- `shp2pgsql` (viene con PostGIS)
- Python 3.10+ con: `psycopg2`, `flask` (ver `requirements.txt`)

## Datos incluidos (`data/`)

| Archivo | Descripción |
|---|---|
| `shp/fibra_optica_detectada.*` | Tendidos de fibra óptica (red en operación) |
| `shp/postacion_electrica_detectada.*` | Postación eléctrica (infraestructura potencial) |
| `shp/camino_sin_postacion_detectado.*` | Caminos sin postación (potencial) |
| `shp/trayecto_en_ferry.*` | Enlaces marítimos en ferry (operación) |
| `sismo_maule_2010.geojson` | Sismo M8.8 Maule, descargado de **USGS** |

## Dos formas de ejecutar (elige una)

| Opción | Cuándo usarla | Comando |
|---|---|---|
| **A. Local (`main.py`)** (recomendada) | Tienes PostgreSQL+PostGIS+pgRouting | `python3 main.py all` (ver pasos abajo) |
| **B. Docker** (alternativa) | No quieres instalar nada en el host | `docker compose up --build` |

Ambas construyen la BD, calculan los ATTR (antes y después) y levantan el mapa
en `http://localhost:5000`. **La vía recomendada y verificada es `main.py`**: un
solo comando reconstruye todo desde cero y reproduce los valores del informe.

## Opción A — Local con `main.py` (recomendada)

El proyecto se reproduce desde un **clon limpio** del repositorio con un solo
comando, siguiendo estos prerequisitos:

```bash
# Prerequisitos (una vez):
sudo apt install -y postgresql postgresql-postgis \
     postgresql-pgrouting
sudo service postgresql start
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
pip install -r requirements.txt   # psycopg2, flask

# UN SOLO COMANDO: construye todo y levanta el mapa
python3 main.py all
```

El subcomando `all` ejecuta secuencialmente:

1. **`initdb`** — crea la base de datos `resiliencia`, carga las extensiones
   (PostGIS, pgRouting), importa los 4 shapefiles con `shp2pgsql`, construye
   la topología (`pgr_createTopology`), identifica los 19 nodos clave, carga
   el epicentro **parseando** el GeoJSON del USGS (`ST_GeomFromGeoJSON`) y
   aplica el modelo de falla (GMPE Campbell + fragilidad HAZUS) para obtener
   la probabilidad de falla de cada enlace.
2. **`attr -n 5000`** — calcula el ATTR (dos terminales, Monte Carlo) antes y
   después del sismo; guarda los resultados en la BD.
3. **`serve`** — levanta el servidor Flask con el mapa Leaflet en
   `http://127.0.0.1:5000`.

Las dependencias de Python están declaradas en `requirements.txt`
(`psycopg2-binary`, `flask`). Las dependencias del sistema (PostgreSQL,
PostGIS, pgRouting, `shp2pgsql`) son paquetes estándar de Debian/Ubuntu/Kali.

El DSN por defecto (`host=localhost port=5432 user=postgres password=postgres`)
permite que `python3 main.py all` funcione sin exportar variables de entorno;
si la instalación difiere, se configuran `RESIL_DSN` y `RESIL_ADMIN_DSN`.

Los valores que produce el script son **deterministas** (semilla fija por
componente) y coinciden con los reportados en el informe.

## Cargar solo `main.sql` (entregable autocontenido)

`main.sql` es **autocontenido**: carga en una **base de datos vacía** toda la
infraestructura (topología de red con geometría) junto con la **probabilidad de
falla `p_fail` de cada enlace** ante el sismo M8.8. No requiere los shapefiles
ni ejecutar `main.py`:

```bash
createdb -h localhost -p 5432 -U postgres resiliencia_main
psql     -h localhost -p 5432 -U postgres -d resiliencia_main -f main.sql
```

Incluye las extensiones (PostGIS + pgRouting), las funciones del modelo de falla
(`norm_cdf`, `pga_campbell`) y las tablas `edges`, `edges_vertices_pgr`,
`nodos_clave`, `sismo`, `modelo_param` y `edge_failure` con sus datos.

## Opción B — Docker (alternativa)

Para garantizar la reproducibilidad del proyecto, se construyó un entorno
Docker que ejecuta todo el pipeline — desde la inicialización de la base de
datos hasta la visualización web — con un solo comando:

```bash
sudo docker compose up --build
```

La solución emplea un enfoque de **contenedor único** basado en la imagen
`postgres:17-bookworm`, sobre la cual se instalan PostGIS 3, pgRouting y un
entorno virtual Python con Flask. Un script de entrada
(`docker-entrypoint.sh`) orquesta la secuencia completa: inicializa el clúster
PostgreSQL, construye la base de datos invocando `main.py initdb`, calcula el
ATTR mediante Monte Carlo (`main.py attr -n 5000`) y finalmente levanta el
servidor Flask en `http://localhost:5000`.

## Estructura

```
codigo-t2/
├── main.py                 Orquestador (initdb / attr / serve / all)
├── main.sql                Entregable autocontenido: infraestructura +
│                           probabilidades de falla, carga en BD vacía
├── requirements.txt        Dependencias Python
├── Dockerfile              Imagen Docker (PG17 + PostGIS + pgRouting + Flask)
├── docker-compose.yml      Un solo comando: docker compose up --build
├── docker-entrypoint.sh    Script de entrada del contenedor
├── sql/
│   ├── 00_pgr_createtopology_compat.sql  Compat. pgr_createTopology para pgRouting 4.x
│   ├── 01_carga.sql          Extensiones PostGIS + pgRouting
│   ├── 02_topologia.sql      Tabla edges + pgr_createTopology
│   ├── 03_nodos_clave.sql    Nodos que generan/intercambian/reciben información
│   ├── 04_sismo.sql          Tabla sismo + staging GeoJSON
│   ├── 04b_sismo_extract.sql Extrae epicentro desde GeoJSON (ST_GeomFromGeoJSON)
│   └── 05_modelo_falla.sql   GMPE Campbell(1981) + fragilidad lognormal HAZUS
├── scripts/
│   └── attr.py               ATTR (Average Two-Terminal Reliability) Monte Carlo
├── templates/
│   └── index.html            Mapa Leaflet
├── data/
│   ├── shp/                  Shapefiles de infraestructura (fibra, postación, camino, ferry)
│   └── sismo_maule_2010.geojson
├── material/                 Material de referencia (estudios CORFO/SUBTEL)
└── docs/
    └── informe-final.tex     Informe LaTeX (entregable)
```

## Resultado (resumen)

- Red de fibra en operación: **2.119 enlaces**, red **fragmentada** (la mayor
  componente conexa es ~11–17% de los nodos, coincidiendo con el estudio).
- **ATTR** = *Average Two-Terminal Reliability*: fracción promedio de pares de
  nodos que siguen conectados tras las fallas (definición de Boettcher et al.,
  IEEE 2018, ec. 8).
- **ATTR de la red** (promedio ponderado del ATTR de cada sub-red operativa):
  **1,00 → 0,87 tras el M8.8 (−13%)**. Las sub-redes del epicentro son las que
  más caen: **Talca** conserva solo 17% de sus pares conectados y
  **Concepción–Chillán** 43%; las lejanas (norte y sur) quedan intactas.
- **ATTR dos terminales entre los 19 nodos clave:** **0,047 → 0,042** (−11%).
- **ATTR estricto (all-terminal) = 0** ya en operación (los 19 nodos clave no
  están todos en una misma componente ⇒ la red no es resiliente ni sin sismo).

Detalle completo de metodología, parámetros y referencias en
[`docs/informe-final.tex`](docs/informe-final.tex).
