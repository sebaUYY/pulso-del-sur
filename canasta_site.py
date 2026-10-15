"""Canasta UY: descarga (solo si cambió) el CSV anual del SIPC y genera site/canasta/.
Cache en canasta/ (resumen JSON + fecha del recurso) para no bajar 1 GB en cada corrida."""
import json, subprocess, os, sys, datetime as dt, statistics as st
from zoneinfo import ZoneInfo

CA = "/root/.ccr/ca-bundle.crt"
CK = "https://catalogodatos.gub.uy/api/3/action/package_show?id=defensa-del-consumidor-sistema-de-informacion-de-precios-al-consumidor-"
NOW = dt.datetime.now(ZoneInfo("America/Montevideo"))
os.makedirs("canasta", exist_ok=True)


def curl(*a):
    c = ["curl", "-sS", "-L", "--retry", "4", "--max-time", "3000"] + (["--cacert", CA] if os.path.exists(CA) else []) + list(a)
    return c


def meta(year):
    r = subprocess.run(curl(CK + str(year)), capture_output=True, text=True)
    res = {x["name"]: x for x in json.loads(r.stdout)["result"]["resources"]}
    return res


year = NOW.year
try:
    res = meta(year)
except Exception:
    year -= 1
    res = meta(year)
pre = next(v for k, v in res.items() if k.lower().startswith("precios"))
stamp_f = "canasta/stamp.txt"
summary = f"canasta/resumen-{year}.json"
stamp = f'{pre["url"]}|{pre.get("last_modified") or pre.get("created")}'
if not os.path.exists(summary) or open(stamp_f).read() != stamp or "--force" in sys.argv:
    for name, fn in (("Productos", "canasta/productos.csv"), ("Establecimiento", "canasta/establecimiento.csv")):
        subprocess.run(curl("-o", fn, res[name]["url"]), check=True)
    p1 = subprocess.Popen(curl(pre["url"]), stdout=subprocess.PIPE)
    subprocess.run([sys.executable, "canasta.py", "canasta/productos.csv", "canasta/establecimiento.csv", summary],
                   stdin=p1.stdout, check=True)
    p1.wait()
    open(stamp_f, "w").write(stamp)
else:
    print("canasta: sin cambios en la fuente")

d = json.load(open(summary))
meses, ult = d["meses"], d["ultimo_mes"]
# índice por cadena: precio mediano de la cadena / mediana entre cadenas, promediado en productos con ≥4 cadenas
idx = {}
for p in d["productos"]:
    c = p["cadenas_ultimo_mes"]
    if len(c) < 4:
        continue
    med = st.median(v["mediana"] for v in c.values())
    for k, v in c.items():
        idx.setdefault(k, []).append(v["mediana"] / med)
cadenas = sorted(({"cadena": k.strip(), "indice": round(st.mean(v) * 100, 1), "productos": len(v)}
                  for k, v in idx.items() if len(v) >= 40 and k.strip() not in ("?", "Sin Cadena")), key=lambda x: x["indice"])
prods = []
for p in d["productos"]:
    s = {m: v["mediana"] for m, v in p["serie"].items() if v["obs"] >= 30}
    if ult not in s:
        continue
    base = s.get(meses[0])
    prods.append({"n": p["nombre"].replace(",  ", " "), "g": p["producto"], "s": [s.get(m) for m in meses],
                  "v": round(s[ult] / base - 1, 4) if base else None,
                  "c": sorted(([k.strip(), v["mediana"]] for k, v in p["cadenas_ultimo_mes"].items() if k.strip() not in ("?",)), key=lambda x: x[1])})
prods.sort(key=lambda x: x["n"])
vs = sorted(x["v"] for x in prods if x["v"] is not None)
MES = "enero febrero marzo abril mayo junio julio agosto setiembre octubre noviembre diciembre".split()
lab = lambda m: f'{MES[int(m[5:]) - 1]} {m[:4]}'
data = json.dumps({"meses": meses, "prods": prods, "cadenas": cadenas}, ensure_ascii=False).replace("</", "<\\/")
html = (open("canasta_template.html", encoding="utf-8").read().replace("{{DATA}}", data)
        .replace("{{ULT}}", lab(ult)).replace("{{DESDE}}", lab(meses[0])).replace("{{NPROD}}", str(len(prods)))
        .replace("{{NOBS}}", f'{d["filas"]:,}'.replace(",", ".")).replace("{{MEDVAR}}", f'{st.median(vs) * 100:+.1f}'.replace(".", ","))
        .replace("{{SUBEN}}", str(sum(1 for v in vs if v > 0.005))).replace("{{BAJAN}}", str(sum(1 for v in vs if v < -0.005)))
        .replace("{{FECHA}}", NOW.strftime("%d/%m/%Y")))
os.makedirs("site/canasta", exist_ok=True)
open("site/canasta/index.html", "w", encoding="utf-8").write(html)
print("canasta:", len(prods), "productos ·", len(cadenas), "cadenas ·", meses[0], "→", ult)
