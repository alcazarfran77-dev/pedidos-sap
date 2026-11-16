"""API y servidor web. Ejecutar:  uvicorn app.main:app --host 0.0.0.0 --port 8000

Acceso: cada persona entra con su usuario. Perfiles: admin (todo), ventas (todos los pedidos, sin configuración)
y cliente (solo los pedidos de su cliente SAP). El filtro se aplica aquí, en el servidor, no en la interfaz.
"""
import json, os, threading
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from . import api_v1, core, servicio as sv

ESTATICO = Path(__file__).resolve().parent.parent / "static"
GALLETA = "sesion"


@asynccontextmanager
async def vida(app):
    detener = threading.Event()
    sv.cargar_demo_si_vacio()
    if sv.sftp_habilitado():
        threading.Thread(target=sv.ciclo_programado, args=(detener,), daemon=True).start()
    yield
    detener.set()


app = FastAPI(title="Pedidos SAP", lifespan=vida, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def guardia(request, call_next):
    if request.url.path != "/healthz":
        # En Render la aplicación no abre hasta que exista el administrador en variables de entorno.
        if os.environ.get("RENDER") and not sv.admin_entorno():
            return PlainTextResponse("Set APP_USER and APP_PASSWORD in the service environment variables.", 503)
        # Las operaciones que cambian datos deben venir de la propia interfaz (evita envíos desde otros sitios).
        # La API v1 queda fuera de esta regla: exige llave de API, que el navegador nunca envía por su cuenta.
        if (request.method not in ("GET", "HEAD") and request.headers.get("x-app") != "pedidos-sap"
                and not request.url.path.startswith("/api/v1/")):
            return PlainTextResponse("Request not allowed", 403)
    return await call_next(request)


def usuario(request: Request):
    u = sv.sesion(request.cookies.get(GALLETA))
    if not u:
        raise HTTPException(401, core.M("e_sesion"))
    return u


def interno(u=Depends(usuario)):
    if u["rol"] == "cliente":
        raise HTTPException(403, core.M("e_permiso"))
    return u


def admin(u=Depends(usuario)):
    if u["rol"] != "admin":
        raise HTTPException(403, core.M("e_solo_admin"))
    return u


def _seguro(fn, *a, **k):
    try:
        return fn(*a, **k)
    except KeyError as e:
        raise HTTPException(404, core.M("e_no_pedido", e.args[0] if e.args else ""))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {e}")


# ---------- abierto ----------
@app.get("/healthz")
def salud():
    return {"ok": True}


@app.get("/")
def inicio():
    return FileResponse(ESTATICO / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/ping")
def ping():
    return {"ok": True, "app": "pedidos-sap"}


@app.get("/api/sesion")
def ver_sesion(request: Request):
    u = sv.sesion(request.cookies.get(GALLETA))
    if not u:
        return JSONResponse({"detail": core.M("e_sesion"), "instalar": not sv.hay_admin()}, 401)
    return u


@app.post("/api/login")
def login(request: Request, response: Response, b: dict = Body(...)):
    try:
        token, u = sv.autenticar(b.get("usuario"), b.get("password"))
    except PermissionError as e:
        raise HTTPException(401, str(e))
    https = request.headers.get("x-forwarded-proto", request.url.scheme).startswith("https")
    response.set_cookie(GALLETA, token, max_age=sv.HORAS_SESION * 3600, httponly=True, samesite="lax", secure=https, path="/")
    return u


@app.post("/api/logout")
def logout(request: Request, response: Response):
    sv.cerrar_sesion(request.cookies.get(GALLETA))
    response.delete_cookie(GALLETA, path="/")
    return {"ok": True}


@app.post("/api/instalar")
def instalar(b: dict = Body(...)):
    _seguro(sv.instalar, b)
    return {"ok": True}


# ---------- cualquier usuario (los datos se filtran por perfil en servicio.py) ----------
@app.get("/api/estado")
def estado(u=Depends(usuario)):
    return sv.estado(u)


@app.post("/api/importar")
def importar(b: dict = Body(...), u=Depends(usuario)):
    if b.get("tipo") != "pedidos" and u["rol"] != "admin":
        raise HTTPException(403, core.M("e_solo_admin"))
    return {"mensaje": _seguro(sv.importar, b.get("tipo"), b.get("nombre", "archivo"), b.get("texto", ""), "o_manual", None, u)}


@app.post("/api/previsualizar")
def previsualizar(b: dict = Body(...), u=Depends(usuario)):
    return _seguro(sv.previsualizar, b, u)


@app.post("/api/pedidos")
def crear(b: dict = Body(...), u=Depends(usuario)):
    return _seguro(sv.crear, b["entradas"], None, bool(b.get("enviar")), u)


@app.post("/api/pedidos/{pid}/enviar")
def enviar(pid: str, u=Depends(usuario)):
    return _seguro(sv.enviar, pid, u)


@app.post("/api/pedidos/{pid}/recalcular")
def recalcular(pid: str, b: dict = Body(default={}), u=Depends(usuario)):
    return _seguro(sv.recalcular, pid, b.get("entrada"), u)


@app.delete("/api/pedidos/{pid}")
def eliminar(pid: str, u=Depends(usuario)):
    _seguro(sv.eliminar, pid, u)
    return {"ok": True}


@app.get("/api/pedidos/{pid}/json")
def json_sap(pid: str, u=Depends(usuario)):
    return JSONResponse(core.json_sap(_seguro(sv.obtener, pid, u)))


# ---------- solo administrador ----------
@app.put("/api/config")
def config(b: dict = Body(...), u=Depends(admin)):
    _seguro(sv.guardar_config, b)
    return {"ok": True}


@app.post("/api/sync/{tipo}")
def sync(tipo: str, u=Depends(admin)):
    if tipo not in core.TIPOS:
        raise HTTPException(400, core.M("e_tipo"))
    return {"mensaje": core.M("m_archivos", _seguro(sv.sincronizar, tipo))}


@app.post("/api/probar")
def probar(u=Depends(admin)):
    return {"mensaje": _seguro(sv.probar_conexion)}


@app.post("/api/demo")
def demo(u=Depends(admin)):
    _seguro(sv.cargar_demo)
    return {"ok": True}


@app.get("/api/usuarios")
def usuarios(u=Depends(admin)):
    return sv.listar_usuarios()


@app.put("/api/usuarios")
def guardar_usuario(b: dict = Body(...), u=Depends(admin)):
    _seguro(sv.guardar_usuario, b, u)
    return {"ok": True}


@app.delete("/api/usuarios/{nombre}")
def borrar_usuario(nombre: str, u=Depends(admin)):
    _seguro(sv.borrar_usuario, nombre, u)
    return {"ok": True}


@app.delete("/api/usuarios/{nombre}/llaves")
def revocar_llaves_usuario(nombre: str, u=Depends(admin)):
    sv.revocar_llaves_de(nombre)
    return {"ok": True}


# ---------- llaves de API de cada usuario (desde la interfaz) ----------
@app.get("/api/llaves")
def mis_llaves(u=Depends(usuario)):
    return sv.listar_llaves(u)


@app.post("/api/llaves")
def nueva_llave(b: dict = Body(default={}), u=Depends(usuario)):
    return _seguro(sv.crear_llave, u, b.get("nombre", ""))


@app.delete("/api/llaves/{llave_id}")
def borrar_llave(llave_id: int, u=Depends(usuario)):
    _seguro(sv.revocar_llave, u, llave_id)
    return {"ok": True}


app.mount("/api/v1", api_v1.api)
