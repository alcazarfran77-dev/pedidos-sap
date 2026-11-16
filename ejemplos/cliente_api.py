"""Ejemplo de cliente de la API de SAP Orders para el sistema local de un cliente.

Solo usa la biblioteca estándar de Python 3.8+. Configuración por variables de entorno:
    SAP_ORDERS_URL   dirección base, por ejemplo https://pedidos-sap-xxxx.onrender.com/api/v1
    SAP_ORDERS_KEY   llave de API generada en la pantalla «API» de la aplicación

Uso:
    python cliente_api.py enviar pedido.json             # envía el archivo (JSON o CSV) y guarda la respuesta en respuesta.csv
    python cliente_api.py enviar pedidos.csv --send      # además lo manda a SAP si no tiene errores
    python cliente_api.py estatus --since 2026-11-16     # guarda el estatus de los pedidos en estatus.csv
    python cliente_api.py materiales                     # guarda precios y disponibilidad en materiales.csv
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def llamar(metodo, ruta, params=None, cuerpo=None, tipo=None):
    base = os.environ.get("SAP_ORDERS_URL", "").rstrip("/")
    llave = os.environ.get("SAP_ORDERS_KEY", "")
    if not base or not llave:
        sys.exit("Define SAP_ORDERS_URL y SAP_ORDERS_KEY")
    url = base + ruta + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, data=cuerpo, method=metodo, headers={"Authorization": "Bearer " + llave})
    if tipo:
        req.add_header("Content-Type", tipo)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # el plan gratuito de Render tarda en despertar
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def guardar(nombre, texto):
    with open(nombre, "w", encoding="utf-8", newline="") as f:
        f.write(texto)
    print("Guardado en", nombre)


def main():
    ap = argparse.ArgumentParser(description="Cliente de la API de SAP Orders")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("enviar", help="Envía un archivo de pedidos (JSON o CSV)")
    e.add_argument("archivo")
    e.add_argument("--send", action="store_true", help="Enviar a SAP los pedidos sin errores")
    e.add_argument("--salida", default="respuesta.csv")
    s = sub.add_parser("estatus", help="Descarga el estatus de los pedidos")
    s.add_argument("--since", help="Solo pedidos creados o actualizados desde esta fecha (AAAA-MM-DD)")
    s.add_argument("--salida", default="estatus.csv")
    m = sub.add_parser("materiales", help="Descarga precios y disponibilidad")
    m.add_argument("--salida", default="materiales.csv")
    a = ap.parse_args()

    if a.cmd == "enviar":
        with open(a.archivo, "rb") as f:
            datos = f.read()
        tipo = "text/csv" if a.archivo.lower().endswith(".csv") else "application/json"
        params = {"format": "csv", "lang": "es"}
        if a.send:
            params["send"] = "true"
        codigo, texto = llamar("POST", "/orders", params, datos, tipo)
        if codigo == 201:
            guardar(a.salida, texto)
        elif codigo == 409:
            print("El pedido ya existía; no se duplicó:", json.loads(texto)["error"])
        else:
            sys.exit(f"Error {codigo}: {texto}")
    elif a.cmd == "estatus":
        params = {"format": "csv", "lang": "es"}
        if a.since:
            params["since"] = a.since
        codigo, texto = llamar("GET", "/orders", params)
        guardar(a.salida, texto) if codigo == 200 else sys.exit(f"Error {codigo}: {texto}")
    else:
        codigo, texto = llamar("GET", "/materials", {"format": "csv"})
        guardar(a.salida, texto) if codigo == 200 else sys.exit(f"Error {codigo}: {texto}")


if __name__ == "__main__":
    main()
