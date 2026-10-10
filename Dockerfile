# Lindero: plataforma web + motor, sin QGIS.
# Las ruedas de pyogrio, shapely y pyproj ya traen GDAL, GEOS y PROJ: no hace falta instalar nada del sistema.
#
#   python -m motor.empacar_base malambo        (una vez, en el equipo que tiene la geodatabase)
#   docker build -t lindero .
#   docker run -p 8080:8080 -v lindero_datos:/datos -e PLANOS_ADMIN_CLAVE=... -e PLANOS_SECRETO=... lindero
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    PLANOS_DATOS=/datos

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY motor ./motor
COPY web ./web
COPY config ./config
COPY base ./base

RUN useradd --create-home lindero && mkdir -p /datos && chown -R lindero:lindero /datos /app
USER lindero
VOLUME /datos
EXPOSE 8080

# Un solo proceso: la cola de pedidos vive en memoria. Los hilos atienden las páginas mientras el motor trabaja.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "180", "web.app:app"]
