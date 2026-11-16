"""Persistencia en SQLite. Maestros en tablas propias; pedidos en cabecera + posiciones + historial."""
import json, sqlite3, copy
from . import core

DDL = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS clientes(KUNNR TEXT NOT NULL, NAME1 TEXT, KUNWE TEXT NOT NULL DEFAULT '', STRAS TEXT, ORT01 TEXT, REGIO TEXT, PSTLZ TEXT, PRIMARY KEY(KUNNR,KUNWE));
CREATE TABLE IF NOT EXISTS almacenes(WERKS TEXT PRIMARY KEY, NAME1 TEXT, ORT01 TEXT, PSTLZ TEXT, LAT REAL, LON REAL);
CREATE TABLE IF NOT EXISTS inventario(MATNR TEXT NOT NULL, MAKTX TEXT, WERKS TEXT NOT NULL, LGORT TEXT NOT NULL DEFAULT '', LABST REAL NOT NULL DEFAULT 0, MEINS TEXT, PRIMARY KEY(MATNR,WERKS,LGORT));
CREATE TABLE IF NOT EXISTS precios(MATNR TEXT NOT NULL, KUNNR TEXT NOT NULL DEFAULT '', KBETR REAL NOT NULL, KONWA TEXT, DATAB TEXT NOT NULL DEFAULT '', DATBI TEXT, PRIMARY KEY(MATNR,KUNNR,DATAB));
CREATE TABLE IF NOT EXISTS xref(KUNNR TEXT NOT NULL, KDMAT TEXT NOT NULL, MATNR TEXT NOT NULL, PRIMARY KEY(KUNNR,KDMAT));
CREATE TABLE IF NOT EXISTS pedidos(id TEXT PRIMARY KEY, BSTKD TEXT, KUNNR TEXT NOT NULL, NAME1 TEXT, estatus TEXT NOT NULL, VBELN TEXT, fecha TEXT NOT NULL,
  origen TEXT, moneda TEXT, total REAL, archivo_sap TEXT, direccion TEXT, errores TEXT, avisos TEXT, entrada TEXT);
CREATE TABLE IF NOT EXISTS pedido_pos(pedido_id TEXT NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE, POSNR INTEGER NOT NULL, MATNR TEXT, cantidad REAL,
  precio REAL, importe REAL, WERKS TEXT, EDATU TEXT, detalle TEXT, PRIMARY KEY(pedido_id,POSNR));
CREATE TABLE IF NOT EXISTS pedido_hist(n INTEGER PRIMARY KEY AUTOINCREMENT, pedido_id TEXT NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
  fecha TEXT, estatus TEXT, texto TEXT, fuente TEXT);
CREATE INDEX IF NOT EXISTS ix_ped_estatus ON pedidos(estatus);
CREATE INDEX IF NOT EXISTS ix_pos_mat ON pedido_pos(MATNR,WERKS);
CREATE TABLE IF NOT EXISTS config(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS bitacora(n INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, tipo TEXT, archivo TEXT, ok INTEGER, mensaje TEXT);
CREATE TABLE IF NOT EXISTS archivos(ruta TEXT, firma TEXT, PRIMARY KEY(ruta,firma));
CREATE TABLE IF NOT EXISTS usuarios(usuario TEXT PRIMARY KEY, nombre TEXT, rol TEXT NOT NULL CHECK(rol IN ('admin','ventas','cliente')),
  KUNNR TEXT NOT NULL DEFAULT '', hash TEXT NOT NULL, sal TEXT NOT NULL, activo INTEGER NOT NULL DEFAULT 1,
  CHECK(rol <> 'cliente' OR KUNNR <> ''));
CREATE TABLE IF NOT EXISTS api_llaves(id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT NOT NULL, nombre TEXT, prefijo TEXT NOT NULL,
  hash TEXT NOT NULL UNIQUE, creada TEXT NOT NULL, ultimo_uso TEXT);
CREATE TABLE IF NOT EXISTS sesiones(token TEXT PRIMARY KEY, usuario TEXT NOT NULL, expira REAL NOT NULL);
"""
CAB = ["id", "BSTKD", "KUNNR", "NAME1", "estatus", "VBELN", "fecha", "origen", "moneda", "total", "archivo_sap"]
CABJ = ["direccion", "errores", "avisos", "entrada"]
POS = ["POSNR", "MATNR", "cantidad", "precio", "importe", "WERKS", "EDATU"]


def conectar(ruta):
    c = sqlite3.connect(ruta, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript(DDL)
    return c


def _mezclar(base, extra):
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _mezclar(base[k], v)
        else:
            base[k] = v
    return base


def cargar(c):
    st = {t: [dict(r) for r in c.execute(f"SELECT * FROM {t}")] for t in core.MAESTROS}
    fila = c.execute("SELECT v FROM config WHERE k='config'").fetchone()
    st["config"] = _mezclar(copy.deepcopy(core.CONFIG_DEFAULT), json.loads(fila["v"]) if fila else {})
    peds = []
    for r in c.execute("SELECT * FROM pedidos ORDER BY fecha DESC, id DESC"):
        p = {k: r[k] for k in CAB}
        p.update({k: json.loads(r[k]) for k in CABJ})
        p["posiciones"] = [dict(json.loads(x["detalle"]), **{k: x[k] for k in POS})
                           for x in c.execute("SELECT * FROM pedido_pos WHERE pedido_id=? ORDER BY POSNR", (p["id"],))]
        p["historial"] = [{k: h[k] for k in ("fecha", "estatus", "texto", "fuente")}
                          for h in c.execute("SELECT * FROM pedido_hist WHERE pedido_id=? ORDER BY n", (p["id"],))]
        peds.append(p)
    st["pedidos"] = peds
    return st


def guardar_maestro(c, tipo, filas):
    cols = list(core.ESQ[tipo])
    c.execute(f"DELETE FROM {tipo}")
    c.executemany(f"INSERT OR REPLACE INTO {tipo}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                  [[("" if r.get(k) is None and k not in core.NUM else r.get(k)) for k in cols] for r in filas])


def guardar_pedido(c, p):
    c.execute("DELETE FROM pedidos WHERE id=?", (p["id"],))
    c.execute(f"INSERT INTO pedidos({','.join(CAB + CABJ)}) VALUES({','.join('?' * (len(CAB) + len(CABJ)))})",
              [p[k] for k in CAB] + [json.dumps(p[k], ensure_ascii=False) for k in CABJ])
    for x in p["posiciones"]:
        det = {k: v for k, v in x.items() if k not in POS}
        c.execute(f"INSERT INTO pedido_pos(pedido_id,{','.join(POS)},detalle) VALUES(?,{','.join('?' * len(POS))},?)",
                  [p["id"]] + [x[k] for k in POS] + [json.dumps(det, ensure_ascii=False)])
    c.executemany("INSERT INTO pedido_hist(pedido_id,fecha,estatus,texto,fuente) VALUES(?,?,?,?,?)",
                  [(p["id"], h["fecha"], h["estatus"], h["texto"], h["fuente"]) for h in p["historial"]])


def borrar_pedido(c, pid):
    c.execute("DELETE FROM pedidos WHERE id=?", (pid,))


def guardar_config(c, cfg):
    c.execute("INSERT OR REPLACE INTO config(k,v) VALUES('config',?)", (json.dumps(cfg, ensure_ascii=False),))


def log(c, tipo, archivo, ok, mensaje):
    c.execute("INSERT INTO bitacora(fecha,tipo,archivo,ok,mensaje) VALUES(?,?,?,?,?)", (core.ahora(), tipo, archivo, int(ok), mensaje))
    c.execute("DELETE FROM bitacora WHERE n <= (SELECT MAX(n) FROM bitacora) - 500")


def bitacora(c, n=80):
    return [dict(r) for r in c.execute("SELECT fecha,tipo,archivo,ok,mensaje FROM bitacora ORDER BY n DESC LIMIT ?", (n,))]


def visto(c, ruta, firma):
    return c.execute("SELECT 1 FROM archivos WHERE ruta=? AND firma=?", (ruta, firma)).fetchone() is not None


def marcar_visto(c, ruta, firma):
    c.execute("INSERT OR IGNORE INTO archivos VALUES(?,?)", (ruta, firma))
