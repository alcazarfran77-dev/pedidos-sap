# Subir a GitHub y desplegar en Render

## 1. Repositorio en GitHub (desde el navegador, sin instalar nada)

1. En github.com: **New repository** → nombre `pedidos-sap` → **Private** → sin README ni .gitignore → **Create repository**.
2. En la página del repositorio vacío: **uploading an existing file**.
3. Descomprime `pedidos-sap.zip` y arrastra **el contenido** de la carpeta `pedidos-sap` (no la carpeta misma), de modo que
   `render.yaml`, `requirements.txt` y la carpeta `app/` queden en la raíz del repositorio.
4. Revisa que también subieron `.gitignore` y la carpeta `.github/` (en algunos equipos los nombres que empiezan con punto
   están ocultos). Si faltan, la aplicación funciona igual; solo se pierden las pruebas automáticas y el filtro de archivos.
5. **Commit changes**.

No subas nunca `pedidos.db`, llaves privadas ni contraseñas: `.gitignore` ya los excluye y las contraseñas van en Render.

## 2. Servicio en Render

1. En dashboard.render.com: **New → Blueprint** → conecta tu cuenta de GitHub y elige el repositorio `pedidos-sap`.
2. Render lee `render.yaml` y te pide tres valores:
   - `APP_USER` y `APP_PASSWORD`: usuario y contraseña del **administrador** (usa una contraseña larga). Los demás
     usuarios se crean después, dentro de la aplicación.
   - `SFTP_PASSWORD`: contraseña del SFTP de SAP. Si entras con llave, déjala vacía.
3. **Apply**. Al terminar, la aplicación queda en `https://pedidos-sap-xxxx.onrender.com`.
4. Entra con el administrador, ve a **Intercambio con SAP**, elige el medio **SFTP**, captura servidor, puerto,
   usuario, rutas y minutos de lectura, guarda y pulsa **Probar conexión**. El campo de contraseña puede quedar vacío:
   se toma de `SFTP_PASSWORD`.

Cada cambio que subas a GitHub se despliega solo.

5. Cuando ya hayan llegado los clientes de SAP, ve a **Usuarios** y crea un usuario con perfil Cliente por cada cliente
   (o varios por cliente), ligado a su número de cliente SAP. Entrégales la dirección, su usuario y su contraseña.

## 3. Lo que hay que saber de Render

- **Plan**: `render.yaml` usa el plan de pago más pequeño (`starter`) con un disco de 1 GB en `/var/data`, donde vive la base
  `pedidos.db`. Con el plan gratuito el servicio se duerme tras 15 minutos sin visitas (y deja de leer el SFTP) y pierde la
  base en cada reinicio, así que no sirve para este uso.
- **Una sola instancia**: el disco y el programador de lecturas exigen una instancia. No actives autoescalado.
- **Reinicio en cada despliegue**: con disco, el servicio se detiene unos segundos al desplegar. Las lecturas pendientes se
  hacen al volver.
- **Acceso al SFTP de SAP**: si el SFTP filtra por IP, pide que autoricen las direcciones IP de salida del servicio
  (consulta en el panel de Render cuáles son para tu región). Verifica también que el puerto del SFTP sea alcanzable desde internet.
- **Llave privada**: si el SFTP usa llave, súbela como *Secret File* en Render y escribe su ruta
  (`/etc/secrets/<nombre>`) en «Llave privada».
- **Huella del servidor**: tras la primera conexión correcta, conviene desactivar «Aceptar servidores sin huella registrada»
  solo si registras la huella en el servidor; en Render no hay `known_hosts` persistente, así que por ahora déjalo activado.
- **Respaldo**: revisa en la documentación de Render qué copias hace del disco y, además, guarda una copia de
  `pedidos.db` periódicamente.
