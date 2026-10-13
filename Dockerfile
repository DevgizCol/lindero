# Lindero: plataforma web + motor cartografico y planimetria predial.
# Compatible con Hugging Face Spaces (0$ / 16GB RAM), Render, y contenedores Docker.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    PLANOS_DATOS=/datos \
    PORT=7860 \
    PLANOS_MODO=peticion

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar modulos del proyecto
COPY motor ./motor
COPY web ./web
COPY config ./config
COPY base ./base

# Permisos para el almacenamiento de pedidos y cache
RUN mkdir -p /datos /tmp/matplotlib && chmod -R 777 /datos /tmp/matplotlib

VOLUME /datos
EXPOSE 7860

# Iniciar servidor Gunicorn en el puerto asignado (7860 por defecto en Hugging Face Spaces)
CMD exec gunicorn --bind 0.0.0.0:${PORT:-7860} --workers 1 --threads 8 --timeout 900 web.app:app
