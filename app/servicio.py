"""Casos de uso: importar archivos, crear/enviar pedidos, sincronizar con SAP. Todo bajo un candado global."""
import copy, hashlib, json, os, re, secrets, threading, time
from . import core, db, transporte

RUTA_DB = os.environ.get("PEDIDOS_DB", "pedidos.db")
CANDADO = threading.RLock()
_con = None
_ultima = {}  # tipo -> epoch de la última sincronización


def con():
    global _con
    if _con is None:
        _con = db.conectar(RUTA_DB)
    return _con


def _cfg_efectiva(cfg):
    """La contraseña puede venir de la variable de entorno SFTP_PASSWORD en lugar de guardarse en la base."""
    cfg = copy.deepcopy(cfg)
    if os.environ.get("SFTP_PASSWORD"):
        cfg["conexion"]["password"] = os.environ["SFTP_PASSWORD"]
    return cfg


def es_cliente(u):
    return bool(u) and u["rol"] == "cliente"


def _restringir(ent, u):
    """Un usuario cliente solo levanta pedidos de su propio cliente y no elige almacén."""
    if es_cliente(u):
        ent["KUNNR"] = u["KUNNR"]
        for p in ent.get("posiciones", []):
            p["WERKS"] = ""
    return ent


def estado(u=None):
    """Estado para la interfaz. A un usuario cliente solo se le entrega lo suyo: sus pedidos, sus direcciones,
    sus precios y el inventario ya descontado de lo comprometido por otros clientes (sin revelar esos pedidos)."""
    with CANDADO:
        st = db.cargar(con())
        st["config"]["conexion"]["password"] = "********" if st["config"]["conexion"]["password"] else ""
        st["bitacora"] = db.bitacora(con())
        st["usuario"] = u
        if u and u["rol"] != "admin":
            st["bitacora"] = []
            st["config"] = {k: v for k, v in st["config"].items() if k != "conexion"}
        if es_cliente(u):
            k = u["KUNNR"]
            ajeno = {}
            for o in st["pedidos"]:
                if o["KUNNR"] != k and o["estatus"] in core.ABIERTOS:
                    for x in o["posiciones"]:
                        ajeno[(x["MATNR"], x["WERKS"])] = ajeno.get((x["MATNR"], x["WERKS"]), 0) + x["cantidad"]
            for r in st["inventario"]:
                r["LABST"] = (r["LABST"] or 0) - ajeno.pop((r["MATNR"], r["WERKS"]), 0)
            st["pedidos"] = [o for o in st["pedidos"] if o["KUNNR"] == k]
            for o in st["pedidos"]:  # sin rutas internas del SFTP en el historial que ve el cliente
                for h in o["historial"]:
                    if h["fuente"] == "sistema" and h["estatus"] == "ENVIADO_SAP":
                        h["texto"] = core.M("h_enviado")
            st["clientes"] = [r for r in st["clientes"] if r["KUNNR"] == k]
            st["precios"] = [r for r in st["precios"] if r["KUNNR"] in ("", k)]
            st["xref"] = [r for r in st["xref"] if r["KUNNR"] == k]
            st["config"] = {"moneda": st["config"]["moneda"], "prefijo": st["config"]["prefijo"]}
        st["ultima_sync"] = {k: core.dt.datetime.fromtimestamp(v).replace(microsecond=0).isoformat() for k, v in _ultima.items()}
        st["modo"] = "servidor"
        return st


def guardar_config(nueva):
    with CANDADO:
        st = db.cargar(con())
        pw = st["config"]["conexion"]["password"]
        cfg = db._mezclar(st["config"], nueva)
        if cfg["conexion"]["password"] == "********":
            cfg["conexion"]["password"] = pw
        cfg["consecutivo"] = st["config"]["consecutivo"] if "consecutivo" not in nueva else int(nueva["consecutivo"])
        db.guardar_config(con(), cfg)
        con().commit()


def _crear(st, entradas, origen, tr=None, auto=False):
    creados = []
    for ent in entradas:
        ent["origen"] = origen
        p = core.construir_pedido(st, ent)
        p["id"] = core.siguiente_id(st)
        st["pedidos"].insert(0, p)
        if st["config"].get("enviar_automatico") and auto and not core.tiene_errores(p):
            try:
                _enviar(st, p, tr)
            except Exception as e:  # el pedido queda en borrador y se puede reenviar
                p["avisos"].append(core.M("a_auto", e))
        db.guardar_pedido(con(), p)
        creados.append(p)
    db.guardar_config(con(), st["config"])
    return creados


def _enviar(st, p, tr=None):
    if core.tiene_errores(p):
        raise ValueError(core.M("e_errores"))
    if p["estatus"] != "BORRADOR":
        raise ValueError(core.M("e_ya_enviado"))
    nombre = core.nombre_archivo_sap(p)
    datos = json.dumps(core.json_sap(p), ensure_ascii=False, indent=2).encode("utf-8")
    cfg = _cfg_efectiva(st["config"])
    if tr:
        tr.escribir(cfg["rutas"]["salida"], nombre, datos)
    else:
        with transporte.abrir(cfg) as t:
            t.escribir(cfg["rutas"]["salida"], nombre, datos)
    core.marcar_enviado(p, nombre, core.M("h_archivo", nombre, cfg["conexion"]["modo"], cfg["rutas"]["salida"]))


def importar(tipo, nombre, texto, fuente="o_manual", tr=None, u=None):
    """Procesa un archivo de cualquier tipo. Devuelve un mensaje para la bitácora."""
    if tipo not in core.TIPOS:
        raise ValueError(core.M("e_tipo"))
    with CANDADO:
        st = db.cargar(con())
        filas = core.normalizar(tipo, core.leer_texto(nombre, texto))
        if es_cliente(u):
            for f in filas:
                f["KUNNR"], f["WERKS"] = u["KUNNR"], ""
        if not filas:
            raise ValueError(core.M("e_sin_validos", ", ".join(core.REQ[tipo])))
        if tipo in core.MAESTROS:
            n = core.aplicar_maestro(st, tipo, filas)
            db.guardar_maestro(con(), tipo, st[tipo])
            msg = core.M("m_registros", n)
        elif tipo == "estatus":
            n, sin = core.aplicar_estatus(st, filas)
            for p in st["pedidos"]:
                db.guardar_pedido(con(), p)
            msg = core.M("m_estatus_sin", n, ", ".join(sin[:8])) if sin else core.M("m_estatus", n)
        else:
            cre = _crear(st, core.agrupar_entradas(filas), core.M(fuente, nombre, u["usuario"] if u else ""), tr, auto=True)
            err = sum(core.tiene_errores(p) for p in cre)
            ids = ", ".join(p["id"] for p in cre)
            msg = core.M("m_pedidos_err", len(cre), ids, err) if err else core.M("m_pedidos", len(cre), ids)
        db.log(con(), tipo, nombre, True, msg)
        con().commit()
        return msg


def previsualizar(ent, u=None):
    with CANDADO:
        st = db.cargar(con())
        if ent.get("id"):
            _pedido(st, ent["id"], u)
        return core.construir_pedido(st, _restringir(ent, u), ent.get("id") or "")


def crear(entradas, origen=None, enviar=False, u=None):
    with CANDADO:
        st = db.cargar(con())
        cre = _crear(st, [_restringir(e, u) for e in entradas], core.M("o_captura", u["usuario"]) if u else origen)
        con().commit()
        if enviar:
            for p in cre:
                _enviar(st, p)
                db.guardar_pedido(con(), p)
            con().commit()
        return cre


def _pedido(st, pid, u=None):
    p = next((x for x in st["pedidos"] if x["id"] == pid), None)
    if not p or (es_cliente(u) and p["KUNNR"] != u["KUNNR"]):  # el pedido de otro cliente "no existe"
        raise KeyError(pid)
    return p


def enviar(pid, u=None):
    with CANDADO:
        st = db.cargar(con())
        p = _pedido(st, pid, u)
        _enviar(st, p)
        db.guardar_pedido(con(), p)
        con().commit()
        return p


def recalcular(pid, entrada=None, u=None):
    with CANDADO:
        st = db.cargar(con())
        p = _pedido(st, pid, u)
        if p["estatus"] != "BORRADOR":
            raise ValueError(core.M("e_rec"))
        n = core.construir_pedido(st, _restringir(entrada or p["entrada"], u), pid, previo=p)
        n["origen"] = p["origen"]
        db.guardar_pedido(con(), n)
        con().commit()
        return n


def obtener(pid, u=None):
    with CANDADO:
        return _pedido(db.cargar(con()), pid, u)


def eliminar(pid, u=None):
    with CANDADO:
        p = _pedido(db.cargar(con()), pid, u)
        if p["estatus"] != "BORRADOR":
            raise ValueError(core.M("e_del"))
        db.borrar_pedido(con(), pid)
        con().commit()


def cargar_demo():
    with CANDADO:
        st = db.cargar(con())
        d = core.SHARED["demo"]
        for t in core.MAESTROS:
            core.aplicar_maestro(st, t, core.normalizar(t, d[t]))
            db.guardar_maestro(con(), t, st[t])
        if not st["pedidos"]:
            _crear(st, copy.deepcopy(d["pedidos"]), core.M("o_demo"))
        db.log(con(), "demo", "", True, core.M("m_demo"))
        con().commit()


def probar_conexion():
    with CANDADO:
        cfg = _cfg_efectiva(db.cargar(con())["config"])
    with transporte.abrir(cfg) as t:
        n = len(t.listar(cfg["rutas"]["estatus"]))
    return core.M("m_conexion", cfg["conexion"]["modo"], n, cfg["rutas"]["estatus"])


def sincronizar(tipo):
    """Lee del SFTP los archivos nuevos de un tipo y los procesa en orden de antigüedad."""
    with CANDADO:
        cfg = _cfg_efectiva(db.cargar(con())["config"])
        ruta, n = cfg["rutas"][tipo], 0
        _ultima[tipo] = time.time()
        try:
            with transporte.abrir(cfg) as t:
                for nombre, mtime, tam in t.listar(ruta):
                    firma = f"{nombre}|{int(mtime)}|{tam}"
                    if db.visto(con(), ruta, firma):
                        continue
                    try:
                        importar(tipo, nombre, t.leer(ruta, nombre).decode("utf-8-sig"), "o_sftp" if cfg["conexion"]["modo"] == "sftp" else "o_carpeta", t)
                        n += 1
                    except Exception as e:
                        con().rollback()
                        db.log(con(), tipo, nombre, False, core.M("e_rechazado", e))
                    db.marcar_visto(con(), ruta, firma)
                    con().commit()
                    if cfg["conexion"].get("archivar"):
                        try:
                            t.archivar(ruta, nombre)
                        except Exception as e:
                            db.log(con(), tipo, nombre, False, core.M("e_mover", e))
                            con().commit()
        except Exception as e:
            db.log(con(), tipo, "", False, core.M("e_sync", e))
            con().commit()
            raise
        return n


def ciclo_programado(detener):
    """Hilo en segundo plano: ejecuta cada sincronización según su intervalo en minutos (0 = desactivada)."""
    while not detener.wait(20):
        try:
            with CANDADO:
                inter = db.cargar(con())["config"]["intervalos"]
            for tipo in core.TIPOS:
                m = float(inter.get(tipo) or 0)
                if m > 0 and time.time() - _ultima.get(tipo, 0) >= m * 60:
                    try:
                        sincronizar(tipo)
                    except Exception:
                        pass  # ya quedó en bitácora; se reintenta en el siguiente intervalo
        except Exception:
            pass


# ---------- usuarios y sesiones ----------
ROLES = ("admin", "ventas", "cliente")
HORAS_SESION = 12
_fallos = {}  # usuario -> [intentos fallidos, bloqueado hasta]


def _hash(clave, sal=None):
    sal = sal or secrets.token_hex(16)
    return hashlib.scrypt(clave.encode("utf-8"), salt=bytes.fromhex(sal), n=2 ** 14, r=8, p=1).hex(), sal


def admin_entorno():
    """Administrador definido por variables de entorno (APP_USER / APP_PASSWORD); no se guarda en la base."""
    u, c = os.environ.get("APP_USER", "").strip().lower(), os.environ.get("APP_PASSWORD", "")
    return (u, c) if u and c else None


def hay_admin():
    with CANDADO:
        return bool(admin_entorno()) or con().execute("SELECT 1 FROM usuarios WHERE rol='admin' AND activo=1").fetchone() is not None


def _publico(r):
    return {"usuario": r["usuario"], "nombre": r["nombre"], "rol": r["rol"], "KUNNR": r["KUNNR"], "activo": bool(r["activo"])}


def _buscar(usuario):
    env = admin_entorno()
    if env and usuario == env[0]:
        return {"usuario": usuario, "nombre": "Administrator", "rol": "admin", "KUNNR": "", "activo": True}
    r = con().execute("SELECT * FROM usuarios WHERE usuario=?", (usuario,)).fetchone()
    return _publico(r) if r and r["activo"] else None


def autenticar(usuario, clave):
    usuario = str(usuario or "").strip().lower()
    f = _fallos.setdefault(usuario, [0, 0])
    if time.time() < f[1]:
        raise PermissionError(core.M("e_bloqueo"))
    with CANDADO:
        env, ok = admin_entorno(), False
        if env and usuario == env[0]:
            ok = secrets.compare_digest(str(clave).encode(), env[1].encode())
        else:
            r = con().execute("SELECT * FROM usuarios WHERE usuario=? AND activo=1", (usuario,)).fetchone()
            h, _ = _hash(str(clave), r["sal"] if r else "00" * 16)  # mismo costo exista o no el usuario
            ok = bool(r) and secrets.compare_digest(h, r["hash"])
        if not ok:
            f[0] += 1
            if f[0] >= 5:
                f[0], f[1] = 0, time.time() + 300
            raise PermissionError(core.M("e_login"))
        _fallos.pop(usuario, None)
        token = secrets.token_urlsafe(32)
        con().execute("DELETE FROM sesiones WHERE expira < ?", (time.time(),))
        con().execute("INSERT INTO sesiones VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), usuario, time.time() + HORAS_SESION * 3600))
        con().commit()
        return token, _buscar(usuario)


def sesion(token):
    if not token:
        return None
    with CANDADO:
        r = con().execute("SELECT usuario FROM sesiones WHERE token=? AND expira > ?", (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return _buscar(r["usuario"]) if r else None


def cerrar_sesion(token):
    with CANDADO:
        con().execute("DELETE FROM sesiones WHERE token=?", (hashlib.sha256((token or "").encode()).hexdigest(),))
        con().commit()


def listar_usuarios():
    with CANDADO:
        us = [_publico(r) for r in con().execute("SELECT * FROM usuarios ORDER BY rol, usuario")]
        env = admin_entorno()
        if env:
            us.insert(0, {"usuario": env[0], "nombre": "Administrator", "rol": "admin", "KUNNR": "", "activo": True, "fijo": True})
        return us


def guardar_usuario(d, actor=None):
    usuario = str(d.get("usuario", "")).strip().lower()
    rol, kunnr, clave = d.get("rol"), str(d.get("KUNNR", "")).strip(), str(d.get("password") or "")
    activo = bool(d.get("activo", True))
    if not re.fullmatch(r"[a-z0-9._@-]{3,60}", usuario):
        raise ValueError(core.M("e_usr_formato"))
    env = admin_entorno()
    if env and usuario == env[0]:
        raise ValueError(core.M("e_usr_env"))
    if rol not in ROLES:
        raise ValueError(core.M("e_perfil"))
    with CANDADO:
        previo = con().execute("SELECT * FROM usuarios WHERE usuario=?", (usuario,)).fetchone()
        if d.get("nuevo") and previo:
            raise ValueError(core.M("e_usr_existe", usuario))
        if rol == "cliente":
            if not con().execute("SELECT 1 FROM clientes WHERE KUNNR=?", (kunnr,)).fetchone():
                raise ValueError(core.M("cli_no_existe", kunnr))
        else:
            kunnr = ""
        if not previo and not clave:
            raise ValueError(core.M("e_pw_nueva"))
        if clave and len(clave) < 8:
            raise ValueError(core.M("e_pw_corta"))
        if actor and actor["usuario"] == usuario and (rol != "admin" or not activo):
            raise ValueError(core.M("e_auto_admin"))
        h, sal = _hash(clave) if clave else (previo["hash"], previo["sal"])
        con().execute("INSERT OR REPLACE INTO usuarios(usuario,nombre,rol,KUNNR,hash,sal,activo) VALUES(?,?,?,?,?,?,?)",
                      (usuario, str(d.get("nombre", "")).strip(), rol, kunnr, h, sal, int(activo)))
        if previo and (clave or not activo or previo["rol"] != rol or previo["KUNNR"] != kunnr):
            con().execute("DELETE FROM sesiones WHERE usuario=?", (usuario,))  # obliga a entrar de nuevo
        con().commit()


def borrar_usuario(usuario, actor):
    if actor["usuario"] == usuario:
        raise ValueError(core.M("e_auto_borrar"))
    with CANDADO:
        con().execute("DELETE FROM usuarios WHERE usuario=?", (usuario,))
        con().execute("DELETE FROM sesiones WHERE usuario=?", (usuario,))
        con().commit()


def instalar(d):
    """Primer arranque sin APP_USER/APP_PASSWORD: crea el primer administrador."""
    with CANDADO:
        if hay_admin() or os.environ.get("RENDER"):
            raise PermissionError(core.M("e_ya_admin"))
        guardar_usuario({**d, "rol": "admin", "activo": True, "nuevo": True})
