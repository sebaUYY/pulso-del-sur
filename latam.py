"""Tres sitios para cualquier persona de Latinoamérica, 100% automáticos:
  site/feriados/  feriados 2026-2027 por país, fines de semana largos, calculadora de días hábiles y calendarios .ics
  site/sismos/    sismos de Latinoamérica en vivo (USGS, se actualiza en el navegador) + resumen de 30 días
  site/visas/     ¿necesito visa? para los pasaportes latinoamericanos (Passport Index Data)"""
import json, os, subprocess, datetime as dt, csv, io, html
from zoneinfo import ZoneInfo

CA = "/root/.ccr/ca-bundle.crt"
NOW = dt.datetime.now(ZoneInfo("America/Montevideo"))
HOY = NOW.date()


def get(url):
    cmd = ["curl", "-sS", "-L", "--retry", "4", "--max-time", "90"] + (["--cacert", CA] if os.path.exists(CA) else []) + [url]
    r = subprocess.run(cmd, capture_output=True, check=True)
    return r.stdout


PAISES = {"AR": "Argentina", "BO": "Bolivia", "BR": "Brasil", "CL": "Chile", "CO": "Colombia", "CR": "Costa Rica",
          "DO": "República Dominicana", "EC": "Ecuador", "MX": "México", "PA": "Panamá", "PY": "Paraguay", "PE": "Perú", "UY": "Uruguay"}
UY_NO_LABORABLES = {"01-01", "05-01", "07-18", "08-25", "12-25"}   # Ley 12.590 y modificativas: feriados pagos en Uruguay
CSS = """:root{--bg:#f6f5f1;--surface:#fff;--fg:#17202a;--muted:#5f6b76;--rule:#dfe3e6;--accent:#1d5fa8;--hot:#c2410c;--ok:#1f7a4a;
--display:"Archivo","Arial Narrow",system-ui,sans-serif;--body:"Public Sans",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#10151b;--surface:#18202a;--fg:#e6ebf0;--muted:#97a4b0;--rule:#2b3642;--accent:#6aa8ec;--hot:#fb923c;--ok:#6fcf97;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 var(--body);padding:28px max(16px,env(safe-area-inset-left,0px)) 56px max(16px,env(safe-area-inset-right,0px))}
.wrap{max-width:1040px;margin:0 auto;display:grid;grid-template-columns:minmax(0,1fr);gap:26px}.wrap>*{min-width:0}
.eyebrow{font:500 12px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
h1{font:800 clamp(34px,6vw,56px)/.95 var(--display);font-stretch:78%;margin:8px 0}h2{font:700 22px/1.15 var(--display);font-stretch:85%;margin:0 0 10px}
.lede{color:var(--muted);max-width:68ch;margin:0}.muted{color:var(--muted);font-size:14px}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
select,input{font:inherit;padding:10px;border:1px solid var(--rule);border-radius:6px;background:var(--surface);color:var(--fg)}
.panel{background:var(--surface);border:1px solid var(--rule);border-radius:8px;padding:16px;overflow-x:auto}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,160px),1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--rule);border-radius:8px;padding:14px}.kpi b{display:block;font:700 26px/1.1 var(--display)}.kpi span{font-size:13px;color:var(--muted)}
table{border-collapse:collapse;width:100%;font-size:14.5px}th,td{padding:8px;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top}
th{font:500 12px var(--mono);color:var(--muted);text-transform:uppercase}.num{text-align:right;font-family:var(--mono)}
.tag{font:500 12px var(--mono);padding:2px 7px;border-radius:4px;border:1px solid var(--rule);white-space:nowrap}
.tag.ok{color:var(--ok);border-color:var(--ok)}.tag.hot{color:var(--hot);border-color:var(--hot)}
.cta{background:var(--surface);border:1px solid var(--rule);border-radius:8px;padding:16px;display:grid;gap:8px}
.btn{justify-self:start;background:var(--accent);color:var(--surface);padding:10px 16px;border-radius:6px;font-weight:600;text-decoration:none;border:0;cursor:pointer;font:inherit}
@media (max-width:560px){.hm{display:none}}
a{color:var(--accent)}footer{font-size:13px;color:var(--muted)}"""
HEAD = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{t}</title><meta name="description" content="{d}">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,500..800&family=Public+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{css}</style></head><body><div class="wrap">"""
CTA = """<section class="cta"><strong>{t}</strong><span class="muted">{d}</span><a class="btn" href="https://pulsodelsur.beehiiv.com/subscribe">Suscribirme gratis</a></section>"""


def page(path, title, desc, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(HEAD.format(t=html.escape(title), d=html.escape(desc), css=CSS) + body + "</div></body></html>")


# ======================= 1) FERIADOS =======================
fer = {}
for c in PAISES:
    fer[c] = []
    for y in (HOY.year, HOY.year + 1):
        try:
            data = json.loads(get(f"https://date.nager.at/api/v3/PublicHolidays/{y}/{c}"))
        except Exception as e:
            print("feriados: falla", c, y, e)
            continue
        for x in data:
            if not x.get("global") or "Public" not in (x.get("types") or []):
                continue
            nota = ""
            if c == "UY":
                nota = "No laborable, pago" if x["date"][5:] in UY_NO_LABORABLES else "Laborable"
            f = x["date"]
            if c == "UY" and f[5:] in ("04-19", "05-18", "10-12"):
                d = dt.date.fromisoformat(f)
                if d.weekday() in (1, 2):
                    f = (d - dt.timedelta(days=d.weekday())).isoformat()
                elif d.weekday() in (3, 4):
                    f = (d + dt.timedelta(days=7 - d.weekday())).isoformat()
            fer[c].append({"f": f, "n": x["localName"], "nota": nota})
    # sin duplicados (mismo día)
    seen, out = set(), []
    for x in sorted(fer[c], key=lambda x: x["f"]):
        if x["f"] not in seen:
            seen.add(x["f"])
            out.append(x)
    fer[c] = out
    # calendario .ics
    os.makedirs("site/feriados/ics", exist_ok=True)
    ev = "".join(f"BEGIN:VEVENT\r\nUID:{x['f']}-{c}@pulsodelsur\r\nDTSTAMP:{NOW.astimezone(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\nDTSTART;VALUE=DATE:{x['f'].replace('-', '')}\r\n"
                 f"SUMMARY:{x['n']}{' · ' + x['nota'] if x['nota'] else ''}\r\nTRANSP:TRANSPARENT\r\nEND:VEVENT\r\n" for x in fer[c])
    open(f"site/feriados/ics/{c}.ics", "w", encoding="utf-8").write(
        f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Pulso del Sur//Feriados {PAISES[c]}//ES\r\nX-WR-CALNAME:Feriados {PAISES[c]}\r\n{ev}END:VCALENDAR\r\n")
json.dump(fer, open("site/feriados/feriados.json", "w"), ensure_ascii=False)
opts = "".join(f'<option value="{c}"{" selected" if c == "UY" else ""}>{n}</option>' for c, n in sorted(PAISES.items(), key=lambda kv: kv[1]))
page("site/feriados/index.html", "Feriados y fines de semana largos en Latinoamérica · 2026 y 2027",
     "Feriados nacionales de 13 países de Latinoamérica, los próximos fines de semana largos, calculadora de días hábiles y calendario para tu celular.",
     f"""<header><div class="eyebrow">Actualizado {NOW.strftime('%d/%m/%Y')}</div><h1>Feriados LatAm</h1>
<p class="lede">Feriados nacionales de {HOY.year} y {HOY.year + 1}, cuál es el próximo fin de semana largo y cuántos días hábiles hay entre dos fechas. Elegí tu país.</p></header>
<div class="row"><select id="pais" aria-label="País">{opts}</select><a id="ics" class="btn" href="ics/UY.ics">Agregar a mi calendario</a></div>
<section class="kpis" id="kp"></section>
<section class="panel"><h2>Fines de semana largos</h2><div id="largos"></div></section>
<section class="panel"><h2>Calculadora de días hábiles</h2>
<div class="row"><label>Desde <input type="date" id="d1"></label><label>Hasta <input type="date" id="d2"></label></div>
<p id="hab" style="font-size:18px;margin:10px 0 0"></p><p class="muted" style="margin:4px 0 0">Cuenta de lunes a viernes, sin feriados nacionales del país elegido. Incluye las dos fechas.</p></section>
<section class="panel"><h2>Todos los feriados</h2><table><thead><tr><th>Fecha</th><th>Día</th><th>Feriado</th><th></th></tr></thead><tbody id="tb"></tbody></table></section>
{CTA.format(t="Recibí los feriados y fines largos del mes", d="Un correo corto el primer lunes de cada mes. Gratis.")}
<footer>Fuente: Nager.Date (base pública de feriados, mantenida por su comunidad). Los gobiernos pueden agregar o mover feriados por decreto (por ejemplo, los días puente de Argentina): confirmá en el sitio oficial de tu país. En Uruguay se indica si el feriado es pago (no laborable) o laborable, y se aplican los traslados a lunes de la Ley 16.805. <a href="../">Pulso del Sur</a></footer>
<script>
const F={json.dumps(fer, ensure_ascii=False)};
const DIAS=["domingo","lunes","martes","miércoles","jueves","viernes","sábado"],$=id=>document.getElementById(id);
const d0=new Date();d0.setHours(0,0,0,0);const iso=d=>d.toISOString().slice(0,10);
const dt=s=>new Date(s+"T12:00:00");const fmt=s=>{{const d=dt(s);return d.toLocaleDateString("es",{{day:"numeric",month:"long"}})}};
function largos(c){{const H={{}};F[c].forEach(x=>H[x.f]=x);const out=[];const end=new Date(d0.getFullYear()+2,0,1);
 let d=new Date(d0),blk=[];const off=d=>[0,6].includes(d.getDay())||H[iso(d)];
 for(;d<end;d=new Date(d.getTime()+864e5)){{if(off(d)){{blk.push(new Date(d))}}else{{
   if(blk.length>=3&&blk.some(b=>H[iso(b)])){{const h=blk.map(b=>H[iso(b)]).filter(Boolean)[0];out.push({{s:blk[0],e:blk[blk.length-1],n:h.n+(h.nota==="Laborable"?" (feriado laborable)":""),tipo:"largo"}})}}
   blk=[]}}}}
 F[c].forEach(x=>{{const t=dt(x.f),w=t.getDay();if(t<d0||!(w===2||w===4))return;const nb=new Date(t.getTime()+(w===2?-1:1)*864e5);
  if(!H[iso(nb)])out.push({{s:t,e:t,n:x.n+(x.nota==="Laborable"?" (feriado laborable)":""),tipo:"puente"}})}});
 return out.sort((a,b)=>a.s-b.s)}}
function draw(){{const c=$("pais").value;$("ics").href="ics/"+c+".ics";
 const fut=F[c].filter(x=>dt(x.f)>=d0),prox=fut[0];const L=largos(c);const lg=d=>d.toLocaleDateString("es",{{weekday:"long",day:"numeric",month:"long"}})+(d.getFullYear()!==d0.getFullYear()?" de "+d.getFullYear():"");
 $("kp").innerHTML=`<div class="kpi"><b>${{prox?fmt(prox.f):"—"}}</b><span>próximo feriado${{prox?": "+prox.n:""}}</span></div><div class="kpi"><b>${{prox?Math.round((dt(prox.f)-d0)/864e5):"—"}}</b><span>días que faltan</span></div><div class="kpi"><b>${{L.filter(l=>l.tipo==="largo"&&l.s.getFullYear()===d0.getFullYear()).length}}</b><span>fines de semana largos que quedan este año</span></div>`;
 $("largos").innerHTML=L.slice(0,8).map(l=>{{const n=Math.round((l.e-l.s)/864e5)+1;return l.tipo==="largo"?`<p style="margin:6px 0"><span class="tag ok">${{n}} días</span> del ${{lg(l.s)}} al ${{lg(l.e)}} · ${{l.n}}</p>`:`<p style="margin:6px 0"><span class="tag hot">puente</span> ${{lg(l.s)}} · ${{l.n}}: tomando un día libre se arman 4 días</p>`}}).join("")||'<p class="muted">No quedan fines de semana largos en el período.</p>';
 $("tb").innerHTML=F[c].map(x=>`<tr style="${{dt(x.f)<d0?"opacity:.5":""}}"><td>${{fmt(x.f)}} ${{x.f.slice(0,4)}}</td><td>${{DIAS[dt(x.f).getDay()]}}</td><td>${{x.n}}</td><td>${{x.nota?`<span class="tag ${{x.nota.startsWith("No")?"ok":""}}">${{x.nota}}</span>`:""}}</td></tr>`).join("");hab()}}
function hab(){{const c=$("pais").value,a=$("d1").value,b=$("d2").value;if(!a||!b){{$("hab").textContent="";return}}
 const set=new Set(F[c].map(x=>x.f));let n=0,d=dt(a),e=dt(b);if(d>e)[d,e]=[e,d];for(;d<=e;d=new Date(d.getTime()+864e5)){{const w=d.getDay();if(w&&w<6&&!set.has(iso(d)))n++}}
 $("hab").innerHTML=`<b>${{n}}</b> días hábiles`}}
$("d1").value=iso(d0);const t=new Date(d0);t.setDate(t.getDate()+30);$("d2").value=iso(t);
["pais","d1","d2"].forEach(i=>$(i).addEventListener("input",draw));draw();
</script>""")

# ======================= 2) SISMOS =======================
EN = {"Argentina": "Argentina", "Bolivia": "Bolivia", "Brazil": "Brasil", "Chile": "Chile", "Colombia": "Colombia", "Costa Rica": "Costa Rica",
      "Cuba": "Cuba", "Dominican Republic": "República Dominicana", "Ecuador": "Ecuador", "El Salvador": "El Salvador", "Guatemala": "Guatemala",
      "Honduras": "Honduras", "Mexico": "México", "Nicaragua": "Nicaragua", "Panama": "Panamá", "Paraguay": "Paraguay", "Peru": "Perú",
      "Puerto Rico": "Puerto Rico", "Uruguay": "Uruguay", "Venezuela": "Venezuela"}
Q = "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minlatitude=-60&maxlatitude=33&minlongitude=-120&maxlongitude=-25"
desde = (HOY - dt.timedelta(days=30)).isoformat()
try:
    snap = json.loads(get(f"{Q}&starttime={desde}&minmagnitude=2.5&orderby=time"))["features"]
except Exception as e:
    print("sismos: falla", e)
    snap = []


def pais_de(place):
    for en, es in EN.items():
        if (place or "").endswith(en) or f"{en} region" in (place or "") or f", {en}" in (place or ""):
            return es
    return None


rs = [{"t": f["properties"]["time"], "m": f["properties"]["mag"], "p": f["properties"]["place"], "u": f["properties"]["url"],
       "z": round(f["geometry"]["coordinates"][2]), "c": pais_de(f["properties"]["place"])} for f in snap]
rs = [r for r in rs if r["c"]]
cnt = {}
for r in rs:
    cnt.setdefault(r["c"], [0, 0.0])
    cnt[r["c"]][0] += 1
    cnt[r["c"]][1] = max(cnt[r["c"]][1], r["m"] or 0)
page("site/sismos/index.html", "Sismos en Latinoamérica hoy · en vivo",
     "Últimos sismos en Chile, Perú, México, Ecuador, Colombia, Centroamérica y el resto de Latinoamérica, actualizados en vivo con datos del USGS.",
     f"""<header><div class="eyebrow">En vivo · datos del USGS</div><h1>Sismos LatAm</h1>
<p class="lede">Los últimos temblores de Latinoamérica, con magnitud, profundidad y hora local. La lista se actualiza sola cada minuto mientras tengas la página abierta.</p></header>
<div class="row"><select id="pais" aria-label="País"><option value="">Todos los países</option>{"".join(f'<option>{v}</option>' for v in sorted(EN.values()))}</select>
<select id="mag" aria-label="Magnitud mínima"><option value="2.5">Magnitud 2,5 o más</option><option value="4" selected>4 o más</option><option value="5">5 o más</option><option value="6">6 o más</option></select>
<span class="muted" id="st"></span></div>
<section class="kpis" id="kp"></section>
<section class="panel"><table><thead><tr><th>Hora</th><th class="num">Magnitud</th><th>Lugar</th><th class="num hm">Profundidad</th></tr></thead><tbody id="tb"></tbody></table></section>
<section class="panel"><h2>Últimos 30 días por país (magnitud 2,5 o más)</h2><table><thead><tr><th>País</th><th class="num">Sismos</th><th class="num">Mayor magnitud</th></tr></thead><tbody>{"".join(f'<tr><td>{k}</td><td class="num">{v[0]}</td><td class="num">{v[1]:.1f}</td></tr>' for k, v in sorted(cnt.items(), key=lambda kv: -kv[1][0]))}</tbody></table>
<p class="muted">Resumen generado el {NOW.strftime('%d/%m/%Y %H:%M')} (hora de Uruguay).</p></section>
{CTA.format(t="Alerta semanal de sismos de tu país", d="Un resumen cada lunes con los sismos más fuertes de la semana. Gratis.")}
<footer>Fuente: Servicio Geológico de Estados Unidos (USGS), catálogo ComCat. Las magnitudes preliminares pueden corregirse. Para emergencias seguí siempre a los organismos oficiales de tu país (por ejemplo, CSN en Chile, IGP en Perú, SSN en México). <a href="../">Pulso del Sur</a></footer>
<script>
const SNAP={json.dumps(rs[:400], ensure_ascii=False)};const EN={json.dumps(EN, ensure_ascii=False)};
const Q="{Q}",$=id=>document.getElementById(id);let DATA=SNAP;
const DIR={{N:"N",S:"S",E:"E",W:"O"}};const lugar=p=>{{let t=p||"";for(const [en,es] of Object.entries(EN))t=t.replace(new RegExp(en+"$"),es);t=t.replace(/^off the coast of /,"frente a la costa de ").replace(/ region$/," (región)");const m=t.match(/^(\\d+) km ([NSEW]+) of (.+)$/);return m?`a ${{m[1]}} km al ${{m[2].split("").map(c=>DIR[c]).join("")}} de ${{m[3]}}`:t}};const pais=p=>{{for(const [en,es] of Object.entries(EN)){{if((p||"").endsWith(en)||(p||"").includes(en+" region")||(p||"").includes(", "+en))return es}}return null}};
async function load(){{try{{const s=new Date(Date.now()-7*864e5).toISOString().slice(0,10);
 const r=await fetch(Q+"&starttime="+s+"&minmagnitude=2.5&orderby=time");const j=await r.json();
 DATA=j.features.map(f=>({{t:f.properties.time,m:f.properties.mag,p:f.properties.place,u:f.properties.url,z:Math.round(f.geometry.coordinates[2]),c:pais(f.properties.place)}})).filter(x=>x.c);
 $("st").textContent="Actualizado "+new Date().toLocaleTimeString("es",{{hour:"2-digit",minute:"2-digit"}});}}catch(e){{$("st").textContent="Sin conexión al USGS: se muestran los datos guardados."}}draw()}}
function draw(){{const c=$("pais").value,m=+$("mag").value;const r=DATA.filter(x=>(!c||x.c===c)&&(x.m||0)>=m);
 const d1=r.filter(x=>Date.now()-x.t<864e5);const mx=r.reduce((a,x)=>x.m>(a?a.m:-1)?x:a,null);
 $("kp").innerHTML=`<div class="kpi"><b>${{d1.length}}</b><span>sismos en las últimas 24 h</span></div><div class="kpi"><b>${{r.length}}</b><span>en los últimos 7 días</span></div><div class="kpi"><b>${{mx?mx.m.toFixed(1).replace(".",","):"—"}}</b><span>mayor magnitud${{mx?": "+lugar(mx.p):""}}</span></div>`;
 $("tb").innerHTML=r.slice(0,150).map(x=>`<tr><td>${{new Date(x.t).toLocaleString("es",{{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}})}}</td><td class="num"><span class="tag ${{x.m>=6?"hot":""}}">${{x.m.toFixed(1).replace(".",",")}}</span></td><td><a href="${{x.u}}" target="_blank" rel="noopener">${{lugar(x.p)}}</a></td><td class="num hm">${{x.z}} km</td></tr>`).join("")||'<tr><td colspan="4" class="muted">Sin sismos con ese filtro.</td></tr>'}}
["pais","mag"].forEach(i=>$(i).addEventListener("input",draw));draw();load();setInterval(load,60000);
</script>""")

# ======================= 3) VISAS =======================
LAT = {"AR": "Argentina", "BO": "Bolivia", "BR": "Brasil", "CL": "Chile", "CO": "Colombia", "CR": "Costa Rica", "CU": "Cuba", "DO": "República Dominicana",
       "EC": "Ecuador", "SV": "El Salvador", "GT": "Guatemala", "HN": "Honduras", "MX": "México", "NI": "Nicaragua", "PA": "Panamá", "PY": "Paraguay",
       "PE": "Perú", "UY": "Uruguay", "VE": "Venezuela"}
raw = get("https://raw.githubusercontent.com/imorte/passport-index-data/main/passport-index-tidy-iso2.csv").decode("utf-8")
readme = get("https://raw.githubusercontent.com/imorte/passport-index-data/main/README.md").decode("utf-8")
import re
m = re.search(r"Last updated:\s*\*\*(.+?)\*\*", readme)
fecha_v = m.group(1) if m else "sin fecha"
for en, es in zip("January February March April May June July August September October November December".split(),
                  "enero febrero marzo abril mayo junio julio agosto setiembre octubre noviembre diciembre".split()):
    fecha_v = fecha_v.replace(" " + en + " ", f" de {es} de ")
try:
    nombres = {r["alpha-2"]: r["name"] for r in csv.DictReader(io.StringIO(get(
        "https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/master/all/all.csv").decode("utf-8")))}
except Exception:
    nombres = {}
vis = {c: {} for c in LAT}
for r in csv.DictReader(io.StringIO(raw)):
    if r["Passport"] in vis:
        vis[r["Passport"]][r["Destination"]] = r["Requirement"]


def cat(v):
    if v.isdigit() or v in ("visa free", "visa on arrival", "-1"):
        return "libre"
    if v in ("eta", "e-visa"):
        return "online"
    if v == "no admission":
        return "no"
    return "visa"


res = {c: {"libre": sum(1 for v in d.values() if cat(v) == "libre"), "online": sum(1 for v in d.values() if cat(v) == "online"),
           "visa": sum(1 for v in d.values() if cat(v) == "visa")} for c, d in vis.items()}
popt = "".join(f'<option value="{c}"{" selected" if c == "UY" else ""}>{n}</option>' for c, n in sorted(LAT.items(), key=lambda kv: kv[1]))
page("site/visas/index.html", "¿Necesito visa? Pasaportes de Latinoamérica",
     "A qué países podés viajar sin visa, con trámite online o con visa, según tu pasaporte latinoamericano. Ranking de pasaportes de la región.",
     f"""<header><div class="eyebrow">Datos al {html.escape(fecha_v)}</div><h1>¿Necesito visa?</h1>
<p class="lede">Elegí tu pasaporte y mirá a qué países podés entrar sin visa, con autorización online o con visa consular, y por cuántos días.</p></header>
<div class="row"><select id="pp" aria-label="Pasaporte">{popt}</select><input id="q" type="search" placeholder="Buscar destino: Japón, España…" aria-label="Buscar destino">
<select id="f" aria-label="Filtro"><option value="">Todos</option><option value="libre">Sin visa o visa al llegar</option><option value="online">Trámite online (e-visa, ETA)</option><option value="visa">Visa consular</option></select></div>
<section class="kpis" id="kp"></section>
<section class="panel"><table><thead><tr><th>Destino</th><th>Requisito</th></tr></thead><tbody id="tb"></tbody></table></section>
<section class="panel"><h2>Ranking de pasaportes latinoamericanos</h2><table><thead><tr><th>Pasaporte</th><th class="num">Sin visa</th><th class="num">Online</th><th class="num">Con visa</th></tr></thead><tbody>
{"".join(f'<tr><td>{LAT[c]}</td><td class="num">{v["libre"]}</td><td class="num">{v["online"]}</td><td class="num">{v["visa"]}</td></tr>' for c, v in sorted(res.items(), key=lambda kv: -kv[1]["libre"]))}</tbody></table></section>
{CTA.format(t="Avisos de cambios de visas para tu pasaporte", d="Te avisamos cuando un país cambia los requisitos para tu pasaporte. Gratis.")}
<footer>Fuente: Passport Index Data (base pública, última actualización {html.escape(fecha_v)}). Los requisitos cambian: antes de viajar confirmá siempre en el consulado o la web oficial de migraciones del destino. "Sin visa" incluye visa al llegar. <a href="../">Pulso del Sur</a></footer>
<script>
const V={json.dumps(vis, ensure_ascii=False)};const N0={json.dumps(nombres, ensure_ascii=False)};let DN=null;try{{DN=new Intl.DisplayNames(["es"],{{type:"region"}})}}catch(e){{}}const N=new Proxy({{}},{{get:(o,k)=>{{try{{return (DN&&DN.of(k))||N0[k]||k}}catch(e){{return N0[k]||k}}}}}});const $=id=>document.getElementById(id);
const cat=v=>/^\\d+$/.test(v)||v==="visa free"||v==="visa on arrival"||v==="-1"?"libre":(v==="eta"||v==="e-visa")?"online":v==="no admission"?"no":"visa";
const txt=v=>/^\\d+$/.test(v)?`Sin visa · ${{v}} días`:v==="visa free"?"Sin visa":v==="visa on arrival"?"Visa al llegar":v==="eta"?"Autorización online (ETA/ESTA)":v==="e-visa"?"Visa online (e-visa)":v==="no admission"?"Sin ingreso":v==="-1"?"Mismo país":"Visa consular";
function draw(){{const p=$("pp").value,q=$("q").value,f=$("f").value;const d=V[p]||{{}};
 const nz=t=>t.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");const rows=Object.entries(d).filter(([k,v])=>v!=="-1").map(([k,v])=>[N[k.toUpperCase()]||k,v]).filter(([n,v])=>(!q||nz(n).includes(nz(q)))&&(!f||cat(v)===f)).sort((a,b)=>a[0].localeCompare(b[0],"es"));
 const all=Object.values(d).filter(v=>v!=="-1");
 $("kp").innerHTML=`<div class="kpi"><b>${{all.filter(v=>cat(v)==="libre").length}}</b><span>destinos sin visa o con visa al llegar</span></div><div class="kpi"><b>${{all.filter(v=>cat(v)==="online").length}}</b><span>con trámite online</span></div><div class="kpi"><b>${{all.filter(v=>cat(v)==="visa").length}}</b><span>con visa consular</span></div>`;
 $("tb").innerHTML=rows.map(([n,v])=>`<tr><td>${{n}}</td><td><span class="tag ${{cat(v)==="libre"?"ok":cat(v)==="visa"?"hot":""}}">${{txt(v)}}</span></td></tr>`).join("")}}
["pp","q","f"].forEach(i=>$(i).addEventListener("input",draw));draw();
</script>""")
print("feriados", {c: len(v) for c, v in fer.items()}, "· sismos", len(rs), "· visas al", fecha_v)
