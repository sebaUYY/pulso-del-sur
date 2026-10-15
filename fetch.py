"""Pulso del Sur — descarga indicadores de fuentes oficiales/públicas, valida frescura y calcula derivados.
Salida: data.json. Corre igual en local y en GitHub Actions."""
import json, os, re, datetime as dt, subprocess, xml.etree.ElementTree as ET
from collections import defaultdict
from zoneinfo import ZoneInfo

UY_TZ = ZoneInfo("America/Montevideo")       # el servidor de GitHub corre en UTC
TODAY = dt.datetime.now(UY_TZ).date()
HIST_START = dt.date(2024, 1, 1)          # histórico para cierres mensuales y tipo de cambio real
CA = "/root/.ccr/ca-bundle.crt"           # solo existe en el entorno de Claude; en Actions se usan los certificados del sistema


def get(url, data=None, headers=(), timeout=40, tries=3):
    err = ""
    for _ in range(tries):
        cmd = ["curl", "-sS", "-L", "-m", str(timeout), "-A", "Mozilla/5.0 (PulsoDelSur data bot)"]
        if os.path.exists(CA):
            cmd += ["--cacert", CA]
        for h in headers:
            cmd += ["-H", h]
        if data:
            cmd += ["--data", data]
        r = subprocess.run(cmd + [url], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
        err = r.stderr.strip()[:160]
    raise RuntimeError(f"no respondió ({err})")


def getj(url, tries=3, **kw):
    for i in range(tries):   # algunas APIs devuelven a veces una página vacía o de error: reintentar
        try:
            return json.loads(get(url, **kw))
        except (ValueError, RuntimeError):
            if i == tries - 1:
                raise


# ---------- BCU (Uruguay) ----------
def bcu(codes, desde, hasta):
    """El servicio acepta ~1 año por consulta: se parte en tramos."""
    out = defaultdict(list)
    a = desde
    while a <= hasta:
        b = min(a + dt.timedelta(days=300), hasta)
        body = ('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:cot="Cotiza">'
                '<soapenv:Body><cot:wsbcucotizaciones.Execute><cot:Entrada><cot:Moneda>'
                + "".join(f"<cot:item>{c}</cot:item>" for c in codes) +
                f'</cot:Moneda><cot:FechaDesde>{a}</cot:FechaDesde><cot:FechaHasta>{b}</cot:FechaHasta>'
                '<cot:Grupo>0</cot:Grupo></cot:Entrada></cot:wsbcucotizaciones.Execute></soapenv:Body></soapenv:Envelope>')
        ns = {"c": "Cotiza"}
        for intento in range(4):   # el servicio a veces devuelve una respuesta vacía: reintentar
            x = get("https://cotizaciones.bcu.gub.uy/wscotizaciones/servlet/awsbcucotizaciones", body,
                    ["Content-Type: text/xml; charset=utf-8", 'SOAPAction: "Cotizaaction/AWSBCUCOTIZACIONES.Execute"'])
            datos = list(ET.fromstring(x).iter("{Cotiza}datoscotizaciones.dato"))
            if datos:
                break
        else:
            raise RuntimeError(f"BCU sin datos para {a}..{b}")
        for d in datos:
            out[d.find("c:Moneda", ns).text].append((d.find("c:Fecha", ns).text, float(d.find("c:TCV", ns).text)))
        a = b + dt.timedelta(days=1)
    return {k: sorted(set(v)) for k, v in out.items()}


def uy():
    # una moneda por consulta: con varias, el servicio corta la respuesta en rangos largos
    fx = bcu([2225], HIST_START, TODAY - dt.timedelta(days=1))["2225"]
    ui = bcu([9800], dt.date(2020, 1, 1), TODAY - dt.timedelta(days=1))["9800"]   # también alimenta la calculadora
    last = ui[-1]
    d0 = dt.date.fromisoformat(last[0]).replace(year=dt.date.fromisoformat(last[0]).year - 1).isoformat()
    prev = [x for x in ui if x[0] <= d0][-1]
    # índice mensual de precios aproximado por la UI del día 1 de cada mes
    cpi = {}
    for f, v in ui:
        cpi.setdefault(f[:7], v)
    return {"nombre": "Uruguay", "moneda": "UYU", "fx": [x for x in fx if x[0] >= str(HIST_START)],
            "fx_fuente": "BCU – dólar billete interbancario",
            "infl": round((last[1] / prev[1] - 1) * 100, 2), "infl_ref": f"UI al {last[0]}",
            "infl_fuente": "BCU – variación interanual de la Unidad Indexada (aproxima el IPC)",
            "cpi_m": cpi, "extra": {"UI": last}, "ui": ui}


# ---------- Argentina ----------
def ar():
    h = getj("https://api.argentinadatos.com/v1/cotizaciones/dolares/oficial")
    b = getj("https://api.argentinadatos.com/v1/cotizaciones/dolares/blue")
    # la fuente repite el valor en fines de semana: solo días hábiles (lun-vie)
    fx = [(r["fecha"], float(r["venta"])) for r in h
          if r["fecha"] >= str(HIST_START) and dt.date.fromisoformat(r["fecha"]).weekday() < 5]
    ip = getj("https://apis.datos.gob.ar/series/api/series/?ids=148.3_INIVELNAL_DICI_M_26&start_date=2023-01-01&limit=1000")["data"]
    cpi = {f[:7]: v for f, v in ip}
    lk = max(cpi); pk = f"{int(lk[:4]) - 1}{lk[4:]}"
    return {"nombre": "Argentina", "moneda": "ARS", "fx": fx, "fx_fuente": "ArgentinaDatos – dólar oficial, venta (días hábiles)",
            "infl": round((cpi[lk] / cpi[pk] - 1) * 100, 2), "infl_ref": f"IPC {lk}", "infl_fuente": "INDEC vía datos.gob.ar",
            "cpi_m": cpi, "extra": {"blue": (b[-1]["fecha"], b[-1]["venta"])}}


# ---------- Brasil ----------
def br():
    di = lambda d: dt.datetime.strptime(d, "%d/%m/%Y").date().isoformat()
    sgs = lambda c, a, b: getj(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{c}/dados?formato=json&dataInicial={a:%d/%m/%Y}&dataFinal={b:%d/%m/%Y}")
    fx = [(di(r["data"]), float(r["valor"])) for r in sgs(1, HIST_START, TODAY)]
    ip12 = getj("https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json")[-1]
    m = sgs(433, dt.date(2023, 1, 1), TODAY)                     # IPCA variación mensual
    cpi, idx = {}, 100.0
    for r in m:
        idx *= 1 + float(r["valor"]) / 100
        cpi[di(r["data"])[:7]] = round(idx, 4)
    # Focus: mediana del mercado para el cierre de este año y el próximo
    exp = {}
    for ind in ["Câmbio", "IPCA"]:
        q = (f"https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais?"
             f"$top=20&$orderby=Data%20desc&$format=json&$select=Indicador,Data,DataReferencia,Mediana,numeroRespondentes,baseCalculo"
             f"&$filter=Indicador%20eq%20'{ind.replace('â', '%C3%A2')}'%20and%20baseCalculo%20eq%200")
        for r in getj(q)["value"]:
            y = r["DataReferencia"]
            if y in (str(TODAY.year), str(TODAY.year + 1)) and (ind, y) not in exp:
                exp[(ind, y)] = {"indicador": "Dólar fin de año" if ind == "Câmbio" else "Inflación del año (%)",
                                 "anio": y, "mediana": r["Mediana"], "fecha": r["Data"], "n": r["numeroRespondentes"]}
    return {"nombre": "Brasil", "moneda": "BRL", "fx": fx, "fx_fuente": "Banco Central do Brasil – PTAX venta",
            "infl": float(ip12["valor"]), "infl_ref": f"IPCA {di(ip12['data'])[:7]}", "infl_fuente": "IBGE vía BCB – IPCA 12 meses",
            "cpi_m": cpi, "expectativas": sorted(exp.values(), key=lambda e: (e["indicador"], e["anio"])),
            "exp_fuente": "BCB – Encuesta Focus (mediana, todos los participantes)"}


# ---------- Perú ----------
MES = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7, "Ago": 8, "Set": 9, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}


def pe():
    fx = []
    a = HIST_START
    while a <= TODAY:
        b = min(a + dt.timedelta(days=360), TODAY)
        j = getj(f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04640PD/json/{a}/{b}")
        for p in j["periods"]:
            v = p["values"][0]
            if v in ("n.d.", ""):
                continue
            dd, mm, yy = re.match(r"(\d+)\.(\w+)\.(\d+)", p["name"]).groups()
            fx.append((dt.date(2000 + int(yy), MES[mm], int(dd)).isoformat(), float(v)))
        a = b + dt.timedelta(days=1)
    ji = getj(f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PN01273PM/json/{TODAY.year - 1}-1/{TODAY.year}-12")
    last = [p for p in ji["periods"] if p["values"][0] not in ("n.d.", "")][-1]
    return {"nombre": "Perú", "moneda": "PEN", "fx": sorted(set(fx)), "fx_fuente": "BCRP – TC sistema bancario SBS, venta",
            "infl": round(float(last["values"][0]), 2), "infl_ref": f"IPC Lima {last['name']}",
            "infl_fuente": "BCRP – IPC Lima Metropolitana, var. 12 meses"}


# ---------- Colombia ----------
def co():
    j = getj(f"https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=2000&$order=vigenciadesde%20DESC"
             f"&$where=vigenciadesde%20%3E=%20'{HIST_START}T00:00:00'")
    # la TRM tiene valor también en fines de semana: solo días hábiles
    # cada fila vale desde..hasta (un viernes puede cubrir hasta el lunes): se expande y se dejan días hábiles
    s = {}
    for r in j:
        d, h = dt.date.fromisoformat(r["vigenciadesde"][:10]), dt.date.fromisoformat(r["vigenciahasta"][:10])
        while d <= min(h, TODAY):
            if d.weekday() < 5:
                s[str(d)] = float(r["valor"])
            d += dt.timedelta(days=1)
    return {"nombre": "Colombia", "moneda": "COP", "fx": sorted(s.items()), "fx_fuente": "Superfinanciera – TRM (datos.gov.co), días hábiles",
            "infl": None, "infl_ref": "", "infl_fuente": "pendiente (DANE)"}


# ---------- México ----------
def mx():
    j = getj(f"https://api.frankfurter.dev/v1/{HIST_START}..?from=USD&to=MXN")
    return {"nombre": "México", "moneda": "MXN", "fx": sorted((k, v["MXN"]) for k, v in j["rates"].items() if k >= str(HIST_START)),
            "fx_fuente": "BCE (referencia) vía Frankfurter – no es el FIX de Banxico",
            "infl": None, "infl_ref": "", "infl_fuente": "pendiente (token gratuito Banxico SIE)"}


# ---------- Chile ----------
def cl():
    s = {}
    for y in range(HIST_START.year, TODAY.year + 1):
        for r in getj(f"https://mindicador.cl/api/dolar/{y}", timeout=25)["serie"]:
            s[r["fecha"][:10]] = r["valor"]
    return {"nombre": "Chile", "moneda": "CLP", "fx": sorted(s.items()),
            "fx_fuente": "Banco Central de Chile – dólar observado (vía mindicador.cl)",
            "infl": None, "infl_ref": "", "infl_fuente": "pendiente"}


ORDER = ["UY", "AR", "BR", "CL", "PE", "CO", "MX"]
FUNCS = {"UY": uy, "AR": ar, "BR": br, "CL": cl, "PE": pe, "CO": co, "MX": mx}
NAMES = {"UY": "Uruguay", "AR": "Argentina", "BR": "Brasil", "CL": "Chile", "PE": "Perú", "CO": "Colombia", "MX": "México"}


def monthly(fx):
    """Cierre (último día hábil con dato) y promedio de días hábiles por mes calendario cerrado."""
    g = defaultdict(list)
    for f, v in fx:
        g[f[:7]].append((f, v))
    cur = str(TODAY)[:7]
    out = {}
    for m, rows in sorted(g.items()):
        if m >= cur:
            continue
        out[m] = {"cierre": rows[-1][1], "fecha_cierre": rows[-1][0],
                  "promedio": round(sum(v for _, v in rows) / len(rows), 6), "dias": len(rows)}
    return out


def tcr(p_uy, p_x):
    """Tipo de cambio real bilateral UY vs X (índice ene-2024=100). Sube = Uruguay se abarata frente a X."""
    m_uy, m_x = monthly(p_uy["fx"]), monthly(p_x["fx"])
    out = {}
    for m in sorted(set(m_uy) & set(m_x) & set(p_uy["cpi_m"]) & set(p_x["cpi_m"])):
        e = m_uy[m]["promedio"] / m_x[m]["promedio"]          # pesos uruguayos por unidad de moneda X
        out[m] = e * p_x["cpi_m"][m] / p_uy["cpi_m"][m]
    if not out:
        return {}
    base = out.get("2024-01") or out[min(out)]
    return {m: round(v / base * 100, 2) for m, v in out.items()}


def main():
    res = {"generado": dt.datetime.now(UY_TZ).replace(tzinfo=None).isoformat(timespec="minutes"), "paises": {}, "errores": []}
    for k in ORDER:
        try:
            res["paises"][k] = FUNCS[k]()
        except Exception as e:
            res["errores"].append(f"{k}: {e}")
    for k, p in res["paises"].items():
        last = dt.date.fromisoformat(p["fx"][-1][0])
        p["dias_desde_ultimo"] = (TODAY - last).days
        p["mensual"] = monthly(p["fx"])
        if p["dias_desde_ultimo"] > 5:
            res["errores"].append(f"{k}: último dato de tipo de cambio es del {last}")
    P = res["paises"]
    res["tcr"] = {}
    for k in ["AR", "BR"]:
        if "UY" in P and k in P:
            res["tcr"][k] = tcr(P["UY"], P[k])
    for p in P.values():
        p.pop("cpi_m", None)
    json.dump(res, open("data.json", "w"), ensure_ascii=False, indent=1)
    print("OK:", list(P), "\nERRORES:", res["errores"])


if __name__ == "__main__":
    main()
