# Informe — Resiliencia de la Internet chilena ante un terremoto M8.8

## 1. Datos y fuente

La infraestructura proviene del proyecto **Yafún** (NIC Chile) y del estudio
**"Estudio y Recomendaciones sobre la Resiliencia de la infraestructura de la
Internet chilena"**, Informe Técnico Final CORFO 15BPE-47225 (U. de Chile / NIC
Labs, diciembre 2018). Los datos geográficos fueron entregados por SUBTEL vía
solicitud de transparencia (oficio en `docs/oficio_subtel_respuesta.pdf`) como
shapefiles en WGS84 (EPSG:4326):

| Capa | Tramos | Largo aprox. | Uso en el modelo |
|---|---:|---:|---|
| `fibra_optica_detectada` | 1.915 | 10.313 km | **arista operativa** (transporta datos) |
| `trayecto_en_ferry` | 204 | 2.390 km | **arista operativa** (continuidad marítima) |
| `postacion_electrica_detectada` | 1.213 | 6.712 km | potencial (no operativa) |
| `camino_sin_postacion_detectado` | 1.165 | 8.108 km | potencial (no operativa) |

Total ≈ 27.500 km, consistente con los "28.000 km" del proyecto. La red **en
operación** se define como `fibra + ferry`; postación y caminos son
infraestructura *potencial* (dónde se podría tender fibra a menor costo, como la
usa el estudio en su modelo de optimización) y no cursan tráfico.

## 2. Nodos clave (punto 2)

El estudio modela la red con las **comunas** como nodos. De ese conjunto
seleccionamos los **nodos clave que generan, intercambian y reciben
información**, criterio del enunciado:

- **Intercambio:** Santiago (sede del PIT Chile / NAP, mayor concentración de
  data centers y tráfico nacional), y hubs regionales (Valparaíso, Antofagasta,
  La Serena, Concepción, Temuco, Puerto Montt, Punta Arenas).
- **Generación / recepción:** capitales regionales y ciudades cabecera que
  agregan y distribuyen el tráfico de su zona.

Son 19 ciudades (ver `sql/03_nodos_clave.sql`), cada una *enganchada* al vértice
más cercano de la red **en operación** (`ST_Distance` sobre `edges_vertices_pgr`).

## 3. Topología de red (punto 3, `pgr_createTopology`)

Se unen las 4 capas en una tabla `edges` (MultiLineString → LineString con
`ST_Dump`), con `cost`/`reverse_cost` = largo en metros.

**Nota técnica importante:** pgRouting **4.0** *eliminó* la función
`pgr_createTopology` (reemplazada por `pgr_extractVertices`). Como el enunciado
exige `pgr_createTopology`, se implementó una **función de compatibilidad con
esa misma firma y comportamiento** (`sql/00_pgr_createtopology_compat.sql`): usa
`ST_ClusterDBSCAN` con `eps = tolerancia` para unir los extremos cercanos en un
mismo nodo, genera `edges_vertices_pgr` y rellena `source`/`target`.

- **Tolerancia:** 0.005° (~555 m). Se calibró probando 0.001–0.02; con 0.005 se
  cierran huecos de digitalización sin fusionar nodos distintos.
- **Resultado:** 4.268 vértices, 4.497 aristas, grado medio 2.06 (máx. 7).
- **Conectividad de la red operativa:** 157 componentes; la mayor tiene solo
  **261** vértices. La red está **fuertemente fragmentada**, exactamente el
  hallazgo del estudio (componente conexa mayor ≈ 17% de las comunas).

## 4. ATTR de la red en operación (punto 6)

El **ATTR (All-Terminal Reliability)** es la probabilidad de que *todos* los
nodos terminales (aquí, los nodos clave) permanezcan mutuamente conectados bajo
fallas de enlaces. Se calcula por **Monte Carlo** (`scripts/attr.py`): en cada
iteración cada enlace sobrevive con probabilidad `1 − p_fail`, se reconstruye el
grafo (union-find) y se evalúa la conectividad de los nodos clave.

Como la red ya está desconectada en operación, se reportan **dos indicadores**:

1. **ATTR estricto:** P(los 19 nodos clave quedan en una sola componente).
2. **Conectividad de pares:** E[fracción de los 171 pares de nodos clave que
   siguen conectados] — generalización que degrada suavemente y permite medir el
   impacto marginal del sismo.

**En operación (red intacta, determinista):**
- ATTR estricto = **0** (los nodos clave están repartidos en varias
  componentes: p.ej. Osorno–Pto. Montt–Castro–Coyhaique en una, Concepción–
  Chillán en otra, Santiago–La Serena en otra).
- Conectividad de pares = **0.047** (8 de 171 pares conectados).

Es decir, **la red de fibra chilena no es resiliente ni en condiciones
normales**: no garantiza conectividad entre los principales nodos.

## 5. Sismo M8.8 (punto 7)

Descargado del catálogo **USGS** en GeoJSON
(`data/sismo_maule_2010.geojson`, evento `official20100227063411530_30`):

- **M8.8 Maule, 2010-02-27 06:34 UTC**
- Epicentro **(−72.898, −36.122)**, profundidad focal **22.9 km**.

## 6. Modelo de falla probabilístico (punto 8) y probabilidades por enlace (punto 9–10)

Pipeline de riesgo sísmico estándar en dos etapas (`sql/05_modelo_falla.sql`):

**(a) Atenuación (GMPE) — PGA por enlace.** Ley de atenuación de
**Campbell (1981)** para la aceleración máxima del suelo (PGA, en g):

```
PGA = 0.0185 · e^{1.28 M} · (R + 0.147 e^{0.732 M})^{-1.75}
R   = √(R_epi² + h²)      (R_epi = distancia en superficie al epicentro; h = 22.9 km)
```

`R_epi` se obtiene con `ST_Distance(edge, epicentro)` sobre geografía.

**(b) Fragilidad — P(falla | PGA).** Curva de fragilidad **lognormal** (enfoque
HAZUS/FEMA para componentes de comunicaciones y *lifelines*):

```
P_fail = Φ( ln(PGA / μ) / β ),   μ = 0.30 g,  β = 0.55
```

μ es el PGA mediano que produce daño en postación/cable aéreo y β su dispersión.
La CDF normal Φ se implementó en SQL (`norm_cdf`, aprox. Abramowitz-Stegun).

El sismo actúa como **fuente común** que *correlaciona* las fallas por zona
geográfica (coherente con el enfoque de fallas correlacionadas de Boettcher et
al.): los enlaces cercanos al epicentro fallan juntos con alta probabilidad.

**Resultado:** P_fail máxima ≈ **0.45** (fibra a ~33 km del epicentro), ~146
enlaces operativos con P_fail > 0.1, concentrados < 250 km del epicentro
(Concepción, Chillán, Talca, Maule). Las probabilidades por enlace quedan en el
entregable **`main.sql`** (tabla `edge_failure`, 2.119 enlaces).

## 7. Nuevo ATTR tras el sismo (punto 11)

Como la red global está fragmentada, el **ATTR se calcula por componente
operativa**: cada sub-red conexa es un sistema cuyos terminales son todos sus
nodos. Intacta, cada componente está conectada (ATTR = 1); el sismo baja el ATTR
de las componentes cercanas al epicentro (Monte Carlo, `scripts/attr.py`):

| Componente (nodos clave) | Nodos | ATTR antes | ATTR después | Zona |
|---|---:|---:|---:|---|
| Osorno, Pto Montt, Castro, Coyhaique | 261 | 1.00 | **1.00** | Sur (lejos) |
| **Concepción, Chillán** | 195 | 1.00 | **0.00** | **Epicentro** |
| **Talca** | 184 | 1.00 | **0.00** | **Junto al epicentro** |
| Santiago, La Serena | 176 | 1.00 | 1.00 | Centro |
| Punta Arenas | 135 | 1.00 | 1.00 | Extremo sur |
| Antofagasta | 128 | 1.00 | 1.00 | Norte (lejos) |

**ATTR de la red** (promedio ponderado por nodos sobre todas las componentes):

| | Antes | Después | Variación |
|---|---:|---:|---:|
| **ATTR de la red** | **1.00** | **0.80** | **−20%** |

Las sub-redes en el área de mayor PGA (Concepción–Chillán y Talca) pasan de ATTR
= 1 a **≈ 0**: el M8.8 casi con certeza destruye su conectividad total. Las
sub-redes lejanas (sur y norte) quedan intactas. Esto evidencia el **efecto
espacial** del terremoto sobre la resiliencia.

**Observación sobre el daño por sub-red:** aunque la *ciudad* de Concepción
(79 km del epicentro) está más cerca que Talca (136 km), la **sub-red de Talca
presenta mayor daño promedio** (11.5% vs. 6.5% de probabilidad de falla por
enlace). Esto se explica porque el daño se calcula por enlace, no por nodo
clave: los enlaces de fibra de la sub-red de Talca cruzan más cerca del
epicentro (distancia mínima 33 km, promedio 118 km) que los de Concepción
(mínima 55 km, promedio 140 km). Es decir, la topología del tendido de fibra
determina la vulnerabilidad real de cada sub-red, no solo la ubicación de su
ciudad principal.

**Indicadores globales complementarios** (conectividad entre los 19 nodos clave,
que ya están en componentes distintas desde antes del sismo):

| Indicador | Antes | Después | Variación |
|---|---:|---:|---:|
| ATTR estricto (los 19 juntos) | 0.000 | 0.000 | — |
| Conectividad de pares clave | 0.047 | 0.042 | −11% |

El ATTR estricto permanece en 0 porque la red estaba desconectada desde antes: el
sismo **agrava** una fragilidad estructural preexistente que el propio estudio
denuncia.

## 8. Visualización (punto 12)

`main.py serve` levanta un servidor Flask con un mapa **Leaflet** que muestra:
- los enlaces de la red en operación coloreados por `p_fail` (verde→rojo),
- el **epicentro** con anillos de atenuación (~60/150/250 km),
- los **nodos clave**, y
- un panel con los **ATTR antes/después**.

## 9. Reproducibilidad

La forma recomendada de compilar el proyecto es **Docker**:

```bash
docker compose up --build
```

El contenedor levanta su propio PostgreSQL con autenticación `trust` (sin
contraseña), corre `main.py initdb` + `main.py attr` y sirve el mapa, todo con
un solo comando — no requiere instalar PostgreSQL/PostGIS/pgRouting en el host
ni configurar manualmente usuarios o contraseñas. Ver sección *Uso rápido
(Docker)* del `README.md`.

**Bug corregido (PostGIS ≥ 3.5 vs. `shp2pgsql -d`):** al cargar los
shapefiles, la bandera `-d` de `shp2pgsql` genera una llamada a
`DropGeometryColumn` antes de crear la tabla. En PostGIS 3.5+ esa función
lanza un `ERROR` (antes solo era un `NOTICE`) cuando la tabla todavía no
existe, lo que rompía la carga en instalaciones nuevas. Se corrigió en
`main.py` (`initdb`) haciendo `DROP TABLE IF EXISTS ... CASCADE` antes de cada
capa y usando `shp2pgsql -c` (crear) en vez de `-d`.

## 10. Limitaciones

- Los `id` de los shapefiles no son únicos ni describen operador/capacidad; el
  modelo se apoya en la geometría.
- La red entregada por SUBTEL es una versión agregada (4 capas) de las 9 del
  estudio; su fragmentación puede incluir huecos de digitalización además de la
  desconexión real.
- Los parámetros μ, β (fragilidad) y la GMPE son valores de literatura de primer
  orden; afinar con fragilidades específicas de telecom chilenas mejoraría la
  calibración. Son parámetros editables en `modelo_param`.

## Referencias

- Universidad de Chile / NIC Labs (2018). *Estudio y Recomendaciones sobre la
  resiliencia de la infraestructura de la Internet chilena*. CORFO 15BPE-47225.
- N. Boettcher, Y. Prieto, S. E. Restrepo, J. E. Pezoa. *Resilient Multiculture
  Network Design in the Presence of Exploit-Triggered Correlated Failures*, IEEE.
- Campbell, K. W. (1981). *Near-source attenuation of peak horizontal
  acceleration*. Bulletin of the Seismological Society of America, 71(6).
- FEMA / NIBS. *HAZUS-MH Technical Manual* — fragility curves (lognormal) for
  communication and lifeline components.
- USGS Earthquake Catalog — evento `official20100227063411530_30`.
