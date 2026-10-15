"""Empleos públicos UY — llamados abiertos y próximos de Uruguay Concursa (ONSC).
Genera site/empleos/index.html, llamados.csv y feed.xml (RSS). Solo datos públicos del portal oficial."""
import json, subprocess, os, csv, html, re, time, datetime as dt
from zoneinfo import ZoneInfo

API = "https://www.uruguayconcursa.gub.uy/api-backend/llamados/recientes"
LINK = "https://www.uruguayconcursa.gub.uy/llamado/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
CA = "/root/.ccr/ca-bundle.crt"
OUT = "site/empleos"
NOW = dt.datetime.now(ZoneInfo("America/Montevideo"))


def page(n, size=50):
    body = json.dumps({"PaginadoFiltrosSDT": {"PaginaActual": n, "CntPorPagina": size}})
    cmd = ["curl", "-sS", "--max-time", "150", "-A", UA, "-H", "Content-Type: application/json", "-H", "Accept: application/json",
           "-H", "Origin: https://www.uruguayconcursa.gub.uy", "-H", "Referer: https://www.uruguayconcursa.gub.uy/", "-d", body, API]
    if os.path.exists(CA):
        cmd[1:1] = ["--cacert", CA]
    for i in range(4):
        r = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return json.loads(r.stdout)
        except ValueError:
            time.sleep(10 * (i + 1))
    raise RuntimeError("Uruguay Concursa no respondió")


first = page(1)
rows = list(first["ListaLlamados"])
for n in range(2, int(first.get("cntPaginas") or 1) + 1):
    rows += page(n)["ListaLlamados"]


def depto(x):
    t = (x.get("LlaLugDes") or "") + " " + (x.get("UnidadEjecutora") or "") + " " + (x.get("Inciso") or "")
    for d in ("Montevideo", "Canelones", "Maldonado", "Rocha", "Treinta y Tres", "Cerro Largo", "Rivera", "Artigas", "Salto",
              "Paysandú", "Río Negro", "Soriano", "Colonia", "San José", "Flores", "Florida", "Durazno", "Lavalleja", "Tacuarembó"):
        if d.lower() in t.lower():
            return d
    return "Sin especificar"


def sueldo(s):
    m = re.search(r"\$\s?U?\s?([\d\.]{4,})", s or "")
    return int(m.group(1).replace(".", "")) if m else None


ll, seen = [], set()
for x in rows:
    if x["LlaId"] in seen:
        continue
    seen.add(x["LlaId"])
    puestos = sum(o.get("LlaOrgCntPue") or 0 for o in x.get("listaOrganismoCantPuestos") or [])
    ll.append({"id": x["LlaId"], "estado": x.get("LlaEstWeb") or "", "cargo": (x.get("CarNom") or "").strip(),
               "titulo": (x.get("LlaTit") or "").strip(), "organismo": (x.get("Inciso") or "").strip(),
               "unidad": (x.get("UnidadEjecutora") or "").strip(), "depto": depto(x), "tipo": x.get("TipTarDsc") or "",
               "vinculo": x.get("TipVinDsc") or "", "puestos": puestos, "sueldo_txt": (x.get("LlaRet") or "").strip(),
               "sueldo": sueldo(x.get("LlaRet")), "horario": (x.get("LlaCarHor") or "").strip(),
               "abre": x.get("LlaFchApeIns") or "", "cierra": x.get("LlaFchCieIns") or "", "num": x.get("LlaNum") or "",
               "url": LINK + x["LlaId"]})
ll.sort(key=lambda r: (r["estado"] != "Abierto", r["cierra"]))
os.makedirs(OUT, exist_ok=True)

with open(f"{OUT}/llamados.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(ll[0].keys()))
    w.writeheader()
    w.writerows(ll)

e = html.escape
items = "".join(f"<item><title>{e(r['cargo'])} — {e(r['organismo'])}</title><link>{r['url']}</link><guid>{r['url']}</guid>"
                f"<description>{e(r['estado'])}. Inscripción {r['abre']} a {r['cierra']}. {e(r['sueldo_txt'])}</description></item>"
                for r in sorted(ll, key=lambda r: -int(r["id"]))[:100])
open(f"{OUT}/feed.xml", "w", encoding="utf-8").write(
    f'<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>Empleos públicos UY · Pulso del Sur</title>'
    f'<link>https://www.uruguayconcursa.gub.uy/</link><description>Llamados abiertos y próximos de Uruguay Concursa</description>{items}</channel></rss>')

hoy = NOW.date().isoformat()
abiertos = [r for r in ll if r["estado"] == "Abierto"]
cierran = [r for r in abiertos if r["cierra"] and (dt.date.fromisoformat(r["cierra"]) - NOW.date()).days <= 7]
data = json.dumps(ll, ensure_ascii=False).replace("</", "<\\/")
tpl = open("empleos_template.html", encoding="utf-8").read()
page_html = (tpl.replace("{{DATA}}", data).replace("{{N}}", str(len(ll))).replace("{{ABIERTOS}}", str(len(abiertos)))
             .replace("{{PROXIMOS}}", str(len(ll) - len(abiertos))).replace("{{CIERRAN}}", str(len(cierran)))
             .replace("{{PUESTOS}}", f'{sum(r["puestos"] for r in ll):,}'.replace(",", "."))
             .replace("{{FECHA}}", NOW.strftime("%d/%m/%Y %H:%M")))
open(f"{OUT}/index.html", "w", encoding="utf-8").write(page_html)
json.dump({"generado": NOW.isoformat(timespec="minutes"), "llamados": ll}, open(f"{OUT}/llamados.json", "w"), ensure_ascii=False)
print(len(ll), "llamados ·", len(abiertos), "abiertos ·", len(cierran), "cierran en 7 días")
