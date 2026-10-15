"""Abrí tu negocio UY — qué trámites necesitás para habilitar un negocio, por rubro y departamento.
Fuente principal: Catálogo de trámites y servicios del Estado (AGESIC, datos abiertos, se actualiza a diario).
Los pasos que no están en el catálogo (Bomberos, BSE, Intendencia de Montevideo, INAU) van a mano, con su fuente oficial.
Genera site/habilitar/index.html y una página por rubro (site/habilitar/<rubro>/)."""
import csv, json, os, re, io, html, subprocess, datetime as dt, unicodedata
from zoneinfo import ZoneInfo

CA = "/root/.ccr/ca-bundle.crt"
NOW = dt.datetime.now(ZoneInfo("America/Montevideo"))
OUT = "site/habilitar"
os.makedirs(OUT, exist_ok=True)


def get(url, binary=False):
    r = subprocess.run(["curl", "-sS", "-L", "--retry", "4", "--max-time", "300"] + (["--cacert", CA] if os.path.exists(CA) else []) + [url],
                       capture_output=True, check=True).stdout
    return r if binary else r.decode("utf-8", "replace")


pk = json.loads(get("https://catalogodatos.gub.uy/api/3/action/package_show?id=agesic-guia-de-tramites"))["result"]
csv_url = next(x["url"] for x in pk["resources"] if x["format"].upper() == "CSV")
raw = b""
for _ in range(4):
    raw = get(csv_url, binary=True)
    if len(raw) > 1_000_000 and not raw.lstrip().startswith(b"<"):
        break
else:
    raise SystemExit("hab: no se pudo bajar el catálogo de trámites")
csv.field_size_limit(10 ** 9)
rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
BY = {r["url"].rstrip("/").rsplit("/", 1)[-1]: r for r in rows if r["url"]}


def clean(s, n=260):
    s = " ".join((s or "").split())
    s = re.sub(r"\s*(Por mayor información|Más información|En caso de)\b.*$", "", s)
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def costo(r):
    u, v = r["unidad"].strip(), r["valor"].strip()
    if u in ("U.R.", "U.I.", "$") and v:
        return f"{v.replace('.', ',')} {'UR' if u == 'U.R.' else 'UI' if u == 'U.I.' else '$'}"
    if u == "Sin definir":
        return "Costo: ver ficha"
    return ""


def cat(slug, nivel="Obligatorio", nota=""):
    r = BY.get(slug)
    if not r:
        print("hab: falta en el catálogo:", slug)
        return None
    org = r["institucion_padre_organizacional_nombre"] or r["institucion_nombre"]
    if r["institucion_nombre"] and r["institucion_nombre"] != org and org.isupper() is False:
        org = f"{org} · {r['institucion_nombre']}"
    return {"t": r["nombre_tramite"].strip(), "org": org.strip(), "q": clean(r["ques_es"]), "c": costo(r),
            "can": r["canales_de_atencion"].replace("internet", "en línea").replace("persona", "presencial").replace("telefono", "teléfono"),
            "u": r["url"], "act": r["actualizado"], "n": nivel, "nota": nota}


def man(t, org, q, links, nivel="Obligatorio", nota=""):
    return {"t": t, "org": org, "q": q, "c": "", "can": "", "u": links[0][1], "links": links, "act": "", "n": nivel, "nota": nota}


# ---------------- pasos ----------------
FORMAS = {
    "unipersonal": ("Empresa unipersonal", "inscripcion-empresa-unipersonal"),
    "monotributo": ("Monotributo", "inscripcion-empresa-unipersonal-monotributo"),
    "sas": ("Sociedad por Acciones Simplificada (SAS)", "inscripcion-sociedad-acciones-simplificada-formacion-sas"),
    "srl": ("Sociedad de Responsabilidad Limitada (SRL)", "inscripcion-sociedades-personales-contrato-sociedades-colectiva-srl-comandita-simple"),
    "sa": ("Sociedad Anónima (SA)", "inscripcion-sociedad-anonima-formacion"),
}
P = {k: cat(s, nota="Te inscribe en DGI y BPS. Es lo primero: el RUT y el certificado de BPS te los piden en casi todos los demás trámites.")
     for k, (_, s) in FORMAS.items()}

P["bomberos"] = man(
    "Autorización de Bomberos (Dirección Nacional de Bomberos)", "Ministerio del Interior · Bomberos",
    "Todo local que no sea vivienda de una familia necesita autorización de Bomberos (Ley 15.896, Decreto 372/023). La gestiona un técnico "
    "registrado ante Bomberos, que presenta el proyecto en línea. Para locales de hasta 750 m² y hasta 12 m de altura corresponde el trámite "
    "más simple (Proyecto Técnico – Certificación, PTC). Vale hasta 4 años y se renueva.",
    [("Trámites ante Bomberos", "https://www.gub.uy/ministerio-interior/politicas-y-gestion/tramites-ante-bomberos"),
     ("Consultar locales habilitados", "https://www.gub.uy/ministerio-interior/tramites-y-servicios/servicios/formulario-consulta-locales-habilitados-bomberos"),
     ("Decreto 372/023", "https://impo.com.uy/bases/decretos/372-2023")],
    nota="Buscá un técnico registrado ante Bomberos. Muchas intendencias piden esta autorización (o el trámite iniciado) para habilitarte.")
P["runaev_emp"] = cat("inscripcion-empresa-runaev", nota="Para cualquier negocio que elabore, fraccione, almacene, distribuya o venda alimentos. Se hace en línea y vale en todo el país.")
P["runaev_local"] = cat("habilitacion-local-runaev", nota="Habilitación bromatológica del local donde manipulás alimentos (la inspecciona tu intendencia).")
P["runaev_veh"] = cat("habilitacion-vehiculo-runaev", nota="Incluye food trucks, puestos rodantes y vehículos de reparto de alimentos.")
P["bromato_dir"] = man(
    "Oficina de Bromatología de tu intendencia", "Congreso de Intendentes",
    "Teléfonos y correos de las 19 direcciones de bromatología, para consultar inspección, carné de manipulador y requisitos del local.",
    [("Directorio de bromatología", "https://www.gub.uy/congreso-intendentes/datos-y-estadisticas/datos/direcciones-bromatologia")],
    nivel="Según tu caso")
P["carne_salud"] = cat("carne-salud", nota="Todos los trabajadores, incluido vos si trabajás en el negocio. En alimentos suele pedirse además el carné de manipulador.")
P["bps_dep"] = man(
    "Declarar a tus trabajadores en BPS", "Banco de Previsión Social",
    "Cada trabajador se da de alta en BPS antes de empezar. Desde 2017 la planilla de trabajo del MTSS sale de los registros de BPS "
    "(Planilla de Trabajo Unificada): no hay que registrarla aparte.",
    [("BPS · trámites para empresas", "https://www.bps.gub.uy/12622/empresarios.html"),
     ("Planilla de Trabajo Unificada (MTSS)", "https://www.gub.uy/ministerio-trabajo-seguridad-social/comunicacion/noticias/planilla-de-trabajo-unificada-de-mtss-y-bps")])
P["bse"] = man(
    "Seguro de accidentes de trabajo (BSE)", "Banco de Seguros del Estado",
    "Si tenés empleados, el seguro de accidentes de trabajo y enfermedades profesionales es obligatorio y lo da el BSE (Ley 16.074). "
    "Se contrata antes de que el trabajador empiece.",
    [("BSE · seguro para empresas", "https://www.bse.com.uy/portal-comercial/seguros/seguro-adt-empresa/adt-empresas/"),
     ("Ley 16.074 (PDF)", "https://www.bse.com.uy/wps/wcm/connect/ee6db5e8-6035-4efe-90f9-4d4ec2f2e3b6/LEY16074.pdf?MOD=AJPERES")])
P["inau"] = man(
    "Autorización de centro de primera infancia privado (INAU)", "Instituto del Niño y Adolescente del Uruguay",
    "Desde 2021 la autorización de los centros de educación en primera infancia privados la otorga INAU (antes era el MEC).",
    [("INAU · centros privados", "https://www.inau.gub.uy/primera-infancia/centros-de-primera-infancia-privados-cpip"),
     ("Comunicado MEC sobre la transición", "https://www.gub.uy/ministerio-educacion-cultura/comunicado-transicion")])
for k, s, n, nota in [
    ("tatuajes", "habilitacion-empresas-dedicadas-tatuajes-afines", "Obligatorio", ""),
    ("salud", "solicitud-habilitacion-modificacion-renovacion-habilitacion-servicios-salud", "Obligatorio", ""),
    ("optica", "habilitacion-establecimientos-casas-opticas", "Obligatorio", ""),
    ("farmacia", "habilitacion-apertura-farmacia-primera-categoria", "Obligatorio", ""),
    ("larga", "habilitacion-establecimiento-larga-estadia-personas-mayores", "Obligatorio", ""),
    ("mintur_aloj", "inscripcion-prestador-turistico-alojamientos", "Obligatorio", ""),
    ("mintur_agencia", "inscripcion-prestador-turistico-agencia-viajes-yo-transporte-turistico", "Obligatorio", ""),
    ("dnt_prof", "alta-empresas-direccion-nacional-transporte-dnt-empresa-carga-profesional", "Según tu caso", "Si transportás carga de terceros."),
    ("dnt_propio", "alta-empresas-direccion-nacional-transporte-dnt-empresa-carga-no-profesional-tambien-denominada-empresa-carga-transporte-propio", "Según tu caso", "Si transportás solo tu propia mercadería."),
    ("seguridad", "habilitacion-renovacion-empresas-seguridad-registro-renovacion-empresas-otros-rubros-operan-digefe", "Obligatorio", ""),
    ("gas", "renovacion-nuevo-registro-empresa-instaladora-gas", "Obligatorio", ""),
    ("plagas", "habilitacion-registro-empresas-control-plagas-domisanitarios", "Obligatorio", ""),
    ("veterinaria", "registro-comercio-expendedor-productos-veterinarios", "Según tu caso", "Si vendés productos veterinarios."),
    ("msp_fab", "habilitacion-registro-empresas-alimentos-cosmeticos-domisanitarios", "Según tu caso", "Para fabricantes, importadores o depósitos de alimentos, cosméticos o productos de limpieza."),
    ("msp_hig", "habilitacion-higienico-sanitaria-empresas", "Según tu caso", "Certificado del MSP para plantas y locales industriales; el costo depende del área, empleados y ramo."),
]:
    P[k] = cat(s, n, nota)

# ---------------- rubros ----------------
# (slug, nombre, alimentos, local por defecto, pasos propios)
RUBROS = [
    ("almacen", "Almacén, autoservicio o kiosco", True, True, []),
    ("restaurante", "Restaurante, bar o cafetería", True, True, []),
    ("panaderia", "Panadería, confitería o rotisería", True, True, []),
    ("comida-casera", "Comida casera para vender", True, True, []),
    ("food-truck", "Food truck o puesto de comida", True, False, ["runaev_veh"]),
    ("tienda", "Tienda de ropa, regalos u otro comercio", False, True, []),
    ("peluqueria", "Peluquería, barbería o estética", False, True, []),
    ("tatuajes", "Estudio de tatuajes o piercing", False, True, ["tatuajes"]),
    ("gimnasio", "Gimnasio, academia o estudio", False, True, []),
    ("oficina", "Oficina o servicios profesionales", False, True, []),
    ("online", "Venta online o servicios sin local", False, False, []),
    ("consultorio", "Consultorio o servicio de salud", False, True, ["salud"]),
    ("optica", "Óptica", False, True, ["optica"]),
    ("farmacia", "Farmacia", False, True, ["farmacia"]),
    ("residencial", "Residencial para personas mayores", True, True, ["larga"]),
    ("guarderia", "Centro de primera infancia (guardería)", True, True, ["inau"]),
    ("alojamiento", "Hostel, hotel o alojamiento turístico", False, True, ["mintur_aloj"]),
    ("agencia-viajes", "Agencia de viajes", False, True, ["mintur_agencia"]),
    ("taller", "Taller mecánico, carpintería o pequeña industria", False, True, ["msp_hig"]),
    ("fabrica", "Fábrica de alimentos, cosméticos o productos de limpieza", True, True, ["msp_fab", "msp_hig"]),
    ("transporte", "Fletes o transporte de carga", False, False, ["dnt_prof", "dnt_propio"]),
    ("seguridad", "Empresa de seguridad", False, True, ["seguridad"]),
    ("gas", "Instalador de gas", False, False, ["gas"]),
    ("plagas", "Control de plagas o fumigación", False, False, ["plagas"]),
    ("veterinaria", "Veterinaria o agroveterinaria", False, True, ["veterinaria"]),
]

# ---------------- departamentos ----------------
DEPS = ["Artigas", "Canelones", "Cerro Largo", "Colonia", "Durazno", "Flores", "Florida", "Lavalleja", "Maldonado", "Montevideo",
        "Paysandú", "Río Negro", "Rivera", "Rocha", "Salto", "San José", "Soriano", "Tacuarembó", "Treinta y Tres"]
SITIO = {"Artigas": "https://www.artigas.gub.uy", "Canelones": "https://www.imcanelones.gub.uy", "Cerro Largo": "https://www.gub.uy/intendencia-cerro-largo/inicio",
         "Durazno": "https://durazno.uy", "Florida": "https://www.gub.uy/intendencia-florida", "Lavalleja": "https://www.gub.uy/intendencia-lavalleja/mapa-sitio",
         "Maldonado": "https://www.maldonado.gub.uy/tramites", "Montevideo": "https://tramites.montevideo.gub.uy", "Paysandú": "http://www.paysandu.gub.uy",
         "Río Negro": "https://www.rionegro.gub.uy/tramites-en-linea-listado/", "Rivera": "https://www.rivera.gub.uy", "Rocha": "https://www.rocha.gub.uy",
         "Salto": "https://www.salto.gub.uy", "Soriano": "https://www.soriano.gub.uy", "Tacuarembó": "https://tacuarembo.gub.uy/?page_id=308",
         "Treinta y Tres": "https://treintaytres.gub.uy"}
EXTRA = {
    "Montevideo": [
        man("Inicio de habilitación de locales comerciales e industriales", "Intendencia de Montevideo",
            "Primer paso en la Intendencia: formulario en línea con certificado notarial (no se pide a microemprendimientos), consulta de Bomberos vigente, "
            "certificado de RUT y certificado de BPS. Es gratis; por correo te indican qué habilitaciones te corresponden.",
            [("Ir al trámite", "https://tramites.montevideo.gub.uy/tramites-y-tributos/solicitud/inicio-de-habilitacion-de-locales-comerciales-e-industriales")],
            nota="Necesitás usuario gub.uy verificado o firma electrónica."),
        man("Habilitación de locales comerciales e industriales (SIME)", "Intendencia de Montevideo",
            "Segundo paso para muchos locales: declaración jurada, planos y memoria descriptiva, con firma digital.",
            [("Ir al trámite", "https://tramites.montevideo.gub.uy/tramites-y-tributos/habilitacion/locales-comerciales-e-industriales-sime")],
            nivel="Según tu caso"),
        man("Carné de manipulador de alimentos", "Intendencia de Montevideo",
            "Curso y carné para quienes manipulan alimentos.",
            [("Ver requisitos", "https://montevideo.gub.uy/areas-tematicas/salud/regulacion-alimentaria/carne-de-manipulador-de-alimentos")],
            nivel="Alimentos"),
    ],
    "Treinta y Tres": [
        man("Formularios de habilitación bromatológica", "Intendencia de Treinta y Tres", "Formularios para empresas, vehículos y productos alimentarios.",
            [("Ver formularios", "https://treintaytres.gub.uy/formulaios-de-habilitacion-bromatologica/")], nivel="Alimentos"),
        man("Manipulación de alimentos", "Intendencia de Treinta y Tres", "Información sobre el curso y carné de manipulador.",
            [("Ver información", "https://treintaytres.gub.uy/manipulacion-de-alimentos/")], nivel="Alimentos"),
    ],
}


def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


REL = re.compile(r"HABILITACI|BROMATOL|MANIPULA|CARNE DE SALUD|VIABILIDAD|LOCALIZACION DE ACTIVIDAD|OCUPACION DE VEREDA|VENTA AMBULANTE|"
                 r"CARROS DE COMIDA|COMIDA ARTESANAL|FERIANTE|PERMISOS? DE FERIA|REGISTRO DE EMPRESAS - |ARTESANOS|CARTEL|LETRERO|PUBLICIDAD")
NOREL = re.compile(r"ESPECTACULO|EVENTO|ASCENSOR|CRIADERO|BAROMETR|RESIDUOS|FUMIGACION|PROPAGANDA SONORA|TRANSPORTISTA|FINCA|ARRENDAMIENTO|"
                   r"URBANISTICA - FLORIDA|DENUNCIA|ANTENA|RENOVACION|RODANTE|^REGISTRO DE EMPRESAS - RIVERA$|SIMULADOR|CONTRATISTA|TRAMITES EN LINEA|SALUD PARA EXPEDIR|CONDUCTOR|REHABILIT|CARNAVAL")
ALIM = re.compile(r"BROMATOL|MANIPULA|ALIMENT|COMIDA|PANADER|CARROS")
dep = {}
for d in DEPS:
    D = norm(d)
    items = []
    for r in rows:
        if norm(r["institucion_padre_organizacional_nombre"]) != D:
            continue
        n = norm(r["nombre_tramite"])
        if REL.search(n) and not NOREL.search(n.strip()):
            x = cat(r["url"].rstrip("/").rsplit("/", 1)[-1], "Alimentos" if ALIM.search(n) and "NO ALIMENT" not in n else ("Según tu caso" if re.search(r"VIABILIDAD|LOCALIZACION|VEREDA|CARTEL|LETRERO|PUBLICIDAD|AMBULANTE|FERIA|ARTESANO|CARNE DE SALUD", n) else "Obligatorio"))
            if x:
                x["org"] = f"Intendencia de {d}"
                items.append(x)
    items.sort(key=lambda x: ({"Obligatorio": 0, "Alimentos": 1, "Según tu caso": 2}.get(x["n"], 3), x["t"]))
    dep[d] = {"items": EXTRA.get(d, []) + items, "sitio": SITIO.get(d, "")}

data = {"pasos": P, "formas": {k: v[0] for k, v in FORMAS.items()},
        "rubros": [{"s": s, "n": n, "a": a, "l": l, "p": p} for s, n, a, l, p in RUBROS], "deps": dep,
        "catalogo": {"filas": len(rows), "actualizado": pk.get("metadata_modified", "")[:10]}}
json.dump(data, open(f"{OUT}/datos.json", "w"), ensure_ascii=False)

# ---------------- páginas ----------------
tpl = open("hab_template.html", encoding="utf-8").read()
e = html.escape


def estatico(rub):
    """Lista nacional sin JS (para buscadores y lectores sin JavaScript)."""
    s, n, a, l, p = rub
    pasos = [P["unipersonal"]] + [P[k] for k in p] + ([P["bomberos"]] if l else []) + ([P["runaev_emp"]] + ([P["runaev_local"]] if l else []) if a else []) + [P["bps_dep"], P["bse"], P["carne_salud"]]
    return "".join(f'<li><a href="{e(x["u"])}">{e(x["t"])}</a> — {e(x["org"])}</li>' for x in pasos if x)


def page(path, title, desc, pre, lista, canon):
    out = (tpl.replace("{{TITLE}}", e(title)).replace("{{DESC}}", e(desc)).replace("{{PRE}}", pre).replace("{{STATIC}}", lista)
           .replace("{{CANON}}", canon).replace("{{DATA}}", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
           .replace("{{FECHA}}", NOW.strftime("%d/%m/%Y")).replace("{{N}}", str(len(rows))).replace("{{ROOT}}", "../../" if pre else "../"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(out)


BASE = "https://sebauyy.github.io/pulso-del-sur/habilitar/"
page(f"{OUT}/index.html", "Qué trámites necesito para abrir un negocio en Uruguay",
     "Elegí tu rubro y tu departamento y obtené la lista de habilitaciones: DGI, BPS, Bomberos, bromatología, intendencia y más, con enlaces oficiales.",
     "", estatico(RUBROS[0]), BASE)
for rub in RUBROS:
    s, n = rub[0], rub[1]
    page(f"{OUT}/{s}/index.html", f"Habilitar {n.lower()} en Uruguay: trámites y requisitos",
         f"Lista de trámites para abrir {n.lower()} en Uruguay: inscripción en DGI y BPS, Bomberos, intendencia y permisos del rubro, con enlaces oficiales.",
         s, estatico(rub), f"{BASE}{s}/")
sm = "".join(f"<url><loc>{BASE}{r[0]}/</loc></url>" for r in RUBROS)
open(f"{OUT}/sitemap.xml", "w").write(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{BASE}</loc></url>{sm}</urlset>')
print("habilitar:", len(rows), "trámites en el catálogo ·", len(RUBROS), "rubros ·", {d: len(v["items"]) for d, v in dep.items()})
