"""Radar de compras públicas de Uruguay — llamados abiertos y adjudicaciones desde los datos abiertos de ARCE (OCDS).
Mantiene un cache en licitaciones/cache.json (lo commitea GitHub Actions) y escribe site/licitaciones/."""
import json, os, re, csv, html, datetime as dt, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
from fetch import get, getj          # mismas utilidades de descarga con reintentos

TZ = ZoneInfo("America/Montevideo")
NOW = dt.datetime.now(TZ)
TODAY = NOW.date()
BASE = "https://www.comprasestatales.gub.uy/ocds"
CACHE = "licitaciones/cache.json"
OUT = "site/licitaciones"


def load():
    try:
        return json.load(open(CACHE))
    except Exception:
        return {"tenders": {}, "awards": {}, "seen": []}


def rss(url):
    items = []
    for it in ET.fromstring(get(url, timeout=90)).iter("item"):
        items.append((it.findtext("guid"), it.findtext("category"), it.findtext("pubDate")))
    return items


def fetch_release(rid):
    try:
        return rid, getj(f"{BASE}/release/{rid}", tries=2, timeout=40)
    except Exception:
        return rid, None


def parse_tender(r):
    t = r.get("tender", {})
    end = (t.get("tenderPeriod") or {}).get("endDate")
    docs = [d.get("url") for d in t.get("documents", []) if d.get("url")]
    return {"id": r.get("ocid", "").split("-")[-1] or r.get("id"), "comprador": (r.get("buyer") or {}).get("name", ""),
            "titulo": t.get("title") or "", "descripcion": (t.get("description") or "").strip(),
            "tipo": t.get("procurementMethodDetails") or "", "cierre": end,
            "items": [(i.get("description") or "")[:120] for i in t.get("items", [])][:8],
            "pliego": docs[0] if docs else ""}


def parse_award(r):
    out = []
    for a in r.get("awards", []):
        prov = ", ".join(s.get("name", "") for s in a.get("suppliers", []))
        for i in a.get("items", []):
            u = i.get("unit", {}).get("value") or {}
            qty = i.get("quantity") or 0
            amt = u.get("amount")
            out.append({"proveedor": prov, "item": (i.get("description") or "")[:140], "cantidad": qty,
                        "precio_unitario": amt, "moneda": u.get("currency", ""),
                        "total": round(qty * amt, 2) if (amt is not None and qty) else None})
    return {"id": r.get("id", ""), "comprador": (r.get("buyer") or {}).get("name", ""),
            "fecha": (r.get("date") or "")[:10], "lineas": out}


def update(cache):
    seen = set(cache["seen"])
    items = rss(f"{BASE}/rss")
    if not cache["tenders"]:                      # primera corrida: llamados del mes actual y del anterior
        prev = (TODAY.replace(day=1) - dt.timedelta(days=1))
        for y, m in [(prev.year, prev.month), (TODAY.year, TODAY.month)]:
            items += [x for x in rss(f"{BASE}/rss/{y}/{m:02d}") if x[1] == "tender"]
    todo = list({rid: cat for rid, cat, _ in items if rid and rid not in seen and cat in ("tender", "award")}.items())
    with ThreadPoolExecutor(8) as ex:
        for rid, data in ex.map(lambda x: fetch_release(x[0]), todo):
            if not data or not data.get("releases"):
                continue
            r = data["releases"][0]
            if rid.startswith("llamado"):
                t = parse_tender(r)
                cache["tenders"][rid] = t
            elif rid.startswith("adjudicacion"):
                a = parse_award(r)
                if a["lineas"]:
                    cache["awards"][rid] = a
            seen.add(rid)
    # limpieza: llamados cerrados hace más de 7 días, adjudicaciones de más de 35 días
    lim_t = (TODAY - dt.timedelta(days=7)).isoformat()
    lim_a = (TODAY - dt.timedelta(days=35)).isoformat()
    cache["tenders"] = {k: v for k, v in cache["tenders"].items() if (v.get("cierre") or "9999")[:10] >= lim_t}
    cache["awards"] = {k: v for k, v in cache["awards"].items() if v.get("fecha", "") >= lim_a}
    keep = set(cache["tenders"]) | set(cache["awards"])
    cache["seen"] = sorted((seen & keep) | {rid for rid, _, _ in items})[-6000:]
    cache["actualizado"] = NOW.replace(tzinfo=None).isoformat(timespec="minutes")
    return len(todo)


def money(v, cur):
    if v is None:
        return ""
    return f"{cur} {v:,.0f}".replace(",", ".")


def render(cache):
    os.makedirs(OUT, exist_ok=True)
    # ARCE publica la hora de cierre como hora local de Uruguay aunque lleve la marca "Z": se compara tal cual
    nowl = NOW.replace(tzinfo=None).isoformat()[:16]
    soonl = (NOW + dt.timedelta(days=3)).replace(tzinfo=None).isoformat()[:16]
    abiertos = sorted([t for t in cache["tenders"].values() if (t.get("cierre") or "")[:16] >= nowl],
                      key=lambda t: t.get("cierre") or "")
    # CSV gratis de llamados abiertos
    with open(f"{OUT}/llamados-abiertos.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id_compra", "comprador", "tipo", "titulo", "descripcion", "cierre", "items", "pliego"])
        for t in abiertos:
            w.writerow([t["id"], t["comprador"], t["tipo"], t["titulo"], t["descripcion"], t["cierre"], " | ".join(t["items"]), t["pliego"]])
    # adjudicaciones de los últimos 7 días
    lim = (TODAY - dt.timedelta(days=7)).isoformat()
    lines = [dict(l, comprador=a["comprador"], fecha=a["fecha"]) for a in cache["awards"].values() if a["fecha"] >= lim for l in a["lineas"]]
    uyu = [l for l in lines if l["moneda"] == "UYU" and l["total"]]
    top = sorted(uyu, key=lambda l: -l["total"])[:15]
    n_prov = len({l["proveedor"] for l in lines})
    cierran = [t for t in abiertos if (t.get("cierre") or "")[:16] <= soonl]
    data_js = json.dumps([[t["id"], t["comprador"], t["tipo"], t["titulo"], t["descripcion"][:300], (t["cierre"] or "")[:16],
                           " · ".join(t["items"][:4]), t["pliego"], int((t.get("cierre") or "")[:16] <= soonl)]
                          for t in abiertos], ensure_ascii=False, separators=(",", ":"))
    top_rows = "".join(f'<tr><td>{html.escape(l["fecha"][8:10] + "/" + l["fecha"][5:7])}</td><td>{html.escape(l["comprador"])}</td>'
                       f'<td>{html.escape(l["item"])}</td><td>{html.escape(l["proveedor"])}</td><td class="num">{money(l["total"], "$")}</td></tr>'
                       for l in top)
    page = PAGE
    for a, b in {"{{N_ABIERTOS}}": str(len(abiertos)), "{{N_CIERRAN}}": str(len(cierran)), "{{N_ADJ}}": str(len(lines)),
                 "{{N_PROV}}": str(n_prov), "{{ACT}}": NOW.strftime("%d/%m/%Y %H:%M"), "{{DATA}}": data_js, "{{TOP}}": top_rows}.items():
        page = page.replace(a, b)
    open(f"{OUT}/index.html", "w").write(page)
    return len(abiertos), len(lines)


PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Radar de Compras Públicas · Uruguay</title>
<meta name="description" content="Llamados abiertos del Estado uruguayo en un buscador simple, y quién ganó las últimas adjudicaciones y a qué precio. Datos abiertos de ARCE, actualización diaria.">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,500..800&family=Public+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{--bg:#f6f6f2;--surface:#fff;--fg:#1d1f1a;--muted:#62665c;--rule:#dfe0d8;--accent:#2f5d2a;--warn:#9a5b00;--warn-bg:#fbf0dc;
--display:"Archivo","Arial Narrow",system-ui,sans-serif;--body:"Public Sans",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#141612;--surface:#1c1f19;--fg:#e8eae2;--muted:#9da394;--rule:#30342b;--accent:#9bd18f;--warn:#f0b75a;--warn-bg:#3a2d14;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 var(--body);padding:32px max(16px,env(safe-area-inset-left,0px)) 56px max(16px,env(safe-area-inset-right,0px))}
.wrap{max-width:1080px;margin:0 auto;display:grid;grid-template-columns:minmax(0,1fr);gap:36px}.wrap>*{min-width:0}
.eyebrow{font:500 12px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
h1{font:800 clamp(36px,6vw,60px)/.95 var(--display);font-stretch:78%;margin:8px 0}
h2{font:700 24px/1.1 var(--display);font-stretch:85%;margin:0 0 6px}
.lede,.note{color:var(--muted);max-width:68ch;margin:0}.note{font-size:14px;margin-bottom:12px}
.kpis{display:flex;flex-wrap:wrap;gap:12px 28px;font:13px var(--mono);color:var(--muted)}.kpis b{display:block;font:700 26px var(--display);color:var(--fg)}
input{font:16px var(--body);padding:10px 12px;border:1px solid var(--rule);border-radius:6px;background:var(--surface);color:var(--fg);width:100%;box-sizing:border-box}
.list{display:grid;gap:10px}.card{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:14px 16px;display:grid;gap:4px}
.card h3{margin:0;font:600 16px/1.3 var(--body)}.meta{font:12.5px var(--mono);color:var(--muted);display:flex;flex-wrap:wrap;gap:4px 14px}
.soon{background:var(--warn-bg);color:var(--warn);border-radius:99px;padding:1px 8px}
.card p{margin:0;font-size:14px;color:var(--muted)}a{color:var(--accent)}
.ledger{overflow-x:auto;background:var(--surface);border:1px solid var(--rule);border-radius:6px}
table{width:100%;border-collapse:collapse;min-width:720px;font-size:14px}th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--rule);vertical-align:top}
th{font:500 11px var(--mono);text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}.num{text-align:right;font-family:var(--mono);white-space:nowrap}
.pro{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:20px;display:grid;gap:8px;max-width:640px}
.pro ul{margin:0;padding-left:18px;font-size:14px}.btn{justify-self:start;background:var(--accent);color:var(--bg);padding:10px 16px;border-radius:6px;font-weight:600;opacity:.55}
#more{justify-self:start;font:600 14px var(--body);padding:8px 14px;border:1px solid var(--rule);border-radius:6px;background:var(--surface);color:var(--fg);cursor:pointer}
footer{font-size:13px;color:var(--muted)}
</style></head><body><div class="wrap">
<header><div class="eyebrow">Datos abiertos de ARCE · actualización diaria</div><h1>Radar de Compras Públicas</h1>
<p class="lede">Lo que el Estado uruguayo está comprando ahora, en un buscador simple. Y quién ganó las últimas licitaciones y a qué precio.</p>
<p class="note" style="margin-top:8px">Actualizado {{ACT}} (hora de Uruguay) · <a href="../">Pulso del Sur</a></p>
<div class="kpis"><span><b>{{N_ABIERTOS}}</b>llamados abiertos</span><span><b>{{N_CIERRAN}}</b>cierran en 3 días</span><span><b>{{N_ADJ}}</b>ítems adjudicados en 7 días</span><span><b>{{N_PROV}}</b>proveedores ganadores</span></div></header>
<section><h2>Llamados abiertos</h2><p class="note">Buscá por producto, servicio u organismo. Ordenados por fecha de cierre.</p>
<input id="q" type="search" placeholder="Ej.: computadoras, limpieza, UTE, Paysandú" aria-label="Buscar llamados">
<p class="note" id="count" style="margin-top:10px"></p><div class="list" id="list"></div><button id="more" hidden>Ver más</button>
<p class="note" style="margin-top:12px">Lista completa en <a href="llamados-abiertos.csv">llamados-abiertos.csv</a>.</p></section>
<section><h2>Las adjudicaciones más grandes de la semana</h2><p class="note">Ítems adjudicados en pesos en los últimos 7 días, por monto total.</p>
<div class="ledger"><table><thead><tr><th>Fecha</th><th>Comprador</th><th>Ítem</th><th>Ganó</th><th class="num">Total</th></tr></thead><tbody>{{TOP}}</tbody></table></div></section>
<section class="pro"><h2>Radar Pro</h2><p class="note" style="margin:0">Para empresas que le venden al Estado.</p>
<ul><li>Excel semanal con todas las adjudicaciones: proveedor ganador, precio unitario, cantidad y organismo</li><li>Llamados nuevos agrupados por rubro</li><li>Para saber a qué precio gana tu competencia antes de cotizar</li></ul>
<span class="btn" aria-disabled="true">Disponible muy pronto · USD 10 por mes</span></section>
<footer>Fuente: Agencia Reguladora de Compras Estatales (ARCE), datos abiertos en formato OCDS. Este sitio no es oficial. Verificá siempre los pliegos en comprasestatales.gub.uy.</footer>
</div>
<script id="d" type="application/json">{{DATA}}</script>
<script>
(function(){var D=JSON.parse(document.getElementById('d').textContent),L=document.getElementById('list'),Q=document.getElementById('q'),C=document.getElementById('count'),M=document.getElementById('more'),n=30;
function norm(s){return (s||'').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')}
function esc(s){return String(s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function f(iso){return iso?iso.slice(8,10)+'/'+iso.slice(5,7)+' '+iso.slice(11,16)+' h':'sin fecha'}
function draw(){var q=norm(Q.value).split(/\\s+/).filter(Boolean),r=D.filter(function(t){var s=norm(t.join(' '));return q.every(function(w){return s.indexOf(w)>=0})});
C.textContent=r.length+' llamados'+(q.length?' coinciden':'');L.innerHTML=r.slice(0,n).map(function(t){var s=t[8]===1;
return '<article class="card"><h3>'+esc(t[4]||t[3])+'</h3><div class="meta"><span>'+esc(t[1])+'</span><span>'+esc(t[2])+' · '+esc(t[3])+'</span><span'+(s?' class="soon"':'')+'>Cierra '+f(t[5])+'</span></div>'+(t[6]?'<p>'+esc(t[6])+'</p>':'')+(t[7]?'<p><a href="'+esc(t[7])+'" rel="noopener">Pliego</a> · id '+esc(t[0])+'</p>':'')+'</article>'}).join('');M.hidden=r.length<=n}
Q.addEventListener('input',function(){n=30;draw()});M.addEventListener('click',function(){n+=30;draw()});draw()})();
</script></body></html>"""

if __name__ == "__main__":
    os.makedirs("licitaciones", exist_ok=True)
    c = load()
    nuevos = update(c)
    json.dump(c, open(CACHE, "w"), ensure_ascii=False, separators=(",", ":"))
    a, l = render(c)
    print(f"releases nuevos: {nuevos} · abiertos: {a} · líneas adjudicadas 7d: {l}")
