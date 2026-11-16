# Pedidos SAP

Levanta pedidos de clientes (captura o archivos JSON/CSV), revisa inventario por almacén, sugiere el almacén de embarque
más cercano a la dirección de entrega, calcula precio, importe y fecha planificada, genera el JSON para SAP y lo deposita
en un SFTP. Los clientes, el inventario, los precios y el estatus de cada pedido llegan de SAP por el mismo SFTP.

## Idioma y datos de ejemplo

La interfaz abre en **inglés** y tiene un botón para cambiar a **español** (la elección se recuerda en cada navegador).
Los mensajes que genera el servidor (avisos, errores, historial, bitácora) se guardan como códigos y se muestran en el
idioma elegido; los textos que manda SAP en los estatus se muestran tal cual. Los archivos aceptan encabezados con el
nombre SAP o alias en español o inglés (`customer`, `customer_po`, `material`, `quantity`, `delivery_address`…).

Los datos de demostración son empresas ficticias de **Canadá**, con importes en CAD. La ubicación de la entrega reconoce
códigos postales canadienses (`A1A 1A1`, por sus dos primeros caracteres) y mexicanos (5 dígitos).

## Dos formas de usarla

| | Con servidor | Sin servidor |
|---|---|---|
| Qué es | Python + FastAPI + SQLite | `static/index.html` abierto en el navegador |
| SFTP | Lee y escribe solo, según los minutos configurados | No hay: los archivos se cargan y el JSON se descarga a mano |
| Datos | `pedidos.db` (SQLite) | Almacenamiento del navegador |
| Instalación | Python 3.10+ en un servidor | Ninguna |

La interfaz es el mismo archivo en ambos casos: detecta si hay servidor y se adapta.

## Arranque del servidor

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abrir `http://servidor:8000`, entrar a **Intercambio con SAP**, capturar host, usuario, contraseña o llave, rutas y minutos
de lectura, y pulsar **Probar conexión**. Variables de entorno:

| Variable | Valor por defecto | Uso |
|---|---|---|
| `SFTP_HABILITADO` | `1` | `0` apaga toda conexión con SAP: archivos a mano y JSON descargable |
| `CARGAR_DEMO` | vacío | `1` carga los datos de ejemplo al arrancar si la base está vacía |
| `PEDIDOS_DB` | `pedidos.db` | Ruta de la base SQLite |
| `SFTP_PASSWORD` | vacío | Contraseña del SFTP, para no guardarla en la base |
| `APP_USER` / `APP_PASSWORD` | vacío | Administrador inicial (obligatorio en Render) |

El medio «Carpeta local o compartida» usa el mismo contrato de carpetas sin SFTP; sirve para pruebas o para una unidad de red.

Para GitHub y Render, ver `DESPLIEGUE.md`. El `render.yaml` incluido usa el plan gratuito con el SFTP desactivado.

## Usuarios y perfiles (versión con servidor)

Cada persona entra con su propio usuario y contraseña. El administrador los da de alta en la pantalla **Usuarios**.

| Perfil | Ve | Puede |
|---|---|---|
| Cliente | Solo los pedidos, direcciones y precios de su cliente SAP; inventario disponible | Capturar y enviar sus pedidos, cargar archivos de pedidos (siempre a su nombre). No elige almacén |
| Ventas | Todos los pedidos, inventario, datos maestros | Capturar para cualquier cliente, elegir almacén, enviar a SAP |
| Administrador | Todo | Además: SFTP, datos maestros, estatus, usuarios |

El filtro se aplica en el servidor (`app/servicio.py`): al navegador de un cliente nunca llegan pedidos de otros clientes,
y pedir uno ajeno por su número responde «no encontrado». El inventario que ve un cliente ya trae descontado lo
comprometido por otros, sin mostrar esos pedidos.

El primer administrador sale de `APP_USER` / `APP_PASSWORD` (obligatorio en Render) o, en una instalación local sin esas
variables, de la pantalla de primer arranque. Contraseñas guardadas con scrypt; sesión de 12 horas en cookie HttpOnly;
bloqueo de 5 minutos tras 5 intentos fallidos. La versión sin servidor no tiene usuarios.

## API para sistemas de clientes (versión con servidor)

El sistema local de cada cliente genera su archivo JSON o CSV y lo envía a la API; la API lo valida, crea los pedidos y
devuelve la salida (almacén, precio, importe, fecha planificada) en JSON o CSV. Después el sistema puede consultar el
estatus de sus pedidos.

- **Dirección**: `https://<servidor>/api/v1` · documentación interactiva en `/api/v1/docs`.
- **Llaves**: cada usuario genera las suyas en la pantalla **API** (máximo 5). Se envían como
  `Authorization: Bearer <llave>` (o `X-API-Key`). La llave completa solo se muestra al crearla; en la base queda su
  huella SHA-256. Una llave hereda los permisos de su usuario: la de un Cliente solo ve y crea pedidos de su número de
  cliente, aunque el archivo diga otro. Si el usuario se desactiva o se elimina, sus llaves dejan de funcionar; el
  administrador puede revocarlas desde **Usuarios**.

| Método y ruta | Uso |
|---|---|
| `POST /orders` | Recibe el archivo (JSON o CSV en el cuerpo, o multipart en el campo `file`) y crea los pedidos. `send=true` los envía a SAP si no tienen errores. Un pedido del cliente repetido responde 409 (`allow_duplicate=true` lo permite) |
| `POST /orders/preview` | Igual, sin guardar: cotiza almacén, precio, importe y fecha |
| `GET /orders` | Pedidos y estatus. Filtros `status`, `customer_po`, `since` (creados o actualizados desde) |
| `GET /orders/{id}` | Salida e historial de un pedido |
| `POST /orders/{id}/send` | Envía a SAP un borrador |
| `GET /materials` | Precio vigente para el cliente y disponible por almacén |
| `GET /me` | Usuario y cliente de la llave |

Todas las respuestas admiten `format=csv` (una fila por posición) y `lang=es`. El programa `ejemplos/cliente_api.py`
(solo biblioteca estándar de Python) muestra cómo enviar un archivo y descargar el estatus desde el sistema del cliente.

## Carpetas en el SFTP (configurables)

| Ruta | Sentido | Contenido | Lectura por defecto |
|---|---|---|---|
| `entrada/clientes` | SAP → app | Clientes y direcciones de entrega | 60 min |
| `entrada/inventario` | SAP → app | Existencia por material y almacén | 15 min |
| `entrada/precios` | SAP → app | Lista de precios (general y por cliente) | 60 min |
| `entrada/xref` | SAP → app | Código del cliente → material SAP | 60 min |
| `entrada/almacenes` | SAP → app | Almacenes con CP o coordenadas | desactivada |
| `entrada/estatus` | SAP → app | Estatus de pedidos | 5 min |
| `entrada/pedidos` | cliente → app | Pedidos en JSON o CSV | 5 min |
| `salida/pedidos` | app → SAP | `PEDIDO_<número>_<fecha>.json` | al enviar |

Cada archivo leído se mueve a `procesados/` (o se recuerda por nombre, fecha y tamaño si se desactiva el movimiento).
Los archivos de salida se suben como `.tmp` y se renombran al terminar. Los campos de cada archivo están en la pantalla
**Formatos de archivo** y hay ejemplos en `ejemplos/`.

## Reglas de cálculo

- **Material**: código SAP, código del cliente (xref) o descripción exacta.
- **Precio**: el del cliente si existe y está vigente; si no, el de la lista general.
- **Almacén**: se ordenan por distancia en línea recta a la entrega y se toma el primero cuyo disponible cubre la cantidad.
  Si ninguno la cubre, el de mayor disponible, con aviso. El usuario puede cambiarlo en la captura.
- **Ubicación de la entrega**: destinatario SAP del cliente, o dirección libre con CP. El código postal se ubica por sus dos primeros
  caracteres (tablas de Canadá y México en `tools/gen_shared.py`): es una aproximación a nivel ciudad/región, no geocodificación exacta.
- **Disponible**: existencia SAP menos pedidos en BORRADOR y ENVIADO_SAP (los que SAP aún no confirma).
- **Fecha planificada**: días de preparación + días de tránsito por tramo de distancia, en días hábiles.
- **Importes**: sin impuestos.

## Estructura

```
app/core.py        motor (misma lógica portada a JavaScript en la interfaz)
app/db.py          SQLite
app/transporte.py  SFTP (paramiko) y carpeta
app/servicio.py    casos de uso y programador de sincronización
app/main.py        API
static/index.html  interfaz (generada por tools/build.py desde index.src.html + app/shared.json)
tests/test_flujo.py  prueba de punta a punta contra un SFTP de prueba:  python -m tests.test_flujo
```

## Pendiente antes de producción

- No hay recuperación de contraseña por correo: el administrador la restablece desde **Usuarios**.
- El bloqueo por intentos fallidos vive en memoria y se reinicia con el servicio.

- «Aceptar servidores sin huella registrada» viene activado para facilitar la primera conexión; desactivarlo cuando la
  huella del SFTP esté en `known_hosts`.
- Los nombres de campo (KUNNR, MATNR, WERKS…) son una propuesta; el programa ABAP o la interfaz que genere y lea los
  archivos en SAP debe usar estos nombres o alguno de los alias listados.
