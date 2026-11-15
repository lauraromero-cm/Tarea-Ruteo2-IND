# Tarea 2 — Resiliencia de la Internet chilena ante un sismo M8.8

Modelo de red de la infraestructura de fibra óptica chilena (datos SUBTEL/NIC,
proyecto *Yafún* / estudio CORFO 15BPE-47225) sobre **PostgreSQL + PostGIS +
pgRouting**, con cálculo del **ATTR** (All-Terminal Reliability) de los nodos
clave antes y después del terremoto **M8.8 del Maule (2010)**, y visualización
web en **Leaflet**.

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

## Uso rápido (Docker)

```bash
docker compose up --build
# Abre http://localhost:5000
```

Esto levanta PostgreSQL + PostGIS + pgRouting, construye la BD, calcula el ATTR
y sirve el mapa web, todo en un solo contenedor. El puerto se puede cambiar con
`APP_PORT` en `docker-compose.yml`.

## Uso local (sin Docker)

```bash
# 0) configurar conexión (ajuste a su instalación)
export RESIL_DSN="host=localhost port=5432 user=postgres dbname=resiliencia"
export RESIL_ADMIN_DSN="host=localhost port=5432 user=postgres dbname=postgres"

# Todo de corrido:
python main.py all           # initdb + attr + serve

# O paso a paso:
python main.py initdb        # construir la BD
python main.py attr -n 5000  # calcular ATTR (Monte Carlo)
python main.py serve         # mapa web en http://127.0.0.1:5000
```

## Estructura

```
codigo-t2/
├── main.py                 Orquestador (initdb / attr / serve / all)
├── main.sql                Probabilidades de falla por enlace (entregable)
├── requirements.txt        Dependencias Python
├── Dockerfile              Imagen Docker (PG17 + PostGIS + pgRouting + Flask)
├── docker-compose.yml      Un solo comando: docker compose up --build
├── docker-entrypoint.sh    Script de entrada del contenedor
├── .dockerignore           Exclusiones para el build
├── sql/
│   ├── 00_pgr_createtopology_compat.sql  Compat. pgr_createTopology para pgRouting 4.x
│   ├── 01_carga.sql          Extensiones PostGIS + pgRouting
│   ├── 02_topologia.sql      Tabla edges + pgr_createTopology
│   ├── 03_nodos_clave.sql    Nodos que generan/intercambian/reciben información
│   ├── 04_sismo.sql          Epicentro M8.8
│   └── 05_modelo_falla.sql   GMPE Campbell(1981) + fragilidad lognormal HAZUS
├── scripts/
│   └── attr.py               ATTR (All-Terminal Reliability) Monte Carlo
├── templates/
│   └── index.html            Mapa Leaflet
├── data/
│   ├── shp/                  Shapefiles de infraestructura (fibra, postación, camino, ferry)
│   └── sismo_maule_2010.geojson
└── docs/
    └── INFORME.md            Informe: metodología, decisiones y resultados
```

## Resultado (resumen)

- Red de fibra en operación: **2.119 enlaces**, red **fragmentada** (la mayor
  componente conexa es ~11–17% de los nodos, coincidiendo con el estudio).
- **ATTR estricto = 0** (los 19 nodos clave no están todos en una misma
  componente ⇒ la red no es resiliente ya en operación).
- Indicador graduado (conectividad de pares de nodos clave): **0.047 antes →
  0.042 después** del sismo, es decir una **caída ~11%** por el terremoto.

Ver `docs/INFORME.md` para el detalle.
# Tarea-Ruteo2-IND
