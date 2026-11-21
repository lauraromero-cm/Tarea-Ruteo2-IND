#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
attr.py - Calculo del ATTR (Average Two-Terminal Reliability) de la red de
fibra optica en operacion, antes y despues del terremoto M8.8.

ATTR (fiabilidad promedio de dos terminales), siguiendo la definicion de
Boettcher, Prieto, Restrepo & Pezoa, "Resilient Multiculture Network Design
in the Presence of Exploit-Triggered Correlated Failures", IEEE Latin America
Transactions 16(9), 2018 (ec. 8):

        ATTR = C(n,2)^-1 * sum_{i<j} Z_ij

donde Z_ij = 1 si existe un camino entre los nodos i y j tras las fallas, y 0
en caso contrario. Es decir, ATTR es la FRACCION PROMEDIO DE PARES DE NODOS que
permanecen mutuamente conectados. A diferencia de la fiabilidad de "todos los
terminales" (all-terminal: que TODOS queden en una sola componente), el ATTR de
dos terminales degrada suavemente y permite medir el impacto marginal del sismo.

Reportamos la metrica del paper como principal y, como complemento, el
indicador ESTRICTO (all-terminal) para evidenciar que la red chilena no es
resiliente ni siquiera en operacion.

Escenarios:
  - ANTES  : red intacta (p_fail = 0) -> ATTR determinista.
  - DESPUES: cada enlace sobrevive con prob (1 - p_fail) -> Monte Carlo.
"""
import os, json, random, argparse
from collections import defaultdict
import psycopg2

DSN = os.environ.get("RESIL_DSN",
    "host=/tmp port=5433 user=postgres dbname=resiliencia")

# ---------- Union-Find ----------
class DSU:
    def __init__(self, nodes):
        self.p = {n: n for n in nodes}
    def find(self, a):
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]; a = p[a]
        return a
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb: self.p[ra] = rb

def cargar(cur):
    cur.execute("""SELECT id, source, target, COALESCE(p_fail,0)
                   FROM edges WHERE operativo
                     AND source IS NOT NULL AND target IS NOT NULL""")
    edges = cur.fetchall()
    cur.execute("""SELECT cod, nombre, vertex_id FROM nodos_clave
                   WHERE vertex_id IS NOT NULL ORDER BY cod""")
    claves = cur.fetchall()
    nodes = set()
    for _, s, t, _ in edges:
        nodes.add(s); nodes.add(t)
    return edges, claves, nodes

def pares_conectados(dsu, keys):
    """Dado un union-find ya construido, cuenta cuantos pares del conjunto
       'keys' quedan conectados (ATTR de dos terminales, numerador de la ec. 8).
       Devuelve (pares_conectados, total_pares, todos_en_una_componente)."""
    grupos = defaultdict(int)
    for v in keys:
        grupos[dsu.find(v)] += 1
    pares = sum(n*(n-1)//2 for n in grupos.values())
    total = len(keys)*(len(keys)-1)//2
    todos = (len(grupos) == 1)
    return pares, total, todos

def componentes(edges):
    """Particiona la red en componentes conexas (red intacta).
       Devuelve: dict comp_id->set(nodos), dict comp_id->list(aristas)."""
    nodos = set()
    for _, s, t, _ in edges:
        nodos.add(s); nodos.add(t)
    dsu = DSU(nodos)
    for _, s, t, _ in edges:
        dsu.union(s, t)
    nbc = defaultdict(set); ebc = defaultdict(list)
    for n in nodos:
        nbc[dsu.find(n)].add(n)
    for eid, s, t, pf in edges:
        ebc[dsu.find(s)].append((s, t, pf))
    return nbc, ebc

def attr_tt_componente(nodos, aristas, N, seed):
    """ATTR (Average Two-Terminal Reliability) de una componente: fraccion
       promedio de pares de sus nodos que siguen conectados cuando los enlaces
       fallan (Monte Carlo). Intacta = 1.0 por construccion (todos los pares
       conectados); el sismo la degrada suavemente.

       Usa un generador PROPIO sembrado con 'seed' (derivado del id estable de
       la componente), de modo que el resultado es determinista, reproducible e
       INDEPENDIENTE del orden en que se procesan las componentes."""
    n = len(nodos)
    if n < 2:
        return 1.0
    total = n*(n-1)//2
    rng = random.Random(seed)
    suma_frac = 0.0
    for _ in range(N):
        dsu = DSU(nodos)
        for s, t, pf in aristas:
            if pf == 0.0 or rng.random() > pf:
                dsu.union(s, t)
        grupos = defaultdict(int)
        for node in nodos:
            grupos[dsu.find(node)] += 1
        pares = sum(k*(k-1)//2 for k in grupos.values())
        suma_frac += pares / total
    return suma_frac / N

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--trials", type=int, default=5000)
    # El ATTR por componente se reporta con 3 decimales en el mapa; por eso usa
    # un N mayor (sub-redes chicas, calculo barato) para que ese tercer decimal
    # sea significativo (±0.001) y los valores no fluctuen entre corridas.
    ap.add_argument("--trials-comp", type=int, default=20000,
                    help="iteraciones Monte Carlo del ATTR por componente")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    random.seed(args.seed)

    con = psycopg2.connect(DSN); cur = con.cursor()
    edges, claves, nodes = cargar(cur)
    keys = [vid for _, _, vid in claves]
    keyset = sorted(set(keys))
    print(f"Enlaces operativos: {len(edges)} | Nodos de red: {len(nodes)}")
    print(f"Nodos clave: {len(claves)} (vertices distintos: {len(keyset)})")

    # ---- ATTR GLOBAL sobre los nodos clave (ec. 8 del paper) ----
    # ANTES (intacto, determinista): fraccion de pares clave conectados.
    dsu0 = DSU(nodes)
    for _, s, t, _ in edges:
        dsu0.union(s, t)
    pares0, total, todos0 = pares_conectados(dsu0, keyset)
    attr_before = pares0 / total                 # ATTR two-terminal (principal)
    attr_strict_before = 1.0 if todos0 else 0.0  # all-terminal (complementario)

    # DESPUES (Monte Carlo): cada enlace sobrevive con prob 1 - p_fail.
    N = args.trials
    sum_pairs = 0; cnt_all = 0
    for _ in range(N):
        dsu = DSU(nodes)
        for _, s, t, pf in edges:
            if pf == 0.0 or random.random() > pf:
                dsu.union(s, t)
        pares, _, todos = pares_conectados(dsu, keyset)
        sum_pairs += pares
        if todos: cnt_all += 1
    attr_after = sum_pairs / (N * total)         # ATTR two-terminal (principal)
    attr_strict_after = cnt_all / N              # all-terminal (complementario)

    res = {
        "escenario_sismo": "M8.8 Maule 2010",
        "metrica": "ATTR = Average Two-Terminal Reliability (Boettcher et al., IEEE 2018, ec. 8)",
        "n_enlaces_operativos": len(edges),
        "n_nodos_clave": len(claves),
        "n_pares_clave": total,
        "trials_montecarlo": N,
        "trials_componente": args.trials_comp,
        # ATTR (two-terminal) global sobre los 19 nodos clave -> metrica del paper
        "ATTR_NODOS_CLAVE": {
            "descripcion": "Fraccion promedio de los pares de nodos clave que siguen conectados",
            "antes": round(attr_before, 4),
            "despues": round(attr_after, 4),
            "caida_relativa_pct": round(
                100*(attr_before - attr_after)/attr_before, 2) if attr_before > 0 else None,
            "pares_conectados_antes": pares0,
            "pares_conectados_despues_esperados": round(attr_after*total, 1),
        },
        # Indicador ESTRICTO (all-terminal): que los 19 queden en UNA componente
        "ATTR_ESTRICTO_NODOS_CLAVE": {
            "descripcion": "All-terminal: P(los 19 nodos clave en una sola componente)",
            "antes": round(attr_strict_before, 4),
            "despues": round(attr_strict_after, 4),
        },
    }

    # ---- ATTR POR COMPONENTE OPERATIVA (metrica principal, two-terminal) ----
    # Cada sub-red conexa es un sistema con todos sus nodos como terminales.
    # Antes del sismo cada componente esta conectada (ATTR=1, todos los pares);
    # el sismo baja el ATTR de dos terminales de las componentes cercanas.
    nbc, ebc = componentes(edges)
    comp2keys = defaultdict(list)
    raiz_de = {n: dsu0.find(n) for n in nodes}
    nombre_de = {vid: nom for cod, nom, vid in claves}
    for _, nom, vid in claves:
        if vid in raiz_de: comp2keys[raiz_de[vid]].append(nombre_de[vid])

    N_comp = args.trials_comp
    comp_list = sorted(nbc, key=lambda c: -len(nbc[c]))
    tabla = []
    n_total = sum(len(v) for v in nbc.values())
    suma_pond_after = 0.0
    for c in comp_list:
        n_i = len(nbc[c])
        # Semilla estable por componente (id de raiz union-find): hace el ATTR
        # reproducible e independiente del orden de procesamiento.
        a_after = attr_tt_componente(nbc[c], ebc[c], N_comp, seed=args.seed + int(c))
        suma_pond_after += n_i * a_after
        if n_i >= 2 and (len(tabla) < 8 or comp2keys.get(c)):
            pfails = [pf for _, _, pf in ebc[c]]
            avg_pf = sum(pfails)/len(pfails) if pfails else 0.0
            tabla.append({
                "componente": int(c), "nodos": n_i,
                "nodos_clave": comp2keys.get(c, []),
                "attr_antes": 1.0,
                "attr_despues": round(a_after, 4),
                "p_fail_prom": round(avg_pf, 5),
            })
    attr_red_before = 1.0   # cada componente intacta: todos los pares conectados
    attr_red_after = round(suma_pond_after / n_total, 4)

    res["ATTR_POR_COMPONENTE"] = tabla[:10]
    res["ATTR_RED"] = {
        "descripcion": "ATTR (two-terminal) promedio ponderado por nodos sobre las componentes operativas",
        "antes": attr_red_before,
        "despues": attr_red_after,
        "caida_relativa_pct": round(100*(attr_red_before-attr_red_after), 2),
    }

    print(json.dumps(res, indent=2, ensure_ascii=False))

    # Persistir en la BD para main.py / Leaflet
    cur.execute("""CREATE TABLE IF NOT EXISTS attr_resultados(
        id serial primary key, calculado_en timestamptz default now(),
        resultado jsonb)""")
    cur.execute("INSERT INTO attr_resultados(resultado) VALUES (%s)",
                (json.dumps(res),))
    con.commit()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, ensure_ascii=False)
    con.close()

if __name__ == "__main__":
    main()
