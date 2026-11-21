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

Pensado para una instalación nativa de PostgreSQL (ej. Debian/Kali: paquetes
`postgresql`, `postgresql-postgis`, `postgresql-<version>-pgrouting`).
**Copia y pega el bloque completo** (ajusta host/puerto solo si tu instalación
difiere):

```bash
# 1) dependencias del sistema (Debian/Kali/Ubuntu)
sudo apt install -y postgresql postgresql-postgis postgresql-pgrouting

# 2) levantar el servicio
sudo service postgresql start

# 3) contraseña para el rol postgres (una sola vez por instalación)
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"

# 4) dependencias de Python
pip install -r requirements.txt

# 5) UN SOLO COMANDO: construye la BD, calcula el ATTR y levanta el mapa
python3 main.py all          # initdb + attr + serve -> http://127.0.0.1:5000
```

> `main.py` usa por defecto `host=localhost port=5432 user=postgres
> password=postgres dbname=resiliencia`, de modo que `python3 main.py all`
> funciona sin exportar nada. Si tu instalación difiere (otro puerto, host o
> contraseña), exporta `RESIL_DSN` y `RESIL_ADMIN_DSN` antes. El password del
> DSN se pasa a `psql` vía `PGPASSWORD` automáticamente.

Alternativa paso a paso (equivalente al `all`):

```bash
python3 main.py initdb        # construir la BD (topología + sismo + modelo)
python3 main.py attr -n 5000  # calcular ATTR (Monte Carlo)
python3 main.py serve         # mapa web en http://127.0.0.1:5000
```

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

Se incluye además un `Dockerfile` + `docker-compose.yml` que empaquetan
PostgreSQL + PostGIS + pgRouting + Flask en un contenedor con autenticación
`trust`:

```bash
docker compose up --build        # -> http://localhost:5000
```

La **vía soportada y verificada es la Opción A (`main.py`)**; el contenedor se
ofrece solo como empaquetado alternativo de las mismas dependencias.

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
