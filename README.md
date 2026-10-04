# Ai_project-

## SITCO

SITCO permite solicitar el transporte de compras grandes del supermercado hasta
el domicilio del cliente y consultar el estado de una solicitud mediante su
código y teléfono.

### Ejecutar localmente

Requiere Python 3.10 o posterior; no necesita instalar paquetes adicionales.

```powershell
python recommendation.py
```

Abre `http://127.0.0.1:8000` en el navegador. La primera ejecución crea la base
de datos SQLite `sitco.db` junto al archivo. Se puede cambiar el host, puerto o
ruta de la base con las variables de entorno `SITCO_HOST`, `SITCO_PORT` y
`SITCO_DATABASE`.

La API expone `POST /api/requests` para crear solicitudes y
`GET /api/requests/{codigo}?phone={telefono}` para consultar su estado. Las
solicitudes comienzan como `solicitado`; la confirmación y actualización de
estados por personal del supermercado todavía no están incluidas en esta
primera versión.