"""Prueba de flujo completo contra un servidor SFTP real (paramiko, en proceso). Ejecutar: python -m tests.test_flujo"""
import json, os, shutil, socket, sys, tempfile, threading, time, datetime as dt
from pathlib import Path
import paramiko

TMP = Path(tempfile.mkdtemp())
os.environ["PEDIDOS_DB"] = str(TMP / "t.db")
RAIZ = TMP / "sftp"; RAIZ.mkdir()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import core, servicio as sv  # noqa: E402


# ---- servidor SFTP mínimo para la prueba ----
class Srv(paramiko.ServerInterface):
    def check_auth_password(self, u, p): return paramiko.AUTH_SUCCESSFUL if (u, p) == ("sap", "secreto") else paramiko.AUTH_FAILED
    def check_channel_request(self, k, c): return paramiko.OPEN_SUCCEEDED
    def get_allowed_auths(self, u): return "password"

class H(paramiko.SFTPHandle):
    def stat(self): return paramiko.SFTPAttributes.from_stat(os.fstat(self.readfile.fileno()))

class FS(paramiko.SFTPServerInterface):
    def _r(self, p): return str(RAIZ / self.canonicalize(p).lstrip("/"))
    def list_folder(self, p):
        out = []
        for n in os.listdir(self._r(p)):
            a = paramiko.SFTPAttributes.from_stat(os.stat(os.path.join(self._r(p), n))); a.filename = n; out.append(a)
        return out
    def stat(self, p):
        try: return paramiko.SFTPAttributes.from_stat(os.stat(self._r(p)))
        except OSError as e: return paramiko.SFTPServer.convert_errno(e.errno)
    lstat = stat
    def open(self, p, flags, attr):
        try:
            fd = os.open(self._r(p), flags, 0o644)
        except OSError as e: return paramiko.SFTPServer.convert_errno(e.errno)
        f = os.fdopen(fd, "r+b" if flags & os.O_RDWR else ("wb" if flags & os.O_WRONLY else "rb"))
        h = H(flags); h.readfile = f; h.writefile = f; return h
    def mkdir(self, p, attr): os.mkdir(self._r(p)); return paramiko.SFTP_OK
    def rename(self, a, b): os.replace(self._r(a), self._r(b)); return paramiko.SFTP_OK
    def remove(self, p):
        try: os.remove(self._r(p)); return paramiko.SFTP_OK
        except OSError as e: return paramiko.SFTPServer.convert_errno(e.errno)

def servidor(sock, llave):
    while True:
        c, _ = sock.accept()
        t = paramiko.Transport(c); t.add_server_key(llave)
        t.set_subsystem_handler("sftp", paramiko.SFTPServer, FS)
        t.start_server(server=Srv())

sock = socket.socket(); sock.bind(("127.0.0.1", 0)); sock.listen(5)
threading.Thread(target=servidor, args=(sock, paramiko.RSAKey.generate(2048)), daemon=True).start()
PUERTO = sock.getsockname()[1]

def poner(ruta, nombre, texto):
    d = RAIZ / ruta; d.mkdir(parents=True, exist_ok=True); (d / nombre).write_text(texto, "utf-8")

def ok(cond, msg):
    print(("  OK  " if cond else " FALLA ") + msg)
    if not cond: sys.exit(1)

EJ = Path(__file__).resolve().parent.parent / "ejemplos"
sv.guardar_config({"conexion": {"modo": "sftp", "host": "127.0.0.1", "puerto": PUERTO, "usuario": "sap", "password": "secreto"}})
ok("m_conexion" in sv.probar_conexion(), "conexión SFTP con usuario/contraseña")
ok(sv.estado()["config"]["conexion"]["password"] == "********", "la contraseña no se devuelve a la interfaz")

# 1) maestros llegan de SAP por SFTP (JSON y CSV)
for ruta, f in [("entrada/clientes", "clientes_sap.json"), ("entrada/inventario", "inventario_sap.csv"), ("entrada/precios", "precios_sap.json"),
                ("entrada/xref", "xref_material_cliente.csv"), ("entrada/almacenes", "almacenes.json")]:
    poner(ruta, f, (EJ / f).read_text("utf-8"))
for t in core.MAESTROS:
    ok(sv.sincronizar(t) == 1, f"sincroniza {t}")
st = sv.estado()
ok(len(st["clientes"]) == 10 and len(st["inventario"]) == 32 and len(st["almacenes"]) == 4, "maestros cargados en SQLite")
ok((RAIZ / "entrada/clientes/procesados/clientes_sap.json").exists(), "archivo movido a procesados")
ok(sv.sincronizar("clientes") == 0, "no reprocesa archivos ya leídos")

# 2) captura: Prairie Industrial Supply -> planta Edmonton (T5S 0A2): el más cercano es 3000 (Calgary)
hoy = dt.date.today()
p = sv.previsualizar({"KUNNR": "100040", "BSTKD": "OC-1", "DIRECCION": "100041",
                      "posiciones": [{"MATERIAL": "PIS-BOLT-050", "CANTIDAD": 200}, {"MATERIAL": "10000205", "CANTIDAD": 100}]})
a, b = p["posiciones"]
ok(a["MATNR"] == "10000101", "material del cliente PIS-BOLT-050 -> código SAP 10000101")
ok(a["precio"] == 171.0 and a["importe"] == 34200.0, "precio especial del cliente y su importe")
ok(a["WERKS"] == "3000" and 250 < a["distancia_km"] < 320, f"almacén más cercano a Edmonton: 3000 Calgary ({a['distancia_km']} km)")
ok(b["WERKS"] == "1000" and "alm_lejos" in b["avisos"][0], "ancla: 3000 tiene 35 y 4000 nada -> siguiente más cercano con existencia (1000) y aviso")
ok(p["total"] == r if (r := round(34200 + 264.75 * 100, 2)) else False, "importe total")
ok(dt.date.fromisoformat(a["EDATU"]) > hoy and dt.date.fromisoformat(a["EDATU"]).weekday() < 5, "fecha planificada en día hábil")
q = sv.previsualizar({"KUNNR": "100030", "BSTKD": "X", "DIRECCION": "1960 Windsor Rd, Kelowna, BC v1y4r5", "posiciones": [{"MATERIAL": "10000550", "CANTIDAD": 10}]})
ok(q["posiciones"][0]["WERKS"] == "4000" and q["direccion"]["PSTLZ"] == "V1Y 4R5", "dirección libre con código postal canadiense -> Vancouver DC")
ok(core.geo_cp("Av. Juárez 10, Puebla CP 72008")["ciudad"] == "Puebla" and core.geo_texto("Halifax, Nova Scotia")["estado"] == "NS", "siguen funcionando los códigos postales de México y la ubicación por ciudad")
e = sv.previsualizar({"KUNNR": "999", "BSTKD": "X", "DIRECCION": "", "posiciones": [{"MATERIAL": "NOPE", "CANTIDAD": 1}]})
ok(core.tiene_errores(e), "cliente y material inexistentes marcan error")

creado = sv.crear([p["entrada"]])[0]
ok(creado["id"] == "PED-000001" and creado["estatus"] == "BORRADOR", "pedido capturado como borrador")
# el inventario comprometido por el borrador reduce el disponible del siguiente
p2 = sv.previsualizar({"KUNNR": "100040", "BSTKD": "OC-2", "DIRECCION": "100041", "posiciones": [{"MATERIAL": "10000101", "CANTIDAD": 10}]})
ok(p2["posiciones"][0]["disponible"] == 450, "disponible descuenta pedidos abiertos (650-200)")

# 3) envío a SAP: JSON depositado en el SFTP
env = sv.enviar("PED-000001")
sal = list((RAIZ / "salida/pedidos").glob("PEDIDO_PED-000001_*.json"))
ok(len(sal) == 1 and env["estatus"] == "ENVIADO_SAP", "JSON depositado en salida/pedidos")
doc = json.loads(sal[0].read_text("utf-8"))
ok(doc["KUNNR"] == "100040" and doc["KUNWE"] == "100041" and doc["POSICIONES"][0]["WERKS"] == "3000" and doc["NETWR"] == p["total"], "contenido del JSON para SAP")
ok(not list((RAIZ / "salida/pedidos").glob("*.tmp")), "sin archivos temporales a medias")
try: sv.enviar("PED-000001"); ok(False, "reenvío")
except ValueError: ok(True, "no permite enviar dos veces")

# 4) pedidos recibidos por archivo (JSON anidado y CSV plano) vía SFTP
poner("entrada/pedidos", "pedido_entrada.json", (EJ / "pedido_entrada.json").read_text("utf-8"))
poner("entrada/pedidos", "pedidos_entrada.csv", (EJ / "pedidos_entrada.csv").read_text("utf-8"))
ok(sv.sincronizar("pedidos") == 2, "lee 2 archivos de pedidos")
st = sv.estado()
ok(len(st["pedidos"]) == 4, "3 pedidos nuevos (1 del JSON + 2 del CSV)")
mz = next(x for x in st["pedidos"] if x["BSTKD"] == "MTF-11300")
ok(mz["posiciones"][0]["WERKS"] == "2000" and mz["direccion"]["PSTLZ"] == "B2Y 3Z1", "Dartmouth, NS (B2Y 3Z1) -> Montréal DC")
ln = next(x for x in st["pedidos"] if x["BSTKD"] == "QL-PO-5521")
ok(len(ln["posiciones"]) == 2 and ln["posiciones"][0]["MATNR"] == "10000310", "CSV agrupado por pedido del cliente")

# 5) estatus desde SAP
sv.enviar(next(x["id"] for x in st["pedidos"] if x["BSTKD"] == "PO-45001999"))
poner("entrada/estatus", "estatus_1.json", json.dumps([
    {"ID_PEDIDO": "PED-000001", "VBELN": "0080012345", "STATUS": "CREADO", "FECHA": "2099-01-01T09:00:00", "TEXTO": "Pedido de venta creado"},
    {"ID_PEDIDO": "PED-000001", "STATUS": "EMBARCADO", "FECHA": "2099-01-02T16:00:00", "TEXTO": "Guía 778"},
    {"BSTKD": "PO-45001999", "KUNNR": "100040", "VBELN": "0080012350", "STATUS": "Rechazado", "FECHA": "2099-01-01T10:00:00", "TEXTO": "Bloqueo de crédito"},
    {"ID_PEDIDO": "PED-999999", "STATUS": "CREADO"}]))
ok(sv.sincronizar("estatus") == 1, "lee archivo de estatus")
st = sv.estado()
p1 = next(x for x in st["pedidos"] if x["id"] == "PED-000001")
ok(p1["estatus"] == "EMBARCADO" and p1["VBELN"] == "0080012345" and len(p1["historial"]) == 4, "PED-000001 -> EMBARCADO con pedido SAP e historial")
ok(next(x for x in st["pedidos"] if x["BSTKD"] == "PO-45001999")["estatus"] == "RECHAZADO", "estatus localizado por pedido del cliente")
ok("PED-999999" in st["bitacora"][0]["mensaje"], "estatus sin pedido queda en bitácora")
p3 = sv.previsualizar({"KUNNR": "100040", "BSTKD": "OC-3", "DIRECCION": "100041", "posiciones": [{"MATERIAL": "10000101", "CANTIDAD": 10}]})
ok(p3["posiciones"][0]["disponible"] == 650, "pedido ya creado en SAP deja de comprometer inventario local")

# 6) API HTTP con usuarios individuales
from fastapi.testclient import TestClient
from app.main import app
X = {"X-App": "pedidos-sap"}
def cliente_http(): return TestClient(app, headers=X)
def entrar(c, u, p): return c.post("/api/login", json={"usuario": u, "password": p})

with cliente_http() as c:
    ok(c.get("/api/ping").json()["ok"] and c.get("/").status_code == 200, "API responde y sirve la interfaz")
    ok(c.get("/api/estado").status_code == 401 and c.get("/api/sesion").json()["instalar"] is True, "sin sesión -> 401; primer arranque pide crear administrador")
    ok(c.post("/api/instalar", json={"usuario": "fran", "nombre": "Fran", "password": "corta"}).status_code == 400, "rechaza contraseña corta")
    ok(c.post("/api/instalar", json={"usuario": "fran", "nombre": "Fran", "password": "clave-larga-1"}).status_code == 200, "crea el primer administrador")
    ok(c.post("/api/instalar", json={"usuario": "otro", "password": "clave-larga-2"}).status_code == 403, "no se puede instalar dos veces")
    ok(entrar(c, "fran", "mala").status_code == 401 and entrar(c, "fran", "clave-larga-1").json()["rol"] == "admin", "inicio de sesión del administrador")
    ok(TestClient(app).post("/api/logout").status_code == 403, "operación sin encabezado de la interfaz -> 403")
    r = c.post("/api/pedidos", json={"entradas": [{"KUNNR": "100010", "BSTKD": "API-1", "DIRECCION": "", "posiciones": [{"MATERIAL": "10000310", "CANTIDAD": 5}]}], "enviar": True})
    ok(r.status_code == 200 and r.json()[0]["estatus"] == "ENVIADO_SAP" and r.json()[0]["posiciones"][0]["WERKS"] == "1000", "captura + envío por API (Monterrey -> 1000)")
    ok("o_captura" in r.json()[0]["origen"] and "fran" in r.json()[0]["origen"], "el pedido registra quién lo capturó")
    ok(c.post("/api/pedidos/NOEXISTE/enviar").status_code == 404, "pedido inexistente -> 404")
    ok(c.post("/api/importar", json={"tipo": "inventario", "nombre": "x.csv", "texto": "foo;bar\n1;2"}).status_code == 400, "archivo inválido -> 400 con mensaje")
    alta = lambda **d: c.put("/api/usuarios", json={"nuevo": True, **d})
    ok(alta(usuario="valle", nombre="Compras Valle", rol="cliente", KUNNR="100040", password="valle-12345").status_code == 200, "alta de usuario cliente 100040")
    ok(alta(usuario="norte", nombre="Compras Norte", rol="cliente", KUNNR="100010", password="norte-12345").status_code == 200, "alta de usuario cliente 100010")
    ok(alta(usuario="ana", nombre="Ana Ventas", rol="ventas", password="ventas-12345").status_code == 200, "alta de usuario de ventas")
    ok(alta(usuario="x1", rol="cliente", KUNNR="NOPE", password="12345678").status_code == 400, "cliente inexistente -> 400")
    ok(alta(usuario="valle", rol="ventas", password="12345678").status_code == 400, "usuario duplicado -> 400")
    ok(c.delete("/api/usuarios/fran").status_code == 400, "el administrador no puede eliminarse a sí mismo")
    todos = c.get("/api/estado").json()
    ped_norte = next(p["id"] for p in todos["pedidos"] if p["KUNNR"] == "100010")
    disp_admin = sum(r["LABST"] for r in todos["inventario"] if r["MATNR"] == "10000310" and r["WERKS"] == "1000")

# 7) un cliente solo ve y toca lo suyo
with cliente_http() as v:
    entrar(v, "valle", "valle-12345")
    e = v.get("/api/estado").json()
    ok(e["pedidos"] and all(p["KUNNR"] == "100040" for p in e["pedidos"]), f"valle solo ve sus pedidos ({len(e['pedidos'])} de {len(todos['pedidos'])})")
    ok({r["KUNNR"] for r in e["clientes"]} == {"100040"} and all(r["KUNNR"] in ("", "100040") for r in e["precios"]), "solo sus direcciones y sus precios")
    ok("conexion" not in e["config"] and e["bitacora"] == [], "sin configuración del SFTP ni bitácora")
    for metodo, ruta in [("post", f"/api/pedidos/{ped_norte}/enviar"), ("post", f"/api/pedidos/{ped_norte}/recalcular"), ("delete", f"/api/pedidos/{ped_norte}"), ("get", f"/api/pedidos/{ped_norte}/json")]:
        ok(getattr(v, metodo)(ruta).status_code == 404, f"pedido ajeno: {metodo.upper()} {ruta.split('/')[-1]} -> 404")
    ok(v.post("/api/previsualizar", json={"id": ped_norte, "KUNNR": "100010", "posiciones": []}).status_code == 404, "no puede previsualizar sobre un pedido ajeno")
    r = v.post("/api/pedidos", json={"entradas": [{"KUNNR": "100010", "BSTKD": "INTENTO", "DIRECCION": "", "posiciones": [{"MATERIAL": "10000310", "CANTIDAD": 3, "WERKS": "4000"}]}]}).json()[0]
    ok(r["KUNNR"] == "100040" and r["posiciones"][0]["WERKS"] != "4000", "captura a nombre de otro cliente -> queda en el suyo; no elige almacén")
    ok(r["posiciones"][0]["precio"] == 18.9, "no recibe el precio especial de otro cliente")
    m = v.post("/api/importar", json={"tipo": "pedidos", "nombre": "p.csv", "texto": "cliente,pedido_cliente,material,cantidad\n100010,ARCH-1,10000550,10"})
    ok(m.status_code == 200 and all(p["KUNNR"] == "100040" for p in v.get("/api/estado").json()["pedidos"]), "archivo con otro cliente -> pedidos a su nombre")
    for metodo, ruta, cuerpo in [("post", "/api/importar", {"tipo": "precios", "nombre": "x.json", "texto": "[]"}), ("put", "/api/config", {}), ("post", "/api/sync/estatus", None),
                                 ("post", "/api/demo", None), ("get", "/api/usuarios", None), ("put", "/api/usuarios", {"usuario": "valle", "rol": "admin"})]:
        ok((getattr(v, metodo)(ruta, json=cuerpo) if cuerpo is not None else getattr(v, metodo)(ruta)).status_code == 403, f"cliente: {metodo.upper()} {ruta} -> 403")
with cliente_http() as n:
    entrar(n, "norte", "norte-12345")
    e = n.get("/api/estado").json()
    ok(all(p["KUNNR"] == "100010" for p in e["pedidos"]) and not any(p["BSTKD"] in ("INTENTO", "ARCH-1") for p in e["pedidos"]), "norte no ve los pedidos de valle")
    disp = sum(r["LABST"] for r in e["inventario"] if r["MATNR"] == "10000310" and r["WERKS"] == "3000")
    ok(disp == 3100 - 3, "su inventario ya descuenta lo comprometido por otros clientes, sin mostrar esos pedidos")
with cliente_http() as a:
    entrar(a, "ana", "ventas-12345")
    ok(len(a.get("/api/estado").json()["pedidos"]) > len(e["pedidos"]) and a.get("/api/usuarios").status_code == 403 and a.put("/api/config", json={}).status_code == 403, "ventas ve todos los pedidos pero no usuarios ni configuración")
with cliente_http() as c, cliente_http() as v:
    entrar(c, "fran", "clave-larga-1"); entrar(v, "valle", "valle-12345")
    c.put("/api/usuarios", json={"usuario": "valle", "nombre": "Compras Valle", "rol": "cliente", "KUNNR": "100040", "activo": False})
    ok(v.get("/api/estado").status_code == 401 and entrar(v, "valle", "valle-12345").status_code == 401, "usuario desactivado pierde la sesión y no puede entrar")
    for _ in range(5): entrar(v, "norte", "mala")
    ok("e_bloqueo" in entrar(v, "norte", "norte-12345").json()["detail"], "bloqueo temporal tras 5 intentos fallidos")
    c.post("/api/logout"); ok(c.get("/api/estado").status_code == 401, "cerrar sesión")

# 8) administrador por variables de entorno (Render)
os.environ.update(APP_USER="jefe", APP_PASSWORD="clave-de-render", RENDER="true")
with cliente_http() as c:
    ok(entrar(c, "jefe", "clave-de-render").json()["rol"] == "admin" and c.get("/api/usuarios").json()[0]["fijo"], "administrador de APP_USER / APP_PASSWORD")
del os.environ["APP_USER"], os.environ["APP_PASSWORD"]
with cliente_http() as c:
    ok(c.get("/").status_code == 503 and c.get("/healthz").status_code == 200, "en Render sin APP_USER/APP_PASSWORD la aplicación no abre")
del os.environ["RENDER"]
print("\nTODAS LAS PRUEBAS PASARON")
shutil.rmtree(TMP, ignore_errors=True)
