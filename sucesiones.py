"""Sucesiones UY — edictos de apertura de sucesiones, herencias yacentes e inmuebles en juicio de prescripción, del Diario Oficial (IMPO).
Fuente: PDF diario de avisos, de acceso libre: https://www.impo.com.uy/diariooficial/AAAA/MM/DD/avisos.pdf (robots.txt: 10 s entre pedidos).
Privacidad: no se publican nombres de herederos, promotores ni otras personas vivas; los nombres de causantes de sucesiones comunes
no se publican: el buscador compara hashes de pares de palabras y muestra solo juzgado, expediente y enlace al Diario Oficial. Las herencias yacentes sí muestran el causante, porque el
edicto busca justamente a herederos e interesados.
Uso: python sucesiones.py            (baja los días que falten, hasta 6 hábiles atrás)
     python sucesiones.py a.pdf ...  (procesa PDFs locales; el nombre debe empezar con AAAAMMDD_)"""
import re, os, sys, json, time, html, hashlib, subprocess, unicodedata, itertools, datetime as dt
from zoneinfo import ZoneInfo
import pymupdf

CA = "/root/.ccr/ca-bundle.crt"
NOW = dt.datetime.now(ZoneInfo("America/Montevideo"))
HOY = NOW.date()
OUT, HIST = "site/sucesiones", "sucesiones/historico.json"
os.makedirs(OUT, exist_ok=True)
os.makedirs("sucesiones/tmp", exist_ok=True)
DEPS = ["Artigas", "Canelones", "Cerro Largo", "Colonia", "Durazno", "Flores", "Florida", "Lavalleja", "Maldonado", "Montevideo",
        "Paysandú", "Río Negro", "Rivera", "Rocha", "Salto", "San José", "Soriano", "Tacuarembó", "Treinta y Tres"]


def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


DEPN = {norm(d): d for d in DEPS}
MES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SETIEMBRE": 9,
       "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}


def curl(url, out):
    r = subprocess.run(["curl", "-sS", "-L", "--retry", "3", "--max-time", "180", "-A", "PulsoDelSur/1.0 (+https://sebauyy.github.io/pulso-del-sur/)",
                        "-o", out, "-w", "%{http_code}"] + (["--cacert", CA] if os.path.exists(CA) else []) + [url], capture_output=True, text=True)
    return r.stdout.strip() == "200" and os.path.getsize(out) > 20000


def leer(pdf):
    """Texto en orden de lectura (3 columnas), con el número de página del PDF en cada línea."""
    lines = []
    for pno, p in enumerate(pymupdf.open(pdf)):
        W = p.rect.width
        bl = [b for b in p.get_text("blocks") if b[4].strip()]
        col = lambda b: 0 if (b[0] + b[2]) / 2 < W * 0.37 else (1 if (b[0] + b[2]) / 2 < W * 0.63 else 2)
        bl.sort(key=lambda b: (col(b) if b[2] - b[0] < W * 0.6 else -1, b[1]))
        for b in bl:
            for ln in b[4].split("\n"):
                if ln.strip():
                    lines.append((pno + 1, ln.strip()))
    return lines


def espaciado(s):
    # "M A R T Í N E Z N E G R O N" -> "MARTÍNEZ NEGRON" no es recuperable con certeza: se juntan las letras sueltas
    return re.sub(r"\b(?:\w ){3,}\w\b", lambda m: m.group(0).replace(" ", ""), s)


TRAILER = re.compile(r"^\d\d\)\s*(?:\$\s*[\d.]+|\([^)]{2,20}\))\s*(\d+)/p\s+(\d+)\s+(\w{3})\s*(\d\d)-\s*(\w{3})\s*(\d\d)")
FECHA = re.compile(r"(\d{1,2}) de (\w+) de (\d{4})")
IUE = re.compile(r"IUE\s*([\d]+\s*-\s*[\d]+\s*/\s*\d{4})")
ABR = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7, "Ago": 8, "Set": 9, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}


def fecha_txt(s):
    m = None
    for m in FECHA.finditer(s):
        pass
    if not m:
        return ""
    try:
        return dt.date(int(m.group(3)), MES.get(norm(m.group(2)), 0), int(m.group(1))).isoformat()
    except ValueError:
        return ""


def hasta(abr, dd, ref):
    try:
        d = dt.date(ref.year, ABR[abr[:3].title()], int(dd))
        return (d.replace(year=d.year + 1) if d < ref - dt.timedelta(days=60) else d).isoformat()
    except (KeyError, ValueError):
        return ""


def procesar(pdf, dia):
    lines = leer(pdf)
    url = f"https://www.impo.com.uy/diariooficial/{dia:%Y/%m/%d}/avisos.pdf"
    out, body, dep, juz, turno, abierto = [], [], "", "", "", False
    for pg, ln in lines:
        n = norm(ln).strip(" .,")
        if n in DEPN:
            dep, juz, turno = DEPN[n], "", ""
        if n.startswith("JUZGADO"):
            juz, turno, abierto = ln, "", True
        elif re.match(r"^[A-Z]+ TURNO$", n):
            turno, abierto = ln, False
        elif abierto and re.match(r"^(INSTANCIA|DE |DEPARTAMENTAL|LETRADO|FAMILIA|COSTA|PAZ|CAPITAL|ESPECIALIZAD)", n):
            juz += " " + ln
        else:
            abierto = False
        m = TRAILER.match(ln)
        if not m:
            body.append((pg, ln))
            continue
        if body:
            out.append({"txt": " ".join(x[1] for x in body), "lines": [x[1] for x in body], "pg": body[0][0], "dep": dep,
                        "sede": " ".join(f"{juz} {turno}".split()).title(),
                        "aviso": m.group(2), "hasta": hasta(m.group(5), m.group(6), dia), "pub": m.group(1)})
        body = []
    recs = []
    for a in out:
        t = espaciado(" ".join(a["txt"].split()))
        T = norm(t)
        iue = IUE.search(t)
        base = {"aviso": a["aviso"], "iue": re.sub(r"\s", "", iue.group(1)) if iue else "", "dep": a["dep"], "fecha": fecha_txt(t),
                "hasta": a["hasta"], "pdf": f"{url}#page={a['pg']}", "visto": dia.isoformat()}
        sd = re.search(r"Juez(?:a)?\s+(?:Letrad[oa]|de Paz)[^,:]{3,90}?(?:Turno|Int\.?|Departamental[^,:]{0,40})", t)
        base["sede"] = " ".join((sd.group(0) if sd else a["sede"]).split())[:110]
        if "YACENTE" in T:
            m = re.search(r"yacente\s+de\s+la\s+sucesi[oó]n\s+de(?:l causante)?\s+(.+?),\s+(?:emplaz|cit|se\s)", t, re.I) or \
                re.search(r"[“\"]\s*([^”\"]+?)\s*-?\s*HERENCIA\s+YACENTE", t, re.I)
            if m:
                recs.append({**base, "tipo": "yacente", "causante": m.group(1).strip(" ,.-").title()[:90]})
        elif "PRESCRIPCI" in T and "ADQUISITIVA" in T and re.search(r"INMUEBLE|SOLAR|PADRON|TERRENO|FRACCION|PREDIO|CAMPO", T) \
                and not re.search(r"BIEN MUEBLE|VEHICULO|AUTOMOTOR", T):
            pads = []
            for mm in re.finditer(r"(?:EMPADRONAD[OA]S?\s+CON\s+(?:EL|LOS)\s+N\S*\s*|PADRON(?:ES)?\s*(?:N\S*\s*)?)([\d.]{1,9})", T):
                antes = T[max(0, mm.start() - 40):mm.start()]
                if re.search(r"LIND|MAYOR AREA|ANTES|ANTERIOR", antes):
                    continue
                pv = mm.group(1).replace(".", "").strip()
                if pv and pv not in pads:
                    pads.append(pv)
            loc = re.search(r"(?:LOCALIDAD CATASTRAL|CIUDAD|BALNEARIO|PUEBLO|VILLA)\s+(?:DE\s+)?([A-Z][A-Z ]{2,30}?)(?:[,.(]|\s+ZONA|\s+DEPARTAMENTO|\s+EMPADRON|\s+Y\s)", T)
            dp = re.search(r"DEPARTAMENTO\s+DE\s+([A-Z ]{4,16}?)(?:[,.]|\s+(?:ZONA|LOCALIDAD|CIUDAD|EMPADRON|SEGUN|CON|QUE|Y)\b)", T)
            zona = "rural" if "RURAL" in T else ("urbana" if re.search(r"URBAN|SOLAR", T) else "")
            recs.append({**base, "tipo": "prescripcion", "padrones": pads[:4], "zona": zona,
                         "localidad": loc.group(1).strip().title() if loc and not re.match(r"Y\b|DEPARTAMENTO", loc.group(1).strip()) else "",
                         "dep": base["dep"] or DEPN.get((dp.group(1).strip() if dp else ""), "")})
        elif "(IUE" in t.upper() and len(t) < 480 and "EDICTO" not in T and not re.search(r"INTIMA|REPUDI|DIVORCIO|INCAPAC|AUSENCIA|CURADOR", T):
            # apertura de sucesión (lista): el/los causantes son las líneas justo antes de "(IUE"
            L = a["lines"]
            k = next(i for i, x in enumerate(L) if "(IUE" in x.upper())
            partes = [L[k][:L[k].upper().find("(IUE")]]
            for x in reversed(L[:k]):
                nx = norm(x).strip(" .,")
                if re.search(r"TURNO$|^JUZGADO|^INSTANCIA|PUBLICACION|CORRESPONDIENTE|ACTUARI|^DE |^\(LEY|DIAS,|INTERESADOS|SEGUIDAMENTE|APERTURA|JUECES|PODER JUDICIAL|EMPLAZAN|TERMINO", nx) or nx in DEPN or re.search(r"\d", nx):
                    break
                partes.insert(0, x)
            cau = re.sub(r"^\W+|\W+$", "", espaciado(" ".join(" ".join(partes).split())))
            if 3 < len(cau) < 140 and not re.search(r"\d", cau) and len(cau.split()) <= 14:
                recs.append({**base, "tipo": "sucesion", "causante": cau})
    return recs


def tokens(s):
    return sorted({w for w in re.findall(r"[A-Z]{2,}", norm(s)) if w not in ("DE", "DEL", "LA", "LOS", "LAS", "Y", "O", "U", "OTRO", "OTROS", "OTRA", "SUCESION")})


def h(a, b):
    return hashlib.sha256(f"pds|{a}|{b}".encode()).hexdigest()[:10]


# ---------------- bajar los días que falten ----------------
hist = json.load(open(HIST)) if os.path.exists(HIST) else {"dias": [], "recs": {}}
pdfs = []
if sys.argv[1:]:
    for f in sys.argv[1:]:
        pdfs.append((f, dt.datetime.strptime(os.path.basename(f)[:8], "%Y%m%d").date()))
else:
    dias = [HOY - dt.timedelta(days=i) for i in range(0, 9) if (HOY - dt.timedelta(days=i)).weekday() < 5][:6]
    for d in sorted(dias):
        if d.isoformat() in hist["dias"]:
            continue
        f = f"sucesiones/tmp/{d:%Y%m%d}_avisos.pdf"
        ok = curl(f"https://www.impo.com.uy/diariooficial/{d:%Y/%m/%d}/avisos.pdf", f)
        time.sleep(10)
        if ok:
            pdfs.append((f, d))
nuevos = 0
for f, d in pdfs:
    try:
        rs = procesar(f, d)
    except Exception as ex:
        print("sucesiones: no se pudo leer", f, ex)
        continue
    for r in rs:
        k = r["aviso"]
        if k not in hist["recs"]:
            nuevos += 1
            if r["tipo"] == "sucesion":
                # el histórico queda en un repositorio público: del nombre se guardan solo los hashes del buscador
                r["h"] = sorted({h(a, b) for a, b in itertools.combinations(tokens(r.pop("causante")), 2)})
            hist["recs"][k] = r
    if d.isoformat() not in hist["dias"]:
        hist["dias"].append(d.isoformat())
    print("sucesiones:", d, len(rs), "avisos útiles")
# conservar dos años
lim = (HOY - dt.timedelta(days=730)).isoformat()
hist["recs"] = {k: v for k, v in hist["recs"].items() if v["visto"] >= lim}
hist["dias"] = sorted(x for x in hist["dias"] if x >= lim)
json.dump(hist, open(HIST, "w"), ensure_ascii=False, separators=(",", ":"))

# ---------------- salida ----------------
R = list(hist["recs"].values())
indice = []
for r in R:
    if r["tipo"] != "sucesion":
        continue
    # sin el nombre: solo hashes de pares de palabras, para que el buscador encuentre el edicto sin exponer una lista de nombres
    indice.append({"h": r["h"], "d": r["dep"], "s": r["sede"],
                   "i": r["iue"], "f": r["fecha"], "p": r["pdf"], "v": r["visto"]})
yac = sorted((r for r in R if r["tipo"] == "yacente" and r["visto"] >= (HOY - dt.timedelta(days=120)).isoformat()), key=lambda r: r["visto"], reverse=True)
pre = sorted((r for r in R if r["tipo"] == "prescripcion"), key=lambda r: r["visto"], reverse=True)
suc = [r for r in R if r["tipo"] == "sucesion"]
mes = (HOY - dt.timedelta(days=30)).isoformat()
porDep = {}
for r in suc:
    if r["visto"] >= mes:
        porDep[r["dep"] or "Sin dato"] = porDep.get(r["dep"] or "Sin dato", 0) + 1
json.dump(indice, open(f"{OUT}/indice.json", "w"), separators=(",", ":"))
data = {"yacentes": yac, "prescripciones": pre, "porDep": porDep,
        "kpi": {"suc30": sum(porDep.values()), "pre": len(pre), "total": len(suc), "desde": min(hist["dias"]) if hist["dias"] else ""}}
json.dump(data, open(f"{OUT}/datos.json", "w"), ensure_ascii=False)
tpl = open("sucesiones_template.html", encoding="utf-8").read()
open(f"{OUT}/index.html", "w", encoding="utf-8").write(
    tpl.replace("{{DATA}}", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    .replace("{{FECHA}}", NOW.strftime("%d/%m/%Y")))
print("sucesiones:", nuevos, "nuevos ·", len(suc), "sucesiones ·", len(yac), "yacentes ·", len(pre), "inmuebles en prescripción")
