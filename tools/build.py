"""Inyecta app/shared.json en static/index.src.html y genera static/index.html (archivo único, funciona con o sin servidor)."""
import pathlib
R = pathlib.Path(__file__).resolve().parent.parent
src = (R / "static" / "index.src.html").read_text("utf-8")
out = src.replace("/*__SHARED__*/null", (R / "app" / "shared.json").read_text("utf-8").replace("</", "<\\/"))
assert out != src
(R / "static" / "index.html").write_text(out, "utf-8")
print("static/index.html", len(out) // 1024, "KB")
