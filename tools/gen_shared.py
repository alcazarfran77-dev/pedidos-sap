"""Genera app/shared.json: esquema de campos, tabla CP->coordenadas (aprox.) y datos demo.
Lo usan tanto el servidor (Python) como la interfaz (se inyecta en index.html con tools/build.py)."""
import json, pathlib
R = pathlib.Path(__file__).resolve().parent.parent
CPS = """01-16|CDMX|Ciudad de México|19.43|-99.13
20|AGS|Aguascalientes|21.88|-102.29
21|BC|Mexicali|32.62|-115.45
22|BC|Tijuana|32.51|-117.04
23|BCS|La Paz|24.14|-110.31
24|CAM|Campeche|19.83|-90.53
25|COAH|Saltillo|25.42|-101.00
26|COAH|Piedras Negras|28.70|-100.52
27|COAH|Torreón|25.54|-103.41
28|COL|Colima|19.24|-103.72
29|CHIS|Tuxtla Gutiérrez|16.75|-93.12
30|CHIS|Tapachula|14.90|-92.26
31|CHIH|Chihuahua|28.63|-106.07
32|CHIH|Ciudad Juárez|31.69|-106.42
33|CHIH|Delicias|28.19|-105.47
34|DGO|Durango|24.03|-104.65
35|DGO|Gómez Palacio|25.56|-103.50
36|GTO|Irapuato|20.68|-101.35
37|GTO|León|21.12|-101.68
38|GTO|Celaya|20.52|-100.81
39|GRO|Acapulco|16.86|-99.88
40|GRO|Iguala|18.35|-99.54
41|GRO|Tlapa|17.55|-98.58
42|HGO|Pachuca|20.12|-98.73
43|HGO|Tulancingo|20.08|-98.37
44|JAL|Guadalajara|20.67|-103.35
45|JAL|Zapopan|20.72|-103.39
46|JAL|Tequila|20.88|-103.83
47|JAL|Lagos de Moreno|21.35|-101.93
48|JAL|Puerto Vallarta|20.65|-105.23
49|JAL|Ciudad Guzmán|19.70|-103.46
50|MEX|Toluca|19.29|-99.66
51|MEX|Valle de Bravo|19.19|-100.13
52|MEX|Metepec|19.36|-99.45
53|MEX|Naucalpan|19.48|-99.24
54|MEX|Tlalnepantla|19.54|-99.19
55|MEX|Ecatepec|19.60|-99.05
56|MEX|Texcoco|19.40|-98.90
57|MEX|Nezahualcóyotl|19.40|-99.01
58|MICH|Morelia|19.70|-101.19
59|MICH|Zamora|19.98|-102.28
60|MICH|Uruapan|19.42|-102.06
61|MICH|Zitácuaro|19.43|-100.36
62|MOR|Cuernavaca|18.92|-99.23
63|NAY|Tepic|21.50|-104.89
64|NL|Monterrey|25.67|-100.31
65|NL|Sabinas Hidalgo|26.50|-100.18
66|NL|Apodaca|25.75|-100.25
67|NL|Guadalupe|25.68|-100.21
68|OAX|Oaxaca|17.07|-96.72
69|OAX|Huajuapan|17.80|-97.78
70|OAX|Juchitán|16.43|-95.02
71|OAX|Puerto Escondido|15.87|-97.07
72|PUE|Puebla|19.04|-98.20
73|PUE|Zacatlán|19.93|-97.96
74|PUE|Atlixco|18.90|-98.44
75|PUE|Tehuacán|18.46|-97.39
76|QRO|Querétaro|20.59|-100.39
77|QROO|Cancún|21.16|-86.85
78|SLP|San Luis Potosí|22.15|-100.98
79|SLP|Ciudad Valles|21.99|-99.01
80|SIN|Culiacán|24.81|-107.39
81|SIN|Los Mochis|25.79|-108.99
82|SIN|Mazatlán|23.25|-106.41
83|SON|Hermosillo|29.07|-110.96
84|SON|Nogales|31.30|-110.94
85|SON|Ciudad Obregón|27.48|-109.93
86|TAB|Villahermosa|17.99|-92.93
87|TAMPS|Ciudad Victoria|23.74|-99.15
88|TAMPS|Reynosa|26.08|-98.29
89|TAMPS|Tampico|22.25|-97.87
90|TLAX|Tlaxcala|19.32|-98.24
91|VER|Xalapa|19.54|-96.91
92|VER|Tuxpan|20.96|-97.40
93|VER|Poza Rica|20.53|-97.46
94|VER|Córdoba|18.88|-96.93
95|VER|San Andrés Tuxtla|18.45|-95.21
96|VER|Coatzacoalcos|18.13|-94.46
97|YUC|Mérida|20.97|-89.62
98|ZAC|Zacatecas|22.77|-102.58
99|ZAC|Fresnillo|23.17|-102.87"""
cp = {}
for ln in CPS.splitlines():
    r, est, ciu, la, lo = ln.split("|")
    a, b = (r.split("-") + [r])[:2]
    for i in range(int(a), int(b) + 1):
        cp[f"{i:02d}"] = {"estado": est, "ciudad": ciu, "lat": float(la), "lon": float(lo)}

# Canadá: dos primeros caracteres del código postal (o la primera letra si el prefijo no está en la tabla)
CPS_CA = """A|NL|St. John's|47.56|-52.71
A2|NL|Corner Brook|48.95|-57.95
B|NS|Halifax|44.65|-63.58
B1|NS|Sydney|46.14|-60.19
C|PE|Charlottetown|46.24|-63.13
E|NB|Moncton|46.09|-64.78
E2|NB|Saint John|45.27|-66.06
E3|NB|Fredericton|45.96|-66.64
G|QC|Québec|46.81|-71.21
G5|QC|Rimouski|48.45|-68.52
G7|QC|Saguenay|48.43|-71.07
G8|QC|Trois-Rivières|46.34|-72.54
G9|QC|Trois-Rivières|46.34|-72.54
H|QC|Montréal|45.50|-73.57
H7|QC|Laval|45.57|-73.75
J|QC|Longueuil|45.53|-73.52
J1|QC|Sherbrooke|45.40|-71.89
J7|QC|Terrebonne|45.70|-73.65
J8|QC|Gatineau|45.48|-75.70
K|ON|Ottawa|45.42|-75.70
K7|ON|Kingston|44.23|-76.49
K8|ON|Belleville|44.16|-77.38
K9|ON|Peterborough|44.31|-78.32
L|ON|Mississauga|43.59|-79.64
L1|ON|Oshawa|43.90|-78.85
L2|ON|St. Catharines|43.16|-79.24
L3|ON|Markham|43.86|-79.34
L4|ON|Vaughan|43.84|-79.50
L6|ON|Brampton|43.73|-79.76
L7|ON|Burlington|43.33|-79.80
L8|ON|Hamilton|43.26|-79.87
L9|ON|Hamilton|43.26|-79.87
M|ON|Toronto|43.65|-79.38
N|ON|London|42.98|-81.25
N1|ON|Guelph|43.54|-80.25
N2|ON|Kitchener|43.45|-80.49
N3|ON|Brantford|43.14|-80.26
N7|ON|Sarnia|42.97|-82.40
N8|ON|Windsor|42.31|-83.04
N9|ON|Windsor|42.31|-83.04
P|ON|Sudbury|46.49|-81.00
P1|ON|North Bay|46.31|-79.46
P6|ON|Sault Ste. Marie|46.52|-84.35
P7|ON|Thunder Bay|48.38|-89.25
R|MB|Winnipeg|49.90|-97.14
R7|MB|Brandon|49.85|-99.95
S|SK|Saskatoon|52.13|-106.67
S4|SK|Regina|50.45|-104.62
T|AB|Calgary|51.05|-114.07
T1|AB|Lethbridge|49.69|-112.84
T4|AB|Red Deer|52.27|-113.81
T5|AB|Edmonton|53.55|-113.49
T6|AB|Edmonton|53.55|-113.49
T7|AB|Edmonton|53.55|-113.49
T8|AB|Edmonton|53.55|-113.49
T9|AB|Fort McMurray|56.73|-111.38
V|BC|Vancouver|49.28|-123.12
V1|BC|Kelowna|49.89|-119.50
V2|BC|Kamloops|50.67|-120.33
V3|BC|Surrey|49.19|-122.85
V4|BC|Delta|49.09|-123.03
V7|BC|North Vancouver|49.32|-123.07
V8|BC|Victoria|48.43|-123.37
V9|BC|Nanaimo|49.17|-123.94
X|NT|Yellowknife|62.45|-114.37
Y|YT|Whitehorse|60.72|-135.06"""
cp_ca = {}
for ln in CPS_CA.splitlines():
    k, est, ciu, la, lo = ln.split("|")
    cp_ca[k] = {"estado": est, "ciudad": ciu, "lat": float(la), "lon": float(lo)}

# Cada campo acepta su nombre SAP y alias en español e inglés
esquema = {
 "clientes": {"KUNNR": ["cliente","no_cliente","customer","customer_no"], "NAME1": ["nombre","razon_social","name"],
              "KUNWE": ["destinatario","id_direccion","ship_to","ship_to_id"], "STRAS": ["calle","direccion","domicilio","street","address"],
              "ORT01": ["ciudad","poblacion","city"], "REGIO": ["estado","region","provincia","province","state"], "PSTLZ": ["cp","codigo_postal","postal_code","zip"]},
 "inventario": {"MATNR": ["material","codigo","codigo_sap","sap_code"], "MAKTX": ["descripcion","texto_material","description"],
                "WERKS": ["almacen","centro","warehouse","plant"], "LGORT": ["ubicacion","almacen_sap","storage_location"],
                "LABST": ["existencia","stock","cantidad","libre_utilizacion","quantity","unrestricted"], "MEINS": ["unidad","um","unit","uom"]},
 "precios": {"MATNR": ["material","codigo"], "KUNNR": ["cliente","customer"], "KBETR": ["precio","importe","price"],
             "KONWA": ["moneda","currency"], "DATAB": ["valido_desde","desde","valid_from"], "DATBI": ["valido_hasta","hasta","valid_to"]},
 "xref": {"KUNNR": ["cliente","customer"], "KDMAT": ["material_cliente","codigo_cliente","customer_material"], "MATNR": ["material","codigo_sap","sap_material"]},
 "almacenes": {"WERKS": ["almacen","centro","warehouse","plant"], "NAME1": ["nombre","name"], "ORT01": ["ciudad","city"],
               "PSTLZ": ["cp","codigo_postal","postal_code","zip"], "LAT": ["latitud","latitude"], "LON": ["longitud","lng","longitude"]},
 "estatus": {"ID_PEDIDO": ["pedido","id_pedido","order","order_id"], "BSTKD": ["pedido_cliente","orden_compra","customer_po","po"], "KUNNR": ["cliente","customer"],
             "VBELN": ["pedido_sap","documento_sap","sap_order","sales_order"], "STATUS": ["estatus","estado","status"],
             "FECHA": ["fecha","fecha_hora","date","timestamp"], "TEXTO": ["texto","comentario","mensaje","text","comment"]},
 "pedidos": {"KUNNR": ["cliente","customer"], "BSTKD": ["pedido_cliente","orden_compra","oc","customer_po","po"],
             "MATERIAL": ["material","matnr","codigo","kdmat","item"], "CANTIDAD": ["cantidad","kwmeng","qty","quantity"],
             "DIRECCION": ["direccion_entrega","direccion","kunwe","destinatario","entrega","delivery_address","ship_to","address"],
             "WERKS": ["almacen","centro","warehouse","plant"]},
}
numericos = ["LABST", "KBETR", "CANTIDAD", "LAT", "LON"]
requeridos = {"clientes": ["KUNNR"], "inventario": ["MATNR","WERKS"], "precios": ["MATNR","KBETR"],
              "xref": ["KUNNR","KDMAT","MATNR"], "almacenes": ["WERKS"], "estatus": ["STATUS"], "pedidos": ["KUNNR","MATERIAL","CANTIDAD"]}
estatus_flujo = ["BORRADOR","ENVIADO_SAP","CREADO","EN_SURTIDO","EMBARCADO","ENTREGADO","FACTURADO"]

# ---- Datos de demostración: empresas ficticias en Canadá, importes en CAD ----
def C(k, n, we, s, o, r, p): return {"KUNNR": k, "NAME1": n, "KUNWE": we, "STRAS": s, "ORT01": o, "REGIO": r, "PSTLZ": p}
clientes = [
 C("100010","Northline Fasteners Ltd.","","480 Carlaw Ave","Toronto","ON","M4M 2T3"),
 C("100010","Northline Fasteners - Ottawa Branch","100011","2255 St. Laurent Blvd","Ottawa","ON","K1G 4K3"),
 C("100020","Quincaillerie Laurentides Inc.","","9150 boul. de l'Acadie","Montréal","QC","H4N 2T2"),
 C("100020","Quincaillerie Laurentides - Québec DC","100021","1175 av. Galilée","Québec","QC","G1P 4G1"),
 C("100030","Pacific Coast Building Supplies Ltd.","","1575 Venables St","Vancouver","BC","V5L 2G8"),
 C("100030","Pacific Coast Building Supplies - Kelowna","100031","1960 Windsor Rd","Kelowna","BC","V1Y 4R5"),
 C("100040","Prairie Industrial Supply Ltd.","","2835 23 St NE","Calgary","AB","T2E 7A4"),
 C("100040","Prairie Industrial Supply - Edmonton Plant","100041","17404 111 Ave NW","Edmonton","AB","T5S 0A2"),
 C("100040","Prairie Industrial Supply - Winnipeg Plant","100042","1425 Erin St","Winnipeg","MB","R3E 2S9"),
 C("100050","Maritime Tool & Fastener Co.","","3695 Kempt Rd","Halifax","NS","B3K 4X6"),
]
almacenes = [
 {"WERKS":"1000","NAME1":"Toronto DC","ORT01":"Mississauga","PSTLZ":"L5T 2N5","LAT":43.66,"LON":-79.68},
 {"WERKS":"2000","NAME1":"Montréal DC","ORT01":"Laval","PSTLZ":"H7L 5A7","LAT":45.60,"LON":-73.75},
 {"WERKS":"3000","NAME1":"Calgary DC","ORT01":"Calgary","PSTLZ":"T2C 4T8","LAT":50.98,"LON":-113.98},
 {"WERKS":"4000","NAME1":"Vancouver DC","ORT01":"Delta","PSTLZ":"V4G 1E2","LAT":49.14,"LON":-123.01},
]
mats = [("10000101","Hex bolt 1/2 x 2 in Gr 5","BX",185.50,[420,300,650,80]),
        ("10000102","Hex nut 1/2 in Gr 5","BX",92.00,[500,0,720,60]),
        ("10000205","Wedge anchor 3/8 x 3 in","BX",264.75,[120,210,35,0]),
        ("10000310","Metal cut-off wheel 4-1/2 in","EA",18.90,[2400,1800,3100,600]),
        ("10000311","Grinding wheel 7 in","EA",46.30,[0,900,1400,150]),
        ("10000420","Welding electrode E6013 1/8 in","KG",58.40,[800,650,90,300]),
        ("10000550","Electrical tape black 19 mm","EA",14.20,[5000,4200,6100,1200]),
        ("10000675","Cobalt drill bit 1/4 in","EA",39.80,[350,20,480,0])]
inventario, precios = [], []
for m, d, u, p, st in mats:
    for a, q in zip(almacenes, st):
        inventario.append({"MATNR": m, "MAKTX": d, "WERKS": a["WERKS"], "LGORT": "0001", "LABST": q, "MEINS": u})
    precios.append({"MATNR": m, "KUNNR": "", "KBETR": p, "KONWA": "CAD", "DATAB": "20260101", "DATBI": "99991231"})
precios += [{"MATNR":"10000101","KUNNR":"100040","KBETR":171.00,"KONWA":"CAD","DATAB":"20260701","DATBI":"20261231"},
            {"MATNR":"10000310","KUNNR":"100010","KBETR":17.25,"KONWA":"CAD","DATAB":"20260701","DATBI":"20261231"}]
xref = [{"KUNNR":"100040","KDMAT":"PIS-BOLT-050","MATNR":"10000101"},
        {"KUNNR":"100040","KDMAT":"PIS-NUT-050","MATNR":"10000102"},
        {"KUNNR":"100020","KDMAT":"QL-7731","MATNR":"10000310"}]
pedidos_demo = [
 {"KUNNR":"100040","BSTKD":"PO-45001872","DIRECCION":"100041","posiciones":[{"MATERIAL":"PIS-BOLT-050","CANTIDAD":200},{"MATERIAL":"10000102","CANTIDAD":200},{"MATERIAL":"10000205","CANTIDAD":30}]},
 {"KUNNR":"100010","BSTKD":"NF-2026-0931","DIRECCION":"","posiciones":[{"MATERIAL":"10000310","CANTIDAD":1200},{"MATERIAL":"10000311","CANTIDAD":300}]},
 {"KUNNR":"100030","BSTKD":"PC-88214","DIRECCION":"845 Douglas St, Victoria, BC V8W 2B6","posiciones":[{"MATERIAL":"10000550","CANTIDAD":900},{"MATERIAL":"10000675","CANTIDAD":40}]},
 {"KUNNR":"100050","BSTKD":"MTF-11207","DIRECCION":"","posiciones":[{"MATERIAL":"10000420","CANTIDAD":250}]},
]
# Nombres de estatus [español, inglés] y mensajes traducibles (fuente: app/mensajes.json)
estatus_nombres = {"BORRADOR": ["Borrador", "Draft"], "ENVIADO_SAP": ["Enviado a SAP", "Sent to SAP"], "CREADO": ["Creado en SAP", "Created in SAP"],
                   "EN_SURTIDO": ["En surtido", "Picking"], "EMBARCADO": ["Embarcado", "Shipped"], "ENTREGADO": ["Entregado", "Delivered"],
                   "FACTURADO": ["Facturado", "Invoiced"], "RECHAZADO": ["Rechazado", "Rejected"], "BLOQUEADO": ["Bloqueado", "Blocked"], "CANCELADO": ["Cancelado", "Cancelled"]}
mensajes = json.loads((R / "app" / "mensajes.json").read_text("utf-8"))
out = {"mensajes": mensajes, "estatus_nombres": estatus_nombres, "cp": cp, "cp_ca": cp_ca, "esquema": esquema, "numericos": numericos, "requeridos": requeridos, "estatus_flujo": estatus_flujo,
       "demo": {"clientes": clientes, "almacenes": almacenes, "inventario": inventario, "precios": precios, "xref": xref, "pedidos": pedidos_demo}}
(R / "app" / "shared.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")
# archivos de ejemplo
import csv, io
def w_csv(name, rows):
    f = io.StringIO(); w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    (R / "ejemplos" / name).write_text(f.getvalue(), "utf-8")
def w_json(name, obj): (R / "ejemplos" / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), "utf-8")
w_json("clientes_sap.json", clientes); w_csv("inventario_sap.csv", inventario); w_json("precios_sap.json", precios)
w_csv("xref_material_cliente.csv", xref); w_json("almacenes.json", almacenes)
w_json("pedido_entrada.json", {"customer":"100040","customer_po":"PO-45001999","delivery_address":"100042",
        "items":[{"material":"PIS-BOLT-050","quantity":120},{"material":"10000420","quantity":60}]})
w_csv("pedidos_entrada.csv", [
 {"customer":"100020","customer_po":"QL-PO-5521","material":"QL-7731","quantity":500,"delivery_address":"100021"},
 {"customer":"100020","customer_po":"QL-PO-5521","material":"10000675","quantity":25,"delivery_address":"100021"},
 {"customer":"100050","customer_po":"MTF-11300","material":"10000550","quantity":300,"delivery_address":"45 Wyse Rd, Dartmouth, NS B2Y 3Z1"}])
w_json("estatus_sap.json", [
 {"ID_PEDIDO":"PED-000001","VBELN":"0080012345","STATUS":"CREADO","FECHA":"2026-11-16T09:10:00","TEXTO":"Sales order created"},
 {"ID_PEDIDO":"PED-000001","VBELN":"0080012345","STATUS":"EN_SURTIDO","FECHA":"2026-11-16T11:40:00","TEXTO":"Picking started"},
 {"BSTKD":"NF-2026-0931","KUNNR":"100010","VBELN":"0080012346","STATUS":"EMBARCADO","FECHA":"2026-11-16T16:05:00","TEXTO":"Waybill 7781234"}])
print("ok", len(cp), "prefijos MX,", len(cp_ca), "prefijos CA")
