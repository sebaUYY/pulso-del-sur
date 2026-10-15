"""Remates UY — remates judiciales vigentes publicados en el Diario Oficial (IMPO), con buscador, filtros, calendario y RSS.
Fuente: https://www.impo.com.uy/remates (lista oficial; respeta robots.txt: una sola página por corrida).
Guarda un histórico en remates/historico.json para mostrar estadísticas y no perder remates ya pasados."""
import re, html, json, os, subprocess, datetime as dt, unicodedata
from zoneinfo import ZoneInfo

URL = "https://www.impo.com.uy/remates"
CA = "/root/.ccr/ca-bundle.crt"
NOW = dt.datetime.now(ZoneInfo("America/Montevideo"))
HOY = NOW.date()
OUT, HIST = "site/remates", "remates/historico.json"
os.makedirs(OUT, exist_ok=True)
os.makedirs("remates", exist_ok=True)

cmd = ["curl", "-sS", "-L", "--retry", "3", "--max-time", "60", "-A", "PulsoDelSur/1.0 (+https://sebauyy.github.io/pulso-del-sur/)"]
raw = subprocess.run(cmd + (["--cacert", CA] if os.path.exists(CA) else []) + [URL], capture_output=True, check=True).stdout
try:
    page = raw.decode("utf-8")
except UnicodeDecodeError:
    page = raw.decode("latin-1")


def txt(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


TIPOS = [("Campo", r"\b(CAMPO|HECTAREA|HAS\.|RURAL|CHACRA)"),
         ("Casa o apartamento", r"\b(CASA|APARTAMENTO|VIVIENDA|UNIDAD DE PROPIEDAD HORIZONTAL|PROPIEDAD HORIZONTAL|FINCA)"),
         ("Terreno", r"\b(TERRENO|SOLAR|BALDIO|FRACCION)"),
         ("Local o inmueble", r"\b(INMUEBLE|LOCAL|PADRON|PADRÓN|EDIFICIO|GALPON|NAVE)"),
         ("Vehículo", r"\b(VEHICULO|AUTOMOVIL|AUTOMOTOR|CAMION|CAMIONETA|MOTO|OMNIBUS|TRACTOR|MATRICULA|AUTO )"),
         ("Maquinaria", r"\b(MAQUINA|MAQUINARIA|FERTILIZADORA|COSECHADORA|EXCAVADORA|EQUIPO)"),
         ("Bienes muebles", r"\b(MUEBLE|MERCADERIA|ENSERES|OBJETOS|LOTE)")]

items = []
for block in re.split(r'<a name="', page)[1:]:
    depto = txt(block.split('"', 1)[0])
    for m in re.finditer(r'class="col-md-12 rfecha".*?(?=class="col-md-12 rfecha"|<a name=|$)', block, re.S):
        b = m.group(0)
        f = re.search(r"Fecha:\s*<strong>([^<]+)</strong>.*?Hora:\s*<strong>([^<]*)</strong>.*?Lugar:\s*<strong>(.*?)</strong>", b, re.S)
        if not f:
            continue
        campos = {txt(k).rstrip(" -").lower(): txt(v) for k, v in re.findall(r"<strong>([^<]+?) - </strong>(.*?)</div>", b, re.S)}
        av = re.search(r'href="([^"]*avisos-remate/(\d+)-(\d+))"', b)
        pub = re.search(r"Diario Oficial el d[íi]a\s*([\d/]+)", txt(b))
        d, mth, y = (f.group(1).strip().split("/") + ["", "", ""])[:3]
        try:
            fecha = dt.date(int(y), int(mth), int(d)).isoformat()
        except ValueError:
            continue
        bien = campos.get("bien a rematar", "")
        cond = campos.get("condiciones", "")
        nb = norm(bien)
        tipo = next((t for t, rx in TIPOS if re.search(rx, nb)), "Otros")
        base = None
        mb = re.search(r"BASE\s*(?:DE\s*)?(U\$S|US\$|USD|U\.S\.\$|DOLARES|\$|UI)\s*([\d\.\,]+)", norm(cond))
        if mb:
            try:
                base = {"moneda": "UI" if mb.group(1) == "UI" else ("$" if mb.group(1) == "$" else "USD"),
                        "monto": float(mb.group(2).replace(".", "").replace(",", "."))}
            except ValueError:
                base = None
        padrones = sorted(set(re.findall(r"PADR[OÓ]N(?:ES)?\s*(?:N[º°O\.]*\s*)?([\d\.]{2,9})", norm(bien))))
        items.append({"id": f"{av.group(2)}-{av.group(3)}" if av else f"{fecha}-{depto}-{len(items)}",
                      "depto": depto.title().replace(" Y ", " y "), "fecha": fecha, "hora": f.group(2).strip(), "lugar": txt(f.group(3)),
                      "bien": bien, "tipo": tipo, "condiciones": cond, "sin_base": "SIN BASE" in norm(cond), "base": base,
                      "padrones": [p.replace(".", "") for p in padrones], "rematador": campos.get("rematador", ""),
                      "publicado": pub.group(1) if pub else "", "aviso": av.group(1).replace("http://", "https://") if av else URL})
if not items:
    raise SystemExit("remates: no se pudo leer la lista de IMPO (cambió el formato)")

hist = json.load(open(HIST)) if os.path.exists(HIST) else {}
import time
pedidos = 0
for it in items:
    nc = norm(it["condiciones"])
    it["moneda"] = "USD" if "DOLAR" in nc else ("$" if "PESO" in nc or "MONEDA NACIONAL" in nc else "")
    it["sucesion"] = bool(re.search(r"SUCESI|YACENTE", norm(it["bien"]) + " " + nc))
    prev = hist.get(it["id"])
    if prev and "detalle" in prev and (prev.get("det_v") == 2 or pedidos >= 12):
        it.update({k: prev[k] for k in ("detalle", "juzgado", "superficie", "det_v") if k in prev})
        it["sucesion"] = it["sucesion"] or prev.get("sucesion", False)
        it["padrones"] = prev.get("padrones") or it["padrones"]
    elif it["aviso"] != URL and pedidos < 12:
        # aviso completo: padrones, superficie y juzgado (robots.txt de IMPO pide 10 s entre pedidos)
        time.sleep(10)
        pedidos += 1
        try:
            r = subprocess.run(cmd + (["--cacert", CA] if os.path.exists(CA) else []) + [it["aviso"]], capture_output=True, check=True).stdout
            try:
                a = txt(r.decode("utf-8"))
            except UnicodeDecodeError:
                a = txt(r.decode("latin-1"))
            na = norm(a)
            pads = []
            for mm in re.finditer(r"PADRON(?:ES)?\s*(?:N[O\.]*\s*)?(?:\(?[A-Z ]+\)?\s*)?\(?(?:PADRON\s*N[O\.]*\s*)?([\d\.]{2,9})", na):
                antes = na[max(0, mm.start() - 40):mm.start()]
                if re.search(r"LIND|CON PARTE|CON LOS|CON EL|MAYOR AREA|ANTES", antes):
                    continue
                pv = mm.group(1).replace(".", "")
                if pv and pv not in pads:
                    pads.append(pv)
            it["padrones"] = it["padrones"] or pads[:4]
            sup = re.search(r"\(([\d\.,]+\s*(?:MTS2|M2|MTS\.?\s*2|METROS CUADRADOS|HAS?\.?|HECTAREAS)[^)]{0,30})\)", na)
            it["superficie"] = sup.group(1).lower() if sup else ""
            jz = re.search(r"(JUZGADO LETRADO[^.]{0,90}?TURNO|JUZGADO DE PAZ[^.]{0,60}|JUZGADO LETRADO DE PRIMERA INSTANCIA[^.]{0,60}|BANCO HIPOTECARIO DEL URUGUAY|AGENCIA NACIONAL DE VIVIENDA)", na)
            it["juzgado"] = jz.group(1).split(" EDICTO")[0].title() if jz else ""
            it["detalle"], it["det_v"] = True, 2
            it["sucesion"] = it["sucesion"] or bool(re.search(r"SUCESI|YACENTE", na))
        except Exception as ex:
            print("aviso: falla", it["aviso"], ex)
    hist[it["id"]] = it
json.dump(hist, open(HIST, "w"), ensure_ascii=False, separators=(",", ":"))
vig = sorted((x for x in hist.values() if x["fecha"] >= HOY.isoformat()), key=lambda x: (x["fecha"], x["hora"]))
nuevos = [x for x in vig if x["id"] in {i["id"] for i in items} and x["publicado"] and
          dt.datetime.strptime(x["publicado"], "%d/%m/%Y").date() >= HOY - dt.timedelta(days=7)]

# calendario y RSS
def ics_dt(x):
    h = re.match(r"(\d{1,2})[:\.](\d{2})", x["hora"] or "")
    return x["fecha"].replace("-", "") + (f"T{int(h.group(1)):02d}{h.group(2)}00" if h else "")


ev = "".join(f"BEGIN:VEVENT\r\nUID:{x['id']}@remates-pulsodelsur\r\nDTSTAMP:{NOW.astimezone(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\n"
             f"DTSTART;TZID=America/Montevideo:{ics_dt(x)}\r\nSUMMARY:Remate {x['tipo'].lower()} · {x['depto']}\r\nLOCATION:{x['lugar'][:150].replace(',', ' ')}\r\n"
             f"DESCRIPTION:{x['bien'][:300].replace(',', ' ')} — {x['aviso']}\r\nEND:VEVENT\r\n" for x in vig if ics_dt(x))
open(f"{OUT}/remates.ics", "w", encoding="utf-8").write(
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Pulso del Sur//Remates UY//ES\r\nX-WR-CALNAME:Remates judiciales UY\r\n" + ev + "END:VCALENDAR\r\n")
e = html.escape
rss = "".join(f"<item><title>{e(x['tipo'])} en {e(x['depto'])} · {x['fecha'][8:]}/{x['fecha'][5:7]}</title><link>{e(x['aviso'])}</link><guid>{e(x['id'])}</guid>"
              f"<description>{e(x['bien'][:400])} {e(x['condiciones'])}</description></item>" for x in sorted(vig, key=lambda x: x["publicado"][::-1], reverse=True)[:80])
open(f"{OUT}/feed.xml", "w", encoding="utf-8").write(f'<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>Remates judiciales UY · Pulso del Sur</title>'
                                                      f'<link>{URL}</link><description>Remates judiciales vigentes publicados en el Diario Oficial</description>{rss}</channel></rss>')
json.dump({"generado": NOW.isoformat(timespec="minutes"), "remates": vig}, open(f"{OUT}/remates.json", "w"), ensure_ascii=False)

tpl = open("remates_template.html", encoding="utf-8").read()
por_tipo = {}
for x in vig:
    por_tipo[x["tipo"]] = por_tipo.get(x["tipo"], 0) + 1
out = (tpl.replace("{{DATA}}", json.dumps(vig, ensure_ascii=False).replace("</", "<\\/"))
       .replace("{{N}}", str(len(vig))).replace("{{NUEVOS}}", str(len(nuevos)))
       .replace("{{SEMANA}}", str(sum(1 for x in vig if x["fecha"] <= (HOY + dt.timedelta(days=7)).isoformat())))
       .replace("{{INMUEBLES}}", str(sum(v for k, v in por_tipo.items() if k in ("Campo", "Casa o apartamento", "Terreno", "Local o inmueble"))))
       .replace("{{HIST}}", str(len(hist))).replace("{{FECHA}}", NOW.strftime("%d/%m/%Y %H:%M")))
open(f"{OUT}/index.html", "w", encoding="utf-8").write(out)
print("remates:", len(items), "leídos ·", len(vig), "vigentes ·", len(nuevos), "nuevos en 7 días ·", len(hist), "en histórico ·", por_tipo)
