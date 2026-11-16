# Subir a GitHub y desplegar en Render

La configuración actual (`render.yaml`) es para el **plan gratuito de Render con el SFTP desactivado**: sirve para probar
el flujo con usuarios reales. La sección 4 explica cómo pasar a producción con SFTP.

## 1. Repositorio en GitHub (desde el navegador, sin instalar nada)

1. En github.com: **New repository** → nombre `pedidos-sap` → **Private** → sin README ni .gitignore → **Create repository**.
2. En la página del repositorio vacío: **uploading an existing file**.
3. Descomprime `pedidos-sap.zip` y arrastra **el contenido** de la carpeta `pedidos-sap` (no la carpeta misma), de modo que
   `render.yaml`, `requirements.txt` y la carpeta `app/` queden en la raíz del repositorio.
4. Revisa que también subieron `.gitignore` y la carpeta `.github/` (en algunos equipos los nombres que empiezan con punto
   están ocultos). Si faltan, la aplicación funciona igual; solo se pierden las pruebas automáticas y el filtro de archivos.
5. **Commit changes**.

No subas nunca `pedidos.db`, llaves privadas ni contraseñas: `.gitignore` ya los excluye y las contraseñas van en Render.

## 2. Servicio en Render (plan gratuito)

1. En dashboard.render.com: **New → Blueprint** → conecta tu cuenta de GitHub y elige el repositorio `pedidos-sap`.
2. Render lee `render.yaml` y te pide dos valores: `APP_USER` y `APP_PASSWORD`, usuario y contraseña del **administrador**
   (usa una contraseña larga).
3. **Apply**. Al terminar, la aplicación queda en `https://pedidos-sap-xxxx.onrender.com`.
4. Entra con el administrador. La aplicación arranca con los datos de ejemplo de Canadá (`CARGAR_DEMO=1`). Para usar tus
   datos, carga los archivos de SAP en **Intercambio con SAP** (formatos en **Formatos de archivo**).
5. En **Usuarios** crea un usuario con perfil Cliente por cada cliente que vaya a probar.
6. Para probar la API, entra con el usuario cliente, ve a **API** y genera una llave. La dirección y los ejemplos
   aparecen en esa misma pantalla; la documentación interactiva está en `https://pedidos-sap-xxxx.onrender.com/api/v1/docs`.

Cada cambio que subas a GitHub se despliega solo.

### Cómo funciona sin SFTP (`SFTP_HABILITADO=0`)

- No hay lecturas programadas ni conexión con SAP; la pantalla de conexión no aparece.
- Clientes, inventario, precios, almacenes y estatus se cargan a mano en **Intercambio con SAP**.
- Al enviar un pedido queda en «Enviado a SAP» y se genera su JSON. El administrador o ventas lo descargan desde el
  monitor con **Ver JSON para SAP**. El cliente no ve ese paso.

## 3. Límites del plan gratuito

- **Se duerme**: tras 15 minutos sin visitas el servicio se suspende; la siguiente visita tarda cerca de un minuto.
- **Sin disco**: la base SQLite se borra en cada suspensión, reinicio o despliegue. Se pierden los pedidos, los usuarios
  creados en la aplicación, sus llaves de API y los datos cargados a mano. Solo se conserva el administrador de `APP_USER` / `APP_PASSWORD`, y
  con `CARGAR_DEMO=1` vuelven los datos de ejemplo.
- **Uso adecuado**: demostraciones y pruebas de flujo en una sola sesión. No para pedidos reales.
- **API**: la primera llamada después de que el servicio se durmió tarda cerca de un minuto (el programa de ejemplo
  espera hasta dos minutos). Una llave generada deja de existir cuando la base se reinicia: genera otra.

## 4. Pasar a producción con SFTP

1. En `render.yaml` cambia el servicio así:

   ```yaml
       plan: starter
       envVars:
         - key: PYTHON_VERSION
           value: 3.12.7
         - key: SFTP_HABILITADO
           value: "1"
         - key: CARGAR_DEMO
           value: "0"
         - key: PEDIDOS_DB
           value: /var/data/pedidos.db
         - key: APP_USER
           sync: false
         - key: APP_PASSWORD
           sync: false
         - key: SFTP_PASSWORD     # contraseña del SFTP de SAP (vacía si se usa llave)
           sync: false
       disk:
         name: datos
         mountPath: /var/data
         sizeGB: 1
   ```

2. Si el servicio ya existe, cambia también el tipo de instancia en el panel de Render (**Settings → Instance Type**):
   en un servicio existente Render conserva el plan que ya tiene aunque cambie `render.yaml`.
3. Entra con el administrador, ve a **Intercambio con SAP**, elige el medio **SFTP**, captura servidor, puerto, usuario,
   rutas y minutos de lectura, guarda y pulsa **Probar conexión**. La contraseña puede quedar vacía: se toma de
   `SFTP_PASSWORD`.

Lo que hay que saber en producción:

- **Una sola instancia**: el disco y el programador de lecturas exigen una instancia. No actives autoescalado.
- **Acceso al SFTP de SAP**: si el SFTP filtra por IP, pide que autoricen las direcciones IP de salida del servicio
  (consulta en el panel de Render cuáles son para tu región). Verifica también que el puerto del SFTP sea alcanzable desde internet.
- **Llave privada**: si el SFTP usa llave, súbela como *Secret File* en Render y escribe su ruta
  (`/etc/secrets/<nombre>`) en «Llave privada».
- **Huella del servidor**: en Render no hay `known_hosts` persistente; deja activado «Aceptar servidores sin huella registrada».
- **Respaldo**: guarda una copia de `pedidos.db` periódicamente.
