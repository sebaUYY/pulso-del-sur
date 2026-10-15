"""Importá Fácil — costo de importar a Uruguay desde fuera del Mercosur y oportunidades de venta al Estado.
Uso (una vez por actualización del arancel o del año de compras):
  python3 impo.py <Arancel Nacional.xlsx> <dir OCDS año> static/importar/
Genera static/importar/ncm.json (arancel con descripción completa) y oportunidades.json (lo que el Estado compra seguido).
La página static/importar/index.html se publica tal cual (cálculo en el navegador)."""
import sys, json, re, glob, collections, statistics as st, os
import openpyxl

if sys.argv[1:2] == ["--auto"]:
    # modo GitHub Actions: baja el arancel del MEF y el último año completo de compras de ARCE
    import subprocess, zipfile, datetime as dt
    CA = "/root/.ccr/ca-bundle.crt"
    def curl(url, out):
        subprocess.run(["curl", "-sS", "-L", "--retry", "4", "--max-time", "1200"] + (["--cacert", CA] if os.path.exists(CA) else []) + ["-o", out, url], check=True)
    os.makedirs("impo/tmp", exist_ok=True)
    curl("https://www.gub.uy/ministerio-economia-finanzas/sites/ministerio-economia-finanzas/files/2025-02/Arancel%20Nacional_Febrero%202025_0.xlsx", "impo/tmp/an.xlsx")
    pk = json.loads(subprocess.run(["curl", "-sS", "--max-time", "120"] + (["--cacert", CA] if os.path.exists(CA) else []) +
                                   ["https://catalogodatos.gub.uy/api/3/action/package_show?id=arce-datos-historicos-de-compras"], capture_output=True, text=True).stdout)["result"]
    anios = sorted((r for r in pk["resources"] if re.search(r"Compras (\d{4})", r["name"]) and r["url"].endswith(".zip")),
                   key=lambda r: re.search(r"(\d{4})", r["name"]).group(1))
    curl(anios[-1]["url"], "impo/tmp/ocds.zip")
    zipfile.ZipFile("impo/tmp/ocds.zip").extractall("impo/tmp/ocds")
    jsons = glob.glob("impo/tmp/ocds/**/a-*.json", recursive=True)
    AN, SRC, OUT = "impo/tmp/an.xlsx", os.path.dirname(jsons[0]), "impo"
else:
    AN, SRC, OUT = sys.argv[1:4]
os.makedirs(OUT, exist_ok=True)

# ---------- 1) Arancel nacional: código → descripción completa, TGA extrazona (E/Z), clase (BK/BIT) ----------
ws = openpyxl.load_workbook(AN, read_only=True).worksheets[0]
desc, leaves = {}, []
for r in ws.iter_rows(values_only=True):
    code, d = r[0], r[1]
    if not isinstance(code, str) or not d or not re.match(r"^\d{2}\.?\d", code.strip()):
        continue
    code = code.strip()
    digits = re.sub(r"\D", "", code)
    d = re.sub(r"^[\s\-–]+", "", str(d)).strip().rstrip(":").strip()
    if len(digits) == 10 and r[4] is not None:
        leaves.append((code, digits, d, r[4], (r[3] or "").strip()))
    else:
        desc[digits] = d
rows, heads = [], {}
for code, digits, d, ez, cl in leaves:
    path = []
    for n in (4, 5, 6, 7, 8):
        p = desc.get(digits[:n])
        if p and (not path or path[-1] != p):
            path.append(p)
    head = desc.get(digits[:4], "")
    heads[digits[:4]] = head
    rest = [p for p in path if p != head] + [d]
    rows.append([code, " › ".join(rest), float(str(ez).replace(",", ".")), cl])
json.dump({"fuente": "MEF, Arancel Nacional (febrero 2025)", "partidas": heads, "filas": rows}, open(f"{OUT}/ncm.json", "w"), ensure_ascii=False, separators=(",", ":"))
print("arancel:", len(rows), "posiciones")

# ---------- 2) Oportunidades: ítems que el Estado compra seguido, con precio unitario adjudicado ----------
REC = "https://www.comprasestatales.gub.uy/ocds/record/"
EXCL = re.compile(r"\b(SERVICIO|MANTENIMIENTO|REPARACION|ARRENDAMIENTO|ALQUILER|OBRA|CONSULTORIA|HONORARIO|SEGURO|TRASLADO|TRANSPORTE|"
                  r"PASAJE|CATERING|LIMPIEZA DE|VIGILANCIA|CAPACITACION|PUBLICIDAD|ANALISIS|ESTUDIO|CARNE|POLLO|LECHE|PAN|FRUTA|VERDURA|"
                  r"MEDICAMENTO|COMPRIMIDO|INYECTABLE|AMPOLLA|JARABE|SOLUCION|VACUNA|REACTIVO|COMBUSTIBLE|GASOIL|NAFTA|ENERGIA|CONTRATACION|"
                  r"ACONDICIONAMIENTO|REFORMA|DIETA|RACION|COMIDA|SOFTWARE|ADMINISTRACION|TRATAMIENTO|DESARROLLO|ASESORAMIENTO|ASISTENCIA|"
                  r"CONSTRUCCION|INSTALACION|PINTURA DE|SUMINISTRO DE|EMULSION|HORMIGON|ASFALT|BITUMIN|DETERMINACION|ANALISIS|LICENCIA|SUSCRIPCION|"
                  r"UREA|FERTILIZANTE|SEMILLA|GANADO|AGUA|GAS|LIMPIEZA|ENTREGA|RECOLECCION|FLETE|EJECUCION|IMPERMEABILIZACION|TICKET|"
                  r"DIGITALIZACION|CANASTA|USO HUMANO|QUESO|HUEVO|HARINA|ACEITE COMESTIBLE|ARROZ|AZUCAR|YERBA|CAFE|FIDEO|PASTA SECA|GALLETITA|"
                  r"DULCE|YOGUR|MANTECA|POLLO|CERDO|PESCADO|HELADO|BEBIDA|REFRESCO|JUGO|VINO|LIBRO|IMPRESION|CEMENTO|ARENA|PEDREGULLO|BALASTO|"
                  r"HORMIGON|LADRILLO|BLOQUE|PORTLAND|STENT|PROTESIS|IMPLANTE|CATETER|SUTURA|MARCAPASO|VALVULA CARDIACA|CLORURO DE POTASIO)")
BIENES = {"UNIDAD", "KG", "L", "M", "M2", "ROLLO", "KIT", "PAR", "PLACA", "CAJA", "CARTUCHO", "PAQUETE", "LATA", "JUEGO", "DOCENA",
          "BOLSA", "BOBINA", "G", "RESMA", "BIDON", "TONELADA", "METRO", "LITRO", "KILOGRAMO", "BALDE", "TAMBOR", "BLOCK", "SET"}
by = collections.defaultdict(list)
for f in sorted(glob.glob(f"{SRC}/a-*.json")):
    for rel in json.load(open(f))["releases"]:
        buyer = (rel.get("buyer") or {}).get("name", "").strip()
        for a in rel.get("awards", []):
            sup = ((a.get("suppliers") or [{}])[0].get("name") or "").strip()
            for i in a.get("items", []):
                c = i.get("classification") or {}
                v = (i.get("unit") or {}).get("value") or {}
                q, p = i.get("quantity") or 0, v.get("amount")
                if v.get("currency") != "UYU" or not p or not q or q * p > 3e8:
                    continue
                d = (c.get("description") or "").strip()
                un = ((i.get("unit") or {}).get("name") or "").upper()
                if not d or EXCL.search(d.upper()) or un not in BIENES:
                    continue
                by[(c.get("id"), d)].append({"q": q, "p": p, "b": buyer, "s": sup, "o": rel["ocid"], "u": (i.get("unit") or {}).get("name", "")})
ops = []
for (cid, d), xs in by.items():
    compradores = {x["b"] for x in xs}
    if len(xs) < 8 or len(compradores) < 3:
        continue
    ps = sorted(x["p"] for x in xs)
    q = sum(x["q"] for x in xs)
    tot = sum(x["q"] * x["p"] for x in xs)
    if tot < 300000:
        continue
    provs = collections.Counter(x["s"] for x in xs)
    ops.append({"item": d, "unidad": collections.Counter(x["u"] for x in xs).most_common(1)[0][0], "adjudicaciones": len(xs),
                "compradores": len(compradores), "cantidad": round(q), "monto": round(tot),
                "p25": round(ps[len(ps) // 4], 2), "mediana": round(st.median(ps), 2), "p75": round(ps[3 * len(ps) // 4], 2),
                "proveedores": len(provs), "top_proveedor": provs.most_common(1)[0][0],
                "top_share": round(provs.most_common(1)[0][1] / len(xs), 2), "ejemplo": REC + xs[0]["o"].split("-")[-1]})
ops.sort(key=lambda o: -o["monto"])
json.dump({"fuente": "ARCE, adjudicaciones (datos abiertos OCDS)", "items": ops[:1500]}, open(f"{OUT}/oportunidades.json", "w"),
          ensure_ascii=False, separators=(",", ":"))
print("oportunidades:", len(ops), "ítems")

if sys.argv[1:2] == ["--auto"]:
    import shutil
    shutil.rmtree("impo/tmp", ignore_errors=True)
