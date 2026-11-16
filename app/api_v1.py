"""API v1 para los sistemas de los clientes.

El sistema local del cliente genera su archivo JSON o CSV y lo envía aquí; la API lo valida, propone almacén, precio,
importe y fecha de entrega, y devuelve la salida en JSON o CSV. También permite consultar el estatus de sus pedidos.

Autenticación: encabezado  Authorization: Bearer <llave>  (o  X-API-Key: <llave>). Cada llave pertenece a un usuario
de la aplicación y hereda sus permisos: la llave de un usuario Cliente solo ve y crea pedidos de su número de cliente.
Documentación interactiva: /api/v1/docs
"""
import json
from typing import Optional
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from . import core, servicio as sv

DESCRIPCION = """
Connect a customer's own system to SAP Orders.

**Authentication**: send `Authorization: Bearer <your API key>`. Keys are created on the **API** screen of the
application. A key belongs to a user and has that user's permissions: a Customer user's key only sees and creates
orders for its own customer number.

**Sending orders**: `POST /orders` with the file your system generates, as JSON or CSV, in the request body
(`Content-Type: application/json` or `text/csv`) or as a multipart upload in the field `file`. Columns and fields accept
the SAP name or English/Spanish aliases: `customer`, `customer_po`, `material`, `quantity`, `delivery_address`, `items`.

**Responses**: JSON by default; add `format=csv` (or `Accept: text/csv`) for one CSV row per line item.
Add `lang=es` for messages in Spanish.
"""

api = FastAPI(title="SAP Orders API", version="1.0", description=DESCRIPCION, docs_url="/docs", redoc_url=None,
              openapi_url="/openapi.json", swagger_ui_parameters={"defaultModelsExpandDepth": -1})
portador = HTTPBearer(auto_error=False, description="API key created on the API screen of the application")

EJEMPLO_JSON = {"customer": "100040", "customer_po": "PO-2026-1188", "delivery_address": "100041",
                "items": [{"material": "PIS-BOLT-050", "quantity": 120}, {"material": "10000420", "quantity": 60}]}
EJEMPLO_CSV = ("customer,customer_po,material,quantity,delivery_address\r\n"
               "100040,PO-2026-1189,PIS-BOLT-050,120,100041\r\n100040,PO-2026-1189,10000420,60,100041\r\n")
CUERPO = {"requestBody": {"required": True, "content": {
    "application/json": {"schema": {"type": "object"}, "example": EJEMPLO_JSON},
    "text/csv": {"schema": {"type": "string"}, "example": EJEMPLO_CSV},
    "multipart/form-data": {"schema": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}, "required": ["file"]}}}}}


def _lang(request: Request, lang: Optional[str]):
    if lang in ("es", "en"):
        return lang
    return "es" if request.headers.get("accept-language", "").lower().startswith("es") else "en"


@api.exception_handler(HTTPException)
async def _error(request: Request, exc: HTTPException):
    lang = _lang(request, request.query_params.get("lang"))
    det = exc.detail
    cuerpo = {"error": core.texto(det["mensaje"], lang), **{k: v for k, v in det.items() if k != "mensaje"}} if isinstance(det, dict) \
        else {"error": core.texto(det, lang)}
    return JSONResponse(cuerpo, exc.status_code, headers=exc.headers)


def autenticar(request: Request, cred: Optional[HTTPAuthorizationCredentials] = Depends(portador)):
    llave = (cred.credentials if cred else "") or request.headers.get("x-api-key", "").strip()
    if llave:
        u = sv.usuario_por_llave(llave)
        if not u:
            raise HTTPException(401, core.M("e_llave"), headers={"WWW-Authenticate": "Bearer"})
        return u
    # Para consultar desde el navegador con la sesión abierta en la aplicación (solo lectura).
    if request.method in ("GET", "HEAD"):
        u = sv.sesion(request.cookies.get("sesion"))
        if u:
            return u
    raise HTTPException(401, core.M("e_llave_req"), headers={"WWW-Authenticate": "Bearer"})


def _ejecutar(fn, *a):
    try:
        return fn(*a)
    except sv.Duplicado as e:
        raise HTTPException(409, {"mensaje": str(e), "existing_orders": e.existentes})
    except KeyError as e:
        raise HTTPException(404, core.M("e_no_pedido", e.args[0] if e.args else ""))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {e}")


def _quiere_csv(request: Request, fmt: Optional[str]):
    if fmt:
        if fmt.lower() not in ("json", "csv"):
            raise HTTPException(400, "format must be json or csv")
        return fmt.lower() == "csv"
    return "text/csv" in request.headers.get("accept", "")


def _csv(texto, nombre):
    return Response(texto, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


def _responder(request, fmt, lang, pedidos, nombre, codigo=200, extra=None):
    salida = [core.pedido_api(p, lang) for p in pedidos]
    if _quiere_csv(request, fmt):
        r = _csv(core.csv_pedidos(salida), nombre)
        r.status_code = codigo
        return r
    return JSONResponse({**(extra or {}), "orders": salida}, codigo)


async def _leer_cuerpo(request: Request):
    """Acepta el archivo en el cuerpo (JSON o CSV) o como carga multipart en el campo «file»."""
    tipo = request.headers.get("content-type", "").lower()
    if tipo.startswith("multipart/form-data"):
        form = await request.form()
        f = form.get("file")
        if f is None or not hasattr(f, "read"):
            raise HTTPException(400, core.M("e_vacio"))
        return (await f.read()).decode("utf-8-sig"), f.filename or "upload"
    datos = await request.body()
    return datos.decode("utf-8-sig"), "api.csv" if "csv" in tipo else "api"


# ---------- puntos de entrada ----------
@api.get("/me", summary="Who am I", tags=["Account"])
def yo(u=Depends(autenticar)):
    return {"user": u["usuario"], "name": u["nombre"], "role": u["rol"], "customer": u["KUNNR"] or None}


@api.post("/orders", status_code=201, summary="Send orders (JSON or CSV)", tags=["Orders"], openapi_extra=CUERPO,
          description="Creates one order per customer + customer PO + delivery address found in the file. Each order comes back "
                      "with the proposed warehouse, price, amount and planned delivery date. Orders with errors are kept as drafts. "
                      "A customer PO that already exists is rejected with 409 so a retry never duplicates an order.")
async def crear_pedidos(request: Request, send: bool = Query(False, description="Send orders without errors to SAP right away"),
                        allow_duplicate: bool = Query(False, description="Create the order even if the customer PO already exists"),
                        format: Optional[str] = Query(None, description="json (default) or csv"),
                        lang: Optional[str] = Query(None, description="en (default) or es"), u=Depends(autenticar)):
    texto, nombre = await _leer_cuerpo(request)
    cre = await run_in_threadpool(_ejecutar, sv.recibir_api, texto, nombre, u, send, allow_duplicate)
    return _responder(request, format, _lang(request, lang), cre, "orders.csv", 201,
                      {"created": len(cre), "with_errors": sum(o["errores"] != [] or any(x["errores"] for x in o["posiciones"]) for o in cre)})


@api.post("/orders/preview", summary="Quote orders without saving", tags=["Orders"], openapi_extra=CUERPO,
          description="Same input as POST /orders. Returns warehouse, price, amount and planned delivery without creating anything.")
async def cotizar(request: Request, format: Optional[str] = Query(None), lang: Optional[str] = Query(None), u=Depends(autenticar)):
    texto, nombre = await _leer_cuerpo(request)
    peds = await run_in_threadpool(_ejecutar, sv.cotizar_api, texto, nombre, u)
    return _responder(request, format, _lang(request, lang), peds, "preview.csv")


@api.get("/orders", summary="List orders and their status", tags=["Orders"],
         description="Newest first. Use `since` to fetch only orders created or updated after a date and time.")
def listar(request: Request, status: Optional[str] = Query(None, description="Comma-separated status codes, e.g. ENVIADO_SAP,EMBARCADO"),
           customer_po: Optional[str] = Query(None), since: Optional[str] = Query(None, description="ISO date or date-time, e.g. 2026-11-16T08:00:00"),
           customer: Optional[str] = Query(None, description="Internal users only"), limit: int = Query(200, ge=1, le=1000),
           format: Optional[str] = Query(None), lang: Optional[str] = Query(None), u=Depends(autenticar)):
    peds = _ejecutar(sv.pedidos_api, u, status, customer_po, since, customer, limit)
    return _responder(request, format, _lang(request, lang), peds, "orders.csv", extra={"count": len(peds)})


@api.get("/orders/{order_id}", summary="Order output and status history", tags=["Orders"])
def detalle(request: Request, order_id: str, format: Optional[str] = Query(None), lang: Optional[str] = Query(None), u=Depends(autenticar)):
    p = _ejecutar(sv.pedido_api, order_id, u)
    if _quiere_csv(request, format):
        return _csv(core.csv_pedidos([core.pedido_api(p, _lang(request, lang))]), f"{order_id}.csv")
    return core.pedido_api(p, _lang(request, lang))


@api.post("/orders/{order_id}/send", summary="Send a draft order to SAP", tags=["Orders"])
def enviar(request: Request, order_id: str, lang: Optional[str] = Query(None), u=Depends(autenticar)):
    return core.pedido_api(_ejecutar(sv.enviar_api, order_id, u), _lang(request, lang))


@api.get("/materials", summary="Materials with price and availability", tags=["Catalog"],
         description="Price valid today for the customer of the key (or `customer` for internal users) and available quantity by warehouse.")
def materiales(request: Request, customer: Optional[str] = Query(None, description="Internal users only"),
               format: Optional[str] = Query(None), u=Depends(autenticar)):
    mats = _ejecutar(sv.materiales_api, u, customer)
    if _quiere_csv(request, format):
        return _csv(core.csv_materiales(mats), "materials.csv")
    return {"count": len(mats), "materials": mats}
