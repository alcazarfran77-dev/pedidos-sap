"""Intercambio de archivos con SAP: SFTP (paramiko) o carpeta local/compartida (mismo contrato)."""
import os, posixpath, stat
from pathlib import Path

EXT = (".json", ".csv")


class Carpeta:
    def __init__(self, cx):
        self.base = Path(cx.get("carpeta_base") or "intercambio").resolve()

    def __enter__(self): return self
    def __exit__(self, *a): pass

    def _p(self, ruta):
        p = (self.base / ruta.lstrip("/")).resolve()
        if self.base != p and self.base not in p.parents:
            raise ValueError("Ruta fuera de la carpeta base")
        return p

    def listar(self, ruta):
        d = self._p(ruta)
        d.mkdir(parents=True, exist_ok=True)
        fs = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() in EXT]
        return sorted(((f.name, f.stat().st_mtime, f.stat().st_size) for f in fs), key=lambda x: x[1])

    def leer(self, ruta, nombre): return (self._p(ruta) / nombre).read_bytes()

    def escribir(self, ruta, nombre, datos):
        d = self._p(ruta)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / (nombre + ".tmp")
        tmp.write_bytes(datos)
        os.replace(tmp, d / nombre)

    def archivar(self, ruta, nombre):
        d = self._p(ruta) / "procesados"
        d.mkdir(exist_ok=True)
        os.replace(self._p(ruta) / nombre, d / nombre)


class Sftp:
    def __init__(self, cx):
        self.cx = cx

    def __enter__(self):
        import paramiko
        cx = self.cx
        self.cli = paramiko.SSHClient()
        self.cli.load_system_host_keys()
        self.cli.set_missing_host_key_policy(paramiko.AutoAddPolicy() if cx.get("aceptar_host_desconocido") else paramiko.RejectPolicy())
        self.cli.connect(cx["host"], port=int(cx.get("puerto") or 22), username=cx["usuario"],
                         password=cx.get("password") or None, key_filename=cx.get("ruta_llave") or None,
                         timeout=20, look_for_keys=False, allow_agent=False)
        self.s = self.cli.open_sftp()
        return self

    def __exit__(self, *a):
        try:
            self.s.close()
        finally:
            self.cli.close()

    def _mkdirs(self, ruta):
        acum = "/" if ruta.startswith("/") else ""
        for parte in [x for x in ruta.split("/") if x]:
            acum = posixpath.join(acum, parte)
            try:
                self.s.stat(acum)
            except IOError:
                self.s.mkdir(acum)

    def listar(self, ruta):
        self._mkdirs(ruta)
        fs = [a for a in self.s.listdir_attr(ruta) if stat.S_ISREG(a.st_mode or 0) and a.filename.lower().endswith(EXT)]
        return sorted(((a.filename, a.st_mtime or 0, a.st_size or 0) for a in fs), key=lambda x: x[1])

    def leer(self, ruta, nombre):
        with self.s.open(posixpath.join(ruta, nombre), "rb") as f:
            return f.read()

    def escribir(self, ruta, nombre, datos):
        self._mkdirs(ruta)
        tmp = posixpath.join(ruta, nombre + ".tmp")  # se sube con .tmp y se renombra: SAP nunca lee un archivo a medias
        with self.s.open(tmp, "wb") as f:
            f.write(datos)
        self.s.rename(tmp, posixpath.join(ruta, nombre))

    def archivar(self, ruta, nombre):
        d = posixpath.join(ruta, "procesados")
        self._mkdirs(d)
        dest = posixpath.join(d, nombre)
        try:
            self.s.remove(dest)
        except IOError:
            pass
        self.s.rename(posixpath.join(ruta, nombre), dest)


def abrir(cfg):
    cx = cfg["conexion"]
    return Sftp(cx) if cx.get("modo") == "sftp" else Carpeta(cx)
