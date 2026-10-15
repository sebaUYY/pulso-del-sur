"""Canasta UY — precios al consumidor (Defensa del Consumidor / SIPC, datos abiertos).
Lee el CSV anual por streaming y resume: mediana mensual por producto y, para el último mes, mediana por cadena.
Uso: curl -s <precios_YYYY.csv> | python3 canasta.py productos.csv establecimiento.csv salida.json"""
import sys, csv, json, io, collections


def median(c):
    n, acc = sum(c.values()), 0
    for v in sorted(c):
        acc += c[v]
        if acc * 2 >= n:
            return v


def rd(path):
    raw = open(path, "rb").read()
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        txt = raw.decode("latin-1")
    return list(csv.DictReader(io.StringIO(txt), delimiter=";"))


prods = {r["id.producto"]: r for r in rd(sys.argv[1])}
ests = {r["id.establecimientos"]: r for r in rd(sys.argv[2])}

mes_prod = collections.defaultdict(collections.Counter)            # (mes, prod) -> Counter(precio)
mes_prod_cad = collections.defaultdict(collections.Counter)        # (mes, prod, cadena) -> Counter(precio)
n = 0
for r in csv.DictReader(io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")):
    try:
        p = int(float(r["Precio"]))
    except (ValueError, TypeError):
        continue
    if p <= 0:
        continue
    m, pid = r["Fecha"][:7], r["Presentacion_Producto"]
    mes_prod[(m, pid)][p] += 1
    e = ests.get(r["Establecimiento"])
    cad = (e or {}).get("cadena") or "?"
    mes_prod_cad[(m, pid, cad)][p] += 1
    n += 1

meses = sorted({m for m, _ in mes_prod})
ult = meses[-1]
serie = collections.defaultdict(dict)
for (m, pid), c in mes_prod.items():
    serie[pid][m] = {"mediana": median(c), "obs": sum(c.values())}
out = {"filas": n, "meses": meses, "ultimo_mes": ult, "productos": []}
for pid, s in serie.items():
    pr = prods.get(pid, {})
    cad = {k[2]: {"mediana": median(c), "obs": sum(c.values())} for k, c in mes_prod_cad.items()
           if k[0] == ult and k[1] == pid and sum(c.values()) >= 20}
    out["productos"].append({"id": pid, "nombre": pr.get("nombre", pid), "producto": pr.get("producto", ""),
                             "marca": pr.get("marca", ""), "presentacion": pr.get("especificacion", ""),
                             "serie": s, "cadenas_ultimo_mes": cad})
json.dump(out, open(sys.argv[3], "w"), ensure_ascii=False)
print(n, "precios ·", len(out["productos"]), "productos ·", meses[0], "→", ult)
