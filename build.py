"""Pulso del Sur — arma el sitio a partir de data.json.
Salidas: site/index.html (documento completo, GitHub Pages) y artifact.html (solo el cuerpo, para la vista previa en Claude)."""
import json, html, os, datetime as dt

d = json.load(open("data.json"))
P = d["paises"]
ORDER = ["UY", "AR", "BR", "CL", "PE", "CO", "MX"]
NAMES = {"UY": "Uruguay", "AR": "Argentina", "BR": "Brasil", "CL": "Chile", "PE": "Perú", "CO": "Colombia", "MX": "México"}
MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESL = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
GEN = dt.datetime.fromisoformat(d["generado"])


def fd(s):
    x = dt.date.fromisoformat(s)
    return f"{x.day} {MES[x.month - 1]}"


def ym(m):
    return f"{MESL[int(m[5:]) - 1]} {m[:4]}"


def fmt(v):
    if v >= 1000:
        return f"{v:,.0f}".replace(",", ".")
    if v >= 100:
        return f"{v:,.1f}".replace(".", ",")
    return f"{v:.3f}".replace(".", ",") if v < 10 else f"{v:.2f}".replace(".", ",")


def es(v, dec):
    """Número con formato rioplatense: punto de miles, coma decimal."""
    return f"{v:,.{dec}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def pct(v):
    return ("+" if v > 0 else "") + f"{v:.1f}".replace(".", ",") + "%"


def chg(fx, days):
    ld = dt.date.fromisoformat(fx[-1][0])
    t = (ld - dt.timedelta(days=days)).isoformat()
    base = [x for x in fx if x[0] <= t][-1]
    return (fx[-1][1] / base[1] - 1) * 100


def cls(v):
    return "up" if v > 0.05 else ("down" if v < -0.05 else "flat")


def spark(fx, w=180, h=44):
    vs = [v for _, v in fx]
    lo, hi = min(vs), max(vs)
    rng = (hi - lo) or 1
    pts = [(i * (w - 8) / (len(vs) - 1) + 4, h - 6 - (v - lo) / rng * (h - 12)) for i, v in enumerate(vs)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"4,{h - 2} " + line + f" {pts[-1][0]:.1f},{h - 2}"
    x, y = pts[-1]
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" role="img" aria-label="Evolución 90 días">'
            f'<polygon points="{area}" fill="var(--area)"/><polyline points="{line}" fill="none" stroke="var(--line)" stroke-width="1.6" stroke-linejoin="round"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="var(--accent)"/></svg>')


cut90 = (GEN.date() - dt.timedelta(days=92)).isoformat()

# ---------- tabla principal
rows, ok = [], 0
for k in ORDER:
    p = P.get(k)
    if not p:
        rows.append(f'<tr><th scope="row"><span class="cc">{k}</span>{NAMES[k]}</th><td colspan="6" class="err">'
                    f'<span class="chip bad">Fuente caída</span> No se publica: la fuente no respondió. Se reintenta en la próxima actualización.</td></tr>')
        continue
    ok += 1
    fx = p["fx"]
    f90 = [x for x in fx if x[0] >= cut90]
    infl = f'{p["infl"]:.1f}%'.replace(".", ",") if p["infl"] is not None else '<span class="muted">pendiente</span>'
    chip = '<span class="chip good">Al día</span>' if p["dias_desde_ultimo"] <= 4 else '<span class="chip warn">Revisar</span>'
    c7, c30, c90 = chg(fx, 7), chg(fx, 30), (f90[-1][1] / f90[0][1] - 1) * 100
    rows.append(f'''<tr><th scope="row"><span class="cc">{k}</span>{p["nombre"]}<small>USD/{p["moneda"]}</small></th>
<td class="num big">{fmt(fx[-1][1])}<small>{fd(fx[-1][0])}</small></td>
<td class="num {cls(c7)}">{pct(c7)}</td><td class="num {cls(c30)}">{pct(c30)}</td>
<td class="sp">{spark(f90)}<small>{pct(c90)} en 90 días</small></td>
<td class="num">{infl}<small>{html.escape(p["infl_ref"])}</small></td><td>{chip}</td></tr>''')

# ---------- cierre del último mes cerrado
lastm = max(max(p["mensual"]) for p in P.values())
crow = []
for k in ORDER:
    p = P.get(k)
    m = p and p["mensual"].get(lastm)
    if not m:
        continue
    crow.append(f'<tr><th scope="row">{p["nombre"]}<small>USD/{p["moneda"]}</small></th>'
                f'<td class="num">{es(m["cierre"], 4)}</td><td class="num">{es(m["promedio"], 4)}</td>'
                f'<td class="num">{pct((m["cierre"] / m["promedio"] - 1) * 100)}</td><td class="num">{m["dias"]}</td></tr>')
CIERRE = "\n".join(crow)

# ---------- expectativas
exp_rows = []
if "BR" in P:
    for e in P["BR"].get("expectativas", []):
        val = f'R$ {e["mediana"]:.2f}'.replace(".", ",") if e["indicador"].startswith("Dólar") else f'{e["mediana"]:.2f}%'.replace(".", ",")
        exp_rows.append(f'<tr><th scope="row">Brasil</th><td>{e["indicador"]}</td><td class="num">{e["anio"]}</td>'
                        f'<td class="num big">{val}</td><td class="num">{e["n"]}</td><td class="num">{fd(e["fecha"])}</td></tr>')
EXP = "\n".join(exp_rows)

# ---------- tipo de cambio real
def tcr_chart(series, w=640, h=230):
    ms = sorted(set().union(*[set(s) for s in series.values()]))
    vals = [v for s in series.values() for v in s.values()]
    lo, hi = min(min(vals), 90), max(vals)
    lo, hi = (int(lo // 10) * 10), (int(hi // 10 + 1) * 10)
    L, R, T, B = 44, 118, 14, 30
    X = lambda i: L + i * (w - L - R) / (len(ms) - 1)
    Y = lambda v: T + (hi - v) / (hi - lo) * (h - T - B)
    g = []
    for v in range(lo, hi + 1, 20 if hi - lo > 60 else 10):
        g.append(f'<line x1="{L}" x2="{w - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="var(--rule)" stroke-width="1"/>'
                 f'<text x="{L - 8}" y="{Y(v) + 4:.1f}" text-anchor="end" class="ax">{v}</text>')
    g.append(f'<line x1="{L}" x2="{w - R}" y1="{Y(100):.1f}" y2="{Y(100):.1f}" stroke="var(--muted)" stroke-dasharray="3 3" stroke-width="1"/>')
    for i, m in enumerate(ms):
        if m.endswith("-01") or i == len(ms) - 1:
            g.append(f'<text x="{X(i):.1f}" y="{h - 8}" text-anchor="middle" class="ax">{MES[int(m[5:]) - 1]} {m[2:4]}</text>')
    colors = {"AR": "var(--accent)", "BR": "var(--line2)"}
    for k, s in series.items():
        pts = [(X(ms.index(m)), Y(v)) for m, v in sorted(s.items())]
        g.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" stroke="{colors[k]}" stroke-width="2.2" stroke-linejoin="round"/>')
        x, y = pts[-1]
        g.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{colors[k]}"/>'
                 f'<text x="{x + 8:.1f}" y="{y + 4:.1f}" class="lab" fill="{colors[k]}">{NAMES[k]} {list(sorted(s.items()))[-1][1]:.0f}</text>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Tipo de cambio real de Uruguay">{"".join(g)}</svg>'


TCR = tcr_chart(d["tcr"]) if d.get("tcr") else "<p class='muted'>Sin datos esta semana.</p>"
tlast = {k: sorted(v.items())[-1] for k, v in d.get("tcr", {}).items()}
TCR_TXT = " ".join(
    f'Frente a {NAMES[k]}: {v:.0f} a {ym(m)} ({"Uruguay " + ("más barato" if v > 100 else "más caro")} que en enero de 2024 en {abs(v - 100):.0f}%).'
    for k, (m, v) in tlast.items())

# ---------- resumen automático de la semana (solo describe cifras)
movs = sorted(((abs(chg(P[k]["fx"], 7)), k) for k in P), reverse=True)
top = movs[0][1]
t7 = chg(P[top]["fx"], 7)
lines = [f'<h3>{"El dólar subió" if t7 > 0 else "El dólar bajó"} {abs(t7):.1f}% en {P[top]["nombre"]}</h3>'.replace(".", ","),
         f'<p>Fue el mayor movimiento semanal de la región: cotiza {fmt(P[top]["fx"][-1][1])} {P[top]["moneda"]} por dólar al {fd(P[top]["fx"][-1][0])}.</p>']
if "UY" in P and top != "UY":
    u = P["UY"]
    lines.append(f'<p>En Uruguay el dólar interbancario está en <b>$ {fmt(u["fx"][-1][1])}</b> ({pct(chg(u["fx"], 7))} en la semana). '
                 f'La Unidad Indexada vale {str(u["extra"]["UI"][1]).replace(".", ",")}.</p>')
items = "".join(f'<li><b>{P[k]["nombre"]}:</b> {fmt(P[k]["fx"][-1][1])} ({pct(chg(P[k]["fx"], 7))} en 7 días)</li>'
                for k in ORDER if k in P and k not in (top, "UY"))
lines.append(f"<ul>{items}</ul>")
if d["errores"]:
    lines.append(f'<p class="fine">Sin publicar esta vez: {", ".join(html.escape(e) for e in d["errores"])}.</p>')
RESUMEN = "\n".join(lines)

# ---------- datos para las calculadoras (en la página, sin pedidos externos)
calc = {"fx": {P[k]["moneda"]: [P[k]["fx"][-1][1], P[k]["fx"][-1][0], P[k]["nombre"]] for k in ORDER if k in P},
        "ui": P["UY"]["ui"] if "UY" in P else []}
calc["fx"]["USD"] = [1, "", "Estados Unidos"]
CALC = json.dumps(calc, separators=(",", ":"))

# ---------- vista previa del plan Pro: muestra real de dos hojas del Excel
pm = sorted({m for p in P.values() for m in p["mensual"]})[-3:]
pv_head = "".join(f'<th class="num" colspan="2">{MES[int(m[5:]) - 1]} {m[:4]}</th>' for m in pm)
pv_sub = '<th class="num">Cierre</th><th class="num">Prom.</th>' * len(pm)
pv_rows = "".join(
    f'<tr><th scope="row">{P[k]["nombre"]}</th>' + "".join(
        (f'<td class="num">{es(P[k]["mensual"][m]["cierre"], 2)}</td><td class="num">{es(P[k]["mensual"][m]["promedio"], 2)}</td>'
         if m in P[k]["mensual"] else '<td></td><td></td>') for m in pm) + '</tr>'
    for k in ["UY", "AR", "BR"] if k in P)
PV1 = f'<table class="compact"><thead><tr><th>País</th>{pv_head}</tr><tr><th></th>{pv_sub}</tr></thead><tbody>{pv_rows}</tbody></table>'
bud = []
for k in ["UY", "AR", "BR"]:
    if k not in P:
        continue
    p = P[k]
    p3 = sum(p["mensual"][m]["promedio"] for m in pm if m in p["mensual"]) / max(1, sum(m in p["mensual"] for m in pm))
    focus = next((e for e in p.get("expectativas", []) if e["indicador"].startswith("Dólar") and e["anio"] == str(GEN.year + 1)), None)
    sup = focus["mediana"] if focus else p3
    bud.append(f'<tr><th scope="row">{p["nombre"]}</th><td class="num">{es(p["fx"][-1][1], 2)}</td><td class="num">{es(p3, 2)}</td>'
               f'<td class="num">{es(focus["mediana"], 2) if focus else "–"}</td><td class="num big">{es(sup, 2)}</td>'
               f'<td class="num">{es(sup * 0.9, 2)}</td><td class="num">{es(sup * 1.1, 2)}</td></tr>')
PV2 = ('<table class="compact"><thead><tr><th>País</th><th class="num">Último</th><th class="num">Prom. 3 meses</th>'
       '<th class="num">Mercado</th><th class="num">Supuesto</th><th class="num">−10%</th><th class="num">+10%</th></tr></thead>'
       f'<tbody>{"".join(bud)}</tbody></table>')

src = "".join(f'<li><b>{P[k]["nombre"]}</b>: {html.escape(P[k]["fx_fuente"])}. Inflación: {html.escape(P[k]["infl_fuente"])}.</li>' for k in ORDER if k in P)
if "BR" in P:
    src += f'<li><b>Expectativas</b>: {html.escape(P["BR"]["exp_fuente"])}.</li>'

page = open("template.html").read()
for a, b in {"{{ROWS}}": "\n".join(rows), "{{OK}}": str(ok), "{{TOTAL}}": str(len(ORDER)),
             "{{FECHA}}": f"{GEN.day} {MES[GEN.month - 1]} {GEN.year}, {GEN:%H:%M}", "{{SOURCES}}": src,
             "{{RESUMEN}}": RESUMEN, "{{CIERRE}}": CIERRE, "{{MESCIERRE}}": ym(lastm), "{{EXP}}": EXP,
             "{{TCR}}": TCR, "{{TCRTXT}}": TCR_TXT, "{{CALC}}": CALC, "{{ANIO}}": str(GEN.year + 1), "{{PV1}}": PV1, "{{PV2}}": PV2}.items():
    page = page.replace(a, b)

open("artifact.html", "w").write(page)
os.makedirs("site", exist_ok=True)
head = ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        '<meta name="description" content="Dólar, inflación y tipos de cambio de cierre de 7 países de América del Sur y México, con fuente oficial y actualización diaria.">'
        '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}</style></head><body>')
open("site/index.html", "w").write(head + page + "</body></html>")
print("ok", ok, "países")
