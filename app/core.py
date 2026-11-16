"""Motor de pedidos: lectura de archivos JSON/CSV, sugerencia de almacén por distancia,
precio, fecha planificada de entrega, JSON de salida para SAP y aplicación de estatus.

Trabaja sobre un diccionario de estado `st` con las llaves:
clientes, inventario, precios, xref, almacenes, pedidos (listas) y config (dict).
La misma lógica está portada a JavaScript en static/index.html (modo sin servidor).
"""
import csv, io, json, math, re, unicodedata
import datetime as dt
from pathlib import Path

SHARED = json.loads((Path(__file__).parent / "shared.json").read_text("utf-8"))
ESQ, CP, CP_CA, NUM, REQ = SHARED["esquema"], SHARED["cp"], SHARED["cp_ca"], set(SHARED["numericos"]), SHARED["requeridos"]
MENSAJES, ESTATUS_NOMBRES = SHARED["mensajes"], SHARED["estatus_nombres"]
MAESTROS = ["clientes", "inventario", "precios", "xref", "almacenes"]
TIPOS = MAESTROS + ["estatus", "pedidos"]
ABIERTOS = ("BORRADOR", "ENVIADO_SAP")  # pedidos cuyo consumo aún no refleja el inventario de SAP

CONFIG_DEFAULT = {
    "conexion": {"modo": "carpeta", "host": "", "puerto": 22, "usuario": "", "password": "", "ruta_llave": "",
                 "carpeta_base": "intercambio", "aceptar_host_desconocido": True, "archivar": True},
    "rutas": {"clientes": "entrada/clientes", "inventario": "entrada/inventario", "precios": "entrada/precios",
              "xref": "entrada/xref", "almacenes": "entrada/almacenes", "estatus": "entrada/estatus",
              "pedidos": "entrada/pedidos", "salida": "salida/pedidos"},
    "intervalos": {"clientes": 60, "inventario": 15, "precios": 60, "xref": 60, "almacenes": 0, "estatus": 5, "pedidos": 5},
    "logistica": {"dias_preparacion": 1, "omitir_fin_semana": True,
                  "tramos": [[150, 1], [500, 2], [1000, 3], [1800, 4], [99999, 5]]},
    "moneda": "CAD", "prefijo": "PED", "consecutivo": 0, "enviar_automatico": False,
}


# ---------- utilidades ----------
def M(codigo, *params):
    """Mensaje traducible: la interfaz lo muestra en inglés o español según el idioma elegido (ver MSG en index.html)."""
    return "@" + codigo + "".join("\x1f" + str(p) for p in params)


def plano(s):
    s = unicodedata.normalize("NFD", str(s if s is not None else ""))
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip().lower()


def _clave(k):
    return re.sub(r"[^a-z0-9]+", "_", plano(k)).strip("_")


def num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fecha8(v):
    return re.sub(r"\D", "", str(v or ""))[:8]


def ahora():
    return dt.datetime.now().replace(microsecond=0).isoformat()


def r2(x):
    return round(x + 1e-9, 2)


# ---------- lectura de archivos ----------
def leer_texto(nombre, texto):
    """Devuelve una lista de dicts a partir de un archivo JSON o CSV."""
    texto = texto.lstrip("﻿").strip()
    if not texto:
        return []
    if nombre.lower().endswith(".json") or texto[0] in "[{":
        d = json.loads(texto)
        if isinstance(d, dict):
            listas = [v for v in d.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
            con_pos = any(_clave(k) in ("posiciones", "items", "partidas", "lineas", "lines") for k in d)
            d = [d] if con_pos or not listas else listas[0]
        return [x for x in d if isinstance(x, dict)]
    cab = texto.splitlines()[0]
    sep = max(";,\t|", key=cab.count)
    return [dict(r) for r in csv.DictReader(io.StringIO(texto), delimiter=sep)]


def normalizar(tipo, filas):
    """Renombra columnas a su nombre canónico (acepta nombre SAP o alias en español)."""
    mapa = {}
    for canon, alias in ESQ[tipo].items():
        for a in [canon] + alias:
            mapa.setdefault(_clave(a), canon)
    if tipo == "pedidos":  # pedidos anidados -> filas planas
        planas = []
        for f in filas:
            pos = next((v for k, v in f.items() if _clave(k) in ("posiciones", "items", "partidas", "lineas", "lines")), None)
            if isinstance(pos, list):
                cab = {k: v for k, v in f.items() if not isinstance(v, (list, dict))}
                planas += [dict(cab, **p) for p in pos if isinstance(p, dict)]
            else:
                planas.append(f)
        filas = planas
    out = []
    for f in filas:
        r = {c: (None if c in NUM else "") for c in ESQ[tipo]}
        for k, v in f.items():
            c = mapa.get(_clave(k))
            if not c or v is None or (r[c] not in ("", None)):
                continue
            r[c] = num(v) if c in NUM else str(v).strip()
        if all(r.get(q) not in ("", None) for q in REQ[tipo]):
            out.append(r)
    return out


def aplicar_maestro(st, tipo, filas):
    """Actualiza un dato maestro: reemplaza los registros cuyas llaves vienen en el archivo."""
    llave = {"clientes": lambda r: r["KUNNR"], "inventario": lambda r: r["WERKS"],
             "precios": lambda r: (r["MATNR"], r["KUNNR"]), "xref": lambda r: (r["KUNNR"], r["KDMAT"]),
             "almacenes": lambda r: r["WERKS"]}[tipo]
    if tipo == "inventario":
        for r in filas:
            r["LABST"] = r["LABST"] or 0.0
    nuevas = {llave(r) for r in filas}
    st[tipo] = [r for r in st[tipo] if llave(r) not in nuevas] + filas
    return len(filas)


# ---------- geografía ----------
RE_CA = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]\d[A-Za-z])[ -]?(\d[A-Za-z]\d)(?![A-Za-z0-9])")


def geo_cp(cp):
    """Ubicación aproximada de un código postal: canadiense (A1A 1A1) o mexicano (5 dígitos)."""
    t = str(cp or "")
    m = RE_CA.search(t)
    if m:
        fsa = m.group(1).upper()
        e = CP_CA.get(fsa[:2]) or CP_CA.get(fsa[0])
        if e:
            return dict(e, PSTLZ=fsa + " " + m.group(2).upper())
    m = re.search(r"(?<!\d)\d{5}(?!\d)", t)
    if not m:
        return None
    e = CP.get(m.group()[:2])
    return dict(e, PSTLZ=m.group()) if e else None


def geo_texto(texto):
    t, mejor = plano(texto), None
    for e in list(CP_CA.values()) + list(CP.values()):
        m = re.search(r"\b" + re.escape(plano(e["ciudad"])) + r"\b", t)
        if m and (mejor is None or m.start() < mejor[0]):
            mejor = (m.start(), e)
    return dict(mejor[1], PSTLZ="") if mejor else None


def distancia_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def geo_almacen(a):
    if a.get("LAT") is not None and a.get("LON") is not None:
        return {"lat": a["LAT"], "lon": a["LON"]}
    return geo_cp(a.get("PSTLZ"))


def _dir_de_fila(r, origen):
    g = geo_cp(r["PSTLZ"]) or geo_texto(r["ORT01"]) or {}
    return {"texto": ", ".join(x for x in (r["STRAS"], r["ORT01"], r["REGIO"], r["PSTLZ"]) if x),
            "KUNWE": r["KUNWE"] or r["KUNNR"], "PSTLZ": r["PSTLZ"], "ciudad": r["ORT01"] or g.get("ciudad", ""),
            "lat": g.get("lat"), "lon": g.get("lon"), "origen": origen, "aviso": ""}


def resolver_direccion(st, kunnr, texto):
    filas = [r for r in st["clientes"] if r["KUNNR"] == kunnr]
    principal = next((r for r in filas if r["KUNWE"] in ("", kunnr)), filas[0] if filas else None)
    t = (texto or "").strip()
    if not t:
        return _dir_de_fila(principal, "principal") if principal else None
    for r in filas:
        if t.lower() in ((r["KUNWE"] or r["KUNNR"]).lower(),):
            return _dir_de_fila(r, "destinatario")
    g = geo_cp(t) or geo_texto(t)
    if g:
        return {"texto": t, "KUNWE": "", "PSTLZ": g["PSTLZ"], "ciudad": g["ciudad"], "lat": g["lat"], "lon": g["lon"],
                "origen": "texto", "aviso": "" if g["PSTLZ"] else M("dir_sin_cp")}
    d = _dir_de_fila(principal, "principal") if principal else {"KUNWE": "", "PSTLZ": "", "ciudad": "", "lat": None, "lon": None, "origen": "texto"}
    d.update(texto=t, KUNWE="", aviso=M("dir_no_ubicada"))
    return d


# ---------- materiales, precio, inventario ----------
def catalogo(st):
    cat = {}
    for r in st["inventario"]:
        cat.setdefault(r["MATNR"], {"MAKTX": r["MAKTX"], "MEINS": r["MEINS"]})
    for r in st["precios"]:
        cat.setdefault(r["MATNR"], {"MAKTX": "", "MEINS": ""})
    return cat


def resolver_material(st, kunnr, entrada, cat=None):
    cat = cat or catalogo(st)
    e = str(entrada or "").strip()
    if e in cat:
        return e
    for m in cat:
        if m.lstrip("0").lower() == e.lstrip("0").lower() and e:
            return m
    for x in st["xref"]:
        if x["KUNNR"] == kunnr and x["KDMAT"].lower() == e.lower():
            return x["MATNR"]
    pe = plano(e)
    return next((m for m, v in cat.items() if pe and plano(v["MAKTX"]) == pe), None)


def buscar_precio(st, matnr, kunnr, hoy):
    h = hoy.strftime("%Y%m%d")
    vig = [p for p in st["precios"] if p["MATNR"] == matnr and p["KUNNR"] in ("", kunnr)
           and (fecha8(p["DATAB"]) or "0") <= h <= (fecha8(p["DATBI"]) or "99999999")]
    vig.sort(key=lambda p: (p["KUNNR"] == kunnr, fecha8(p["DATAB"])), reverse=True)
    return vig[0] if vig else None


def comprometido(st, matnr, werks, excluir=None):
    return sum(p["cantidad"] for o in st["pedidos"] if o["estatus"] in ABIERTOS and o["id"] != excluir
               for p in o["posiciones"] if p["MATNR"] == matnr and p["WERKS"] == werks)


def candidatos(st, matnr, dest, excluir=None, usado=None):
    usado = usado or {}
    out = []
    for a in st["almacenes"]:
        w = a["WERKS"]
        stock = sum(r["LABST"] or 0 for r in st["inventario"] if r["MATNR"] == matnr and r["WERKS"] == w)
        g = geo_almacen(a)
        d = distancia_km(dest, g) if dest and dest.get("lat") is not None and g else None
        out.append({"WERKS": w, "nombre": a["NAME1"], "distancia_km": None if d is None else round(d),
                    "existencia": stock, "disponible": stock - comprometido(st, matnr, w, excluir) - usado.get((matnr, w), 0)})
    out.sort(key=lambda c: (c["distancia_km"] is None, c["distancia_km"] or 0, -c["disponible"]))
    return out


def fecha_entrega(dist, cfg, hoy):
    lg = cfg["logistica"]
    d = 800 if dist is None else dist
    dias = int(lg["dias_preparacion"]) + next((t[1] for t in lg["tramos"] if d <= t[0]), lg["tramos"][-1][1])
    f = hoy
    while dias > 0:
        f += dt.timedelta(days=1)
        if not (lg["omitir_fin_semana"] and f.weekday() >= 5):
            dias -= 1
    return f.isoformat()


# ---------- pedidos ----------
def agrupar_entradas(filas):
    """Filas planas normalizadas -> entradas de pedido agrupadas por cliente + pedido del cliente + dirección."""
    grupos = {}
    for f in filas:
        k = (f["KUNNR"], f["BSTKD"], f["DIRECCION"])
        g = grupos.setdefault(k, {"KUNNR": f["KUNNR"], "BSTKD": f["BSTKD"], "DIRECCION": f["DIRECCION"], "posiciones": []})
        g["posiciones"].append({"MATERIAL": f["MATERIAL"], "CANTIDAD": f["CANTIDAD"], "WERKS": f.get("WERKS", "")})
    return list(grupos.values())


def construir_pedido(st, ent, pid="", hoy=None, previo=None):
    """Enriquece una entrada {KUNNR, BSTKD, DIRECCION, posiciones:[{MATERIAL, CANTIDAD, WERKS?}]}."""
    hoy = hoy or dt.date.today()
    cfg = st["config"]
    errores, avisos = [], []
    k_in = str(ent.get("KUNNR", "")).strip()
    fila = next((r for r in st["clientes"] if r["KUNNR"] == k_in), None) or \
        next((r for r in st["clientes"] if k_in and plano(r["NAME1"]) == plano(k_in)), None)
    kunnr = fila["KUNNR"] if fila else k_in
    nombre = next((r["NAME1"] for r in st["clientes"] if r["KUNNR"] == kunnr and r["KUNWE"] in ("", kunnr)), fila["NAME1"] if fila else "")
    if not fila:
        errores.append(M("cli_no_existe", k_in))
    bstkd = str(ent.get("BSTKD", "")).strip()
    if not bstkd:
        avisos.append(M("sin_ref"))
    elif any(o["KUNNR"] == kunnr and o["BSTKD"] == bstkd and o["id"] != pid for o in st["pedidos"]):
        avisos.append(M("ref_dup", bstkd))
    direc = resolver_direccion(st, kunnr, ent.get("DIRECCION", "")) if fila else None
    if fila and direc and direc["aviso"]:
        avisos.append(direc["aviso"])
    if not st["almacenes"]:
        errores.append(M("sin_almacenes"))
    cat, usado, posiciones, total = catalogo(st), {}, [], 0.0
    for i, p in enumerate(ent.get("posiciones", []), 1):
        pe, pa = [], []
        cant = num(p.get("CANTIDAD"))
        matnr = resolver_material(st, kunnr, p.get("MATERIAL"), cat)
        pos = {"POSNR": i * 10, "material_entrada": str(p.get("MATERIAL", "")).strip(), "MATNR": matnr or "",
               "MAKTX": cat[matnr]["MAKTX"] if matnr else "", "MEINS": cat[matnr]["MEINS"] if matnr else "",
               "cantidad": cant or 0, "precio": None, "importe": None, "WERKS": "", "almacen": "",
               "distancia_km": None, "disponible": None, "EDATU": "", "candidatos": [], "forzado": False}
        if not matnr:
            pe.append(M("mat_no", pos["material_entrada"]))
        if not cant or cant <= 0:
            pe.append(M("cant_inv"))
        if matnr and cant and cant > 0:
            pr = buscar_precio(st, matnr, kunnr, hoy)
            if pr:
                pos["precio"], pos["importe"] = pr["KBETR"], r2(pr["KBETR"] * cant)
                total += pos["importe"]
            else:
                pe.append(M("sin_precio"))
            cs = candidatos(st, matnr, direc, pid or None, usado)
            pos["candidatos"] = cs
            forz = str(p.get("WERKS") or "").strip()
            el = next((c for c in cs if c["WERKS"] == forz), None)
            pos["forzado"] = bool(el)
            if not el:
                el = next((c for c in cs if c["disponible"] >= cant), None)
            if not el and cs:
                el = max(cs, key=lambda c: c["disponible"])  # ninguno cubre: el de mayor disponible
                if el["disponible"] <= 0:
                    el = cs[0]
            if el:
                pos.update(WERKS=el["WERKS"], almacen=el["nombre"], distancia_km=el["distancia_km"], disponible=el["disponible"],
                           EDATU=fecha_entrega(el["distancia_km"], cfg, hoy))
                usado[(matnr, el["WERKS"])] = usado.get((matnr, el["WERKS"]), 0) + cant
                if el["disponible"] < cant:
                    pa.append(M("stock_insuf", el["WERKS"], format(el["disponible"], "g"), format(cant, "g")))
                elif cs and el is not cs[0] and not pos["forzado"]:
                    pa.append(M("alm_lejos", cs[0]["WERKS"], el["WERKS"]))
        pos["errores"], pos["avisos"] = pe, pa
        posiciones.append(pos)
    if not posiciones:
        errores.append(M("sin_pos"))
    t = ahora()
    ped = {"id": pid, "BSTKD": bstkd, "KUNNR": kunnr, "NAME1": nombre, "direccion": direc, "fecha": t, "origen": (ent.get("origen") or M("o_captura0")),
           "estatus": "BORRADOR", "VBELN": "", "moneda": cfg["moneda"], "total": r2(total), "errores": errores, "avisos": avisos,
           "posiciones": posiciones, "historial": [{"fecha": t, "estatus": "BORRADOR", "texto": M("h_registrado"), "fuente": "sistema"}],
           "archivo_sap": "",
           "entrada": {"KUNNR": k_in, "BSTKD": bstkd, "DIRECCION": ent.get("DIRECCION", ""), "origen": (ent.get("origen") or M("o_captura0")),
                       "posiciones": [{"MATERIAL": p.get("MATERIAL"), "CANTIDAD": p.get("CANTIDAD"), "WERKS": p.get("WERKS", "")} for p in ent.get("posiciones", [])]}}
    if previo:
        ped["fecha"] = previo["fecha"]
        ped["historial"] = previo["historial"] + [{"fecha": t, "estatus": "BORRADOR", "texto": M("h_recalculado"), "fuente": "sistema"}]
    return ped


def tiene_errores(p):
    return bool(p["errores"] or any(x["errores"] for x in p["posiciones"]))


def siguiente_id(st):
    st["config"]["consecutivo"] = int(st["config"].get("consecutivo", 0)) + 1
    return f"{st['config']['prefijo']}-{st['config']['consecutivo']:06d}"


def json_sap(p):
    """Documento que se deposita en el SFTP para que SAP cree el pedido de venta."""
    d = p["direccion"] or {}
    return {"ID_PEDIDO": p["id"], "BSTKD": p["BSTKD"], "KUNNR": p["KUNNR"], "KUNWE": d.get("KUNWE") or p["KUNNR"],
            "DIRECCION_ENTREGA": {"TEXTO": d.get("texto", ""), "PSTLZ": d.get("PSTLZ", ""), "ORT01": d.get("ciudad", "")},
            "AUDAT": p["fecha"][:10], "WAERK": p["moneda"], "NETWR": p["total"],
            "POSICIONES": [{"POSNR": x["POSNR"], "MATNR": x["MATNR"], "ARKTX": x["MAKTX"], "KWMENG": x["cantidad"], "VRKME": x["MEINS"],
                            "NETPR": x["precio"], "NETWR": x["importe"], "WERKS": x["WERKS"], "EDATU": x["EDATU"]} for x in p["posiciones"]]}


def nombre_archivo_sap(p):
    return f"PEDIDO_{p['id']}_{dt.datetime.now():%Y%m%d%H%M%S}.json"


def marcar_enviado(p, archivo, texto):
    p["estatus"], p["archivo_sap"] = "ENVIADO_SAP", archivo
    p["historial"].append({"fecha": ahora(), "estatus": "ENVIADO_SAP", "texto": texto, "fuente": "sistema"})


def aplicar_estatus(st, filas, fuente="SAP"):
    """Aplica estatus recibidos de SAP. Busca por ID_PEDIDO; si no viene, por BSTKD (+KUNNR)."""
    n, sin = 0, []
    for f in filas:
        o = next((x for x in st["pedidos"] if f["ID_PEDIDO"] and x["id"] == f["ID_PEDIDO"]), None) or \
            next((x for x in st["pedidos"] if not f["ID_PEDIDO"] and f["BSTKD"] and x["BSTKD"] == f["BSTKD"]
                  and (not f["KUNNR"] or x["KUNNR"] == f["KUNNR"])), None)
        if not o:
            sin.append(f["ID_PEDIDO"] or f["BSTKD"] or "?")
            continue
        est = re.sub(r"\s+", "_", f["STATUS"].strip().upper())
        h = {"fecha": f["FECHA"] or ahora(), "estatus": est, "texto": f["TEXTO"], "fuente": fuente}
        if any(x["fecha"] == h["fecha"] and x["estatus"] == est and x["texto"] == h["texto"] for x in o["historial"]):
            continue
        o["historial"].append(h)
        o["historial"].sort(key=lambda x: x["fecha"])
        o["estatus"] = [x for x in o["historial"] if x["fuente"] != "sistema"][-1]["estatus"]
        if f["VBELN"]:
            o["VBELN"] = f["VBELN"]
        n += 1
    return n, sin


# ---------- salida para la API (sistemas de los clientes) ----------
def texto(m, lang="en"):
    """Convierte un mensaje "@codigo␟params" al idioma pedido (en / es). Un texto normal se devuelve igual."""
    m = str(m if m is not None else "")
    if not m.startswith("@"):
        return m
    partes = m[1:].split("\x1f")
    d = MENSAJES.get(partes.pop(0))
    if not d:
        return m
    tpl = d[0 if lang == "es" else 1]
    n = len(re.findall(r"\{\d\}", tpl))
    if n and len(partes) > n:
        partes = partes[:n - 1] + ["\x1f".join(partes[n - 1:])]
    return re.sub(r"\{(\d)\}", lambda g: texto(partes[int(g.group(1))] if int(g.group(1)) < len(partes) else "", lang), tpl)


def nombre_estatus(e, lang="en"):
    n = ESTATUS_NOMBRES.get(e)
    return n[0 if lang == "es" else 1] if n else e.replace("_", " ").capitalize()


def pedido_api(p, lang="en"):
    d = p.get("direccion") or {}
    tx = lambda xs: [texto(x, lang) for x in xs]
    return {
        "order_id": p["id"] or None, "customer": p["KUNNR"], "customer_name": p["NAME1"], "customer_po": p["BSTKD"],
        "status": p["estatus"], "status_text": nombre_estatus(p["estatus"], lang), "sap_order": p["VBELN"] or None,
        "created_at": p["fecha"], "source": texto(p["origen"], lang),
        "ship_to": {"id": d.get("KUNWE") or None, "address": d.get("texto", ""), "city": d.get("ciudad", ""), "postal_code": d.get("PSTLZ", "")},
        "currency": p["moneda"], "total": p["total"], "has_errors": tiene_errores(p),
        "errors": tx(p["errores"]), "warnings": tx(p["avisos"]),
        "items": [{"item": x["POSNR"], "material": x["MATNR"] or None, "material_received": x["material_entrada"], "description": x["MAKTX"],
                   "quantity": x["cantidad"], "uom": x["MEINS"], "price": x["precio"], "amount": x["importe"],
                   "warehouse": x["WERKS"] or None, "warehouse_name": x["almacen"], "planned_delivery": x["EDATU"] or None,
                   "errors": tx(x["errores"]), "warnings": tx(x["avisos"])} for x in p["posiciones"]],
        "history": [{"date": h["fecha"], "status": h["estatus"], "status_text": nombre_estatus(h["estatus"], lang), "text": texto(h["texto"], lang)}
                    for h in p["historial"]],
    }


COLUMNAS_CSV = ["order_id", "customer", "customer_po", "status", "status_text", "sap_order", "created_at", "ship_to_id", "ship_to_postal_code",
                "item", "material", "material_received", "description", "quantity", "uom", "price", "amount", "currency",
                "warehouse", "warehouse_name", "planned_delivery", "order_total", "errors", "warnings"]


def csv_pedidos(pedidos_api):
    """Una fila por posición: lo que el sistema del cliente necesita para registrar la respuesta."""
    f = io.StringIO()
    w = csv.DictWriter(f, fieldnames=COLUMNAS_CSV, lineterminator="\r\n")
    w.writeheader()
    for o in pedidos_api:
        base = {"order_id": o["order_id"] or "", "customer": o["customer"], "customer_po": o["customer_po"], "status": o["status"],
                "status_text": o["status_text"], "sap_order": o["sap_order"] or "", "created_at": o["created_at"],
                "ship_to_id": o["ship_to"]["id"] or "", "ship_to_postal_code": o["ship_to"]["postal_code"], "currency": o["currency"],
                "order_total": o["total"]}
        for x in o["items"] or [{}]:
            w.writerow(dict(base, item=x.get("item", ""), material=x.get("material") or "", material_received=x.get("material_received", ""),
                            description=x.get("description", ""), quantity=x.get("quantity", ""), uom=x.get("uom", ""),
                            price="" if x.get("price") is None else x["price"], amount="" if x.get("amount") is None else x["amount"],
                            warehouse=x.get("warehouse") or "", warehouse_name=x.get("warehouse_name", ""), planned_delivery=x.get("planned_delivery") or "",
                            errors="; ".join(o["errors"] + x.get("errors", [])), warnings="; ".join(o["warnings"] + x.get("warnings", []))))
    return f.getvalue()


def materiales_api(st, kunnr, hoy=None):
    """Catálogo con precio vigente para el cliente y disponible por almacén (existencia menos pedidos abiertos)."""
    hoy = hoy or dt.date.today()
    out = []
    for m, v in sorted(catalogo(st).items()):
        pr = buscar_precio(st, m, kunnr, hoy)
        disp = {}
        for a in st["almacenes"]:
            ex = sum(r["LABST"] or 0 for r in st["inventario"] if r["MATNR"] == m and r["WERKS"] == a["WERKS"])
            disp[a["WERKS"]] = ex - comprometido(st, m, a["WERKS"])
        out.append({"material": m, "description": v["MAKTX"], "uom": v["MEINS"], "price": pr["KBETR"] if pr else None,
                    "currency": (pr or {}).get("KONWA") or st["config"]["moneda"], "available": sum(disp.values()), "available_by_warehouse": disp})
    return out


def csv_materiales(mats):
    alms = sorted({w for m in mats for w in m["available_by_warehouse"]})
    f = io.StringIO()
    w = csv.writer(f, lineterminator="\r\n")
    w.writerow(["material", "description", "uom", "price", "currency", "available"] + [f"available_{a}" for a in alms])
    for m in mats:
        w.writerow([m["material"], m["description"], m["uom"], "" if m["price"] is None else m["price"], m["currency"], m["available"]]
                   + [m["available_by_warehouse"].get(a, "") for a in alms])
    return f.getvalue()
