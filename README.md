---
title: Lindero - Planos Prediales y SIG Catastral
emoji: 🗺️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Lindero PRO · Spatial Engine

[![CI & Keep-Alive de Producción](https://github.com/DevgizCol/lindero/actions/workflows/ci.yml/badge.svg)](https://github.com/DevgizCol/lindero/actions/workflows/ci.yml)
[![Render Status](https://img.shields.io/badge/Render-Live%20Deploy-00f0ff?logo=render)](https://lindero.onrender.com/)
[![IGAC CTM12](https://img.shields.io/badge/IGAC-MAGNA--SIRGAS%20CTM12-0066ff)](https://lindero.onrender.com/)
[![Habeas Data](https://img.shields.io/badge/Seguridad-Ley%201581%20Habeas%20Data-10b981)](#)

Plataforma empresarial de inteligencia espacial y automatización cartográfica. A partir del Excel de campo y el plano DXF, **Lindero PRO** proyecta cada predio sobre la base catastral oficial del IGAC en CTM12 (EPSG:9377), calcula cuadros de coordenadas elipsoidales, rumbos y colindantes oficiales, y emite certificados en PDF, Shapefiles con 25 campos estandarizados e informes de revisión en segundos.

Un desarrollo de **DevGiz Engineering** ([https://devgiz.vercel.app/](https://devgiz.vercel.app/)).

## Qué hay aquí

| Carpeta | Qué es |
|---|---|
| `motor/` | El motor: referencia catastral, polígonos, ubicación, capas, colindantes y el PDF del certificado |
| `base/` | La base catastral empacada de cada municipio (sin nombres ni cédulas) |
| `web/` | La plataforma de autoservicio con pago anticipado (Flask) |
| `plugin/` | Parche y ZIP del plugin de QGIS *Colindante Elite* con el motor nuevo de colindantes |
| `config/` | Un JSON por municipio (rutas de la base catastral, proyecto de QGIS, plantilla) |
| `tests/` | Validaciones contra entregas reales y pruebas sintéticas sobre la base catastral |

## Requisitos

- Python 3.11 o superior y `pip install -r requirements.txt`. Nada más: **no necesita QGIS ni GDAL instalados**.
  El certificado lo dibuja `motor/plano_pdf.py` y los shapefile los escribe `motor/shp.py`, ambos en Python puro.
- La base catastral empacada del municipio en `base/<municipio>/` (17 MB para Malambo). Se genera una vez, en el
  equipo que tiene la geodatabase y el R1, con:

  ```bat
  python -m motor.empacar_base malambo
  ```

  Del R1 solo se guarda dirección → código predial; nombres y cédulas no salen de ese equipo.

QGIS queda como opción: con `"salida": "qgis"` en `config/<municipio>.json` el PDF se genera con el proyecto y la
plantilla `.qpt` originales (requiere QGIS LTR por OSGeo4W).

## Llevarlo a un servidor

La imagen (`Dockerfile`) sirve para cualquier proveedor de contenedores. Necesita 1 GB de memoria, un solo proceso
y una carpeta persistente en `/datos` para los pedidos.

### Google Cloud Run (sin servidor que mantener)

Cloud Run solo da procesador mientras atiende una petición y no tiene disco, por eso:

- `PLANOS_MODO=peticion` (ya viene en la imagen): la página del pedido lanza el trabajo y la petición dura lo que tarde el motor.
- Los pedidos se guardan en un bucket de Cloud Storage montado como volumen en `/datos`.

Configuración del servicio: región `us-east1`, 1 GiB de memoria, 1 instancia como máximo, tiempo de espera 900 s,
procesador solo durante las peticiones, acceso sin autenticación, volumen de Cloud Storage en `/datos`, y las
variables `PLANOS_ADMIN_CLAVE`, `PLANOS_SECRETO` y `PLANOS_HTTPS=1`. Cada pedido puede pesar hasta 30 MB
(límite de Cloud Run por petición).

### Servidor propio o máquina virtual

```bat
docker build -t lindero .
docker run -p 8080:8080 -v lindero_datos:/datos -e PLANOS_ADMIN_CLAVE=... -e PLANOS_SECRETO=... -e PLANOS_HTTPS=1 lindero
```

Un trabajo de 22 predios usa unos 260 MB de memoria y tarda cerca de 20 s.

## Uso del motor

```bat
:: Flujo completo: capas + colindantes + un PDF por NODO + ZIP
planos.bat planos --excel "LEVANTAMIENTO.xlsx" --dxf "PLANO.dxf" --salida "trabajos\barrio" --nombre BR_BARRIO

:: Con otra firma, o solo una vista previa con marca de agua
planos.bat planos --excel X.xlsx --dxf P.dxf --salida trabajos\x --firma firma.png --firmante "Top. Nombre\nT.P. 00-0000"
planos.bat planos --excel X.xlsx --dxf P.dxf --salida trabajos\x --previa --sin-firma

:: Solo la referencia catastral de un Excel (más un KML con los casos por revisar)
planos.bat refcat --excel "DIRECCIONES.xlsx" --salida "trabajos\ref"
```

Cada trabajo deja `01.SHAPEFILE/` (LEVANTAMIENTO_01, COTAS, COORDENADAS), `02.PDF/`, el ZIP,
`vista_general.png` e `INFORME_REVISION.xlsx` con lo que conviene revisar a mano.

### Qué debe traer el cliente

- **Excel** con las columnas NODO y dirección; si trae el código predial, se respeta.
- **DXF** con cada predio como figura cerrada y su NODO escrito dentro (o la cartera de campo con el
  código de cada punto). Si el plano viene en CTM12 u origen Bogotá, se detecta solo.

## Plataforma web

```bat
web\iniciar_web.bat          :: http://127.0.0.1:5080
```

Subir archivos → vista previa gratis con marca de agua → pago → generación → revisión si hace falta →
descarga. El panel de operación está en `/admin`.

| Variable | Para qué |
|---|---|
| `PLANOS_ADMIN_CLAVE` | Clave del panel `/admin` (en desarrollo puede ir en `web/.env.local`) |
| `PLANOS_SECRETO` | Secreto de las sesiones |
| `PLANOS_HTTPS=1` | Marca las cookies como seguras cuando se publica detrás de HTTPS |
| `WOMPI_LLAVE_PUBLICA`, `WOMPI_SECRETO_INTEGRIDAD`, `WOMPI_SECRETO_EVENTOS` | Pago en línea (activar en `web/config.json`) |

Precio, textos de pago, cifras de la portada y límites de uso están en `web/config.json`.

## Validación

| Prueba | Resultado | Cómo repetirla |
|---|---|---|
| Colindantes contra la entrega de El Tesoro corregida a mano | 145 de 147 iguales; los 2 restantes están intercambiados en la entrega | `python tests/eval_colindantes.py` |
| Mismo caso con la lógica anterior del plugin | 49 de 147 | `python tests/plugin_viejo.py` |
| Colindantes sobre 400 predios de la base desplazados al azar | 99,7 % de 2.446 linderos | `python tests/sintetico.py` |
| Ubicación de El Tesoro frente a la hecha a mano | 6 cm de diferencia (con los códigos del Excel) | `python tests/eval_ubicacion.py` |
| Ubicación sobre 40 grupos de predios corridos hasta 4 m | error máximo 5 cm con códigos; sin códigos falla 1 de cada 5 | `python tests/sintetico_ubicacion.py` |
| Referencia catastral por placa o R1 (confianza ALTA) | 28 de 29 iguales a las entregadas; la otra coincide con una entrega posterior | `python tests/eval_refcat.py` |
| Referencia por interpolación (placa oculta) | acierta el predio en 63 %; entre los 3 primeros candidatos en 77 % | `python tests/loo_refcat.py` |
| Flujo completo sin QGIS ni GDAL del sistema | 22 PDF en 21 s; shapefile con los mismos campos y tipos que la entrega | `python tests/prueba_sin_qgis.py` |
| Recorrido completo de la web | 19 comprobaciones | `python tests/prueba_web.py` (con el servidor arriba) |

Las pruebas leen los datos del municipio desde las rutas de `config/malambo.json`; esos datos no van en el repositorio.

## Pendiente antes de abrir al público

- Probar Wompi con llaves reales (la integración está escrita, no probada contra Wompi).
- Correos automáticos al cliente (hoy el aviso depende del enlace del pedido).
- Política de tratamiento de datos (los Excel traen nombres y cédulas) y plazo de borrado de pedidos.
- Escaneo de seguridad dinámico (HawkScan) y publicación detrás de HTTPS.
- Construir y probar la imagen de Docker (el `Dockerfile` está escrito; en el equipo de desarrollo no había Docker).
- Cargar la base catastral de cada municipio nuevo.

## Datos que nunca van al repositorio

La geodatabase catastral, el R1/R2, los Excel y planos de clientes, `web/datos/` y `trabajos/`.
