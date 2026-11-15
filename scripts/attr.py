#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
attr.py - Calculo del ATTR (All-Terminal Reliability) de la red de fibra
optica en operacion, antes y despues del terremoto M8.8.

ATTR = probabilidad de que TODOS los nodos clave permanezcan mutuamente
conectados cuando los enlaces fallan de forma independiente con su
probabilidad p_fail.

Como la red real esta fragmentada (el estudio reporta componente conexa
mayor ~17% de las comunas), el ATTR estricto es practicamente 0 ya en
operacion. Por eso reportamos DOS indicadores:

  1. ATTR estricto            : P(los K nodos clave quedan en UNA sola
                                 componente conexa).
  2. Conectividad de pares    : E[ fraccion de pares de nodos clave que
                                 siguen conectados ]  (generalizacion del
                                 ATTR que degrada suavemente y permite ver
                                 el impacto marginal del sismo).

Escenarios:
  - ANTES  : red intacta (p_fail = 0) -> indicadores deterministas.
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

def conectividad(edges, keys, nodes, incluir):
    """Construye DSU con los enlaces en 'incluir' y mide conectividad de keys.
       Devuelve (todos_conectados, pares_conectados, total_pares)."""
    dsu = DSU(nodes)
    for eid, s, t, pf in edges:
        if incluir(eid, pf):
            dsu.union(s, t)
    roots = [dsu.find(v) for v in keys]
    grupos = defaultdict(int)
    for r in roots:
        grupos[r] += 1
    todos = (len(set(roots)) == 1)
    # pares conectados = sum C(n_i,2) sobre cada grupo
    pares = sum(n*(n-1)//2 for n in grupos.values())
    total = len(keys)*(len(keys)-1)//2
    return todos, pares, total

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

def attr_componente(nodos, aristas, N):
    """ATTR (All-Terminal Reliability) de una componente: probabilidad de que
       TODOS sus nodos sigan conectados cuando los enlaces fallan (Monte Carlo).
       Intacta = 1.0 por construccion; devolvemos ATTR tras el sismo."""
    if len(nodos) < 2:
        return 1.0
    ok = 0
    for _ in range(N):
        dsu = DSU(nodos)
        for s, t, pf in aristas:
            if pf == 0.0 or random.random() > pf:
                dsu.union(s, t)
        if len({dsu.find(n) for n in nodos}) == 1:
            ok += 1
    return ok / N

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--trials", type=int, default=5000)
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

    # ---- ANTES (intacto, determinista) ----
    todos0, pares0, total = conectividad(edges, keyset, nodes, lambda e, p: True)
    attr_pairs_before = pares0 / total
    attr_strict_before = 1.0 if todos0 else 0.0

    # ---- DESPUES (Monte Carlo) ----
    N = args.trials
    cnt_all = 0; sum_pairs = 0
    for _ in range(N):
        surv = lambda e, p, r=random.random: (p == 0.0) or (r() > p)
        todos, pares, _ = conectividad(edges, keyset, nodes, surv)
        if todos: cnt_all += 1
        sum_pairs += pares
    attr_strict_after = cnt_all / N
    attr_pairs_after = sum_pairs / (N * total)

    res = {
        "escenario_sismo": "M8.8 Maule 2010",
        "n_enlaces_operativos": len(edges),
        "n_nodos_clave": len(claves),
        "n_pares_clave": total,
        "trials_montecarlo": N,
        "ANTES": {
            "attr_estricto": round(attr_strict_before, 4),
            "conectividad_pares": round(attr_pairs_before, 4),
            "pares_conectados": pares0,
        },
        "DESPUES": {
            "attr_estricto": round(attr_strict_after, 4),
            "conectividad_pares": round(attr_pairs_after, 4),
            "pares_conectados_esperados": round(attr_pairs_after*total, 1),
        },
    }
    res["caida_relativa_conectividad_pct"] = round(
        100*(attr_pairs_before - attr_pairs_after)/attr_pairs_before, 2) \
        if attr_pairs_before > 0 else None

    # ---- ATTR POR COMPONENTE OPERATIVA (metrica principal) ----
    # Cada sub-red conexa es un sistema con todos sus nodos como terminales.
    # Antes del sismo cada componente esta conectada (ATTR=1); el sismo baja
    # el ATTR de las componentes cercanas al epicentro.
    nbc, ebc = componentes(edges)
    comp2keys = defaultdict(list)
    dsu0 = DSU(nodes)
    for _, s, t, _ in edges: dsu0.union(s, t)
    raiz_de = {n: dsu0.find(n) for n in nodes}
    nombre_de = {vid: nom for cod, nom, vid in claves}
    for _, nom, vid in claves:
        if vid in raiz_de: comp2keys[raiz_de[vid]].append(nombre_de[vid])

    comp_list = sorted(nbc, key=lambda c: -len(nbc[c]))
    tabla = []
    n_total = sum(len(v) for v in nbc.values())
    suma_pond_after = 0.0
    for c in comp_list:
        n_i = len(nbc[c])
        a_after = attr_componente(nbc[c], ebc[c], N)
        suma_pond_after += n_i * a_after
        if n_i >= 2 and (len(tabla) < 8 or comp2keys.get(c)):
            pfails = [pf for _, _, pf in ebc[c]]
            avg_pf = sum(pfails)/len(pfails) if pfails else 0.0
            tabla.append({
                "componente": int(c), "nodos": n_i,
                "nodos_clave": comp2keys.get(c, []),
                "attr_antes": 1.0,
                "attr_despues": round(a_after, 4),
                "p_fail_prom": round(avg_pf, 4),
            })
    attr_red_before = 1.0   # cada componente intacta esta conectada
    attr_red_after = round(suma_pond_after / n_total, 4)

    res["ATTR_POR_COMPONENTE"] = tabla[:10]
    res["ATTR_RED"] = {
        "descripcion": "ATTR promedio ponderado por nodos sobre las componentes operativas",
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
