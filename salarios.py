"""Salarios UY — Consejos de Salarios por grupo y subgrupo: actas, ajustes pactados, próximos aumentos, comparativa entre rubros y evolución.
Fuentes: índice de convenios colectivos de IMPO (https://www.impo.com.uy/convenios) y el texto de cada acta publicada en el Diario Oficial
(bases/otras-normas-originales). robots.txt de IMPO: 10 s entre pedidos; se leen hasta LIMITE actas nuevas por corrida y se guardan en caché.
Inflación: Unidad Indexada del BCU (data.json de Pulso del Sur).
No se publican nombres de delegados ni de personas: solo ajustes, fechas, vigencias y enlaces."""
import re, os, json, time, html, subprocess, unicodedata, datetime as dt
from zoneinfo import ZoneInfo

CA = "/root/.ccr/ca-bundle.crt"
NOW = dt.datetime.now(ZoneInfo("America/Montevideo"))
HOY = NOW.date()
OUT, CACHE, LIMITE = "site/salarios", "salarios/cache.json", int(os.environ.get("SAL_LIMITE", "60"))
os.makedirs(OUT, exist_ok=True)
os.makedirs("salarios", exist_ok=True)


def get(url):
    r = subprocess.run(["curl", "-sS", "-L", "--retry", "3", "--max-time", "90", "-A", "PulsoDelSur/1.0 (+https://sebauyy.github.io/pulso-del-sur/)"]
                       + (["--cacert", CA] if os.path.exists(CA) else []) + [url], capture_output=True)
    return r.stdout if r.returncode == 0 else b""


def tit(s):
    s = s.title()
    for w in ("De", "Del", "La", "Las", "Los", "Y", "O", "En", "Para", "Por", "Con", "Sin", "A", "El", "No", "Al"):
        s = re.sub(r"(?<=\S )" + w + r"(?= )", w.lower(), s)
    return s.replace("Glp", "GLP").replace("Ii", "II")


def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


def txt(x):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", x)).replace("\xa0", " ").split())


# ---------------- índice de convenios (IMPO) ----------------
def parse_index(s):
    secs = re.split(r'<a name="(e\d+)" id="e\d+"></a>', s)
    units = []
    for i in range(1, len(secs), 2):
        body = secs[i + 1].split('<a name="e')[0]
        grupo = txt(body.split("</h2>")[0])
        for tr in re.split(r"<tr[^>]*>", body, flags=re.I)[1:]:
            tr = re.split(r"</tr>", tr, flags=re.I)[0]
            tds = re.split(r"<td[^>]*>", tr, flags=re.I)[1:]
            if len(tds) < 2:
                continue
            sub = txt(tds[0])
            cap = txt(tds[1]) if "href" not in tds[1] else ""
            docs = [(txt(a[1]), re.sub(r"\s", "", a[0]).replace("http://", "https://")) for a in re.findall(r'href="([^"]+)"[^>]*>(.*?)</a>', tr, re.S)]
            if docs:
                units.append({"gid": secs[i], "grupo": grupo, "sub": sub, "cap": cap, "docs": docs})
    return units


def doc_info(lab, url):
    m = re.search(r"SN(\d{4})(\d{2})(\d{2})\d+-\d{4}", url)
    if m:
        return {"id": url.rsplit("/", 1)[-1], "tipo": "acta", "fecha": f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "anio": int(m.group(1)), "u": url}
    y = re.search(r"[-/](\d{3,4})(?:\.pdf)?$", url)
    anio = int(y.group(1)) if y else 0
    anio = anio + 2000 if anio < 100 else (2000 + anio % 1000 if anio < 1900 else anio)
    tipo = "decreto" if "/decretos/" in url else ("aviso" if "/avisos/" in url else "convenio")
    return {"id": url.rsplit("/", 1)[-1], "tipo": tipo, "fecha": "", "anio": anio, "u": url, "n": lab}


# ---------------- lectura de actas ----------------
MES = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12}
NIV = {"I": "1", "II": "2", "III": "3", "1": "1", "2": "2", "3": "3"}
PCT = r"(\d{1,2}(?:[.,]\d{1,3})?)\s*%"
FD = r"1\s*(?:ero|ro|°|º|o)?\s*(?:de\s+)?(ene\w*|feb\w*|mar\w*|abr\w*|may\w*|jun\w*|jul\w*|ago\w*|set\w*|sep\w*|oct\w*|nov\w*|dic\w*)\.?\s*(?:de\s+|del\s+)?(\d{4}|\d{2})\b"


def fch(m, y, d=1):
    y = int(y)
    y = y + 2000 if y < 100 else y
    mm = int(m) if str(m).isdigit() else MES.get(norm(m)[:3])
    try:
        return dt.date(y, mm, int(d)).isoformat()
    except (ValueError, TypeError):
        return ""


def parse_acta(raw):
    s = raw.decode("latin-1")
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())
    T = norm(t)
    tit = re.search(r"(CONSEJOS? DE SALARIOS\.?\s*GRUPO.{0,240}?)(?:Documento original|Fecha de Publicaci)", t, re.I)
    pub = re.search(r"Fecha de Publicaci[oó]n:\s*(\d{2})/(\d{2})/(\d{4})", t)
    o = {"titulo": (tit.group(1).strip() if tit else "")[:240], "publicado": fch(pub.group(2), pub.group(3), pub.group(1)) if pub else ""}
    v = re.search(r"entre el\s+(\d{1,2})\s*(?:ero|ro|°|º|o)?\s*(?:de\s+)?([a-zé]+)\s+(?:de\s+|del\s+)?(\d{4})\s+y el\s+(\d{1,2})\s*(?:°|º)?\s*(?:de\s+)?([a-zé]+)\s+(?:de\s+|del\s+)?(\d{4})", t, re.I)
    if v:
        o["desde"], o["hasta"] = fch(v.group(2), v.group(3), v.group(1)), fch(v.group(5), v.group(6), v.group(4))
    aj = {}
    for m in re.finditer(r"((?:" + FD + r"\s*){2,8})", t, re.I):          # A) tabla de ajustes por nivel
        fechas = [fch(a, b) for a, b in re.findall(FD, m.group(1), re.I)]
        resto = t[m.end():m.end() + 700]
        for nv, vals in re.findall(r"(?:Nivel|Franja)(?:\s+salarial)?\s*(III|II|I|1|2|3)\b[^%\d]{0,20}((?:\d{1,2}(?:[.,]\d{1,3})?\s*%\s*\*?\s*){2,8})", resto, re.I):
            ps = [float(x.replace(",", ".")) for x in re.findall(PCT, vals)]
            if len(ps) == len(fechas):
                for fe, p in zip(fechas, ps):
                    if fe:
                        aj.setdefault(fe, {})[NIV[nv.upper()]] = p
    if not aj:                                                              # B) texto por fecha
        heads = sorted([(m.start(), fch(m.group(1), m.group(2))) for m in re.finditer(r"(?:ajust|increment|aument)\w*[^.%]{0,90}?(?:(?:al|a partir del?|del?|el)\s+)?" + FD, t, re.I)]
                       + [(m.start(), fch(m.group(1), m.group(2))) for m in re.finditer(r"a partir del?\s+" + FD + r"(?=[^.%]{0,80}?(?:increment|ajust|aument))", t, re.I)])
        for k, (pos, fe) in enumerate(heads):
            if not fe or fe in aj:
                continue
            win = t[pos:heads[k + 1][0] if k + 1 < len(heads) else pos + 900][:900]
            lv = {}
            for nv, p in re.findall(r"(?:nivel|franja)(?:\s+salarial)?\s*(III|II|I|1|2|3)\b[^%]{0,130}?" + PCT, win, re.I):
                lv.setdefault(NIV[nv.upper()], float(p.replace(",", ".")))
            if lv:
                aj[fe] = lv
                continue
            m = re.search(r"(?:ajust|increment|aument)\w*[^%]{0,200}?" + PCT, win, re.I)
            if m and re.search(r"IPC|inflaci", win[:m.start(1)], re.I) and not re.search(r"\d[.,]\d+\s*%", win[:m.start(1)]):
                aj[fe] = {"ipc": True}
            elif m and not re.search(r"inflaci[oó]n (?:verificada|observada|de)|diferencial|imputad", win[max(0, m.start(1) - 80):m.start(1)], re.I):
                aj[fe] = {"g": float(m.group(1).replace(",", "."))}
    o["ajustes"] = sorted(aj.items())
    o["correctivo"] = "CORRECTIV" in T
    return o


# ---------------- corrida ----------------
idx_raw = get("https://www.impo.com.uy/convenios")
units = parse_index(idx_raw.decode("latin-1")) if idx_raw else []
if len(units) < 100:
    raise SystemExit("salarios: no se pudo leer el índice de convenios de IMPO")
cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
for u in units:
    u["docs"] = sorted((doc_info(*d) for d in u["docs"]), key=lambda d: (d["fecha"] or str(d["anio"]), d["id"]), reverse=True)
# actas a leer: las de 2023 en adelante, más nuevas primero
pend = sorted({d["id"]: d for u in units for d in u["docs"] if d["tipo"] == "acta" and d["anio"] >= 2023 and d["id"] not in cache}.values(),
              key=lambda d: d["fecha"], reverse=True)
for d in pend[:LIMITE]:
    raw = get(d["u"])
    time.sleep(10)
    if len(raw) < 3000:
        continue
    try:
        cache[d["id"]] = parse_acta(raw)
    except Exception as ex:
        print("salarios: no se pudo leer", d["id"], ex)
json.dump(cache, open(CACHE, "w"), ensure_ascii=False, separators=(",", ":"))

# inflación: Unidad Indexada (BCU)
ui = {}
try:
    ui = dict(json.load(open("data.json"))["paises"]["UY"]["ui"])
except Exception:
    pass

out, proximos = [], []
for u in units:
    nombre = (u["sub"] + (" · " + u["cap"] if u["cap"] and u["cap"] != u["sub"] else "")) or "General"
    actas = [dict(cache[d["id"]], id=d["id"], u=d["u"], fecha=d["fecha"]) for d in u["docs"] if d["id"] in cache]
    vig = next((a for a in actas if a.get("ajustes")), None)
    aj = {}
    for a in reversed(actas):                       # serie de ajustes de todas las actas leídas (las más nuevas pisan)
        for fe, v in a.get("ajustes", []):
            aj[fe] = v
    serie = sorted(aj.items())
    for fe, v in serie:
        if HOY.isoformat() <= fe <= (HOY + dt.timedelta(days=200)).isoformat():
            proximos.append({"f": fe, "g": u["gid"], "n": nombre, "v": v, "u": vig["u"] if vig else ""})
    out.append({"g": u["gid"], "grupo": tit(re.sub(r"^GRUPO\s*", "", u["grupo"])), "n": tit(nombre),
                "vig": {k: vig.get(k) for k in ("desde", "hasta", "publicado", "correctivo", "u", "titulo")} if vig else None,
                "aj": serie, "docs": [{k: d[k] for k in ("tipo", "anio", "fecha", "u", "id")} for d in u["docs"]],
                "nact": sum(1 for d in u["docs"] if d["tipo"] == "acta"), "ult": max((d["fecha"] or str(d["anio"]) for d in u["docs"]), default="")})
proximos.sort(key=lambda x: x["f"])
uis = sorted(ui.items())
data = {"u": out, "prox": proximos, "ui": uis[-1800:][::7] if uis else [], "leidas": len(cache), "pend": max(0, len(pend) - LIMITE),
        "fecha": NOW.strftime("%d/%m/%Y")}
json.dump(data, open(f"{OUT}/datos.json", "w"), ensure_ascii=False)
tpl = open("salarios_template.html", encoding="utf-8").read()
open(f"{OUT}/index.html", "w", encoding="utf-8").write(
    tpl.replace("{{DATA}}", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")).replace("{{FECHA}}", data["fecha"]))
print("salarios:", len(units), "unidades ·", len(cache), "actas leídas ·", data["pend"], "pendientes ·", len(proximos), "ajustes próximos")
